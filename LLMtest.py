from curl_cffi import requests # <--- specific import for bypassing 403s
import json
from bs4 import BeautifulSoup
from google import genai

# --- CONFIGURATION ---
API_KEY = "AIzaSyC2sKMGfT5QuwVd-xEejV4rULwg_Tome88"  # Paste your key here
client = genai.Client(api_key=API_KEY)

def get_depop_details(url):
    print(f"Fetching details from: {url}...")
    
    try:
        # 'impersonate="chrome"' makes the server think we are a real browser
        response = requests.get(url, impersonate="chrome")
        
        if response.status_code != 200:
            return f"Error: Status Code {response.status_code}"

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Method A: Try to find the hidden JSON data
        script_tag = soup.find("script", id="__NEXT_DATA__")
        
        if script_tag:
            try:
                data = json.loads(script_tag.string)
                product_data = data['props']['pageProps']['product']
                
                # Extract clean details
                description = product_data.get('description', 'No description')
                price_amount = product_data['price']['priceAmount']
                currency = product_data['price']['currencyName']
                brand_id = product_data.get('brandId', 'Unknown Brand')
                
                # Combine into a clean string
                clean_text = (
                    f"Product Description: {description}\n"
                    f"Price: {price_amount} {currency}\n"
                    f"Brand ID: {brand_id}"
                )
                return clean_text
            except KeyError:
                return "Error: JSON found, but structure was different than expected."
        
        # Method B: Fallback to raw text
        return soup.get_text()[:3000]

    except Exception as e:
        return f"Failed to fetch page: {e}"

# --- MAIN EXECUTION ---
depop_url = "https://www.depop.com/products/assortedgarmentz-blue-and-purple-jimi-hendrix/?moduleOrigin=meganav"

# 1. Scrape the site
scraped_text = get_depop_details(depop_url)
print("\n--- Scraped Data ---")
print(scraped_text)
print("--------------------\n")

# 2. Analyze with Gemini
if "Error" not in scraped_text and "Failed" not in scraped_text:
    print("Analyzing with Gemini...")
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=[
            f"Here is the data from a clothing listing: '{scraped_text}'. \n\nPlease summarize this item for a search index. Include keywords, aesthetic (e.g. vintage, street), and estimated category."
        ]
    )
    print("\n--- AI Analysis ---")
    print(response.text)
else:
    print("Skipping AI analysis due to scrape error.")