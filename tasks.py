import asyncio
import discord
from discord.ext import tasks

from shared import bot, logger, ROLE_SOURCES
from utils import load_usernames, members_by_username


@tasks.loop(minutes=10)
async def audit_roles():
    logger.info("Starting role audit...")
    authorized = {name: load_usernames(coll) for coll, name in ROLE_SOURCES.items()}
    results = {}  # guild.id -> {role_name: {"added": n, "missing": n}}

    for guild in bot.guilds:
        lookup = members_by_username(guild)
        results[guild.id] = {}

        for role_name, usernames in authorized.items():
            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                logger.info(f"No '{role_name}' role in {guild.name}, skipping")
                continue

            added = 0
            missing = []
            for username in usernames:
                member = lookup.get(username)
                if member is None:
                    missing.append(username)
                    continue
                if role in member.roles:
                    continue
                try:
                    await member.add_roles(role, reason="Role audit")
                    logger.info(f"Added {role_name} role to {member.display_name}")
                    added += 1
                except Exception as e:
                    logger.error(f"Error adding {role_name} role to {member.display_name}: {e}")
                await asyncio.sleep(0.5)

            results[guild.id][role_name] = {"added": added, "missing": len(missing)}
            logger.info(
                f"{role_name} audit for {guild.name}: {added} added, "
                f"{len(missing)} usernames not in server")

    logger.info("Role audit completed")
    return results


@audit_roles.before_loop
async def before_audit_roles():
    await bot.wait_until_ready()
    # The loop would otherwise fire immediately on startup. Wait one full
    # interval first so the initial audit happens 10 minutes after boot.
    await asyncio.sleep(audit_roles.minutes * 60)
