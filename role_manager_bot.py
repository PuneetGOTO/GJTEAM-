# slash_role_manager_bot.py (FINAL COMPLETE CODE v18 - Part 1: Setup & Basic Events - CORRECTED)

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import get
import os
import datetime
import asyncio
from typing import Optional, Union
import requests # Required for DeepSeek API
import json     # Required for DeepSeek API

# --- Configuration ---
# !!! IMPORTANT: Load the bot token from an environment variable !!!
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ FATAL ERROR: The DISCORD_BOT_TOKEN environment variable is not set.")
    print("   Please set this variable in your hosting environment (e.g., Railway Variables).")
    exit()

# !!! IMPORTANT: Load the DeepSeek API Key from an environment variable !!!
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    print("⚠️ WARNING: DEEPSEEK_API_KEY environment variable not set. DeepSeek content moderation will be disabled.")

# !!! IMPORTANT: Confirm DeepSeek API Endpoint and Model Name !!!
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions" # <--- Confirm DeepSeek API URL!
DEEPSEEK_MODEL = "deepseek-chat" # <--- Replace with your desired DeepSeek model!

COMMAND_PREFIX = "!" # Legacy prefix (mostly unused now)

# --- Intents Configuration ---
# Ensure these are enabled in your Discord Developer Portal as well!
intents = discord.Intents.default()
intents.members = True      # REQUIRED for on_member_join, member info, member commands
intents.message_content = True # REQUIRED for on_message spam/bad word detection
intents.voice_states = True # REQUIRED for temporary voice channel feature

# --- Bot Initialization ---
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

# --- Spam Detection & Mod Alert Config ---
SPAM_COUNT_THRESHOLD = 5
SPAM_TIME_WINDOW_SECONDS = 5
KICK_THRESHOLD = 3 # Warnings before kick
BOT_SPAM_COUNT_THRESHOLD = 8
BOT_SPAM_TIME_WINDOW_SECONDS = 3

# !!! 重要：替换成你的管理员/Mod身份组ID列表 !!!
MOD_ALERT_ROLE_IDS = [
    1362713317222912140, # <--- 替换! Example ID
    1362713953960198216  # <--- 替换! Example ID
]

# --- Public Warning Log Channel Config ---
# !!! 重要：替换成你的警告/消除警告公开通知频道ID !!!
PUBLIC_WARN_LOG_CHANNEL_ID = 123456789012345682 # <--- 替换! Example ID

# --- Bad Word Detection Config & Storage (In-Memory) ---
# !!! 【可选】如果你完全信任 DeepSeek API，可以清空或注释掉这个列表 !!!
# !!! 否则，【仔细审查并大幅删减】此列表，避免误判 !!!
BAD_WORDS = [
    "操你妈", "草泥马", "cnm", "日你妈", "rnm", "屌你老母", "屌你媽", "死妈", "死媽", "nmsl", "死全家", "死全家",
    "杂种", "雜種", "畜生", "畜牲", "狗娘养的", "狗娘養的", "贱人", "賤人", "婊子", "bitch", "傻逼", "煞笔", "sb", "脑残", "腦殘",
    "智障", "弱智", "低能", "白痴", "白癡", "废物", "廢物", "垃圾", "lj", "kys", "去死", "自杀", "自殺", "杀你", "殺你",
    "他妈的", "他媽的", "tmd", "妈的", "媽的", "卧槽", "我肏", "我操", "我草", "靠北", "靠杯", "干你娘", "干您娘",
    "fuck", "shit", "cunt", "asshole", "鸡巴", "雞巴", "jb",
]
BAD_WORDS_LOWER = [word.lower() for word in BAD_WORDS]

# 记录用户首次触发提醒 {guild_id: {user_id: {lowercase_word1}}}
user_first_offense_reminders = {}

# --- Temporary Voice Channel Config & Storage (In-Memory) ---
temp_vc_settings = {}
temp_vc_owners = {}
temp_vc_created = set()

# In-memory storage for spam warnings
user_message_timestamps = {}
user_warnings = {}
bot_message_timestamps = {}

# --- Helper Function to Get/Set Settings (Simulated DB) ---
def get_setting(guild_id: int, key: str):
    return temp_vc_settings.get(guild_id, {}).get(key)

def set_setting(guild_id: int, key: str, value):
    if guild_id not in temp_vc_settings: temp_vc_settings[guild_id] = {}
    temp_vc_settings[guild_id][key] = value
    print(f"[Setting Update] Guild {guild_id}: {key}={value}")

# --- Helper Function to Send to Public Log Channel ---
async def send_to_public_log(guild: discord.Guild, embed: discord.Embed, log_type: str = "Generic"):
    log_channel_id_for_public = PUBLIC_WARN_LOG_CHANNEL_ID
    log_channel = guild.get_channel(log_channel_id_for_public)
    if log_channel and isinstance(log_channel, discord.TextChannel):
        bot_perms = log_channel.permissions_for(guild.me)
        if bot_perms.send_messages and bot_perms.embed_links:
            try: await log_channel.send(embed=embed); print(f"   ✅ Sent public log ({log_type})"); return True
            except Exception as log_e: print(f"   ❌ Error sending public log ({log_type}): {log_e}")
        else: print(f"   ❌ Error: Bot lacks Send/Embed permission in public log channel {log_channel_id_for_public}.")
    elif log_channel_id_for_public != 123456789012345682: # Only warn if ID was changed from default example
         print(f"⚠️ Public warn log channel {log_channel_id_for_public} not found in guild {guild.id}.")
    return False

# --- Helper Function: DeepSeek API Content Check ---
async def check_message_with_deepseek(message_content: str) -> Optional[str]:
    """Uses DeepSeek API to check content. Returns violation type or None."""
    if not DEEPSEEK_API_KEY: return None # Skip if no key

    headers = { "Content-Type": "application/json", "Authorization": f"Bearer {DEEPSEEK_API_KEY}" }
    # !!! --- IMPORTANT: Design and Refine Your Prompt --- !!!
    prompt = f"""
    Analyze the Discord message for severe violations: Hate Speech, Harassment/Bullying, Explicit NSFW Content, Severe Threats.
    If a clear violation exists, respond ONLY with the category name (e.g., "Hate Speech").
    If it contains milder issues (spam, profanity) but not severe violations, respond with "Minor Violation".
    If safe, respond ONLY with "Safe".

    Message Content: "{message_content}"
    Analysis Result:"""
    # !!! --- End Prompt Example --- !!!
    data = {"model": DEEPSEEK_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 30, "temperature": 0.2, "stream": False}
    loop = asyncio.get_event_loop()
    try:
        response = await loop.run_in_executor(None, lambda: requests.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=8))
        response.raise_for_status()
        result = response.json()
        api_response_text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        print(f"DEBUG: DeepSeek response for '{message_content[:30]}...': {api_response_text}")
        processed_response = api_response_text.lower()
        if processed_response == "safe" or not processed_response: return None
        elif processed_response == "minor violation": return "Minor Violation"
        else: return api_response_text # Return the specific violation type
    except requests.exceptions.Timeout:
        print(f"❌ Timeout calling DeepSeek API")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Error calling DeepSeek API: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error during DeepSeek check: {e}")
        return None

# --- Event: Bot Ready ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('Syncing application commands...')
    try:
        # Sync globally. Consider syncing to specific guilds for faster updates during testing:
        # synced = await bot.tree.sync(guild=discord.Object(id=YOUR_GUILD_ID))
        synced = await bot.tree.sync() # Global sync
        print(f'Synced {len(synced)} application command(s) globally.')
    except Exception as e:
        print(f'Error syncing commands: {e}')
    print('Bot is ready!')
    print('------')
    await bot.change_presence(activity=discord.Game(name="/help 顯示幫助"))

# --- Event: Command Error Handling (Legacy Prefix Commands) ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return # Ignore commands not found for prefix
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send(f"🚫 PrefixCmd: 缺少權限: {error.missing_permissions}")
    else:
        # Log other prefix command errors
        print(f"Error with prefix command {ctx.command}: {error}")

# --- Event: App Command Error Handling ---
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    error_message = "🤔 發生未知的錯誤。"
    ephemeral_response = True # Default to ephemeral

    if isinstance(error, app_commands.CommandNotFound):
        error_message = "未知的指令。"
    elif isinstance(error, app_commands.MissingPermissions):
        error_message = f"🚫 你缺少必要權限: {', '.join(f'`{p}`' for p in error.missing_permissions)}。"
    elif isinstance(error, app_commands.BotMissingPermissions):
        error_message = f"🤖 我缺少必要權限: {', '.join(f'`{p}`' for p in error.missing_permissions)}。"
    elif isinstance(error, app_commands.CheckFailure):
        # This catches general check failures, including custom checks or has_permissions failing
        error_message = "🚫 你無權使用此指令。"
    elif isinstance(error, app_commands.CommandInvokeError):
        original = error.original
        print(f'Error invoking app command {interaction.command.name if interaction.command else "<UnknownCmd>"} by {interaction.user}: {original}') # Log original error
        if isinstance(original, discord.Forbidden):
            error_message = f"🚫 Discord 權限錯誤 (通常是身份組層級或頻道權限問題)。"
        elif isinstance(original, discord.HTTPException):
             error_message = f"⚙️ Discord API 錯誤 (代碼: {original.status})。請稍後再試。"
        else:
             error_message = "⚙️ 指令執行時發生預期外的錯誤。"
    else:
        # Log any other unexpected app command error types
        print(f'Unhandled app command error type: {type(error).__name__} - {error}')

    try:
        # Check if the interaction has already been responded to
        if not interaction.response.is_done():
            await interaction.response.send_message(error_message, ephemeral=ephemeral_response)
        else:
            # If already responded (e.g., defer), use followup
            await interaction.followup.send(error_message, ephemeral=ephemeral_response)
    except Exception as e:
        # Log error if sending the error message itself fails
        print(f"Error sending error message response: {e}")

# Attach the error handler to the command tree
bot.tree.on_error = on_app_command_error

