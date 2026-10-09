import asyncio

import discord
from discord import app_commands

from shared import bot, logger, mongo_client, MONGO_DB, ROLE_SOURCES, ANNOUNCE_CHANNEL, REMINDER_LEAD_MINUTES
from tasks import audit_roles, event_reminders, upcoming_reminders
from utils import (load_usernames, load_events, format_schedule, fmt_event_window,
                   announcement_text, find_announce_channel)

# Every command here is a slash command. The Staff role gate lives in
# StaffOnlyTree (shared.py), so nothing below needs its own permission check.
# Replies are ephemeral (only the invoker sees them) except the public
# announcement posted by /announce_event.

HACKER_ROLE = ROLE_SOURCES["hackers"]

# (command, what it does) for /help.
COMMAND_HELP = [
    ("/help", "List the commands"),
    ("/ping", "Check that the bot is alive and the database is reachable"),
    ("/list_schedule", "List every workshop and activity with time and room"),
    ("/announce_event", "Pick an event from a dropdown and ping all hackers about it"),
    ("/audit_roles", "Run the Hacker/Judge role sync now and report the result"),
    ("/role_stats", "Compare Hacker/Judge counts in the server against the database"),
    ("/invite_check", "Show usage for an invite link and list members with no roles"),
    ("/reminders", "Show which events the automatic reminder will ping next"),
]


@bot.tree.command(name="help", description="List the bot's commands")
async def help_command(interaction: discord.Interaction):
    lines = [f"`{name}` - {desc}" for name, desc in COMMAND_HELP]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="ping", description="Check that the bot and database are up")
async def ping_command(interaction: discord.Interaction):
    db_ok = False
    if mongo_client is not None:
        try:
            # pymongo is synchronous; run the ping off the event loop.
            await asyncio.to_thread(mongo_client.admin.command, "ping")
            db_ok = True
        except Exception as e:
            logger.error(f"DB ping failed: {e}")
    if db_ok:
        text = f"✅ Alive and running, DB connected ({MONGO_DB})"
    else:
        text = "❌ Alive and running, but DB is unreachable"
    await interaction.response.send_message(text, ephemeral=True)


@bot.tree.command(name="list_schedule", description="List every workshop and activity with time and room")
async def list_schedule_command(interaction: discord.Interaction):
    events = load_events()
    if not events:
        await interaction.response.send_message("No workshops or activities found in the database.", ephemeral=True)
        return

    # One embed per day: the day is the title, the body is one chronological table.
    embeds = [
        discord.Embed(title=day_title, description=table, color=0xFF66AD)
        for day_title, table in format_schedule(events)
    ]
    await interaction.response.send_message(embeds=embeds[:10], ephemeral=True)
    for i in range(10, len(embeds), 10):  # Discord allows 10 embeds per message
        await interaction.followup.send(embeds=embeds[i:i + 10], ephemeral=True)


@bot.tree.command(name="audit_roles", description="Run the Hacker/Judge role sync now")
async def audit_roles_command(interaction: discord.Interaction):
    logger.info(f"Manual role audit triggered by {interaction.user}")
    await interaction.response.defer(ephemeral=True, thinking=True)  # audit can take a while
    results = await audit_roles()
    lines = ["✅ Role audit completed"]
    for role_name, counts in results.get(interaction.guild.id, {}).items():
        lines.append(
            f"• **{role_name}:** {counts['added']} newly assigned, "
            f"{counts['missing']} registered but haven't joined the server")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="role_stats", description="Compare Hacker/Judge counts in the server against the database")
async def role_stats_command(interaction: discord.Interaction):
    guild = interaction.guild
    lines = [f"**Role Statistics for {guild.name}**", ""]
    for collection_name, role_name in ROLE_SOURCES.items():
        role = discord.utils.get(guild.roles, name=role_name)
        in_server = len(role.members) if role else 0
        in_db = len(load_usernames(collection_name))
        lines.append(f"**{role_name}:** {in_server} in server, {in_db} in database")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="invite_check", description="Show invite usage and list members who have no roles yet")
