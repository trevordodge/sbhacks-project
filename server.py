from flask import Flask, jsonify, request
from pymongo import MongoClient
from bson import ObjectId
from openai import OpenAI
import json
import requests
import base64
import os
from dotenv import load_dotenv

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
# Structure: {session_id: {category: str, swipes: [], tag_weights: {}}}
swipe_sessions = {}

# Custom JSON encoder to handle ObjectId
class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)

app.json_encoder = JSONEncoder

# ===== SESSION MANAGEMENT =====

@app.route('/api/session/start', methods=['POST'])
def start_session():
    """Start a new session with category selection"""
    try:
        data = request.json
        category = data.get('category')
        
        # Validate category
        valid_categories = ["mens_shirts", "mens_jeans", "womens_tops", "womens_skirts"]
        if not category or category not in valid_categories:
            return jsonify({
                'error': f'Invalid category. Must be one of: {", ".join(valid_categories)}'
            }), 400
        
        # Generate session ID
        session_id = data.get('session_id', f"session_{len(swipe_sessions) + 1}")
        
        # Initialize session
        swipe_sessions[session_id] = {
            'category': category,
            'swipes': [],
            'tag_weights': {}
        }
        
        # Get initial random items
        initial_items = list(collection.aggregate([
            {'$match': {'category': category}},
            {'$sample': {'size': 5}}
        ]))
        
        for item in initial_items:
            item['_id'] = str(item['_id'])
        
        print(f"✅ Started session {session_id} for category: {category}")
        
        return jsonify({
            'session_id': session_id,
            'category': category,
            'count': len(initial_items),
            'products': initial_items
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ===== LISTING ROUTES =====

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
            'count': len(listings),
            'products': listings
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/listings/random/<category>/<int:count>', methods=['GET'])
def get_random_listings_by_category(category, count):
    """Get random listings from a specific category"""
    try:
        valid_categories = ["mens_shirts", "mens_jeans", "womens_tops", "womens_skirts"]
        if category not in valid_categories:
            return jsonify({
                'error': f'Invalid category. Must be one of: {", ".join(valid_categories)}'
            }), 400
        
        listings = list(collection.aggregate([
            {'$match': {'category': category}},
            {'$sample': {'size': count}}
        ]))
        
        for listing in listings:
            listing['_id'] = str(listing['_id'])
        
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
    """Record user's swipe and update tag weights"""
    try:
        data = request.json
        session_id = data.get('session_id')
        listing_id = data.get('listing_id')
        action = data.get('action')  # 'like' or 'dislike'

        if session_id not in swipe_sessions:
            return jsonify({
                'error': 'Session not found. Start a session first with /api/session/start'
            }), 404

        listing = collection.find_one({'_id': ObjectId(listing_id)})

        if not listing:
            return jsonify({'error': 'Listing not found'}), 404

        listing['_id'] = str(listing['_id'])
        
        session = swipe_sessions[session_id]

        # Record swipe
        session['swipes'].append({
            'listing': listing,
            'action': action
        })
        
        # Update tag weights
        item_tags = listing.get('tags', [])
        
        if action == 'like':
            # Increase weight for each tag
            for tag in item_tags:
                session['tag_weights'][tag] = session['tag_weights'].get(tag, 0) + 0.1
        elif action == 'dislike':
            # Decrease weight for each tag
            for tag in item_tags:
                session['tag_weights'][tag] = session['tag_weights'].get(tag, 0) - 0.05
        
        # Keep weights between 0 and 1
        for tag in session['tag_weights']:
            session['tag_weights'][tag] = max(0, min(1, session['tag_weights'][tag]))

        liked_count = len([s for s in session['swipes'] if s['action'] == 'like'])
        disliked_count = len([s for s in session['swipes'] if s['action'] == 'dislike'])
        
        print(f"📊 Session {session_id}: +{liked_count} likes, -{disliked_count} dislikes")
        print(f"🏷️  Top tags: {dict(sorted(session['tag_weights'].items(), key=lambda x: x[1], reverse=True)[:5])}")

        return jsonify({
            'total_swipes': len(session['swipes']),
            'liked_count': liked_count,
            'disliked_count': disliked_count,
            'can_get_recommendations': liked_count >= 1,
            'top_tags': dict(sorted(session['tag_weights'].items(), key=lambda x: x[1], reverse=True)[:5])
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

    return jsonify({
        'exists': True,
        'category': session['category'],
        'swipes': len(session['swipes']),
        'liked': liked_count,
        'disliked': disliked_count,
        'tag_weights': dict(sorted(session['tag_weights'].items(), key=lambda x: x[1], reverse=True)[:10]),
        'can_get_recommendations': liked_count >= 1
    }), 200

@app.route('/api/recommendations', methods=['POST'])
def get_recommendations():
    """Get tag-weighted recommendations (no AI cost - using pre-generated tags)"""
    try:
        data = request.json
        session_id = data.get('session_id')

        if session_id not in swipe_sessions:
            return jsonify({'error': 'Session not found'}), 404

        session = swipe_sessions[session_id]
        liked_items = [s['listing'] for s in session['swipes'] if s['action'] == 'like']

        if len(liked_items) == 0:
            return jsonify({'error': 'No liked items yet'}), 400
        
        user_category = session['category']
        tag_weights = session['tag_weights']
        
        print(f"🎯 Getting recommendations for category: {user_category}")
        print(f"🏷️  Tag weights: {dict(sorted(tag_weights.items(), key=lambda x: x[1], reverse=True)[:5])}")
        
        # Get all items from same category (excluding already swiped)
        swiped_ids = [s['listing']['_id'] for s in session['swipes']]
        
        available_items = list(collection.find({
            'category': user_category,
            '_id': {'$nin': [ObjectId(id) for id in swiped_ids]}
        }))
        
        # Score each item based on tag overlap
        scored_items = []
        for item in available_items:
            item_tags = item.get('tags', [])
            
            # Calculate score
            score = 0
            for tag in item_tags:
                score += tag_weights.get(tag, 0)
            
            # Average score
            if item_tags:
                score = score / len(item_tags)
            
            scored_items.append((score, item))
        
        # Sort by score and get top 10
        scored_items.sort(reverse=True, key=lambda x: x[0])
        recommendations = [item for score, item in scored_items[:10]]
        
        # Convert ObjectId to string
        for item in recommendations:
            item['_id'] = str(item['_id'])
        
        print(f"✅ Returning {len(recommendations)} recommendations")
        
        return jsonify({
            'category': user_category,
            'liked_count': len(liked_items),
            'count': len(recommendations),
            'products': recommendations
        }), 200

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ===== AI HELPER FUNCTIONS (for backup/fallback) =====

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