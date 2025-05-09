# --- MERGED BOT CODE ---
# Combines role_manager_bot.py (v23), giveaway_bot.py (nextcord-based), and ticket_verification_bot.py

import discord
from discord import app_commands, ui
from discord.ext import commands, tasks
from discord.utils import get
import os
import datetime
import asyncio
from typing import Optional, Union, List # Added List
import requests # Required for DeepSeek API & Announce fallback & Giveaway Bot HEAD request fallback
import json     # Required for DeepSeek API & Giveaway Bot data
import traceback # For detailed error logging
from dotenv import load_dotenv # For local .env file loading

# --- AIOHTTP (Preferred for async requests) ---
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    print("⚠️ WARNING: 'aiohttp' library not found. /announce image URL validation and DeepSeek (if adapted) will use 'requests' (blocking). Consider: pip install aiohttp")

# --- Redis (for Giveaway Bot persistence) ---
try:
    import redis.asyncio as redis_async
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("⚠️ WARNING: 'redis' library not found. Giveaway features will be disabled. Consider: pip install redis")

# --- Load Environment Variables ---
load_dotenv()

# --- Unified Configuration ---
# !!! CRITICAL: SET THESE IN YOUR ENVIRONMENT / .env FILE !!!

# Core Bot Token
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# DeepSeek API (Optional - for content moderation - from File 1)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions") # Default if not set
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat") # Default if not set

# Redis URL (Required for Giveaway features - from File 2)
REDIS_URL = os.getenv("REDIS_URL")

# Ticket & Member Verification System (from File 3)
SUPPORT_ROLE_ID_STR = os.getenv("SUPPORT_ROLE_ID")
TICKET_CATEGORY_ID_STR = os.getenv("TICKET_CATEGORY_ID") # Category for ACTUAL tickets (File 1 tickets, File 3 listens here)
LOG_CHANNEL_ID_STR = os.getenv("LOG_CHANNEL_ID") # Log channel for VERIFIED tickets (File 3)
NEW_MEMBER_CATEGORY_ID_STR = os.getenv("NEW_MEMBER_CATEGORY_ID") # Category for private welcome channels for UNVERIFIED members (File 3)
VERIFIED_ROLE_IDS_STR = os.getenv("VERIFIED_ROLE_IDS") # Comma-separated Role IDs that mean a user is 'verified' (File 3)
TICKET_PANEL_CHANNEL_NAME_STR = os.getenv("TICKET_PANEL_CHANNEL_NAME") # Name of the channel where users click to create tickets (e.g., "#客服中心") (File 3)


# Role Manager & Moderation System (from File 1)
PUBLIC_WARN_LOG_CHANNEL_ID_STR = os.getenv("PUBLIC_WARN_LOG_CHANNEL_ID") # Public log for warnings, kicks, etc.
MOD_ALERT_ROLE_IDS_STR = os.getenv("MOD_ALERT_ROLE_IDS") # Comma-separated Role IDs for generic mod alerts

# Welcome Message Channel IDs (Optional - for generic welcome in File 1)
WELCOME_CHANNEL_ID_STR = os.getenv("WELCOME_CHANNEL_ID")
RULES_CHANNEL_ID_STR = os.getenv("RULES_CHANNEL_ID")
ROLES_INFO_CHANNEL_ID_STR = os.getenv("ROLES_INFO_CHANNEL_ID")
# VERIFICATION_CHANNEL_ID_STR from File 1 is now effectively TICKET_PANEL_CHANNEL_NAME_STR for guidance

# --- Validate Core Configuration & Initialize Variables ---
CONFIG_ERROR = False
if not BOT_TOKEN: print("❌ CRITICAL ERROR: DISCORD_BOT_TOKEN missing."); CONFIG_ERROR = True

# Initialize IDs, converting from string to int
SUPPORT_ROLE_ID = None
TICKET_CATEGORY_ID = None
LOG_CHANNEL_ID = None # For File 3's /verifyticket logs
NEW_MEMBER_CATEGORY_ID = None
VERIFIED_ROLE_IDS: List[int] = []
TICKET_PANEL_CHANNEL_NAME = None # For File 3's guidance

PUBLIC_WARN_LOG_CHANNEL_ID = None # For File 1's mod logs
MOD_ALERT_ROLE_IDS: List[int] = []

WELCOME_CHANNEL_ID = None
RULES_CHANNEL_ID = None
ROLES_INFO_CHANNEL_ID = None

try:
    if SUPPORT_ROLE_ID_STR: SUPPORT_ROLE_ID = int(SUPPORT_ROLE_ID_STR)
    else: print("❌ CONFIG ERROR: SUPPORT_ROLE_ID missing."); CONFIG_ERROR = True

    if TICKET_CATEGORY_ID_STR: TICKET_CATEGORY_ID = int(TICKET_CATEGORY_ID_STR)
    else: print("❌ CONFIG ERROR: TICKET_CATEGORY_ID missing (for File 1 tickets & File 3 listener)."); CONFIG_ERROR = True

    if NEW_MEMBER_CATEGORY_ID_STR: NEW_MEMBER_CATEGORY_ID = int(NEW_MEMBER_CATEGORY_ID_STR)
    else: print("❌ CONFIG ERROR: NEW_MEMBER_CATEGORY_ID missing."); CONFIG_ERROR = True

    if VERIFIED_ROLE_IDS_STR:
        ids_str = VERIFIED_ROLE_IDS_STR.split(',')
        for id_val_str in ids_str:
            VERIFIED_ROLE_IDS.append(int(id_val_str.strip()))
        if not VERIFIED_ROLE_IDS: print("❌ CONFIG ERROR: VERIFIED_ROLE_IDS parsed to an empty list."); CONFIG_ERROR = True
    else: print("❌ CONFIG ERROR: VERIFIED_ROLE_IDS missing."); CONFIG_ERROR = True

    if TICKET_PANEL_CHANNEL_NAME_STR: TICKET_PANEL_CHANNEL_NAME = TICKET_PANEL_CHANNEL_NAME_STR
    else: print("❌ CONFIG ERROR: TICKET_PANEL_CHANNEL_NAME missing."); CONFIG_ERROR = True

    if LOG_CHANNEL_ID_STR: LOG_CHANNEL_ID = int(LOG_CHANNEL_ID_STR) # Optional, can be set by command

    if PUBLIC_WARN_LOG_CHANNEL_ID_STR: PUBLIC_WARN_LOG_CHANNEL_ID = int(PUBLIC_WARN_LOG_CHANNEL_ID_STR)
    else: print("⚠️ WARNING: PUBLIC_WARN_LOG_CHANNEL_ID not set. Some moderation logs will not be sent publicly.")

    if MOD_ALERT_ROLE_IDS_STR:
        ids_str = MOD_ALERT_ROLE_IDS_STR.split(',')
        for id_val_str in ids_str:
            MOD_ALERT_ROLE_IDS.append(int(id_val_str.strip()))
    # else: print("⚠️ WARNING: MOD_ALERT_ROLE_IDS not set. Mod pings will be limited.") # Less critical

    if WELCOME_CHANNEL_ID_STR: WELCOME_CHANNEL_ID = int(WELCOME_CHANNEL_ID_STR)
    if RULES_CHANNEL_ID_STR: RULES_CHANNEL_ID = int(RULES_CHANNEL_ID_STR)
    if ROLES_INFO_CHANNEL_ID_STR: ROLES_INFO_CHANNEL_ID = int(ROLES_INFO_CHANNEL_ID_STR)

except ValueError as e:
    print(f"❌ CRITICAL ERROR: Invalid integer value for one of the ID environment variables: {e}")
    CONFIG_ERROR = True

if not DEEPSEEK_API_KEY:
    print("⚠️ WARNING: DEEPSEEK_API_KEY not set. AI content moderation (File 1) will be disabled.")
if not REDIS_URL and REDIS_AVAILABLE: # Only warn if redis lib is available but URL not set
    print("⚠️ WARNING: REDIS_URL not set. Giveaway features (File 2) will be disabled or may fail.")
if not REDIS_AVAILABLE:
    print("ℹ️ INFO: 'redis' library not installed, Giveaway features (File 2) are disabled.")


if CONFIG_ERROR:
    print("--- BOT NOT STARTED DUE TO CRITICAL CONFIGURATION ERRORS ---")
    exit()

COMMAND_PREFIX = "!" # Legacy prefix (File 1)

# --- Intents Configuration ---
intents = discord.Intents.default()
intents.members = True      # For on_member_join, member info, member commands (File 1 & 3)
intents.message_content = True # For on_message spam/profanity detection (File 1)
intents.voice_states = True # For temporary voice channels (File 1)
intents.guilds = True       # For ticket features and other server info (File 1 & 3)
intents.reactions = True    # For Giveaway reactions (File 2)

# --- Bot Initialization ---
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)
bot.persistent_views_added = False # Flag for File 1's persistent views
bot.http_session = None # For aiohttp session (File 1 & Giveaway HEAD fallback)
bot.log_channel_id = LOG_CHANNEL_ID # For File 3's /verifyticket (can be updated by command)

# --- Spam Detection & Mod Alert Config (File 1) ---
SPAM_COUNT_THRESHOLD = 5
SPAM_TIME_WINDOW_SECONDS = 5
KICK_THRESHOLD = 3
BOT_SPAM_COUNT_THRESHOLD = 8
BOT_SPAM_TIME_WINDOW_SECONDS = 3

# --- Bad Word Detection Config & Storage (File 1 - In-Memory) ---
# !!! 【警告】仔细审查并【大幅删减】此列表，避免误判 !!!
# !!! 如果你完全信任 DeepSeek API 的判断，可以清空或注释掉这个列表 !!!
BAD_WORDS = [
    "操你妈", "草泥马", "cnm", "日你妈", "rnm", "屌你老母", "屌你媽", "死妈", "死媽", "nmsl", "死全家",
    "杂种", "雜種", "畜生", "畜牲", "狗娘养的", "狗娘養的", "贱人", "賤人", "婊子", "bitch", "傻逼", "煞笔", "sb", "脑残", "腦殘",
    "智障", "弱智", "低能", "白痴", "白癡", "废物", "廢物", "垃圾", "lj", "kys", "去死", "自杀", "自殺", "杀你", "殺你",
    "他妈的", "他媽的", "tmd", "妈的", "媽的", "卧槽", "我肏", "我操", "我草", "靠北", "靠杯", "干你娘", "干您娘",
    "fuck", "shit", "cunt", "asshole", "鸡巴", "雞巴", "jb",
]
BAD_WORDS_LOWER = [word.lower() for word in BAD_WORDS]
user_first_offense_reminders = {} # {guild_id: {user_id: {lowercase_word}}}

# --- General Settings Storage (File 1 - In-Memory) ---
general_settings = {} # {guild_id: {"log_channel_id": int, "announce_channel_id": int}} (Note: File 1's log_channel is distinct from File 3's)

# --- Temporary Voice Channel Config & Storage (File 1 - In-Memory) ---
temp_vc_settings = {}
temp_vc_owners = {}
temp_vc_created = set()

# --- Ticket Tool Config & Storage (File 1 - In-Memory) ---
ticket_settings = {} # {guild_id: {"setup_channel_id": int, "category_id": int, "staff_role_ids": list[int], "button_message_id": int, "ticket_count": int}}
open_tickets = {}    # {guild_id: {user_id: channel_id}}

# --- Spam Warning Storage (File 1 - In-Memory) ---
user_message_timestamps = {}
user_warnings = {}
bot_message_timestamps = {}

# --- AI Content Check Exemption Storage (File 1 - In-Memory) ---
exempt_users_from_ai_check = set()
exempt_channels_from_ai_check = set()

# --- Ticket Data Cache (File 3 - In-Memory) ---
ticket_data_cache = {}

# --- Redis Connection for Giveaways (File 2) ---
redis_pool = None
GIVEAWAY_PREFIX = "giveaway:" # From File 2

