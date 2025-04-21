# slash_role_manager_bot.py (FINAL COMPLETE CODE - Part 1/5: Setup & Basic Events)

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
    elif log_channel_id_for_public != 123456789012345682:
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
        response.raise_for_status(); result = response.json(); api_response_text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        print(f"DEBUG: DeepSeek response for '{message_content[:30]}...': {api_response_text}")
        processed_response = api_response_text.lower()
        if processed_response == "safe" or not processed_response: return None
        elif processed_response == "minor violation": return "Minor Violation"
        else: return api_response_text
    except requests.exceptions.Timeout: print(f"❌ Timeout calling DeepSeek API"); return None
    except requests.exceptions.RequestException as e: print(f"❌ Error calling DeepSeek API: {e}"); return None
    except Exception as e: print(f"❌ Unexpected error during DeepSeek check: {e}"); return None

# --- Event: Bot Ready ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('Syncing application commands...')
    try:
        synced = await bot.tree.sync() # Global sync
        print(f'Synced {len(synced)} application command(s) globally.')
    except Exception as e: print(f'Error syncing commands: {e}')
    print('Bot is ready!')
    print('------')
    await bot.change_presence(activity=discord.Game(name="/help 顯示幫助"))

# --- Event: Command Error Handling (Legacy Prefix Commands) ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    elif isinstance(error, commands.MissingPermissions): await ctx.send(f"🚫 PrefixCmd: 缺少權限: {error.missing_permissions}")
    else: print(f"Error with prefix command {ctx.command}: {error}")

# --- Event: App Command Error Handling ---
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    error_message = "🤔 發生未知的錯誤。"
    ephemeral_response = True
    if isinstance(error, app_commands.CommandNotFound): error_message = "未知的指令。"
    elif isinstance(error, app_commands.MissingPermissions): error_message = f"🚫 你缺少必要權限: {', '.join(f'`{p}`' for p in error.missing_permissions)}。"
    elif isinstance(error, app_commands.BotMissingPermissions): error_message = f"🤖 我缺少必要權限: {', '.join(f'`{p}`' for p in error.missing_permissions)}。"
    elif isinstance(error, app_commands.CheckFailure): error_message = "🚫 你無權使用此指令。"
    elif isinstance(error, app_commands.CommandInvokeError):
        original = error.original
        if isinstance(original, discord.Forbidden): error_message = f"🚫 Discord 權限錯誤 (通常是身份組層級問題)。"
        else: print(f'Unhandled app command error {interaction.command.name if interaction.command else ""}: {original}'); error_message = "⚙️ 指令執行時發生預期外的錯誤。"
    else: print(f'Unhandled app command error type: {type(error).__name__} - {error}')
    try:
        if not interaction.response.is_done(): await interaction.response.send_message(error_message, ephemeral=ephemeral_response)
        else: await interaction.followup.send(error_message, ephemeral=ephemeral_response)
    except Exception as e: print(f"Error sending error message: {e}")
bot.tree.on_error = on_app_command_error

# --- End of Part 1 ---
# slash_role_manager_bot.py (FINAL COMPLETE CODE - Part 2/5: Event Handlers - Member Join & Message)

# --- Event: Member Join - Assign Separator Roles & Welcome ---
@bot.event
async def on_member_join(member: discord.Member):
    """Handles actions when a new member joins the server."""
    guild = member.guild
    print(f'[+] {member.name} ({member.id}) 加入 {guild.name}')

    # --- Assign Separator Roles ---
    # !!! IMPORTANT: Replace role names below with your exact separator role names !!!
    separator_role_names_to_assign = ["▲─────身分─────", "▲─────通知─────", "▲─────其他─────"] # <--- 替换!
    roles_to_add = []
    roles_failed = []
    for role_name in separator_role_names_to_assign:
        role = get(guild.roles, name=role_name)
        if role:
            # Check hierarchy before adding to the list
            if role < guild.me.top_role or guild.me == guild.owner:
                roles_to_add.append(role)
            else:
                roles_failed.append(f"{role_name}(层级不足)")
                print(f"⚠️ Cannot assign join role '{role_name}' to {member.name} - Bot role too low.")
        else:
            roles_failed.append(f"{role_name}(未找到!)")
            print(f"⚠️ Join role '{role_name}' not found in server {guild.name}.")

    if roles_to_add:
        try:
            await member.add_roles(*roles_to_add, reason="Auto-assigned separator roles on join")
            print(f"✅ Assigned {len(roles_to_add)} separator roles to {member.name}.")
        except discord.Forbidden:
            print(f"❌ Error: Bot lacks 'Manage Roles' permission for {member.name}.")
            roles_failed.extend([f"{r.name}(权限不足)" for r in roles_to_add])
        except discord.HTTPException as http_err:
            print(f"❌ Error: HTTP error assigning roles to {member.name}: {http_err}")
            roles_failed.extend([f"{r.name}(HTTP错误)" for r in roles_to_add])
        except Exception as e:
            print(f"❌ Error: Unexpected error assigning roles to {member.name}: {e}")
            roles_failed.extend([f"{r.name}(未知错误)" for r in roles_to_add])

    if roles_failed:
         print(f"‼️ Could not assign the following separator roles for {member.name}: {', '.join(roles_failed)}")

    # --- (Optional) Send Welcome Message ---
    # !!! IMPORTANT: Replace channel IDs below with your actual channel IDs !!!
    welcome_channel_id = 123456789012345678      # <--- 替换! Example ID
    rules_channel_id = 123456789012345679        # <--- 替换! Example ID
    roles_info_channel_id = 123456789012345680   # <--- 替换! Example ID
    verification_channel_id = 123456789012345681 # <--- 替换! Example ID

    welcome_channel = guild.get_channel(welcome_channel_id)
    if welcome_channel and isinstance(welcome_channel, discord.TextChannel):
        # Check bot permissions for the welcome channel
        welcome_perms = welcome_channel.permissions_for(guild.me)
        if welcome_perms.send_messages and welcome_perms.embed_links:
            try:
                embed = discord.Embed(
                    title=f"🎉 歡迎來到 {guild.name}! 🎉",
                    description=(
                        f"你好 {member.mention}! 很高興你能加入 **GJ Team**！\n\n"
                        f"👇 **開始之前:**\n"
                        f"- 阅读服务器规则: <#{rules_channel_id}>\n"
                        f"- 了解身份组信息: <#{roles_info_channel_id}>\n"
                        f"- 认证你的TSB实力: <#{verification_channel_id}>\n\n"
                        f"祝你在 GJ Team 玩得愉快!"
                    ),
                    color=discord.Color.blue() # Customize color
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text=f"你是伺服器的第 {guild.member_count} 位成員！")
                await welcome_channel.send(embed=embed)
                print(f"Sent welcome message for {member.name}.")
            except Exception as e:
                print(f"❌ Error sending welcome message: {e}")
        else:
            print(f"❌ Error: Bot lacks Send/Embed permission in welcome channel {welcome_channel_id}.")
    elif welcome_channel_id != 123456789012345678: # Only warn if ID was changed from placeholder
        print(f"⚠️ Welcome channel {welcome_channel_id} not found or is not a text channel.")


