from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager
from bs4 import BeautifulSoup
from pymongo import MongoClient
import time
import re
from dotenv import load_dotenv
load_dotenv()

def connect_to_db():
    """Connect to MongoDB Atlas"""
    # MongoDB Atlas connection string
    MONGODB_URI = os.getenv('MONGODB_URI')
    client = MongoClient(MONGODB_URI)
    
    db = client['thrifttinderDB']
    collection = db['listings']
    return client, collection

def extract_price(price_text):
    """Extract numeric price from text like '$25.00'"""
    try:
        # Remove currency symbols and extract number
        price_str = re.sub(r'[^\d.]', '', price_text)
        return float(price_str)
    except:
        return 0.0

def scrape_product_details(driver, product_url):
    """Visit individual product page and extract details"""
    try:
        driver.get(product_url)
        time.sleep(1)  # Brief wait for page load
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Extract product name/title
        name = "Unknown Item"
        title_elem = soup.find('h1') or soup.find('h2')
        if title_elem:
            name = title_elem.text.strip()
        
        # Extract brand (often in description or meta tags)
        brand = "Various"
        brand_elem = soup.find('p', class_='ProductDescription_brandName__')
        if not brand_elem:
            # Try to find brand in text
            desc = soup.find('p', class_='ProductDescription_description__')
            if desc and desc.text:
                text = desc.text.lower()
                # Common brand indicators
                if 'nike' in text:
                    brand = 'Nike'
                elif 'adidas' in text:
                    brand = 'Adidas'
                elif 'levi' in text:
                    brand = 'Levis'
                elif 'carhartt' in text:
                    brand = 'Carhartt'
                elif 'dickies' in text:
                    brand = 'Dickies'
                elif 'vintage' in text:
                    brand = 'Vintage'
        else:
            brand = brand_elem.text.strip()
        
        # Extract size (usually in description)
        size = "Various"
        size_elem = soup.find('p', string=re.compile(r'size', re.IGNORECASE))
        if size_elem:
            size_text = size_elem.text
            # Extract size patterns like "Size: M", "Large", "32x34"
            size_match = re.search(r'(size[:\s]+)?([XS|S|M|L|XL|XXL|\d+x?\d*])', size_text, re.IGNORECASE)
            if size_match:
                size = size_match.group(2)
        
        # Extract price
        price = 0.0
        price_elem = soup.find(class_='styles_price__')
        if not price_elem:
            price_elem = soup.find('p', string=re.compile(r'\$\d+'))
        if price_elem:
            price = extract_price(price_elem.text)
        
        # Extract image
        image = ""
        img_elem = soup.find('img', src=re.compile(r'media-photos.depop.com'))
        if img_elem:
            image = img_elem.get('src')
            if '/medium/' in image:
                image = image.replace('/medium/', '/large/')
        
        return {
            'name': name,
            'brand': brand,
            'size': size,
            'price': price,
            'image': image
        }
    
    except Exception as e:
        print(f"  ⚠️  Error scraping {product_url}: {e}")
        return None

def initialize_driver():
    """
    Initialize Selenium WebDriver for Firefox

    Returns:
        WebDriver instance
    """
    # Set up Firefox options for headless mode
    firefox_options = FirefoxOptions()
    firefox_options.add_argument('--headless')
    firefox_options.add_argument('--no-sandbox')
    firefox_options.add_argument('--disable-dev-shm-usage')

    # Initialize Firefox driver
    driver = webdriver.Firefox(
        service=FirefoxService(GeckoDriverManager().install()),
        options=firefox_options
    )
    print("🦊 Using Firefox browser")

    return driver

def scrape_depop(url, save_to_db=True, max_products=100):
    """
    Scrape Depop listings

    Args:
        url (str): Depop category URL to scrape
        save_to_db (bool): Whether to save results to MongoDB
        max_products (int): Maximum number of products to scrape
    """
    # Initialize driver
    driver = initialize_driver()
    
    # Connect to MongoDB if saving
    if save_to_db:
        client, collection = connect_to_db()
    
    try:
        # Navigate to page
        print(f"Loading: {url}")
        driver.get(url)
        
        # Wait for products to load
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'img[src*="media-photos.depop.com"]')))
        
        # Scroll to load more products (Depop uses lazy loading)
        print("Scrolling to load products...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 10  # More scrolls to get ~100 products
        
        for scroll in range(scroll_attempts):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = driver.execute_script("return document.body.scrollHeight")
            print(f"  Scroll {scroll + 1}/{scroll_attempts}")
            if new_height == last_height:
                break
            last_height = new_height
        
        # Get page source and parse
        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find all product links
        product_links = []
        all_links = soup.find_all('a', href=True)
        for link in all_links:
            href = link.get('href')
            if href and '/products/' in href:
                full_url = f"https://www.depop.com{href}" if href.startswith('/') else href
                if full_url not in product_links:
                    product_links.append(full_url)
        
        print(f"Found {len(product_links)} product links")
        
        # Limit to max_products
        product_links = product_links[:max_products]
        print(f"Scraping first {len(product_links)} products in detail...")
        
        # Extract category from search URL
        category = "T-Shirts"  # Default
        if "tshirts" in url.lower():
            category = "T-Shirts"
        elif "jeans" in url.lower():
            category = "Jeans"
        elif "shoes" in url.lower():
            category = "Footwear"
        elif "jackets" in url.lower():
            category = "Outerwear"
        
        # Deep scrape each product
        listings = []
        for idx, product_url in enumerate(product_links, 1):
            print(f"\n[{idx}/{len(product_links)}] Scraping: {product_url}")
            
            details = scrape_product_details(driver, product_url)
            
            if details:
                listing = {
                    'name': details['name'],
                    'style': category,
                    'price': details['price'],
                    'brand': details['brand'],
                    'size': details['size'],
                    'url': product_url,
                    'image': details['image']
                }
                listings.append(listing)
                print(f"  ✅ {details['name'][:50]} - ${details['price']:.2f} - {details['brand']} - Size {details['size']}")
        
        # Save to MongoDB
        if save_to_db and listings:
            print(f"\nSaving {len(listings)} listings to MongoDB...")
            result = collection.insert_many(listings)
            print(f"✅ Saved {len(result.inserted_ids)} listings to thrifttinderDB")
            
            # Show stats
            total = collection.count_documents({})
            print(f"📊 Total listings in database: {total}")
        
        return {
            'listings': listings
        }
        
    except Exception as e:
        print(f"Error occurred: {e}")
        import traceback
        traceback.print_exc()
        return None
        
    finally:
        driver.quit()
        if save_to_db:
            client.close()

# Run the scraper
if __name__ == "__main__":
    url = "https://www.depop.com/category/mens/tops/tshirts/?moduleOrigin=meganav"
    
    print("="*50)
    print("DEPOP DEEP SCRAPER -> MongoDB")
    print("="*50)

    results = scrape_depop(url, save_to_db=True, max_products=100)
    
    if results:
        print(f"\n{'='*50}")
        print(f"✅ Summary: {len(results['listings'])} products scraped and saved")
        print(f"{'='*50}")