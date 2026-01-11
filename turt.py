from flask import Flask, jsonify, request
from pymongo import MongoClient
from bson import ObjectId
import json

from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# MongoDB connection
MONGODB_URI = "mongodb+srv://thrifttinder:poopshit69@sbhacks.nqf2fze.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(MONGODB_URI)
db = client['thrifttinderDB']
collection = db['listings']

# Custom JSON encoder to handle ObjectId
class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)

app.json_encoder = JSONEncoder

# Route 1: Get all listings
@app.route('/api/listings', methods=['GET'])
def get_all_listings():
    """Retrieve all listings from MongoDB"""
    try:
        listings = list(collection.find({}))
        
        # Convert ObjectId to string for JSON serialization
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

# Route 2: Get listings with filters (query parameters)
@app.route('/api/listings/filter', methods=['GET'])
def filter_listings():
    """Filter listings by brand, style, price range, size"""
    try:
        # Build query from parameters
        query = {}
        
        brand = request.args.get('brand')
        style = request.args.get('style')
        size = request.args.get('size')
        min_price = request.args.get('min_price')
        max_price = request.args.get('max_price')
        
        if brand:
            query['brand'] = {'$regex': brand, '$options': 'i'}  # Case-insensitive
        if style:
            query['style'] = {'$regex': style, '$options': 'i'}
        if size:
            query['size'] = {'$regex': size, '$options': 'i'}
        
        # Price range filter
        if min_price or max_price:
            query['price'] = {}
            if min_price:
                query['price']['$gte'] = float(min_price)
            if max_price:
                query['price']['$lte'] = float(max_price)
        
        listings = list(collection.find(query))
        
        # Convert ObjectId to string
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

# Route 3: Get single listing by ID
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

# Route 4: Get random listings (for "swipe" feature)
@app.route('/api/listings/random/<int:count>', methods=['GET'])
def get_random_listings(count):
    """Get random listings for swiping (Tinder-style)"""
    try:
        # MongoDB aggregation for random sampling
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

# Route 5: Get stats about your database
@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get statistics about the listings database"""
    try:
        total_count = collection.count_documents({})
        
        # Get brand distribution
        brands = collection.aggregate([
            {'$group': {'_id': '$brand', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ])
        
        # Get price stats
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

# Route 6: Search listings by name
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

if __name__ == '__main__':
    print("🚀 ThriftTinder API starting...")
    print(f"📊 Database has {collection.count_documents({})} listings")
    app.run(debug=True, port=5000)