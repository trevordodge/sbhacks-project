from pymongo import MongoClient
from openai import OpenAI
import requests
import base64
import time
from dotenv import load_dotenv
load_dotenv()

# MongoDB connection
MONGODB_URI = os.getenv('MONGODB_URI')
client = MongoClient(MONGODB_URI)
db = client['thrifttinderDB']
collection = db['listings']

# OpenRouter client
openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv('OPENROUTER_API_KEY')
)

def enhance_item_with_ai(item):
    """Add AI description and tags to a single item"""
    
    image_url = item.get('image', '')
    name = item.get('name', 'Unknown')
    category = item.get('category', 'Unknown')
    price = item.get('price', 0)
    
    if not image_url:
        print(f"  ⚠️ No image for {name}, skipping")
        return None
    
    try:
        # Download and encode image
        print(f"  📸 Downloading image...")
        response = requests.get(image_url, timeout=10)
        if response.status_code != 200:
            print(f"  ⚠️ Failed to download image")
            return None
        
        image_base64 = base64.b64encode(response.content).decode('utf-8')
        
        # Ask Gemini to analyze
        print(f"  🤖 Asking Gemini for analysis...")
        completion = openrouter_client.chat.completions.create(
            model="google/gemini-2.5-flash",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"""Analyze this clothing item from a thrift store listing.

Item info:
- Name: {name}
- Category: {category}
- Price: ${price:.2f}

Provide:
1. A 2-3 sentence description focusing on visual details (colors, patterns, graphics, style, condition)
2. Style tags that describe the aesthetic (like: vintage, y2k, grunge, preppy, streetwear, minimal, boho, athletic, etc.)
3. Color tags (main colors visible)
4. Fit/type tags (like: oversized, cropped, fitted, baggy, mini, midi, ripped, distressed, etc.)

Return ONLY valid JSON in this exact format (no markdown, no ```json):
{{
  "ai_description": "detailed description here",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
}}

Include 8-12 total tags covering style, colors, and fit. Be specific and accurate based on what you see."""
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }]
        )
        
        response_text = completion.choices[0].message.content.strip()
        print(f"  📝 Response: {response_text[:100]}...")
        
        # Clean response (remove markdown if present)
        if response_text.startswith('```'):
            # Remove ```json and ``` markers
            response_text = response_text.replace('```json', '').replace('```', '').strip()
        
        # Parse JSON
        import json
        ai_data = json.loads(response_text)
        
        return {
            'ai_description': ai_data.get('ai_description', ''),
            'tags': ai_data.get('tags', [])
        }
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def enhance_database(sample_size=None):
    """Enhance all items in database with AI analysis"""
    
    # Get items that need enhancement (don't have ai_description yet)
    query = {'ai_description': {'$exists': False}}
    
    if sample_size:
        items = list(collection.find(query).limit(sample_size))
        print(f"🧪 SAMPLE MODE: Processing {len(items)} items\n")
    else:
        items = list(collection.find(query))
        print(f"🚀 FULL MODE: Processing {len(items)} items\n")
    
    if not items:
        print("✅ All items already enhanced!")
        return
    
    successful = 0
    failed = 0
    
    for idx, item in enumerate(items, 1):
        print(f"\n[{idx}/{len(items)}] Processing: {item.get('name', 'Unknown')[:50]}")
        print(f"  Category: {item.get('category')}")
        print(f"  Price: ${item.get('price', 0):.2f}")
        
        ai_data = enhance_item_with_ai(item)
        
        if ai_data:
            # Update item in database
            collection.update_one(
                {'_id': item['_id']},
                {'$set': {
                    'ai_description': ai_data['ai_description'],
                    'tags': ai_data['tags']
                }}
            )
            
            print(f"  ✅ Updated!")
            print(f"  📝 Description: {ai_data['ai_description'][:80]}...")
            print(f"  🏷️  Tags: {', '.join(ai_data['tags'][:5])}...")
            
            successful += 1
        else:
            failed += 1
        
        # Rate limiting - be nice to the API
        time.sleep(2)
    
    print(f"\n{'='*50}")
    print(f"✅ Successfully enhanced: {successful}")
    print(f"❌ Failed: {failed}")
    print(f"{'='*50}")

# Run on 10 items first
if __name__ == '__main__':
    print("🎨 AI Enhancement Script for ThriftTinder")
    print("="*50)
    
    
    enhance_database()
    
    print("\n💡 If this looks good, remove sample_size parameter to process all items!")