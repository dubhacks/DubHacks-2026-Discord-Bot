from shared import bot, logger, DISCORD_TOKEN
from tasks import audit_roles, event_reminders
import commands as _bot_commands  # noqa: F401  (registers the slash commands)


@bot.event
async def on_ready():
    logger.info(f"Bot is ready! Logged in as {bot.user}")
    logger.info(f"Bot is connected to {len(bot.guilds)} guilds")
    for guild in bot.guilds:
        logger.info(f"  - {guild.name} (id: {guild.id})")

    # Register slash commands per server so they show up immediately instead
    # of waiting on Discord's global propagation.
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            logger.info(f"Synced {len(synced)} slash commands to {guild.name}")
        except Exception as e:
            logger.error(f"Failed to sync slash commands to {guild.name}: {e}")

    if not audit_roles.is_running():
        audit_roles.start()
    if not event_reminders.is_running():
        event_reminders.start()


logger.info("Starting bot...")
bot.run(DISCORD_TOKEN)