# --- Event: On Message - Handles Content Check, Spam, Commands ---
@bot.event
async def on_message(message: discord.Message):
    """Handles incoming messages for moderation (content, spam) and command processing."""
    # --- Basic Checks: Ignore DMs, self, other bots initially ---
    if not message.guild or message.author.bot or message.author.id == bot.user.id:
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    author = message.author
    author_id = author.id
    guild = message.guild
    channel = message.channel
    member = guild.get_member(author_id) # Fetch member object once, might be None if user leaves quickly

    # --- Ignore Mods/Admins based on Manage Messages permission ---
    if member and channel.permissions_for(member).manage_messages:
        # If you still want mods to use potential legacy prefix commands:
        # if message.content.startswith(COMMAND_PREFIX):
        #     await bot.process_commands(message)
        return # Skip all moderation checks for mods

    # --- 1. DeepSeek API Content Moderation (Primary Check) ---
    violation_type = await check_message_with_deepseek(message.content)
    if violation_type and violation_type != "Minor Violation": # Act on severe API violations
        print(f"🚫 API Violation Detected ({violation_type}): by {author} in #{channel.name}")
        reason_api = f"自动检测到违规内容 ({violation_type})"

        # Attempt to delete the offending message
        delete_success = False
        try:
            if channel.permissions_for(guild.me).manage_messages:
                await message.delete()
                print("   Deleted offending message (API Violation).")
                delete_success = True
            else: print("   Bot lacks Manage Messages permission to delete.")
        except discord.NotFound: print("   Message already deleted (API Violation)."); delete_success = True # Treat as success if gone
        except discord.Forbidden: print("   Forbidden to delete message (API Violation).")
        except Exception as del_e: print(f"   Error deleting message (API Violation): {del_e}")

        # Log the violation to the public channel
        mod_mentions = " ".join([f"<@&{role_id}>" for role_id in MOD_ALERT_ROLE_IDS]) # !!! Ensure IDs are correct !!!
        log_embed_api = discord.Embed(
            title=f"🚨 自动内容审核提醒 ({violation_type}) 🚨",
            color=discord.Color.dark_red(),
            timestamp=now
        )
        log_embed_api.add_field(name="用户", value=f"{author.mention} ({author_id})", inline=False)
        log_embed_api.add_field(name="频道", value=channel.mention, inline=False)
        log_embed_api.add_field(name="内容摘要", value=f"```{message.content[:1000]}```", inline=False) # Show part of the content
        log_embed_api.add_field(name="消息状态", value="已删除" if delete_success else "删除失败/无权限", inline=True)
        log_embed_api.add_field(name="消息链接", value=f"[原始链接]({message.jump_url}) (可能已删除)", inline=True)
        log_embed_api.add_field(name="建议操作", value=f"{mod_mentions} 请管理员审核并处理！", inline=False)
        await send_to_public_log(guild, log_embed_api, log_type=f"API Violation ({violation_type})")

        # --- OPTIONAL: Auto-Warn based on API result (USE WITH CAUTION) ---
        # Consider the risks of false positives from the API.
        # Example: Warn only for specific severe types
        # if violation_type.lower() in ["hate speech", "severe threats", "harassment/bullying"]:
        #     user_warnings[author_id] = user_warnings.get(author_id, 0) + 1
        #     warning_count = user_warnings[author_id]
        #     print(f"   API Violation: Auto-warning user {author}. Count: {warning_count}")
        #     # Add kick logic if warning_count >= KICK_THRESHOLD
        #     # Build and send warn embed to public log
        #     # Notify user in channel (if not kicked)
        # --- End Optional Auto-Warn ---

        return # Stop further checks after severe API violation handled

    # --- 2. Bad Word Detection Logic (Optional Fallback or Complement) ---
    # Runs only if DeepSeek is disabled, returns None, or returns "Minor Violation" AND bad word list is not empty
    if BAD_WORDS_LOWER: # Only run if the list is not empty
        content_lower_for_bw = message.content.lower() # Ensure it's lowercase
        triggered_bad_word = None
        for word in BAD_WORDS_LOWER:
            # Using simple 'in' check. For more accuracy against parts of words,
            # consider using regex with word boundaries: r'\b' + re.escape(word) + r'\b'
            if word in content_lower_for_bw:
                triggered_bad_word = word # Store the matched lowercase word
                break

        if triggered_bad_word:
            print(f"🚫 Bad Word Detected: '{triggered_bad_word}' by {author} in #{channel.name}")
            guild_offenses = user_first_offense_reminders.setdefault(guild.id, {})
            user_offenses = guild_offenses.setdefault(author_id, set())

            if triggered_bad_word not in user_offenses: # First offense for this specific word
                user_offenses.add(triggered_bad_word)
                print(f"   First offense for '{triggered_bad_word}' by {author}. Sending reminder.")
                try:
                    # !!! Replace rules_channel_id if needed !!!
                    rules_ch_id = 123456789012345679 # <--- 替换! Example ID
                    rules_ch_mention = f"<#{rules_ch_id}>" if rules_ch_id != 123456789012345679 else "#規則"
                    reminder_msg = (f"{author.mention}，请注意言辞，参考 {rules_ch_mention}。本次提醒。")
                    await channel.send(reminder_msg, delete_after=20)
                except Exception as remind_err: print(f"   Error sending bad word reminder: {remind_err}")
                # Decide whether to delete the first offense message (optional)
                # try: await message.delete() except: pass
                return # Stop processing after reminder

            else: # Repeat offense (any bad word after first reminder for *a* bad word) -> Warn
                print(f"   Repeat bad word offense. Issuing warn.")
                reason = f"自动警告：再次使用不当词语 ('{triggered_bad_word}')"
                user_warnings[author_id] = user_warnings.get(author_id, 0) + 1; warning_count = user_warnings[author_id]; print(f"   User warnings: {warning_count}/{KICK_THRESHOLD}")
                warn_embed = discord.Embed(color=discord.Color.orange(), timestamp=now); warn_embed.set_author(name=f"自动警告发出", icon_url=bot.user.display_avatar.url); warn_embed.add_field(name="用户", value=f"{author.mention} ({author_id})", inline=False); warn_embed.add_field(name="原因", value=reason, inline=False); warn_embed.add_field(name="当前警告次数", value=f"{warning_count}/{KICK_THRESHOLD}", inline=False); warn_embed.add_field(name="消息链接", value=f"[点击跳转]({message.jump_url})", inline=False) # Add message link to log

                kick_performed = False
                if warning_count >= KICK_THRESHOLD:
                    warn_embed.title = "🚨 自动踢出 (不当言语警告上限) 🚨"; warn_embed.color = discord.Color.red(); warn_embed.add_field(name="处 置", value="用户已被踢出", inline=False); print(f"   Kick threshold: {author}")
                    if member: bot_member = guild.me; kick_reason_bw = f"自动踢出：不当言语警告达到 {KICK_THRESHOLD} 次。"; if bot_member.guild_permissions.kick_members and (bot_member.top_role > member.top_role or bot_member == guild.owner): try: await member.kick(reason=kick_reason_bw); print(f"   Kicked {member.name}."); kick_performed = True; user_warnings[author_id] = 0; warn_embed.add_field(name="踢出状态", value="成功", inline=False); except Exception as kick_err: print(f"   Kick Err (Bad Words): {kick_err}"); warn_embed.add_field(name="踢出状态", value=f"失败 ({kick_err})", inline=False)
                    else: print(f"   Bot lacks kick perms/hierarchy."); warn_embed.add_field(name="踢出状态", value="失败 (权限/层级不足)", inline=False)
                    else: print(f"   Cannot get Member for kick."); warn_embed.add_field(name="踢出状态", value="失败 (无法获取成员)", inline=False)
                else: warn_embed.title = "⚠️ 自动警告 (不当言语) ⚠️"

                await send_to_public_log(guild, warn_embed, log_type="Auto Warn (Bad Word)") # Log publicly
                if not kick_performed:
                    try: await channel.send(f"{author.mention}，你的言论触发自动警告。({warning_count}/{KICK_THRESHOLD})", delete_after=20)
                    except Exception as e: print(f"   Error sending bad word repeat offense notice: {e}")
                # Optionally delete the offensive message even if warned
                # try: await message.delete() except: pass
                return # Stop processing after bad word warning/kick

    # --- 3. User Spam Detection Logic ---
    # This runs only if no severe API violation or repeat bad word offense occurred
    user_message_timestamps.setdefault(author_id, []); user_warnings.setdefault(author_id, 0)
    user_message_timestamps[author_id].append(now)
    time_limit_user = now - datetime.timedelta(seconds=SPAM_TIME_WINDOW_SECONDS)
    user_message_timestamps[author_id] = [ts for ts in user_message_timestamps[author_id] if ts > time_limit_user]
    if len(user_message_timestamps[author_id]) >= SPAM_COUNT_THRESHOLD:
        print(f"🚨 User Spam: {author} in #{channel.name}")
        user_warnings[author_id] += 1; warning_count = user_warnings[author_id]
        print(f"   User warnings: {warning_count}/{KICK_THRESHOLD}")
        user_message_timestamps[author_id] = [] # Reset user timestamps
        log_embed_user = discord.Embed(color=discord.Color.orange(), timestamp=now); log_embed_user.set_author(name=f"自动警告 (用户刷屏)", icon_url=bot.user.display_avatar.url); log_embed_user.add_field(name="用户", value=f"{author.mention} ({author_id})", inline=False); log_embed_user.add_field(name="频道", value=channel.mention, inline=True); log_embed_user.add_field(name="警告次数", value=f"{warning_count}/{KICK_THRESHOLD}", inline=True); log_embed_user.add_field(name="消息链接", value=f"[点击跳转]({message.jump_url})", inline=False)
        kick_performed_spam = False
        if warning_count >= KICK_THRESHOLD:
            log_embed_user.title = "🚨 自动踢出 (用户刷屏警告上限) 🚨"; log_embed_user.color = discord.Color.red(); log_embed_user.add_field(name="处 置", value="用户已被踢出", inline=False); print(f"   Kick threshold: {author}")
            if member: # Kick logic...
                bot_member = guild.me; kick_reason = f"自动踢出：刷屏警告达到 {KICK_THRESHOLD} 次。";
                if bot_member.guild_permissions.kick_members and (bot_member.top_role > member.top_role or bot_member == guild.owner):
                    try: await member.kick(reason=kick_reason); print(f"   Kicked {member.name}."); kick_performed_spam = True; user_warnings[author_id] = 0; log_embed_user.add_field(name="踢出状态", value="成功", inline=False);
                    except Exception as kick_err: print(f"   Kick Err: {kick_err}"); log_embed_user.add_field(name="踢出状态", value=f"失败 ({kick_err})", inline=False)
                else: print(f"   Bot lacks kick perms/hierarchy."); log_embed_user.add_field(name="踢出状态", value="失败 (权限/层级不足)", inline=False)
            else: print(f"   Cannot get Member for kick."); log_embed_user.add_field(name="踢出状态", value="失败 (无法获取成员)", inline=False)
        else: log_embed_user.title = "⚠️ 自动警告 (用户刷屏) ⚠️"
        await send_to_public_log(guild, log_embed_user, log_type="Auto Warn (User Spam)") # Send log
        if not kick_performed_spam:
            try: await channel.send(f"⚠️ {author.mention}，请减缓发言！({warning_count}/{KICK_THRESHOLD} 警告)", delete_after=15)
            except Exception as warn_err: print(f"   Error sending warning: {warn_err}")
        # Do not return here, allow potential prefix commands below if needed

    # --- Process Legacy Prefix Commands (Optional) ---
    # Only processes if the message wasn't handled by any moderation above
    # if message.content.startswith(COMMAND_PREFIX):
    #    await bot.process_commands(message)

