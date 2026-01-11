from pymongo import MongoClient

# MongoDB connection
MONGODB_URI = "mongodb+srv://thrifttinder:fishstick1212@sbhacks.nqf2fze.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(MONGODB_URI)
db = client['thrifttinderDB']
collection = db['listings']

print("🗑️  Cleaning up old listings without category field...\n")

# Find items without category
items_without_category = collection.count_documents({'category': {'$exists': False}})
print(f"Found {items_without_category} items without category field")

if items_without_category > 0:
    # Ask for confirmation
    response = input(f"\nDelete these {items_without_category} items? (yes/no): ")
    
    if response.lower() == 'yes':
        result = collection.delete_many({'category': {'$exists': False}})
        print(f"\n✅ Deleted {result.deleted_count} items")
    else:
        print("\n❌ Cancelled - no items deleted")
else:
    print("\n✅ Database is clean - all items have category field!")

# Show final stats
print(f"\n📊 Items remaining in database: {collection.count_documents({})}")
print("\nBreakdown by category:")
for category in ["mens_shirts", "womens_tops", "mens_jeans", "womens_skirts"]:
    count = collection.count_documents({"category": category})
    print(f"  {category}: {count} items")

client.close()