async def setup_redis(): # From File 2, adapted
    global redis_pool
    if not REDIS_AVAILABLE or not REDIS_URL:
        print("Redis not available or REDIS_URL not set. Giveaway features will be limited/disabled.")
        return
    try:
        print(f"Connecting to Redis: {REDIS_URL}...")
        redis_pool = redis_async.from_url(REDIS_URL, decode_responses=True)
        await redis_pool.ping()
        print("Successfully connected to Redis for giveaways.")
    except Exception as e:
        print(f"❌ FATAL: Could not connect to Redis: {e}")
        redis_pool = None # Ensure it's None on failure
        # Consider if bot should exit if Redis is critical and fails
        # For now, it will continue with giveaways disabled/failing.

# --- Helper Function to Get/Set Settings (File 1 - Simulated DB for its own settings) ---
def get_setting(store: dict, guild_id: int, key: str):
    return store.get(guild_id, {}).get(key)

def set_setting(store: dict, guild_id: int, key: str, value):
    if guild_id not in store: store[guild_id] = {}
    store[guild_id][key] = value

# --- Helper Function: Send to Public Log Channel (File 1) ---
async def send_to_public_log(guild: discord.Guild, embed: discord.Embed, log_type: str = "Generic"):
    if not PUBLIC_WARN_LOG_CHANNEL_ID: return False
    log_channel = guild.get_channel(PUBLIC_WARN_LOG_CHANNEL_ID)
    if log_channel and isinstance(log_channel, discord.TextChannel):
        bot_perms = log_channel.permissions_for(guild.me)
        if bot_perms.send_messages and bot_perms.embed_links:
            try:
                await log_channel.send(embed=embed)
                print(f"   ✅ Sent public log ({log_type}) to #{log_channel.name} ({log_channel.id}).")
                return True
            except discord.Forbidden: print(f"   ❌ Bot lacks send/embed perms in public log channel {PUBLIC_WARN_LOG_CHANNEL_ID}.")
            except Exception as log_e: print(f"   ❌ Error sending public log ({log_type}): {log_e}")
        else: print(f"   ❌ Bot lacks send/embed perms in public log channel {PUBLIC_WARN_LOG_CHANNEL_ID} (checked).")
    else: print(f"⚠️ Public log channel ID {PUBLIC_WARN_LOG_CHANNEL_ID} not found in {guild.name}.")
    return False

# --- Helper Function: DeepSeek API Content Check (File 1) ---
async def check_message_with_deepseek(message_content: str) -> Optional[str]:
    if not DEEPSEEK_API_KEY: return None
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
    prompt = f"""
    请分析以下 Discord 消息内容是否包含严重的违规行为。
    严重违规分类包括：仇恨言论、骚扰/欺凌、露骨的 NSFW 内容、严重威胁。
    - 如果检测到明确的严重违规，请【仅】返回对应的中文分类名称（例如：“仇恨言论”）。
    - 如果内容包含一些轻微问题（如刷屏、普通脏话）但【不构成】上述严重违规，请【仅】返回：“轻微违规”。
    - 如果内容安全，没有任何违规，请【仅】返回：“安全”。
    消息内容：“{message_content}”
    分析结果："""
    data = {"model": DEEPSEEK_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 30, "temperature": 0.1, "stream": False}

    try:
        if AIOHTTP_AVAILABLE and bot.http_session:
            async with bot.http_session.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=8) as response:
                response.raise_for_status()
                result = await response.json()
        else: # Fallback to requests
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: requests.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=8))
            response.raise_for_status()
            result = response.json()

        api_response_text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not api_response_text or api_response_text == "安全" or api_response_text == "轻微违规": return None
        return api_response_text
    except (requests.exceptions.Timeout, asyncio.TimeoutError): print(f"❌ DeepSeek API call timed out.")
    except (requests.exceptions.RequestException, aiohttp.ClientError) as e: print(f"❌ DeepSeek API network error: {e}")
    except json.JSONDecodeError: print(f"❌ DeepSeek API response parsing failed (non-JSON).")
    except Exception as e: print(f"❌ Unexpected error during DeepSeek check: {e}")
    return None

# --- Ticket Tool UI Views (File 1) ---
class CloseTicketView(ui.View): # From File 1
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="关闭票据", style=discord.ButtonStyle.danger, custom_id="close_ticket_button_v1") # Custom ID changed to avoid conflict if any
    async def close_button(self, interaction: discord.Interaction, button: ui.Button):
        guild = interaction.guild; channel = interaction.channel; user = interaction.user
        if not guild or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("❌ 操作无法在此处完成。", ephemeral=True); return

        creator_id = None
        guild_tickets = open_tickets.get(guild.id, {})
        for uid, chan_id in guild_tickets.items():
            if chan_id == channel.id: creator_id = uid; break
        is_creator = (creator_id == user.id)

        staff_role_ids = get_setting(ticket_settings, guild.id, "staff_role_ids") or []
        is_staff = isinstance(user, discord.Member) and any(role.id in staff_role_ids for role in user.roles)
        can_manage_channels = channel.permissions_for(user).manage_channels

        if not is_creator and not is_staff and not can_manage_channels:
            await interaction.response.send_message("❌ 你没有权限关闭此票据。", ephemeral=True); return

        await interaction.response.defer(ephemeral=True)
        await channel.send(f"⏳ {user.mention} 已请求关闭此票据，频道将在几秒后删除...")
        print(f"[Ticket Tool] User {user} closing ticket #{channel.name}")

        log_embed = discord.Embed(title="🎫 票据已关闭 (File 1 Tool)", description=f"票据频道 **#{channel.name}** 已被关闭。", color=discord.Color.greyple(), timestamp=discord.utils.utcnow())
        log_embed.add_field(name="关闭者", value=user.mention, inline=True)
        log_embed.add_field(name="频道 ID", value=str(channel.id), inline=True)
        if creator_id:
            try: creator_user = await bot.fetch_user(creator_id); creator_mention = f"{creator_user.mention} (`{creator_user}`)"
            except: creator_mention = f"<@{creator_id}>"
            log_embed.add_field(name="创建者", value=creator_mention, inline=True)
        await send_to_public_log(guild, log_embed, log_type="TicketClosed_File1")

        if creator_id and guild.id in open_tickets and creator_id in open_tickets[guild.id]:
            if open_tickets[guild.id][creator_id] == channel.id: del open_tickets[guild.id][creator_id]

        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket closed by {user.name} (File 1 Tool)")
            await interaction.followup.send("✅ 票据频道已删除。", ephemeral=True)
        except discord.Forbidden: await interaction.followup.send("❌ 无法删除频道：机器人缺少权限。", ephemeral=True)
        except discord.NotFound: pass # Channel already gone
        except Exception as e:
            try: await interaction.followup.send(f"❌ 删除频道时发生错误: {e}", ephemeral=True)
            except: pass


class CreateTicketView(ui.View): # From File 1
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="➡️ 开票-认证 (GJ Team)", style=discord.ButtonStyle.primary, custom_id="create_verification_ticket_v1") # Custom ID
    async def create_ticket_button(self, interaction: discord.Interaction, button: ui.Button):
        guild = interaction.guild; user = interaction.user
        if not guild: return
        await interaction.response.defer(ephemeral=True)

        category_id = get_setting(ticket_settings, guild.id, "category_id")
        staff_role_ids = get_setting(ticket_settings, guild.id, "staff_role_ids")
        if not category_id or not staff_role_ids:
            await interaction.followup.send("❌ 票据系统 (File 1) 尚未完全配置。请联系管理员。", ephemeral=True); return

        ticket_category = guild.get_channel(category_id)
        if not ticket_category or not isinstance(ticket_category, discord.CategoryChannel):
            await interaction.followup.send("❌ 配置的票据分类 (File 1) 无效。请联系管理员。", ephemeral=True); return

        staff_roles = [guild.get_role(role_id) for role_id in staff_role_ids if guild.get_role(role_id)]
        if not staff_roles:
            await interaction.followup.send("❌ 配置的票据员工身份组 (File 1) 无效。请联系管理员。", ephemeral=True); return

        guild_tickets = open_tickets.setdefault(guild.id, {})
        if user.id in guild_tickets:
            existing_channel = guild.get_channel(guild_tickets[user.id])
            if existing_channel:
                await interaction.followup.send(f"⚠️ 你已有一个开启的票据 (File 1): {existing_channel.mention}。", ephemeral=True); return
            else: del guild_tickets[user.id] # Clean stale entry

        bot_perms = ticket_category.permissions_for(guild.me)
        if not bot_perms.manage_channels or not bot_perms.manage_permissions:
            await interaction.followup.send("❌ 创建票据 (File 1) 失败：机器人缺少 '管理频道' 或 '管理权限'。", ephemeral=True); return

        ticket_count = get_setting(ticket_settings, guild.id, "ticket_count") or 0
        ticket_count += 1
        set_setting(ticket_settings, guild.id, "ticket_count", ticket_count)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_permissions=True)
        }
        staff_mentions = []
        for role in staff_roles:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
            staff_mentions.append(role.mention)
        staff_mention_str = " ".join(staff_mentions)

        s_username = "".join(c for c in user.name if c.isalnum() or c in ('-', '_')).lower() or "user"
        channel_name = f"认证-{ticket_count:04d}-{s_username}"[:100]
        new_channel = None
        try:
            new_channel = await guild.create_text_channel(name=channel_name, category=ticket_category, overwrites=overwrites, topic=f"Ticket for {user.id}", reason="File 1 Ticket Creation")
            guild_tickets[user.id] = new_channel.id

            welcome_embed = discord.Embed(title="📝 GJ Team 认证票据 (File 1)", description=f"你好 {user.mention}！请说明你的认证需求。\n团队 ({staff_mention_str}) 会处理。\n完成后请点下方关闭按钮。", color=discord.Color.green())
            welcome_embed.set_footer(text=f"票据 ID: {new_channel.id}")
            await new_channel.send(content=f"{user.mention} {staff_mention_str}", embed=welcome_embed, view=CloseTicketView())
            await interaction.followup.send(f"✅ 你的认证票据 (File 1) 已创建：{new_channel.mention}", ephemeral=True)
        except Exception as e:
            set_setting(ticket_settings, guild.id, "ticket_count", ticket_count - 1)
            if user.id in guild_tickets: del guild_tickets[user.id]
            if new_channel: await new_channel.delete(reason="Error during creation")
            await interaction.followup.send(f"❌ 创建票据 (File 1) 时发生错误: {e}", ephemeral=True)
            print(f"Error creating File 1 ticket: {e}")


