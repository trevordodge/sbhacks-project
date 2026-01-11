from flask import Flask, jsonify, request
from pymongo import MongoClient
from bson import ObjectId
from openai import OpenAI
import json
import requests
import base64
from io import BytesIO

from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# MongoDB connection
MONGODB_URI = "mongodb+srv://thrifttinder:fishstick1212@sbhacks.nqf2fze.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(MONGODB_URI)
db = client['thrifttinderDB']
collection = db['listings']

# OpenRouter client for AI
openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="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"
)

# Swipe session storage (in production, use MongoDB)
swipe_sessions = {}

# Custom JSON encoder to handle ObjectId
class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)

app.json_encoder = JSONEncoder

# ===== ORIGINAL ROUTES =====

@app.route('/api/listings', methods=['GET'])
def get_all_listings():
    """Retrieve all listings from MongoDB"""
    try:
        listings = list(collection.find({}))
        
        for listing in listings:
            listing['_id'] = str(listing['_id'])
        
        return jsonify({
            'success': True,
            'count': len(listings),
            'listings': listings
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/listings/filter', methods=['GET'])
def filter_listings():
    """Filter listings by brand, style, price range, size"""
    try:
        query = {}
        
        brand = request.args.get('brand')
        style = request.args.get('style')
        size = request.args.get('size')
        min_price = request.args.get('min_price')
        max_price = request.args.get('max_price')
        
        if brand:
            query['brand'] = {'$regex': brand, '$options': 'i'}
        if style:
            query['style'] = {'$regex': style, '$options': 'i'}
        if size:
            query['size'] = {'$regex': size, '$options': 'i'}
        
        if min_price or max_price:
            query['price'] = {}
            if min_price:
                query['price']['$gte'] = float(min_price)
            if max_price:
                query['price']['$lte'] = float(max_price)
        
        listings = list(collection.find(query))
        
        for listing in listings:
            listing['_id'] = str(listing['_id'])
        
        return jsonify({
            'success': True,
            'count': len(listings),
            'filters': query,
            'listings': listings
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/listings/<listing_id>', methods=['GET'])
def get_listing_by_id(listing_id):
    """Get a specific listing by its MongoDB _id"""
    try:
        listing = collection.find_one({'_id': ObjectId(listing_id)})
        
        if listing:
            listing['_id'] = str(listing['_id'])
            return jsonify({
                'success': True,
                'listing': listing
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Listing not found'
            }), 404
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/listings/random/<int:count>', methods=['GET'])
def get_random_listings(count):
    """Get random listings for swiping (Tinder-style)"""
    try:
        listings = list(collection.aggregate([
            {'$sample': {'size': count}}
        ]))
        
        for listing in listings:
            listing['_id'] = str(listing['_id'])
        
        return jsonify({
            'success': True,
            'count': len(listings),
            'listings': listings
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get statistics about the listings database"""
    try:
        total_count = collection.count_documents({})
        
        brands = collection.aggregate([
            {'$group': {'_id': '$brand', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ])
        
        price_stats = collection.aggregate([
            {'$group': {
                '_id': None,
                'avg_price': {'$avg': '$price'},
                'min_price': {'$min': '$price'},
                'max_price': {'$max': '$price'}
            }}
        ])
        
        return jsonify({
            'success': True,
            'total_listings': total_count,
            'brands': list(brands),
            'price_stats': list(price_stats)
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/listings/search', methods=['GET'])
def search_listings():
    """Search listings by name/description"""
    try:
        search_term = request.args.get('q', '')
        
        if not search_term:
            return jsonify({
                'success': False,
                'error': 'Search term required (use ?q=term)'
            }), 400
        
        listings = list(collection.find({
            'name': {'$regex': search_term, '$options': 'i'}
        }))
        
        for listing in listings:
            listing['_id'] = str(listing['_id'])
        
        return jsonify({
            'success': True,
            'count': len(listings),
            'search_term': search_term,
            'listings': listings
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ===== NEW AI-POWERED ROUTES =====

@app.route('/api/swipe', methods=['POST'])
def record_swipe():
    """Record user's swipe (like/dislike)"""
    try:
        data = request.json
        session_id = data.get('session_id', 'default')
        listing_id = data.get('listing_id')
        action = data.get('action')  # 'like' or 'dislike'
        
        listing = collection.find_one({'_id': ObjectId(listing_id)})
        
        if not listing:
            return jsonify({'success': False, 'error': 'Listing not found'}), 404
        
        listing['_id'] = str(listing['_id'])
        
        if session_id not in swipe_sessions:
            swipe_sessions[session_id] = []
        
        swipe_sessions[session_id].append({
            'listing': listing,
            'action': action
        })
        
        liked_count = len([s for s in swipe_sessions[session_id] if s['action'] == 'like'])
        
        return jsonify({
            'success': True,
            'total_swipes': len(swipe_sessions[session_id]),
            'liked_count': liked_count,
            'can_get_recommendations': liked_count >= 1
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/session/<session_id>', methods=['GET'])
def get_session_info(session_id):
    """Get info about a swipe session"""
    if session_id not in swipe_sessions:
        return jsonify({
            'success': True,
            'exists': False,
            'swipes': 0,
            'liked': 0
        }), 200
    
    swipes = swipe_sessions[session_id]
    liked_count = len([s for s in swipes if s['action'] == 'like'])
    
    return jsonify({
        'success': True,
        'exists': True,
        'swipes': len(swipes),
        'liked': liked_count,
        'can_get_recommendations': liked_count >= 1
    }), 200

@app.route('/api/recommendations', methods=['POST'])
def get_recommendations():
    """Get AI-powered recommendations based on swipe history"""
    try:
        data = request.json
        session_id = data.get('session_id', 'default')
        
        if session_id not in swipe_sessions:
            return jsonify({
                'success': False,
                'error': 'No swipe history found'
            }), 400
        
        liked_items = [s['listing'] for s in swipe_sessions[session_id] if s['action'] == 'like']
        
        if len(liked_items) == 0:
            return jsonify({
                'success': False,
                'error': 'No liked items yet. Swipe right on at least one item!'
            }), 400
        
        print(f"🤖 Getting AI recommendations for {len(liked_items)} liked items WITH IMAGE ANALYSIS...")
        
        liked_items_text = format_for_ai(liked_items)
        recommendations = get_ai_recommendations(liked_items_text, liked_items)
        
        return jsonify({
            'success': True,
            'liked_count': len(liked_items),
            'recommendation_count': len(recommendations),
            'recommendations': recommendations
        }), 200
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/describe-likes', methods=['POST'])
def describe_likes():
    """Get AI descriptions of liked items based on their images"""
    try:
        data = request.json
        session_id = data.get('session_id', 'default')
        
        if session_id not in swipe_sessions:
            return jsonify({'success': False, 'error': 'No swipe history'}), 400
        
        liked_items = [s['listing'] for s in swipe_sessions[session_id] if s['action'] == 'like']
        
        if len(liked_items) == 0:
            return jsonify({'success': False, 'error': 'No liked items'}), 400
        
        print(f"🔍 Getting AI descriptions for {len(liked_items)} images...")
        
        descriptions = []
        
        for idx, item in enumerate(liked_items, 1):
            image_url = item.get('image', '')
            if not image_url:
                continue
                
            try:
                # Download image
                response = requests.get(image_url, timeout=10)
                if response.status_code == 200:
                    image_base64 = base64.b64encode(response.content).decode('utf-8')
                    
                    # Ask Gemini to describe it
                    completion = openrouter_client.chat.completions.create(
                        model="google/gemini-2.5-flash",
                        messages=[{
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": """Describe this clothing item in detail. Include:
- Main colors
- Graphic/design elements
- Style/aesthetic (vintage, modern, streetwear, etc.)
- Notable features
- Overall vibe

Keep it concise (2-3 sentences)."""
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
                    
                    description = completion.choices[0].message.content.strip()
                    
                    descriptions.append({
                        'item_name': item.get('name'),
                        'item_id': str(item.get('_id')),
                        'ai_description': description,
                        'image': image_url
                    })
                    
                    print(f"  ✅ Item {idx}: {description[:60]}...")
                    
            except Exception as e:
                print(f"  ⚠️ Error describing item {idx}: {e}")
        
        return jsonify({
            'success': True,
            'count': len(descriptions),
            'descriptions': descriptions
        }), 200
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ===== AI HELPER FUNCTIONS =====

def format_for_ai(liked_items):
    """Format liked items for AI"""
    formatted_text = "USER'S LIKED ITEMS:\n\n"
    
    for idx, item in enumerate(liked_items, 1):
        formatted_text += f"""Item #{idx}:
- Name: {item.get('name', 'Unknown')}
- Brand: {item.get('brand', 'Various')}
- Category: {item.get('style', 'Unknown')}
- Size: {item.get('size', 'Various')}
- Price: ${item.get('price', 0):.2f}
---
"""
    
    return formatted_text

def get_ai_recommendations(liked_items_text, liked_items):
    """Get recommendations from Gemini via OpenRouter with IMAGE ANALYSIS"""
    
    all_listings = list(collection.find({}))
    
    # Create simpler text list of available items
    all_items_text = "AVAILABLE ITEMS (return IDs from this list):\n\n"
    for item in all_listings:
        all_items_text += f"ID: {str(item['_id'])} | {item.get('name', 'Unknown')} | {item.get('brand', 'Various')} | ${item.get('price', 0):.2f}\n"
    
    # Download and encode images from liked items
    image_contents = []
    for idx, item in enumerate(liked_items, 1):
        image_url = item.get('image', '')
        if image_url:
            try:
                print(f"  📸 Downloading image {idx}: {image_url[:50]}...")
                response = requests.get(image_url, timeout=10)
                if response.status_code == 200:
                    # Convert to base64
                    image_base64 = base64.b64encode(response.content).decode('utf-8')
                    image_contents.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    })
                    print(f"    ✅ Image {idx} loaded")
            except Exception as e:
                print(f"    ⚠️ Could not load image {idx}: {e}")
    
    # Build message with images + text
    message_content = [
        {
            "type": "text",
            "text": f"""These are the items the user LIKED (with images):

{liked_items_text}

Here are ALL AVAILABLE ITEMS in our database:

{all_items_text}

Analyze the VISUAL style of the liked items (colors, graphics, patterns, aesthetic) and the text descriptions.

Based on both the images and descriptions, recommend 10 similar items from the available list.

Look for:
- Similar color palettes
- Similar graphic styles (vintage, minimalist, bold, etc.)
- Similar visual aesthetic
- Similar price range
- Similar categories

CRITICAL: Return ONLY a comma-separated list of MongoDB IDs (24-character hex strings).
NO explanations, NO extra text.

Example format: 6962e11fca3dce721a6185d9,6962e11fca3dce721a61861a

Return the IDs now:"""
        }
    ]
    
    # Add all images to the message
    message_content.extend(image_contents)
    
    try:
        print(f"\n🤖 Sending {len(image_contents)} images + text to Gemini for analysis...")
        
        completion = openrouter_client.chat.completions.create(
            model="google/gemini-2.5-flash",  # Supports vision
            messages=[
                {
                    "role": "user",
                    "content": message_content
                }
            ]
        )
        
        response_text = completion.choices[0].message.content.strip()
        print(f"\n🤖 AI RESPONSE:\n{response_text[:200]}...\n")
        
        # Extract IDs using regex
        import re
        found_ids = re.findall(r'[a-f0-9]{24}', response_text)
        
        print(f"📝 Found {len(found_ids)} potential IDs")
        
        recommendations = []
        for id_str in found_ids[:10]:
            try:
                listing = collection.find_one({'_id': ObjectId(id_str)})
                if listing:
                    listing['_id'] = str(listing['_id'])
                    recommendations.append(listing)
                    print(f"  ✅ Added: {listing.get('name', 'Unknown')[:40]}")
            except Exception as e:
                print(f"  ⚠️ Could not fetch {id_str}: {e}")
                continue
        
        print(f"\n✅ Returning {len(recommendations)} recommendations\n")
        return recommendations
        
    except Exception as e:
        print(f"❌ AI API Error: {e}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == '__main__':
    print("🚀 ThriftTinder API starting...")
    try:
        count = collection.count_documents({})
        print(f"📊 Database has {count} listings")
    except Exception as e:
        print(f"⚠️ Database connection issue: {e}")
        print("Starting anyway - will retry on first request")
    app.run(debug=True, port=5000)
