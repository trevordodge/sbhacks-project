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
        
        # Find all price elements
        prices = soup.find_all(class_='styles_price__H8qdh')
        print(f"Found {len(prices)} prices:")
        for price in prices:
            print(f"  Price: {price.text}")
        
        # Find all product images
        all_images = soup.find_all('img')
        product_images = []
        
        for img in all_images:
            img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if img_url and 'media-photos.depop.com/b1/' in img_url and 'P8' in img_url:
                # Get high quality version
                if '/medium/' in img_url:
                    img_url = img_url.replace('/medium/', '/large/')
                product_images.append(img_url)
        
        # Remove duplicates while preserving order
        product_images = list(dict.fromkeys(product_images))
        
        print(f"\n{'='*50}")
        print(f"Total unique product images: {len(product_images)}")
        print(f"{'='*50}\n")
        
        for idx, img_url in enumerate(product_images, 1):
            print(f"{idx}. {img_url}")
        
        return {
            'prices': [price.text for price in prices],
            'images': product_images
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
    print(f"Summary: {len(results['prices'])} products found")
    print(f"{'='*50}")