import os
import sys
import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
from pymongo import MongoClient

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Load environment variables (same names as hacker-profile-2026 and Judging2026)
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
MONGO_DB = os.getenv('MONGO_DB', 'dev-cluster')

# Which MongoDB collection feeds which Discord role.
# Collections are the ones hacker-profile-2026 writes to. Each document has a
# "discord_id" field holding the member's Discord username (not numeric ID).
ROLE_SOURCES = {
    "hackers": "Hacker",
    "judges": "Judge",
}

# Set up MongoDB connection
try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
    db = mongo_client[MONGO_DB]
    mongo_client.admin.command('ping')
    logger.info(f"Successfully connected to MongoDB database '{MONGO_DB}'")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    mongo_client = None
    db = None

# Set up Discord bot
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