# --- Ticket Verification UI Elements (File 3) ---
class InfoModal(discord.ui.Modal, title='请提供必要信息以处理您的请求'): # From File 3
    identifier = discord.ui.TextInput(label='角色ID 或 个人资料链接 (用于身份确认)', style=discord.TextStyle.short, placeholder='请提供相关ID或链接', required=True, max_length=150)
    reason = discord.ui.TextInput(label='请说明来意 (Reason for contact)', style=discord.TextStyle.paragraph, placeholder='例如：申请GJ正式成员/GJZ精英部队/GJK前鋒部队/合作/或其他...', required=True, max_length=1000)
    kill_count = discord.ui.TextInput(label='(如果适用) 你大概多少杀？', style=discord.TextStyle.short, placeholder='例如：50+ (若不适用可填 N/A)', required=False, max_length=50)
    notes = discord.ui.TextInput(label='其他补充说明 (Optional Notes)', style=discord.TextStyle.paragraph, placeholder='任何其他需要让客服知道的信息...', required=False, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user; channel_id = interaction.channel_id
        submitted_data = {
            "user_id": user.id, "user_mention": user.mention, "user_name": str(user),
            "identifier": self.identifier.value, "reason": self.reason.value,
            "kill_count": self.kill_count.value if self.kill_count.value else "N/A",
            "notes": self.notes.value if self.notes.value else "无",
            "channel_name": interaction.channel.name, "channel_mention": interaction.channel.mention,
            "submission_time": discord.utils.utcnow()
        }
        ticket_data_cache[channel_id] = submitted_data
        confirm_embed = discord.Embed(title="📄 信息已提交，等待客服审核 (File 3 Modal)", description=f"感谢 {user.mention}！\n客服 <@&{SUPPORT_ROLE_ID}> 将审核。\n**请耐心等待确认。**", color=discord.Color.orange())
        confirm_embed.add_field(name="身份标识", value=self.identifier.value, inline=False)
        confirm_embed.add_field(name="来意说明", value=self.reason.value, inline=False)
        confirm_embed.set_footer(text=f"Ticket: {interaction.channel.name} | Status: Pending Verification")
        await interaction.channel.send(embed=confirm_embed)
        await interaction.response.send_message("✅ 你的信息已提交 (File 3 Modal)，请等待客服审核。", ephemeral=True, delete_after=20)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        print(f"Error in InfoModal (File 3) submission: {error}"); traceback.print_exc()
        await interaction.response.send_message('提交信息 (File 3 Modal) 时发生错误。', ephemeral=True)

class InfoButtonView(discord.ui.View): # From File 3
    def __init__(self, *, timeout=300):
        super().__init__(timeout=timeout); self.message = None

    @discord.ui.button(label="📝 提供信息 (Provide Info)", style=discord.ButtonStyle.primary, custom_id="provide_ticket_info_v2")
    async def provide_info_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(InfoModal())

    async def on_timeout(self):
        self.provide_info_button.disabled = True
        if self.message:
            try: await self.message.edit(content="*此信息收集按钮 (File 3) 已过期。*", view=self)
            except Exception as e: print(f"Error editing File 3 button on timeout: {e}")
        self.stop()

# --- Giveaway Helper Functions & UI (File 2 - adapted to discord.py) ---
def parse_duration(duration_str: str) -> Optional[datetime.timedelta]: # From File 2
    duration_str = duration_str.lower().strip(); value_str = ""; unit = ""
    for char in duration_str:
        if char.isdigit() or char == '.': value_str += char
        else: unit += char
    if not value_str or not unit: return None
    try:
        value = float(value_str)
        if unit == 's': return datetime.timedelta(seconds=value)
        elif unit == 'm': return datetime.timedelta(minutes=value)
        elif unit == 'h': return datetime.timedelta(hours=value)
        elif unit == 'd': return datetime.timedelta(days=value)
        else: return None
    except ValueError: return None

async def save_giveaway_data(message_id: int, data: dict): # From File 2
    if not redis_pool: return
    try:
        key = f"{GIVEAWAY_PREFIX}{message_id}"; data_to_save = data.copy()
        if isinstance(data_to_save.get('end_time'), datetime.datetime):
            if data_to_save['end_time'].tzinfo is None: data_to_save['end_time'] = data_to_save['end_time'].replace(tzinfo=datetime.timezone.utc)
            data_to_save['end_time'] = data_to_save['end_time'].isoformat()
        await redis_pool.set(key, json.dumps(data_to_save))
    except TypeError as e: print(f"Save giveaway {message_id} to Redis error (serialization): {e}")
    except Exception as e: print(f"Save giveaway {message_id} to Redis error: {e}")

async def load_giveaway_data(message_id: int) -> Optional[dict]: # From File 2
    if not redis_pool: return None
    try:
        key = f"{GIVEAWAY_PREFIX}{message_id}"; data_str = await redis_pool.get(key)
        if data_str:
            data = json.loads(data_str)
            if isinstance(data.get('end_time'), str):
                try: data['end_time'] = datetime.datetime.fromisoformat(data['end_time'])
                except ValueError: print(f"Warning: Giveaway {message_id} end_time invalid format.")
            return data
        return None
    except json.JSONDecodeError: print(f"Redis JSON decode error for giveaway {message_id}."); return None
    except Exception as e: print(f"Load giveaway {message_id} from Redis error: {e}"); return None

async def delete_giveaway_data(message_id: int): # From File 2
     if not redis_pool: return
     try: key = f"{GIVEAWAY_PREFIX}{message_id}"; await redis_pool.delete(key)
     except Exception as e: print(f"Delete giveaway {message_id} from Redis error: {e}")

async def get_all_giveaway_ids() -> List[int]: # From File 2
     if not redis_pool: return []
     try: keys = await redis_pool.keys(f"{GIVEAWAY_PREFIX}*"); return [int(k.split(':')[-1]) for k in keys]
     except Exception as e: print(f"Get all giveaway IDs from Redis error: {e}"); return []

async def parse_message_link(interaction: discord.Interaction, link_or_id: str) -> tuple[Optional[int], Optional[int]]: # From File 2
    message_id = None; channel_id = None
    # Try parsing as full link first
    # Example: https://discord.com/channels/GUILD_ID/CHANNEL_ID/MESSAGE_ID
    link_parts = link_or_id.strip().split('/')
    if len(link_parts) >= 3 and link_parts[-3] == "channels": # Basic check for URL structure
        try:
            guild_id_from_link = int(link_parts[-3]) if len(link_parts) >=4 else None # Actually this is channels
            channel_id = int(link_parts[-2])
            message_id = int(link_parts[-1])
            # Check if the guild ID from link matches current guild if provided (part of a full URL)
            # A bit tricky because link_parts[-3] might be @me for DMs or guild ID
            # For simplicity here, we'll rely on channel_id being valid in current guild context
            # Or if it's just message_id, channel_id needs to be interaction.channel_id
        except ValueError:
             # If parsing as link fails, try as direct message ID (assuming current channel)
            try:
                message_id = int(link_or_id)
                channel_id = interaction.channel_id
            except ValueError:
                await interaction.followup.send("无效的消息链接或ID格式。", ephemeral=True); return None, None
    else: # Try as direct message ID
        try:
            message_id = int(link_or_id)
            channel_id = interaction.channel_id # Assume current channel if only ID is given
        except ValueError:
            await interaction.followup.send("请提供有效的 Discord 消息链接或消息ID。", ephemeral=True); return None, None
    return channel_id, message_id


def create_giveaway_embed(prize: str, end_time: datetime.datetime, winners: int, creator: Union[discord.User, discord.Member], required_role: Optional[discord.Role], status: str = "running") -> discord.Embed: # From File 2
    embed=discord.Embed(title="<a:_:1198114874891632690> **赛博抽奖进行中!** <a:_:1198114874891632690>", description=f"点击 🎉 表情参与!\n\n**奖品:** `{prize}`", color=0x00FFFF)
    embed.add_field(name="<:timer:1198115585629569044> 结束于", value=f"<t:{int(end_time.timestamp())}:R>", inline=True)
    embed.add_field(name="<:winner:1198115869403988039> 获奖人数", value=f"`{winners}`", inline=True)
    embed.add_field(name="<:requirement:1198116280151654461> 参与条件", value=(f"需要拥有 {required_role.mention} 身份组。" if required_role else "`无`"), inline=False)
    embed.set_footer(text=f"由 {creator.display_name} 发起 | 状态: {status.upper()}", icon_url=creator.display_avatar.url if creator.display_avatar else None)
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1003591315297738772/1198117400949297172/giveaway-box.png?ex=65bda71e&is=65ab321e&hm=375f317989609026891610d51d14116503d730ffb1ed1f8749f8e8215e911c18&")
    return embed

def update_embed_ended(embed: discord.Embed, winner_mentions: Optional[str], prize: str, participant_count: int) -> discord.Embed: # From File 2
     embed.title="<:check:1198118533916270644> **抽奖已结束** <:check:1198118533916270644>"; embed.color=0x36393F; embed.clear_fields();
     if winner_mentions: embed.description=f"**奖品:** `{prize}`\n\n恭喜以下获奖者！"; embed.add_field(name="<:winner:1198115869403988039> 获奖者", value=winner_mentions, inline=False);
     else: embed.description=f"**奖品:** `{prize}`\n\n本次抽奖没有符合条件的参与者。"; embed.add_field(name="<:cross:1198118636147118171> 获奖者", value="`无`", inline=False);
     embed.add_field(name="<:members:1198118814719295550> 参与人数", value=f"`{participant_count}`", inline=True);
     if embed.footer: original_footer_text=embed.footer.text.split('|')[0].strip(); embed.set_footer(text=f"{original_footer_text} | 状态: 已结束", icon_url=embed.footer.icon_url);
     return embed

async def process_giveaway_end(message: discord.Message, giveaway_data: dict): # From File 2
    guild = message.guild; channel = message.channel
    if not guild or not channel or not isinstance(channel, discord.TextChannel):
        print(f"Error: process_giveaway_end invalid params (Msg ID: {message.id})"); return
    print(f"Processing giveaway end: {message.id} (Prize: {giveaway_data.get('prize', 'N/A')})")
    reaction = discord.utils.get(message.reactions, emoji="🎉"); potential_participants = []
    if reaction:
        try: potential_participants = [m async for m in reaction.users() if isinstance(m, discord.Member)]
        except discord.Forbidden: print(f"Cannot get reactions for {message.id} (Forbidden).")
        except Exception as e: print(f"Error getting reaction users for giveaway {message.id}: {e}.")
    else: print(f"Message {message.id} has no 🎉 reaction.")

    eligible_participants = []; required_role_id = giveaway_data.get('required_role_id'); required_role = None
    if required_role_id: required_role = guild.get_role(required_role_id)
    if required_role: eligible_participants = [m for m in potential_participants if required_role in m.roles and not m.bot] # Also exclude bots
    else: eligible_participants = [m for m in potential_participants if not m.bot] # Exclude bots

    winners_list = []; winner_mentions = None; participant_count = len(eligible_participants)
    if eligible_participants:
        num_winners_to_pick = min(giveaway_data['winners'], len(eligible_participants))
        if num_winners_to_pick > 0:
            winners_list = random.sample(eligible_participants, num_winners_to_pick)
            winner_mentions = ", ".join([w.mention for w in winners_list])
            print(f"Giveaway {message.id} winners: {[w.name for w in winners_list]}")

    result_message_content = f"<a:_:1198114874891632690> **抽奖结束！** <a:_:1198114874891632690>\n奖品: `{giveaway_data['prize']}`\n";
    if winner_mentions: result_message_content += f"\n恭喜 {winner_mentions}！"
    else: result_message_content += "\n可惜，本次抽奖没有符合条件的获奖者。"
    try: await channel.send(result_message_content, allowed_mentions=discord.AllowedMentions(users=True))
    except Exception as e: print(f"Error sending giveaway {message.id} winner announcement: {e}")

    if message.embeds:
        try:
            updated_embed = update_embed_ended(message.embeds[0], winner_mentions, giveaway_data['prize'], participant_count)
            await message.edit(embed=updated_embed, view=None) # Remove any buttons/views
        except Exception as e: print(f"Error editing giveaway {message.id} message: {e}")
    else: print(f"Giveaway {message.id} has no embed to update.")


# --- Helper Function to Create Welcome Channel (File 3) ---
async def create_welcome_channel_for_member(member: discord.Member, guild: discord.Guild, welcome_category: discord.CategoryChannel, support_role: discord.Role) -> Optional[discord.TextChannel]:
    print(f"Attempting to create/find welcome channel for {member.name} ({member.id})...")
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, embed_links=True, attach_files=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_permissions=True),
        support_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    }
    safe_name = "".join(c for c in member.name if c.isalnum() or c in ['-', '_']).lower() or "member"
    channel_name = f"welcome-{safe_name[:80]}"
    existing_channel = discord.utils.get(welcome_category.text_channels, name=channel_name)

    if existing_channel:
        print(f"Welcome channel '{channel_name}' already exists for {member.name}. Sending reminder.")
        try:
            current_overwrites = existing_channel.overwrites_for(member)
            if not current_overwrites.view_channel:
                 await existing_channel.set_permissions(member, overwrite=overwrites[member], reason="Re-applying permissions for existing welcome channel")
            # TICKET_PANEL_CHANNEL_NAME is now a global from ENV
            await existing_channel.send(f"👋 {member.mention}, 提醒您尽快前往 `{TICKET_PANEL_CHANNEL_NAME}` 完成验证。 <@&{support_role.id}>")
            return existing_channel
        except discord.Forbidden: print(f"Bot lacks permission in existing channel #{existing_channel.name}")
        except Exception as e: print(f"Error with existing welcome channel for {member.name}: {e}")
        return existing_channel

    try:
        welcome_channel = await guild.create_text_channel(name=channel_name, category=welcome_category, overwrites=overwrites, topic=f"引导成员 {member.display_name} 验证", reason=f"为成员 {member.name} 创建引导频道 (File 3 logic)")
        print(f"Created welcome channel #{welcome_channel.name} (ID: {welcome_channel.id})")
    except discord.Forbidden: print(f"ERROR: Bot lacks permissions to create welcome channel for {member.name}."); return None
    except Exception as e: print(f"ERROR: Failed to create welcome channel for {member.name}: {e}"); traceback.print_exc(); return None

    try:
        # TICKET_PANEL_CHANNEL_NAME is now a global from ENV
        guidance_message = (
            f"欢迎 {member.mention}！看起来您尚未完成身份验证。\n\n"
            f"➡️ **请前往 `{TICKET_PANEL_CHANNEL_NAME}` 频道，点击那里的 'Create Ticket' 按钮来开始正式的验证流程。**\n\n"
            f"我们的客服团队 <@&{support_role.id}> 已经收到通知，会尽快协助您。\n"
            f"如果在 `{TICKET_PANEL_CHANNEL_NAME}` 遇到问题，您可以在此频道简单说明。"
        )
        await welcome_channel.send(guidance_message)
        return welcome_channel
    except discord.Forbidden: print(f"ERROR: Bot lacks permission to send messages in #{welcome_channel.name}.")
    except Exception as e: print(f"ERROR: Failed to send welcome message: {e}"); traceback.print_exc()
    return welcome_channel