# --- Event: Voice State Update ---
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    # (Full temp VC logic with corrected claim syntax)
    guild = member.guild; master_vc_id = get_setting(guild.id, "master_channel_id"); category_id = get_setting(guild.id, "category_id")
    if not master_vc_id: return
    master_channel = guild.get_channel(master_vc_id)
    if not master_channel or not isinstance(master_channel, discord.VoiceChannel): print(f"⚠️ Invalid Master VC ID {master_vc_id}"); return
    category = guild.get_channel(category_id) if category_id else master_channel.category
    if category and not isinstance(category, discord.CategoryChannel): category = master_channel.category
    # Join Master VC
    if after.channel == master_channel:
        print(f"{member.name} joined master VC. Creating...")
        try:
            owner_overwrites = discord.PermissionOverwrite(manage_channels=True, manage_permissions=True, move_members=True); everyone_overwrites = discord.PermissionOverwrite(connect=True, speak=True); temp_channel_name = f"{member.display_name} 的頻道"
            new_channel = await guild.create_voice_channel(name=temp_channel_name, category=category, overwrites={guild.default_role: everyone_overwrites, member: owner_overwrites, guild.me: discord.PermissionOverwrite(manage_channels=True, manage_permissions=True, move_members=True)}, reason=f"Temp VC by {member.name}")
            print(f"   Created {new_channel.name} ({new_channel.id})"); await member.move_to(new_channel); print(f"   Moved {member.name}.")
            temp_vc_owners[new_channel.id] = member.id; temp_vc_created.add(new_channel.id)
        except Exception as e: print(f"   Error creating temp VC: {e}")
    # Leave Temp VC
    if before.channel and before.channel.id in temp_vc_created:
        print(f"{member.name} left temp VC {before.channel.name}. Checking empty..."); await asyncio.sleep(1)
        channel_to_check = guild.get_channel(before.channel.id)
        if channel_to_check and isinstance(channel_to_check, discord.VoiceChannel):
            if not any(m for m in channel_to_check.members if not m.bot):
                print(f"   {channel_to_check.name} empty. Deleting..."); try: await channel_to_check.delete(reason="Temp VC empty"); print(f"   Deleted.")
                except Exception as e: print(f"   Error deleting {channel_to_check.name}: {e}")
                finally: if channel_to_check.id in temp_vc_owners: del temp_vc_owners[channel_to_check.id]; if channel_to_check.id in temp_vc_created: temp_vc_created.remove(channel_to_check.id)
            else: print(f"   {channel_to_check.name} still has members.")
        else:
            print(f"   Channel {before.channel.id} no longer exists or not a VC.")
            if before.channel.id in temp_vc_owners: del temp_vc_owners[before.channel.id]
            if before.channel.id in temp_vc_created: temp_vc_created.remove(before.channel.id)