@app_commands.describe(invite_code="The invite code, e.g. ABC123")
async def invite_check_command(interaction: discord.Interaction, invite_code: str):
    guild = interaction.guild
    invite = discord.utils.get(await guild.invites(), code=invite_code)
    if not invite:
        await interaction.response.send_message(f"Invite code `{invite_code}` not found in this server.", ephemeral=True)
        return

    lines = [
        f"**Invite `{invite_code}`**",
        f"• Uses: {invite.uses}",
        f"• Max uses: {invite.max_uses or 'Unlimited'}",
        f"• Created by: {invite.inviter}",
        f"• Created: {invite.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
    ]

    no_roles = [
        f"{m.name} ({m.display_name})"
        for m in guild.members
        if not m.bot and all(r.is_default() for r in m.roles)
    ]
    if not no_roles:
        lines.append("✅ All members have roles assigned.")
    else:
        lines.append(f"**Members with no roles ({len(no_roles)}):**")
        lines.append("```\n" + "\n".join(no_roles[:50]) + "\n```")
        if len(no_roles) > 50:
            lines.append(f"...and {len(no_roles) - 50} more.")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


# ---------------------------------------------------------------------------
# /announce_event: pick an event from a private dropdown, then ping all hackers.
# ---------------------------------------------------------------------------

def _event_option(index, ev):
    """Dropdown option for one event (label and description max 100 chars)."""
    return discord.SelectOption(
        label=ev["name"][:100],
        description=f"{fmt_event_window(ev)} | {ev['location']}"[:100],
        value=str(index),
    )


class EventPicker(discord.ui.View):
    """Private dropdown; selecting an event posts the announcement to the channel."""

    def __init__(self, invoker_id, events):
        super().__init__(timeout=120)
        self.invoker_id = invoker_id
        self.events = events
        self.select = discord.ui.Select(
            placeholder="Choose an event to announce",
            options=[_event_option(i, ev) for i, ev in enumerate(events)],
        )
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def interaction_check(self, interaction):
        return interaction.user.id == self.invoker_id

    async def on_select(self, interaction):
        ev = self.events[int(self.select.values[0])]
        role = discord.utils.get(interaction.guild.roles, name=HACKER_ROLE)
        await interaction.channel.send(
            announcement_text(ev, role),
            allowed_mentions=discord.AllowedMentions(roles=True),
        )
        logger.info(f"{interaction.user} announced event '{ev['name']}'")
        await interaction.response.edit_message(content=f"Announced **{ev['name']}**.", view=None)
        self.stop()


@bot.tree.command(name="announce_event", description="Pick an event and ping all hackers about it in this channel")
async def announce_event_command(interaction: discord.Interaction):
    events = load_events()
    if not events:
        await interaction.response.send_message("No workshops or activities found in the database.", ephemeral=True)
        return
    events = events[:25]  # Discord dropdowns hold at most 25 options.
    await interaction.response.send_message(
        "Which event should I announce? Pick one below.",
        view=EventPicker(interaction.user.id, events),
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# /reminders: show what the automatic 5-minute-before pinger is going to do.
# ---------------------------------------------------------------------------

@bot.tree.command(name="reminders", description="Show the next events the automatic reminder will ping")
async def reminders_command(interaction: discord.Interaction):
    channel = find_announce_channel(interaction.guild)
    status = "running" if event_reminders.is_running() else "**not running**"
    where = channel.mention if channel else f"**no channel named `{ANNOUNCE_CHANNEL}` found**"
    lines = [
        f"Automatic reminders are {status}, posting to {where} "
        f"{REMINDER_LEAD_MINUTES} minutes before each event.",
        "",
    ]
    upcoming = await asyncio.to_thread(upcoming_reminders, 10)
    if not upcoming:
        lines.append("No upcoming events left to remind about.")
    else:
        lines.append("**Next up:**")
        lines += [f"• {fmt_event_window(ev)} - {ev['name']} ({ev['location']})" for ev in upcoming]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)