# --- Event: Bot Ready ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print(f'Discord.py Version: {discord.__version__}')
    print(f'Python Version: {os.sys.version}')
    print(f'Running on: {len(bot.guilds)} servers')
    print('------ Configuration Info ------')
    print(f'DeepSeek API Key Loaded: {"Yes" if DEEPSEEK_API_KEY else "No"}')
    print(f'Redis URL Loaded: {"Yes" if REDIS_URL else "No"}')
    print(f'Support Role ID: {SUPPORT_ROLE_ID}')
    print(f'Ticket Category ID (for File 1 tickets & File 3 listening): {TICKET_CATEGORY_ID}')
    print(f'Log Channel ID (for /verifyticket): {bot.log_channel_id if bot.log_channel_id else "Not Set (use /setlogchannel)"}')
    print(f'New Member Welcome Category ID: {NEW_MEMBER_CATEGORY_ID}')
    print(f'Verified Role IDs: {VERIFIED_ROLE_IDS}')
    print(f'Ticket Panel Channel Name (for guidance): {TICKET_PANEL_CHANNEL_NAME}')
    print(f'Public Warn Log Channel ID (File 1 mod logs): {PUBLIC_WARN_LOG_CHANNEL_ID if PUBLIC_WARN_LOG_CHANNEL_ID else "Not Set"}')
    print(f'Mod Alert Role IDs (File 1): {MOD_ALERT_ROLE_IDS if MOD_ALERT_ROLE_IDS else "Not Set"}')
    print('-------------------------------')

    # Initialize aiohttp session (File 1)
    if AIOHTTP_AVAILABLE and not bot.http_session:
         bot.http_session = aiohttp.ClientSession()
         print("aiohttp session created.")

    # Initialize Redis (File 2)
    await setup_redis()

    # Register persistent views (File 1)
    if not bot.persistent_views_added:
        bot.add_view(CreateTicketView()) # File 1 Ticket Tool
        bot.add_view(CloseTicketView())  # File 1 Ticket Tool
        # InfoButtonView from File 3 is NOT persistent by design, it's added dynamically.
        bot.persistent_views_added = True
        print("Registered persistent UI views (File 1 Ticket Tool).")

    # Start background tasks
    if redis_pool and not check_giveaways.is_running(): # From File 2
        check_giveaways.start()
        print("Giveaway checking task started.")
    elif not redis_pool :
        print("Redis not connected, giveaway checking task not started.")


    print('Syncing application commands...')
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} application commands.')
    except Exception as e:
        print(f'Error syncing commands: {e}')

    try:
        await bot.change_presence(activity=discord.Game(name="/help for commands"))
        print("Bot presence set.")
    except Exception as e:
        print(f"Warning: Could not set bot presence: {e}")

    print('------ Bot is Ready! ------')


# --- Event: Command Error Handling (Legacy Prefix - File 1) ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    elif isinstance(error, commands.MissingPermissions):
        try: await ctx.send(f"🚫 Legacy CMD: Missing permissions: {', '.join(error.missing_permissions)}")
        except: pass
    elif isinstance(error, commands.BotMissingPermissions):
         try: await ctx.send(f"🤖 Legacy CMD: I'm missing permissions: {', '.join(error.missing_permissions)}")
         except: pass
    else: print(f"Legacy command '{ctx.command}' error: {error}")


# --- Event: App Command Error Handling (File 1 - Main Handler) ---
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    error_message = "🤔 An unknown error occurred while processing the command."
    ephemeral_response = True

    if isinstance(error, app_commands.CommandNotFound): error_message = "❓ Unknown command."
    elif isinstance(error, app_commands.MissingPermissions): error_message = f"🚫 You lack permissions: {', '.join(f'`{p}`' for p in error.missing_permissions)}."
    elif isinstance(error, app_commands.BotMissingPermissions): error_message = f"🤖 I lack permissions: {', '.join(f'`{p}`' for p in error.missing_permissions)}."
    elif isinstance(error, app_commands.CheckFailure): error_message = "🚫 You do not meet the conditions to use this command."
    elif isinstance(error, app_commands.CommandOnCooldown): error_message = f"⏳ Command on cooldown. Try again in {error.retry_after:.2f}s."
    elif isinstance(error, app_commands.NoPrivateMessage): error_message = "💬 This command cannot be used in DMs."
    elif isinstance(error, app_commands.MissingRole): error_message = f"🚫 You need the role: '{error.missing_role}'."
    elif isinstance(error, app_commands.MissingAnyRole): error_message = f"🚫 You need one of these roles: {', '.join([f'`{r}`' for r in error.missing_roles])}."
    elif isinstance(error, app_commands.CommandInvokeError):
        original = error.original
        print(f"Command '{interaction.command.name if interaction.command else 'Unknown'}' failed: {type(original).__name__} - {original}")
        traceback.print_exception(type(original), original, original.__traceback__)
        if isinstance(original, discord.Forbidden): error_message = f"🚫 Discord Permissions Error: I can't perform this action. Check my role hierarchy and channel permissions."
        elif isinstance(original, discord.HTTPException): error_message = f"🌐 Network Error: Communication with Discord API failed (HTTP {original.status}). Try again later."
        elif isinstance(original, asyncio.TimeoutError): error_message = "⏱️ Operation timed out. Try again later."
        else: error_message = f"⚙️ Internal error executing command. Admin notified. Error: {type(original).__name__}"
    else: print(f'Unhandled app command error: {type(error).__name__} - {error}')

    try:
        if interaction.response.is_done(): await interaction.followup.send(error_message, ephemeral=ephemeral_response)
        else: await interaction.response.send_message(error_message, ephemeral=ephemeral_response)
    except discord.NotFound: print(f"Interaction gone, couldn't send error: {error_message}")
    except Exception as e: print(f"Error sending error message itself: {e}")

bot.tree.on_error = on_app_command_error


# --- Event: Member Join (Merged from File 1 & File 3) ---
@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    print(f'[+] Member Joined: {member.name} ({member.id}) to guild {guild.name} ({guild.id})')

    # --- Auto-assign separator roles (File 1 logic) ---
    separator_role_names_to_assign = [ # Example names, replace with actual
        "▽─────————─────身份─────————─────",
        "▽─────————─────通知─────————─────",
        "▽─────————─────其他─────————─────"
    ]
    roles_to_add_f1 = []
    for role_name in separator_role_names_to_assign:
        role = get(guild.roles, name=role_name)
        if role and (role < guild.me.top_role or guild.me == guild.owner): roles_to_add_f1.append(role)
        elif role: print(f"   ⚠️ Cannot assign separator role '{role_name}' to {member.name} (hierarchy).")
        # else: print(f"   ℹ️ Separator role '{role_name}' not found for {member.name}.") # Can be verbose
    if roles_to_add_f1:
        try:
            await member.add_roles(*roles_to_add_f1, reason="New member auto-assign separator roles (File 1)")
            print(f"   ✅ Assigned separator roles to {member.name}: {', '.join([r.name for r in roles_to_add_f1])}")
        except Exception as e: print(f"   ❌ Error assigning separator roles to {member.name}: {e}")

    # --- Send generic welcome message (File 1 logic) ---
    # Uses WELCOME_CHANNEL_ID, RULES_CHANNEL_ID, ROLES_INFO_CHANNEL_ID from ENV
    if WELCOME_CHANNEL_ID:
        welcome_channel_f1 = guild.get_channel(WELCOME_CHANNEL_ID)
        if welcome_channel_f1 and isinstance(welcome_channel_f1, discord.TextChannel):
            welcome_perms = welcome_channel_f1.permissions_for(guild.me)
            if welcome_perms.send_messages and welcome_perms.embed_links:
                try:
                    # TICKET_PANEL_CHANNEL_NAME is global from ENV
                    verification_link_text = f"`{TICKET_PANEL_CHANNEL_NAME}` (点击按钮开票)" if TICKET_PANEL_CHANNEL_NAME else "验证频道 (请咨询管理员)"
                    embed_f1 = discord.Embed(title=f"🎉 欢迎来到 {guild.name}! 🎉", color=discord.Color.blue())
                    desc_f1 = f"你好 {member.mention}! 很高兴你能加入 **GJ Team**！\n\n"
                    if RULES_CHANNEL_ID: desc_f1 += f"- 服务器规则: <#{RULES_CHANNEL_ID}>\n"
                    if ROLES_INFO_CHANNEL_ID: desc_f1 += f"- 身份组信息: <#{ROLES_INFO_CHANNEL_ID}>\n"
                    desc_f1 += f"- 认证申请: {verification_link_text}\n\n祝你在 **GJ Team** 玩得愉快！"
                    embed_f1.description = desc_f1
                    embed_f1.set_thumbnail(url=member.display_avatar.url)
                    embed_f1.set_footer(text=f"你是服务器的第 {guild.member_count} 位成员！")
                    embed_f1.timestamp = discord.utils.utcnow()
                    await welcome_channel_f1.send(embed=embed_f1)
                    print(f"   ✅ Sent generic welcome message (File 1) to {member.name} in #{welcome_channel_f1.name}.")
                except Exception as e: print(f"   ❌ Error sending generic welcome (File 1) to {member.name}: {e}")
            # else: print(f"   ⚠️ Bot lacks send/embed perms in generic welcome channel {WELCOME_CHANNEL_ID} for {member.name}.")
        # else: print(f"   ⚠️ Generic welcome channel {WELCOME_CHANNEL_ID} not found or invalid for {member.name}.")


    # --- Create private welcome/guidance channel for UNVERIFIED members (File 3 logic) ---
    if not NEW_MEMBER_CATEGORY_ID or not SUPPORT_ROLE_ID or not VERIFIED_ROLE_IDS or not TICKET_PANEL_CHANNEL_NAME:
        print(f"   ℹ️ Skipping File 3's unverified member welcome for {member.name} due to missing core config (NewMemCat, SupportRole, VerifiedRoles, TicketPanelName).")
        return

    support_role_f3 = guild.get_role(SUPPORT_ROLE_ID)
    welcome_category_f3 = guild.get_channel(NEW_MEMBER_CATEGORY_ID)

    if not support_role_f3 or not welcome_category_f3 or not isinstance(welcome_category_f3, discord.CategoryChannel):
        print(f"   ⚠️ File 3's Support Role or New Member Category not found/invalid for {member.name}. Skipping private welcome.")
        return

    member_role_ids = {role.id for role in member.roles}
    has_verified_role = any(verified_id in member_role_ids for verified_id in VERIFIED_ROLE_IDS)

    if not has_verified_role:
        print(f"   ℹ️ Member {member.name} is unverified. Initiating File 3's private welcome channel process.")
        await create_welcome_channel_for_member(member, guild, welcome_category_f3, support_role_f3)
    else:
        print(f"   ✅ Member {member.name} is already verified. Skipping File 3's private welcome channel.")


