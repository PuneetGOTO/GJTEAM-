# slash_role_manager_bot.py (Version with All Features: Role Mgmt, Separators, Clear, Warn/Unwarn, Spam Detect, Auto Role, Announce)

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import get
import os
import datetime # Needed for spam detection timing

# --- Configuration ---
# Load the bot token from an environment variable for security.
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ FATAL ERROR: The DISCORD_BOT_TOKEN environment variable is not set.")
    print("   Please set this variable in your hosting environment (e.g., Railway Variables).")
    exit() # Stop the script if token is missing

COMMAND_PREFIX = "!" # Legacy prefix (mostly unused now)

# --- Intents Configuration ---
intents = discord.Intents.default()
intents.members = True      # REQUIRED for on_member_join, member info, member commands
intents.message_content = True # REQUIRED for on_message spam detection

# --- Bot Initialization ---
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

# --- Spam Detection Configuration & Storage ---
SPAM_COUNT_THRESHOLD = 5
SPAM_TIME_WINDOW_SECONDS = 5
KICK_THRESHOLD = 3
BOT_SPAM_COUNT_THRESHOLD = 8
BOT_SPAM_TIME_WINDOW_SECONDS = 3

# !!! 重要：替换成你的管理员/Mod身份组ID列表 !!!
MOD_ALERT_ROLE_IDS = [
    1362713317222912140, # <--- 替换!
    1362713953960198216  # <--- 替换!
    # 如果有更多，继续添加 , 111222333444555666
]

# In-memory storage (cleared on bot restart)
user_message_timestamps = {}
user_warnings = {}
bot_message_timestamps = {}

# --- Event: Bot Ready ---
@bot.event
async def on_ready():
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
    if isinstance(error, commands.CommandNotFound): return
    elif isinstance(error, commands.MissingPermissions): await ctx.send(f"🚫 PrefixCmd: Missing Perms: {error.missing_permissions}")
    else: print(f"Error with prefix command {ctx.command}: {error}")

# --- Event: App Command Error Handling ---
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    error_message = "🤔 An unknown error occurred."
    ephemeral_response = True # Most errors should be ephemeral

    if isinstance(error, app_commands.CommandNotFound): error_message = "Unknown command."
    elif isinstance(error, app_commands.MissingPermissions): error_message = f"🚫 You need permission: {', '.join(f'`{p}`' for p in error.missing_permissions)}."
    elif isinstance(error, app_commands.BotMissingPermissions): error_message = f"🤖 Bot needs permission: {', '.join(f'`{p}`' for p in error.missing_permissions)}."
    elif isinstance(error, app_commands.CheckFailure): error_message = "🚫 You do not have permission to use this command."
    elif isinstance(error, app_commands.CommandInvokeError):
        original = error.original
        if isinstance(original, discord.Forbidden): error_message = f"🚫 Discord Permissions Error (often role hierarchy)."
        else:
            print(f'Unhandled error in app command {interaction.command.name if interaction.command else "Unknown"}: {original}')
            error_message = "⚙️ An unexpected error occurred."
    else:
        print(f'Unhandled app command error type: {type(error).__name__} - {error}')

    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(error_message, ephemeral=ephemeral_response)
        else: # If we already deferred or responded
            await interaction.followup.send(error_message, ephemeral=ephemeral_response)
    except discord.InteractionResponded: # Catch if we somehow try to respond twice
        try: # Try followup if initial response failed but interaction still valid
            await interaction.followup.send(error_message, ephemeral=ephemeral_response)
        except Exception as followup_error:
             print(f"Error sending followup error message after InteractionResponded: {followup_error}")
    except Exception as e:
        print(f"Error sending error message: {e}")

# Add the error handler to the tree
bot.tree.on_error = on_app_command_error

