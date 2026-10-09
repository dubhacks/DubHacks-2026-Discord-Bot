import os
import sys
import discord
from discord import app_commands
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

# Collections written by the hacker-profile-2026 admin portal. Each document has
# name, start, end (UTC datetimes), location, and dubcoinReward.
EVENT_SOURCES = {
    "workshops": "Workshop",
    "activities": "Activity",
}

# Only members holding this Discord role may run any bot command.
STAFF_ROLE = "Staff"

# Timezone used when displaying event times.
EVENT_TZ = "America/Los_Angeles"

# Where the automatic event reminders are posted. Either a channel name
# (e.g. "announcements") or a numeric channel ID.
ANNOUNCE_CHANNEL = os.getenv("ANNOUNCE_CHANNEL", "announcements")

# How many minutes before an event starts the automatic reminder goes out.
REMINDER_LEAD_MINUTES = int(os.getenv("REMINDER_LEAD_MINUTES", "5"))

# How often the reminder task re-reads the schedule from Mongo while idle, so
# events edited in the admin portal are picked up. Lower it (e.g. 1) when testing.
RESCHEDULE_CHECK_MINUTES = int(os.getenv("RESCHEDULE_CHECK_MINUTES", "10"))

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

# Set up Discord bot. All commands are slash commands, so the bot never reads
# message content and nothing typed in chat can trigger it.
intents = discord.Intents.default()
intents.guilds = True
intents.members = True


class StaffOnlyTree(app_commands.CommandTree):
    """Command tree that refuses every slash command unless the user has the Staff role."""

    async def interaction_check(self, interaction):
        if interaction.guild is None:
            return False
        return any(role.name == STAFF_ROLE for role in interaction.user.roles)

    async def on_error(self, interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            message = "Only members with the Staff role can use this bot."
        else:
            logger.error(f"Slash command error in {interaction.command}: {error}")
            message = f"Error: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


bot = commands.Bot(
    command_prefix=commands.when_mentioned,  # unused; no text commands are registered
    intents=intents,
    help_command=None,
    tree_cls=StaffOnlyTree,
)
