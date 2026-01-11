from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from pymongo import MongoClient
import time
import re
from dotenv import load_dotenv
load_dotenv()

# MongoDB connection
MONGODB_URI = os.getenv('MONGODB_URI')
client = MongoClient(MONGODB_URI)
db = client['thrifttinderDB']
collection = db['listings']

def clean_price(price_text):
    """Convert '$25.00' to 25.00"""
    try:
        price_str = re.sub(r'[^\d.]', '', price_text)
        return float(price_str) if price_str else 0.0
    except:
        return 0.0

def scrape_page(driver, category):
    """Scrape current page and return products"""
    
    try:
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'img[src*="media-photos.depop.com"]')))
    except:
        return []
    
    # Scroll to load images
    for _ in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
    
    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')
    
    all_images = soup.find_all('img')
    all_prices = soup.select('.styles_price__H8qdh:not(.styles_discountedFullPrice__JTi1d)')
    sizes = soup.find_all(class_='styles_sizeAttributeText__r9QJj')
    all_names = soup.select('.styles_productAttributes__nt3TO > p:last-child')

    products = []
    price_index = 0
    size_index = 0
    name_index = 0
    
    for img in all_images:
        img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
        if img_url and 'media-photos.depop.com/b1/' in img_url and 'P8' in img_url:
            if '/medium/' in img_url:
                img_url = img_url.replace('/medium/', '/large/')
            
            parent_link = img.find_parent('a', href=True)
            
            product_url = 'N/A'
            if parent_link:
                product_url = parent_link.get('href')
                if product_url and not product_url.startswith('http'):
                    product_url = 'https://www.depop.com' + product_url
            
            price = 'N/A'
            if parent_link:
                price_elem = parent_link.select_one('.styles_price__H8qdh:not(.styles_discountedFullPrice__JTi1d)')
                if price_elem:
                    price = price_elem.text.strip()
            
            if price == 'N/A':
                container = img.find_parent('div')
                for _ in range(5):
                    if container:
                        price_elem = container.select_one('.styles_price__H8qdh:not(.styles_discountedFullPrice__JTi1d)')
                        if price_elem:
                            price = price_elem.text.strip()
                            break
                        container = container.find_parent('div')
            
            if price == 'N/A' and price_index < len(all_prices):
                price = all_prices[price_index].text.strip()
                price_index += 1
            
            size = 'N/A'
            if size_index < len(sizes):
                size = sizes[size_index].text.strip()
                size_index += 1

            name = 'N/A'
            if name_index < len(all_names): 
                name = all_names[name_index].text.strip()
                name_index += 1

            products.append({
                'name': name,
                'url': product_url,
                'image': img_url,
                'price': clean_price(price),
                'size': size,
                'category': category
            })
    
    return products

