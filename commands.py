import discord
from discord.ext import commands

from shared import bot, logger, ROLE_SOURCES
from tasks import audit_roles
from utils import load_usernames


@bot.command(name='ping')
async def ping_command(ctx):
    await ctx.send("Pong! 🏓")


@bot.command(name='audit_roles')
@commands.has_permissions(manage_roles=True)
async def manual_audit_roles(ctx):
    logger.info(f"Manual role audit triggered by {ctx.author}")
    try:
        await ctx.send("🔍 Starting role audit...")
        results = await audit_roles()
        lines = ["✅ Role audit completed!"]
        for role_name, counts in results.get(ctx.guild.id, {}).items():
            lines.append(
                f"• **{role_name}:** {counts['added']} newly assigned, "
                f"{counts['missing']} registered but haven't joined the server")
        await ctx.send("\n".join(lines))
    except Exception as e:
        logger.error(f"Error in manual role audit: {e}")
        await ctx.send(f"❌ Error: {str(e)}")


@manual_audit_roles.error
async def audit_roles_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need 'Manage Roles' permission to use this command.")


@bot.command(name='role_stats')
@commands.has_permissions(manage_roles=True)
async def role_stats_command(ctx):
    try:
        guild = ctx.guild
        lines = [f"**Role Statistics for {guild.name}**", ""]
        for collection_name, role_name in ROLE_SOURCES.items():
            role = discord.utils.get(guild.roles, name=role_name)
            in_server = len(role.members) if role else 0
            in_db = len(load_usernames(collection_name))
            lines.append(f"**{role_name}:** {in_server} in server, {in_db} in database")
        await ctx.send("\n".join(lines))
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")


@role_stats_command.error
async def role_stats_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need 'Manage Roles' permission.")


@bot.command(name='invite_check')
@commands.has_permissions(manage_guild=True)
async def invite_check_command(ctx, invite_code=None):
    """Show stats for an invite and list members who have no roles yet."""
    if not invite_code:
        await ctx.send("❌ Please provide an invite code. Usage: `!invite_check ABC123`")
        return

    try:
        guild = ctx.guild
        invite = discord.utils.get(await guild.invites(), code=invite_code)
        if not invite:
            await ctx.send(f"❌ Invite code `{invite_code}` not found in this server.")
            return

        await ctx.send(
            f"🔍 **Invite `{invite_code}`**\n"
            f"• Uses: {invite.uses}\n"
            f"• Max uses: {invite.max_uses or 'Unlimited'}\n"
            f"• Created by: {invite.inviter}\n"
            f"• Created: {invite.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )

        no_roles = [
            f"• {m.name} ({m.display_name})"
            for m in guild.members
            if not m.bot and all(r.is_default() for r in m.roles)
        ]
        if not no_roles:
            await ctx.send("✅ All members have roles assigned!")
            return

        await ctx.send(f"👥 **Members with no roles ({len(no_roles)} total):**")
        for i in range(0, len(no_roles), 10):
            await ctx.send("```\n" + "\n".join(no_roles[i:i + 10]) + "\n```")

    except Exception as e:
        logger.error(f"Error in invite_check command: {e}")
        await ctx.send(f"❌ Error: {str(e)}")


@invite_check_command.error
async def invite_check_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need 'Manage Server' permission to use this command.")