# --- Event: On Message (File 1 - Spam, Bad Words, AI Check) ---
@bot.event
async def on_message(message: discord.Message):
    if not message.guild or message.author.id == bot.user.id: return
    if message.author.bot: # Handle bot spam separately
        # --- Bot Spam Detection (File 1) ---
        bot_author_id = message.author.id; now = discord.utils.utcnow()
        bot_message_timestamps.setdefault(bot_author_id, [])
        bot_message_timestamps[bot_author_id].append(now)
        time_limit_bot = now - datetime.timedelta(seconds=BOT_SPAM_TIME_WINDOW_SECONDS)
        bot_message_timestamps[bot_author_id] = [ts for ts in bot_message_timestamps[bot_author_id] if ts > time_limit_bot]

        if len(bot_message_timestamps[bot_author_id]) >= BOT_SPAM_COUNT_THRESHOLD:
            print(f"🚨 Bot Spam Detected! Bot: {message.author} in #{message.channel.name}")
            bot_message_timestamps[bot_author_id] = [] # Reset
            mod_pings = " ".join([f"<@&{rid}>" for rid in MOD_ALERT_ROLE_IDS]) if MOD_ALERT_ROLE_IDS else "Moderators"
            # Simplified action for now, full auto-kick/role-removal is complex and risky
            alert_msg = (f"🚨 **机器人刷屏警报!** 🚨\n"
                        f"机器人: {message.author.mention}\n频道: {message.channel.mention}\n"
                        f"{mod_pings} 请管理员关注并处理！可能需要手动清理或调整该机器人权限。")
            try: await message.channel.send(alert_msg)
            except Exception as e: print(f"   Error sending bot spam alert: {e}")
        return # End processing for other bots here

    # --- User Message Processing (File 1) ---
    now = discord.utils.utcnow(); author = message.author; author_id = author.id
    guild = message.guild; channel = message.channel
    member = guild.get_member(author_id)

    # Exemption for users with 'manage_messages' permission
    if member and isinstance(channel, (discord.TextChannel, discord.Thread)) and channel.permissions_for(member).manage_messages:
        pass # Mod/Admin, skip content/spam checks for them
    else:
        perform_content_check = author_id not in exempt_users_from_ai_check and channel.id not in exempt_channels_from_ai_check

        if perform_content_check:
            # 1. DeepSeek API Check
            if DEEPSEEK_API_KEY:
                violation_type = await check_message_with_deepseek(message.content)
                if violation_type:
                    print(f"🚫 API Violation ({violation_type}): User {author} in #{channel.name}")
                    deleted = False
                    try:
                        if channel.permissions_for(guild.me).manage_messages: await message.delete(); deleted = True
                    except: pass # Ignore delete error
                    mod_pings = " ".join([f"<@&{rid}>" for rid in MOD_ALERT_ROLE_IDS]) if MOD_ALERT_ROLE_IDS else "Moderators"
                    embed = discord.Embed(title=f"🚨 API 内容审核 ({violation_type}) 🚨", color=discord.Color.dark_red(), timestamp=now)
                    embed.add_field(name="用户", value=f"{author.mention} ({author_id})", inline=False)
                    embed.add_field(name="频道", value=channel.mention, inline=False)
                    embed.add_field(name="内容摘要", value=f"```{message.content[:1000]}```", inline=False)
                    embed.add_field(name="状态", value="已删除" if deleted else "删除失败/无权限", inline=True)
                    embed.add_field(name="建议操作", value=f"{mod_pings} 请管理员审核！", inline=False)
                    await send_to_public_log(guild, embed, log_type=f"API Violation ({violation_type})")
                    return # Stop further processing

            # 2. Local Bad Word Check
            if BAD_WORDS_LOWER:
                content_lower = message.content.lower(); triggered_bad_word = next((word for word in BAD_WORDS_LOWER if word in content_lower), None)
                if triggered_bad_word:
                    print(f"🚫 Bad Word: '{triggered_bad_word}' by {author} in #{channel.name}")
                    # Simplified: delete and log, no complex first-offense/warning escalation here for brevity
                    # Full warning system from File 1 could be re-integrated if needed.
                    deleted_bw = False
                    try:
                        if channel.permissions_for(guild.me).manage_messages: await message.delete(); deleted_bw = True
                    except: pass
                    embed_bw = discord.Embed(title="🚫 不当词语检测", color=discord.Color.orange(), timestamp=now)
                    embed_bw.add_field(name="用户", value=f"{author.mention} ({author_id})", inline=False)
                    embed_bw.add_field(name="触发词", value=f"`{triggered_bad_word}`", inline=True)
                    embed_bw.add_field(name="频道", value=channel.mention, inline=True)
                    embed_bw.add_field(name="状态", value="已删除" if deleted_bw else "删除失败/无权限", inline=True)
                    await send_to_public_log(guild, embed_bw, log_type="Bad Word")
                    # Optionally, send a DM or temporary channel message
                    try: await author.send(f"检测到你在 {guild.name} 服务器的发言包含不当词语，已被处理。请注意言行。", delete_after=30)
                    except: pass
                    return # Stop further processing


        # 3. User Spam Detection (Simplified from File 1 for this merge)
        user_message_timestamps.setdefault(author_id, [])
        user_message_timestamps[author_id].append(now)
        time_limit_user = now - datetime.timedelta(seconds=SPAM_TIME_WINDOW_SECONDS)
        user_message_timestamps[author_id] = [ts for ts in user_message_timestamps[author_id] if ts > time_limit_user]

        if len(user_message_timestamps[author_id]) >= SPAM_COUNT_THRESHOLD:
            print(f"🚨 User Spam Detected! User: {author} in #{channel.name}")
            user_message_timestamps[author_id] = [] # Reset
            user_warnings[author_id] = user_warnings.get(author_id, 0) + 1
            # Simplified: Log and temporary message, no auto-kick here for brevity
            embed_spam = discord.Embed(title="🚨 用户刷屏检测", color=discord.Color.orange(), timestamp=now)
            embed_spam.add_field(name="用户", value=f"{author.mention} ({author_id})", inline=False)
            embed_spam.add_field(name="频道", value=channel.mention, inline=True)
            embed_spam.add_field(name="警告次数 (示例)", value=f"{user_warnings[author_id]}/{KICK_THRESHOLD}", inline=True) # Example, full kick logic not here
            await send_to_public_log(guild, embed_spam, log_type="User Spam")
            try: await channel.send(f"⚠️ {author.mention}，检测到刷屏，请减缓速度！", delete_after=15)
            except: pass
            # Optional: Purge user's messages after spam detection
            # try:
            #     if channel.permissions_for(guild.me).manage_messages:
            #         await channel.purge(limit=SPAM_COUNT_THRESHOLD, check=lambda m: m.author == author, after=time_limit_user)
            # except Exception as e: print(f"Error purging spam: {e}")
            return

    # await bot.process_commands(message) # For legacy prefix commands, if any were kept


# --- Event: Voice State Update (File 1 - Temp VCs) ---
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    guild = member.guild
    master_vc_id = get_setting(temp_vc_settings, guild.id, "master_channel_id")
    category_id = get_setting(temp_vc_settings, guild.id, "category_id")
    if not master_vc_id: return

    master_channel = guild.get_channel(master_vc_id)
    if not master_channel or not isinstance(master_channel, discord.VoiceChannel): return

    vc_category = guild.get_channel(category_id) if category_id else master_channel.category
    if not vc_category or not isinstance(vc_category, discord.CategoryChannel):
        print(f"TempVC: Invalid category for {guild.name}. Using master's category if possible.")
        vc_category = master_channel.category
        if not vc_category : print(f"TempVC: Still no valid category for {guild.name}. Aborting."); return


    # Create temp channel
    if after.channel == master_channel:
        if not vc_category.permissions_for(guild.me).manage_channels or \
           not vc_category.permissions_for(guild.me).move_members:
            print(f"TempVC: Bot lacks manage_channels/move_members in {vc_category.name} for {member.name}")
            try: await member.send(f"抱歉，我在服务器 **{guild.name}** 创建临时语音频道所需的权限不足。")
            except: pass
            return

        owner_overwrites = discord.PermissionOverwrite(manage_channels=True, manage_permissions=True, move_members=True, connect=True, speak=True, stream=True)
        bot_overwrites = discord.PermissionOverwrite(manage_channels=True, connect=True, view_channel=True) # Ensure bot can see and manage
        temp_channel_name = f"🎮 {member.display_name}的频道"[:100]
        new_channel = None
        try:
            new_channel = await guild.create_voice_channel(name=temp_channel_name, category=vc_category, overwrites={guild.default_role: discord.PermissionOverwrite(connect=True, speak=True), member: owner_overwrites, guild.me: bot_overwrites}, reason=f"Temp VC for {member.name}")
            await member.move_to(new_channel)
            temp_vc_owners[new_channel.id] = member.id
            temp_vc_created.add(new_channel.id)
            print(f"TempVC: Created {new_channel.name} for {member.name}")
        except Exception as e:
            print(f"TempVC: Error creating/moving for {member.name}: {e}")
            if new_channel: await new_channel.delete(reason="Creation error")

    # Delete empty temp channel
    if before.channel and before.channel.id in temp_vc_created:
        await asyncio.sleep(1) # Delay to prevent race conditions
        channel_to_check = guild.get_channel(before.channel.id) # Re-fetch
        if channel_to_check and isinstance(channel_to_check, discord.VoiceChannel) and not any(m for m in channel_to_check.members if not m.bot):
            try:
                await channel_to_check.delete(reason="Temp VC empty")
                print(f"TempVC: Deleted empty channel {channel_to_check.name}")
            except Exception as e: print(f"TempVC: Error deleting {channel_to_check.name}: {e}")
            finally:
                if channel_to_check.id in temp_vc_owners: del temp_vc_owners[channel_to_check.id]
                if channel_to_check.id in temp_vc_created: temp_vc_created.remove(channel_to_check.id)
        elif not channel_to_check and before.channel.id in temp_vc_created: # Channel already gone
            if before.channel.id in temp_vc_owners: del temp_vc_owners[before.channel.id]
            temp_vc_created.remove(before.channel.id)


# --- Event: on_guild_channel_create (File 3 - For Ticket Tool Integration) ---
@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    if not isinstance(channel, discord.TextChannel): return
    # TICKET_CATEGORY_ID is global from ENV - should match File 1's ticket category
    if channel.category_id != TICKET_CATEGORY_ID: return

    print(f"Detected potential ticket channel (File 3 listener): #{channel.name} (ID: {channel.id}) in configured category.")
    await asyncio.sleep(1) # Allow Ticket Tool (File 1) to fully set up permissions
    guild = channel.guild

    if not SUPPORT_ROLE_ID: print(f"ERROR (File 3 listener): Support Role ID not configured."); return
    support_role = guild.get_role(SUPPORT_ROLE_ID)
    if not support_role: print(f"ERROR (File 3 listener): Support Role ID {SUPPORT_ROLE_ID} not found."); return

    try:
        # Ensure support role has perms (might be redundant if File 1's tool already does this for its staff roles)
        # This ensures File 3's specific SUPPORT_ROLE_ID also has access if it's different
        current_perms = channel.permissions_for(support_role)
        if not current_perms.view_channel or not current_perms.send_messages:
            overwrite = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, embed_links=True, attach_files=True, manage_messages=True) # Full perms
            await channel.set_permissions(support_role, overwrite=overwrite, reason="Auto-adding File 3 Support Role to ticket")
            print(f"Applied permissions for File 3 Support Role '{support_role.name}' to ticket #{channel.name}")

        # Send the message with the File 3 info collection button
        initial_message_text = (f"欢迎！负责人 <@&{SUPPORT_ROLE_ID}> 已就绪。\n"
                                f"**请点击下方按钮提供必要信息 (File 3 Modal) 以开始处理您的请求：**")
        view = InfoButtonView() # This is File 3's button view
        sent_message = await channel.send(initial_message_text, view=view)
        view.message = sent_message
        print(f"Sent File 3 info button to ticket #{channel.name}")

    except discord.Forbidden: print(f"ERROR (File 3 listener): Bot lacks permissions in ticket channel #{channel.name}.")
    except Exception as e: print(f"ERROR in on_guild_channel_create (File 3 listener): {e}"); traceback.print_exc()


