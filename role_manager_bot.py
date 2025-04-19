# slash_role_manager_bot.py (Version with All Features: Role Mgmt, Separators, Clear, Warn/Unwarn, Spam Detect, Auto Role)

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import get
import os
import datetime # Needed for spam detection timing

# --- Configuration ---
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ FATAL ERROR: The DISCORD_BOT_TOKEN environment variable is not set.")
    print("   Please set this variable in your hosting environment (e.g., Railway Variables).")
    exit()

COMMAND_PREFIX = "!" # Legacy prefix (mostly unused now)

# --- Intents Configuration ---
intents = discord.Intents.default()
intents.members = True      # REQUIRED for on_member_join, member info, member commands
intents.message_content = True # REQUIRED for on_message spam detection

# --- Bot Initialization ---
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

# --- Spam Detection Configuration & Storage ---
SPAM_COUNT_THRESHOLD = 5  # Messages within window to trigger
SPAM_TIME_WINDOW_SECONDS = 5 # Time window (seconds)
KICK_THRESHOLD = 3 # Warnings before kick (applies to both auto and manual warnings)

# In-memory storage (cleared on bot restart)
user_message_timestamps = {} # Stores {user_id: [timestamp1, timestamp2, ...]}
user_warnings = {} # Stores {user_id: warning_count}

# --- Event: Bot Ready ---
@bot.event
async def on_ready():
    """Called when the bot is ready and has finished syncing commands."""
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('Syncing application commands...')
    try:
        # --- Choose ONE sync method ---
        # 1. Global Sync (might take up to an hour initially)
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} application command(s) globally.')

        # 2. Guild Sync (for testing, nearly instant)
        # guild_id = 123456789012345678 # <<< REPLACE WITH YOUR SERVER ID (integer)
        # synced = await bot.tree.sync(guild=discord.Object(id=guild_id))
        # print(f'Synced {len(synced)} application command(s) to guild {guild_id}.')
        # --- End of sync method choice ---

    except Exception as e:
        print(f'Error syncing commands: {e}')
    print('Bot is ready!')
    print('------')
    await bot.change_presence(activity=discord.Game(name="/help for commands"))

# --- Event: Command Error Handling (Legacy Prefix Commands) ---
@bot.event
async def on_command_error(ctx, error):
    # Handles potential errors if legacy commands are somehow invoked
    if isinstance(error, commands.CommandNotFound): return
    elif isinstance(error, commands.MissingPermissions): await ctx.send(f"🚫 PrefixCmd: Missing Perms: {error.missing_permissions}")
    else: print(f"Error with prefix command {ctx.command}: {error}")

