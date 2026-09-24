from shared import bot, logger, DISCORD_TOKEN
from tasks import audit_roles
import commands  # Import commands module to register the commands


@bot.event
async def on_ready():
    logger.info(f"Bot is ready! Logged in as {bot.user}")
    logger.info(f"Bot is connected to {len(bot.guilds)} guilds")
    for guild in bot.guilds:
        logger.info(f"  - {guild.name} (id: {guild.id})")

    if not audit_roles.is_running():
        audit_roles.start()


@bot.event
async def on_command_error(ctx, error):
    logger.error(f"Command error in {ctx.command}: {error}")

logger.info("Starting bot...")
bot.run(DISCORD_TOKEN)
