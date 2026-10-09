import asyncio
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import tasks

from shared import (bot, logger, ROLE_SOURCES, ANNOUNCE_CHANNEL, REMINDER_LEAD_MINUTES,
                    RESCHEDULE_CHECK_MINUTES)
from utils import (load_usernames, members_by_username, load_events,
                   announcement_text, find_announce_channel, HACKER_ROLE)


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


# ---------------------------------------------------------------------------
# Automatic event reminders: ping hackers REMINDER_LEAD_MINUTES before each
# workshop/activity starts, in the ANNOUNCE_CHANNEL of every guild.
#
# Rather than polling, the task loads the schedule, sleeps until the next
# reminder is due, sends it, and repeats. The sleep is capped so that events
# edited in the admin portal (which writes straight to Mongo) are picked up
# within RESCHEDULE_CHECK_MINUTES even though the bot gets no signal.
# ---------------------------------------------------------------------------

# (event id, start time) pairs already announced since the bot booted. Keyed
# on the start time too, so an event that gets rescheduled in the admin portal
# is announced again at its new time.
_reminded = set()


def _reminder_key(ev):
    return (ev["id"], ev["start"])


def _remind_at(ev):
    return ev["start"] - timedelta(minutes=REMINDER_LEAD_MINUTES)


def upcoming_reminders(limit=None):
    """Events that still have a reminder ahead of them, soonest first."""
    now = datetime.now(timezone.utc)
    pending = [
        ev for ev in load_events()
        if ev["start"] and ev["start"] > now and _reminder_key(ev) not in _reminded
    ]
    return pending[:limit] if limit else pending


async def _send_reminder(ev):
    _reminded.add(_reminder_key(ev))  # mark first so a send error can't cause a double ping
    headline = f"starts in {REMINDER_LEAD_MINUTES} minute{'s' if REMINDER_LEAD_MINUTES != 1 else ''}!"
    for guild in bot.guilds:
        channel = find_announce_channel(guild)
        if channel is None:
            logger.warning(
                f"No announcement channel '{ANNOUNCE_CHANNEL}' in {guild.name}; "
                f"skipping reminder for '{ev['name']}'")
            continue
        role = discord.utils.get(guild.roles, name=HACKER_ROLE)
        try:
            await channel.send(
                announcement_text(ev, role, headline),
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
            logger.info(f"Reminder sent for '{ev['name']}' in {guild.name}#{channel.name}")
        except Exception as e:
            logger.error(f"Error sending reminder for '{ev['name']}' in {guild.name}: {e}")


@tasks.loop(seconds=1)  # interval is irrelevant; each iteration sleeps until the next reminder
async def event_reminders():
    now = datetime.now(timezone.utc)

    # pymongo is synchronous; keep it off the event loop.
    events = await asyncio.to_thread(load_events)
    pending = sorted(
        (ev for ev in events
         if ev["start"] and ev["start"] > now and _reminder_key(ev) not in _reminded),
        key=_remind_at,
    )

    # Anything whose reminder time has already passed but hasn't started yet
    # (e.g. the bot booted 3 minutes before an event) goes out right away.
    while pending and _remind_at(pending[0]) <= now:
        await _send_reminder(pending.pop(0))

    if not pending:
        await asyncio.sleep(RESCHEDULE_CHECK_MINUTES * 60)
        return

    nxt = pending[0]
    wait = (_remind_at(nxt) - now).total_seconds()
    if wait > RESCHEDULE_CHECK_MINUTES * 60:
        # Too far out to trust the schedule won't change; re-check later.
        await asyncio.sleep(RESCHEDULE_CHECK_MINUTES * 60)
        return

    logger.info(f"Next reminder: '{nxt['name']}' in {wait / 60:.1f} min")
    await asyncio.sleep(wait)
    await _send_reminder(nxt)


@event_reminders.before_loop
async def before_event_reminders():
    await bot.wait_until_ready()
    logger.info(
        f"Event reminders active: pinging #{ANNOUNCE_CHANNEL} "
        f"{REMINDER_LEAD_MINUTES} minutes before each event")
