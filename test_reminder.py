#!/usr/bin/env python3
"""
Insert a throwaway workshop that starts a few minutes from now, so the
automatic reminder can be watched end to end. Reads MONGO_URI / MONGO_DB from
.env, exactly like the bot does, so point MONGO_DB at a scratch database first.

Usage:
    python test_reminder.py            # event starts in 3 minutes
    python test_reminder.py 7          # event starts in 7 minutes
    python test_reminder.py --cleanup  # delete every event this script created
"""

import os
import re
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from pymongo import MongoClient

TEST_NAME_PREFIX = "[TEST] Reminder check"

load_dotenv()
client = MongoClient(os.getenv("MONGO_URI"), serverSelectionTimeoutMS=10000)
db = client[os.getenv("MONGO_DB", "dev-cluster")]
coll = db["workshops"]

if "--cleanup" in sys.argv:
    result = coll.delete_many({"name": {"$regex": "^" + re.escape(TEST_NAME_PREFIX)}})
    print(f"Deleted {result.deleted_count} test event(s) from '{db.name}.workshops'")
    sys.exit(0)

minutes = int(sys.argv[1]) if len(sys.argv) > 1 else 3
start = datetime.now(timezone.utc) + timedelta(minutes=minutes)
doc = {
    "name": f"{TEST_NAME_PREFIX} {start.strftime('%H:%M:%S')} UTC",
    "start": start,
    "end": start + timedelta(minutes=30),
    "location": "Nowhere (test)",
    "dubcoinReward": 0,
}
inserted = coll.insert_one(doc)
lead = int(os.getenv("REMINDER_LEAD_MINUTES", "5"))
print(f"Inserted '{doc['name']}' into '{db.name}.workshops' (id {inserted.inserted_id})")
print(f"Starts in {minutes} min; with REMINDER_LEAD_MINUTES={lead} the ping is due in {minutes - lead} min")
print(f"Target channel: {os.getenv('ANNOUNCE_CHANNEL', 'announcements')}")
print("Run `python test_reminder.py --cleanup` when done.")
