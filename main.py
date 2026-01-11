from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time

def scrape_depop(url):
    # Set up Chrome options for headless mode
    chrome_options = Options()

    chrome_options.add_argument("--disable-blink-features=AutomationControlled") 
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"]) 
chrome_options.add_experimental_option("useAutomationExtension", False) 
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    chrome_options.add_argument('--headless')  # Run without GUI
    chrome_options.add_argument('--no-sandbox')  # Bypass OS security model
    chrome_options.add_argument('--disable-dev-shm-usage')  # Overcome limited resource problems
    chrome_options.add_argument('--disable-gpu')  # Applicable to Windows OS only
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # Initialize driver
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )
    
    try:
        # Navigate to page
        driver.get(url)
        
        # Wait for products to load
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'img[src*="media-photos.depop.com"]')))
        
        # Scroll to load more products (Depop uses lazy loading)
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 3  # Number of scrolls

        size = 'N/A'
        name = 'N/A'
        
        for _ in range(scroll_attempts):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        
        # Get page source and parse
        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find all product images first
        all_images = soup.find_all('img')
        
        # Also get all prices
        all_prices = soup.select('.styles_price__H8qdh:not(.styles_discountedFullPrice__JTi1d)')
        
        # Get all sizes - FIXED: single 'j' at the end
        sizes = soup.find_all(class_='styles_sizeAttributeText__r9QJj')

        all_names = soup.select('.styles_productAttributes__nt3TO > p:last-child')

        products = []
        price_index = 0
        size_index = 0
        name_index = 0
        
        for img in all_images:
            img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if img_url and 'media-photos.depop.com/b1/' in img_url and 'P8' in img_url:
                # Get high quality version
                if '/medium/' in img_url:
                    img_url = img_url.replace('/medium/', '/large/')
                
                # Find the parent link (traverse up the DOM tree)
                parent_link = img.find_parent('a', href=True)
                
                product_url = 'N/A'
                if parent_link:
                    product_url = parent_link.get('href')
                    if product_url and not product_url.startswith('http'):
                        product_url = 'https://www.depop.com' + product_url
                
                price = 'N/A'
                
                # Method 1: Look in parent link
                if parent_link:
                    price_elem = parent_link.select_one('.styles_price__H8qdh:not(.styles_discountedFullPrice__JTi1d)')
                    if price_elem:
                        price = price_elem.text.strip()
                                
                # Method 2: Look in siblings or nearby elements
                if price == 'N/A':
                    # Go up multiple levels to find a container
                    container = img.find_parent('div')
                    for _ in range(5):  # Try going up 5 levels
                        if container:
                            price_elem = container.select_one('.styles_price__H8qdh:not(.styles_discountedFullPrice__JTi1d)')
                            if price_elem:
                                price = price_elem.text.strip()
                                break
                            container = container.find_parent('div')
                
                # Method 3: Use sequential matching (assume prices are in same order as images)
                if price == 'N/A' and price_index < len(all_prices):
                    price = all_prices[price_index].text.strip()
                    price_index += 1
                
               
                if size_index < len(sizes):
                    size = sizes[size_index].text.strip()
                    size_index += 1

                if name_index < len(all_names): 
                    name = all_names[name_index].text.strip()
                    name_index += 1
   
                products.append({
                    'url': product_url,
                    'image': img_url,
                    'price': price,
                    'size': size,
                    'name': name
                })
        
        # Remove duplicates based on image URL
        # --- NEW DEDUPLICATION LOGIC ---
        seen_urls = set()
        unique_products = []
        
        for product in products:
            # We use the product URL as the unique identifier
            # Also ensure we aren't adding "N/A" links
            if product['url'] != 'N/A' and product['url'] not in seen_urls:
                seen_urls.add(product['url'])
                unique_products.append(product)
        
        print(f"\n{'='*50}")
        print(f"Total unique products: {len(unique_products)}")
        print(f"{'='*50}\n")
        
        for idx, product in enumerate(unique_products, 1):
            print(f"{idx}. {product['name']}:")
            print(f"  Price: {product['price']}")
            print(f"  Size: {product['size']}")
            print(f"  URL: {product['url']}")
            # Optional: print(f"  Image: {product['image']}")
            print("-" * 50)
        
        return {
            'products': unique_products
        }
        
    except Exception as e:
        print(f"Error occurred: {e}")
        import traceback
        traceback.print_exc()
        return None
        
    finally:
        driver.quit()


# Run the scraper
url = "https://www.depop.com/category/mens/tops/tshirts/?moduleOrigin=meganav"
results = scrape_depop(url)

if results:
    print(f"\n{'='*50}")
    print(f"Summary: {len(results['products'])} products found")
    print(f"{'='*50}")