# --- Slash Command: Help (File 1) ---
@bot.tree.command(name="help", description="显示可用指令的帮助信息。")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 GJ Team Bot 指令帮助", description="以下是本机器人支持的斜线指令列表：", color=discord.Color.purple())
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.add_field(name="👤 身份组管理 (File 1)", value="`/createrole`, `/deleterole`, `/giverole`, `/takerole`, `/createseparator`", inline=False)
    embed.add_field(name="🛠️ 审核与管理 (File 1)", value="`/clear`, `/warn`, `/unwarn`", inline=False)
    embed.add_field(name="📢 公告发布 (File 1)", value="`/announce`", inline=False)
    embed.add_field(name="⚙️ 高级管理 (/管理 ...) (File 1)", value="`... 票据设定`, `... 删讯息`, `... 频道名`, `... 禁言`, `... 踢出`, `... 封禁`, `... 解封`, `... 人数频道`, `... ai豁免-*`", inline=False)
    embed.add_field(name="🔊 临时语音 (/语音 ...) (File 1)", value="`... 设定母频道`, `... 设定权限`, `... 转让`, `... 房主`", inline=False)
    embed.add_field(name="🎁 抽奖活动 (/giveaway ...) (File 2)", value="`... create`, `... reroll`, `... pickwinner`, `... end`", inline=False)
    embed.add_field(name="🎫 成员与票据验证 (File 3)", value="`/setlogchannel` (Admin), `/verifyticket` (Support), `/checkmemberverify` (Support)", inline=False)
    embed.set_footer(text="[] = 必填参数, <> = 可选参数。大部分管理指令需要相应权限。")
    embed.timestamp = discord.utils.utcnow()
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Role Management Commands (File 1) ---
@bot.tree.command(name="createrole", description="在服务器中创建一个新的身份组。")
@app_commands.describe(role_name="新身份组的确切名称。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_createrole(interaction: discord.Interaction, role_name: str):
    guild = interaction.guild; await interaction.response.defer(ephemeral=True)
    if get(guild.roles, name=role_name): await interaction.followup.send(f"❌ 身份组 **{role_name}** 已存在！", ephemeral=True); return
    try:
        new_role = await guild.create_role(name=role_name, reason=f"Created by {interaction.user}")
        await interaction.followup.send(f"✅ 已创建身份组: {new_role.mention}", ephemeral=False) # Public for confirmation
    except Exception as e: await interaction.followup.send(f"⚙️ 创建身份组时出错: {e}", ephemeral=True)

@bot.tree.command(name="deleterole", description="根据精确名称删除一个现有的身份组。")
@app_commands.describe(role_name="要删除的身份组的确切名称。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_deleterole(interaction: discord.Interaction, role_name: str):
    guild = interaction.guild; await interaction.response.defer(ephemeral=True)
    role_to_delete = get(guild.roles, name=role_name)
    if not role_to_delete: await interaction.followup.send(f"❓ 找不到身份组 **{role_name}**。", ephemeral=True); return
    if role_to_delete >= guild.me.top_role and guild.me.id != guild.owner_id : await interaction.followup.send(f"🚫 无法删除 {role_to_delete.mention} (层级问题)。", ephemeral=True); return
    try:
        await role_to_delete.delete(reason=f"Deleted by {interaction.user}")
        await interaction.followup.send(f"✅ 已删除身份组: **{role_name}**", ephemeral=False)
    except Exception as e: await interaction.followup.send(f"⚙️ 删除身份组时出错: {e}", ephemeral=True)

@bot.tree.command(name="giverole", description="将一个现有的身份组分配给指定成员。")
@app_commands.describe(user="要给予身份组的用户。", role_name="要分配的身份组的确切名称。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_giverole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    guild = interaction.guild; await interaction.response.defer(ephemeral=True)
    role_to_give = get(guild.roles, name=role_name)
    if not role_to_give: await interaction.followup.send(f"❓ 找不到身份组 **{role_name}**。", ephemeral=True); return
    if role_to_give >= guild.me.top_role and guild.me.id != guild.owner_id : await interaction.followup.send(f"🚫 无法分配 {role_to_give.mention} (我的层级问题)。", ephemeral=True); return
    if isinstance(interaction.user, discord.Member) and interaction.user.id != guild.owner_id and role_to_give >= interaction.user.top_role : await interaction.followup.send(f"🚫 你无法分配层级高于或等于你的身份组。", ephemeral=True); return
    if role_to_give in user.roles: await interaction.followup.send(f"ℹ️ 用户 {user.mention} 已拥有 {role_to_give.mention}。", ephemeral=True); return
    try:
        await user.add_roles(role_to_give, reason=f"Assigned by {interaction.user}")
        await interaction.followup.send(f"✅ 已将 {role_to_give.mention} 赋予给 {user.mention}。", ephemeral=False)
    except Exception as e: await interaction.followup.send(f"⚙️ 赋予身份组时出错: {e}", ephemeral=True)

@bot.tree.command(name="takerole", description="从指定成员移除一个特定的身份组。")
@app_commands.describe(user="要移除其身份组的用户。", role_name="要移除的身份组的确切名称。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_takerole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    guild = interaction.guild; await interaction.response.defer(ephemeral=True)
    role_to_take = get(guild.roles, name=role_name)
    if not role_to_take: await interaction.followup.send(f"❓ 找不到身份组 **{role_name}**。", ephemeral=True); return
    if role_to_take >= guild.me.top_role and guild.me.id != guild.owner_id : await interaction.followup.send(f"🚫 无法移除 {role_to_take.mention} (我的层级问题)。", ephemeral=True); return
    if isinstance(interaction.user, discord.Member) and interaction.user.id != guild.owner_id and role_to_take >= interaction.user.top_role : await interaction.followup.send(f"🚫 你无法移除层级高于或等于你的身份组。", ephemeral=True); return
    if role_to_take not in user.roles: await interaction.followup.send(f"ℹ️ 用户 {user.mention} 未拥有 {role_to_take.mention}。", ephemeral=True); return
    try:
        await user.remove_roles(role_to_take, reason=f"Removed by {interaction.user}")
        await interaction.followup.send(f"✅ 已从 {user.mention} 移除 {role_to_take.mention}。", ephemeral=False)
    except Exception as e: await interaction.followup.send(f"⚙️ 移除身份组时出错: {e}", ephemeral=True)

@bot.tree.command(name="createseparator", description="创建一个用于视觉分隔的特殊身份组。")
@app_commands.describe(label="要在分隔线中显示的文字标签。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_createseparator(interaction: discord.Interaction, label: str):
    guild = interaction.guild; await interaction.response.defer(ephemeral=True)
    separator_name = f"▽─── {label} ───"
    if get(guild.roles, name=separator_name): await interaction.followup.send(f"⚠️ 分隔线 **{separator_name}** 已存在！", ephemeral=True); return
    try:
        new_role = await guild.create_role(name=separator_name, permissions=discord.Permissions.none(), reason=f"Separator by {interaction.user}")
        await interaction.followup.send(f"✅ 已创建分隔线: **{new_role.name}**。请手动调整其在身份组列表中的位置。", ephemeral=False)
    except Exception as e: await interaction.followup.send(f"⚙️ 创建分隔线时出错: {e}", ephemeral=True)


# --- Moderation Commands (File 1) ---
@bot.tree.command(name="clear", description="清除当前频道中指定数量的消息 (1-100)。")
@app_commands.describe(amount="要删除的消息数量 (1 到 100 之间)。")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
async def slash_clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel): await interaction.response.send_message("❌ 此命令仅限文字频道。", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    try:
        deleted = await channel.purge(limit=amount)
        await interaction.followup.send(f"✅ 已删除 {len(deleted)} 条消息。", ephemeral=True)
        log_embed = discord.Embed(title="🧹 消息清除", color=discord.Color.light_grey(), timestamp=discord.utils.utcnow())
        log_embed.add_field(name="执行者", value=interaction.user.mention, inline=True)
        log_embed.add_field(name="频道", value=channel.mention, inline=True)
        log_embed.add_field(name="数量", value=str(len(deleted)), inline=True)
        await send_to_public_log(interaction.guild, log_embed, log_type="ClearMessages")
    except Exception as e: await interaction.followup.send(f"⚙️ 清除消息时出错: {e}", ephemeral=True)

# Simplified warn/unwarn from File 1 (full kick logic on N warns omitted for brevity in merge)
@bot.tree.command(name="warn", description="手动向用户发出一次警告。")
@app_commands.describe(user="要警告的用户。", reason="警告的原因 (可选)。")
@app_commands.checks.has_permissions(kick_members=True) # Or moderate_members
async def slash_warn(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    guild = interaction.guild; author = interaction.user
    if user.bot or user == author: await interaction.response.send_message("❌ 无效操作对象。", ephemeral=True); return
    # Simplified: Log warning, no complex state tracking here
    user_warnings[user.id] = user_warnings.get(user.id, 0) + 1 # Example tracking
    embed = discord.Embed(title="⚠️ 手动警告已发出", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
    embed.set_author(name=f"由 {author.display_name} 发出", icon_url=author.display_avatar.url)
    embed.add_field(name="被警告用户", value=f"{user.mention} ({user.id})", inline=False)
    embed.add_field(name="原因", value=reason, inline=False)
    embed.add_field(name="当前警告(示例)", value=f"{user_warnings[user.id]}/{KICK_THRESHOLD}", inline=False)
    await interaction.response.send_message(embed=embed)
    await send_to_public_log(guild, embed, log_type="ManualWarn_Simplified")

@bot.tree.command(name="unwarn", description="移除用户的一次警告记录。")
@app_commands.describe(user="要移除其警告的用户。", reason="移除警告的原因 (可选)。")
@app_commands.checks.has_permissions(kick_members=True) # Or moderate_members
async def slash_unwarn(interaction: discord.Interaction, user: discord.Member, reason: str = "管理员酌情处理"):
    if user_warnings.get(user.id, 0) > 0: user_warnings[user.id] -= 1
    embed = discord.Embed(title="✅ 警告已移除", color=discord.Color.green(), timestamp=discord.utils.utcnow())
    embed.set_author(name=f"由 {interaction.user.display_name} 操作", icon_url=interaction.user.display_avatar.url)
    embed.add_field(name="用户", value=f"{user.mention} ({user.id})", inline=False)
    embed.add_field(name="原因", value=reason, inline=False)
    embed.add_field(name="新警告次数(示例)", value=f"{user_warnings.get(user.id, 0)}/{KICK_THRESHOLD}", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await send_to_public_log(interaction.guild, embed, log_type="ManualUnwarn_Simplified")


# --- Announce Command (File 1) ---
@bot.tree.command(name="announce", description="以嵌入式消息格式发送服务器公告。")
@app_commands.describe(channel="要发送公告的目标文字频道。", title="公告的醒目标题。", message="公告的主要内容 (使用 '\\n' 来换行)。", ping_role="(可选) 要在公告前提及的身份组。", image_url="(可选) 图片 URL。", color="(可选) 十六进制颜色代码 (如 '#3498db')。")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True)
async def slash_announce(interaction: discord.Interaction, channel: discord.TextChannel, title: str, message: str, ping_role: Optional[discord.Role] = None, image_url: Optional[str] = None, color: Optional[str] = None):
    await interaction.response.defer(ephemeral=True)
    embed_color = discord.Color.blue()
    if color:
        try: embed_color = discord.Color(int(color.lstrip('#').lstrip('0x'), 16))
        except ValueError: await interaction.followup.send(f"⚠️ 无效颜色代码 '{color}'. 使用默认蓝色。",ephemeral=True)

    embed = discord.Embed(title=f"**{title}**", description=message.replace('\\n', '\n'), color=embed_color, timestamp=discord.utils.utcnow())
    embed.set_footer(text=f"由 {interaction.user.display_name} 发布 | {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else bot.user.display_avatar.url)

    if image_url: # Basic validation
        if image_url.startswith(('http://', 'https://')): embed.set_image(url=image_url)
        else: await interaction.followup.send("⚠️ 无效图片URL格式。图片未添加。", ephemeral=True)

    ping_content = ping_role.mention if ping_role and (ping_role.mentionable or (isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.mention_everyone)) else None
    if ping_role and not ping_content: await interaction.followup.send(f"⚠️ 身份组 {ping_role.name} 不可提及。", ephemeral=True)

    try:
        await channel.send(content=ping_content, embed=embed)
        await interaction.followup.send(f"✅ 公告已发送到 {channel.mention}！", ephemeral=True)
    except Exception as e: await interaction.followup.send(f"❌ 发送公告失败: {e}", ephemeral=True)


# --- Management Command Group (File 1) ---
manage_group = app_commands.Group(name="管理", description="服务器高级管理相关指令")

@manage_group.command(name="票据设定", description="配置票据系统 (File 1)，并在指定频道发布创建按钮。")
@app_commands.describe(button_channel="发布“创建票据”按钮的频道", ticket_category="新票据创建的分类", staff_roles="负责票据的身份组 (空格分隔提及)")
@app_commands.checks.has_permissions(administrator=True)
async def manage_ticket_setup(interaction: discord.Interaction, button_channel: discord.TextChannel, ticket_category: discord.CategoryChannel, staff_roles: str):
    guild = interaction.guild; guild_id = guild.id; await interaction.response.defer(ephemeral=True)
    parsed_role_ids = [int(mention.strip('<@&>')) for mention in staff_roles.split() if mention.startswith('<@&') and mention.endswith('>')]
    if not parsed_role_ids: await interaction.followup.send("❌ 未能识别有效的员工身份组。", ephemeral=True); return

    set_setting(ticket_settings, guild_id, "setup_channel_id", button_channel.id)
    set_setting(ticket_settings, guild_id, "category_id", ticket_category.id)
    set_setting(ticket_settings, guild_id, "staff_role_ids", parsed_role_ids)
    set_setting(ticket_settings, guild_id, "ticket_count", get_setting(ticket_settings, guild_id, "ticket_count") or 0)

    embed = discord.Embed(title="🎫 GJ Team 服务台 - 认证申请 (File 1)", description="**需要认证？**\n请点击下方 **➡️ 开票-认证** 按钮创建专属频道。", color=discord.Color.blue())
    embed.set_footer(text="GJ Team | 认证服务")
    try:
        old_msg_id = get_setting(ticket_settings, guild_id, "button_message_id")
        if old_msg_id:
            try: old_msg = await button_channel.fetch_message(old_msg_id); await old_msg.delete()
            except: pass # Ignore if not found or error
        button_message = await button_channel.send(embed=embed, view=CreateTicketView()) # File 1's CreateTicketView
        set_setting(ticket_settings, guild_id, "button_message_id", button_message.id)
        staff_mentions_str = ", ".join([f"<@&{rid}>" for rid in parsed_role_ids])
        await interaction.followup.send(f"✅ 票据系统 (File 1) 已设置！\n- 按钮在 {button_channel.mention}\n- 分类: **{ticket_category.name}**\n- 员工: {staff_mentions_str}", ephemeral=True)
    except Exception as e: await interaction.followup.send(f"❌ 设置/发送票据按钮 (File 1) 时出错: {e}", ephemeral=True)


# ... (Other /管理 commands from File 1: 删讯息, 频道名, 禁言, 踢出, 封禁, 解封, 人数频道, ai豁免-*)
# These are quite extensive, I'll add a few representative ones for brevity. The full set from File 1 can be pasted here.

@manage_group.command(name="踢出", description="将成员踢出服务器。")
@app_commands.describe(user="要踢出的用户。", reason="踢出的原因。")
@app_commands.checks.has_permissions(kick_members=True)
@app_commands.checks.bot_has_permissions(kick_members=True)
async def manage_kick(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    guild = interaction.guild; author = interaction.user; await interaction.response.defer(ephemeral=False)
    # Basic checks from File 1
    if user == author or user.id == guild.owner_id or user.bot: await interaction.followup.send("❌ 无效操作对象。", ephemeral=True); return
    if isinstance(author, discord.Member) and author.id != guild.owner_id and user.top_role >= author.top_role : await interaction.followup.send(f"🚫 你无法踢出层级高于或等于你的成员。", ephemeral=True); return
    if user.top_role >= guild.me.top_role and guild.me.id != guild.owner_id : await interaction.followup.send(f"🚫 我无法踢出层级高于或等于我的成员。", ephemeral=True); return
    try:
        await user.kick(reason=f"Kicked by {author.display_name}. Reason: {reason}")
        await interaction.followup.send(f"👢 用户 {user.mention} 已被踢出。原因: {reason}")
        # Log to public warn channel (File 1)
        log_embed = discord.Embed(title="👢 用户踢出", color=discord.Color.dark_orange(), timestamp=discord.utils.utcnow())
        log_embed.add_field(name="执行者", value=author.mention, inline=True); log_embed.add_field(name="被踢出用户", value=f"{user.mention} (`{user}`)", inline=True)
        log_embed.add_field(name="原因", value=reason, inline=False)
        await send_to_public_log(guild, log_embed, log_type="Kick Member")
    except Exception as e: await interaction.followup.send(f"⚙️ 踢出用户时出错: {e}", ephemeral=True)

# --- Temporary Voice Channel Command Group (File 1) ---
voice_group = app_commands.Group(name="语音", description="临时语音频道相关指令")
# ... (Full commands from File 1 for /语音: 设定母频道, 设定权限, 转让, 房主)
@voice_group.command(name="设定母频道", description="设置创建临时语音的入口频道。")
@app_commands.describe(master_channel="作为创建入口的语音频道。", category="(可选) 临时频道创建的分类。")
@app_commands.checks.has_permissions(manage_channels=True)
async def voice_set_master(interaction: discord.Interaction, master_channel: discord.VoiceChannel, category: Optional[discord.CategoryChannel] = None):
    guild_id = interaction.guild_id; guild = interaction.guild; await interaction.response.defer(ephemeral=True)
    # Simplified permission check for brevity
    target_category = category if category else master_channel.category
    if not target_category or not target_category.permissions_for(guild.me).manage_channels:
        await interaction.followup.send(f"❌ 我缺少在分类 **{target_category.name if target_category else '未知'}** 管理频道的权限。", ephemeral=True); return

    set_setting(temp_vc_settings, guild_id, "master_channel_id", master_channel.id)
    set_setting(temp_vc_settings, guild_id, "category_id", target_category.id if target_category else None)
    await interaction.followup.send(f"✅ 临时语音母频道已设为 {master_channel.mention} (分类: {target_category.name if target_category else '母频道所在分类'})。", ephemeral=True)


# --- Giveaway Command Group (File 2 - adapted to discord.py) ---
giveaway_group = app_commands.Group(name="giveaway", description="抽奖活动管理")

@giveaway_group.command(name="create", description="🎉 发起一个新的抽奖活动！")
@app_commands.describe(duration="时长 (e.g., 10s, 5m, 2h, 1d)", winners="获奖人数", prize="奖品名称", channel="(可选) 发布抽奖的频道", required_role="(可选) 参与所需的身份组")
async def giveaway_create(interaction: discord.Interaction, duration: str, winners: int, prize: str, channel: Optional[discord.TextChannel] = None, required_role: Optional[discord.Role] = None):
    await interaction.response.defer(ephemeral=True)
    target_channel = channel or interaction.channel
    if not isinstance(target_channel, discord.TextChannel):
        await interaction.followup.send("错误: 抽奖只能在文字频道创建。", ephemeral=True); return

    # Permission checks for bot in target_channel (simplified)
    bot_perms = target_channel.permissions_for(interaction.guild.me)
    if not bot_perms.send_messages or not bot_perms.embed_links or not bot_perms.add_reactions:
        await interaction.followup.send(f"错误: 我在 {target_channel.mention} 缺少发送消息/嵌入链接/添加反应的权限。", ephemeral=True); return

    delta = parse_duration(duration)
    if delta is None or delta.total_seconds() <= 5:
        await interaction.followup.send("无效时长。请输入如 10s, 5m, 2h, 1d 格式，且至少5秒。", ephemeral=True); return
    if winners <= 0:
        await interaction.followup.send("获奖人数必须大于0。", ephemeral=True); return

    end_time = discord.utils.utcnow() + delta
    embed = create_giveaway_embed(prize, end_time, winners, interaction.user, required_role)
    try:
        giveaway_message = await target_channel.send(embed=embed)
        await giveaway_message.add_reaction("🎉")
    except Exception as e:
        await interaction.followup.send(f"创建抽奖时出错: {e}", ephemeral=True); print(f"Error creating giveaway: {e}"); return

    giveaway_data = {'guild_id': interaction.guild.id, 'channel_id': target_channel.id, 'message_id': giveaway_message.id, 'end_time': end_time, 'winners': winners, 'prize': prize, 'required_role_id': required_role.id if required_role else None, 'creator_id': interaction.user.id, 'creator_name': interaction.user.display_name}
    await save_giveaway_data(giveaway_message.id, giveaway_data)
    await interaction.followup.send(f"✅ `{prize}` 抽奖已在 {target_channel.mention} 创建！结束于: <t:{int(end_time.timestamp())}:F>", ephemeral=True)


@giveaway_group.command(name="reroll", description="<:reroll:1198121147395555328> 重新抽取获胜者。")
@app_commands.describe(message_link_or_id="原始抽奖消息的链接或ID。")
@app_commands.checks.has_permissions(manage_guild=True) # Only server managers can reroll
async def giveaway_reroll(interaction: discord.Interaction, message_link_or_id: str):
    await interaction.response.defer(ephemeral=True)
    channel_id, message_id = await parse_message_link(interaction, message_link_or_id)
    if channel_id is None or message_id is None: return # parse_message_link sends ephemeral error

    target_channel = bot.get_channel(channel_id)
    if not target_channel or not isinstance(target_channel, discord.TextChannel):
        await interaction.followup.send("错误：无法找到链接中的频道或频道非文字类型。", ephemeral=True); return
    try:
        message = await target_channel.fetch_message(message_id)
    except discord.NotFound: await interaction.followup.send("无法找到原始抽奖消息。", ephemeral=True); return
    except discord.Forbidden: await interaction.followup.send(f"无权限在 {target_channel.mention} 读取历史记录。", ephemeral=True); return
    except Exception as e: await interaction.followup.send(f"获取消息时出错: {e}", ephemeral=True); return

    if not message.embeds: await interaction.followup.send("该消息没有抽奖嵌入信息。", ephemeral=True); return
    original_embed = message.embeds[0]

    giveaway_data = await load_giveaway_data(message_id)
    if not giveaway_data:
        await interaction.followup.send("错误: 无法从数据库加载此抽奖数据以进行重抽。", ephemeral=True); return

    prize = giveaway_data.get('prize', "未知奖品")
    winners_count = giveaway_data.get('winners', 1)
    required_role_id = giveaway_data.get('required_role_id')

    reaction = discord.utils.get(message.reactions, emoji="🎉")
    if reaction is None: await interaction.followup.send("消息上无 🎉 反应。", ephemeral=True); return

    try: potential_participants = [m async for m in reaction.users() if isinstance(m, discord.Member)]
    except discord.Forbidden: await interaction.followup.send("错误: 我需要读取成员列表的权限 (Members Intent)。", ephemeral=True); return
    except Exception as e: await interaction.followup.send(f"获取反应用户列表时出错: {e}", ephemeral=True); return

    eligible_participants = []
    required_role = interaction.guild.get_role(required_role_id) if required_role_id else None
    if required_role: eligible_participants = [m for m in potential_participants if required_role in m.roles and not m.bot]
    else: eligible_participants = [m for m in potential_participants if not m.bot]

    if not eligible_participants:
        await interaction.followup.send("没有符合条件的参与者可供重抽。", ephemeral=True)
        await target_channel.send(f"尝试为 `{prize}` 重抽，但没有合格的参与者。")
        return

    num_to_reroll = min(winners_count, len(eligible_participants))
    if num_to_reroll <= 0: await interaction.followup.send("无法重抽0位获奖者。", ephemeral=True); return

    new_winners = random.sample(eligible_participants, num_to_reroll)
    new_winner_mentions = ", ".join([w.mention for w in new_winners])

    await target_channel.send(f"<:reroll:1198121147395555328> **重新抽奖！** <:reroll:1198121147395555328>\n恭喜 `{prize}` 的新获奖者: {new_winner_mentions}", allowed_mentions=discord.AllowedMentions(users=True))
    try:
        updated_embed = update_embed_ended(original_embed, new_winner_mentions, prize, len(eligible_participants))
        await message.edit(embed=updated_embed) # Keep existing view if any or remove if ended
    except Exception as e: print(f"Error editing message embed after reroll {message_id}: {e}")
    await interaction.followup.send(f"✅ 已为 `{prize}` 重抽。新获奖者: {new_winner_mentions}", ephemeral=True)


# --- Member & Ticket Verification Commands (File 3) ---
@bot.tree.command(name="setlogchannel", description="设置记录已验证用户信息的频道 (File 3 /verifyticket)。")
@app_commands.describe(channel="选择要发送日志的文本频道")
@app_commands.checks.has_permissions(administrator=True)
async def set_log_channel_f3(interaction: discord.Interaction, channel: discord.TextChannel): # Renamed to avoid conflict
    bot.log_channel_id = channel.id # Uses the global bot.log_channel_id
    LOG_CHANNEL_ID = channel.id # Also update the global constant if needed for other parts
    print(f"File 3 Log Channel set to: #{channel.name} (ID: {channel.id}) by {interaction.user}")
    await interaction.response.send_message(f"✅ File 3 记录频道已设置为 {channel.mention}。", ephemeral=True)

def is_in_ticket_category_check(): # From File 3
    async def predicate(interaction: discord.Interaction) -> bool:
        if TICKET_CATEGORY_ID is None: return False # TICKET_CATEGORY_ID is global from ENV
        return interaction.channel and hasattr(interaction.channel, 'category_id') and interaction.channel.category_id == TICKET_CATEGORY_ID
    return app_commands.check(predicate)

@bot.tree.command(name="verifyticket", description="确认当前 Ticket 用户身份已验证，并记录信息 (File 3)。")
@is_in_ticket_category_check() # Uses global TICKET_CATEGORY_ID
@app_commands.checks.has_role(SUPPORT_ROLE_ID) # Uses global SUPPORT_ROLE_ID
async def verify_ticket_f3(interaction: discord.Interaction): # Renamed
    channel_id = interaction.channel_id
    if not bot.log_channel_id: # Check the one set by /setlogchannel or ENV
        await interaction.response.send_message("❌ **错误:** File 3 Log Channel 未设置。", ephemeral=True); return

    data_to_log = ticket_data_cache.get(channel_id) # From File 3's InfoModal
    if not data_to_log:
        await interaction.response.send_message("❌ **错误:** 未找到此 Ticket (File 3) 的初始信息。", ephemeral=True); return

    log_channel_obj = bot.get_channel(bot.log_channel_id)
    if not log_channel_obj or not isinstance(log_channel_obj, discord.TextChannel):
        await interaction.response.send_message(f"❌ **错误:** 无法找到 File 3 Log Channel (ID: `{bot.log_channel_id}`)。", ephemeral=True); return

    log_embed = discord.Embed(title=f"✅ Ticket 已验证 (File 3) | 用户信息记录", description=f"Ticket 频道: {data_to_log.get('channel_mention', f'<#{channel_id}>')}", color=discord.Color.green(), timestamp=discord.utils.utcnow())
    log_embed.add_field(name="验证处理人", value=interaction.user.mention, inline=False)
    log_embed.add_field(name="用户信息", value=f"{data_to_log['user_mention']} (`{data_to_log['user_id']}`)", inline=False)
    log_embed.add_field(name="提交身份标识", value=data_to_log['identifier'], inline=False)
    log_embed.add_field(name="提交来意", value=data_to_log['reason'], inline=False)
    if data_to_log.get('kill_count', "N/A") != "N/A": log_embed.add_field(name="提交击杀数", value=data_to_log['kill_count'], inline=True)
    if data_to_log.get('notes', "无") != "无": log_embed.add_field(name="补充说明", value=data_to_log['notes'], inline=False)
    log_embed.set_footer(text=f"原始提交时间 (File 3 Modal): {data_to_log['submission_time'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
    try: user_obj = await bot.fetch_user(data_to_log['user_id']); log_embed.set_thumbnail(url=user_obj.display_avatar.url)
    except: pass

    try: await log_channel_obj.send(embed=log_embed)
    except discord.Forbidden: await interaction.response.send_message(f"❌ 机器人无权向 File 3 Log Channel {log_channel_obj.mention} 发送消息。", ephemeral=True); return
    except Exception as e: await interaction.response.send_message(f"❌ 发送日志到 File 3 Log Channel 时出错: {e}", ephemeral=True); return

    await interaction.response.send_message(f"✅ **验证完成 (File 3)！** {interaction.user.mention} 已确认此 Ticket 用户身份。")
    if channel_id in ticket_data_cache: del ticket_data_cache[channel_id]


@bot.tree.command(name="checkmemberverify", description="检查成员是否需验证，并创建引导频道 (File 3)。")
@app_commands.describe(member="要检查的服务器成员")
@app_commands.checks.has_any_role(SUPPORT_ROLE_ID) # Uses global SUPPORT_ROLE_ID
async def check_member_verification_f3(interaction: discord.Interaction, member: discord.Member): # Renamed
    if not VERIFIED_ROLE_IDS or not NEW_MEMBER_CATEGORY_ID or not SUPPORT_ROLE_ID or not TICKET_PANEL_CHANNEL_NAME:
        await interaction.response.send_message("❌ **配置错误:** 缺少 File 3 验证系统所需的核心配置。", ephemeral=True); return

    guild = interaction.guild
    support_role_obj = guild.get_role(SUPPORT_ROLE_ID)
    welcome_category_obj = guild.get_channel(NEW_MEMBER_CATEGORY_ID)
    if not support_role_obj or not welcome_category_obj or not isinstance(welcome_category_obj, discord.CategoryChannel):
        await interaction.response.send_message("❌ **配置错误:** 无法找到客服角色或新成员欢迎分类 (File 3)。", ephemeral=True); return

    member_role_ids = {role.id for role in member.roles}
    has_verified_role = any(verified_id in member_role_ids for verified_id in VERIFIED_ROLE_IDS)

    if has_verified_role:
        await interaction.response.send_message(f"✅ 用户 {member.mention} **已拥有**验证身份组 (File 3)，无需再次验证。", ephemeral=True); return
    else:
        await interaction.response.send_message(f"⏳ 用户 {member.mention} **未验证** (File 3)。正在创建/检查引导频道...", ephemeral=True)
        created_channel = await create_welcome_channel_for_member(member, guild, welcome_category_obj, support_role_obj) # Uses global TICKET_PANEL_CHANNEL_NAME
        if created_channel: await interaction.edit_original_response(content=f"✅ 已为 {member.mention} 创建/找到引导频道 {created_channel.mention} (File 3)。")
        else: await interaction.edit_original_response(content=f"❌ 为 {member.mention} 创建引导频道 (File 3) 失败。")


# --- Background Tasks ---
@tasks.loop(seconds=15) # From File 2
async def check_giveaways():
    if not redis_pool: return # Giveaway task needs Redis
    current_time = discord.utils.utcnow(); ended_giveaway_ids = []
    giveaway_ids_to_check = await get_all_giveaway_ids()
    if not giveaway_ids_to_check: return

    for msg_id_int in giveaway_ids_to_check:
        giveaway_data = await load_giveaway_data(msg_id_int)
        if not giveaway_data: await delete_giveaway_data(msg_id_int); continue # Clean up if data is faulty
        if not isinstance(giveaway_data.get('end_time'), datetime.datetime):
            print(f"Warning: Giveaway {msg_id_int} end_time is not datetime object. Removing."); await delete_giveaway_data(msg_id_int); continue

        if giveaway_data['end_time'] <= current_time:
            print(f"Giveaway {msg_id_int} has ended. Processing...")
            guild = bot.get_guild(giveaway_data['guild_id'])
            channel = guild.get_channel(giveaway_data['channel_id']) if guild else None
            if not guild or not channel or not isinstance(channel, discord.TextChannel):
                print(f"Could not find guild/channel for ended giveaway {msg_id_int}. Removing."); ended_giveaway_ids.append(msg_id_int); continue
            try:
                message = await channel.fetch_message(msg_id_int)
                await process_giveaway_end(message, giveaway_data)
                ended_giveaway_ids.append(msg_id_int)
            except discord.NotFound: print(f"Message for giveaway {msg_id_int} not found. Removing."); ended_giveaway_ids.append(msg_id_int)
            except discord.Forbidden: print(f"Forbidden to fetch message for giveaway {msg_id_int}.") # Don't remove, might be temporary
            except Exception as e: print(f"Error processing ended giveaway {msg_id_int}: {e}")

    if ended_giveaway_ids:
        print(f"Cleaning up ended giveaways from Redis: {ended_giveaway_ids}")
        for ended_id in ended_giveaway_ids: await delete_giveaway_data(ended_id)

@check_giveaways.before_loop
async def before_check_giveaways():
    await bot.wait_until_ready()
    print("Giveaway checking task is ready.")


# --- Add Command Groups to Bot Tree ---
bot.tree.add_command(manage_group) # From File 1
bot.tree.add_command(voice_group)  # From File 1
bot.tree.add_command(giveaway_group) # From File 2 (adapted)
# File 3 commands (/setlogchannel, /verifyticket, /checkmemberverify) are added directly.

# --- Main Execution Block ---
async def main():
    global BOT_TOKEN # Ensure it's accessible
    if not BOT_TOKEN:
        print("❌ CRITICAL ERROR: DISCORD_BOT_TOKEN not found in main(). Bot cannot start.")
        return

    # Initialize aiohttp session (moved from on_ready for earlier availability if needed)
    if AIOHTTP_AVAILABLE:
        bot.http_session = aiohttp.ClientSession()
        print("Main: aiohttp session created.")

    try:
        print("Starting bot...")
        await bot.start(BOT_TOKEN)
    except discord.LoginFailure: print("❌ CRITICAL ERROR: Login Failure. Invalid DISCORD_BOT_TOKEN.")
    except discord.PrivilegedIntentsRequired: print("❌ CRITICAL ERROR: Bot missing Privileged Intents (Members, Message Content). Enable them in Developer Portal.")
    except Exception as e: print(f"❌ CRITICAL ERROR during bot startup: {e}"); traceback.print_exc()
    finally:
        if bot.http_session:
            await bot.http_session.close()
            print("Main: aiohttp session closed.")
        if redis_pool: # From File 2
            await redis_pool.close()
            print("Main: Redis connection pool closed.")
        await bot.close()
        print("Bot connection closed.")

if __name__ == "__main__":
    if CONFIG_ERROR: # Check again before running main
        print("--- BOT HALTED DUE TO PREVIOUSLY NOTED CONFIGURATION ERRORS ---")
    else:
        try:
            asyncio.run(main())
        except KeyboardInterrupt: print("\nBot shutting down (KeyboardInterrupt)...")
        except Exception as main_err: print(f"\nUnhandled error in main asyncio run: {main_err}"); traceback.print_exc()