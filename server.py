from flask import Flask, jsonify, request
from pymongo import MongoClient
from bson import ObjectId
from openai import OpenAI
import json
import requests
import base64
import os
from dotenv import load_dotenv
import re

from flask_cors import CORS

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# MongoDB connection
MONGODB_URI = os.getenv('MONGODB_URI')
client = MongoClient(MONGODB_URI)
db = client['thrifttinderDB']
collection = db['listings']

# OpenRouter client for AI
openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv('OPENROUTER_API_KEY')
)

# Swipe session storage
swipe_sessions = {}

# Custom JSON encoder to handle ObjectId
class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)

app.json_encoder = JSONEncoder

# ===== LISTING ROUTES =====

@app.route('/api/listings/random/<int:count>', methods=['GET'])
def get_random_listings(count):
    """Get random listings with optional category filter - excludes already shown items"""
    try:
        category = request.args.get('category')
        session_id = request.args.get('session_id', 'default')
        
        # Build query
        query = {}
        if category:
            valid_categories = ["mens_shirts", "mens_jeans", "womens_tops", "womens_skirts"]
            if category not in valid_categories:
                return jsonify({
                    'error': f'Invalid category. Must be one of: {", ".join(valid_categories)}'
                }), 400
            query['category'] = category
        
        # Exclude already shown items
        if session_id in swipe_sessions:
            shown_items = swipe_sessions[session_id].get('shown_items', set())
            if shown_items:
                query['_id'] = {'$nin': [ObjectId(item_id) for item_id in shown_items]}
                print(f"  🚫 Excluding {len(shown_items)} already shown items")
        
        listings = list(collection.aggregate([
            {'$match': query},
            {'$sample': {'size': count}}
        ]))

        # Track these items as shown
        if session_id not in swipe_sessions:
            swipe_sessions[session_id] = {
                'swipes': [],
                'tag_weights': {},
                'shown_items': set()
            }
        
        for listing in listings:
            listing_id = str(listing['_id'])
            swipe_sessions[session_id]['shown_items'].add(listing_id)
            listing['_id'] = listing_id

        print(f"  📊 Showing {len(listings)} new items (total shown: {len(swipe_sessions[session_id]['shown_items'])})")

        return jsonify({
            'category': category,
            'count': len(listings),
            'products': listings
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get statistics about the listings database"""
    try:
        total_count = collection.count_documents({})
        
        # Category breakdown
        category_stats = []
        for category in ["mens_shirts", "mens_jeans", "womens_tops", "womens_skirts"]:
            count = collection.count_documents({"category": category})
            category_stats.append({"category": category, "count": count})

        return jsonify({
            'count': total_count,
            'categories': category_stats
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ===== SWIPE & RECOMMENDATION ROUTES =====

@app.route('/api/swipe', methods=['POST'])
def record_swipe():
    """Record user's swipe and update tag weights - handles like/dislike/neutral"""
    try:
        data = request.json
        session_id = data.get('session_id', 'default')
        listing_id = data.get('listing_id')
        action = data.get('action')  # 'like', 'dislike', or 'neutral'

        # Validate action
        valid_actions = ['like', 'dislike', 'neutral']
        if action not in valid_actions:
            return jsonify({'error': f'Invalid action. Must be one of: {", ".join(valid_actions)}'}), 400

        listing = collection.find_one({'_id': ObjectId(listing_id)})

        if not listing:
            return jsonify({'error': 'Listing not found'}), 404

        listing['_id'] = str(listing['_id'])
        
        # Initialize session if needed
        if session_id not in swipe_sessions:
            swipe_sessions[session_id] = {
                'swipes': [],
                'tag_weights': {},
                'shown_items': set()
            }
        
        session = swipe_sessions[session_id]

        # Mark item as shown
        session['shown_items'].add(listing_id)

        # Record swipe
        session['swipes'].append({
            'listing': listing,
            'action': action
        })
        
        # Update tag weights based on action
        item_tags = listing.get('tags', [])
        
        if action == 'like':
            for tag in item_tags:
                session['tag_weights'][tag] = session['tag_weights'].get(tag, 0) + 0.1
        elif action == 'dislike':
            for tag in item_tags:
                session['tag_weights'][tag] = session['tag_weights'].get(tag, 0) - 0.05
        # Neutral/skip: no weight change, but still tracked
        
        # Keep weights between 0 and 1
        for tag in session['tag_weights']:
            session['tag_weights'][tag] = max(0, min(1, session['tag_weights'][tag]))

        liked_count = len([s for s in session['swipes'] if s['action'] == 'like'])
        disliked_count = len([s for s in session['swipes'] if s['action'] == 'dislike'])
        neutral_count = len([s for s in session['swipes'] if s['action'] == 'neutral'])
        
        print(f"📊 Session {session_id}: +{liked_count} likes, -{disliked_count} dislikes, ~{neutral_count} skips")

        return jsonify({
            'total_swipes': len(session['swipes']),
            'liked_count': liked_count,
            'disliked_count': disliked_count,
            'neutral_count': neutral_count,
            'shown_count': len(session['shown_items']),
            'can_get_recommendations': liked_count >= 1
        }), 200

    except Exception as e:
        print(f"❌ Error in swipe: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/session/<session_id>', methods=['GET'])
def get_session_info(session_id):
    """Get info about a swipe session"""
    if session_id not in swipe_sessions:
        return jsonify({
            'exists': False
        }), 200

    session = swipe_sessions[session_id]
    liked_count = len([s for s in session['swipes'] if s['action'] == 'like'])
    disliked_count = len([s for s in session['swipes'] if s['action'] == 'dislike'])
    neutral_count = len([s for s in session['swipes'] if s['action'] == 'neutral'])

    return jsonify({
        'exists': True,
        'swipes': len(session['swipes']),
        'liked': liked_count,
        'disliked': disliked_count,
        'neutral': neutral_count,
        'shown': len(session.get('shown_items', set())),
        'can_get_recommendations': liked_count >= 1
    }), 200

@app.route('/api/session/<session_id>/reset', methods=['POST'])
def reset_session(session_id):
    """Reset a swipe session (clear history)"""
    if session_id in swipe_sessions:
        del swipe_sessions[session_id]
        return jsonify({
            'success': True,
            'message': f'Session {session_id} reset'
        }), 200
    return jsonify({
        'success': False,
        'message': 'Session not found'
    }), 404

@app.route('/api/recommendations', methods=['POST'])
def get_recommendations():
    """Get AI-powered visual recommendations using Gemini - with optional category filter and duplicate prevention"""
    try:
        data = request.json
        session_id = data.get('session_id', 'default')
        category = data.get('category')  # Optional category filter

        if session_id not in swipe_sessions:
            return jsonify({'error': 'No swipe history found'}), 404

        session = swipe_sessions[session_id]
        liked_items = [s['listing'] for s in session['swipes'] if s['action'] == 'like']

        if len(liked_items) == 0:
            return jsonify({'error': 'No liked items yet'}), 400
        
        # Use provided category or infer from first liked item
        if not category:
            category = liked_items[0].get('category')
        
        print(f"🤖 Getting AI recommendations for {len(liked_items)} liked items in category: {category}")
        
        liked_items_text = format_for_ai(liked_items)
        shown_items = session.get('shown_items', set())
        recommendations = get_ai_recommendations(liked_items_text, liked_items, category, shown_items)
        
        # Mark recommendations as shown
        for rec in recommendations:
            session['shown_items'].add(rec['_id'])
        
        return jsonify({
            'category': category,
            'liked_count': len(liked_items),
            'count': len(recommendations),
            'products': recommendations
        }), 200

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ===== AI HELPER FUNCTIONS =====

def format_for_ai(liked_items):
    """Format liked items for AI"""
    formatted_text = "USER'S LIKED ITEMS:\n\n"

    for idx, item in enumerate(liked_items, 1):
        formatted_text += f"""Item #{idx}:
- Name: {item.get('name', 'Unknown')}
- Category: {item.get('category', 'Unknown')}
- Tags: {', '.join(item.get('tags', []))}
- Price: ${item.get('price', 0):.2f}
---
"""

    return formatted_text

def get_ai_recommendations(liked_items_text, liked_items, user_category=None, exclude_shown=None):
    """Get recommendations from Gemini via OpenRouter with IMAGE ANALYSIS - excludes shown items"""
    
    # Build query
    query = {}
    if user_category:
        query['category'] = user_category
        print(f"  🔍 Filtering to category: {user_category}")
    
    # Exclude items that have already been shown
    if exclude_shown and len(exclude_shown) > 0:
        query['_id'] = {'$nin': [ObjectId(item_id) for item_id in exclude_shown]}
        print(f"  🚫 Excluding {len(exclude_shown)} already shown items")
    
    all_listings = list(collection.find(query))
    print(f"  📊 Found {len(all_listings)} NEW items to analyze")
    
    if len(all_listings) == 0:
        print("  ⚠️ No new items available - user has seen everything!")
        return []
    
    # Create text list of available items
    all_items_text = "AVAILABLE ITEMS (return IDs from this list):\n\n"
    for item in all_listings:
        all_items_text += f"ID: {str(item['_id'])} | {item.get('name', 'Unknown')} | ${item.get('price', 0):.2f}\n"
    
    # Download and encode images from liked items
    image_contents = []
    for idx, item in enumerate(liked_items, 1):
        image_url = item.get('image', '')
        if image_url:
            try:
                print(f"  📸 Downloading image {idx}: {image_url[:50]}...")
                response = requests.get(image_url, timeout=10)
                if response.status_code == 200:
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

Here are ALL AVAILABLE ITEMS{' in the SAME CATEGORY' if user_category else ''} (EXCLUDING items already shown):

{all_items_text}

Analyze the VISUAL style of the liked items (colors, graphics, patterns, aesthetic) and the text descriptions including tags.

Based on both the images and descriptions, recommend 10 similar items from the available list.

Look for:
- Similar color palettes
- Similar graphic styles (vintage, minimalist, bold, etc.)
- Similar visual aesthetic
- Similar price range
- Similar tags/style attributes

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
            model="google/gemini-2.5-flash",
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

        print(f"\n✅ Returning {len(recommendations)} NEW recommendations\n")
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
        
        for category in ["mens_shirts", "mens_jeans", "womens_tops", "womens_skirts"]:
            cat_count = collection.count_documents({"category": category})
            print(f"  {category}: {cat_count} items")
    except Exception as e:
        print(f"⚠️ Database connection issue: {e}")
    app.run(port=5000)