from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
import requests

# Set up Selenium
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

# Go to the page
url = "https://www.depop.com/category/mens/tops/tshirts/?moduleOrigin=meganav"  # Replace with actual URL
driver.get(url)

# Wait for page to load
time.sleep(3)

# Get HTML and parse
html = driver.page_source
soup = BeautifulSoup(html, 'html.parser')

# Close browser
driver.quit()

# Scrape price - look for price elements (you'll need to inspect the page)
price = soup.find(class_='styles_price__H8qdh')
if price:
    print(f"Price: {price.text}")

# Find all images
all_images = soup.find_all('img')

# Filter only product images from media-photos.depop.com
product_images = []
for img in all_images:
    img_url = img.get('src') or img.get('data-src')  # Some images use data-src
    if img_url and 'media-photos.depop.com/b1/' in img_url:
        product_images.append(img_url)
        print(f"Product Image: {img_url}")

# Show how many product images found
print(f"\nTotal product images: {len(product_images)}")

# # Scrape images - find all img tags
# images = soup.find_all('img')
# for img in images:
#     img_url = img.get('src')
#     if img_url:
#         print(f"Image URL: {img_url}")

# # More targeted approach for product images:
# product_images = soup.find_all('img', class_='product-image')  # Adjust class
# for img in product_images:
#     print(f"Product Image: {img.get('src')}")