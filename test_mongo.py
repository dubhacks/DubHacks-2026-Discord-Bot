#!/usr/bin/env python3
"""
Sanity-check the MongoDB connection and print what the bot will see.
Usage: python test_mongo.py
"""

import os
from dotenv import load_dotenv
from pymongo import MongoClient


def test_mongodb_connection():
    load_dotenv()
    mongo_uri = os.getenv('MONGO_URI')
    mongo_db = os.getenv('MONGO_DB', 'dev-cluster')

    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=10000)
        db = client[mongo_db]
        client.admin.command('ping')
        print(f"✅ Connected to MongoDB database '{mongo_db}'")
        print(f"📁 Collections: {sorted(db.list_collection_names())}")

        for name in ("hackers", "judges", "staff"):
            coll = db[name]
            total = coll.count_documents({})
            with_discord = coll.count_documents(
                {"discord_id": {"$exists": True, "$nin": [None, ""]}})
            sample = coll.find_one({}, {"_id": 0})
            print(f"\n📊 {name}: {total} documents, {with_discord} with a discord_id")
            print(f"   Keys: {sorted(sample.keys()) if sample else 'no documents'}")
        return True

    except Exception as e:
        print(f"❌ Failed to connect to MongoDB: {e}")
        return False


if __name__ == "__main__":
    test_mongodb_connection()