# --- Event: Member Join - Assign Separator Roles & Welcome ---
@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    print(f'[+] {member.name} ({member.id}) joined {guild.name}')
    # --- Define the EXACT names of your pre-existing separator roles ---
    # !!! IMPORTANT: Replace these with the exact names you created in your server !!!
    separator_role_names_to_assign = [
        "▲─────身分─────",   # <-- 替换!
        "▲─────通知─────",   # <-- 替换!
        "▲─────其他─────"    # <-- 替换!
    ]
    roles_to_add = []; roles_failed = []
    for role_name in separator_role_names_to_assign:
        role = get(guild.roles, name=role_name)
        if role:
            if role < guild.me.top_role or guild.me == guild.owner: roles_to_add.append(role)
            else: roles_failed.append(f"{role_name} (层级)")
        else: roles_failed.append(f"{role_name} (未找到!)")
    if roles_to_add:
        try: await member.add_roles(*roles_to_add, reason="Auto Join Roles")
        except Exception as e: print(f"❌ Err assign roles {member.name}: {e}"); roles_failed.extend([f"{r.name}(Err)" for r in roles_to_add])
    if roles_failed: print(f"‼️ Could not assign for {member.name}: {', '.join(roles_failed)}")
    # --- (Optional) Send Welcome Message ---
    # !!! IMPORTANT: Replace channel IDs below !!!
    welcome_channel_id = 123456789012345678      # <--- 替换! 欢迎频道ID
    rules_channel_id = 123456789012345679        # <--- 替换! 规则频道ID
    roles_info_channel_id = 123456789012345680   # <--- 替换! 身份组介绍频道ID
    verification_channel_id = 123456789012345681 # <--- 替换! 实力认证频道ID
    welcome_channel = guild.get_channel(welcome_channel_id)
    if welcome_channel and isinstance(welcome_channel, discord.TextChannel):
        try:
            embed = discord.Embed(title=f"🎉 欢迎来到 {guild.name}! 🎉", description=f"你好 {member.mention}! 很高兴你能加入 **GJ Team**！\n\n👇 **开始之前:**\n- 阅读服务器规则: <#{rules_channel_id}>\n- 了解身份组信息: <#{roles_info_channel_id}>\n- 认证你的TSB实力: <#{verification_channel_id}>\n\n祝你在 GJ Team 玩得愉快!", color=discord.Color.blue())
            embed.set_thumbnail(url=member.display_avatar.url); embed.set_footer(text=f"你是服务器的第 {guild.member_count} 位成员！")
            await welcome_channel.send(embed=embed); print(f"Sent welcome for {member.name}.")
        except Exception as e: print(f"❌ Error sending welcome: {e}")
    elif welcome_channel_id != 123456789012345678: print(f"⚠️ Welcome channel {welcome_channel_id} not found.")