# --- Event: Member Join ---
@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    print(f'[+] {member.name} ({member.id}) 加入 {guild.name}')

    # !!! IMPORTANT: Replace role names below with your actual separator role names !!!
    separator_role_names_to_assign = ["▲─────身分─────", "▲─────通知─────", "▲─────其他─────"] # <--- 替换!

    roles_to_add = []
    roles_failed = []
    bot_member = guild.me # Get the bot member object once

    for role_name in separator_role_names_to_assign:
        role = get(guild.roles, name=role_name)
        if role:
            # Check if bot has permission and role is lower than bot's top role
            if bot_member.guild_permissions.manage_roles and \
               (role < bot_member.top_role or bot_member == guild.owner):
                roles_to_add.append(role)
            else:
                roles_failed.append(f"{role_name}(层级/权限)")
        else:
            roles_failed.append(f"{role_name}(未找到!)")

    if roles_to_add:
        try:
            await member.add_roles(*roles_to_add, reason="Auto Join Roles")
            print(f"   Assigned roles to {member.name}: {[r.name for r in roles_to_add]}")
        except discord.Forbidden:
             print(f"❌ Err assign roles {member.name}: Bot lacks Permissions.")
             roles_failed.extend([f"{r.name}(权限Err)" for r in roles_to_add])
        except discord.HTTPException as e:
             print(f"❌ Err assign roles {member.name}: HTTP Error {e.status}")
             roles_failed.extend([f"{r.name}(HTTP Err)" for r in roles_to_add])
        except Exception as e:
             print(f"❌ Err assign roles {member.name}: {e}")
             roles_failed.extend([f"{r.name}(Err)" for r in roles_to_add])

    if roles_failed:
        print(f"‼️ Could not assign some roles for {member.name}: {', '.join(roles_failed)}")

    # --- (Optional) Send Welcome Message ---
    # !!! IMPORTANT: Replace channel IDs below with your actual channel IDs !!!
    welcome_channel_id = 123456789012345678      # <--- 替换! Example ID
    rules_channel_id = 123456789012345679        # <--- 替换! Example ID
    roles_info_channel_id = 123456789012345680   # <--- 替换! Example ID
    verification_channel_id = 123456789012345681 # <--- 替换! Example ID

    welcome_channel = guild.get_channel(welcome_channel_id)
    if welcome_channel and isinstance(welcome_channel, discord.TextChannel):
        # Check bot permissions for the welcome channel
        bot_perms = welcome_channel.permissions_for(guild.me)
        if bot_perms.send_messages and bot_perms.embed_links:
            try:
                embed = discord.Embed(
                    title=f"🎉 歡迎來到 {guild.name}! 🎉",
                    description=f"你好 {member.mention}! 很高興見到你。",
                    color=discord.Color.blue(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                if guild.icon:
                    embed.set_thumbnail(url=guild.icon.url)
                if member.display_avatar:
                    embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)

                # Add links if IDs are valid
                rules_mention = f"<#{rules_channel_id}>" if rules_channel_id != 123456789012345679 else "#規則 (請設定頻道ID)"
                roles_mention = f"<#{roles_info_channel_id}>" if roles_info_channel_id != 123456789012345680 else "#身分組介紹 (請設定頻道ID)"
                verify_mention = f"<#{verification_channel_id}>" if verification_channel_id != 123456789012345681 else "#驗證區 (請設定頻道ID)"

                embed.add_field(name="重要連結", value=f"- 請務必閱讀 {rules_mention}\n- 了解伺服器身份組: {roles_mention}\n- 前往 {verify_mention} 取得基礎權限", inline=False)
                embed.set_footer(text=f"你是第 {guild.member_count} 位成員!")

                await welcome_channel.send(embed=embed)
                print(f"   Sent welcome message for {member.name}.")
            except Exception as e:
                print(f"❌ Error sending welcome message: {e}")
        else:
            print(f"❌ Bot lacks Send/Embed permissions in welcome channel {welcome_channel_id}.")
    elif welcome_channel_id != 123456789012345678: # Only warn if ID was changed from default example
        print(f"⚠️ Welcome channel {welcome_channel_id} not found or is not a text channel.")

# --- Event: On Message - Handles Content Check, Spam, Commands ---
@bot.event
async def on_message(message: discord.Message):
    # Ignore DMs, messages from bots (including self), and messages without guild context
    if not message.guild or message.author.bot or message.author.id == bot.user.id:
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    author = message.author
    author_id = author.id
    guild = message.guild
    # Try to get member object, might be None if user leaves quickly
    member = guild.get_member(author_id)

    # --- Ignore Mods/Admins (Based on Manage Messages permission in the specific channel) ---
    # Use member object if available, otherwise fetch permissions (less efficient)
    try:
        perms_target = member if member else author
        # Ensure perms_target is not None before checking permissions
        if perms_target and message.channel.permissions_for(perms_target).manage_messages:
             # print(f"DEBUG: Ignoring message from {author} (has manage_messages perm)")
             return
    except Exception as perm_e:
        # This might happen if the channel context is weird or user leaves instantly
        print(f"DEBUG: Error checking permissions for {author}: {perm_e}")
        # Fallback: continue processing, as we couldn't confirm mod status

    # --- 1. DeepSeek API Content Moderation ---
    violation_type = await check_message_with_deepseek(message.content)
    if violation_type and violation_type != "Minor Violation":
        print(f"🚫 API Violation ('{violation_type}') by {author} ({author_id}) in #{message.channel.name}")
        reason_api = f"自动检测到违规内容 ({violation_type})"

        # Attempt to delete the message first
        try:
            if message.channel.permissions_for(guild.me).manage_messages:
                await message.delete()
                print("   Deleted offending message.")
            else:
                print("   Bot lacks Manage Messages permission to delete.")
        except discord.NotFound:
            print("   Message already deleted.") # Message might have been deleted by another mod/bot
        except discord.Forbidden:
            print("   Error deleting message: Bot lacks permissions.")
        except Exception as del_e:
            print(f"   Error deleting message: {del_e}")

        # Prepare and send log embed
        mod_mentions = " ".join([f"<@&{role_id}>" for role_id in MOD_ALERT_ROLE_IDS])
        log_embed_api = discord.Embed(
            title=f"🚨 自动内容审核提醒 ({violation_type}) 🚨",
            color=discord.Color.dark_red(),
            timestamp=now
        )
        log_embed_api.add_field(name="用户", value=f"{author.mention} ({author_id})", inline=False)
        log_embed_api.add_field(name="频道", value=message.channel.mention, inline=False)
        log_embed_api.add_field(name="内容摘要", value=f"```{message.content[:1000]}```", inline=False) # Limit length
        log_embed_api.add_field(name="消息链接", value=f"[点击跳转]({message.jump_url})", inline=False)
        log_embed_api.add_field(name="建议操作", value=f"{mod_mentions} 请管理员审核并处理！", inline=False)
        log_embed_api.set_footer(text="Moderation via DeepSeek API")

        await send_to_public_log(guild, log_embed_api, log_type=f"API Violation ({violation_type})")

        # --- OPTIONAL: Implement automatic action based on API violation (e.g., warn, mute) ---
        # Example: Issue a warning automatically
        # user_warnings[author_id] = user_warnings.get(author_id, 0) + 1
        # print(f"   Auto-warned user. New count: {user_warnings[author_id]}")
        # Add relevant fields to the log_embed_api or send a separate warn embed
        # ...

        return # Stop further processing after severe API violation

    # --- 2. Bad Word Detection Logic (Optional Fallback/Supplement) ---
    # Only run if API check was 'Safe' or 'Minor Violation' AND the bad word list is not empty
    if not violation_type and BAD_WORDS_LOWER:
        content_lower = message.content.lower()
        triggered_bad_word = None
        for word in BAD_WORDS_LOWER:
            # Use word boundaries (\b) if you want exact word matching,
            # otherwise keep simple 'in' for substring matching.
            # Example exact match: if re.search(r'\b' + re.escape(word) + r'\b', content_lower):
            if word in content_lower:
                triggered_bad_word = word
                break # Found a bad word, stop checking

        if triggered_bad_word:
            print(f"🚫 Bad Word: '{triggered_bad_word}' by {message.author} ({author_id}) in #{message.channel.name}")

            # Initialize guild/user specific first offense tracking if needed
            guild_offenses = user_first_offense_reminders.setdefault(message.guild.id, {})
            user_offenses = guild_offenses.setdefault(author_id, set())

            if triggered_bad_word not in user_offenses: # First time this specific user triggered this specific word (in this session)
                user_offenses.add(triggered_bad_word)
                print(f"   First offense reminder for '{triggered_bad_word}'.")
                try:
                    # !!! IMPORTANT: Replace with your actual rules channel ID !!!
                    rules_ch_id = 123456789012345679 # !!! REPLACE !!!
                    rules_ch_mention = f"<#{rules_ch_id}>" if rules_ch_id != 123456789012345679 else "#規則 (請設定頻道ID)"
                    await message.channel.send(
                        f"{message.author.mention}，请注意言辞，参考 {rules_ch_mention}。本次为初次提醒。",
                        delete_after=20 # Message auto-deletes after 20 seconds
                    )
                except Exception as remind_err:
                    print(f"   Error sending bad word reminder: {remind_err}")
                # Decide if you want to delete the offending message even on first reminder
                # try:
                #     if message.channel.permissions_for(guild.me).manage_messages:
                #         await message.delete()
                #         print("   Deleted offending message (first reminder).")
                # except Exception as del_e: print(f"   Error deleting msg (first reminder): {del_e}")
                return # Stop processing after first reminder
            else: # Repeat offense (already reminded for this word) -> Issue a formal warning
                print(f"   Repeat offense for '{triggered_bad_word}'. Issuing formal warning.")
                reason = f"自动警告：再次使用不当词语 '{triggered_bad_word}'"

                # Increment user warning count
                user_warnings[author_id] = user_warnings.get(author_id, 0) + 1
                warning_count = user_warnings[author_id]
                print(f"   User warnings: {warning_count}/{KICK_THRESHOLD}")

                # Prepare warning embed
                warn_embed = discord.Embed(color=discord.Color.orange(), timestamp=now)
                warn_embed.set_author(name=f"自动警告发出", icon_url=bot.user.display_avatar.url)
                warn_embed.add_field(name="用户", value=f"{message.author.mention} ({author_id})", inline=False)
                warn_embed.add_field(name="原因", value=reason, inline=False)
                warn_embed.add_field(name="当前警告次数", value=f"{warning_count}/{KICK_THRESHOLD}", inline=False)
                warn_embed.set_footer(text="Moderation via Bad Word Filter")

                kick_performed = False # Initialize kick status for this specific action

                # Check if kick threshold is met
                if warning_count >= KICK_THRESHOLD:
                    warn_embed.title = "🚨 警告已达上限 - 自动踢出 🚨"
                    warn_embed.color = discord.Color.red()
                    warn_embed.add_field(name="处 置", value="用户已被踢出", inline=False)
                    print(f"   Kick threshold reached for: {message.author}")

                    # Ensure we have the member object before attempting to kick
                    if member:
                        bot_member = message.guild.me # Get bot member object
                        kick_reason = f"自动踢出：不当言语警告达到 {KICK_THRESHOLD} 次。"

                        # Check bot permissions and role hierarchy
                        can_kick = bot_member.guild_permissions.kick_members and \
                                   (bot_member.top_role > member.top_role or bot_member == message.guild.owner)

                        if can_kick:
                            try:
                                # Attempt to kick the member
                                await member.kick(reason=kick_reason)
                                print(f"   Kicked {member.name}.")
                                kick_performed = True
                                user_warnings[author_id] = 0 # Reset warnings after successful kick
                                warn_embed.add_field(name="踢出状态", value="成功", inline=False)
                            except discord.Forbidden:
                                print(f"   Kick Err (Bad Words): Bot lacks permission or hierarchy despite initial check.")
                                warn_embed.add_field(name="踢出状态", value="失败 (权限/层级不足)", inline=False)
                            except discord.HTTPException as http_e:
                                print(f"   Kick Err (Bad Words): HTTP Error {http_e.status}")
                                warn_embed.add_field(name="踢出状态", value=f"失败 (API错误 {http_e.status})", inline=False)
                            except Exception as kick_err:
                                print(f"   Kick Err (Bad Words): {kick_err}")
                                warn_embed.add_field(name="踢出状态", value=f"失败 ({kick_err})", inline=False)
                        else:
                            print(f"   Bot lacks kick permissions or sufficient role hierarchy for {member.name}.")
                            warn_embed.add_field(name="踢出状态", value="失败 (权限/层级不足)", inline=False)
                    else:
                        # Could not get the Member object (e.g., user left)
                        print(f"   Cannot get Member object for kick (User ID: {author_id}).")
                        warn_embed.add_field(name="踢出状态", value="失败 (无法获取成员)", inline=False)
                else: # warning_count < KICK_THRESHOLD
                    warn_embed.title = "⚠️ 自动警告已发出 (不当言语) ⚠️"

                # Send the warning/kick embed to the public log channel
                await send_to_public_log(message.guild, warn_embed, log_type="Auto Warn (Bad Word)")

                # Optionally delete the offending message that triggered the warn/kick
                try:
                    if message.channel.permissions_for(guild.me).manage_messages:
                         await message.delete()
                         print("   Deleted offending message (warn/kick).")
                except Exception as del_e: print(f"   Error deleting msg (warn/kick): {del_e}")

                # Send a confirmation message in the channel only if user was warned but not kicked
                if not kick_performed and warning_count < KICK_THRESHOLD:
                    try:
                        await message.channel.send(
                            f"{message.author.mention}，你的言论触发自动警告。({warning_count}/{KICK_THRESHOLD})",
                            delete_after=20
                        )
                    except Exception as e:
                        print(f"   Error sending bad word repeat offense notice: {e}")

                return # Stop processing after handling bad word warning/kick

    # --- 3. Bot Spam Detection Logic ---
    # This section is now correctly placed AFTER user checks (API/BadWord)
    # It checks for messages actually sent by other bots.
    # Re-fetch author object as it might be different if code flow changed
    message_author_for_bot_check = message.author
    if message_author_for_bot_check.bot:
        bot_author_id = message_author_for_bot_check.id
        bot_message_timestamps.setdefault(bot_author_id, [])
        bot_message_timestamps[bot_author_id].append(now)

        # Clean up old timestamps
        time_limit_bot = now - datetime.timedelta(seconds=BOT_SPAM_TIME_WINDOW_SECONDS)
        bot_message_timestamps[bot_author_id] = [ts for ts in bot_message_timestamps[bot_author_id] if ts > time_limit_bot]

        # Check if threshold is met
        if len(bot_message_timestamps[bot_author_id]) >= BOT_SPAM_COUNT_THRESHOLD:
            print(f"🚨 BOT Spam Detected: {message_author_for_bot_check.name} ({bot_author_id}) in #{message.channel.name}")
            # Reset timestamps for this bot immediately to prevent rapid re-triggering
            bot_message_timestamps[bot_author_id] = []

            mod_mentions = " ".join([f"<@&{role_id}>" for role_id in MOD_ALERT_ROLE_IDS])
            action_summary = "未尝试自动操作。" # Default message
            spamming_bot_member = message.guild.get_member(bot_author_id) # Try to get member object of the spamming bot
            my_bot_member = message.guild.me

            if spamming_bot_member:
                kick_attempted = False
                kick_successful = False
                roles_removed_msg = ""

                # Attempt 1: Kick (if permissions and hierarchy allow)
                if my_bot_member.guild_permissions.kick_members:
                    if my_bot_member.top_role > spamming_bot_member.top_role:
                        kick_attempted = True
                        try:
                            await spamming_bot_member.kick(reason="Auto Kick: Bot spam detected.")
                            action_summary = "**➡️ Auto: Kicked (Success).**"
                            kick_successful = True
                            print(f"   Kicked bot {spamming_bot_member.name}.")
                        except discord.Forbidden:
                            action_summary = "**➡️ Auto: Kick Failed (权限/层级).**"
                            print(f"   Kick failed (Forbidden/Hierarchy).")
                        except Exception as kick_err:
                            action_summary = f"**➡️ Auto: Kick Failed ({kick_err}).**"
                            print(f"   Kick Error: {kick_err}")
                    else:
                        action_summary = "**➡️ Auto: Cannot Kick (Hierarchy).**"
                        kick_attempted = True # Marked as attempted even if hierarchy prevented it
                        print(f"   Cannot kick {spamming_bot_member.name} (Hierarchy).")
                else:
                    action_summary = "**➡️ Auto: Bot lacks Kick permission.**"
                    kick_attempted = True # Marked as attempted even if perms were missing
                    print("   Bot lacks Kick perms.")

                # Attempt 2: Remove Roles (if kick failed/not attempted and permissions allow)
                if not kick_successful and my_bot_member.guild_permissions.manage_roles:
                    roles_to_try_remove = [
                        r for r in spamming_bot_member.roles
                        if r != message.guild.default_role and r < my_bot_member.top_role
                    ]
                    if roles_to_try_remove:
                        print(f"   Attempting role removal for {spamming_bot_member.name}")
                        try:
                            await spamming_bot_member.remove_roles(*roles_to_try_remove, reason="Auto Remove: Bot spam detected.")
                            roles_removed_msg = "\n**➡️ Auto: Attempted role removal.**"
                            print(f"   Attempted removal of roles: {[r.name for r in roles_to_try_remove]}")
                        except discord.Forbidden:
                             roles_removed_msg = f"\n**➡️ Auto: Role removal failed (权限).**"
                             print(f"   Role removal failed (Forbidden).")
                        except Exception as role_err:
                            roles_removed_msg = f"\n**➡️ Auto: Role removal error: {role_err}**"
                            print(f"   Role removal Error: {role_err}")
                    else:
                        if not kick_attempted: # Only show this if kick wasn't even tried
                             roles_removed_msg = "\n**➡️ Auto: No lower roles found to remove.**"
                        print(f"   No lower roles found to remove from {spamming_bot_member.name}.")
                elif not kick_successful and not my_bot_member.guild_permissions.manage_roles:
                    if not kick_attempted: # Only show this if kick wasn't even tried
                        roles_removed_msg = "\n**➡️ Auto: Bot lacks Manage Roles permission.**"
                    print("   Bot lacks Manage Roles permission.")

                action_summary += roles_removed_msg # Append role removal status if relevant

            else: # Could not find the bot member object
                action_summary = "**➡️ Auto: Cannot find bot member object.**"
                print(f"   Could not find Member object for bot ID {bot_author_id}.")

            # Send alert to the channel
            final_alert_message = (
                f"🚨 **机器人刷屏!** 🚨\n"
                f"Bot: {message_author_for_bot_check.mention}\n"
                f"Channel: {message.channel.mention}\n"
                f"{action_summary}\n" # Include summary of actions taken/failed
                f"{mod_mentions} 请管理员关注!"
            )
            try:
                await message.channel.send(final_alert_message)
                print(f"   Sent bot spam alert.")
            except Exception as alert_err:
                print(f"   Error sending bot spam alert: {alert_err}")

            # Attempt to delete the spamming bot's recent messages
            deleted_count = 0
            if message.channel.permissions_for(message.guild.me).manage_messages:
                print(f"   Attempting to delete recent messages from bot {bot_author_id}...")
                try:
                    # Fetch recent history and delete messages from the spamming bot
                    async for msg in message.channel.history(limit=BOT_SPAM_COUNT_THRESHOLD * 2, # Check a bit more than threshold
                                                             after=now - datetime.timedelta(seconds=BOT_SPAM_TIME_WINDOW_SECONDS + 5)): # Slightly larger window
                        if msg.author.id == bot_author_id:
                            try:
                                await msg.delete()
                                deleted_count += 1
                            except discord.NotFound:
                                pass # Ignore if already deleted
                            except Exception as single_del_err:
                                print(f"      Error deleting single msg {msg.id}: {single_del_err}")
                                await asyncio.sleep(0.1) # Small delay if deletion fails

                    print(f"   Deleted {deleted_count} messages from {message_author_for_bot_check.name}.")
                    # Optionally send a confirmation of cleanup
                    if deleted_count > 0:
                        try:
                            await message.channel.send(f"🧹 Auto-cleaned {deleted_count} spam messages from {message_author_for_bot_check.mention}.", delete_after=15)
                        except Exception as send_err:
                            print(f"   Error sending cleanup confirmation: {send_err}")
                except Exception as bulk_del_err:
                    print(f"   Error during bot message deletion process: {bulk_del_err}")
            else:
                print("   Bot lacks Manage Messages permission to clean up bot spam.")

        return # Stop processing after handling bot spam detection

    # --- 4. User Spam Detection Logic ---
    # Make sure user hasn't been handled by API/BadWord checks already
    # (Handled by `return` statements in those blocks)
    user_message_timestamps.setdefault(author_id, [])
    user_warnings.setdefault(author_id, 0) # Ensure user warning count is initialized

    # Add current timestamp and clean up old ones
    user_message_timestamps[author_id].append(now)
    time_limit_user = now - datetime.timedelta(seconds=SPAM_TIME_WINDOW_SECONDS)
    user_message_timestamps[author_id] = [ts for ts in user_message_timestamps[author_id] if ts > time_limit_user]

    # Check if user spam threshold is met
    if len(user_message_timestamps[author_id]) >= SPAM_COUNT_THRESHOLD:
        print(f"🚨 User Spam Detected: {message.author} ({author_id}) in #{message.channel.name}")

        # Increment warnings and get current count
        user_warnings[author_id] += 1
        warning_count = user_warnings[author_id]
        print(f"   User warnings (spam): {warning_count}/{KICK_THRESHOLD}")

        # Reset timestamps for this user immediately
        user_message_timestamps[author_id] = []

        # Prepare log embed
        log_embed_user = discord.Embed(color=discord.Color.orange(), timestamp=now)
        log_embed_user.set_author(name=f"自动警告 (用户刷屏)", icon_url=bot.user.display_avatar.url)
        log_embed_user.add_field(name="用户", value=f"{message.author.mention} ({author_id})", inline=False)
        log_embed_user.add_field(name="频道", value=message.channel.mention, inline=True)
        log_embed_user.add_field(name="警告次数", value=f"{warning_count}/{KICK_THRESHOLD}", inline=True)
        log_embed_user.add_field(name="消息链接", value=f"[点击跳转]({message.jump_url})", inline=False)
        log_embed_user.set_footer(text="Moderation via Spam Filter")

        kick_performed = False # Reset kick status for this section

        # Check if kick threshold is met
        if warning_count >= KICK_THRESHOLD:
            log_embed_user.title = "🚨 自动踢出 (用户刷屏警告上限) 🚨"
            log_embed_user.color = discord.Color.red()
            log_embed_user.add_field(name="处 置", value="用户已被踢出", inline=False)
            print(f"   Kick threshold reached for user spam: {author}")

            if member: # Ensure member object exists
                bot_member = message.guild.me
                kick_reason = f"自动踢出：刷屏警告达到 {KICK_THRESHOLD} 次。"

                # Check permissions and hierarchy
                can_kick = bot_member.guild_permissions.kick_members and \
                           (bot_member.top_role > member.top_role or bot_member == message.guild.owner)

                if can_kick:
                    try:
                        # Attempt to kick
                        await member.kick(reason=kick_reason)
                        print(f"   Kicked {member.name} for spam.")
                        kick_performed = True
                        user_warnings[author_id] = 0 # Reset warnings on kick
                        log_embed_user.add_field(name="踢出状态", value="成功", inline=False)
                    except discord.Forbidden:
                        print(f"   Kick Err (Spam): Bot lacks permission/hierarchy despite initial check.")
                        log_embed_user.add_field(name="踢出状态", value="失败 (权限/层级不足)", inline=False)
                    except discord.HTTPException as http_e:
                         print(f"   Kick Err (Spam): HTTP Error {http_e.status}")
                         log_embed_user.add_field(name="踢出状态", value=f"失败 (API错误 {http_e.status})", inline=False)
                    except Exception as kick_err:
                        print(f"   Kick Err (Spam): {kick_err}")
                        log_embed_user.add_field(name="踢出状态", value=f"失败 ({kick_err})", inline=False)
                else:
                    print(f"   Bot lacks kick permissions or sufficient hierarchy for {member.name} (spam).")
                    log_embed_user.add_field(name="踢出状态", value="失败 (权限/层级不足)", inline=False)
            else:
                # Cannot get member object
                print(f"   Cannot get Member object for spam kick (User ID: {author_id}).")
                log_embed_user.add_field(name="踢出状态", value="失败 (无法获取成员)", inline=False)
        else: # warning_count < KICK_THRESHOLD
            log_embed_user.title = "⚠️ 自动警告 (用户刷屏) ⚠️"

        # Send the log embed
        await send_to_public_log(guild, log_embed_user, log_type="Auto Warn (User Spam)")

        # Send channel warning only if not kicked
        if not kick_performed:
            try:
                await message.channel.send(
                    f"⚠️ {author.mention}，请减缓发言！({warning_count}/{KICK_THRESHOLD} 警告)",
                    delete_after=15
                )
            except Exception as warn_err:
                print(f"   Error sending user spam warning message: {warn_err}")

        # Optionally delete the spamming user's recent messages (even if only warned)
        deleted_spam_count = 0
        if message.channel.permissions_for(guild.me).manage_messages:
             print(f"   Attempting delete user spam messages from {author_id}")
             try:
                 # Use purge with check for efficiency
                 deleted_messages = await message.channel.purge(
                     limit=SPAM_COUNT_THRESHOLD + 5, # Look slightly beyond threshold
                     check=lambda m: m.author.id == author_id,
                     after=now - datetime.timedelta(seconds=SPAM_TIME_WINDOW_SECONDS + 5) # Check within window
                 )
                 deleted_spam_count = len(deleted_messages)
                 print(f"   Deleted {deleted_spam_count} spam messages from {author.name}.")
                 if deleted_spam_count > 0:
                     try:
                        await message.channel.send(f"🧹 Auto-cleaned {deleted_spam_count} spam messages from {author.mention}.", delete_after=15)
                     except Exception as send_err: print(f"   Error sending user spam cleanup confirm: {send_err}")
             except Exception as del_err:
                 print(f"   Error deleting user spam messages: {del_err}")
        else:
             print("   Bot lacks Manage Messages permission to clean up user spam.")

        return # Stop processing after handling user spam

    # --- 5. Process legacy prefix commands (Optional) ---
    # If you still want to support prefix commands, uncomment the following line:
    # await bot.process_commands(message)


# --- Event: Voice State Update ---
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    guild = member.guild
    master_vc_id = get_setting(guild.id, "master_channel_id")
    category_id = get_setting(guild.id, "category_id")

    # Exit if temp VC system is not configured for this guild
    if not master_vc_id:
        return

    master_channel = guild.get_channel(master_vc_id)
    # Validate master channel exists and is a voice channel
    if not master_channel or not isinstance(master_channel, discord.VoiceChannel):
        print(f"⚠️ Invalid or missing Master VC ID {master_vc_id} for guild {guild.id}")
        # Optionally remove the invalid setting:
        # set_setting(guild.id, "master_channel_id", None)
        return

    category = None
    if category_id:
        category = guild.get_channel(category_id)
        # Validate category exists and is a category channel
        if not category or not isinstance(category, discord.CategoryChannel):
            print(f"⚠️ Invalid or missing Category ID {category_id} for guild {guild.id}. Falling back to Master VC category.")
            category = master_channel.category # Fallback to master channel's category
    else:
        category = master_channel.category # Use master channel's category if none is set

    # --- User Joins the Master VC ---
    if after.channel == master_channel:
        print(f"[TempVC] {member.display_name} ({member.id}) joined master VC '{master_channel.name}'. Attempting creation...")
        try:
            # Permissions for the new channel
            # Owner gets management perms
            owner_overwrites = discord.PermissionOverwrite(
                manage_channels=True,    # Rename, change settings
                manage_permissions=True, # Set permissions for others
                move_members=True,       # Move members in/out
                connect=True,            # Ensure owner can connect
                speak=True               # Ensure owner can speak
            )
            # Everyone else (default role) - adjust as needed
            everyone_overwrites = discord.PermissionOverwrite(
                connect=True, # Allow connection by default? Set to False for private initially
                speak=True
            )
            # Bot needs permissions to manage the channel later (deletion) and move the creator
            bot_overwrites = discord.PermissionOverwrite(
                manage_channels=True,
                manage_permissions=True, # Needed if bot adjusts perms later
                move_members=True,
                connect=True,
                view_channel=True
            )

            temp_channel_name = f"{member.display_name} 的頻道" # Default name

            new_channel = await guild.create_voice_channel(
                name=temp_channel_name,
                category=category, # Assign to the determined category
                overwrites={
                    guild.default_role: everyone_overwrites, # Permissions for @everyone
                    member: owner_overwrites,               # Permissions for the creator (owner)
                    guild.me: bot_overwrites                # Permissions for the bot itself
                },
                reason=f"Temporary VC created by {member.name} ({member.id})"
            )
            print(f"   ✅ Created '{new_channel.name}' ({new_channel.id}) in category '{category.name if category else 'None'}'.")

            # Move the member to their new channel
            try:
                await member.move_to(new_channel)
                print(f"   ✅ Moved {member.display_name} to their channel.")
            except Exception as move_e:
                 print(f"   ⚠️ Failed to move {member.display_name}: {move_e}. Deleting channel.")
                 await new_channel.delete(reason="Failed to move creator")
                 return # Stop if move failed

            # Store ownership and creation status
            temp_vc_owners[new_channel.id] = member.id
            temp_vc_created.add(new_channel.id)

        except discord.Forbidden:
             print(f"   ❌ Error creating temp VC: Bot lacks necessary permissions (Manage Channels, Manage Roles/Permissions, Move Members).")
        except discord.HTTPException as http_e:
             print(f"   ❌ Error creating temp VC: HTTP Error {http_e.status}")
        except Exception as e:
             print(f"   ❌ Error creating temp VC: {e}")

    # --- User Leaves a Temporary VC ---
    # Check if the channel they left *was* one of the created temp VCs
    if before.channel and before.channel.id in temp_vc_created:
        print(f"[TempVC] {member.display_name} left temp VC '{before.channel.name}' ({before.channel.id}). Checking if empty...")
        # Add a small delay to allow Discord API to update member list,
        # but be aware this isn't foolproof against race conditions.
        await asyncio.sleep(1) # Small delay

        # Re-fetch the channel object to ensure it still exists
        channel_to_check = guild.get_channel(before.channel.id)

        if channel_to_check and isinstance(channel_to_check, discord.VoiceChannel):
            # Check if there are any non-bot members left
            if not any(m for m in channel_to_check.members if not m.bot):
                print(f"   Channel '{channel_to_check.name}' is empty. Deleting...")
                try:
                    await channel_to_check.delete(reason="Temporary VC empty")
                    print(f"   ✅ Deleted '{channel_to_check.name}'.")
                except discord.NotFound:
                     print(f"   Channel '{channel_to_check.name}' already deleted.")
                except discord.Forbidden:
                     print(f"   ❌ Error deleting '{channel_to_check.name}': Bot lacks permissions.")
                except Exception as e:
                     print(f"   ❌ Error deleting '{channel_to_check.name}': {e}")
                finally:
                    # Clean up regardless of deletion success/failure if channel object existed
                    if channel_to_check.id in temp_vc_owners: del temp_vc_owners[channel_to_check.id]
                    if channel_to_check.id in temp_vc_created: temp_vc_created.remove(channel_to_check.id)
            else:
                # Channel still has members
                 member_names = [m.display_name for m in channel_to_check.members if not m.bot]
                 print(f"   Channel '{channel_to_check.name}' still has members: {member_names}")
        else:
            # Channel object couldn't be fetched (likely already deleted)
            print(f"   Channel {before.channel.id} no longer exists or is not a VC. Cleaning up stored data.")
            # Clean up data for the potentially deleted channel ID
            if before.channel.id in temp_vc_owners: del temp_vc_owners[before.channel.id]
            if before.channel.id in temp_vc_created: temp_vc_created.remove(before.channel.id)

# --- Slash Command Definitions ---

# Help Command
@bot.tree.command(name="help", description="顯示可用指令的相關資訊。")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 GJ Team Bot Help", description="以下是可用的斜線指令:", color=discord.Color.purple())
    embed.add_field(
        name="🛠️ 身份組 & 基礎管理",
        value=("/createrole `身份組名稱` - 創建新身份組\n"
               "/deleterole `身份組名稱` - 刪除身份組\n"
               "/giverole `用戶` `身份組名稱` - 給予用戶身份組\n"
               "/takerole `用戶` `身份組名稱` - 移除用戶身份組\n"
               "/createseparator `標籤` - 創建分隔線身份組\n"
               "/clear `數量` - 刪除頻道訊息 (1-100)\n"
               "/warn `用戶` `[原因]` - 手動警告用戶\n"
               "/unwarn `用戶` `[原因]` - 移除用戶警告"),
        inline=False
    )
    embed.add_field(
        name="📢 公告",
        value="/announce `頻道` `標題` `訊息` `[提及身份組]` `[圖片URL]` `[顏色]` - 發送嵌入式公告",
        inline=False
    )
    embed.add_field(
        name="⚙️ 進階管理指令群組 (/管理 ...)",
        value=("/管理 公告頻道 `[頻道]` - 設定/查看公告頻道\n"
               "/管理 紀錄頻道 `[頻道]` - 設定/查看記錄頻道\n"
               #"/管理 反應身分 (待實現)\n"
               "/管理 刪訊息 `用戶` `數量` - 刪除特定用戶訊息\n"
               "/管理 頻道名 `新名稱` - 修改目前頻道名稱\n"
               "/管理 禁言 `用戶` `分鐘數` `[原因]` - 禁言用戶 (0=永久)\n"
               "/管理 踢出 `用戶` `[原因]` - 將用戶踢出伺服器\n"
               "/管理 封禁 `用戶ID` `[原因]` - 永久封禁用戶 (用ID)\n"
               "/管理 解封 `用戶ID` `[原因]` - 解除用戶封禁 (用ID)\n"
               "/管理 人數頻道 `[名稱模板]` - 創建/更新成員人數頻道"),
        inline=False
    )
    embed.add_field(
        name="🔊 臨時語音指令群組 (/語音 ...)",
        value=("/語音 設定母頻道 `母頻道` `[分類]` - 設定創建頻道用的母頻道\n"
               "/語音 設定權限 `對象` `[權限設定]` - (房主) 設定頻道權限\n"
               "/語音 轉讓 `新房主` - (房主) 轉讓頻道所有權\n"
               "/語音 房主 - (在頻道內) 如果原房主不在，嘗試獲取所有權"),
        inline=False
    )
    embed.add_field(name="ℹ️ 其他", value="/help - 顯示此幫助訊息", inline=False)
    embed.set_footer(text="提示: <> 代表必填參數, [] 代表可選參數。 大部分管理指令需要相應權限。")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Create Role Command
@bot.tree.command(name="createrole", description="在伺服器中創建一個新的身份組。")
@app_commands.describe(role_name="新身份組的確切名稱。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_createrole(interaction: discord.Interaction, role_name: str):
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True) # Defer for potentially slow operation

    if not guild: # Should not happen with slash commands but good practice
        await interaction.followup.send("此指令僅限伺服器內使用。", ephemeral=True)
        return

    # Check if role already exists (case-insensitive check might be better)
    existing_role = get(guild.roles, name=role_name)
    if existing_role:
        await interaction.followup.send(f"🚫 身份組 **{role_name}** 已存在！({existing_role.mention})", ephemeral=True)
        return

    # Discord role name length limit
    if len(role_name) > 100:
        await interaction.followup.send("🚫 身份組名稱過長 (最多 100 個字元)。", ephemeral=True)
        return
    if not role_name.strip():
         await interaction.followup.send("🚫 身份組名稱不能為空。", ephemeral=True)
         return

    try:
        new_role = await guild.create_role(name=role_name, reason=f"由 {interaction.user} ({interaction.user.id}) 透過 /createrole 創建")
        print(f"Role '{new_role.name}' created by {interaction.user}")
        await interaction.followup.send(f"✅ 已成功創建身份組: {new_role.mention}", ephemeral=False) # Send public confirmation
    except discord.Forbidden:
        print(f"Err /createrole by {interaction.user}: Bot lacks permissions.")
        await interaction.followup.send("⚙️ 創建身份組失敗：機器人權限不足。", ephemeral=True)
    except discord.HTTPException as e:
        print(f"Err /createrole by {interaction.user}: HTTP Error {e.status}")
        await interaction.followup.send(f"⚙️ 創建身份組時發生 Discord API 錯誤 ({e.status})。", ephemeral=True)
    except Exception as e:
        print(f"Err /createrole by {interaction.user}: {e}")
        await interaction.followup.send(f"⚙️ 創建身份組時發生未知錯誤。", ephemeral=True)

# Delete Role Command
@bot.tree.command(name="deleterole", description="依據精確名稱刪除一個現有的身份組。")
@app_commands.describe(role_name="要刪除的身份組的確切名稱。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_deleterole(interaction: discord.Interaction, role_name: str):
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True)

    if not guild:
        await interaction.followup.send("此指令僅限伺服器內使用。", ephemeral=True)
        return

    role_to_delete = get(guild.roles, name=role_name)

    if not role_to_delete:
        await interaction.followup.send(f"❓ 找不到名稱為 **{role_name}** 的身份組。", ephemeral=True)
        return

    if role_to_delete == guild.default_role:
        await interaction.followup.send("🚫 無法刪除 `@everyone` 身份組。", ephemeral=True)
        return

    # Check bot hierarchy
    if role_to_delete >= guild.me.top_role and guild.me != guild.owner:
        await interaction.followup.send(f"🚫 機器人無法刪除層級相同或更高的身份組 ({role_to_delete.mention})。", ephemeral=True)
        return

    # Check if the role is managed by an integration (e.g., bot role)
    if role_to_delete.is_integration() or role_to_delete.is_bot_managed():
         await interaction.followup.send(f"⚠️ 無法刪除由整合或機器人管理的身份組 {role_to_delete.mention}。", ephemeral=True)
         return
    # Check if role is Nitro Booster role
    if role_to_delete.is_premium_subscriber():
         await interaction.followup.send(f"⚠️ 無法刪除 Nitro Booster 身份組 {role_to_delete.mention}。", ephemeral=True)
         return


    try:
        deleted_role_name = role_to_delete.name # Store name before deletion
        await role_to_delete.delete(reason=f"由 {interaction.user} ({interaction.user.id}) 透過 /deleterole 刪除")
        print(f"Role '{deleted_role_name}' deleted by {interaction.user}")
        await interaction.followup.send(f"✅ 已成功刪除身份組: **{deleted_role_name}**", ephemeral=False) # Public confirmation
    except discord.Forbidden:
        print(f"Err /deleterole by {interaction.user}: Bot lacks permissions for role '{role_name}'.")
        await interaction.followup.send(f"⚙️ 刪除身份組 **{role_name}** 失敗：機器人權限不足或層級不夠。", ephemeral=True)
    except discord.HTTPException as e:
        print(f"Err /deleterole by {interaction.user}: HTTP Error {e.status} for role '{role_name}'.")
        await interaction.followup.send(f"⚙️ 刪除身份組時發生 Discord API 錯誤 ({e.status})。", ephemeral=True)
    except Exception as e:
        print(f"Err /deleterole by {interaction.user}: {e} for role '{role_name}'.")
        await interaction.followup.send(f"⚙️ 刪除身份組時發生未知錯誤。", ephemeral=True)

# Give Role Command
@bot.tree.command(name="giverole", description="將一個現有的身份組分配給指定成員。")
@app_commands.describe(user="要給予身份組的用戶。", role_name="要分配的身份組的確切名稱。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_giverole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    guild = interaction.guild
    author = interaction.user # The user executing the command
    await interaction.response.defer(ephemeral=True)

    if not guild:
        await interaction.followup.send("此指令僅限伺服器內使用。", ephemeral=True)
        return

    role_to_give = get(guild.roles, name=role_name)

    if not role_to_give:
        await interaction.followup.send(f"❓ 找不到名稱為 **{role_name}** 的身份組。", ephemeral=True)
        return

    # Check bot hierarchy
    if role_to_give >= guild.me.top_role and guild.me != guild.owner:
        await interaction.followup.send(f"🚫 機器人無法分配層級相同或更高的身份組 ({role_to_give.mention})。", ephemeral=True)
        return

    # Check invoking user hierarchy (if they are not the owner)
    # Ensure author is a Member object before checking top_role
    if isinstance(author, discord.Member) and author != guild.owner:
         if role_to_give >= author.top_role:
              await interaction.followup.send(f"🚫 你的身份組層級不足以分配 {role_to_give.mention}。", ephemeral=True)
              return

    # Check if user already has the role
    if role_to_give in user.roles:
        await interaction.followup.send(f"ℹ️ {user.mention} 已經擁有 {role_to_give.mention} 身份組了。", ephemeral=True)
        return

    # Prevent assigning managed roles
    if role_to_give.is_integration() or role_to_give.is_bot_managed() or role_to_give.is_premium_subscriber():
         await interaction.followup.send(f"⚠️ 無法手動分配由整合、機器人或 Nitro Booster 管理的身份組 {role_to_give.mention}。", ephemeral=True)
         return

    try:
        await user.add_roles(role_to_give, reason=f"由 {author} ({author.id}) 透過 /giverole 分配")
        print(f"Role '{role_to_give.name}' given to {user} by {author}")
        await interaction.followup.send(f"✅ 已成功給予 {user.mention} 身份組 {role_to_give.mention}。", ephemeral=False) # Public confirmation
    except discord.Forbidden:
        print(f"Err /giverole by {author}: Bot lacks permissions for role '{role_name}' or user {user}.")
        await interaction.followup.send(f"⚙️ 分配身份組失敗：機器人權限不足或層級不夠。", ephemeral=True)
    except discord.HTTPException as e:
        print(f"Err /giverole by {author}: HTTP Error {e.status} for role '{role_name}' user {user}.")
        await interaction.followup.send(f"⚙️ 分配身份組時發生 Discord API 錯誤 ({e.status})。", ephemeral=True)
    except Exception as e:
        print(f"Err /giverole by {author}: {e} for role '{role_name}' user {user}.")
        await interaction.followup.send(f"⚙️ 分配身份組時發生未知錯誤。", ephemeral=True)

# Take Role Command
@bot.tree.command(name="takerole", description="從指定成員移除一個特定的身份組。")
@app_commands.describe(user="要移除其身份組的用戶。", role_name="要移除的身份組的確切名稱。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_takerole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    guild = interaction.guild
    author = interaction.user
    await interaction.response.defer(ephemeral=True)

    if not guild:
        await interaction.followup.send("此指令僅限伺服器內使用。", ephemeral=True)
        return

    role_to_take = get(guild.roles, name=role_name)

    if not role_to_take:
        await interaction.followup.send(f"❓ 找不到名稱為 **{role_name}** 的身份組。", ephemeral=True)
        return

    if role_to_take == guild.default_role:
         await interaction.followup.send("🚫 無法移除 `@everyone` 身份組。", ephemeral=True)
         return

    # Check bot hierarchy
    if role_to_take >= guild.me.top_role and guild.me != guild.owner:
        await interaction.followup.send(f"🚫 機器人無法移除層級相同或更高的身份組 ({role_to_take.mention})。", ephemeral=True)
        return

    # Check invoking user hierarchy (if they are not the owner)
    if isinstance(author, discord.Member) and author != guild.owner:
        if role_to_take >= author.top_role:
             await interaction.followup.send(f"🚫 你的身份組層級不足以移除 {role_to_take.mention}。", ephemeral=True)
             return

    # Check if user actually has the role
    if role_to_take not in user.roles:
        await interaction.followup.send(f"ℹ️ {user.mention} 並沒有 {role_to_take.mention} 這個身份組。", ephemeral=True)
        return

    # Prevent removing managed roles
    if role_to_take.is_integration() or role_to_take.is_bot_managed() or role_to_take.is_premium_subscriber():
         await interaction.followup.send(f"⚠️ 無法手動移除由整合、機器人或 Nitro Booster 管理的身份組 {role_to_take.mention}。", ephemeral=True)
         return

    try:
        await user.remove_roles(role_to_take, reason=f"由 {author} ({author.id}) 透過 /takerole 移除")
        print(f"Role '{role_to_take.name}' taken from {user} by {author}")
        await interaction.followup.send(f"✅ 已成功從 {user.mention} 移除身份組 {role_to_take.mention}。", ephemeral=False) # Public confirmation
    except discord.Forbidden:
        print(f"Err /takerole by {author}: Bot lacks permissions for role '{role_name}' or user {user}.")
        await interaction.followup.send(f"⚙️ 移除身份組失敗：機器人權限不足或層級不夠。", ephemeral=True)
    except discord.HTTPException as e:
        print(f"Err /takerole by {author}: HTTP Error {e.status} for role '{role_name}' user {user}.")
        await interaction.followup.send(f"⚙️ 移除身份組時發生 Discord API 錯誤 ({e.status})。", ephemeral=True)
    except Exception as e:
        print(f"Err /takerole by {author}: {e} for role '{role_name}' user {user}.")
        await interaction.followup.send(f"⚙️ 移除身份組時發生未知錯誤。", ephemeral=True)

# Create Separator Role Command
@bot.tree.command(name="createseparator", description="創建一個視覺分隔線身份組。")
@app_commands.describe(label="要在分隔線中顯示的文字 (例如 '身分', '通知')。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_createseparator(interaction: discord.Interaction, label: str):
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True)

    if not guild:
        await interaction.followup.send("此指令僅限伺服器內使用。", ephemeral=True)
        return

    if not label.strip():
         await interaction.followup.send(f"🚫 分隔線標籤不能為空。", ephemeral=True)
         return

    separator_name = f"▲─────{label.strip()}─────" # Ensure no leading/trailing spaces in label

    if len(separator_name) > 100:
        await interaction.followup.send(f"❌ 標籤過長，導致分隔線名稱超過 100 字元。", ephemeral=True)
        return

    # Check if separator role already exists
    if get(guild.roles, name=separator_name):
        await interaction.followup.send(f"⚠️ 分隔線 **{separator_name}** 已經存在!", ephemeral=True)
        return

    try:
        # Create a role with no permissions, specific color, not hoisted, not mentionable
        new_role = await guild.create_role(
            name=separator_name,
            permissions=discord.Permissions.none(), # No permissions
            color=discord.Color.light_grey(),      # Light grey color
            hoist=False,                          # Don't show separately in member list
            mentionable=False,                    # Cannot be mentioned
            reason=f"Separator created by {interaction.user} ({interaction.user.id})"
        )
        print(f"Separator role '{new_role.name}' created by {interaction.user}")
        await interaction.followup.send(
            f"✅ 已成功創建分隔線: **{new_role.name}**\n"
            f"**重要:** 請前往 **伺服器設定 -> 身份組** 手動將此身份組拖動到所需的位置！",
            ephemeral=False # Make visible so user sees the instruction
        )
    except discord.Forbidden:
        print(f"Err /createseparator by {interaction.user}: Bot lacks permissions.")
        await interaction.followup.send("⚙️ 創建分隔線失敗：機器人權限不足。", ephemeral=True)
    except discord.HTTPException as e:
         print(f"Err /createseparator by {interaction.user}: HTTP Error {e.status}")
         await interaction.followup.send(f"⚙️ 創建分隔線時發生 Discord API 錯誤 ({e.status})。", ephemeral=True)
    except Exception as e:
        print(f"Err /createseparator by {interaction.user}: {e}")
        await interaction.followup.send(f"⚙️ 創建分隔線時發生未知錯誤。", ephemeral=True)

# Clear Messages Command
@bot.tree.command(name="clear", description="刪除此頻道中指定數量的訊息 (1-100)。")
@app_commands.describe(amount="要刪除的訊息數量。")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
async def slash_clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    channel = interaction.channel # The channel where the command was used

    # Ensure it's a text channel where messages can be deleted
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("🚫 此指令只能在文字頻道中使用。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True) # Defer response, deletion might take time

    try:
        # Purge the messages
        deleted_messages = await channel.purge(limit=amount)
        print(f"{len(deleted_messages)} messages cleared in #{channel.name} by {interaction.user}")
        await interaction.followup.send(f"✅ 已成功刪除 {len(deleted_messages)} 則訊息。", ephemeral=True) # Ephemeral confirmation
    except discord.Forbidden:
        print(f"Err /clear by {interaction.user} in #{channel.name}: Bot lacks permissions.")
        await interaction.followup.send(f"⚙️ 刪除訊息失敗：機器人權限不足 (需要 `管理訊息` 和 `讀取訊息歷史` 權限)。", ephemeral=True)
    except discord.HTTPException as e:
        print(f"Err /clear by {interaction.user} in #{channel.name}: HTTP Error {e.status}")
        await interaction.followup.send(f"⚙️ 刪除訊息時發生 Discord API 錯誤 ({e.status})。", ephemeral=True)
    except Exception as e:
        print(f"Err /clear by {interaction.user} in #{channel.name}: {e}")
        await interaction.followup.send(f"⚙️ 刪除訊息時發生未知錯誤。", ephemeral=True)


# Manual Warn Command
@bot.tree.command(name="warn", description="手動向用戶發出一次警告。")
@app_commands.describe(user="要警告的用戶。", reason="警告的原因 (可選)。")
@app_commands.checks.has_permissions(kick_members=True) # Use kick_members as a proxy for moderation power
async def slash_warn(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    guild = interaction.guild
    author = interaction.user # User invoking the command

    if not guild:
        await interaction.response.send_message("此指令僅限伺服器內使用。", ephemeral=True)
        return

    if user.bot:
        await interaction.response.send_message("🚫 無法警告機器人。", ephemeral=True)
        return

    if user == author:
        await interaction.response.send_message("🚫 你不能警告自己。", ephemeral=True)
        return

    # Check hierarchy - ensure author is a Member object
    if isinstance(author, discord.Member) and author != guild.owner:
         if user.top_role >= author.top_role:
              await interaction.response.send_message(f"🚫 你無法警告與你同級或更高層級的用戶 ({user.mention})。", ephemeral=True)
              return

    # Defer publicly as the result (warn/kick embed) will be public
    await interaction.response.defer(ephemeral=False)

    user_id = user.id
    # Increment warning count
    user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
    warning_count = user_warnings[user_id]

    print(f"⚠️ Manual Warn: {author} ({author.id}) warned {user} ({user.id}). Reason: {reason}. New count: {warning_count}/{KICK_THRESHOLD}")

    # Prepare the embed
    embed = discord.Embed(color=discord.Color.orange())
    if isinstance(author, discord.Member): # Set author icon if possible
         embed.set_author(name=f"由 {author.display_name} 發出警告", icon_url=author.display_avatar.url)
    else: # Fallback if author somehow isn't a member object
         embed.set_author(name=f"由 {author.name} 發出警告")

    embed.add_field(name="被警告用戶", value=user.mention, inline=False)
    embed.add_field(name="原因", value=reason, inline=False)
    embed.add_field(name="目前警告次數", value=f"{warning_count}/{KICK_THRESHOLD}", inline=False)
    embed.timestamp = discord.utils.utcnow()

    kick_performed = False
    kick_fail_reason = "未尝试"

    # Check if kick threshold is met
    if warning_count >= KICK_THRESHOLD:
        embed.title = "🚨 警告已達上限 - 用戶已被踢出 🚨"
        embed.color = discord.Color.red()
        embed.add_field(name="處置", value="踢出伺服器", inline=False)
        print(f"   Kick threshold reached for {user.name} due to manual warn.")

        bot_member = guild.me
        kick_allowed = False

        # Check bot permissions and hierarchy
        if bot_member.guild_permissions.kick_members:
            if bot_member.top_role > user.top_role or bot_member == guild.owner:
                kick_allowed = True
            else:
                kick_fail_reason = "機器人層級不足"
                print(f"   Manual Warn Kick Fail: Bot hierarchy too low for {user.name}.")
        else:
            kick_fail_reason = "機器人缺少踢出權限"
            print(f"   Manual Warn Kick Fail: Bot lacks Kick Members permission.")

        if kick_allowed:
            try:
                kick_dm_message = f"由於累積達到 **{KICK_THRESHOLD}** 次警告，你已被踢出伺服器 **{guild.name}**。\n最後一次警告由 {author.display_name} 發出，原因：{reason}"
                try:
                    await user.send(kick_dm_message) # Attempt to DM the user before kicking
                    print(f"   Sent kick notification DM to {user.name}.")
                except discord.Forbidden:
                    print(f"   Could not send kick DM to {user.name} (DMs disabled or blocked).")
                except Exception as dm_err:
                    print(f"   Error sending kick DM to {user.name}: {dm_err}")

                # Perform the kick
                await user.kick(reason=f"警告達到 {KICK_THRESHOLD} 次 (最後手動警告 by {author.name}: {reason})")
                print(f"   Kicked {user.name}.")
                embed.add_field(name="踢出狀態", value="成功", inline=False)
                user_warnings[user_id] = 0 # Reset warnings after successful kick
                kick_performed = True
            except discord.Forbidden:
                 kick_fail_reason = "踢出時權限錯誤 (可能層級突變?)"
                 print(f"   Manual Warn Kick Err: Forbidden during kick operation for {user.name}.")
                 embed.add_field(name="踢出狀態", value=f"失敗 ({kick_fail_reason})", inline=False)
            except discord.HTTPException as http_e:
                  kick_fail_reason = f"Discord API 錯誤 ({http_e.status})"
                  print(f"   Manual Warn Kick Err: HTTP Error {http_e.status} for {user.name}.")
                  embed.add_field(name="踢出狀態", value=f"失敗 ({kick_fail_reason})", inline=False)
            except Exception as kick_err:
                kick_fail_reason = f"未知錯誤: {kick_err}"
                print(f"   Manual Warn Kick Err: {kick_err}")
                embed.add_field(name="踢出狀態", value=f"失敗 ({kick_fail_reason})", inline=False)
        else:
            # Kick was not allowed based on initial permission/hierarchy check
             embed.add_field(name="踢出狀態", value=f"失敗 ({kick_fail_reason})", inline=False)
    else: # warning_count < KICK_THRESHOLD
        embed.title = "⚠️ 手動警告已發出 ⚠️"
        embed.add_field(name="後續", value=f"達到 {KICK_THRESHOLD} 次警告將可能被自動踢出。", inline=False)

    # Send the result embed to the interaction channel (publicly, due to defer(ephemeral=False))
    await interaction.followup.send(embed=embed)

    # Also send to the dedicated public log channel
    await send_to_public_log(guild, embed, log_type="Manual Warn")

# Unwarn Command
@bot.tree.command(name="unwarn", description="移除用戶的一次警告。")
@app_commands.describe(user="要移除其警告的用戶。", reason="移除警告的原因 (可選)。")
@app_commands.checks.has_permissions(kick_members=True) # Moderator permission proxy
async def slash_unwarn(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    guild = interaction.guild
    author = interaction.user
    await interaction.response.defer(ephemeral=True) # Response to moderator is ephemeral

    if not guild:
        await interaction.followup.send("此指令僅限伺服器內使用。", ephemeral=True)
        return

    if user.bot:
        await interaction.followup.send("🚫 機器人沒有警告記錄。", ephemeral=True)
        return

    user_id = user.id
    current_warnings = user_warnings.get(user_id, 0)

    if current_warnings <= 0:
        await interaction.followup.send(f"ℹ️ {user.mention} 目前沒有任何警告可以移除。", ephemeral=True)
        return

    # Decrement warning count, ensuring it doesn't go below zero
    user_warnings[user_id] = max(0, current_warnings - 1)
    new_warning_count = user_warnings[user_id]

    print(f"✅ Unwarn: {author} ({author.id}) unwarned {user} ({user.id}). Reason: {reason}. New count: {new_warning_count}/{KICK_THRESHOLD}")

    # Prepare embed for public log
    embed = discord.Embed(title="✅ 警告已移除 ✅", color=discord.Color.green())
    if isinstance(author, discord.Member):
        embed.set_author(name=f"由 {author.display_name} 操作", icon_url=author.display_avatar.url)
    else:
         embed.set_author(name=f"由 {author.name} 操作")
    embed.add_field(name="用戶", value=user.mention, inline=False)
    embed.add_field(name="移除原因", value=reason, inline=False)
    embed.add_field(name="新的警告次數", value=f"{new_warning_count}/{KICK_THRESHOLD}", inline=False)
    embed.timestamp = discord.utils.utcnow()

    # Send to public log channel first
    log_sent = await send_to_public_log(guild, embed, log_type="Manual Unwarn")

    # Confirm operation to the moderator
    log_status = "(已記錄)" if log_sent else "(記錄失敗)"
    await interaction.followup.send(f"✅ 已移除 {user.mention} 的一次警告。新警告數: {new_warning_count} {log_status}", ephemeral=True)

# Announce Command
@bot.tree.command(name="announce", description="發送帶有精美嵌入格式的公告。")
@app_commands.describe(
    channel="要發送公告的頻道。",
    title="公告的標題。",
    message="公告的主要內容 (使用 '\\n' 換行)。",
    ping_role="(可選) 要在公告前提及的身份組。",
    image_url="(可選) 要在公告中包含的圖片 URL (必須是有效 http/https 連結)。",
    color="(可選) 嵌入框的十六進制顏色碼 (例如 '#3498db' 或 '3498db')。"
)
@app_commands.checks.has_permissions(manage_guild=True) # Generally requires high permission level
@app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True)
async def slash_announce(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    title: str,
    message: str,
    ping_role: Optional[discord.Role] = None,
    image_url: Optional[str] = None,
    color: Optional[str] = None):

    guild = interaction.guild
    author = interaction.user
    await interaction.response.defer(ephemeral=True) # Ephemeral confirmation to announcer

    if not guild:
        await interaction.followup.send("此指令僅限伺服器內使用。", ephemeral=True)
        return

    # Validate Bot Permissions in Target Channel
    bot_perms = channel.permissions_for(guild.me)
    if not bot_perms.send_messages or not bot_perms.embed_links:
        await interaction.followup.send(f"🚫 機器人缺少在 {channel.mention} 發送訊息或嵌入連結的權限。", ephemeral=True)
        return

    # Validate Color
    embed_color = discord.Color.blue() # Default color
    color_warning = None
    if color:
        try:
            clean_color = color.lstrip('#').lstrip('0x')
            embed_color = discord.Color(int(clean_color, 16))
        except ValueError:
            color_warning = f"⚠️ 無效的顏色代碼 '{color}'。已使用預設藍色。"
            print(f"Announce Warning: Invalid color code '{color}' provided by {author}.")

    # Validate Image URL (basic check)
    valid_image_url = None
    image_warning = None
    if image_url:
        # Simple check for common image extensions and http start
        if image_url.startswith(('http://', 'https://')) and image_url.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            valid_image_url = image_url
        else:
            image_warning = f"⚠️ 無效或不支持的圖片 URL。圖片已被忽略。"
            print(f"Announce Warning: Invalid image URL '{image_url}' provided by {author}.")

    # Combine warnings if both occurred
    validation_warnings = "\n".join(filter(None, [color_warning, image_warning]))
    if validation_warnings:
        # Send warnings to the user who invoked the command
        await interaction.followup.send(validation_warnings, ephemeral=True)
        # Still proceed with the announcement, just without the failed parts

    # Prepare Embed
    # Use replace('\\n', '\n') to allow users to type \n for newlines
    embed = discord.Embed(
        title=f"**{title}**",
        description=message.replace('\\n', '\n'),
        color=embed_color,
        timestamp=discord.utils.utcnow()
    )

    # Set footer with guild icon if available
    footer_text = f"由 {author.display_name} 發布"
    if guild.icon:
        embed.set_footer(text=footer_text, icon_url=guild.icon.url)
    else:
        embed.set_footer(text=footer_text)

    # Set image if valid URL was provided
    if valid_image_url:
        embed.set_image(url=valid_image_url)

    # Prepare ping content
    ping_content = None
    if ping_role:
         # Check if bot can mention the role (or if it's @everyone/@here which are always mentionable)
        if ping_role.is_mentionable or ping_role == guild.default_role or ping_role == guild.roles.here: # Check if role is @everyone or @here explicitly too
            ping_content = ping_role.mention
        else:
            # Role exists but is not mentionable, warn the user
            await interaction.followup.send(f"⚠️ 身份組 {ping_role.name} 不可提及，公告已發送但未提及該身份組。", ephemeral=True)
            print(f"Announce Warning: Role {ping_role.name} is not mentionable, ping skipped by {author}.")


    # Send the announcement
    try:
        sent_message = await channel.send(content=ping_content, embed=embed)
        print(f"Announcement sent to #{channel.name} by {author}. Title: '{title}'")
        # Send final success confirmation (ephemeral) only if no warnings occurred
        if not validation_warnings:
             await interaction.followup.send(f"✅ 公告已成功發送到 {channel.mention}! ([點此跳轉]({sent_message.jump_url}))", ephemeral=True)
        # If warnings occurred, they were already sent via followup earlier.

    except discord.Forbidden:
        # This might happen if permissions change between the initial check and sending
        print(f"Err /announce by {author}: Bot lost send/embed permissions in #{channel.name}.")
        await interaction.followup.send(f"⚙️ 發送公告至 {channel.mention} 失敗：機器人權限不足。", ephemeral=True)
    except discord.HTTPException as e:
        print(f"Err /announce by {author}: HTTP Error {e.status} in #{channel.name}.")
        await interaction.followup.send(f"⚙️ 發送公告時發生 Discord API 錯誤 ({e.status})。", ephemeral=True)
    except Exception as e:
        print(f"Err /announce by {author}: {e} in #{channel.name}.")
        await interaction.followup.send(f"⚙️ 發送公告時發生未知錯誤。", ephemeral=True)


# --- Management Command Group Definitions ---
manage_group = app_commands.Group(name="管理", description="伺服器管理相關指令 (限管理員)")

@manage_group.command(name="公告頻道", description="設定或查看發布公告的頻道 (需管理員)")
@app_commands.describe(channel="選擇新的公告頻道 (留空則查看當前設定)")
@app_commands.checks.has_permissions(administrator=True) # Requires Administrator
async def manage_announce_channel(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    guild_id = interaction.guild_id
    await interaction.response.defer(ephemeral=True)

    if channel:
        # Validate bot can send in the new channel
        bot_perms = channel.permissions_for(interaction.guild.me)
        if not bot_perms.send_messages or not bot_perms.embed_links:
             await interaction.followup.send(f"⚠️ 無法將公告頻道設為 {channel.mention}，因為機器人缺少在該頻道的 `發送訊息` 或 `嵌入連結` 權限。", ephemeral=True)
             return

        set_setting(guild_id, "announce_channel_id", channel.id)
        await interaction.followup.send(f"✅ 公告頻道已成功設為 {channel.mention}", ephemeral=True)
        print(f"[Settings] Announce channel for Guild {guild_id} set to {channel.id} by {interaction.user}")
    else:
        channel_id = get_setting(guild_id, "announce_channel_id")
        current_channel = interaction.guild.get_channel(channel_id) if channel_id else None
        if current_channel:
            await interaction.followup.send(f"ℹ️ 目前的公告頻道是: {current_channel.mention}", ephemeral=True)
        else:
            await interaction.followup.send("ℹ️ 目前尚未設定公告頻道。", ephemeral=True)

@manage_group.command(name="紀錄頻道", description="設定或查看機器人操作紀錄頻道 (需管理員)")
@app_commands.describe(channel="選擇新的紀錄頻道 (留空則查看當前設定)")
@app_commands.checks.has_permissions(administrator=True) # Requires Administrator
async def manage_log_channel(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
     guild_id = interaction.guild_id
     await interaction.response.defer(ephemeral=True)

     if channel:
         # Validate bot can send messages in the new channel
         bot_perms = channel.permissions_for(interaction.guild.me)
         if not bot_perms.send_messages or not bot_perms.embed_links:
              await interaction.followup.send(f"⚠️ 無法將紀錄頻道設為 {channel.mention}，因為機器人缺少在該頻道的 `發送訊息` 或 `嵌入連結` 權限。", ephemeral=True)
              return

         # Set the new channel ID
         set_setting(guild_id, "log_channel_id", channel.id)
         print(f"[Settings] Log channel for Guild {guild_id} set to {channel.id} by {interaction.user}")

         # Try sending a confirmation message to the new log channel
         try:
             await channel.send(f"✅ 此頻道已被設為 {bot.user.mention} 的操作紀錄頻道。")
             await interaction.followup.send(f"✅ 紀錄頻道已成功設為 {channel.mention}，並已發送測試訊息。", ephemeral=True)
         except discord.Forbidden:
             # Setting was saved, but bot couldn't send test message
             await interaction.followup.send(f"⚠️ 紀錄頻道已設為 {channel.mention}，但機器人無法在該頻道發送確認訊息！請檢查權限。", ephemeral=True)
         except Exception as e:
             # Setting was saved, but other error occurred during test message
             await interaction.followup.send(f"✅ 紀錄頻道已設為 {channel.mention}，但在發送測試訊息時發生錯誤: {e}", ephemeral=True)
     else:
         # Display the current setting
         channel_id = get_setting(guild_id, "log_channel_id")
         current_channel = interaction.guild.get_channel(channel_id) if channel_id else None
         if current_channel:
             await interaction.followup.send(f"ℹ️ 目前的紀錄頻道是: {current_channel.mention}", ephemeral=True)
         else:
             await interaction.followup.send("ℹ️ 目前尚未設定紀錄頻道。", ephemeral=True)

# Reaction Roles (Placeholder)
@manage_group.command(name="反應身分", description="設定反應身份組 (此功能目前建議使用其他Bot或按鈕實現)")
@app_commands.checks.has_permissions(manage_roles=True) # Keep permission check for consistency
async def manage_reaction_roles(interaction: discord.Interaction):
    await interaction.response.send_message(
        "🚧 **反應身份組功能說明:**\n"
        "傳統的訊息反應式身份組系統較為複雜且容易出錯。\n"
        "**強烈建議**改用 Discord 內建的 **[伺服器設定 -> 身份組 -> 瀏覽身份組]** 功能，\n"
        "或者使用支援 **按鈕 (Buttons)** 的身份組 Bot (例如 Carl-bot, Sapphire 等) 來建立更現代、更可靠的身份組領取方式。\n"
        "本 Bot 目前不計劃實作傳統反應式身份組。",
        ephemeral=True
    )

# Delete User Messages
@manage_group.command(name="刪訊息", description="刪除特定用戶在此頻道的最近訊息 (需管理訊息)")
@app_commands.describe(user="要刪除其訊息的用戶", amount="要檢查並刪除的最近訊息數量 (上限100)")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
async def manage_delete_user_messages(interaction: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 1, 100]):
    await interaction.response.defer(ephemeral=True)
    channel = interaction.channel

    if not isinstance(channel, discord.TextChannel):
        await interaction.followup.send("🚫 此指令只能在文字頻道中使用。", ephemeral=True)
        return

    if user == interaction.guild.me:
         await interaction.followup.send("🚫 無法刪除機器人自己的訊息。", ephemeral=True)
         return

    deleted_count = 0
    try:
        # Use purge with the check parameter for efficiency
        deleted_messages = await channel.purge(limit=amount, check=lambda m: m.author == user)
        deleted_count = len(deleted_messages)
        print(f"{deleted_count} messages from {user} deleted in #{channel.name} by {interaction.user}")
        await interaction.followup.send(f"✅ 成功在最近檢查的 {amount} 則訊息中，刪除了 {user.mention} 的 {deleted_count} 則訊息。", ephemeral=True)
    except discord.Forbidden:
        print(f"Err /管理 刪訊息 by {interaction.user}: Bot lacks permissions in #{channel.name}.")
        await interaction.followup.send(f"⚙️ 刪除訊息失敗：機器人權限不足。", ephemeral=True)
    except discord.HTTPException as e:
         print(f"Err /管理 刪訊息 by {interaction.user}: HTTP Error {e.status} in #{channel.name}.")
         await interaction.followup.send(f"⚙️ 刪除訊息時發生 Discord API 錯誤 ({e.status})。", ephemeral=True)
    except Exception as e:
        print(f"Err /管理 刪訊息 by {interaction.user}: {e} in #{channel.name}.")
        await interaction.followup.send(f"⚙️ 刪除訊息時發生未知錯誤: {e}", ephemeral=True)

# Rename Channel
@manage_group.command(name="頻道名", description="修改當前文字/語音頻道的名稱 (需管理頻道)")
@app_commands.describe(new_name="頻道的新名稱")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.checks.bot_has_permissions(manage_channels=True)
async def manage_channel_name(interaction: discord.Interaction, new_name: str):
    channel = interaction.channel # Works for TextChannel, VoiceChannel, StageChannel, ForumChannel etc.
    await interaction.response.defer(ephemeral=True) # Defer privately first

    # Check if the channel type supports renaming (most do)
    if not hasattr(channel, 'edit'):
         await interaction.followup.send("🚫 此頻道類型不支持重新命名。", ephemeral=True)
         return

    # Basic validation
    if not new_name.strip():
         await interaction.followup.send("🚫 頻道名稱不能為空。", ephemeral=True)
         return
    if len(new_name) > 100:
          await interaction.followup.send("🚫 頻道名稱過長 (最多 100 字元)。", ephemeral=True)
          return

    old_name = channel.name
    try:
        await channel.edit(name=new_name, reason=f"由 {interaction.user} ({interaction.user.id}) 透過 /管理 頻道名 修改")
        print(f"Channel #{old_name} renamed to #{new_name} in {interaction.guild.name} by {interaction.user}")
        # Send public confirmation
        await interaction.followup.send(f"✅ 頻道名稱已從 `{old_name}` 修改為 `{new_name}`。", ephemeral=False)
    except discord.Forbidden:
        print(f"Err /管理 頻道名 by {interaction.user}: Bot lacks permissions for channel {channel.id}.")
        await interaction.followup.send("⚙️ 修改頻道名稱失敗：機器人權限不足。", ephemeral=True)
    except discord.HTTPException as e:
         print(f"Err /管理 頻道名 by {interaction.user}: HTTP Error {e.status} for channel {channel.id}.")
         await interaction.followup.send(f"⚙️ 修改頻道名稱時發生 Discord API 錯誤 ({e.status})。", ephemeral=True)
    except Exception as e:
        print(f"Err /管理 頻道名 by {interaction.user}: {e} for channel {channel.id}.")
        await interaction.followup.send(f"⚙️ 修改頻道名稱時發生未知錯誤: {e}", ephemeral=True)

# Mute (Timeout) Command
@manage_group.command(name="禁言", description="暫時禁止成員在伺服器發言/加入語音 (需禁言成員權限)")
@app_commands.describe(
    user="要禁言的用戶。",
    duration_minutes="禁言的持續時間 (分鐘)。輸入 0 代表最長期限 (28天)。",
    reason="禁言的原因 (可選)。"
)
@app_commands.checks.has_permissions(moderate_members=True) # Timeout permission
@app_commands.checks.bot_has_permissions(moderate_members=True)
async def manage_mute(interaction: discord.Interaction, user: discord.Member, duration_minutes: int, reason: str = "未指定原因"):
    await interaction.response.defer(ephemeral=True) # Ephemeral confirmation to moderator
    guild = interaction.guild
    author = interaction.user

    if user == author:
        await interaction.followup.send("🚫 你不能禁言自己。", ephemeral=True)
        return
    if user == guild.owner:
         await interaction.followup.send("🚫 無法禁言伺服器擁有者。", ephemeral=True)
         return
    if user == guild.me:
         await interaction.followup.send("🚫 你不能禁言我！", ephemeral=True)
         return

    # Check hierarchy (both user and bot)
    if isinstance(author, discord.Member) and author != guild.owner:
        if user.top_role >= author.top_role:
            await interaction.followup.send(f"🚫 你無法禁言與你同級或更高層級的用戶 ({user.mention})。", ephemeral=True)
            return
    if user.top_role >= guild.me.top_role and guild.me != guild.owner:
         await interaction.followup.send(f"🚫 機器人無法禁言層級相同或更高的用戶 ({user.mention})。", ephemeral=True)
         return

    # Validate duration
    if duration_minutes < 0:
        await interaction.followup.send("🚫 禁言時間不能是負數。", ephemeral=True)
        return

    # Calculate timeout duration
    max_duration = datetime.timedelta(days=28) # Discord's maximum timeout duration
    timeout_duration: Optional[datetime.timedelta] = None
    duration_text = ""

    if duration_minutes == 0:
        # Use maximum duration
        timeout_duration = max_duration
        duration_text = f"最大 ({max_duration.days}天)"
    else:
        try:
             timeout_duration = datetime.timedelta(minutes=duration_minutes)
             if timeout_duration > max_duration:
                 timeout_duration = max_duration
                 duration_text = f"{duration_minutes} 分鐘 (已限制為最大 {max_duration.days}天)"
                 print(f"Timeout requested for {duration_minutes} min, capped at 28 days.")
             else:
                 duration_text = f"{duration_minutes} 分鐘"
        except OverflowError:
             await interaction.followup.send(f"🚫 禁言時間過長，請輸入較小的值或 0。", ephemeral=True)
             return


    # Check if user is already timed out
    if user.is_timed_out():
         await interaction.followup.send(f"ℹ️ 用戶 {user.mention} 目前已被禁言。如需修改，請先解除禁言。", ephemeral=True)
         # Alternatively, you could allow overriding the timeout here, but it's often clearer to require manual removal first.
         return


    try:
        # Apply the timeout
        await user.timeout(timeout_duration, reason=f"由 {author.name} ({author.id}) 禁言: {reason}")
        print(f"{user} timed out for {duration_text} by {author}. Reason: {reason}")

        # Send confirmation (publicly, as timeout is a visible action)
        confirmation_message = f"✅ {user.mention} 已被成功禁言 **{duration_text}**。\n原因: {reason}"
        # Send to interaction channel first
        await interaction.followup.send(confirmation_message, ephemeral=False)

        # Optionally, send a log embed to the log channel
        log_embed = discord.Embed(title="⏳ 用戶已被禁言 ⏳", color=discord.Color.greyple(), timestamp=discord.utils.utcnow())
        log_embed.add_field(name="用戶", value=f"{user.mention} ({user.id})", inline=False)
        log_embed.add_field(name="操作者", value=f"{author.mention} ({author.id})", inline=False)
        log_embed.add_field(name="持續時間", value=duration_text, inline=True)
        log_embed.add_field(name="原因", value=reason, inline=True)
        if isinstance(author, discord.Member): log_embed.set_thumbnail(url=author.display_avatar.url)
        await send_to_public_log(guild, log_embed, log_type="Timeout")

    except discord.Forbidden:
        print(f"Err /管理 禁言 by {author}: Bot lacks permissions or hierarchy for {user}.")
        await interaction.followup.send(f"⚙️ 禁言操作失敗：機器人權限不足或層級不夠。", ephemeral=True)
    except discord.HTTPException as e:
         print(f"Err /管理 禁言 by {author}: HTTP Error {e.status} for {user}.")
         await interaction.followup.send(f"⚙️ 禁言操作時發生 Discord API 錯誤 ({e.status})。", ephemeral=True)
    except Exception as e:
        print(f"Err /管理 禁言 by {author}: {e} for {user}.")
        await interaction.followup.send(f"⚙️ 禁言操作失敗: {e}", ephemeral=True)

# Kick Command
@manage_group.command(name="踢出", description="將成員踢出伺服器 (需踢出成員權限)")
@app_commands.describe(user="要踢出的用戶", reason="踢出的原因 (可選)。")
@app_commands.checks.has_permissions(kick_members=True)
@app_commands.checks.bot_has_permissions(kick_members=True)
async def manage_kick(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    await interaction.response.defer(ephemeral=True) # Ephemeral confirmation to moderator
    guild = interaction.guild
    author = interaction.user

    # --- Pre-kick Checks ---
    if user == author:
        await interaction.followup.send("🚫 你不能踢出自己。", ephemeral=True)
        return
    if user == guild.owner:
        await interaction.followup.send("🚫 無法踢出伺服器擁有者。", ephemeral=True)
        return
    if user == guild.me:
        await interaction.followup.send("🚫 你不能踢出我！", ephemeral=True)
        return

    # Check hierarchy
    if isinstance(author, discord.Member) and author != guild.owner:
        if user.top_role >= author.top_role:
            await interaction.followup.send(f"🚫 你無法踢出與你同級或更高層級的用戶 ({user.mention})。", ephemeral=True)
            return
    if user.top_role >= guild.me.top_role and guild.me != guild.owner:
         await interaction.followup.send(f"🚫 機器人無法踢出層級相同或更高的用戶 ({user.mention})。", ephemeral=True)
         return
    # --- End Pre-kick Checks ---

    try:
        # Attempt to DM the user before kicking
        dm_message = f"你已被 **{guild.name}** 伺服器踢出。\n原因: {reason}"
        try:
            await user.send(dm_message)
            print(f"   Sent kick notification DM to {user.name}.")
        except discord.Forbidden:
            print(f"   Could not send kick DM to {user.name} (DMs disabled or blocked).")
        except Exception as dm_err:
            print(f"   Error sending kick DM to {user.name}: {dm_err}")

        # Perform the kick
        kick_audit_reason = f"由 {author.name} ({author.id}) 踢出: {reason}"
        await user.kick(reason=kick_audit_reason)
        print(f"{user} ({user.id}) kicked by {author} ({author.id}) from {guild.name}. Reason: {reason}")

        # Send public confirmation message
        confirmation_message = f"👢 {user.mention} (`{user}`) 已被成功踢出伺服器。\n原因: {reason}"
        await interaction.followup.send(confirmation_message, ephemeral=False) # Public confirmation

        # Send log embed
        log_embed = discord.Embed(title="👢 用戶已被踢出 👢", color=discord.Color.dark_orange(), timestamp=discord.utils.utcnow())
        log_embed.add_field(name="用戶", value=f"{user.mention} ({user.id})", inline=False)
        log_embed.add_field(name="操作者", value=f"{author.mention} ({author.id})", inline=False)
        log_embed.add_field(name="原因", value=reason, inline=True)
        if isinstance(author, discord.Member): log_embed.set_thumbnail(url=author.display_avatar.url)
        await send_to_public_log(guild, log_embed, log_type="Kick")

    except discord.Forbidden:
        error_msg = "⚙️ 踢出操作失敗：機器人權限不足或層級不夠。"
        print(f"Err /管理 踢出 by {author}: Bot lacks permissions or hierarchy for {user}.")
        await interaction.followup.send(error_msg, ephemeral=True)
    except discord.HTTPException as e:
        error_msg = f"⚙️ 踢出操作時發生 Discord API 錯誤 ({e.status})。"
        print(f"Err /管理 踢出 by {author}: HTTP Error {e.status} for {user}.")
        await interaction.followup.send(error_msg, ephemeral=True)
    except Exception as e:
        error_msg = f"⚙️ 踢出操作失敗: {e}"
        print(f"Err /管理 踢出 by {author}: {e} for {user}.")
        await interaction.followup.send(error_msg, ephemeral=True)


# Ban Command (Using User ID)
@manage_group.command(name="封禁", description="永久封禁用戶 (可封禁不在伺服器者，需封禁權限)")
@app_commands.describe(
    user_id="要封禁的用戶的 **ID**。",
    reason="封禁的原因 (可選)。"
)
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.checks.bot_has_permissions(ban_members=True)
async def manage_ban(interaction: discord.Interaction, user_id: str, reason: str = "未指定原因"):
    await interaction.response.defer(ephemeral=True) # Ephemeral confirmation to moderator
    guild = interaction.guild
    author = interaction.user

    # Validate User ID format
    try:
        target_user_id = int(user_id)
    except ValueError:
        await interaction.followup.send("🚫 請提供有效的用戶 ID (純數字)。", ephemeral=True)
        return

    # --- Pre-ban Checks ---
    if target_user_id == author.id:
        await interaction.followup.send("🚫 你不能封禁自己。", ephemeral=True)
        return
    if target_user_id == guild.owner_id:
        await interaction.followup.send("🚫 無法封禁伺服器擁有者。", ephemeral=True)
        return
    if target_user_id == bot.user.id:
        await interaction.followup.send("🚫 你不能封禁我！", ephemeral=True)
        return

    # Check if the target user is currently a member and if hierarchy prevents ban
    target_member = guild.get_member(target_user_id)
    if target_member: # User is in the server
        # Check author hierarchy
        if isinstance(author, discord.Member) and author != guild.owner:
             if target_member.top_role >= author.top_role:
                 await interaction.followup.send(f"🚫 你無法封禁與你同級或更高層級的在線成員 ({target_member.mention})。", ephemeral=True)
                 return
        # Check bot hierarchy
        if target_member.top_role >= guild.me.top_role and guild.me != guild.owner:
            await interaction.followup.send(f"🚫 機器人無法封禁層級相同或更高的在線成員 ({target_member.mention})。", ephemeral=True)
            return
    # --- End Pre-ban Checks ---

    # Fetch user object using ID (works even if user is not in the server)
    try:
        user_to_ban = await bot.fetch_user(target_user_id)
    except discord.NotFound:
        await interaction.followup.send(f"❓ 找不到 ID 為 `{target_user_id}` 的用戶。", ephemeral=True)
        return
    except Exception as fetch_err:
        await interaction.followup.send(f"⚙️ 查找用戶時出錯: {fetch_err}", ephemeral=True)
        return

    # Check if user is already banned
    try:
         await guild.fetch_ban(user_to_ban)
         # If fetch_ban succeeds, user is already banned
         await interaction.followup.send(f"ℹ️ 用戶 {user_to_ban.mention} (`{user_to_ban}`) 已經被封禁了。", ephemeral=True)
         return
    except discord.NotFound:
         # User is not banned, proceed
         pass
    except discord.Forbidden:
         await interaction.followup.send(f"⚙️ 無法檢查封禁狀態：機器人缺少 `查看稽核日誌` 或 `封禁成員` 權限。", ephemeral=True)
         return
    except Exception as fetch_ban_err:
         await interaction.followup.send(f"⚙️ 檢查封禁狀態時出錯: {fetch_ban_err}", ephemeral=True)
         return


    # Perform the ban
    try:
        ban_audit_reason = f"由 {author.name} ({author.id}) 封禁: {reason}"
        # delete_message_days=0: Don't delete messages. Change if needed (0-7).
        await guild.ban(user_to_ban, reason=ban_audit_reason, delete_message_days=0)
        print(f"{user_to_ban} ({target_user_id}) banned by {author} ({author.id}) from {guild.name}. Reason: {reason}")

        # Send public confirmation
        confirmation_message = f"🚫 用戶 {user_to_ban.mention} (`{user_to_ban}`) 已被永久封禁。\n原因: {reason}"
        await interaction.followup.send(confirmation_message, ephemeral=False) # Public confirmation

        # Send log embed
        log_embed = discord.Embed(title="🚫 用戶已被封禁 🚫", color=discord.Color.red(), timestamp=discord.utils.utcnow())
        log_embed.add_field(name="用戶", value=f"{user_to_ban.mention} ({target_user_id})", inline=False)
        log_embed.add_field(name="操作者", value=f"{author.mention} ({author.id})", inline=False)
        log_embed.add_field(name="原因", value=reason, inline=True)
        # You might not have the author's avatar if this is used via DM or other context
        if isinstance(author, discord.Member): log_embed.set_thumbnail(url=author.display_avatar.url)
        await send_to_public_log(guild, log_embed, log_type="Ban")

    except discord.Forbidden:
        error_msg = f"⚙️ 封禁操作失敗：機器人權限不足或層級不夠以封禁 `{user_to_ban}`。"
        print(f"Err /管理 封禁 by {author}: Bot lacks permissions or hierarchy for {user_to_ban} ({target_user_id}).")
        await interaction.followup.send(error_msg, ephemeral=True)
    except discord.HTTPException as e:
         error_msg = f"⚙️ 封禁操作時發生 Discord API 錯誤 ({e.status})。"
         print(f"Err /管理 封禁 by {author}: HTTP Error {e.status} for {user_to_ban} ({target_user_id}).")
         await interaction.followup.send(error_msg, ephemeral=True)
    except Exception as e:
        error_msg = f"⚙️ 封禁操作失敗: {e}"
        print(f"Err /管理 封禁 by {author}: {e} for {user_to_ban} ({target_user_id}).")
        await interaction.followup.send(error_msg, ephemeral=True)

# Unban Command (Using User ID)
@manage_group.command(name="解封", description="解除用戶的封禁 (需封禁成員權限)")
@app_commands.describe(user_id="要解除封禁的用戶的 **ID**。", reason="解除封禁的原因 (可選)。")
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.checks.bot_has_permissions(ban_members=True)
async def manage_unban(interaction: discord.Interaction, user_id: str, reason: str = "未指定原因"):
    await interaction.response.defer(ephemeral=True) # Ephemeral confirmation to moderator
    guild = interaction.guild
    author = interaction.user

    # Validate User ID format
    try:
        target_user_id = int(user_id)
    except ValueError:
        await interaction.followup.send("🚫 請提供有效的用戶 ID (純數字)。", ephemeral=True)
        return

    # Fetch the ban entry to confirm the user is actually banned and get the User object
    try:
        # Use discord.Object to avoid fetching the user if not necessary yet
        ban_entry = await guild.fetch_ban(discord.Object(id=target_user_id))
        user_to_unban = ban_entry.user # Get the User object from the ban entry
    except discord.NotFound:
        # If fetch_ban raises NotFound, the user is not banned
        await interaction.followup.send(f"❓ ID 為 `{target_user_id}` 的用戶當前未被封禁。", ephemeral=True)
        return
    except discord.Forbidden:
         await interaction.followup.send(f"⚙️ 無法檢查封禁狀態或解封：機器人缺少 `封禁成員` 權限。", ephemeral=True)
         return
    except Exception as fetch_ban_err:
        await interaction.followup.send(f"⚙️ 查找封禁記錄時出錯: {fetch_ban_err}", ephemeral=True)
        return

    # Perform the unban
    try:
        unban_audit_reason = f"由 {author.name} ({author.id}) 解除封禁: {reason}"
        await guild.unban(user_to_unban, reason=unban_audit_reason)
        print(f"{user_to_unban} ({target_user_id}) unbanned by {author} ({author.id}) from {guild.name}. Reason: {reason}")

        # Send public confirmation
        confirmation_message = f"✅ 用戶 {user_to_unban.mention} (`{user_to_unban}`) 已被成功解除封禁。\n原因: {reason}"
        await interaction.followup.send(confirmation_message, ephemeral=False) # Public confirmation

        # Send log embed
        log_embed = discord.Embed(title="✅ 用戶已被解除封禁 ✅", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        log_embed.add_field(name="用戶", value=f"{user_to_unban.mention} ({target_user_id})", inline=False)
        log_embed.add_field(name="操作者", value=f"{author.mention} ({author.id})", inline=False)
        log_embed.add_field(name="原因", value=reason, inline=True)
        if isinstance(author, discord.Member): log_embed.set_thumbnail(url=author.display_avatar.url)
        await send_to_public_log(guild, log_embed, log_type="Unban")

    except discord.Forbidden:
        # Should be caught by fetch_ban check, but safety first
        error_msg = f"⚙️ 解封操作失敗：機器人權限不足。"
        print(f"Err /管理 解封 by {author}: Bot lacks permissions for {user_to_unban} ({target_user_id}).")
        await interaction.followup.send(error_msg, ephemeral=True)
    except discord.HTTPException as e:
         error_msg = f"⚙️ 解封操作時發生 Discord API 錯誤 ({e.status})。"
         print(f"Err /管理 解封 by {author}: HTTP Error {e.status} for {user_to_unban} ({target_user_id}).")
         await interaction.followup.send(error_msg, ephemeral=True)
    except Exception as e:
        error_msg = f"⚙️ 解封操作失敗: {e}"
        print(f"Err /管理 解封 by {author}: {e} for {user_to_unban} ({target_user_id}).")
        await interaction.followup.send(error_msg, ephemeral=True)


# Member Count Channel Command
@manage_group.command(name="人數頻道", description="創建或更新顯示伺服器人數的語音頻道 (需管理頻道)")
@app_commands.describe(channel_name_template="頻道名稱模板 (必須包含 '{count}' 代表人數)")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.checks.bot_has_permissions(manage_channels=True) # Bot needs manage channels
async def manage_member_count_channel(interaction: discord.Interaction, channel_name_template: str = "成員人數: {count}"):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild

    # Validate template
    if '{count}' not in channel_name_template:
        await interaction.followup.send("🚫 頻道名稱模板必須包含 `{count}` 佔位符。", ephemeral=True)
        return
    if len(channel_name_template.format(count=guild.member_count)) > 100:
         await interaction.followup.send("🚫 模板生成的頻道名稱過長 (最多 100 字元)。", ephemeral=True)
         return

    # Check for existing channel ID in settings
    existing_channel_id = get_setting(guild.id, "member_count_channel_id")
    existing_channel = guild.get_channel(existing_channel_id) if existing_channel_id else None

    member_count = guild.member_count # Fetch current member count
    new_name = channel_name_template.format(count=member_count)

    if existing_channel and isinstance(existing_channel, discord.VoiceChannel):
        # --- Update Existing Channel ---
        print(f"Updating member count channel for guild {guild.id}...")
        # Check if name actually needs updating
        if existing_channel.name == new_name:
             await interaction.followup.send(f"ℹ️ 人數頻道 {existing_channel.mention} 名稱已是最新 (`{new_name}`)，無需更新。", ephemeral=True)
             return
        try:
            await existing_channel.edit(name=new_name, reason="Update member count")
            # Update the template setting in case it changed
            set_setting(guild.id, "member_count_template", channel_name_template)
            await interaction.followup.send(f"✅ 已更新人數頻道 {existing_channel.mention} 名稱為 `{new_name}`。", ephemeral=True)
            print(f"   Updated channel {existing_channel_id} name to '{new_name}'. Template: '{channel_name_template}'")
        except discord.Forbidden:
            print(f"   Err updating count channel {existing_channel_id}: Bot lacks permissions.")
            await interaction.followup.send(f"⚙️ 更新頻道 {existing_channel.mention} 時失敗：機器人權限不足。", ephemeral=True)
        except discord.HTTPException as e:
             print(f"   Err updating count channel {existing_channel_id}: HTTP Error {e.status}")
             await interaction.followup.send(f"⚙️ 更新頻道時發生 Discord API 錯誤 ({e.status})。", ephemeral=True)
        except Exception as e:
            print(f"   Err updating count channel {existing_channel_id}: {e}")
            await interaction.followup.send(f"⚙️ 更新頻道時發生未知錯誤: {e}", ephemeral=True)
    else:
        # --- Create New Channel ---
        print(f"Creating new member count channel for guild {guild.id}...")
        try:
            # Define permissions: deny connection for everyone, allow bot to manage/view/connect
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False),
                guild.me: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True)
            }
            new_channel = await guild.create_voice_channel(
                name=new_name,
                overwrites=overwrites,
                reason="Create member count channel"
                # Optionally place in a specific category: category=some_category_object
            )
            # Save the new channel ID and template
            set_setting(guild.id, "member_count_channel_id", new_channel.id)
            set_setting(guild.id, "member_count_template", channel_name_template)
            await interaction.followup.send(f"✅ 已成功創建人數頻道 {new_channel.mention} (`{new_name}`)。", ephemeral=True)
            print(f"   Created channel {new_channel.id} with name '{new_name}'. Template: '{channel_name_template}'")
        except discord.Forbidden:
            print(f"   Err creating count channel: Bot lacks permissions.")
            await interaction.followup.send("⚙️ 創建人數頻道失敗：機器人權限不足 (需要 `管理頻道` 權限)。", ephemeral=True)
        except discord.HTTPException as e:
             print(f"   Err creating count channel: HTTP Error {e.status}")
             await interaction.followup.send(f"⚙️ 創建頻道時發生 Discord API 錯誤 ({e.status})。", ephemeral=True)
        except Exception as e:
            print(f"   Err creating count channel: {e}")
            await interaction.followup.send(f"⚙️ 創建頻道時發生未知錯誤: {e}", ephemeral=True)


# --- Temporary Voice Channel Command Group ---
voice_group = app_commands.Group(name="語音", description="臨時語音頻道相關指令")

# Set Master Channel Command
@voice_group.command(name="設定母頻道", description="設定用於創建臨時語音頻道的母頻道 (需管理頻道)")
@app_commands.describe(
    master_channel="用戶加入此語音頻道以創建新頻道。",
    category="(可選) 將新創建的臨時頻道放置在哪個分類下 (預設為母頻道所在分類)。"
)
@app_commands.checks.has_permissions(manage_channels=True, manage_roles=True) # Roles needed for potential permission setting later
@app_commands.checks.bot_has_permissions(manage_channels=True, move_members=True) # Bot needs these to create & move
async def voice_set_master(interaction: discord.Interaction, master_channel: discord.VoiceChannel, category: Optional[discord.CategoryChannel] = None):
    guild_id = interaction.guild_id
    await interaction.response.defer(ephemeral=True)

    # Set the master channel ID
    set_setting(guild_id, "master_channel_id", master_channel.id)

    # Set the category ID (or None if not provided)
    category_id = category.id if category else None
    set_setting(guild_id, "category_id", category_id)

    category_info = f" 並將新頻道創建在 '{category.name}' 分類下" if category else " (新頻道將創建在母頻道所在分類下)"
    await interaction.followup.send(
        f"✅ 臨時語音母頻道已設為 {master_channel.mention}{category_info}。",
        ephemeral=True
    )
    print(f"[TempVC Setup] Guild {guild_id}: Master VC set to {master_channel.id}, Category set to {category_id} by {interaction.user}")

# --- Helper to check if user is the owner of the temp VC they are in ---
# Note: This check is now integrated into the commands themselves
# def is_temp_vc_owner_check():
#     async def predicate(interaction: discord.Interaction) -> bool:
#         user_vc = interaction.user.voice.channel if interaction.user.voice else None
#         if not user_vc or user_vc.id not in temp_vc_owners or temp_vc_owners.get(user_vc.id) != interaction.user.id:
#             await interaction.response.send_message("🚫 此指令僅限在你創建的臨時語音頻道中，且由你本人使用。", ephemeral=True)
#             return False
#         return True
#     return app_commands.check(predicate)

# Set Permissions Command (for Temp VC Owner)
@voice_group.command(name="設定權限", description="設定你目前所在的臨時語音頻道的權限 (限頻道擁有者)")
@app_commands.describe(
    target="要設定權限的用戶或身份組。",
    allow_connect="(可選) 允許連接?",
    allow_speak="(可選) 允許說話?",
    allow_stream="(可選) 允許直播?",
    allow_video="(可選) 允許開啟視訊?"
)
# @is_temp_vc_owner_check() # Apply the check using the decorator
async def voice_set_perms(
    interaction: discord.Interaction,
    target: Union[discord.Member, discord.Role],
    allow_connect: Optional[bool] = None,
    allow_speak: Optional[bool] = None,
    allow_stream: Optional[bool] = None,
    allow_video: Optional[bool] = None):

    await interaction.response.defer(ephemeral=True) # Response is private to the owner
    user = interaction.user
    guild = interaction.guild

    # --- Check if user is in a voice channel and owns it ---
    user_vc = user.voice.channel if user.voice else None
    if not user_vc:
         await interaction.followup.send("🚫 你必須在一個語音頻道中才能使用此指令。", ephemeral=True)
         return
    if user_vc.id not in temp_vc_owners or temp_vc_owners.get(user_vc.id) != user.id:
        await interaction.followup.send("🚫 此指令只能在你創建並擁有的臨時語音頻道中使用。", ephemeral=True)
        return
    # --- End Check ---

    # Prevent modifying bot's own permissions or @everyone default (use specific commands if needed)
    if target == guild.me:
         await interaction.followup.send("🚫 無法透過此指令修改機器人自身的權限。", ephemeral=True)
         return
    # Careful about modifying @everyone - might lock owner out if done incorrectly.
    # Maybe add a confirmation step if target is guild.default_role.

    # Check if any permissions were actually specified
    if allow_connect is None and allow_speak is None and allow_stream is None and allow_video is None:
        await interaction.followup.send("⚠️ 你沒有指定任何要修改的權限。請至少選擇一項。", ephemeral=True)
        return

    # Get existing overwrites or create new ones
    overwrites = user_vc.overwrites_for(target)
    perms_changed = [] # Keep track of what changed for the confirmation message

    # Apply specified permission changes
    if allow_connect is not None:
        if overwrites.connect != allow_connect:
            overwrites.connect = allow_connect
            perms_changed.append(f"連接={allow_connect}")
    if allow_speak is not None:
         if overwrites.speak != allow_speak:
            overwrites.speak = allow_speak
            perms_changed.append(f"說話={allow_speak}")
    if allow_stream is not None:
        if overwrites.stream != allow_stream:
            overwrites.stream = allow_stream
            perms_changed.append(f"直播={allow_stream}")
    if allow_video is not None:
        if overwrites.video != allow_video:
            overwrites.video = allow_video
            perms_changed.append(f"視訊={allow_video}")

    # Check if any permissions actually changed value
    if not perms_changed:
         await interaction.followup.send("ℹ️ 指定的權限與目前設定相同，無需修改。", ephemeral=True)
         return

    try:
        # Apply the updated permissions
        await user_vc.set_permissions(
            target,
            overwrite=overwrites,
            reason=f"權限由頻道擁有者 {user.name} ({user.id}) 設定"
        )
        target_mention = target.mention if isinstance(target, discord.Member) else f"@ {target.name}" # Use @ name for roles
        await interaction.followup.send(
            f"✅ 已更新 **{target_mention}** 在頻道 **{user_vc.mention}** 的權限: {', '.join(perms_changed)}",
            ephemeral=True
        )
        print(f"[TempVC Perms] Owner {user} set perms for {target} in {user_vc.id}: {', '.join(perms_changed)}")
    except discord.Forbidden:
         print(f"Err /語音 設定權限 by {user}: Bot lacks permissions for channel {user_vc.id}.")
         await interaction.followup.send(f"⚙️ 設定權限時出錯：機器人缺少管理權限的權力。", ephemeral=True)
    except discord.HTTPException as e:
          print(f"Err /語音 設定權限 by {user}: HTTP Error {e.status} for channel {user_vc.id}.")
          await interaction.followup.send(f"⚙️ 設定權限時發生 Discord API 錯誤 ({e.status})。", ephemeral=True)
    except Exception as e:
        print(f"Err /語音 設定權限 by {user}: {e} for channel {user_vc.id}.")
        await interaction.followup.send(f"⚙️ 設定權限時發生未知錯誤: {e}", ephemeral=True)


# Transfer Ownership Command (for Temp VC Owner)
@voice_group.command(name="轉讓", description="將你目前臨時語音頻道的所有權轉讓給頻道內另一用戶 (限頻道擁有者)")
@app_commands.describe(new_owner="要接收所有權的新用戶 (必須在同一個臨時頻道內)。")
# @is_temp_vc_owner_check()
async def voice_transfer(interaction: discord.Interaction, new_owner: discord.Member):
    await interaction.response.defer(ephemeral=True) # Response is private initially, confirmation can be public
    user = interaction.user # Current owner invoking command
    guild = interaction.guild

    # --- Check if user is in a voice channel and owns it ---
    user_vc = user.voice.channel if user.voice else None
    if not user_vc:
         await interaction.followup.send("🚫 你必須在一個語音頻道中才能使用此指令。", ephemeral=True)
         return
    if user_vc.id not in temp_vc_owners or temp_vc_owners.get(user_vc.id) != user.id:
        await interaction.followup.send("🚫 此指令只能在你創建並擁有的臨時語音頻道中使用。", ephemeral=True)
        return
    # --- End Check ---

    # --- Validate the new owner ---
    if new_owner.bot:
        await interaction.followup.send("❌ 不能將所有權轉讓給機器人。", ephemeral=True)
        return
    if new_owner == user:
        await interaction.followup.send("❌ 你不能將所有權轉讓給自己。", ephemeral=True)
        return
    # Check if the new owner is in the *same* voice channel
    if not new_owner.voice or new_owner.voice.channel != user_vc:
        await interaction.followup.send(f"❌ {new_owner.mention} 必須和你一樣在 **{user_vc.mention}** 頻道內才能接收所有權。", ephemeral=True)
        return
    # --- End Validation ---

    try:
        # Define permissions for the new owner (same as initial creation)
        new_owner_overwrites = discord.PermissionOverwrite(
            manage_channels=True,
            manage_permissions=True,
            move_members=True,
            connect=True, # Ensure they can still connect
            speak=True    # Ensure they can still speak
        )
        # Define permissions for the old owner (reset to default or specific non-owner perms)
        # Setting overwrite to None resets it to category/default permissions
        old_owner_overwrites = None # Or discord.PermissionOverwrite() for explicit empty overwrite

        # Apply permissions transactionally if possible, though Discord API might not guarantee it.
        # Set new owner's permissions
        await user_vc.set_permissions(
            new_owner,
            overwrite=new_owner_overwrites,
            reason=f"所有權由 {user.name} ({user.id}) 轉讓給 {new_owner.name} ({new_owner.id})"
        )
        # Reset old owner's specific permissions (important!)
        await user_vc.set_permissions(
            user,
            overwrite=old_owner_overwrites,
            reason=f"所有權已轉讓給 {new_owner.name} ({new_owner.id})"
        )

        # Update the internal owner tracking
        temp_vc_owners[user_vc.id] = new_owner.id

        # Send public confirmation
        await interaction.followup.send(
            f"✅ 已成功將頻道 **{user_vc.mention}** 的所有權轉讓給 {new_owner.mention}！",
            ephemeral=False # Make confirmation visible to both parties
        )
        print(f"[TempVC Transfer] Ownership of {user_vc.id} transferred from {user.id} to {new_owner.id} by {user.id}")

    except discord.Forbidden:
         print(f"Err /語音 轉讓 by {user}: Bot lacks permissions for channel {user_vc.id}.")
         await interaction.followup.send(f"⚙️ 轉讓所有權時出錯：機器人缺少管理權限的權力。", ephemeral=True)
    except discord.HTTPException as e:
         print(f"Err /語音 轉讓 by {user}: HTTP Error {e.status} for channel {user_vc.id}.")
         await interaction.followup.send(f"⚙️ 轉讓所有權時發生 Discord API 錯誤 ({e.status})。", ephemeral=True)
    except Exception as e:
        print(f"Err /語音 轉讓 by {user}: {e} for channel {user_vc.id}.")
        await interaction.followup.send(f"⚙️ 轉讓所有權時發生未知錯誤: {e}", ephemeral=True)


# Claim Ownership Command (if original owner left)
@voice_group.command(name="房主", description="如果原房主不在頻道內，嘗試獲取目前臨時語音頻道的所有權")
async def voice_claim(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True) # Private response initially
    user = interaction.user # User attempting to claim
    guild = interaction.guild

    # --- Check if user is in a voice channel and if it's a temp VC ---
    user_vc = user.voice.channel if user.voice else None
    if not user_vc:
         await interaction.followup.send("🚫 你必須在一個語音頻道中才能使用此指令。", ephemeral=True)
         return
    if user_vc.id not in temp_vc_created: # Check if it's one of the VCs managed by the bot
        await interaction.followup.send("🚫 此指令只能在由機器人創建的臨時語音頻道中使用。", ephemeral=True)
        return
    # --- End Check ---

    current_owner_id = temp_vc_owners.get(user_vc.id)

    # Check if the user is already the owner
    if current_owner_id == user.id:
        await interaction.followup.send("ℹ️ 你已經是這個頻道的房主了。", ephemeral=True)
        return

    # Check if the current owner exists and is still in the channel
    owner_is_present = False
    current_owner_member = None
    if current_owner_id:
        current_owner_member = guild.get_member(current_owner_id)
        if current_owner_member and current_owner_member.voice and current_owner_member.voice.channel == user_vc:
            owner_is_present = True

    if owner_is_present:
        await interaction.followup.send(f"❌ 無法獲取所有權，目前的房主 {current_owner_member.mention} 仍在頻道中。", ephemeral=True)
        return

    # --- Proceed with claiming ownership ---
    try:
        # Define owner permissions
        owner_overwrites = discord.PermissionOverwrite(
            manage_channels=True,
            manage_permissions=True,
            move_members=True,
            connect=True,
            speak=True
        )

        # Grant ownership permissions to the claiming user
        await user_vc.set_permissions(
            user,
            overwrite=owner_overwrites,
            reason=f"所有權由 {user.name} ({user.id}) 獲取 (原房主不在)"
        )

        # Reset permissions for the old owner (if they existed and we have the object)
        if current_owner_member: # Use the member object fetched earlier
             try:
                 await user_vc.set_permissions(
                     current_owner_member,
                     overwrite=None, # Reset to default/category permissions
                     reason=f"原房主權限因所有權轉移給 {user.name} 而重設"
                 )
                 print(f"   Reset permissions for previous owner {current_owner_member.id} in {user_vc.id}")
             except Exception as e:
                 # Log if resetting old owner perms fails, but don't stop the claim
                 print(f"   Could not reset permissions for old owner {current_owner_member.id} in {user_vc.id}: {e}")

        # Update internal owner tracking
        temp_vc_owners[user_vc.id] = user.id

        # Send public confirmation
        await interaction.followup.send(
            f"✅ 你已成功獲取頻道 **{user_vc.mention}** 的房主權限！",
            ephemeral=False # Let others know who the new owner is
        )
        print(f"[TempVC Claim] Ownership of {user_vc.id} claimed by {user.id} (Previous: {current_owner_id})")

    except discord.Forbidden:
         print(f"Err /語音 房主 by {user}: Bot lacks permissions for channel {user_vc.id}.")
         await interaction.followup.send(f"⚙️ 獲取房主權限時出錯：機器人缺少管理權限的權力。", ephemeral=True)
    except discord.HTTPException as e:
         print(f"Err /語音 房主 by {user}: HTTP Error {e.status} for channel {user_vc.id}.")
         await interaction.followup.send(f"⚙️ 獲取房主權限時發生 Discord API 錯誤 ({e.status})。", ephemeral=True)
    except Exception as e:
        print(f"Err /語音 房主 by {user}: {e} for channel {user_vc.id}.")
        await interaction.followup.send(f"⚙️ 獲取房主權限時發生未知錯誤: {e}", ephemeral=True)


# --- Add the command groups to the bot tree ---
bot.tree.add_command(manage_group)
bot.tree.add_command(voice_group)

# --- Run the Bot ---
if __name__ == "__main__":
    print("Starting bot...")
    try:
        bot.run(BOT_TOKEN)
    except discord.LoginFailure:
        print("❌ FATAL ERROR: Login failed. The provided DISCORD_BOT_TOKEN is invalid.")
    except discord.PrivilegedIntentsRequired:
        print("❌ FATAL ERROR: Privileged Intents (Members and/or Message Content) are required but not enabled in the Discord Developer Portal for this bot.")
        print("   Please enable 'Server Members Intent' and 'Message Content Intent' at https://discord.com/developers/applications")
    except Exception as e:
        print(f"❌ FATAL ERROR during bot startup: {e}")

# --- End of Complete Code ---