# --- Slash Command Definitions ---
@bot.tree.command(name="help", description="顯示可用指令的相關資訊。")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 GJ Team Bot Help", description="可用的斜線指令:", color=discord.Color.purple())
    embed.add_field( name="🛠️ 管理與審核", value=("/createrole `身份組名稱`\n" "/deleterole `身份組名稱`\n" "/giverole `用戶` `身份組名稱`\n" "/takerole `用戶` `身份組名稱`\n" "/createseparator `標籤`\n" "/clear `數量`\n" "/warn `用戶` `[原因]`\n" "/unwarn `用戶` `[原因]`"), inline=False )
    embed.add_field(name="📢 公告", value=("/announce `頻道` `標題` `訊息` `[提及身份組]` `[圖片URL]` `[顏色]`"), inline=False)
    embed.add_field(name="⚙️ 管理指令群組 (/管理)", value=("/管理 公告頻道 `[頻道]`\n" "/管理 紀錄頻道 `[頻道]`\n" "/管理 反應身分 (待實現)\n" "/管理 刪訊息 `用戶` `數量`\n" "/管理 頻道名 `新名稱`\n" "/管理 禁言 `用戶` `分鐘數` `[原因]`\n" "/管理 踢出 `用戶` `[原因]`\n" "/管理 封禁 `用戶ID` `[原因]`\n" "/管理 解封 `用戶ID` `[原因]`\n" "/管理 人數頻道 `[名稱模板]`"), inline=False)
    embed.add_field(name="🔊 臨時語音指令群組 (/語音)", value=("/語音 設定母頻道 `母頻道` `[分類]`\n" "/語音 設定權限 `對象` `[權限設定]`\n" "/語音 轉讓 `新房主`\n" "/語音 房主"), inline=False)
    embed.add_field(name="ℹ️ 其他", value="/help - 顯示此幫助訊息。", inline=False)
    embed.set_footer(text="<> = 必填, [] = 可選。大部分指令需管理權限。")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="createrole", description="在伺服器中創建一個新的身份組。")