# --- Event: On Message - Handles User Spam, Bot Spam, and Commands ---
@bot.event
async def on_message(message: discord.Message):
    if not message.guild or message.author.id == bot.user.id: return
    now = datetime.datetime.now(datetime.timezone.utc)

    # --- Bot Spam Detection ---
    if message.author.bot:
        bot_author_id = message.author.id; bot_message_timestamps.setdefault(bot_author_id, [])
        bot_message_timestamps[bot_author_id].append(now)
        time_limit_bot = now - datetime.timedelta(seconds=BOT_SPAM_TIME_WINDOW_SECONDS)
        bot_message_timestamps[bot_author_id] = [ts for ts in bot_message_timestamps[bot_author_id] if ts > time_limit_bot]
        if len(bot_message_timestamps[bot_author_id]) >= BOT_SPAM_COUNT_THRESHOLD:
            print(f"🚨 BOT Spam Detected: {message.author} in #{message.channel.name}")
            bot_message_timestamps[bot_author_id] = []
            mod_mentions = " ".join([f"<@&{role_id}>" for role_id in MOD_ALERT_ROLE_IDS]) # !!! Ensure MOD_ALERT_ROLE_IDS is defined correctly !!!
            alert_msg = f"🚨 **机器人刷屏!** 🚨\nBot: {message.author.mention}\nChannel: {message.channel.mention}\n{mod_mentions} 请管理员关注!"
            try: await message.channel.send(alert_msg); print(f"   Sent bot spam alert.")
            except Exception as alert_err: print(f"   Error sending bot spam alert: {alert_err}")
            deleted_count = 0
            if message.channel.permissions_for(message.guild.me).manage_messages:
                print(f"   Attempting delete...")
                try:
                    async for msg in message.channel.history(limit=BOT_SPAM_COUNT_THRESHOLD * 2, after=time_limit_bot - datetime.timedelta(seconds=2)):
                        if msg.author.id == bot_author_id:
                            try: await msg.delete(); deleted_count += 1
                            except Exception: pass
                    print(f"   Deleted {deleted_count} bot spam messages.")
                    if deleted_count > 0: await message.channel.send(f"🧹 Auto-cleaned {deleted_count} spam messages from {message.author.mention}.", delete_after=15)
                except Exception as del_err: print(f"   Error during bot msg deletion: {del_err}")
            else: print("   Bot lacks Manage Msgs perm for cleanup.")
        return # Stop processing for bots

    # --- User Spam Detection ---
    author_id = message.author.id
    member = message.guild.get_member(author_id)
    if member and message.channel.permissions_for(member).manage_messages: # Ignore mods
        # if message.content.startswith(COMMAND_PREFIX): await bot.process_commands(message) # Allow mods legacy commands
        return
    user_message_timestamps.setdefault(author_id, [])
    user_warnings.setdefault(author_id, 0)
    user_message_timestamps[author_id].append(now)
    time_limit_user = now - datetime.timedelta(seconds=SPAM_TIME_WINDOW_SECONDS)
    user_message_timestamps[author_id] = [ts for ts in user_message_timestamps[author_id] if ts > time_limit_user]
    if len(user_message_timestamps[author_id]) >= SPAM_COUNT_THRESHOLD:
        print(f"🚨 User Spam: {message.author} in #{message.channel.name}")
        user_warnings[author_id] += 1; warning_count = user_warnings[author_id]
        print(f"   User warnings: {warning_count}/{KICK_THRESHOLD}")
        user_message_timestamps[author_id] = [] # Reset user timestamps
        if warning_count >= KICK_THRESHOLD:
            print(f"   Kick threshold reached for {message.author}.")
            if member: # Kick if possible
                bot_member = message.guild.me; kick_reason = f"Auto Kick: Spam warning limit ({KICK_THRESHOLD}) reached."
                if bot_member.guild_permissions.kick_members and (bot_member.top_role > member.top_role or bot_member == message.guild.owner):
                    try:
                        try: await member.send(f"You have been kicked from **{message.guild.name}**.\nReason: **{kick_reason}**")
                        except Exception as dm_err: print(f"   Could not send kick DM to {member.name}: {dm_err}")
                        await member.kick(reason=kick_reason)
                        print(f"   Kicked {member.name}."); await message.channel.send(f"👢 {member.mention} was auto-kicked for excessive spam.")
                        user_warnings[author_id] = 0 # Reset warnings
                    except Exception as kick_err: print(f"   Error during kick: {kick_err}"); await message.channel.send(f"⚙️ Error kicking {member.mention}.")
                else: print(f"   Bot lacks perms/hierarchy to kick {member.name}."); await message.channel.send(f"⚠️ Cannot kick {member.mention} (Bot perms/hierarchy issue).")
            else: print(f"   Could not get Member object for {author_id} to kick.")
        else: # Send warning
            try: await message.channel.send(f"⚠️ {message.author.mention}, please slow down! ({warning_count}/{KICK_THRESHOLD} warnings)", delete_after=15)
            except Exception as warn_err: print(f"   Error sending warning: {warn_err}")

    # Process legacy prefix commands if needed and not spam/ignored
    # if message.content.startswith(COMMAND_PREFIX):
    #    await bot.process_commands(message)