def scrape_urls(urls, category, target_items=125):
    """Scrape from hardcoded URL list"""
    
    chrome_options = Options()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled") 
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"]) 
    chrome_options.add_experimental_option("useAutomationExtension", False) 
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )
    
    all_products = []
    seen_urls = set()
    
    try:
        print(f"  📜 Scraping {len(urls)} search URLs to reach {target_items} items...")
        
        for idx, url in enumerate(urls, 1):
            if len(all_products) >= target_items:
                print(f"    ✅ Reached target of {target_items} items!")
                break
            
            search_term = url.split('q=')[1] if 'q=' in url else f"search_{idx}"
            print(f"    [{idx}/{len(urls)}] {search_term[:40]}...")
            
            driver.get(url)
            time.sleep(2)
            
            page_products = scrape_page(driver, category)
            
            new_count = 0
            for product in page_products:
                if product['url'] != 'N/A' and product['url'] not in seen_urls:
                    seen_urls.add(product['url'])
                    all_products.append(product)
                    new_count += 1
            
            print(f"      +{new_count} items (total: {len(all_products)})")
            time.sleep(1)
        
        # Check database for duplicates
        new_products = []
        duplicate_count = 0
        
        for product in all_products:
            existing = collection.find_one({'url': product['url']})
            if not existing:
                new_products.append(product)
            else:
                duplicate_count += 1
        
        print(f"\n{'='*50}")
        print(f"Category: {category}")
        print(f"Total unique scraped: {len(all_products)}")
        print(f"Duplicates in DB: {duplicate_count}")
        print(f"New items to add: {len(new_products)}")
        print(f"{'='*50}\n")
        
        if new_products:
            result = collection.insert_many(new_products)
            print(f"✅ Saved {len(result.inserted_ids)} NEW items")
        else:
            print(f"⚠️ No new items")
        
        for idx, product in enumerate(new_products[:3], 1):
            print(f"{idx}. {product['name']}: ${product['price']:.2f}")
        
        if len(new_products) > 3:
            print(f"... and {len(new_products) - 3} more")
        
        return {
            'products': new_products,
            'category': category,
            'duplicates': duplicate_count
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None
        
    finally:
        driver.quit()


# HARD-CODED SEARCH URLS
search_urls = {
    "mens_shirts": [
        "https://www.depop.com/search/?q=mens+vintage+tshirt",
        "https://www.depop.com/search/?q=%22mens+graphic+tee%22",
        "https://www.depop.com/search/?q=%22mens+band+tee%22",
        "https://www.depop.com/search/?q=%22mens+y2k+shirt%22",
        "https://www.depop.com/search/?q=%22mens+oversized+tee%22",
        "https://www.depop.com/search/?q=%22mens+striped+shirt%22",
        "https://www.depop.com/search/?q=%22mens+90s+shirt%22",
        "https://www.depop.com/search/?q=%22mens+retro+tee%22",
        "https://www.depop.com/search/?q=%22mens+streetwear+shirt%22",
        "https://www.depop.com/search/?q=%22mens+grunge+shirt%22"
    ],
    "womens_tops": [
        "https://www.depop.com/search/?q=%22womens+crop+top%22",
        "https://www.depop.com/search/?q=%22womens+vintage+top%22",
        "https://www.depop.com/search/?q=%22womens+y2k+top%22",
        "https://www.depop.com/search/?q=%22womens+tank+top%22",
        "https://www.depop.com/search/?q=%22womens+baby+tee%22",
        "https://www.depop.com/search/?q=%22womens+cami%22",
        "https://www.depop.com/search/?q=%22womens+halter+top%22",
        "https://www.depop.com/search/?q=%22womens+mesh+top%22",
        "https://www.depop.com/search/?q=%22womens+lace+top%22",
        "https://www.depop.com/search/?q=%22womens+90s+top%22"
    ],
    "mens_jeans": [
        "https://www.depop.com/search/?q=%22mens+vintage+jeans%22",
        "https://www.depop.com/search/?q=%22mens+baggy+jeans%22",
        "https://www.depop.com/search/?q=%22mens+straight+jeans%22",
        "https://www.depop.com/search/?q=%22mens+ripped+jeans%22",
        "https://www.depop.com/search/?q=%22mens+black+jeans%22",
        "https://www.depop.com/search/?q=%22mens+y2k+jeans%22",
        "https://www.depop.com/search/?q=%22mens+cargo+pants%22",
        "https://www.depop.com/search/?q=%22mens+wide+leg+jeans%22",
        "https://www.depop.com/search/?q=%22mens+distressed+jeans%22",
        "https://www.depop.com/search/?q=%22mens+90s+jeans%22"
    ],
    "womens_skirts": [
        "https://www.depop.com/search/?q=%22womens+mini+skirt%22",
        "https://www.depop.com/search/?q=%22womens+midi+skirt%22",
        "https://www.depop.com/search/?q=%22womens+denim+skirt%22",
        "https://www.depop.com/search/?q=%22womens+pleated+skirt%22",
        "https://www.depop.com/search/?q=%22womens+vintage+skirt%22",
        "https://www.depop.com/search/?q=%22womens+y2k+skirt%22",
        "https://www.depop.com/search/?q=%22womens+tennis+skirt%22",
        "https://www.depop.com/search/?q=%22womens+flowy+skirt%22",
        "https://www.depop.com/search/?q=%22womens+cargo+skirt%22",
        "https://www.depop.com/search/?q=%22womens+maxi+skirt%22"
    ]
}

# Run scraper
print("🚀 Starting Depop scraper with HARD-CODED URLs...")
print(f"📊 Target: 500 items total (~125 per category)\n")

total_scraped = 0
total_duplicates = 0

for category, urls in search_urls.items():
    print(f"\n🔍 Scraping: {category} ({len(urls)} search queries)...")
    results = scrape_urls(urls, category, target_items=125)
    
    if results:
        total_scraped += len(results['products'])
        total_duplicates += results['duplicates']
    
    time.sleep(3)

print(f"\n{'='*50}")
print(f"🎉 SCRAPING COMPLETE!")
print(f"📊 Total in database: {collection.count_documents({})}")
print(f"📈 New items added: {total_scraped}")
print(f"🔄 Duplicates skipped: {total_duplicates}")
print(f"{'='*50}")

print("\n📊 Breakdown by category:")
for category in ["mens_shirts", "womens_tops", "mens_jeans", "womens_skirts"]:
    count = collection.count_documents({"category": category})
    print(f"  {category}: {count} items")

client.close()