@app_commands.describe(role_name="新身份組的確切名稱。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_createrole(interaction: discord.Interaction, role_name: str):
    guild=interaction.guild; await interaction.response.defer(ephemeral=True);
    if not guild: await interaction.followup.send("僅限伺服器內使用。", ephemeral=True); return
    if get(guild.roles, name=role_name): await interaction.followup.send(f"身份組 **{role_name}** 已存在！", ephemeral=True); return
    if len(role_name) > 100: await interaction.followup.send("身份組名稱過長。", ephemeral=True); return
    try: new_role = await guild.create_role(name=role_name, reason=f"由 {interaction.user} 創建"); await interaction.followup.send(f"✅ 已創建身份組: {new_role.mention}", ephemeral=False)
    except Exception as e: print(f"Err /createrole: {e}"); await interaction.followup.send(f"⚙️ 創建時出錯: {e}", ephemeral=True)

@bot.tree.command(name="deleterole", description="依據精確名稱刪除一個現有的身份組。")
@app_commands.describe(role_name="要刪除的身份組的確切名稱。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_deleterole(interaction: discord.Interaction, role_name: str):
    guild=interaction.guild; await interaction.response.defer(ephemeral=True);
    if not guild: await interaction.followup.send("僅限伺服器內使用。", ephemeral=True); return
    role = get(guild.roles, name=role_name)
    if not role: await interaction.followup.send(f"❓ 找不到身份組 **{role_name}**。", ephemeral=True); return
    if role == guild.default_role: await interaction.followup.send("🚫 無法刪除 `@everyone`。", ephemeral=True); return
    if role >= guild.me.top_role and guild.me != guild.owner: await interaction.followup.send(f"🚫 機器人層級錯誤: {role.mention}。", ephemeral=True); return
    if role.is_managed(): await interaction.followup.send(f"⚠️ 無法刪除受管理的身份組 {role.mention}。", ephemeral=True); return
    try: name = role.name; await role.delete(reason=f"由 {interaction.user} 刪除"); await interaction.followup.send(f"✅ 已刪除身份組: **{name}**", ephemeral=False)
    except Exception as e: print(f"Err /deleterole: {e}"); await interaction.followup.send(f"⚙️ 刪除時出錯: {e}", ephemeral=True)

@bot.tree.command(name="giverole", description="將一個現有的身份組分配給指定成員。")
@app_commands.describe(user="要給予身份組的用戶。", role_name="要分配的身份組的確切名稱。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_giverole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    guild=interaction.guild; await interaction.response.defer(ephemeral=True);
    if not guild: await interaction.followup.send("僅限伺服器內使用。", ephemeral=True); return
    role = get(guild.roles, name=role_name)
    if not role: await interaction.followup.send(f"❓ 找不到身份組 **{role_name}**。", ephemeral=True); return
    if role >= guild.me.top_role and guild.me != guild.owner: await interaction.followup.send(f"🚫 機器人層級錯誤: {role.mention}。", ephemeral=True); return
    if isinstance(interaction.user, discord.Member) and role >= interaction.user.top_role and interaction.user != guild.owner: await interaction.followup.send(f"🚫 你的層級不足以分配 {role.mention}。", ephemeral=True); return
    if role in user.roles: await interaction.followup.send(f"ℹ️ {user.mention} 已擁有 {role.mention}。", ephemeral=True); return
    try: await user.add_roles(role, reason=f"由 {interaction.user} 分配"); await interaction.followup.send(f"✅ 已給予 {user.mention} 身份組 {role.mention}。", ephemeral=False)
    except Exception as e: print(f"Err /giverole: {e}"); await interaction.followup.send(f"⚙️ 分配時出錯: {e}", ephemeral=True)

@bot.tree.command(name="takerole", description="從指定成員移除一個特定的身份組。")
@app_commands.describe(user="要移除其身份組的用戶。", role_name="要移除的身份組的確切名稱。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_takerole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    guild=interaction.guild; await interaction.response.defer(ephemeral=True);
    if not guild: await interaction.followup.send("僅限伺服器內使用。", ephemeral=True); return
    role = get(guild.roles, name=role_name)
    if not role: await interaction.followup.send(f"❓ 找不到身份組 **{role_name}**。", ephemeral=True); return
    if role >= guild.me.top_role and guild.me != guild.owner: await interaction.followup.send(f"🚫 機器人層級錯誤: {role.mention}。", ephemeral=True); return
    if isinstance(interaction.user, discord.Member) and role >= interaction.user.top_role and interaction.user != guild.owner: await interaction.followup.send(f"🚫 你的層級不足以移除 {role.mention}。", ephemeral=True); return
    if role not in user.roles: await interaction.followup.send(f"ℹ️ {user.mention} 並沒有 {role.mention}。", ephemeral=True); return
    if role.is_managed(): await interaction.followup.send(f"⚠️ 無法移除受管理的身份組 {role.mention}。", ephemeral=True); return
    try: await user.remove_roles(role, reason=f"由 {interaction.user} 移除"); await interaction.followup.send(f"✅ 已從 {user.mention} 移除身份組 {role.mention}。", ephemeral=False)
    except Exception as e: print(f"Err /takerole: {e}"); await interaction.followup.send(f"⚙️ 移除時出錯: {e}", ephemeral=True)

@bot.tree.command(name="createseparator", description="創建一個視覺分隔線身份組。")
@app_commands.describe(label="要在分隔線中顯示的文字 (例如 '身分', '通知')。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_createseparator(interaction: discord.Interaction, label: str):
    guild=interaction.guild; await interaction.response.defer(ephemeral=True);
    if not guild: await interaction.followup.send("...", ephemeral=True); return
    separator_name = f"▲─────{label}─────"
    if len(separator_name) > 100: await interaction.followup.send(f"❌ 標籤過長。", ephemeral=True); return
    if get(guild.roles, name=separator_name): await interaction.followup.send(f"⚠️ 分隔線 **{separator_name}** 已存在!", ephemeral=True); return
    try: new_role = await guild.create_role(name=separator_name, permissions=discord.Permissions.none(), color=discord.Color.light_grey(), hoist=False, mentionable=False, reason=f"Separator by {interaction.user}"); await interaction.followup.send(f"✅ 已創建分隔線: **{new_role.name}**\n**重要:** 請去 **伺服器設定 -> 身份組** 手動拖動位置！",ephemeral=False)
    except Exception as e: print(f"Err /createseparator: {e}"); await interaction.followup.send(f"⚙️ 創建分隔線時出錯: {e}", ephemeral=True)

@bot.tree.command(name="clear", description="刪除此頻道中指定數量的訊息 (1-100)。")
@app_commands.describe(amount="要刪除的訊息數量。")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
async def slash_clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel): await interaction.response.send_message("僅限文字頻道。", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    try: deleted = await channel.purge(limit=amount); await interaction.followup.send(f"✅ 已刪除 {len(deleted)} 則訊息。", ephemeral=True)
    except Exception as e: print(f"Err /clear: {e}"); await interaction.followup.send(f"⚙️ 刪除時出錯: {e}", ephemeral=True)

@bot.tree.command(name="warn", description="手動向用戶發出一次警告。")
@app_commands.describe(user="要警告的用戶。", reason="警告的原因 (可選)。")
@app_commands.checks.has_permissions(kick_members=True)
async def slash_warn(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    guild = interaction.guild; author = interaction.user
    if not guild: await interaction.response.send_message("...", ephemeral=True); return
    if user.bot: await interaction.response.send_message("無法警告機器人。", ephemeral=True); return
    if user == author: await interaction.response.send_message("無法警告自己。", ephemeral=True); return
    if isinstance(author, discord.Member) and user.top_role >= author.top_role and author != guild.owner: await interaction.response.send_message(f"🚫 無法警告 {user.mention} (層級問題)。", ephemeral=True); return
    await interaction.response.defer(ephemeral=False) # Make response visible
    user_id = user.id; user_warnings[user_id] = user_warnings.get(user_id, 0) + 1; warning_count = user_warnings[user_id]
    print(f"⚠️ Manual Warn: {author} warned {user}. Reason: {reason}. New count: {warning_count}/{KICK_THRESHOLD}")
    embed = discord.Embed(color=discord.Color.orange())
    embed.set_author(name=f"由 {author.display_name} 發出警告", icon_url=author.display_avatar.url)
    embed.add_field(name="被警告用戶", value=user.mention, inline=False); embed.add_field(name="原因", value=reason, inline=False); embed.add_field(name="目前警告次數", value=f"{warning_count}/{KICK_THRESHOLD}", inline=False); embed.timestamp = discord.utils.utcnow()
    if warning_count >= KICK_THRESHOLD:
        embed.title = "🚨 警告已達上限 - 用戶已被踢出 🚨"; embed.color = discord.Color.red(); embed.add_field(name="處置", value="踢出伺服器", inline=False); print(f"   Kick threshold: {user.name}")
        bot_member = guild.me; kick_allowed = False; kick_fail_reason = "未知"
        if bot_member.guild_permissions.kick_members and (bot_member.top_role > user.top_role or bot_member == guild.owner): kick_allowed = True
        else: kick_fail_reason = "機器人權限/層級"; print(f"   Kick Fail: {kick_fail_reason}")
        if kick_allowed:
            try:
                kick_dm = f"由於累積達到 {KICK_THRESHOLD} 次警告，你已被踢出伺服器 **{guild.name}** (最後警告由 {author.display_name} 發出：{reason})。"
                try: await user.send(kick_dm)
                except Exception as dm_err: print(f"   Kick DM Err: {dm_err}")
                await user.kick(reason=f"警告達到 {KICK_THRESHOLD} 次 (手動警告 by {author}: {reason})")
                print(f"   Kicked {user.name}."); embed.add_field(name="踢出狀態", value="成功", inline=False); user_warnings[user_id] = 0
            except Exception as kick_err: print(f"   Kick Err: {kick_err}"); embed.add_field(name="踢出狀態", value=f"失敗 ({kick_err})", inline=False)
        else: embed.add_field(name="踢出狀態", value=f"失敗 ({kick_fail_reason})", inline=False)
    else: embed.title = "⚠️ 手動警告已發出 ⚠️"; embed.add_field(name="後續", value=f"達到 {KICK_THRESHOLD} 次警告將被踢出。", inline=False)
    await interaction.followup.send(embed=embed) # Send to user first
    await send_to_public_log(guild, embed, log_type="Manual Warn") # Then send to public log

@bot.tree.command(name="unwarn", description="移除用戶的一次警告。")
@app_commands.describe(user="要移除其警告的用戶。", reason="移除警告的原因 (可選)。")
@app_commands.checks.has_permissions(kick_members=True)
async def slash_unwarn(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    guild = interaction.guild; author = interaction.user;
    if not guild: await interaction.response.send_message("...", ephemeral=True); return
    if user.bot: await interaction.response.send_message("機器人沒有警告。", ephemeral=True); return
    user_id = user.id; current_warnings = user_warnings.get(user_id, 0)
    if current_warnings <= 0: await interaction.response.send_message(f"{user.mention} 目前沒有警告可移除。", ephemeral=True); return
    user_warnings[user_id] = current_warnings - 1; new_warning_count = user_warnings[user_id]
    print(f"✅ Unwarn: {author} unwarned {user}. Reason: {reason}. New count: {new_warning_count}/{KICK_THRESHOLD}")
    embed = discord.Embed(title="✅ 警告已移除 ✅", color=discord.Color.green())
    embed.set_author(name=f"由 {author.display_name} 操作", icon_url=author.display_avatar.url)
    embed.add_field(name="用戶", value=user.mention, inline=False); embed.add_field(name="移除原因", value=reason, inline=False); embed.add_field(name="新的警告次數", value=f"{new_warning_count}/{KICK_THRESHOLD}", inline=False); embed.timestamp = discord.utils.utcnow()
    await send_to_public_log(guild, embed, log_type="Manual Unwarn") # Send to public log first
    await interaction.response.send_message(embed=embed, ephemeral=True) # Confirm to user

@bot.tree.command(name="announce", description="發送帶有精美嵌入格式的公告。")
@app_commands.describe( channel="要發送公告的頻道。", title="公告的標題。", message="公告的主要內容 (使用 '\\n' 換行)。", ping_role="(可選) 要在公告前提及的身份組。", image_url="(可選) 要在公告中包含的圖片 URL。", color="(可選) 嵌入框的十六進制顏色碼 (例如 '#3498db').")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True)
async def slash_announce(interaction: discord.Interaction, channel: discord.TextChannel, title: str, message: str, ping_role: discord.Role = None, image_url: str = None, color: str = None):
    guild=interaction.guild; author=interaction.user;
    await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("...", ephemeral=True); return
    embed_color = discord.Color.blue(); valid_image = None; validation_warning = None
    if color:
        try: clr = color.lstrip('#').lstrip('0x'); embed_color = discord.Color(int(clr, 16))
        except ValueError: validation_warning = "無效的顏色格式。使用預設。"
    if image_url and image_url.startswith(('http://', 'https://')): valid_image = image_url
    elif image_url: validation_warning = (validation_warning + "\n" if validation_warning else "") + "無效的圖片URL。已略過圖片。"
    if validation_warning: await interaction.followup.send(f"⚠️ {validation_warning}", ephemeral=True)
    embed = discord.Embed(title=f"**{title}**", description=message.replace('\\n', '\n'), color=embed_color, timestamp=discord.utils.utcnow())
    embed.set_footer(text=f"由 {author.display_name} 發布 | GJ Team", icon_url=guild.icon.url if guild.icon else None)
    if valid_image: embed.set_image(url=valid_image)
    ping_content = ping_role.mention if ping_role else None
    try:
        bot_perms = channel.permissions_for(guild.me)
        if not bot_perms.send_messages or not bot_perms.embed_links: await interaction.followup.send(f"Bot缺少在 {channel.mention} 發送/嵌入的權限。", ephemeral=True); return
        await channel.send(content=ping_content, embed=embed)
        if not validation_warning: await interaction.followup.send(f"✅ 公告已發送到 {channel.mention}!", ephemeral=True)
        else: print(f"公告已發送至 {channel.mention} by {author} 但有驗證警告。")
    except Exception as e: print(f"Err /announce: {e}"); await interaction.followup.send(f"⚙️ 發送時出錯: {e}", ephemeral=True)


# --- Management Command Group Definitions ---
manage_group = app_commands.Group(name="管理", description="伺服器管理相關指令 (限管理員)")

@manage_group.command(name="公告頻道", description="設定或查看發布公告的頻道 (需管理員)")
@app_commands.describe(channel="公告頻道 (留空則查看)")
@app_commands.checks.has_permissions(administrator=True)
async def manage_announce_channel(interaction: discord.Interaction, channel: discord.TextChannel = None):
    guild_id = interaction.guild_id; await interaction.response.defer(ephemeral=True);
    if channel: set_setting(guild_id, "announce_channel_id", channel.id); await interaction.followup.send(f"✅ 公告頻道設為 {channel.mention}", ephemeral=True)
    else: ch_id = get_setting(guild_id, "announce_channel_id"); current_ch = interaction.guild.get_channel(ch_id) if ch_id else None; await interaction.followup.send(f"ℹ️ 目前公告頻道: {current_ch.mention if current_ch else '未設定'}", ephemeral=True)

@manage_group.command(name="紀錄頻道", description="設定或查看紀錄頻道 (需管理員)")
@app_commands.describe(channel="紀錄頻道 (留空則查看)")
@app_commands.checks.has_permissions(administrator=True)
async def manage_log_channel(interaction: discord.Interaction, channel: discord.TextChannel = None):
     guild_id = interaction.guild_id; await interaction.response.defer(ephemeral=True);
     if channel:
         set_setting(guild_id, "log_channel_id", channel.id)
         try: await channel.send("✅ Bot 紀錄頻道已設置"); await interaction.followup.send(f"✅ 紀錄頻道設為 {channel.mention}", ephemeral=True)
         except discord.Forbidden: await interaction.followup.send(f"⚠️ 已設定 {channel.mention} 但 Bot 無法在此發送訊息!", ephemeral=True)
         except Exception as e: await interaction.followup.send(f"⚠️ 設定出錯: {e}", ephemeral=True)
     else: ch_id = get_setting(guild_id, "log_channel_id"); current_ch = interaction.guild.get_channel(ch_id) if ch_id else None; await interaction.followup.send(f"ℹ️ 目前紀錄頻道: {current_ch.mention if current_ch else '未設定'}", ephemeral=True)

@manage_group.command(name="反應身分", description="設定反應身份組 (待實現)")
@app_commands.checks.has_permissions(manage_roles=True)
async def manage_reaction_roles(interaction: discord.Interaction): await interaction.response.send_message("🚧 反應身份組功能待實現 (建議使用 Buttons)。", ephemeral=True)

@manage_group.command(name="刪訊息", description="刪除指定用戶的訊息 (需管理訊息)")
@app_commands.describe(user="要刪除其訊息的用戶", amount="要檢查並刪除的最近訊息數量 (1-100)")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
async def manage_delete_user_messages(interaction: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 1, 100]):
    await interaction.response.defer(ephemeral=True);
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel): await interaction.followup.send("僅限文字頻道。", ephemeral=True); return
    deleted_count = 0
    try: deleted = await channel.purge(limit=amount, check=lambda m: m.author == user); deleted_count = len(deleted); await interaction.followup.send(f"✅ 成功刪除了 {user.mention} 的 {deleted_count} 則訊息。", ephemeral=True)
    except Exception as e: print(f"Err /管理 刪訊息: {e}"); await interaction.followup.send(f"⚙️ 刪除訊息時出錯: {e}", ephemeral=True)

@manage_group.command(name="頻道名", description="修改當前文字頻道的名稱 (需管理頻道)")
@app_commands.describe(new_name="新的頻道名稱")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.checks.bot_has_permissions(manage_channels=True)
async def manage_channel_name(interaction: discord.Interaction, new_name: str):
    channel = interaction.channel;
    if not isinstance(channel, discord.TextChannel): await interaction.response.send_message("僅限文字頻道。", ephemeral=True); return
    await interaction.response.defer(ephemeral=True); old_name = channel.name
    try: await channel.edit(name=new_name, reason=f"由 {interaction.user} 修改"); await interaction.followup.send(f"✅ 頻道名稱已從 `{old_name}` 修改為 `{new_name}`。", ephemeral=False)
    except Exception as e: print(f"Err /管理 頻道名: {e}"); await interaction.followup.send(f"⚙️ 修改頻道名稱時出錯: {e}", ephemeral=True)

@manage_group.command(name="禁言", description="禁言成員 (需禁言成員權限)")
@app_commands.describe(user="要禁言的用戶", duration_minutes="禁言分鐘數 (0=最長28天)", reason="原因(可選)")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.checks.bot_has_permissions(moderate_members=True)
async def manage_mute(interaction: discord.Interaction, user: discord.Member, duration_minutes: int, reason: str = "未指定原因"):
    await interaction.response.defer(ephemeral=True);
    guild = interaction.guild; author = interaction.user
    if user == author: await interaction.followup.send("不能禁言自己。", ephemeral=True); return
    if isinstance(author, discord.Member) and user.top_role >= author.top_role and author != guild.owner: await interaction.followup.send("無法禁言更高層級用戶。", ephemeral=True); return
    if duration_minutes < 0: await interaction.followup.send("時間不能為負。", ephemeral=True); return
    max_duration = datetime.timedelta(days=28)
    if duration_minutes == 0:
        timeout_duration = max_duration; duration_text = "永久 (最長28天)"
    else:
        timeout_duration = datetime.timedelta(minutes=duration_minutes)
        duration_text = f"{duration_minutes} 分鐘"
        if timeout_duration > max_duration: timeout_duration = max_duration; duration_text += " (限制為28天)"
    try: await user.timeout(timeout_duration, reason=f"Muted by {author}: {reason}"); await interaction.followup.send(f"✅ {user.mention} 已被禁言 {duration_text}。原因: {reason}", ephemeral=False)
    except Exception as e: print(f"Err /管理 禁言: {e}"); await interaction.followup.send(f"⚙️ 禁言操作失敗: {e}", ephemeral=True)

@manage_group.command(name="踢出", description="將成員踢出伺服器 (需踢出成員權限)")
@app_commands.describe(user="要踢出的用戶", reason="原因(可選)")
@app_commands.checks.has_permissions(kick_members=True)
@app_commands.checks.bot_has_permissions(kick_members=True)
async def manage_kick(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    await interaction.response.defer(ephemeral=True);
    guild = interaction.guild; author = interaction.user
    if user == author: await interaction.followup.send("不能踢出自己。", ephemeral=True); return
    if isinstance(author, discord.Member) and user.top_role >= author.top_role and author != guild.owner: await interaction.followup.send("無法踢出更高層級用戶。", ephemeral=True); return
    if user == guild.owner: await interaction.followup.send("不能踢出擁有者。", ephemeral=True); return
    if user == guild.me: await interaction.followup.send("不能踢出我自己。", ephemeral=True); return
    if user.top_role >= guild.me.top_role and guild.me != guild.owner: await interaction.followup.send("❌ Bot無法踢出更高層級用戶。", ephemeral=True); return
    try:
        dm_reason = f"你已被踢出伺服器 **{guild.name}**。原因: {reason}"
        try: await user.send(dm_reason); print(f"   Sent kick DM to {user.name}.")
        except discord.Forbidden: print(f"   Could not send kick DM to {user.name} (Forbidden).")
        except Exception as dm_err: print(f"   Error sending kick DM to {user.name}: {dm_err}")
        await user.kick(reason=f"Kicked by {author}: {reason}"); print(f"   Kicked {user.name}.")
        await interaction.followup.send(f"👢 {user.mention} (`{user}`) 已被踢出伺服器。原因: {reason}", ephemeral=False)
    except discord.Forbidden: print(f"Err /管理 踢出: Bot lacks permission/hierarchy to kick {user.name}."); await interaction.followup.send(f"⚙️ 踢出操作失敗：機器人權限不足或層級不夠。", ephemeral=True)
    except discord.HTTPException as http_err: print(f"Err /管理 踢出 (HTTP): {http_err}"); await interaction.followup.send(f"⚙️ 踢出操作時發生網路錯誤: {http_err}", ephemeral=True)
    except Exception as e: print(f"Err /管理 踢出: {e}"); await interaction.followup.send(f"⚙️ 踢出操作失敗: {e}", ephemeral=True)

@manage_group.command(name="封禁", description="將成員永久封禁 (需封禁成員權限)")
@app_commands.describe(user_id="要封禁的用戶ID (防止誤封)", reason="原因(可選)")
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.checks.bot_has_permissions(ban_members=True)
async def manage_ban(interaction: discord.Interaction, user_id: str, reason: str = "未指定原因"):
    await interaction.response.defer(ephemeral=True);
    guild = interaction.guild; author = interaction.user
    try: target_user_id = int(user_id);
    except ValueError: await interaction.followup.send("無效的用戶 ID。", ephemeral=True); return
    if target_user_id == author.id: await interaction.followup.send("不能封禁自己。", ephemeral=True); return
    if target_user_id == guild.owner_id: await interaction.followup.send("不能封禁擁有者。", ephemeral=True); return
    if target_user_id == bot.user.id: await interaction.followup.send("不能封禁我自己。", ephemeral=True); return
    target_member = guild.get_member(target_user_id)
    if target_member:
        if isinstance(author, discord.Member) and target_member.top_role >= author.top_role and author != guild.owner: await interaction.followup.send("無法封禁更高層級用戶。", ephemeral=True); return
        if target_member.top_role >= guild.me.top_role and guild.me != guild.owner: await interaction.followup.send("❌ Bot無法封禁更高層級用戶。", ephemeral=True); return
    try: user_to_ban = await bot.fetch_user(target_user_id); await guild.ban(user_to_ban, reason=f"Banned by {author}: {reason}", delete_message_days=0); await interaction.followup.send(f"🚫 用戶 `{user_to_ban}` (ID: {target_user_id}) 已被永久封禁。原因: {reason}", ephemeral=False)
    except discord.NotFound: await interaction.followup.send("找不到用戶。", ephemeral=True)
    except Exception as e: print(f"Err /管理 封禁: {e}"); await interaction.followup.send(f"⚙️ 封禁操作失敗: {e}", ephemeral=True)

@manage_group.command(name="解封", description="解除成員的封禁 (需封禁成員權限)")
@app_commands.describe(user_id="要解除封禁的用戶ID", reason="原因(可選)")
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.checks.bot_has_permissions(ban_members=True)
async def manage_unban(interaction: discord.Interaction, user_id: str, reason: str = "未指定原因"):
    await interaction.response.defer(ephemeral=True);
    guild = interaction.guild; author = interaction.user
    try: target_user_id = int(user_id);
    except ValueError: await interaction.followup.send("無效的用戶 ID。", ephemeral=True); return
    try: ban_entry = await guild.fetch_ban(discord.Object(id=target_user_id)); user_to_unban = ban_entry.user; await guild.unban(user_to_unban, reason=f"Unbanned by {author}: {reason}"); await interaction.followup.send(f"✅ 用戶 `{user_to_unban}` (ID: {target_user_id}) 已被解除封禁。原因: {reason}", ephemeral=False)
    except discord.NotFound: await interaction.followup.send("找不到封禁記錄。", ephemeral=True)
    except Exception as e: print(f"Err /管理 解封: {e}"); await interaction.followup.send(f"⚙️ 解封操作失敗: {e}", ephemeral=True)

@manage_group.command(name="人數頻道", description="創建/更新顯示伺服器人數的語音頻道 (需管理頻道)")
@app_commands.describe(channel_name_template="頻道名稱模板 (用 '{count}' 代表人數)")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.checks.bot_has_permissions(manage_channels=True)
async def manage_member_count_channel(interaction: discord.Interaction, channel_name_template: str = "成員人數: {count}"):
    await interaction.response.defer(ephemeral=True);
    guild = interaction.guild
    existing_channel_id = get_setting(guild.id, "member_count_channel_id")
    existing_channel = guild.get_channel(existing_channel_id) if existing_channel_id else None
    member_count = guild.member_count; new_name = channel_name_template.format(count=member_count)
    if existing_channel and isinstance(existing_channel, discord.VoiceChannel): # Update
        try:
            if existing_channel.name != new_name: await existing_channel.edit(name=new_name, reason="Update count"); await interaction.followup.send(f"✅ 更新頻道 {existing_channel.mention} 名稱為 `{new_name}`。", ephemeral=True)
            else: await interaction.followup.send(f"ℹ️ 頻道 {existing_channel.mention} 無需更新。", ephemeral=True)
            set_setting(guild.id, "member_count_template", channel_name_template)
        except Exception as e: print(f"Err upd count: {e}"); await interaction.followup.send(f"⚙️ 更新時出錯: {e}", ephemeral=True)
    else: # Create
        try:
            overwrites = { guild.default_role: discord.PermissionOverwrite(connect=False), guild.me: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True) }
            new_channel = await guild.create_voice_channel(name=new_name, overwrites=overwrites, reason="Create count channel")
            set_setting(guild.id, "member_count_channel_id", new_channel.id); set_setting(guild.id, "member_count_template", channel_name_template)
            await interaction.followup.send(f"✅ 已創建頻道 {new_channel.mention}。", ephemeral=True)
        except Exception as e: print(f"Err create count: {e}"); await interaction.followup.send(f"⚙️ 創建時出錯: {e}", ephemeral=True)

# --- Temporary Voice Channel Command Group ---
voice_group = app_commands.Group(name="語音", description="臨時語音頻道相關指令")

@voice_group.command(name="設定母頻道", description="設定用於創建臨時語音頻道的母頻道 (需管理頻道)")
@app_commands.describe(master_channel="用戶加入此頻道以創建新頻道", category="(可選) 將臨時頻道創建在哪個分類下")
@app_commands.checks.has_permissions(manage_channels=True, manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_channels=True, move_members=True)
async def voice_set_master(interaction: discord.Interaction, master_channel: discord.VoiceChannel, category: Optional[discord.CategoryChannel] = None):
    guild_id = interaction.guild_id; await interaction.response.defer(ephemeral=True);
    set_setting(guild_id, "master_channel_id", master_channel.id)
    set_setting(guild_id, "category_id", category.id if category else None)
    cat_name = f" 在分類 '{category.name}' 下" if category else ""
    await interaction.followup.send(f"✅ 臨時語音母頻道已設為 {master_channel.mention}{cat_name}。", ephemeral=True)
    print(f"[TempVC] Guild {guild_id}: Master VC set to {master_channel.id}, Category: {category.id if category else None}")

# --- Helper to check if user is the owner of the temp VC ---
def is_temp_vc_owner(interaction: discord.Interaction) -> bool:
    vc = interaction.user.voice.channel if interaction.user.voice else None
    if vc and vc.id in temp_vc_owners and temp_vc_owners[vc.id] == interaction.user.id: return True
    return False

@voice_group.command(name="設定權限", description="設定你臨時語音頻道的權限 (限頻道主)")
@app_commands.describe( target="要設定權限的用戶或身份組", allow_connect="允許連接?", allow_speak="允許說話?", allow_stream="允許直播?", allow_video="允許開啟視訊?" )
async def voice_set_perms(interaction: discord.Interaction, target: Union[discord.Member, discord.Role], allow_connect: Optional[bool] = None, allow_speak: Optional[bool] = None, allow_stream: Optional[bool] = None, allow_video: Optional[bool] = None):
    await interaction.response.defer(ephemeral=True);
    user_vc = interaction.user.voice.channel if interaction.user.voice else None
    if not user_vc or user_vc.id not in temp_vc_owners or temp_vc_owners[user_vc.id] != interaction.user.id: await interaction.followup.send("❌ 僅限在你創建的臨時頻道中使用。", ephemeral=True); return
    overwrites = user_vc.overwrites_for(target); perms_changed = []
    if allow_connect is not None: overwrites.connect = allow_connect; perms_changed.append(f"連接={allow_connect}")
    if allow_speak is not None: overwrites.speak = allow_speak; perms_changed.append(f"說話={allow_speak}")
    if allow_stream is not None: overwrites.stream = allow_stream; perms_changed.append(f"直播={allow_stream}")
    if allow_video is not None: overwrites.video = allow_video; perms_changed.append(f"視訊={allow_video}")
    if not perms_changed: await interaction.followup.send("⚠️ 未指定要修改的權限。", ephemeral=True); return
    try: await user_vc.set_permissions(target, overwrite=overwrites, reason=f"由房主 {interaction.user} 設定"); await interaction.followup.send(f"✅ 已更新 {target.mention} 在 {user_vc.mention} 的權限: {', '.join(perms_changed)}", ephemeral=True)
    except Exception as e: print(f"Err /語音 設定權限: {e}"); await interaction.followup.send(f"⚙️ 設定權限時出錯: {e}", ephemeral=True)

@voice_group.command(name="轉讓", description="將你的臨時語音頻道所有權轉讓給他人 (限頻道主)")
@app_commands.describe(new_owner="要接收所有權的新用戶 (需在頻道內)")
async def voice_transfer(interaction: discord.Interaction, new_owner: discord.Member):
    await interaction.response.defer(ephemeral=True);
    user = interaction.user; user_vc = user.voice.channel if user.voice else None
    if not user_vc or user_vc.id not in temp_vc_owners or temp_vc_owners[user_vc.id] != user.id: await interaction.followup.send("❌ 僅限在你創建的臨時頻道中使用。", ephemeral=True); return
    if new_owner.bot: await interaction.followup.send("❌ 不能轉讓給機器人。", ephemeral=True); return
    if new_owner == user: await interaction.followup.send("❌ 不能轉讓給自己。", ephemeral=True); return
    if not new_owner.voice or new_owner.voice.channel != user_vc: await interaction.followup.send(f"❌ {new_owner.mention} 必須在頻道內。", ephemeral=True); return
    try:
        owner_overwrites = discord.PermissionOverwrite(manage_channels=True, manage_permissions=True, move_members=True)
        old_owner_overwrites = discord.PermissionOverwrite() # Reset old owner perms
        await user_vc.set_permissions(new_owner, overwrite=owner_overwrites, reason=f"所有權由 {user.name} 轉讓")
        await user_vc.set_permissions(user, overwrite=old_owner_overwrites, reason=f"所有權轉讓給 {new_owner.name}")
        temp_vc_owners[user_vc.id] = new_owner.id
        await interaction.followup.send(f"✅ 已將 {user_vc.mention} 所有權轉讓給 {new_owner.mention}！", ephemeral=False)
        print(f"[TempVC] Ownership {user_vc.id}: {user.id} -> {new_owner.id}")
    except Exception as e: print(f"Err /語音 轉讓: {e}"); await interaction.followup.send(f"⚙️ 轉讓時出錯: {e}", ephemeral=True)

@voice_group.command(name="房主", description="如果原房主不在，嘗試獲取臨時語音房主權限")
async def voice_claim(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True);
    user = interaction.user; user_vc = user.voice.channel if user.voice else None
    if not user_vc or user_vc.id not in temp_vc_created: await interaction.followup.send("❌ 僅限在臨時頻道中使用。", ephemeral=True); return
    current_owner_id = temp_vc_owners.get(user_vc.id)
    if current_owner_id == user.id: await interaction.followup.send("ℹ️ 你已是房主。", ephemeral=True); return
    owner_is_present = False
    if current_owner_id:
        current_owner = interaction.guild.get_member(current_owner_id)
        if current_owner and current_owner.voice and current_owner.voice.channel == user_vc: owner_is_present = True
    if owner_is_present: await interaction.followup.send(f"❌ 無法獲取，房主 {current_owner.mention} 仍在頻道中。", ephemeral=True); return
    try:
        owner_overwrites = discord.PermissionOverwrite(manage_channels=True, manage_permissions=True, move_members=True)
        await user_vc.set_permissions(user, overwrite=owner_overwrites, reason=f"由 {user.name} 獲取房主")
        if current_owner_id: # Reset old owner perms if they exist
             old_owner = interaction.guild.get_member(current_owner_id)
             if old_owner:
                  try: await user_vc.set_permissions(old_owner, overwrite=None, reason="原房主權限重設")
                  except Exception as e: print(f"Could not reset perms for old owner {current_owner_id}: {e}")
        temp_vc_owners[user_vc.id] = user.id
        await interaction.followup.send(f"✅ 你已獲取頻道 {user_vc.mention} 的房主權限！", ephemeral=False)
        print(f"[TempVC] Ownership {user_vc.id} claimed by {user.id} (Old: {current_owner_id})")
    except Exception as e: print(f"Err /語音 房主: {e}"); await interaction.followup.send(f"⚙️ 獲取房主時出錯: {e}", ephemeral=True)


# --- Add the command groups to the bot tree ---
bot.tree.add_command(manage_group)
bot.tree.add_command(voice_group)

# --- Run the Bot ---
if __name__ == "__main__":
    print("Starting bot...")
    try:
        bot.run(BOT_TOKEN)
    except discord.LoginFailure: print("❌ FATAL ERROR: Login failed. Invalid DISCORD_BOT_TOKEN.")
    except discord.PrivilegedIntentsRequired: print("❌ FATAL ERROR: Privileged Intents required but not enabled in Developer Portal.")
    except Exception as e: print(f"❌ FATAL ERROR during startup: {e}")

# --- End of Complete Code ---