# --- Slash Command: Help ---
@bot.tree.command(name="help", description="Shows information about available commands.")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 GJ Team Bot Help", description="Available slash commands:", color=discord.Color.purple())
    embed.add_field( name="🛠️ Moderation & Management", value=("/createrole `role_name`\n" "/deleterole `role_name`\n" "/giverole `user` `role_name`\n" "/takerole `user` `role_name`\n" "/createseparator `label`\n" "/clear `amount`\n" "/warn `user` `[reason]`\n" "/unwarn `user` `[reason]`"), inline=False )
    embed.add_field(name="📢 Announcements", value=("/announce `channel` `title` `message` `[ping_role]` `[image_url]` `[color]`"), inline=False)
    embed.add_field(name="ℹ️ Other", value="/help", inline=False)
    embed.set_footer(text="<> = Required, [] = Optional. Admin permissions needed.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Slash Command: Create Role ---
@bot.tree.command(name="createrole", description="Creates a new role.")
@app_commands.describe(role_name="The exact name for the new role.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_createrole(interaction: discord.Interaction, role_name: str):
    guild = interaction.guild; await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("Server only.", ephemeral=True); return
    if get(guild.roles, name=role_name): await interaction.followup.send(f"Role **{role_name}** exists!", ephemeral=True); return
    if len(role_name) > 100: await interaction.followup.send("Role name too long.", ephemeral=True); return
    try: new_role = await guild.create_role(name=role_name, reason=f"By {interaction.user}"); await interaction.followup.send(f"✅ Created: {new_role.mention}", ephemeral=False)
    except Exception as e: print(f"Err /createrole: {e}"); await interaction.followup.send(f"⚙️ Error: {e}", ephemeral=True)

# --- Slash Command: Delete Role ---
@bot.tree.command(name="deleterole", description="Deletes a role by its exact name.")
@app_commands.describe(role_name="The exact name of the role to delete.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_deleterole(interaction: discord.Interaction, role_name: str):
    guild = interaction.guild; await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("...", ephemeral=True); return
    role = get(guild.roles, name=role_name)
    if not role: await interaction.followup.send(f"❓ Role **{role_name}** not found.", ephemeral=True); return
    if role == guild.default_role: await interaction.followup.send("🚫 Cannot delete `@everyone`.", ephemeral=True); return
    if role >= guild.me.top_role and guild.me != guild.owner: await interaction.followup.send(f"🚫 Bot Hierarchy Err: {role.mention}.", ephemeral=True); return
    if role.is_managed(): await interaction.followup.send(f"⚠️ Cannot delete managed role {role.mention}.", ephemeral=True); return
    try: name = role.name; await role.delete(reason=f"By {interaction.user}"); await interaction.followup.send(f"✅ Deleted: **{name}**", ephemeral=False)
    except Exception as e: print(f"Err /deleterole: {e}"); await interaction.followup.send(f"⚙️ Error: {e}", ephemeral=True)

# --- Slash Command: Give Role ---
@bot.tree.command(name="giverole", description="Assigns a role to a member.")
@app_commands.describe(user="The user.", role_name="The role name.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_giverole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    guild = interaction.guild; await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("...", ephemeral=True); return
    role = get(guild.roles, name=role_name)
    if not role: await interaction.followup.send(f"❓ Role **{role_name}** not found.", ephemeral=True); return
    if role >= guild.me.top_role and guild.me != guild.owner: await interaction.followup.send(f"🚫 Bot Hierarchy Err: {role.mention}.", ephemeral=True); return
    if isinstance(interaction.user, discord.Member) and role >= interaction.user.top_role and interaction.user != guild.owner: await interaction.followup.send(f"🚫 User Hierarchy Err: {role.mention}.", ephemeral=True); return
    if role in user.roles: await interaction.followup.send(f"ℹ️ {user.mention} already has {role.mention}.", ephemeral=True); return
    try: await user.add_roles(role, reason=f"By {interaction.user}"); await interaction.followup.send(f"✅ Gave {role.mention} to {user.mention}.", ephemeral=False)
    except Exception as e: print(f"Err /giverole: {e}"); await interaction.followup.send(f"⚙️ Error: {e}", ephemeral=True)

# --- Slash Command: Take Role ---
@bot.tree.command(name="takerole", description="Removes a role from a member.")
@app_commands.describe(user="The user.", role_name="The role name.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_takerole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    guild = interaction.guild; await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("...", ephemeral=True); return
    role = get(guild.roles, name=role_name)
    if not role: await interaction.followup.send(f"❓ Role **{role_name}** not found.", ephemeral=True); return
    if role >= guild.me.top_role and guild.me != guild.owner: await interaction.followup.send(f"🚫 Bot Hierarchy Err: {role.mention}.", ephemeral=True); return
    if isinstance(interaction.user, discord.Member) and role >= interaction.user.top_role and interaction.user != guild.owner: await interaction.followup.send(f"🚫 User Hierarchy Err: {role.mention}.", ephemeral=True); return
    if role not in user.roles: await interaction.followup.send(f"ℹ️ {user.mention} doesn't have {role.mention}.", ephemeral=True); return
    if role.is_managed(): await interaction.followup.send(f"⚠️ Cannot remove managed role {role.mention}.", ephemeral=True); return
    try: await user.remove_roles(role, reason=f"By {interaction.user}"); await interaction.followup.send(f"✅ Removed {role.mention} from {user.mention}.", ephemeral=False)
    except Exception as e: print(f"Err /takerole: {e}"); await interaction.followup.send(f"⚙️ Error: {e}", ephemeral=True)

# --- Slash Command: Create Separator Role ---
@bot.tree.command(name="createseparator", description="Creates a visual separator role.")
@app_commands.describe(label="Text inside the separator.")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_createseparator(interaction: discord.Interaction, label: str):
    guild = interaction.guild; await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("...", ephemeral=True); return
    separator_name = f"▲─────{label}─────" # Customize format here
    if len(separator_name) > 100: await interaction.followup.send(f"❌ Label too long.", ephemeral=True); return
    if get(guild.roles, name=separator_name): await interaction.followup.send(f"⚠️ Separator **{separator_name}** exists!", ephemeral=True); return
    try:
        new_role = await guild.create_role(name=separator_name, permissions=discord.Permissions.none(), color=discord.Color.light_grey(), hoist=False, mentionable=False, reason=f"Separator by {interaction.user}")
        await interaction.followup.send(f"✅ Created separator: **{new_role.name}**\n**重要:** 请去 **服务器设置 -> 身份组** 手动拖动位置！",ephemeral=False)
    except Exception as e: print(f"Err /createseparator: {e}"); await interaction.followup.send(f"⚙️ Error: {e}", ephemeral=True)

# --- Slash Command: Clear Messages ---
@bot.tree.command(name="clear", description="Deletes messages in this channel (1-100).")
@app_commands.describe(amount="Number of messages to delete.")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
async def slash_clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel): await interaction.response.send_message("Text channels only.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    try: deleted = await channel.purge(limit=amount); await interaction.followup.send(f"✅ Deleted {len(deleted)} message(s).", ephemeral=True)
    except Exception as e: print(f"Err /clear: {e}"); await interaction.followup.send(f"⚙️ Error: {e}", ephemeral=True)

# --- Slash Command: Manually Warn User ---
@bot.tree.command(name="warn", description="Manually issues a warning to a user.")
@app_commands.describe(user="User to warn.", reason="Reason for warning (optional).")
@app_commands.checks.has_permissions(kick_members=True) # Require Kick perms to warn
async def slash_warn(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    guild = interaction.guild; author = interaction.user
    if not guild: await interaction.response.send_message("...", ephemeral=True); return
    if user.bot: await interaction.response.send_message("Cannot warn bots.", ephemeral=True); return
    if user == author: await interaction.response.send_message("Cannot warn self.", ephemeral=True); return
    if isinstance(author, discord.Member) and user.top_role >= author.top_role and author != guild.owner: await interaction.response.send_message(f"🚫 Cannot warn {user.mention} (Hierarchy).", ephemeral=True); return
    await interaction.response.defer(ephemeral=False)
    user_id = user.id; user_warnings[user_id] = user_warnings.get(user_id, 0) + 1; warning_count = user_warnings[user_id]
    print(f"⚠️ Manual Warn: {author} warned {user}. Reason: {reason}. New count: {warning_count}/{KICK_THRESHOLD}")
    embed = discord.Embed(color=discord.Color.orange())
    embed.set_author(name=f"Warning by {author.display_name}", icon_url=author.display_avatar.url)
    embed.add_field(name="User Warned", value=user.mention, inline=False); embed.add_field(name="Reason", value=reason, inline=False); embed.add_field(name="Current Warnings", value=f"{warning_count}/{KICK_THRESHOLD}", inline=False); embed.timestamp = discord.utils.utcnow()
    if warning_count >= KICK_THRESHOLD:
        embed.title = "🚨 Warn Limit Reached - Kicked 🚨"; embed.color = discord.Color.red(); embed.add_field(name="Action", value="Kicked", inline=False); print(f"   Kick threshold: {user.name}")
        bot_member = guild.me; kick_allowed = False; kick_fail_reason = "Unknown"
        if bot_member.guild_permissions.kick_members and (bot_member.top_role > user.top_role or bot_member == guild.owner): kick_allowed = True
        else: kick_fail_reason = "Bot Perms/Hierarchy"; print(f"   Kick Fail: {kick_fail_reason}")
        if kick_allowed:
            try:
                kick_dm = f"Kicked from **{guild.name}** for reaching {KICK_THRESHOLD} warnings (Last by {author.display_name}: {reason})."
                try: await user.send(kick_dm)
                except Exception as dm_err: print(f"   Kick DM Err: {dm_err}")
                await user.kick(reason=f"Warn limit {KICK_THRESHOLD} (Manual by {author}: {reason})")
                print(f"   Kicked {user.name}."); embed.add_field(name="Kick Status", value="Success", inline=False); user_warnings[user_id] = 0
            except Exception as kick_err: print(f"   Kick Err: {kick_err}"); embed.add_field(name="Kick Status", value=f"Failed ({kick_err})", inline=False)
        else: embed.add_field(name="Kick Status", value=f"Failed ({kick_fail_reason})", inline=False)
    else: embed.title = "⚠️ Manual Warning Issued ⚠️"; embed.add_field(name="Next Step", value=f"Kick at {KICK_THRESHOLD} warnings.", inline=False)
    await interaction.followup.send(embed=embed)

# --- Slash Command: Remove Warning ---
@bot.tree.command(name="unwarn", description="Removes one warning from a user.")
@app_commands.describe(user="User to unwarn.", reason="Reason for removal (optional).")
@app_commands.checks.has_permissions(kick_members=True) # Require Kick perms to unwarn
async def slash_unwarn(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    author = interaction.user
    if user.bot: await interaction.response.send_message("Bots have no warnings.", ephemeral=True); return
    user_id = user.id; current_warnings = user_warnings.get(user_id, 0)
    if current_warnings <= 0: await interaction.response.send_message(f"{user.mention} has no warnings.", ephemeral=True); return
    user_warnings[user_id] = current_warnings - 1; new_warning_count = user_warnings[user_id]
    print(f"✅ Unwarn: {author} unwarned {user}. Reason: {reason}. New count: {new_warning_count}/{KICK_THRESHOLD}")
    embed = discord.Embed(title="✅ Warning Removed ✅", color=discord.Color.green())
    embed.set_author(name=f"By {author.display_name}", icon_url=author.display_avatar.url)
    embed.add_field(name="User", value=user.mention, inline=False); embed.add_field(name="Reason", value=reason, inline=False); embed.add_field(name="New Warning Count", value=f"{new_warning_count}/{KICK_THRESHOLD}", inline=False); embed.timestamp = discord.utils.utcnow()
    await interaction.response.send_message(embed=embed) # Visible confirmation

# --- Slash Command: Announce ---
@bot.tree.command(name="announce", description="Sends a formatted announcement embed.")
@app_commands.describe( channel="Channel to send to.", title="Title.", message="Message content (use '\\n' for new lines).", ping_role="(Optional) Role to mention.", image_url="(Optional) Image URL.", color="(Optional) Hex color (e.g., '#3498db').")
@app_commands.checks.has_permissions(manage_guild=True) # User needs Manage Server perm
@app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True)
async def slash_announce(interaction: discord.Interaction, channel: discord.TextChannel, title: str, message: str, ping_role: discord.Role = None, image_url: str = None, color: str = None):
    guild = interaction.guild; author = interaction.user
    # Defer response in case validation or sending takes time
    await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("...", ephemeral=True); return

    embed_color = discord.Color.blue(); valid_image = None; validation_warning = None
    if color:
        try: clr = color.lstrip('#').lstrip('0x'); embed_color = discord.Color(int(clr, 16))
        except ValueError: validation_warning = "Invalid color format. Used default."
    if image_url and image_url.startswith(('http://', 'https://')): valid_image = image_url
    elif image_url: validation_warning = (validation_warning + "\n" if validation_warning else "") + "Invalid image URL. Sending without image."

    # Send validation warnings if any, before sending the main message
    if validation_warning:
        await interaction.followup.send(f"⚠️ {validation_warning}", ephemeral=True)

    embed = discord.Embed(title=f"**{title}**", description=message.replace('\\n', '\n'), color=embed_color, timestamp=discord.utils.utcnow())
    embed.set_footer(text=f"Announced by {author.display_name} | GJ Team", icon_url=guild.icon.url if guild.icon else None)
    if valid_image: embed.set_image(url=valid_image)
    ping_content = ping_role.mention if ping_role else None
    try:
        bot_perms = channel.permissions_for(guild.me)
        if not bot_perms.send_messages or not bot_perms.embed_links: await interaction.followup.send(f"Bot lacks Send/Embed perms in {channel.mention}.", ephemeral=True); return
        await channel.send(content=ping_content, embed=embed)
        # Send final confirmation only if no validation warnings occurred earlier
        if not validation_warning:
             await interaction.followup.send(f"✅ Announcement sent to {channel.mention}!", ephemeral=True)
        else: # If there was a warning, maybe just log success or don't send another confirmation
             print(f"Announcement sent to {channel.mention} by {author} with prior validation warning.")

    except Exception as e: print(f"Err /announce: {e}"); await interaction.followup.send(f"⚙️ Error sending: {e}", ephemeral=True)

# --- Run the Bot ---
if __name__ == "__main__":
    print("Starting bot...")
    try:
        bot.run(BOT_TOKEN)
    except discord.LoginFailure: print("❌ FATAL ERROR: Login failed. Invalid DISCORD_BOT_TOKEN.")
    except discord.PrivilegedIntentsRequired: print("❌ FATAL ERROR: Privileged Intents required but not enabled in Developer Portal.")
    except Exception as e: print(f"❌ FATAL ERROR during startup: {e}")

# --- End of Complete Code ---