# --- Event: App Command Error Handling ---
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Handles errors specifically for application commands."""
    # (Comprehensive error handling from previous examples)
    if isinstance(error, app_commands.CommandNotFound): await interaction.response.send_message("Unknown command.", ephemeral=True)
    elif isinstance(error, app_commands.MissingPermissions): await interaction.response.send_message(f"🚫 You need permission: {', '.join(f'`{p}`' for p in error.missing_permissions)}.", ephemeral=True)
    elif isinstance(error, app_commands.BotMissingPermissions): await interaction.response.send_message(f"🤖 Bot needs permission: {', '.join(f'`{p}`' for p in error.missing_permissions)}.", ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure): await interaction.response.send_message("🚫 You do not have permission to use this command.", ephemeral=True)
    elif isinstance(error, app_commands.CommandInvokeError):
        original = error.original
        if isinstance(original, discord.Forbidden): await interaction.response.send_message(f"🚫 Discord Permissions Error (often role hierarchy).", ephemeral=True)
        else:
            print(f'Unhandled error in app command {interaction.command.name if interaction.command else "Unknown"}: {original}')
            message = "⚙️ An unexpected error occurred."
            if not interaction.response.is_done(): await interaction.response.send_message(message, ephemeral=True)
            else: await interaction.followup.send(message, ephemeral=True)
    else:
        print(f'Unhandled app command error type: {type(error).__name__} - {error}')
        message = "🤔 An unknown error occurred."
        if not interaction.response.is_done(): await interaction.response.send_message(message, ephemeral=True)
        else: await interaction.followup.send(message, ephemeral=True)
# Add the error handler to the tree
bot.tree.on_error = on_app_command_error

# --- Event: Member Join - Assign Separator Roles & Welcome ---
@bot.event
async def on_member_join(member: discord.Member):
    """Automatically assigns specific pre-existing separator roles and sends a welcome message."""
    guild = member.guild
    print(f'[+] {member.name} ({member.id}) joined {guild.name}')

    # --- Define the EXACT names of your pre-existing separator roles ---
    # !!! IMPORTANT: Replace these with the exact names you created in your server !!!
    separator_role_names_to_assign = [
        "▲─────身分─────",   # <-- 替换!
        "▲─────通知─────",   # <-- 替换!
        "▲─────其他─────"    # <-- 替换!
        # Add more separator role names here if needed
    ]

    roles_to_add = []
    roles_failed = []

    # --- Assign Separator Roles ---
    for role_name in separator_role_names_to_assign:
        role = get(guild.roles, name=role_name)
        if role:
            if role < guild.me.top_role or guild.me == guild.owner: roles_to_add.append(role)
            else: roles_failed.append(f"{role_name} (层级不足)")
        else: roles_failed.append(f"{role_name} (未找到!)") # Critical if name is wrong

    if roles_to_add:
        try:
            await member.add_roles(*roles_to_add, reason="Auto-assigned separator roles on join")
            print(f"✅ Assigned {len(roles_to_add)} separators to {member.name}.")
        except Exception as e: # Catch broad errors during assignment
            print(f"❌ Error assigning roles to {member.name}: {e}")
            roles_failed.extend([f"{r.name} ({type(e).__name__})" for r in roles_to_add]) # Mark all as failed

    if roles_failed: print(f"‼️ Could not assign for {member.name}: {', '.join(roles_failed)}")

    # --- (Optional) Send Welcome Message ---
    # !!! IMPORTANT: Replace channel IDs below with your actual channel IDs !!!
    welcome_channel_id = 123456789012345678      # <--- 替换! 欢迎频道ID
    rules_channel_id = 123456789012345679        # <--- 替换! 规则频道ID
    roles_info_channel_id = 123456789012345680   # <--- 替换! 身份组介绍频道ID
    verification_channel_id = 123456789012345681 # <--- 替换! 实力认证频道ID

    welcome_channel = guild.get_channel(welcome_channel_id)
    if welcome_channel and isinstance(welcome_channel, discord.TextChannel):
        try:
            embed = discord.Embed(
                title=f"🎉 欢迎来到 {guild.name}! 🎉",
                description=f"你好 {member.mention}! 很高兴你能加入 **GJ Team**！\n\n"
                            f"👇 **为了更好的体验, 请先:**\n"
                            f"- 阅读服务器规则: <#{rules_channel_id}>\n"
                            f"- 了解身份组信息: <#{roles_info_channel_id}>\n"
                            f"- 认证你的TSB实力: <#{verification_channel_id}>\n"
                            f"\n祝你在 GJ Team 玩得愉快!",
                color=discord.Color.blue() # Customize color
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"你是服务器的第 {guild.member_count} 位成员！")
            await welcome_channel.send(embed=embed)
            print(f"Sent welcome message for {member.name}.")
        except Exception as e: print(f"❌ Error sending welcome message: {e}")
    elif welcome_channel_id != 123456789012345678: # Only warn if ID was changed
        print(f"⚠️ Welcome channel {welcome_channel_id} not found.")


# --- Event: On Message - Spam Detection & Action ---
@bot.event
async def on_message(message: discord.Message):
    # Ignore bots and DMs
    if message.author.bot or not message.guild: return

    # --- Process legacy prefix commands FIRST (if any) ---
    if message.content.startswith(COMMAND_PREFIX):
        await bot.process_commands(message)
        # return # Uncomment this if prefix commands should bypass spam detection

    # --- Spam Detection Logic ---
    author_id = message.author.id
    now = datetime.datetime.now(datetime.timezone.utc)

    # Ignore users with Manage Messages permission (mods/admins)
    member = message.guild.get_member(author_id) # Get member object
    if member and message.channel.permissions_for(member).manage_messages: return

    # Initialize tracking if needed
    user_message_timestamps.setdefault(author_id, [])
    user_warnings.setdefault(author_id, 0)

    # Add timestamp & clean up old ones
    user_message_timestamps[author_id].append(now)
    time_limit = now - datetime.timedelta(seconds=SPAM_TIME_WINDOW_SECONDS)
    user_message_timestamps[author_id] = [ts for ts in user_message_timestamps[author_id] if ts > time_limit]

    # Check threshold
    message_count = len(user_message_timestamps[author_id])
    if message_count >= SPAM_COUNT_THRESHOLD:
        print(f"🚨 Spam detected: {message.author} ({author_id}) in #{message.channel.name}")
        user_warnings[author_id] += 1
        warning_count = user_warnings[author_id]
        print(f"   User warnings: {warning_count}/{KICK_THRESHOLD}")
        user_message_timestamps[author_id] = [] # Reset timestamps after detection

        # Check kick threshold
        if warning_count >= KICK_THRESHOLD:
            print(f"   Kick threshold reached for {message.author}.")
            if member: # Ensure member object is valid
                bot_member = message.guild.me
                kick_reason = f"自动踢出：刷屏警告达到 {KICK_THRESHOLD} 次。"
                if bot_member.guild_permissions.kick_members and (bot_member.top_role > member.top_role or bot_member == message.guild.owner):
                    try:
                        try: await member.send(f"你已被踢出服务器 **{message.guild.name}**。\n原因：**{kick_reason}**")
                        except Exception as dm_err: print(f"   Could not send kick DM to {member.name}: {dm_err}")
                        await member.kick(reason=kick_reason)
                        print(f"   Kicked {member.name}.")
                        await message.channel.send(f"👢 {member.mention} 已被自动踢出，原因：刷屏警告次数过多。")
                        user_warnings[author_id] = 0 # Reset warnings on successful kick
                    except Exception as kick_err: print(f"   Error during kick: {kick_err}"); await message.channel.send(f"⚙️ 踢出 {member.mention} 时发生错误。")
                else: print(f"   Bot lacks perms/hierarchy to kick {member.name}."); await message.channel.send(f"⚠️ 无法踢出 {member.mention} (权限/层级不足)。")
            else: print(f"   Could not get Member object for {author_id} to perform kick.")
        else: # Send warning if not kicking
            try: await message.channel.send(f"⚠️ {message.author.mention}，请减缓发言！({warning_count}/{KICK_THRESHOLD} 警告)", delete_after=15)
            except Exception as warn_err: print(f"   Error sending warning message: {warn_err}")


# --- Slash Command: Help ---
@bot.tree.command(name="help", description="Shows information about available commands.")
async def slash_help(interaction: discord.Interaction):
    """Provides help information via slash command."""
    embed = discord.Embed(
        title="🤖 GJ Team Role Manager Bot Help",
        description="Here are the available slash commands:",
        color=discord.Color.purple()
    )
    embed.add_field(
        name="🛠️ Moderation & Management",
        value=("/createrole `role_name` - Creates a new standard role.\n"
               "/deleterole `role_name` - Deletes a role.\n"
               "/giverole `user` `role_name` - Assigns a role.\n"
               "/takerole `user` `role_name` - Removes a role.\n"
               "/createseparator `label` - Creates a visual separator role.\n"
               "/clear `amount` - Deletes messages (max 100).\n"
               "/warn `user` `[reason]` - Manually issues a warning.\n"
               "/unwarn `user` `[reason]` - Removes one warning."),
        inline=False
    )
    embed.add_field(
        name="ℹ️ Other",
        value="/help - Shows this message.",
        inline=False
    )
    embed.set_footer(text="<> = Required, [] = Optional. Admin permissions needed for most commands.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Slash Command: Create Role ---
@bot.tree.command(name="createrole", description="Creates a new role in the server.")
@app_commands.describe(role_name="The exact name for the new role.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_createrole(interaction: discord.Interaction, role_name: str):
    guild = interaction.guild; await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("Server only.", ephemeral=True); return
    if get(guild.roles, name=role_name): await interaction.followup.send(f"Role **{role_name}** exists!", ephemeral=True); return
    if len(role_name) > 100: await interaction.followup.send("Role name too long.", ephemeral=True); return
    try:
        new_role = await guild.create_role(name=role_name, reason=f"Created by {interaction.user}")
        await interaction.followup.send(f"✅ Created role: {new_role.mention}", ephemeral=False)
    except Exception as e: print(f"Error /createrole: {e}"); await interaction.followup.send(f"⚙️ Error: {e}", ephemeral=True)

# --- Slash Command: Delete Role ---
@bot.tree.command(name="deleterole", description="Deletes an existing role by its exact name.")
@app_commands.describe(role_name="The exact name of the role to delete.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_deleterole(interaction: discord.Interaction, role_name: str):
    guild = interaction.guild; await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("Server only.", ephemeral=True); return
    role = get(guild.roles, name=role_name)
    if not role: await interaction.followup.send(f"❓ Role **{role_name}** not found.", ephemeral=True); return
    if role == guild.default_role: await interaction.followup.send("🚫 Cannot delete `@everyone`.", ephemeral=True); return
    if role >= guild.me.top_role and guild.me != guild.owner: await interaction.followup.send(f"🚫 Bot Hierarchy Error deleting {role.mention}.", ephemeral=True); return
    if role.is_integration() or role.is_premium_subscriber() or role.is_bot_managed(): await interaction.followup.send(f"⚠️ Cannot delete managed role {role.mention}.", ephemeral=True); return
    try:
        name = role.name
        await role.delete(reason=f"Deleted by {interaction.user}")
        await interaction.followup.send(f"✅ Deleted role: **{name}**", ephemeral=False)
    except Exception as e: print(f"Error /deleterole: {e}"); await interaction.followup.send(f"⚙️ Error: {e}", ephemeral=True)

# --- Slash Command: Give Role ---
@bot.tree.command(name="giverole", description="Assigns a role to a specified member.")
@app_commands.describe(user="The user to give the role to.", role_name="The exact name of the role to assign.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_giverole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    guild = interaction.guild; await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("...", ephemeral=True); return
    role = get(guild.roles, name=role_name)
    if not role: await interaction.followup.send(f"❓ Role **{role_name}** not found.", ephemeral=True); return
    if role >= guild.me.top_role and guild.me != guild.owner: await interaction.followup.send(f"🚫 Bot Hierarchy Error assigning {role.mention}.", ephemeral=True); return
    if role >= interaction.user.top_role and interaction.user != guild.owner: await interaction.followup.send(f"🚫 User Hierarchy Error assigning {role.mention}.", ephemeral=True); return
    if role in user.roles: await interaction.followup.send(f"ℹ️ {user.mention} already has {role.mention}.", ephemeral=True); return
    try:
        await user.add_roles(role, reason=f"Added by {interaction.user}")
        await interaction.followup.send(f"✅ Gave {role.mention} to {user.mention}.", ephemeral=False)
    except Exception as e: print(f"Error /giverole: {e}"); await interaction.followup.send(f"⚙️ Error: {e}", ephemeral=True)

# --- Slash Command: Take Role ---
@bot.tree.command(name="takerole", description="Removes a role from a specified member.")
@app_commands.describe(user="The user to remove the role from.", role_name="The exact name of the role to remove.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_takerole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    guild = interaction.guild; await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("...", ephemeral=True); return
    role = get(guild.roles, name=role_name)
    if not role: await interaction.followup.send(f"❓ Role **{role_name}** not found.", ephemeral=True); return
    if role >= guild.me.top_role and guild.me != guild.owner: await interaction.followup.send(f"🚫 Bot Hierarchy Error removing {role.mention}.", ephemeral=True); return
    if role >= interaction.user.top_role and interaction.user != guild.owner: await interaction.followup.send(f"🚫 User Hierarchy Error removing {role.mention}.", ephemeral=True); return
    if role not in user.roles: await interaction.followup.send(f"ℹ️ {user.mention} doesn't have {role.mention}.", ephemeral=True); return
    if role.is_integration() or role.is_premium_subscriber() or role.is_bot_managed(): await interaction.followup.send(f"⚠️ Cannot remove managed role {role.mention}.", ephemeral=True); return
    try:
        await user.remove_roles(role, reason=f"Removed by {interaction.user}")
        await interaction.followup.send(f"✅ Removed {role.mention} from {user.mention}.", ephemeral=False)
    except Exception as e: print(f"Error /takerole: {e}"); await interaction.followup.send(f"⚙️ Error: {e}", ephemeral=True)

# --- Slash Command: Create Separator Role ---
@bot.tree.command(name="createseparator", description="Creates a visual separator role.")
@app_commands.describe(label="The text to display inside the separator (e.g., '身分', '通知').")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_createseparator(interaction: discord.Interaction, label: str):
    guild = interaction.guild; await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("...", ephemeral=True); return
    separator_name = f"▲─────{label}─────" # Customize format here if needed
    if len(separator_name) > 100: await interaction.followup.send(f"❌ Label too long.", ephemeral=True); return
    if get(guild.roles, name=separator_name): await interaction.followup.send(f"⚠️ Separator **{separator_name}** exists!", ephemeral=True); return
    try:
        new_role = await guild.create_role(
            name=separator_name, permissions=discord.Permissions.none(), color=discord.Color.light_grey(),
            hoist=False, mentionable=False, reason=f"Separator created by {interaction.user}")
        await interaction.followup.send(
            f"✅ Created separator: **{new_role.name}**\n**重要:** 请去 **服务器设置 -> 身份组** 手动拖动此身份组到目标位置！",
            ephemeral=False)
    except Exception as e: print(f"Error /createseparator: {e}"); await interaction.followup.send(f"⚙️ Error: {e}", ephemeral=True)

# --- Slash Command: Clear Messages ---
@bot.tree.command(name="clear", description="Deletes a specified number of messages in this channel.")
@app_commands.describe(amount="Number of messages to delete (1-100).")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
async def slash_clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel): await interaction.response.send_message("Text channels only.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    try:
        deleted = await channel.purge(limit=amount)
        await interaction.followup.send(f"✅ Deleted {len(deleted)} message(s).", ephemeral=True)
    except Exception as e: print(f"Error /clear: {e}"); await interaction.followup.send(f"⚙️ Error: {e}", ephemeral=True)

# --- Slash Command: Manually Warn User ---
@bot.tree.command(name="warn", description="Manually issues a warning to a user.")
@app_commands.describe(user="The user to warn.", reason="The reason for the warning (optional).")
@app_commands.checks.has_permissions(kick_members=True) # Require Kick perms to warn
async def slash_warn(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    guild = interaction.guild; author = interaction.user
    if not guild: await interaction.response.send_message("...", ephemeral=True); return
    if user.bot: await interaction.response.send_message("Cannot warn bots.", ephemeral=True); return
    if user == author: await interaction.response.send_message("Cannot warn yourself.", ephemeral=True); return
    if isinstance(author, discord.Member) and isinstance(user, discord.Member): # Check roles only if both are members
         if user.top_role >= author.top_role and author != guild.owner: await interaction.response.send_message(f"🚫 Cannot warn {user.mention} (Role Hierarchy).", ephemeral=True); return

    await interaction.response.defer(ephemeral=False) # Make warning embed visible
    user_id = user.id
    user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
    warning_count = user_warnings[user_id]
    print(f"⚠️ Manual Warn: {author} warned {user}. Reason: {reason}. New count: {warning_count}/{KICK_THRESHOLD}")

    embed = discord.Embed(color=discord.Color.orange())
    embed.set_author(name=f"Warning by {author.display_name}", icon_url=author.display_avatar.url)
    embed.add_field(name="User Warned", value=user.mention, inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Current Warnings", value=f"{warning_count} / {KICK_THRESHOLD}", inline=False)
    embed.timestamp = discord.utils.utcnow()

    if warning_count >= KICK_THRESHOLD:
        embed.title = "🚨 Warning Limit Reached - User Kicked 🚨"; embed.color = discord.Color.red(); embed.add_field(name="Action Taken", value="Kicked", inline=False)
        print(f"   Kick threshold reached for {user.name} (Manual Warn).")
        bot_member = guild.me; kick_allowed = False; kick_fail_reason = "Unknown Error"
        if bot_member.guild_permissions.kick_members and (bot_member.top_role > user.top_role or bot_member == guild.owner): kick_allowed = True
        else: kick_fail_reason = "Bot Permissions/Hierarchy"; print(f"   Kick Fail: {kick_fail_reason}")

        if kick_allowed:
            try:
                kick_dm = f"你因累计达到 {KICK_THRESHOLD} 次警告而被踢出 **{guild.name}** (最后警告 by {author.display_name}: {reason})。"
                try: await user.send(kick_dm)
                except Exception as dm_err: print(f"   Kick DM Error: {dm_err}")
                await user.kick(reason=f"Warn limit {KICK_THRESHOLD} reached (Manual by {author.name}: {reason})")
                print(f"   Kicked {user.name}."); embed.add_field(name="Kick Status", value="Success", inline=False)
                user_warnings[user_id] = 0 # Reset on successful kick
            except Exception as kick_err: print(f"   Kick Error: {kick_err}"); embed.add_field(name="Kick Status", value=f"Failed ({kick_err})", inline=False)
        else: embed.add_field(name="Kick Status", value=f"Failed ({kick_fail_reason})", inline=False)
    else: embed.title = "⚠️ Manual Warning Issued ⚠️"; embed.add_field(name="Next Step", value=f"达到 {KICK_THRESHOLD} 次警告将被踢出。", inline=False)

    await interaction.followup.send(embed=embed)

# --- Slash Command: Remove Warning ---
@bot.tree.command(name="unwarn", description="Removes the most recent warning from a user.")
@app_commands.describe(user="The user to remove a warning from.", reason="The reason for removing the warning (optional).")
@app_commands.checks.has_permissions(kick_members=True) # Require Kick perms to unwarn
async def slash_unwarn(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    guild = interaction.guild; author = interaction.user
    if not guild: await interaction.response.send_message("...", ephemeral=True); return
    if user.bot: await interaction.response.send_message("Bots don't have warnings.", ephemeral=True); return

    user_id = user.id
    current_warnings = user_warnings.get(user_id, 0)
    if current_warnings <= 0: await interaction.response.send_message(f"{user.mention} has no warnings.", ephemeral=True); return

    user_warnings[user_id] = current_warnings - 1
    new_warning_count = user_warnings[user_id]
    print(f"✅ Unwarn: {author} unwarned {user}. Reason: {reason}. New count: {new_warning_count}/{KICK_THRESHOLD}")

    embed = discord.Embed(title="✅ Warning Removed ✅", color=discord.Color.green())
    embed.set_author(name=f"Action by {author.display_name}", icon_url=author.display_avatar.url)
    embed.add_field(name="User", value=user.mention, inline=False)
    embed.add_field(name="Reason for Removal", value=reason, inline=False)
    embed.add_field(name="New Warning Count", value=f"{new_warning_count} / {KICK_THRESHOLD}", inline=False)
    embed.timestamp = discord.utils.utcnow()
    await interaction.response.send_message(embed=embed) # Visible confirmation


# --- Placeholder for Your Highly Customized Assignment Logic ---
# Add more custom @bot.tree.command() or @bot.listen() functions here


# --- Run the Bot ---
if __name__ == "__main__":
    print("Starting bot...")
    try:
        bot.run(BOT_TOKEN)
    except discord.LoginFailure: print("❌ FATAL ERROR: Login failed. Invalid DISCORD_BOT_TOKEN.")
    except discord.PrivilegedIntentsRequired: print("❌ FATAL ERROR: Privileged Intents required but not enabled in Developer Portal.")
    except Exception as e: print(f"❌ FATAL ERROR during startup: {e}")