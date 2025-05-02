# slash_role_manager_bot.py (FINAL COMPLETE CODE v23 - Ticket Tool Added)

import discord
from discord import app_commands, ui # Added ui
from discord.ext import commands
from discord.utils import get
import os
import datetime
import asyncio
from typing import Optional, Union
import requests # Required for DeepSeek API & Announce fallback
import json     # Required for DeepSeek API
try:
    import aiohttp # Preferred for async requests in announce
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    print("⚠️ 警告: 未安装 'aiohttp' 库。 /announce 中的图片URL验证将使用 'requests' (可能阻塞)。建议运行: pip install aiohttp")


# --- Configuration ---
# !!! 重要：从环境变量加载 Bot Token !!!
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ 致命错误：未设置 DISCORD_BOT_TOKEN 环境变量。")
    print("   请在你的托管环境（例如 Railway Variables）中设置此变量。")
    exit()

# !!! 重要：从环境变量加载 DeepSeek API Key !!!
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    print("⚠️ 警告：未设置 DEEPSEEK_API_KEY 环境变量。DeepSeek 内容审核功能将被禁用。")

# !!! 重要：确认 DeepSeek API 端点和模型名称 !!!
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions" # <--- 确认 DeepSeek API URL!
DEEPSEEK_MODEL = "deepseek-chat" # <--- 替换为你希望使用的 DeepSeek 模型!

COMMAND_PREFIX = "!" # 旧版前缀（现在主要使用斜线指令）

# --- Intents Configuration ---
# 确保这些也在 Discord 开发者门户中启用了！
intents = discord.Intents.default()
intents.members = True      # 需要用于 on_member_join, 成员信息, 成员指令
intents.message_content = True # 需要用于 on_message 刷屏/违禁词检测
intents.voice_states = True # 需要用于临时语音频道功能
intents.guilds = True       # 需要用于票据功能和其他服务器信息获取

# --- Bot Initialization ---
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

# --- Spam Detection & Mod Alert Config ---
SPAM_COUNT_THRESHOLD = 5       # 用户刷屏阈值：消息数量
SPAM_TIME_WINDOW_SECONDS = 5   # 用户刷屏时间窗口（秒）
KICK_THRESHOLD = 3             # 警告多少次后踢出
BOT_SPAM_COUNT_THRESHOLD = 8   # Bot 刷屏阈值：消息数量
BOT_SPAM_TIME_WINDOW_SECONDS = 3 # Bot 刷屏时间窗口（秒）

# !!! 重要：替换成你的管理员/Mod身份组ID列表 !!!
MOD_ALERT_ROLE_IDS = [
    1362713317222912140, # <--- 替换! 示例 ID (用于通用警告)
    1362713953960198216  # <--- 替换! 示例 ID
]

# --- Public Warning Log Channel Config ---
# !!! 重要：替换成你的警告/消除警告公开通知频道ID !!!
PUBLIC_WARN_LOG_CHANNEL_ID = 1363523347169939578 # <--- 替换! 示例 ID

# --- Bad Word Detection Config & Storage (In-Memory) ---
# !!! 【警告】仔细审查并【大幅删减】此列表，避免误判 !!!
# !!! 如果你完全信任 DeepSeek API 的判断，可以清空或注释掉这个列表 !!!
BAD_WORDS = [
    "操你妈", "草泥马", "cnm", "日你妈", "rnm", "屌你老母", "屌你媽", "死妈", "死媽", "nmsl", "死全家", "死全家",
    "杂种", "雜種", "畜生", "畜牲", "狗娘养的", "狗娘養的", "贱人", "賤人", "婊子", "bitch", "傻逼", "煞笔", "sb", "脑残", "腦殘",
    "智障", "弱智", "低能", "白痴", "白癡", "废物", "廢物", "垃圾", "lj", "kys", "去死", "自杀", "自殺", "杀你", "殺你",
    "他妈的", "他媽的", "tmd", "妈的", "媽的", "卧槽", "我肏", "我操", "我草", "靠北", "靠杯", "干你娘", "干您娘",
    "fuck", "shit", "cunt", "asshole", "鸡巴", "雞巴", "jb",
]
BAD_WORDS_LOWER = [word.lower() for word in BAD_WORDS]

# 记录用户首次触发提醒 {guild_id: {user_id: {lowercase_word}}}
user_first_offense_reminders = {}

# --- General Settings Storage (In-Memory) ---
# 用于存储各种非特定功能的设置，例如日志频道、公告频道等
general_settings = {} # {guild_id: {"log_channel_id": int, "announce_channel_id": int}}

# --- Temporary Voice Channel Config & Storage (In-Memory) ---
temp_vc_settings = {}  # {guild_id: {"master_channel_id": id, "category_id": id, "member_count_channel_id": id, "member_count_template": str}}
temp_vc_owners = {}    # {channel_id: owner_user_id}
temp_vc_created = set()  # {channel_id1, channel_id2, ...}

# --- Ticket Tool Config & Storage (In-Memory) ---
# 使用 guild_id 作为键
ticket_settings = {} # {guild_id: {"setup_channel_id": int, "category_id": int, "staff_role_ids": list[int], "button_message_id": int, "ticket_count": int}}
open_tickets = {} # {guild_id: {user_id: channel_id}} # 记录每个用户当前打开的票据

# In-memory storage for spam warnings
user_message_timestamps = {} # {user_id: [timestamp1, timestamp2]}
user_warnings = {}           # {user_id: warning_count}
bot_message_timestamps = {}  # {bot_user_id: [timestamp1, timestamp2]}

# --- AI Content Check Exemption Storage (In-Memory) ---
# !!! 注意：这些列表在机器人重启后会丢失，除非使用数据库存储 !!!
exempt_users_from_ai_check = set() # 存储用户 ID (int)
exempt_channels_from_ai_check = set() # 存储频道 ID (int)

# --- Helper Function to Get/Set Settings (Simulated DB) ---
# 注意：这只是内存中的模拟，重启会丢失数据
# 修改为接受一个字典作为存储目标
def get_setting(store: dict, guild_id: int, key: str):
    """从指定的内存字典中获取服务器设置"""
    return store.get(guild_id, {}).get(key)

def set_setting(store: dict, guild_id: int, key: str, value):
    """设置服务器设置到指定的内存字典"""
    if guild_id not in store:
        store[guild_id] = {}
    store[guild_id][key] = value
    # Less verbose logging for settings now
    # print(f"[内存设置更新 @ {id(store)}] 服务器 {guild_id}: {key}={value}")

# --- Helper Function to Send to Public Log Channel ---
async def send_to_public_log(guild: discord.Guild, embed: discord.Embed, log_type: str = "Generic"):
    """发送 Embed 消息到公共日志频道"""
    log_channel_id_for_public = PUBLIC_WARN_LOG_CHANNEL_ID # 使用配置的公共日志频道 ID
    if not log_channel_id_for_public or log_channel_id_for_public == 123456789012345682: # 检查是否为默认示例ID
        # print(f"   ℹ️ 未配置有效的公共日志频道 ID，跳过发送公共日志 ({log_type})。")
        return False # 如果未设置或还是示例ID，则不发送

    log_channel = guild.get_channel(log_channel_id_for_public)
    if log_channel and isinstance(log_channel, discord.TextChannel):
        bot_perms = log_channel.permissions_for(guild.me)
        if bot_perms.send_messages and bot_perms.embed_links:
            try:
                await log_channel.send(embed=embed)
                print(f"   ✅ 已发送公共日志 ({log_type}) 到频道 {log_channel.name} ({log_channel.id})。")
                return True
            except discord.Forbidden:
                print(f"   ❌ 错误：机器人缺少在公共日志频道 {log_channel_id_for_public} 发送消息或嵌入链接的权限。")
            except Exception as log_e:
                print(f"   ❌ 发送公共日志时发生意外错误 ({log_type}): {log_e}")
        else:
            print(f"   ❌ 错误：机器人在公共日志频道 {log_channel_id_for_public} 缺少发送消息或嵌入链接的权限。")
    else:
         # Check if the ID is the default placeholder before printing warning
         if log_channel_id_for_public != 1363523347169939578:
             print(f"⚠️ 在服务器 {guild.name} ({guild.id}) 中找不到公共日志频道 ID: {log_channel_id_for_public}。")
    return False

# --- Helper Function: DeepSeek API Content Check (Returns Chinese Violation Type) ---
async def check_message_with_deepseek(message_content: str) -> Optional[str]:
    """使用 DeepSeek API 检查内容。返回中文违规类型或 None。"""
    if not DEEPSEEK_API_KEY:
        # print("DEBUG: DeepSeek API Key 未设置，跳过检查。")
        return None # Skip if no key

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }

    # !!! --- 重要：设计和优化你的 Prompt --- !!!
    # --- V2: 要求返回中文分类 ---
    prompt = f"""
    请分析以下 Discord 消息内容是否包含严重的违规行为。
    严重违规分类包括：仇恨言论、骚扰/欺凌、露骨的 NSFW 内容、严重威胁。
    - 如果检测到明确的严重违规，请【仅】返回对应的中文分类名称（例如：“仇恨言论”）。
    - 如果内容包含一些轻微问题（如刷屏、普通脏话）但【不构成】上述严重违规，请【仅】返回：“轻微违规”。
    - 如果内容安全，没有任何违规，请【仅】返回：“安全”。

    消息内容：“{message_content}”
    分析结果："""
    # !!! --- Prompt 结束 --- !!!

    data = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 30, # 限制返回长度，只需要分类名称
        "temperature": 0.1, # 较低的温度，追求更确定的分类
        "stream": False
    }

    loop = asyncio.get_event_loop()
    try:
        # 使用 run_in_executor 避免阻塞事件循环
        response = await loop.run_in_executor(
            None,
            lambda: requests.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=8) # 设置超时
        )
        response.raise_for_status() # 检查 HTTP 错误
        result = response.json()
        api_response_text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

        # print(f"DEBUG: DeepSeek 对 '{message_content[:30]}...' 的响应: {api_response_text}") # Debug log

        # --- 处理中文响应 ---
        if not api_response_text: # 空响应视为安全
             return None
        if api_response_text == "安全":
            return None
        if api_response_text == "轻微违规":
             # 对于轻微违规，我们目前也视为不需要机器人直接干预（交给刷屏或本地违禁词处理）
             return None
        # 如果不是 "安全" 或 "轻微违规"，则假定返回的是中文的严重违规类型
        # （例如 “仇恨言论”, “骚扰/欺凌” 等）
        return api_response_text

    except requests.exceptions.Timeout:
        print(f"❌ 调用 DeepSeek API 超时")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ 调用 DeepSeek API 时发生网络错误: {e}")
        return None
    except json.JSONDecodeError:
        print(f"❌ 解析 DeepSeek API 响应失败 (非 JSON): {response.text}")
        return None
    except Exception as e:
        print(f"❌ DeepSeek 检查期间发生意外错误: {e}")
        return None

# --- Ticket Tool UI Views ---

# View for the button to close a ticket
class CloseTicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Buttons inside tickets should persist

    @ui.button(label="关闭票据", style=discord.ButtonStyle.danger, custom_id="close_ticket_button")
    async def close_button(self, interaction: discord.Interaction, button: ui.Button):
        guild = interaction.guild
        channel = interaction.channel
        user = interaction.user # The user clicking the close button

        if not guild or not isinstance(channel, discord.TextChannel):
             await interaction.response.send_message("❌ 操作无法在此处完成。", ephemeral=True)
             return

        # --- 权限检查: 票据创建者 或 票据员工 或 有管理频道权限的人 ---
        # 1. 查找票据创建者ID (从 open_tickets 反查)
        creator_id = None
        guild_tickets = open_tickets.get(guild.id, {})
        for uid, chan_id in guild_tickets.items():
            if chan_id == channel.id:
                creator_id = uid
                break

        is_creator = (creator_id == user.id)

        # 2. 检查票据员工
        staff_role_ids = get_setting(ticket_settings, guild.id, "staff_role_ids") or []
        is_staff = False
        if isinstance(user, discord.Member): # Ensure user is a Member object to check roles
             is_staff = any(role.id in staff_role_ids for role in user.roles)

        # 3. 检查通用管理权限
        can_manage_channels = channel.permissions_for(user).manage_channels

        if not is_creator and not is_staff and not can_manage_channels:
            await interaction.response.send_message("❌ 你没有权限关闭此票据。只有票据创建者或指定员工可以关闭。", ephemeral=True)
            return

        # --- 执行关闭 ---
        await interaction.response.defer(ephemeral=True) # Acknowledge button click privately
        await channel.send(f"⏳ {user.mention} 已请求关闭此票据，频道将在几秒后删除...")
        print(f"[票据] 用户 {user} ({user.id}) 正在关闭票据频道 #{channel.name} ({channel.id})")

        # (可选) 记录日志
        log_embed = discord.Embed(
            title="🎫 票据已关闭",
            description=f"票据频道 **#{channel.name}** 已被关闭。",
            color=discord.Color.greyple(),
            timestamp=discord.utils.utcnow()
        )
        log_embed.add_field(name="关闭者", value=user.mention, inline=True)
        log_embed.add_field(name="频道 ID", value=str(channel.id), inline=True)
        if creator_id:
           creator_mention = f"<@{creator_id}>"
           try:
               creator_user = await bot.fetch_user(creator_id)
               creator_mention = f"{creator_user.mention} (`{creator_user}`)"
           except: pass # Keep ID if fetch fails
           log_embed.add_field(name="创建者", value=creator_mention, inline=True)
        await send_to_public_log(guild, log_embed, log_type="Ticket Closed")

        # 从 open_tickets 中移除记录
        if creator_id and guild.id in open_tickets and creator_id in open_tickets[guild.id]:
            if open_tickets[guild.id][creator_id] == channel.id:
                 del open_tickets[guild.id][creator_id]
                 print(f"   - 已从 open_tickets 移除记录 (用户: {creator_id}, 频道: {channel.id})")

        # 延迟几秒让用户看到消息，然后删除频道
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"票据由 {user.name} 关闭")
            print(f"   - 已成功删除票据频道 #{channel.name}")
            await interaction.followup.send("✅ 票据频道已删除。", ephemeral=True)
        except discord.Forbidden:
             print(f"   - 删除票据频道 #{channel.name} 失败：机器人缺少权限。")
             await interaction.followup.send("❌ 无法删除频道：机器人缺少权限。", ephemeral=True)
        except discord.NotFound:
             print(f"   - 删除票据频道 #{channel.name} 失败：频道未找到 (可能已被删除)。")
             # No need to followup if channel is already gone
        except Exception as e:
            print(f"   - 删除票据频道 #{channel.name} 时发生错误: {e}")
            try:
                await interaction.followup.send(f"❌ 删除频道时发生错误: {e}", ephemeral=True)
            except discord.NotFound: pass # Interaction might be gone


# View for the initial "Create Ticket" button (Persistent)
class CreateTicketView(ui.View):
    def __init__(self):
        # timeout=None 使按钮在机器人重启后仍然有效
        # 需要在 on_ready 中使用 bot.add_view(CreateTicketView()) 注册
        super().__init__(timeout=None)

    @ui.button(label="➡️ 开票-认证", style=discord.ButtonStyle.primary, custom_id="create_verification_ticket")
    async def create_ticket_button(self, interaction: discord.Interaction, button: ui.Button):
        guild = interaction.guild
        user = interaction.user
        if not guild: return # Should not happen with slash commands

        print(f"[票据] 用户 {user} ({user.id}) 在服务器 {guild.id} 点击了创建票据按钮。")
        await interaction.response.defer(ephemeral=True) # Acknowledge privately first

        # --- 检查设置是否完整 ---
        category_id = get_setting(ticket_settings, guild.id, "category_id")
        staff_role_ids = get_setting(ticket_settings, guild.id, "staff_role_ids")

        if not category_id or not staff_role_ids:
            await interaction.followup.send("❌ 抱歉，票据系统尚未完全配置。请联系管理员使用 `/管理 票据设定` 进行设置。", ephemeral=True)
            print(f"   - 票据创建失败：服务器 {guild.id} 未配置票据分类或员工身份组。")
            return

        ticket_category = guild.get_channel(category_id)
        if not ticket_category or not isinstance(ticket_category, discord.CategoryChannel):
            await interaction.followup.send("❌ 抱歉，配置的票据分类无效或已被删除。请联系管理员。", ephemeral=True)
            print(f"   - 票据创建失败：服务器 {guild.id} 配置的票据分类 ({category_id}) 无效。")
            # 考虑清除无效设置: set_setting(ticket_settings, guild.id, "category_id", None)
            return

        staff_roles = [guild.get_role(role_id) for role_id in staff_role_ids]
        staff_roles = [role for role in staff_roles if role] # 过滤掉未找到的角色
        if not staff_roles:
             await interaction.followup.send("❌ 抱歉，配置的票据员工身份组无效或已被删除。请联系管理员。", ephemeral=True)
             print(f"   - 票据创建失败：服务器 {guild.id} 配置的员工身份组 ({staff_role_ids}) 均无效。")
             # 考虑清除无效设置: set_setting(ticket_settings, guild.id, "staff_role_ids", [])
             return

        # --- 检查用户是否已有票据 ---
        guild_tickets = open_tickets.setdefault(guild.id, {})
        if user.id in guild_tickets:
            existing_channel_id = guild_tickets[user.id]
            existing_channel = guild.get_channel(existing_channel_id)
            if existing_channel:
                 await interaction.followup.send(f"⚠️ 你已经有一个开启的票据：{existing_channel.mention}。请先处理完当前的票据。", ephemeral=True)
                 print(f"   - 票据创建失败：用户 {user.id} 已有票据频道 {existing_channel_id}")
                 return
            else:
                 # 如果频道不存在但记录还在，清理记录
                 print(f"   - 清理无效票据记录：用户 {user.id} 的票据频道 {existing_channel_id} 不存在。")
                 del guild_tickets[user.id]

        # --- 检查机器人权限 ---
        bot_perms = ticket_category.permissions_for(guild.me)
        if not bot_perms.manage_channels or not bot_perms.manage_permissions:
             await interaction.followup.send("❌ 创建票据失败：机器人缺少在票据分类中 '管理频道' 或 '管理权限' 的权限。", ephemeral=True)
             print(f"   - 票据创建失败：机器人在分类 {ticket_category.id} 缺少权限。")
             return

        # await interaction.followup.send("⏳ 正在为你创建认证票据...", ephemeral=True) # Already deferred

        # --- 创建票据频道 ---
        # 获取并增加票据计数器
        ticket_count = get_setting(ticket_settings, guild.id, "ticket_count") or 0
        ticket_count += 1
        set_setting(ticket_settings, guild.id, "ticket_count", ticket_count)

        # 定义权限
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False), # @everyone 不可见
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True), # 创建者权限
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_permissions=True, embed_links=True, read_message_history=True) # 机器人权限
        }
        # 添加员工角色权限
        staff_mentions = []
        for role in staff_roles:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True, attach_files=True, embed_links=True) # 员工权限
            staff_mentions.append(role.mention)
        staff_mention_str = " ".join(staff_mentions)

        # 创建频道名称
        # Sanitize username for channel name
        sanitized_username = "".join(c for c in user.name if c.isalnum() or c in ('-', '_')).lower()
        if not sanitized_username: sanitized_username = "user" # Fallback if name has no valid chars
        channel_name = f"认证-{ticket_count:04d}-{sanitized_username}"[:100] # 限制长度
        new_channel = None # Initialize before try block
        try:
            new_channel = await guild.create_text_channel(
                name=channel_name,
                category=ticket_category,
                overwrites=overwrites,
                topic=f"用户 {user.id} ({user}) 的认证票据 | 创建时间: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}", # 在Topic中记录信息
                reason=f"用户 {user.name} 创建认证票据"
            )
            print(f"   - 已成功创建票据频道: #{new_channel.name} ({new_channel.id})")

            # 记录打开的票据
            guild_tickets[user.id] = new_channel.id

            # --- 在新频道发送欢迎消息和关闭按钮 ---
            welcome_embed = discord.Embed(
                title="📝 欢迎进行认证！",
                description=(
                    f"你好 {user.mention}！\n\n"
                    "请在此频道提供你的认证信息。\n"
                    "例如：\n"
                    "- 你的游戏内ID (IGN)\n"
                    "- 相关截图或证明\n"
                    "- 你希望认证的项目 (例如 TSB 实力认证)\n\n"
                    f"我们的认证团队 ({staff_mention_str}) 会尽快处理你的请求。\n\n"
                    "完成后或需要取消，请点击下方的 **关闭票据** 按钮。"
                ),
                color=discord.Color.green()
            )
            welcome_embed.set_footer(text=f"票据 ID: {new_channel.id}")

            await new_channel.send(content=f"{user.mention} {staff_mention_str}", embed=welcome_embed, view=CloseTicketView())

            # 编辑给用户的临时消息，告知成功
            await interaction.followup.send(f"✅ 你的认证票据已创建：{new_channel.mention}", ephemeral=True)

        except discord.Forbidden:
             await interaction.followup.send("❌ 创建票据失败：机器人权限不足，无法创建频道或设置权限。", ephemeral=True)
             print(f"   - 票据创建失败：机器人在创建频道时权限不足。")
             # 回滚计数器和记录
             set_setting(ticket_settings, guild.id, "ticket_count", ticket_count - 1)
             if user.id in guild_tickets: del guild_tickets[user.id]
        except discord.HTTPException as http_err:
             await interaction.followup.send(f"❌ 创建票据时发生网络错误: {http_err}", ephemeral=True)
             print(f"   - 票据创建失败：网络错误 {http_err}")
             set_setting(ticket_settings, guild.id, "ticket_count", ticket_count - 1)
             if user.id in guild_tickets: del guild_tickets[user.id]
        except Exception as e:
            await interaction.followup.send(f"❌ 创建票据时发生未知错误: {e}", ephemeral=True)
            print(f"   - 票据创建失败：未知错误 {e}")
            set_setting(ticket_settings, guild.id, "ticket_count", ticket_count - 1)
            if user.id in guild_tickets: del guild_tickets[user.id]
            # If channel was somehow created before error, try to delete it
            if new_channel:
                try: await new_channel.delete(reason="创建过程中出错")
                except: pass


# --- Event: Bot Ready ---
@bot.event
async def on_ready():
    print(f'以 {bot.user.name} ({bot.user.id}) 身份登录')
    print('正在同步应用程序命令...')
    try:
        synced = await bot.tree.sync()
        print(f'已全局同步 {len(synced)} 个应用程序命令。')
    except Exception as e:
        print(f'同步命令时出错: {e}')

    # --- 注册持久化视图 ---
    if not bot.persistent_views_added: # 加一个标志防止重复添加
        bot.add_view(CreateTicketView())
        bot.add_view(CloseTicketView()) # 关闭按钮也需要持久化
        bot.persistent_views_added = True
        print("已注册持久化视图 (CreateTicketView, CloseTicketView)。")

    # --- 初始化 aiohttp session ---
    if AIOHTTP_AVAILABLE and not hasattr(bot, 'http_session'):
         bot.http_session = aiohttp.ClientSession()
         print("已创建 aiohttp 会话。")

    print('机器人已准备就绪！')
    print('------')
    # 设置机器人状态
    await bot.change_presence(activity=discord.Game(name="/help 显示帮助"))

# 初始化持久化视图标志
bot.persistent_views_added = False


# --- Event: Command Error Handling (Legacy Prefix Commands) ---
@bot.event
async def on_command_error(ctx, error):
    # 这个主要处理旧的 ! 前缀命令错误，现在用得少了
    if isinstance(error, commands.CommandNotFound):
        return # 忽略未找到的旧命令
    elif isinstance(error, commands.MissingPermissions):
        try:
            await ctx.send(f"🚫 你缺少使用此旧命令所需的权限: {', '.join(error.missing_permissions)}")
        except discord.Forbidden:
            pass # 无法发送消息就算了
    elif isinstance(error, commands.BotMissingPermissions):
         try:
            await ctx.send(f"🤖 我缺少执行此旧命令所需的权限: {', '.join(error.missing_permissions)}")
         except discord.Forbidden:
             pass
    else:
        print(f"处理旧命令 '{ctx.command}' 时出错: {error}")


# --- Event: App Command Error Handling (Slash Commands) ---
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    error_message = "🤔 处理指令时发生了未知错误。"
    ephemeral_response = True # 默认发送临时消息

    if isinstance(error, app_commands.CommandNotFound):
        error_message = "❓ 未知的指令。"
    elif isinstance(error, app_commands.MissingPermissions):
        missing_perms = ', '.join(f'`{p}`' for p in error.missing_permissions)
        error_message = f"🚫 你缺少执行此指令所需的权限: {missing_perms}。"
    elif isinstance(error, app_commands.BotMissingPermissions):
        missing_perms = ', '.join(f'`{p}`' for p in error.missing_permissions)
        error_message = f"🤖 我缺少执行此指令所需的权限: {missing_perms}。"
    elif isinstance(error, app_commands.CheckFailure):
        # 这个通常是自定义检查（如 is_owner()）失败，或者不满足 @checks 装饰器条件
        error_message = "🚫 你不满足使用此指令的条件或权限。"
    elif isinstance(error, app_commands.CommandOnCooldown):
         error_message = f"⏳ 指令冷却中，请在 {error.retry_after:.2f} 秒后重试。"
    elif isinstance(error, app_commands.CommandInvokeError):
        original = error.original # 获取原始错误
        print(f"指令 '{interaction.command.name if interaction.command else '未知'}' 执行失败: {type(original).__name__} - {original}") # 在后台打印详细错误
        if isinstance(original, discord.Forbidden):
            error_message = f"🚫 Discord权限错误：我无法执行此操作（通常是身份组层级问题或频道权限不足）。请检查机器人的权限和身份组位置。"
        elif isinstance(original, discord.HTTPException):
             error_message = f"🌐 网络错误：与 Discord API 通信时发生问题 (HTTP {original.status})。请稍后重试。"
        elif isinstance(original, TimeoutError): # Catch asyncio.TimeoutError
              error_message = "⏱️ 操作超时，请稍后重试。"
        else:
            error_message = f"⚙️ 执行指令时发生内部错误。请联系管理员。错误类型: {type(original).__name__}" # 对用户显示通用错误
    else:
        # 其他未预料到的 AppCommandError
        print(f'未处理的应用指令错误类型: {type(error).__name__} - {error}')
        error_message = f"🔧 处理指令时发生意外错误: {type(error).__name__}"

    try:
        # 尝试发送错误信息
        if interaction.response.is_done():
            await interaction.followup.send(error_message, ephemeral=ephemeral_response)
        else:
            await interaction.response.send_message(error_message, ephemeral=ephemeral_response)
    except discord.NotFound:
        # If the interaction is gone (e.g., user dismissed), just log
        print(f"无法发送错误消息，交互已失效: {error_message}")
    except Exception as e:
        # 如果连发送错误消息都失败了，就在后台打印
        print(f"发送错误消息时也发生错误: {e}")

# 将错误处理函数绑定到 bot 的指令树
bot.tree.on_error = on_app_command_error

# --- Event: Member Join - Assign Separator Roles & Welcome ---
@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    print(f'[+] 成员加入: {member.name} ({member.id}) 加入了服务器 {guild.name} ({guild.id})')

    # --- 自动分配分隔线身份组 ---
    # !!! 重要：将下面的身份组名称替换为你服务器中实际的分隔线身份组名称 !!!
    separator_role_names_to_assign = [
        "▽─────————─────身份─────————─────",
        "▽─────————─────通知─────————─────",
        "▽─────————─────其他─────————─────"
    ] # <--- 替换成你实际的身份组名称!

    roles_to_add = []
    roles_failed = [] # 记录失败的身份组和原因

    for role_name in separator_role_names_to_assign:
        role = get(guild.roles, name=role_name)
        if role:
            # 检查机器人是否有权限分配该身份组（层级检查）
            if role < guild.me.top_role or guild.me == guild.owner:
                roles_to_add.append(role)
            else:
                roles_failed.append(f"'{role_name}' (机器人层级低于该身份组)")
        else:
            roles_failed.append(f"'{role_name}' (未在服务器中找到)")

    if roles_to_add:
        try:
            await member.add_roles(*roles_to_add, reason="新成员自动分配分隔线身份组")
            added_names = ', '.join([r.name for r in roles_to_add])
            print(f"   ✅ 已为 {member.name} 分配身份组: {added_names}")
        except discord.Forbidden:
            print(f"   ❌ 为 {member.name} 分配身份组失败：机器人缺少 '管理身份组' 权限。")
            roles_failed.extend([f"'{r.name}' (权限不足)" for r in roles_to_add])
        except discord.HTTPException as e:
             print(f"   ❌ 为 {member.name} 分配身份组时发生网络错误: {e}")
             roles_failed.extend([f"'{r.name}' (网络错误)" for r in roles_to_add])
        except Exception as e:
            print(f"   ❌ 为 {member.name} 分配身份组时发生未知错误: {e}")
            roles_failed.extend([f"'{r.name}' (未知错误)" for r in roles_to_add])

    if roles_failed:
        print(f"   ‼️ 部分身份组未能成功分配给 {member.name}: {', '.join(roles_failed)}")

    # --- (可选) 发送欢迎消息 ---
    # !!! 重要：将下面的频道 ID 替换为你服务器的实际频道 ID !!!
    welcome_channel_id = 1280014596765126669      # <--- 替换! 欢迎频道 ID
    rules_channel_id = 1280026139326283799        # <--- 替换! 规则频道 ID
    roles_info_channel_id = 1362718781498986497   # <--- 替换! 身份组信息频道 ID
    verification_channel_id = 1352886274691956756 # <--- 替换! 验证频道 ID (或票据开启频道)

    # 检查欢迎频道ID是否有效且不是默认示例ID
    if not welcome_channel_id or welcome_channel_id == 123456789012345678:
         # print("   ℹ️ 未配置有效的欢迎频道 ID，跳过发送欢迎消息。")
         return # 如果未设置或还是示例ID，则不发送

    welcome_channel = guild.get_channel(welcome_channel_id)
    if welcome_channel and isinstance(welcome_channel, discord.TextChannel):
        # 检查机器人是否有在欢迎频道发送消息和嵌入链接的权限
        welcome_perms = welcome_channel.permissions_for(guild.me)
        if welcome_perms.send_messages and welcome_perms.embed_links:
            try:
                # 动态获取票据设置中的认证频道ID (如果已设置)
                ticket_setup_channel_id = get_setting(ticket_settings, guild.id, "setup_channel_id")
                verification_link = f"<#{verification_channel_id}>" # Default link
                if ticket_setup_channel_id:
                     verification_link = f"<#{ticket_setup_channel_id}> (点击按钮开票)" # Link to ticket creation channel


                embed = discord.Embed(
                    title=f"🎉 欢迎来到 {guild.name}! 🎉",
                    description=(
                        f"你好 {member.mention}! 很高兴你能加入 **GJ Team**！\n\n"
                        f"👇 **开始之前，请务必查看:**\n"
                        f"- 服务器规则: <#{rules_channel_id}>\n"
                        f"- 身份组信息: <#{roles_info_channel_id}>\n"
                        f"- 认证申请: {verification_link}\n\n" # Updated link
                        f"祝你在 **GJ Team** 玩得愉快！"
                     ),
                    color=discord.Color.blue() # 蓝色
                )
                embed.set_thumbnail(url=member.display_avatar.url) # 使用成员的头像
                embed.set_footer(text=f"你是服务器的第 {guild.member_count} 位成员！")
                embed.timestamp = datetime.datetime.now(datetime.timezone.utc) # 加入时间戳

                await welcome_channel.send(embed=embed)
                print(f"   ✅ 已在频道 {welcome_channel.name} 发送对 {member.name} 的欢迎消息。")
            except discord.Forbidden:
                 print(f"   ❌ 发送欢迎消息失败：机器人缺少在欢迎频道 {welcome_channel_id} 发送消息或嵌入链接的权限。")
            except Exception as e:
                print(f"   ❌ 发送欢迎消息时发生错误: {e}")
        else:
            print(f"   ❌ 发送欢迎消息失败：机器人在欢迎频道 {welcome_channel_id} 缺少发送消息或嵌入链接的权限。")
    else:
        # Check if the ID is the default placeholder before printing warning
        if welcome_channel_id != 1280014596765126669:
             print(f"⚠️ 在服务器 {guild.name} 中找不到欢迎频道 ID: {welcome_channel_id}。")


# --- Event: On Message - Handles Content Check, Spam ---
@bot.event
async def on_message(message: discord.Message):
    # --- 基本过滤 ---
    if not message.guild: return
    if message.author.bot:
        # 允许处理机器人刷屏检测，但要确保不是自己
        if message.author.id == bot.user.id: return
        # Let bot spam detection handle other bots
        pass
    # --- 获取常用变量 ---
    now = datetime.datetime.now(datetime.timezone.utc)
    author = message.author
    author_id = author.id
    guild = message.guild
    channel = message.channel
    member = guild.get_member(author_id) # Fetch member object for permissions

    # --- 忽略管理员/版主的消息 (基于'管理消息'权限) ---
    # Check if member exists and has manage_messages permission
    if member and isinstance(channel, (discord.TextChannel, discord.Thread)) and channel.permissions_for(member).manage_messages:
        # Don't return yet, allow prefix command processing if needed
        pass # Admins/Mods are exempt from content/spam checks below
    else: # Apply checks for normal users
        # --- 标记是否需要进行内容检查 (AI + 本地违禁词) ---
        perform_content_check = True
        if author_id in exempt_users_from_ai_check: perform_content_check = False
        elif channel.id in exempt_channels_from_ai_check: perform_content_check = False

        # --- 执行内容检查 (仅当未被豁免时) ---
        if perform_content_check:
            # --- 1. DeepSeek API 内容审核 ---
            violation_type = await check_message_with_deepseek(message.content)
            if violation_type:
                print(f"🚫 API 违规 ({violation_type}): 用户 {author} 在频道 #{channel.name}")
                reason_api = f"自动检测到违规内容 ({violation_type})"
                delete_success = False
                try:
                    if channel.permissions_for(guild.me).manage_messages:
                        await message.delete()
                        print("   - 已删除违规消息 (API 检测)。")
                        delete_success = True
                    else: print("   - 机器人缺少 '管理消息' 权限，无法删除。")
                except discord.NotFound: delete_success = True; print("   - 尝试删除消息时未找到该消息 (可能已被删除)。")
                except discord.Forbidden: print("   - 尝试删除消息时权限不足。")
                except Exception as del_e: print(f"   - 删除消息时发生错误 (API 检测): {del_e}")

                mod_mentions = " ".join([f"<@&{role_id}>" for role_id in MOD_ALERT_ROLE_IDS])
                log_embed_api = discord.Embed(title=f"🚨 自动内容审核提醒 ({violation_type}) 🚨", color=discord.Color.dark_red(), timestamp=now)
                log_embed_api.add_field(name="用户", value=f"{author.mention} ({author_id})", inline=False)
                log_embed_api.add_field(name="频道", value=channel.mention, inline=False)
                log_embed_api.add_field(name="内容摘要", value=f"```{message.content[:1000]}```", inline=False)
                log_embed_api.add_field(name="消息状态", value="已删除" if delete_success else "删除失败/无权限", inline=True)
                log_embed_api.add_field(name="消息链接", value=f"[原始链接]({message.jump_url}) (可能已删除)", inline=True)
                log_embed_api.add_field(name="建议操作", value=f"{mod_mentions} 请管理员审核并处理！", inline=False)
                await send_to_public_log(guild, log_embed_api, log_type=f"API Violation ({violation_type})")
                return # Stop processing this message

            # --- 2. 本地违禁词检测 ---
            if not violation_type and BAD_WORDS_LOWER:
                content_lower = message.content.lower()
                triggered_bad_word = None
                for word in BAD_WORDS_LOWER:
                    if word in content_lower: # Basic check
                        triggered_bad_word = word
                        break
                if triggered_bad_word:
                    print(f"🚫 本地违禁词: '{triggered_bad_word}' 来自用户 {message.author} 在频道 #{channel.name}")
                    guild_offenses = user_first_offense_reminders.setdefault(guild.id, {})
                    user_offenses = guild_offenses.setdefault(author_id, set())

                    if triggered_bad_word not in user_offenses: # 初犯
                        user_offenses.add(triggered_bad_word)
                        print(f"   - '{triggered_bad_word}' 为该用户初犯，发送提醒。")
                        try:
                            rules_ch_id = 1280026139326283799 # <--- 替换!
                            rules_ch_mention = f"<#{rules_ch_id}>" if rules_ch_id and rules_ch_id != 123456789012345679 else "#规则"
                            await channel.send(
                                f"{author.mention}，请注意你的言辞并遵守服务器规则 ({rules_ch_mention})。本次仅为提醒，再犯将可能受到警告。",
                                delete_after=25
                            )
                        except Exception as remind_err: print(f"   - 发送违禁词提醒时发生错误: {remind_err}")
                        try:
                            if channel.permissions_for(guild.me).manage_messages: await message.delete()
                        except Exception: pass # Ignore delete error
                        return # Stop processing this message
                    else: # 累犯 -> 警告
                        print(f"   - '{triggered_bad_word}' 为该用户累犯，发出警告。")
                        reason = f"自动警告：再次使用不当词语 '{triggered_bad_word}'"
                        user_warnings[author_id] = user_warnings.get(author_id, 0) + 1
                        warning_count = user_warnings[author_id]
                        print(f"   - 用户当前警告次数: {warning_count}/{KICK_THRESHOLD}")

                        warn_embed = discord.Embed(color=discord.Color.orange(), timestamp=now)
                        warn_embed.set_author(name=f"自动警告发出 (不当言语)", icon_url=bot.user.display_avatar.url)
                        warn_embed.add_field(name="用户", value=f"{author.mention} ({author_id})", inline=False)
                        warn_embed.add_field(name="原因", value=reason, inline=False)
                        warn_embed.add_field(name="当前警告次数", value=f"{warning_count}/{KICK_THRESHOLD}", inline=False)
                        warn_embed.add_field(name="触发消息", value=f"[{message.content[:50]}...]({message.jump_url})", inline=False)

                        kick_performed_bw = False
                        if warning_count >= KICK_THRESHOLD:
                            warn_embed.title = "🚨 警告已达上限 - 自动踢出 (不当言语) 🚨"
                            warn_embed.color = discord.Color.red()
                            warn_embed.add_field(name="处理措施", value="用户已被自动踢出服务器", inline=False)
                            print(f"   - 用户 {author} 因不当言语达到踢出阈值。")
                            if member:
                                bot_member = guild.me
                                kick_reason_bw = f"自动踢出：因使用不当言语累计达到 {KICK_THRESHOLD} 次警告。"
                                can_kick = bot_member.guild_permissions.kick_members and (bot_member.top_role > member.top_role or bot_member == guild.owner)
                                if can_kick:
                                    try:
                                        try: await member.send(f"由于在服务器 **{guild.name}** 中累计达到 {KICK_THRESHOLD} 次不当言语警告（最后触发词：'{triggered_bad_word}'），你已被自动踢出。")
                                        except Exception as dm_err: print(f"   - 发送踢出私信给 {member.name} 时发生错误: {dm_err}")
                                        await member.kick(reason=kick_reason_bw)
                                        print(f"   - 已成功踢出用户 {member.name} (不当言语)。")
                                        kick_performed_bw = True
                                        user_warnings[author_id] = 0
                                        warn_embed.add_field(name="踢出状态", value="✅ 成功", inline=False)
                                    except discord.Forbidden: warn_embed.add_field(name="踢出状态", value="❌ 失败 (权限不足)", inline=False); print(f"   - 踢出用户 {member.name} 失败：机器人权限不足。")
                                    except Exception as kick_err: warn_embed.add_field(name="踢出状态", value=f"❌ 失败 ({kick_err})", inline=False); print(f"   - 踢出用户 {member.name} 时发生未知错误: {kick_err}")
                                else: warn_embed.add_field(name="踢出状态", value="❌ 失败 (权限/层级不足)", inline=False); print(f"   - 无法踢出用户 {member.name}：机器人权限不足或层级不够。")
                            else: warn_embed.add_field(name="踢出状态", value="❌ 失败 (无法获取成员对象)", inline=False); print(f"   - 无法获取用户 {author_id} 的 Member 对象，无法执行踢出。")
                        else: warn_embed.title = "⚠️ 自动警告已发出 (不当言语) ⚠️"

                        await send_to_public_log(guild, warn_embed, log_type="Auto Warn (Bad Word)")
                        try:
                            if channel.permissions_for(guild.me).manage_messages: await message.delete()
                        except Exception: pass
                        if not kick_performed_bw:
                            try:
                                await channel.send(f"⚠️ {author.mention}，你的言论再次触发警告 (不当言语)。当前警告次数: {warning_count}/{KICK_THRESHOLD}", delete_after=20)
                            except Exception as e: print(f"   - 发送频道内警告消息时出错: {e}")
                        return # Stop processing this message

        # --- 4. User Spam Detection Logic --- (Only for non-admins/mods)
        user_message_timestamps.setdefault(author_id, [])
        user_warnings.setdefault(author_id, 0) # Ensure user is in dict

        user_message_timestamps[author_id].append(now)
        time_limit_user = now - datetime.timedelta(seconds=SPAM_TIME_WINDOW_SECONDS)
        user_message_timestamps[author_id] = [ts for ts in user_message_timestamps[author_id] if ts > time_limit_user]

        if len(user_message_timestamps[author_id]) >= SPAM_COUNT_THRESHOLD:
            print(f"🚨 检测到用户刷屏! 用户: {author} ({author_id}) 在频道 #{channel.name}")
            user_warnings[author_id] += 1
            warning_count = user_warnings[author_id]
            print(f"   - 用户当前警告次数 (刷屏): {warning_count}/{KICK_THRESHOLD}")
            user_message_timestamps[author_id] = [] # Reset timestamps after detection

            log_embed_user = discord.Embed(color=discord.Color.orange(), timestamp=now)
            log_embed_user.set_author(name=f"自动警告发出 (用户刷屏)", icon_url=bot.user.display_avatar.url)
            log_embed_user.add_field(name="用户", value=f"{author.mention} ({author_id})", inline=False)
            log_embed_user.add_field(name="频道", value=channel.mention, inline=True)
            log_embed_user.add_field(name="触发消息数", value=f"≥ {SPAM_COUNT_THRESHOLD} 条 / {SPAM_TIME_WINDOW_SECONDS} 秒", inline=True)
            log_embed_user.add_field(name="当前警告次数", value=f"{warning_count}/{KICK_THRESHOLD}", inline=False)
            log_embed_user.add_field(name="最后消息链接", value=f"[点击跳转]({message.jump_url})", inline=False)

            kick_performed_spam = False
            if warning_count >= KICK_THRESHOLD:
                log_embed_user.title = "🚨 警告已达上限 - 自动踢出 (用户刷屏) 🚨"
                log_embed_user.color = discord.Color.red()
                log_embed_user.add_field(name="处理措施", value="用户已被自动踢出服务器", inline=False)
                print(f"   - 用户 {author} 因刷屏达到踢出阈值。")
                if member:
                    bot_member = guild.me
                    kick_reason_spam = f"自动踢出：因刷屏累计达到 {KICK_THRESHOLD} 次警告。"
                    can_kick_user = bot_member.guild_permissions.kick_members and (bot_member.top_role > member.top_role or bot_member == guild.owner)
                    if can_kick_user:
                        try:
                            try: await member.send(f"由于在服务器 **{guild.name}** 中累计达到 {KICK_THRESHOLD} 次刷屏警告，你已被自动踢出。")
                            except Exception as dm_err: print(f"   - 发送踢出私信给 {member.name} 时发生错误: {dm_err}")
                            await member.kick(reason=kick_reason_spam)
                            print(f"   - 已成功踢出用户 {member.name} (用户刷屏)。")
                            kick_performed_spam = True
                            user_warnings[author_id] = 0
                            log_embed_user.add_field(name="踢出状态", value="✅ 成功", inline=False)
                        except discord.Forbidden: log_embed_user.add_field(name="踢出状态", value="❌ 失败 (权限不足)", inline=False); print(f"   - 踢出用户 {member.name} 失败：机器人权限不足。")
                        except Exception as kick_err: log_embed_user.add_field(name="踢出状态", value=f"❌ 失败 ({kick_err})", inline=False); print(f"   - 踢出用户 {member.name} 时发生未知错误: {kick_err}")
                    else: log_embed_user.add_field(name="踢出状态", value="❌ 失败 (权限/层级不足)", inline=False); print(f"   - 无法踢出用户 {member.name}：机器人权限不足或层级不够。")
                else: log_embed_user.add_field(name="踢出状态", value="❌ 失败 (无法获取成员对象)", inline=False); print(f"   - 无法获取用户 {author_id} 的 Member 对象，无法执行踢出。")
            else: log_embed_user.title = "⚠️ 自动警告已发出 (用户刷屏) ⚠️"

            await send_to_public_log(guild, log_embed_user, log_type="Auto Warn (User Spam)")
            if not kick_performed_spam:
                try:
                    await message.channel.send(f"⚠️ {author.mention}，检测到你发送消息过于频繁，请减缓速度！(警告 {warning_count}/{KICK_THRESHOLD})", delete_after=15)
                except Exception as warn_err: print(f"   - 发送用户刷屏警告消息时出错: {warn_err}")
            # Optional: Purge user's messages (use with caution)
            # ... (purge logic commented out) ...
            return # Stop processing this message

    # --- Bot Spam Detection Logic --- (Handles messages from other bots)
    if message.author.bot and message.author.id != bot.user.id:
        bot_author_id = message.author.id
        bot_message_timestamps.setdefault(bot_author_id, [])
        bot_message_timestamps[bot_author_id].append(now)
        time_limit_bot = now - datetime.timedelta(seconds=BOT_SPAM_TIME_WINDOW_SECONDS)
        bot_message_timestamps[bot_author_id] = [ts for ts in bot_message_timestamps[bot_author_id] if ts > time_limit_bot]

        if len(bot_message_timestamps[bot_author_id]) >= BOT_SPAM_COUNT_THRESHOLD:
            print(f"🚨 检测到机器人刷屏! Bot: {message.author} ({bot_author_id}) 在频道 #{channel.name}")
            bot_message_timestamps[bot_author_id] = [] # Reset timestamps
            mod_mentions = " ".join([f"<@&{role_id}>" for role_id in MOD_ALERT_ROLE_IDS])
            action_summary = "正在尝试自动处理..."
            spamming_bot_member = guild.get_member(bot_author_id)
            my_bot_member = guild.me
            kick_succeeded = False
            role_removal_succeeded = False

            if spamming_bot_member:
                can_kick_bot = my_bot_member.guild_permissions.kick_members and (my_bot_member.top_role > spamming_bot_member.top_role)
                if can_kick_bot:
                    try:
                        await spamming_bot_member.kick(reason="自动踢出：检测到机器人刷屏")
                        action_summary = "**➡️ 自动操作：已成功踢出该机器人。**"
                        kick_succeeded = True
                        print(f"   - 已成功踢出刷屏机器人 {spamming_bot_member.name}。")
                    except Exception as kick_err: action_summary = f"**➡️ 自动操作：尝试踢出时发生错误: {kick_err}**"; print(f"   - 踢出机器人 {spamming_bot_member.name} 时出错: {kick_err}")
                elif my_bot_member.guild_permissions.kick_members: action_summary = "**➡️ 自动操作：无法踢出 (目标机器人层级不低于我)。**"; print(f"   - 无法踢出机器人 {spamming_bot_member.name} (层级不足)。")
                else: action_summary = "**➡️ 自动操作：机器人缺少“踢出成员”权限。**"; print("   - 机器人缺少踢出权限。")

                can_manage_roles = my_bot_member.guild_permissions.manage_roles
                if not kick_succeeded and can_manage_roles:
                    roles_to_try_removing = [r for r in spamming_bot_member.roles if r != guild.default_role and r < my_bot_member.top_role]
                    if roles_to_try_removing:
                        print(f"   - 尝试移除机器人 {spamming_bot_member.name} 的身份组: {[r.name for r in roles_to_try_removing]}")
                        try:
                            await spamming_bot_member.remove_roles(*roles_to_try_removing, reason="自动移除身份组：检测到机器人刷屏")
                            role_removal_succeeded = True
                            action_summary = "**➡️ 自动操作：踢出失败/无法踢出，但已尝试移除该机器人的身份组。**"
                            print(f"   - 已成功移除机器人 {spamming_bot_member.name} 的部分身份组。")
                        except Exception as role_err: action_summary += f"\n**➡️ 自动操作：尝试移除身份组时出错: {role_err}**"; print(f"   - 移除机器人 {spamming_bot_member.name} 身份组时出错: {role_err}")
                    elif not kick_succeeded: action_summary = "**➡️ 自动操作：踢出失败/无法踢出，且未找到可移除的低层级身份组。**"
                elif not kick_succeeded and not can_manage_roles:
                     if not kick_succeeded: action_summary = "**➡️ 自动操作：无法踢出，且机器人缺少管理身份组权限。**"

            else: action_summary = "**➡️ 自动操作：无法获取该机器人成员对象，无法执行操作。**"; print(f"   - 无法找到 ID 为 {bot_author_id} 的机器人成员对象。")

            final_alert = (f"🚨 **机器人刷屏警报!** 🚨\n"
                           f"机器人: {message.author.mention} ({bot_author_id})\n"
                           f"频道: {channel.mention}\n{action_summary}\n"
                           f"{mod_mentions} 请管理员关注并采取进一步措施！")
            try: await channel.send(final_alert)
            except Exception as alert_err: print(f"   - 发送机器人刷屏警报时出错: {alert_err}")

            # Attempt to clean up messages
            if channel.permissions_for(guild.me).manage_messages:
                print(f"   - 尝试自动清理来自 {message.author.name} 的刷屏消息...")
                deleted_count = 0
                try:
                    limit_check = BOT_SPAM_COUNT_THRESHOLD * 3
                    deleted_messages = await channel.purge(limit=limit_check, check=lambda m: m.author.id == bot_author_id, after=now - datetime.timedelta(seconds=BOT_SPAM_TIME_WINDOW_SECONDS * 2), reason="自动清理机器人刷屏消息")
                    deleted_count = len(deleted_messages)
                    print(f"   - 成功删除了 {deleted_count} 条来自 {message.author.name} 的消息。")
                    if deleted_count > 0:
                       try: await channel.send(f"🧹 已自动清理 {deleted_count} 条来自 {message.author.mention} 的刷屏消息。", delete_after=15)
                       except: pass
                except Exception as del_err: print(f"   - 清理机器人消息过程中发生错误: {del_err}")
            else: print("   - 机器人缺少 '管理消息' 权限，无法清理机器人刷屏。")
            return # Stop processing this message


    # --- Process legacy prefix commands if applicable ---
    # This should be called *after* spam/content checks if you want those applied first
    # Or call it earlier if you want commands to bypass checks
    # Example: Call it here to process commands only if no violation/spam occurred
    # Or call it near the top (after basic bot check) if commands should always run
    # await bot.process_commands(message)


# --- Event: Voice State Update ---
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    guild = member.guild
    # 使用正确的存储字典
    master_vc_id = get_setting(temp_vc_settings, guild.id, "master_channel_id")
    category_id = get_setting(temp_vc_settings, guild.id, "category_id")

    if not master_vc_id: return

    master_channel = guild.get_channel(master_vc_id)
    if not master_channel or not isinstance(master_channel, discord.VoiceChannel):
        print(f"⚠️ 临时语音：服务器 {guild.name} 的母频道 ID ({master_vc_id}) 无效或不是语音频道。")
        # set_setting(temp_vc_settings, guild.id, "master_channel_id", None) # Optional: Clear invalid setting
        return

    category = None
    if category_id:
        category = guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            print(f"⚠️ 临时语音：服务器 {guild.name} 配置的分类 ID ({category_id}) 无效或不是分类频道，将尝试在母频道所在分类创建。")
            category = master_channel.category
    else: category = master_channel.category

    # --- User joins master channel -> Create temp channel ---
    if after.channel == master_channel:
        if not category or not category.permissions_for(guild.me).manage_channels or \
           not category.permissions_for(guild.me).move_members:
            print(f"❌ 临时语音创建失败：机器人在分类 '{category.name if category else '未知'}' 中缺少 '管理频道' 或 '移动成员' 权限。 ({member.name})")
            try: await member.send(f"抱歉，我在服务器 **{guild.name}** 中创建临时语音频道所需的权限不足，请联系管理员检查我在分类 '{category.name if category else '默认'}' 中的权限。")
            except: pass
            return

        print(f"🔊 用户 {member.name} 加入了母频道 ({master_channel.name})，准备创建临时频道...")
        new_channel = None # Init before try
        try:
            owner_overwrites = discord.PermissionOverwrite(manage_channels=True, manage_permissions=True, move_members=True, connect=True, speak=True, stream=True, use_voice_activation=True, priority_speaker=True, mute_members=True, deafen_members=True, use_embedded_activities=True, video=True)
            everyone_overwrites = discord.PermissionOverwrite(connect=True, speak=True)
            bot_overwrites = discord.PermissionOverwrite(manage_channels=True, manage_permissions=True, move_members=True, connect=True, view_channel=True)
            temp_channel_name = f"🎮 {member.display_name} 的频道"[:100]

            new_channel = await guild.create_voice_channel(
                name=temp_channel_name, category=category,
                overwrites={guild.default_role: everyone_overwrites, member: owner_overwrites, guild.me: bot_overwrites},
                reason=f"由 {member.name} 加入母频道自动创建"
            )
            print(f"   ✅ 已创建临时频道: {new_channel.name} ({new_channel.id})")

            try:
                await member.move_to(new_channel, reason="移动到新创建的临时频道")
                print(f"   ✅ 已将 {member.name} 移动到频道 {new_channel.name}。")
                temp_vc_owners[new_channel.id] = member.id
                temp_vc_created.add(new_channel.id)
            except Exception as move_e:
                print(f"   ❌ 将 {member.name} 移动到新频道时发生错误: {move_e}")
                try: await new_channel.delete(reason="移动用户失败/错误，自动删除")
                except: pass # Ignore deletion error if move failed

        except Exception as e:
            print(f"   ❌ 创建/移动临时语音频道时发生错误: {e}")
            if new_channel: # Clean up channel if created before error
                 try: await new_channel.delete(reason="创建/移动过程中出错")
                 except: pass

    # --- User leaves a temp channel -> Check if empty and delete ---
    if before.channel and before.channel.id in temp_vc_created:
        await asyncio.sleep(1) # Short delay
        channel_to_check = guild.get_channel(before.channel.id)

        if channel_to_check and isinstance(channel_to_check, discord.VoiceChannel):
            is_empty = not any(m for m in channel_to_check.members if not m.bot)
            if is_empty:
                print(f"🔊 临时频道 {channel_to_check.name} ({channel_to_check.id}) 已空，准备删除...")
                try:
                    if channel_to_check.permissions_for(guild.me).manage_channels:
                        await channel_to_check.delete(reason="临时语音频道为空，自动删除")
                        print(f"   ✅ 已成功删除频道 {channel_to_check.name}。")
                    else: print(f"   ❌ 删除频道 {channel_to_check.name} 失败：机器人缺少 '管理频道' 权限。")
                except discord.NotFound: print(f"   ℹ️ 尝试删除频道 {channel_to_check.name} 时未找到 (可能已被删)。")
                except discord.Forbidden: print(f"   ❌ 删除频道 {channel_to_check.name} 失败：机器人权限不足。")
                except Exception as e: print(f"   ❌ 删除频道 {channel_to_check.name} 时发生未知错误: {e}")
                finally: # Clean up memory regardless of deletion success
                    if channel_to_check.id in temp_vc_owners: del temp_vc_owners[channel_to_check.id]
                    if channel_to_check.id in temp_vc_created: temp_vc_created.remove(channel_to_check.id)
                    # print(f"   - 已清理频道 {channel_to_check.id} 的内存记录。") # Less verbose log
        else: # Channel disappeared during delay or isn't a VC anymore
            if before.channel.id in temp_vc_owners: del temp_vc_owners[before.channel.id]
            if before.channel.id in temp_vc_created: temp_vc_created.remove(before.channel.id)


# --- Slash Command Definitions ---

# --- Help Command ---
@bot.tree.command(name="help", description="显示可用指令的帮助信息。")
async def slash_help(interaction: discord.Interaction):
    """显示所有可用斜线指令的概览"""
    embed = discord.Embed(
        title="🤖 GJ Team Bot 指令帮助",
        description="以下是本机器人支持的斜线指令列表：",
        color=discord.Color.purple() # 紫色
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url) # 显示机器人头像

    # 身份组管理
    embed.add_field(
        name="👤 身份组管理",
        value=(
            "`/createrole [身份组名称]` - 创建新身份组\n"
            "`/deleterole [身份组名称]` - 删除现有身份组\n"
            "`/giverole [用户] [身份组名称]` - 赋予用户身份组\n"
            "`/takerole [用户] [身份组名称]` - 移除用户身份组\n"
            "`/createseparator [标签]` - 创建分隔线身份组"
        ),
        inline=False
    )

    # 审核与管理
    embed.add_field(
        name="🛠️ 审核与管理",
        value=(
            "`/clear [数量]` - 清除当前频道消息 (1-100)\n"
            "`/warn [用户] [原因]` - 手动警告用户 (累计3次踢出)\n"
            "`/unwarn [用户] [原因]` - 移除用户一次警告"
        ),
        inline=False
    )

     # 公告
    embed.add_field(
        name="📢 公告发布",
        value=(
            "`/announce [频道] [标题] [消息] [提及身份组] [图片URL] [颜色]` - 发送嵌入式公告"
        ),
        inline=False
    )

    # 高级管理指令组 (/管理 ...)
    embed.add_field(
        name="⚙️ 高级管理指令 (/管理 ...)",
        value=(
            "`... 票据设定 [按钮频道] [票据分类] [员工身份组]` - 设置票据系统\n" # <--- 新增
            "`... 删讯息 [用户] [数量]` - 删除特定用户消息\n"
            "`... 频道名 [新名称]` - 修改当前频道名称\n"
            "`... 禁言 [用户] [分钟数] [原因]` - 禁言用户 (0=永久/28天)\n"
            "`... 踢出 [用户] [原因]` - 将用户踢出服务器\n"
            "`... 封禁 [用户ID] [原因]` - 永久封禁用户 (按ID)\n"
            "`... 解封 [用户ID] [原因]` - 解除用户封禁 (按ID)\n"
            "`... 人数频道 [名称模板]` - 创建/更新成员人数统计频道\n"
            "`... ai豁免-添加用户 [用户]` - 添加用户到AI检测豁免\n"
            "`... ai豁免-移除用户 [用户]` - 从AI豁免移除用户\n"
            "`... ai豁免-添加频道 [频道]` - 添加频道到AI检测豁免\n"
            "`... ai豁免-移除频道 [频道]` - 从AI豁免移除频道\n"
            "`... ai豁免-查看列表` - 查看当前AI豁免列表"
        ),
        inline=False
    )

    # 临时语音指令组 (/语音 ...)
    embed.add_field(
        name="🔊 临时语音频道 (/语音 ...)",
        value=(
            "`... 设定母频道 [母频道] [分类]` - 设置创建临时语音的入口频道\n"
            "`... 设定权限 [对象] [权限设置]` - (房主) 设置频道成员权限\n"
            "`... 转让 [新房主]` - (房主) 转让频道所有权\n"
            "`... 房主` - (成员) 如果原房主不在，尝试获取房主权限"
        ),
        inline=False
    )

    # 其他
    embed.add_field(name="ℹ️ 其他", value="`/help` - 显示此帮助信息", inline=False)

    embed.set_footer(text="[] = 必填参数, <> = 可选参数。大部分管理指令需要相应权限。")
    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

    await interaction.response.send_message(embed=embed, ephemeral=True) # 临时消息，仅请求者可见


# --- Role Management Commands ---
@bot.tree.command(name="createrole", description="在服务器中创建一个新的身份组。")
@app_commands.describe(role_name="新身份组的确切名称。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_createrole(interaction: discord.Interaction, role_name: str):
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True); return
    if get(guild.roles, name=role_name): await interaction.followup.send(f"❌ 身份组 **{role_name}** 已经存在！", ephemeral=True); return
    if len(role_name) > 100: await interaction.followup.send("❌ 身份组名称过长（最多100个字符）。", ephemeral=True); return
    if not role_name.strip(): await interaction.followup.send("❌ 身份组名称不能为空。", ephemeral=True); return

    try:
        new_role = await guild.create_role(name=role_name, reason=f"由 {interaction.user} 创建")
        await interaction.followup.send(f"✅ 已成功创建身份组: {new_role.mention}", ephemeral=False)
        print(f"[身份组操作] 用户 {interaction.user} 创建了身份组 '{new_role.name}' ({new_role.id})")
    except discord.Forbidden: await interaction.followup.send(f"⚙️ 创建身份组 **{role_name}** 失败：机器人权限不足。", ephemeral=True)
    except Exception as e: print(f"执行 /createrole 时出错: {e}"); await interaction.followup.send(f"⚙️ 创建身份组时发生未知错误: {e}", ephemeral=True)


@bot.tree.command(name="deleterole", description="根据精确名称删除一个现有的身份组。")
@app_commands.describe(role_name="要删除的身份组的确切名称。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_deleterole(interaction: discord.Interaction, role_name: str):
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True); return
    role_to_delete = get(guild.roles, name=role_name)
    if not role_to_delete: await interaction.followup.send(f"❓ 找不到名为 **{role_name}** 的身份组。", ephemeral=True); return
    if role_to_delete == guild.default_role: await interaction.followup.send("🚫 不能删除 `@everyone` 身份组。", ephemeral=True); return
    if role_to_delete.is_integration() or role_to_delete.is_bot_managed(): await interaction.followup.send(f"⚠️ 不能删除由集成或机器人管理的身份组 {role_to_delete.mention}。", ephemeral=True); return
    if role_to_delete.is_premium_subscriber(): await interaction.followup.send(f"⚠️ 不能删除 Nitro Booster 身份组 {role_to_delete.mention}。", ephemeral=True); return
    if role_to_delete >= guild.me.top_role and guild.me.id != guild.owner_id: await interaction.followup.send(f"🚫 无法删除身份组 {role_to_delete.mention}：我的身份组层级低于或等于它。", ephemeral=True); return

    try:
        deleted_role_name = role_to_delete.name
        await role_to_delete.delete(reason=f"由 {interaction.user} 删除")
        await interaction.followup.send(f"✅ 已成功删除身份组: **{deleted_role_name}**", ephemeral=False)
        print(f"[身份组操作] 用户 {interaction.user} 删除了身份组 '{deleted_role_name}' ({role_to_delete.id})")
    except discord.Forbidden: await interaction.followup.send(f"⚙️ 删除身份组 **{role_name}** 失败：机器人权限不足。", ephemeral=True)
    except Exception as e: print(f"执行 /deleterole 时出错: {e}"); await interaction.followup.send(f"⚙️ 删除身份组时发生未知错误: {e}", ephemeral=True)


@bot.tree.command(name="giverole", description="将一个现有的身份组分配给指定成员。")
@app_commands.describe(user="要给予身份组的用户。", role_name="要分配的身份组的确切名称。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_giverole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True); return
    role_to_give = get(guild.roles, name=role_name)
    if not role_to_give: await interaction.followup.send(f"❓ 找不到名为 **{role_name}** 的身份组。", ephemeral=True); return
    if role_to_give == guild.default_role: await interaction.followup.send("🚫 不能手动赋予 `@everyone` 身份组。", ephemeral=True); return
    if role_to_give >= guild.me.top_role and guild.me.id != guild.owner_id: await interaction.followup.send(f"🚫 无法分配身份组 {role_to_give.mention}：我的身份组层级低于或等于它。", ephemeral=True); return
    if isinstance(interaction.user, discord.Member) and interaction.user.id != guild.owner_id:
        if role_to_give >= interaction.user.top_role: await interaction.followup.send(f"🚫 你无法分配层级等于或高于你自己的身份组 ({role_to_give.mention})。", ephemeral=True); return
    if role_to_give in user.roles: await interaction.followup.send(f"ℹ️ 用户 {user.mention} 已经拥有身份组 {role_to_give.mention}。", ephemeral=True); return

    try:
        await user.add_roles(role_to_give, reason=f"由 {interaction.user} 赋予")
        await interaction.followup.send(f"✅ 已成功将身份组 {role_to_give.mention} 赋予给 {user.mention}。", ephemeral=False)
        print(f"[身份组操作] 用户 {interaction.user} 将身份组 '{role_to_give.name}' ({role_to_give.id}) 赋予了用户 {user.name} ({user.id})")
    except discord.Forbidden: await interaction.followup.send(f"⚙️ 赋予身份组 **{role_name}** 给 {user.mention} 失败：机器人权限不足。", ephemeral=True)
    except Exception as e: print(f"执行 /giverole 时出错: {e}"); await interaction.followup.send(f"⚙️ 赋予身份组时发生未知错误: {e}", ephemeral=True)


@bot.tree.command(name="takerole", description="从指定成员移除一个特定的身份组。")
@app_commands.describe(user="要移除其身份组的用户。", role_name="要移除的身份组的确切名称。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_takerole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True); return
    role_to_take = get(guild.roles, name=role_name)
    if not role_to_take: await interaction.followup.send(f"❓ 找不到名为 **{role_name}** 的身份组。", ephemeral=True); return
    if role_to_take == guild.default_role: await interaction.followup.send("🚫 不能移除 `@everyone` 身份组。", ephemeral=True); return
    if role_to_take.is_integration() or role_to_take.is_bot_managed(): await interaction.followup.send(f"⚠️ 不能手动移除由集成或机器人管理的身份组 {role_to_take.mention}。", ephemeral=True); return
    if role_to_take.is_premium_subscriber(): await interaction.followup.send(f"⚠️ 不能手动移除 Nitro Booster 身份组 {role_to_take.mention}。", ephemeral=True); return
    if role_to_take >= guild.me.top_role and guild.me.id != guild.owner_id: await interaction.followup.send(f"🚫 无法移除身份组 {role_to_take.mention}：我的身份组层级低于或等于它。", ephemeral=True); return
    if isinstance(interaction.user, discord.Member) and interaction.user.id != guild.owner_id:
         if role_to_take >= interaction.user.top_role: await interaction.followup.send(f"🚫 你无法移除层级等于或高于你自己的身份组 ({role_to_take.mention})。", ephemeral=True); return
    if role_to_take not in user.roles: await interaction.followup.send(f"ℹ️ 用户 {user.mention} 并未拥有身份组 {role_to_take.mention}。", ephemeral=True); return

    try:
        await user.remove_roles(role_to_take, reason=f"由 {interaction.user} 移除")
        await interaction.followup.send(f"✅ 已成功从 {user.mention} 移除身份组 {role_to_take.mention}。", ephemeral=False)
        print(f"[身份组操作] 用户 {interaction.user} 从用户 {user.name} ({user.id}) 移除了身份组 '{role_to_take.name}' ({role_to_take.id})")
    except discord.Forbidden: await interaction.followup.send(f"⚙️ 从 {user.mention} 移除身份组 **{role_name}** 失败：机器人权限不足。", ephemeral=True)
    except Exception as e: print(f"执行 /takerole 时出错: {e}"); await interaction.followup.send(f"⚙️ 移除身份组时发生未知错误: {e}", ephemeral=True)


@bot.tree.command(name="createseparator", description="创建一个用于视觉分隔的特殊身份组。")
@app_commands.describe(label="要在分隔线中显示的文字标签 (例如 '成员信息', '游戏身份')。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_createseparator(interaction: discord.Interaction, label: str):
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True); return
    separator_name = f"▽─── {label} ───" # Simplified name
    if len(separator_name) > 100: await interaction.followup.send(f"❌ 标签文字过长，导致分隔线名称超过100字符限制。", ephemeral=True); return
    if not label.strip(): await interaction.followup.send(f"❌ 标签不能为空。", ephemeral=True); return
    if get(guild.roles, name=separator_name): await interaction.followup.send(f"⚠️ 似乎已存在基于标签 **{label}** 的分隔线身份组 (**{separator_name}**)！", ephemeral=True); return

    try:
        new_role = await guild.create_role(name=separator_name, permissions=discord.Permissions.none(), color=discord.Color.default(), hoist=False, mentionable=False, reason=f"由 {interaction.user} 创建的分隔线")
        await interaction.followup.send(f"✅ 已成功创建分隔线身份组: **{new_role.name}**\n**重要提示:** 请前往 **服务器设置 -> 身份组**，手动将此身份组拖动到你希望的位置！", ephemeral=False)
        print(f"[身份组操作] 用户 {interaction.user} 创建了分隔线 '{new_role.name}' ({new_role.id})")
    except discord.Forbidden: await interaction.followup.send(f"⚙️ 创建分隔线失败：机器人权限不足。", ephemeral=True)
    except Exception as e: print(f"执行 /createseparator 时出错: {e}"); await interaction.followup.send(f"⚙️ 创建分隔线时发生未知错误: {e}", ephemeral=True)

# --- Moderation Commands ---
@bot.tree.command(name="clear", description="清除当前频道中指定数量的消息 (1-100)。")
@app_commands.describe(amount="要删除的消息数量 (1 到 100 之间)。")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
async def slash_clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel): await interaction.response.send_message("❌ 此命令只能在文字频道中使用。", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)

    try:
        deleted_messages = await channel.purge(limit=amount)
        deleted_count = len(deleted_messages)
        await interaction.followup.send(f"✅ 已成功删除 {deleted_count} 条消息。", ephemeral=True)
        print(f"[审核操作] 用户 {interaction.user} 在频道 #{channel.name} 清除了 {deleted_count} 条消息。")
        log_embed = discord.Embed(title="🧹 消息清除操作", color=discord.Color.light_grey(), timestamp=discord.utils.utcnow())
        log_embed.add_field(name="执行者", value=interaction.user.mention, inline=True)
        log_embed.add_field(name="频道", value=channel.mention, inline=True)
        log_embed.add_field(name="清除数量", value=str(deleted_count), inline=True)
        log_embed.set_footer(text=f"执行者 ID: {interaction.user.id}")
        await send_to_public_log(interaction.guild, log_embed, log_type="Clear Messages")
    except discord.Forbidden: await interaction.followup.send(f"⚙️ 清除消息失败：机器人缺少在频道 {channel.mention} 中删除消息的权限。", ephemeral=True)
    except Exception as e: print(f"执行 /clear 时出错: {e}"); await interaction.followup.send(f"⚙️ 清除消息时发生未知错误: {e}", ephemeral=True)


@bot.tree.command(name="warn", description="手动向用户发出一次警告 (累计达到阈值会被踢出)。")
@app_commands.describe(user="要警告的用户。", reason="警告的原因 (可选)。")
@app_commands.checks.has_permissions(kick_members=True) # Or moderate_members
async def slash_warn(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    guild = interaction.guild
    author = interaction.user
    await interaction.response.defer(ephemeral=False)
    if not guild: await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True); return
    if user.bot: await interaction.followup.send("❌ 不能警告机器人。", ephemeral=True); return
    if user == author: await interaction.followup.send("❌ 你不能警告自己。", ephemeral=True); return
    if isinstance(author, discord.Member) and author.id != guild.owner_id:
        if user.top_role >= author.top_role: await interaction.followup.send(f"🚫 你无法警告层级等于或高于你的成员 ({user.mention})。", ephemeral=True); return

    user_id = user.id
    user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
    warning_count = user_warnings[user_id]
    print(f"[审核操作] 用户 {author} 手动警告了用户 {user}。原因: {reason}。新警告次数: {warning_count}/{KICK_THRESHOLD}")

    embed = discord.Embed(color=discord.Color.orange(), timestamp=discord.utils.utcnow())
    embed.set_author(name=f"由 {author.display_name} 发出警告", icon_url=author.display_avatar.url)
    embed.add_field(name="被警告用户", value=f"{user.mention} ({user.id})", inline=False)
    embed.add_field(name="警告原因", value=reason, inline=False)
    embed.add_field(name="当前警告次数", value=f"**{warning_count}** / {KICK_THRESHOLD}", inline=False)

    kick_performed = False
    if warning_count >= KICK_THRESHOLD:
        embed.title = "🚨 警告已达上限 - 用户已被踢出 🚨"
        embed.color = discord.Color.red()
        embed.add_field(name="处理措施", value="已自动踢出服务器", inline=False)
        print(f"   - 用户 {user.name} 因手动警告达到踢出阈值。")
        bot_member = guild.me
        can_kick = bot_member.guild_permissions.kick_members and (bot_member.top_role > user.top_role or bot_member == guild.owner)
        if can_kick:
            kick_reason_warn = f"自动踢出：因累计达到 {KICK_THRESHOLD} 次警告 (最后一次由 {author.display_name} 手动发出，原因：{reason})。"
            try:
                try: await user.send(f"由于在服务器 **{guild.name}** 中累计达到 {KICK_THRESHOLD} 次警告（最后由 {author.display_name} 发出警告，原因：{reason}），你已被踢出。")
                except Exception as dm_err: print(f"   - 无法向用户 {user.name} 发送踢出私信 (手动警告): {dm_err}")
                await user.kick(reason=kick_reason_warn)
                print(f"   - 已成功踢出用户 {user.name} (手动警告达到上限)。")
                kick_performed = True
                user_warnings[user_id] = 0
                embed.add_field(name="踢出状态", value="✅ 成功", inline=False)
            except discord.Forbidden: embed.add_field(name="踢出状态", value="❌ 失败 (权限不足)", inline=False); print(f"   - 踢出用户 {user.name} 失败：机器人权限不足。")
            except Exception as kick_err: embed.add_field(name="踢出状态", value=f"❌ 失败 ({kick_err})", inline=False); print(f"   - 踢出用户 {user.name} 时发生未知错误: {kick_err}")
        else:
             embed.add_field(name="踢出状态", value="❌ 失败 (权限/层级不足)", inline=False); print(f"   - 无法踢出用户 {user.name}：机器人权限不足或层级不够。")
             if MOD_ALERT_ROLE_IDS: embed.add_field(name="提醒", value=f"<@&{MOD_ALERT_ROLE_IDS[0]}> 请手动处理！", inline=False) # Ping first mod role if available

    else:
        embed.title = "⚠️ 手动警告已发出 ⚠️"
        embed.add_field(name="后续处理", value=f"该用户再收到 {KICK_THRESHOLD - warning_count} 次警告将被自动踢出。", inline=False)

    await interaction.followup.send(embed=embed)
    await send_to_public_log(guild, embed, log_type="Manual Warn")


@bot.tree.command(name="unwarn", description="移除用户的一次警告记录。")
@app_commands.describe(user="要移除其警告的用户。", reason="移除警告的原因 (可选)。")
@app_commands.checks.has_permissions(kick_members=True) # Or moderate_members
async def slash_unwarn(interaction: discord.Interaction, user: discord.Member, reason: str = "管理员酌情处理"):
    guild = interaction.guild
    author = interaction.user
    await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True); return
    if user.bot: await interaction.followup.send("❌ 机器人没有警告记录。", ephemeral=True); return

    user_id = user.id
    current_warnings = user_warnings.get(user_id, 0)
    if current_warnings <= 0: await interaction.followup.send(f"ℹ️ 用户 {user.mention} 当前没有警告记录可移除。", ephemeral=True); return

    user_warnings[user_id] = current_warnings - 1
    new_warning_count = user_warnings[user_id]
    print(f"[审核操作] 用户 {author} 移除了用户 {user} 的一次警告。原因: {reason}。新警告次数: {new_warning_count}/{KICK_THRESHOLD}")

    embed = discord.Embed(title="✅ 警告已移除 ✅", color=discord.Color.green(), timestamp=discord.utils.utcnow())
    embed.set_author(name=f"由 {author.display_name} 操作", icon_url=author.display_avatar.url)
    embed.add_field(name="用户", value=f"{user.mention} ({user.id})", inline=False)
    embed.add_field(name="移除原因", value=reason, inline=False)
    embed.add_field(name="新的警告次数", value=f"**{new_warning_count}** / {KICK_THRESHOLD}", inline=False)

    await send_to_public_log(guild, embed, log_type="Manual Unwarn")
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="announce", description="以嵌入式消息格式发送服务器公告。")
@app_commands.describe(
    channel="要发送公告的目标文字频道。",
    title="公告的醒目标题。",
    message="公告的主要内容 (使用 '\\n' 来换行)。",
    ping_role="(可选) 要在公告前提及的身份组。",
    image_url="(可选) 要附加在公告底部的图片 URL (必须是 http/https 链接)。",
    color="(可选) 嵌入消息左侧边框的颜色 (十六进制，如 '#3498db' 或 '0x3498db')。"
)
@app_commands.checks.has_permissions(manage_guild=True)
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
    await interaction.response.defer(ephemeral=True)
    if not guild: await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True); return

    embed_color = discord.Color.blue()
    valid_image = None
    validation_warnings = []

    if color:
        try: embed_color = discord.Color(int(color.lstrip('#').lstrip('0x'), 16))
        except ValueError: validation_warnings.append(f"⚠️ 无效颜色代码'{color}'"); embed_color = discord.Color.blue()

    if image_url:
        if image_url.startswith(('http://', 'https://')):
            valid_image_check = False
            try:
                if AIOHTTP_AVAILABLE and hasattr(bot, 'http_session') and bot.http_session:
                    async with bot.http_session.head(image_url, timeout=5, allow_redirects=True) as head_resp:
                        if head_resp.status == 200 and 'image' in head_resp.headers.get('Content-Type', '').lower(): valid_image_check = True
                        elif head_resp.status != 200: validation_warnings.append(f"⚠️ 图片URL无法访问({head_resp.status})")
                        else: validation_warnings.append(f"⚠️ URL内容非图片({head_resp.headers.get('Content-Type','')})")
                else: # Fallback using requests (blocking)
                    loop = asyncio.get_event_loop()
                    head_resp = await loop.run_in_executor(None, lambda: requests.head(image_url, timeout=5, allow_redirects=True))
                    if head_resp.status_code == 200 and 'image' in head_resp.headers.get('Content-Type', '').lower(): valid_image_check = True
                    elif head_resp.status_code != 200: validation_warnings.append(f"⚠️ 图片URL无法访问({head_resp.status_code})")
                    else: validation_warnings.append(f"⚠️ URL内容非图片({head_resp.headers.get('Content-Type','')})")

                if valid_image_check: valid_image = image_url
            except Exception as req_err: validation_warnings.append(f"⚠️ 验证图片URL时出错:{req_err}")
        else: validation_warnings.append("⚠️ 图片URL格式无效")

    if validation_warnings:
        warn_text = "\n".join(validation_warnings)
        try: await interaction.followup.send(f"**公告参数警告:**\n{warn_text}\n公告仍将尝试发送。", ephemeral=True)
        except: pass # Ignore if interaction expires

    embed = discord.Embed(title=f"**{title}**", description=message.replace('\\n', '\n'), color=embed_color, timestamp=discord.utils.utcnow())
    embed.set_footer(text=f"由 {author.display_name} 发布 | {guild.name}", icon_url=guild.icon.url if guild.icon else bot.user.display_avatar.url)
    if valid_image: embed.set_image(url=valid_image)

    ping_content = None
    if ping_role:
        if ping_role.mentionable or (isinstance(author, discord.Member) and author.guild_permissions.mention_everyone): ping_content = ping_role.mention
        else:
             warn_msg = f"⚠️ 身份组 {ping_role.name} 不可提及。公告中不会实际提及。"
             try: await interaction.followup.send(warn_msg, ephemeral=True)
             except: pass
             ping_content = f"(提及 **{ping_role.name}**)"

    try:
        target_perms = channel.permissions_for(guild.me)
        if not target_perms.send_messages or not target_perms.embed_links:
            await interaction.followup.send(f"❌ 发送失败：机器人缺少在频道 {channel.mention} 发送消息或嵌入链接的权限。", ephemeral=True)
            return
        await channel.send(content=ping_content, embed=embed)
        await interaction.followup.send(f"✅ 公告已成功发送到频道 {channel.mention}！", ephemeral=True)
        print(f"[公告] 用户 {author} 在频道 #{channel.name} 发布了公告: '{title}'")
    except discord.Forbidden: await interaction.followup.send(f"❌ 发送失败：机器人缺少在频道 {channel.mention} 发送消息或嵌入链接的权限。", ephemeral=True)
    except Exception as e: print(f"执行 /announce 时出错: {e}"); await interaction.followup.send(f"❌ 发送公告时发生未知错误: {e}", ephemeral=True)


# --- Management Command Group Definitions ---
manage_group = app_commands.Group(name="管理", description="服务器高级管理相关指令 (需要相应权限)")

# --- Ticket Setup Command ---
@manage_group.command(name="票据设定", description="配置票据系统，并在指定频道发布创建按钮。")
@app_commands.describe(
    button_channel="将在哪个文字频道发布“创建票据”按钮？",
    ticket_category="新创建的票据频道将放置在哪个分类下？",
    staff_roles="哪些身份组可以处理票据？(用空格分隔提及多个身份组)"
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True, manage_channels=True, manage_permissions=True, manage_messages=True) # Added Manage Messages for deleting old button
async def manage_ticket_setup(interaction: discord.Interaction, button_channel: discord.TextChannel, ticket_category: discord.CategoryChannel, staff_roles: str):
    guild = interaction.guild
    guild_id = guild.id
    await interaction.response.defer(ephemeral=True)

    parsed_role_ids = []
    failed_roles = []
    role_mentions = staff_roles.split()
    for mention in role_mentions:
        try:
            role_id = int(mention.strip('<@&>'))
            role = guild.get_role(role_id)
            if role and role != guild.default_role: parsed_role_ids.append(role.id) # Exclude @everyone
            else: failed_roles.append(mention)
        except ValueError: failed_roles.append(mention)

    if not parsed_role_ids: await interaction.followup.send("❌ 设置失败：未能识别任何有效的员工身份组提及。请确保使用 `@身份组名称` 并用空格分隔。", ephemeral=True); return
    warning_message = ""
    if failed_roles: warning_message = f"⚠️ 部分身份组无法识别或找到: {', '.join(failed_roles)}。已保存找到的身份组。\n"

    bot_perms_button = button_channel.permissions_for(guild.me)
    bot_perms_category = ticket_category.permissions_for(guild.me)
    if not bot_perms_button.send_messages or not bot_perms_button.embed_links or not bot_perms_button.manage_messages: await interaction.followup.send(f"{warning_message}❌ 设置失败：机器人缺少在 {button_channel.mention} 发送消息/嵌入链接/管理消息 的权限。", ephemeral=True); return
    if not bot_perms_category.manage_channels or not bot_perms_category.manage_permissions: await interaction.followup.send(f"{warning_message}❌ 设置失败：机器人缺少在分类 **{ticket_category.name}** 中 '管理频道' 或 '管理权限' 的权限。", ephemeral=True); return

    set_setting(ticket_settings, guild_id, "setup_channel_id", button_channel.id)
    set_setting(ticket_settings, guild_id, "category_id", ticket_category.id)
    set_setting(ticket_settings, guild_id, "staff_role_ids", parsed_role_ids)
    set_setting(ticket_settings, guild_id, "ticket_count", get_setting(ticket_settings, guild_id, "ticket_count") or 0)
    print(f"[票据设置] 服务器 {guild_id}: 按钮频道={button_channel.id}, 分类={ticket_category.id}, 员工角色={parsed_role_ids}")

    embed = discord.Embed(
        title="🎫 GJ Team 服务台 - 认证申请 🎫",
        description=("**需要进行实力认证或其他官方认证？**\n\n"
                     "请点击下方的 **➡️ 开票-认证** 按钮创建一个专属的私人频道。\n\n"
                     "我们的认证团队将在票据频道中为您提供帮助。\n\n"
                     "*请勿滥用此功能，每个用户同时只能开启一个认证票据。*"),
        color=discord.Color.blue()
    )
    embed.set_footer(text="GJ Team | 认证服务")

    try:
        old_message_id = get_setting(ticket_settings, guild_id, "button_message_id")
        if old_message_id:
             try:
                 old_msg = await button_channel.fetch_message(old_message_id)
                 await old_msg.delete()
                 print(f"   - 已删除旧的票据按钮消息 ({old_message_id})")
             except (discord.NotFound, discord.Forbidden): pass # Ignore if not found or no perm
             except Exception as del_e: print(f"   - 删除旧票据按钮消息时出错：{del_e}")

        button_message = await button_channel.send(embed=embed, view=CreateTicketView())
        set_setting(ticket_settings, guild_id, "button_message_id", button_message.id)
        print(f"   - 已在频道 #{button_channel.name} 发送新的票据按钮消息 ({button_message.id})")

        staff_role_mentions = [f"<@&{rid}>" for rid in parsed_role_ids]
        await interaction.followup.send(
            f"{warning_message}✅ 票据系统已成功设置！\n"
            f"- 按钮已发布在 {button_channel.mention}\n"
            f"- 票据将在 **{ticket_category.name}** 分类下创建\n"
            f"- 负责员工身份组: {', '.join(staff_role_mentions)}",
            ephemeral=True
        )
    except discord.Forbidden: await interaction.followup.send(f"{warning_message}❌ 设置成功，但在频道 {button_channel.mention} 发送按钮消息失败：机器人权限不足。", ephemeral=True)
    except Exception as e: await interaction.followup.send(f"{warning_message}❌ 设置成功，但在发送按钮消息时发生错误: {e}", ephemeral=True); print(f"发送票据按钮消息时出错: {e}")

# --- Other Management Commands ---
@manage_group.command(name="ai豁免-添加用户", description="将用户添加到 AI 内容检测的豁免列表 (管理员)。")
@app_commands.describe(user="要添加到豁免列表的用户。")
@app_commands.checks.has_permissions(administrator=True)
async def manage_ai_exempt_user_add(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)
    if user.bot: await interaction.followup.send("❌ 不能将机器人添加到豁免列表。", ephemeral=True); return
    user_id = user.id
    if user_id in exempt_users_from_ai_check: await interaction.followup.send(f"ℹ️ 用户 {user.mention} 已在 AI 检测豁免列表中。", ephemeral=True)
    else:
        exempt_users_from_ai_check.add(user_id)
        await interaction.followup.send(f"✅ 已将用户 {user.mention} 添加到 AI 内容检测豁免列表。", ephemeral=True)
        print(f"[AI豁免] 管理员 {interaction.user} 添加了用户 {user.name}({user_id}) 到豁免列表。")

@manage_group.command(name="ai豁免-移除用户", description="将用户从 AI 内容检测的豁免列表中移除 (管理员)。")
@app_commands.describe(user="要从豁免列表中移除的用户。")
@app_commands.checks.has_permissions(administrator=True)
async def manage_ai_exempt_user_remove(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)
    user_id = user.id
    if user_id in exempt_users_from_ai_check:
        exempt_users_from_ai_check.remove(user_id)
        await interaction.followup.send(f"✅ 已将用户 {user.mention} 从 AI 内容检测豁免列表中移除。", ephemeral=True)
        print(f"[AI豁免] 管理员 {interaction.user} 从豁免列表移除了用户 {user.name}({user_id})。")
    else: await interaction.followup.send(f"ℹ️ 用户 {user.mention} 不在 AI 检测豁免列表中。", ephemeral=True)

@manage_group.command(name="ai豁免-添加频道", description="将频道添加到 AI 内容检测的豁免列表 (管理员)。")
@app_commands.describe(channel="要添加到豁免列表的文字频道。")
@app_commands.checks.has_permissions(administrator=True)
async def manage_ai_exempt_channel_add(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    channel_id = channel.id
    if channel_id in exempt_channels_from_ai_check: await interaction.followup.send(f"ℹ️ 频道 {channel.mention} 已在 AI 检测豁免列表中。", ephemeral=True)
    else:
        exempt_channels_from_ai_check.add(channel_id)
        await interaction.followup.send(f"✅ 已将频道 {channel.mention} 添加到 AI 内容检测豁免列表。", ephemeral=True)
        print(f"[AI豁免] 管理员 {interaction.user} 添加了频道 #{channel.name}({channel_id}) 到豁免列表。")

@manage_group.command(name="ai豁免-移除频道", description="将频道从 AI 内容检测的豁免列表中移除 (管理员)。")
@app_commands.describe(channel="要从豁免列表中移除的文字频道。")
@app_commands.checks.has_permissions(administrator=True)
async def manage_ai_exempt_channel_remove(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    channel_id = channel.id
    if channel_id in exempt_channels_from_ai_check:
        exempt_channels_from_ai_check.remove(channel_id)
        await interaction.followup.send(f"✅ 已将频道 {channel.mention} 从 AI 内容检测豁免列表中移除。", ephemeral=True)
        print(f"[AI豁免] 管理员 {interaction.user} 从豁免列表移除了频道 #{channel.name}({channel_id})。")
    else: await interaction.followup.send(f"ℹ️ 频道 {channel.mention} 不在 AI 检测豁免列表中。", ephemeral=True)

@manage_group.command(name="ai豁免-查看列表", description="查看当前 AI 内容检测的豁免用户和频道列表 (管理员)。")
@app_commands.checks.has_permissions(administrator=True)
async def manage_ai_exempt_list(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    if not guild: await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True); return

    exempt_user_mentions = []
    for uid in exempt_users_from_ai_check:
        member = guild.get_member(uid)
        exempt_user_mentions.append(f"{member.mention} (`{member}`)" if member else f"未知用户 ({uid})")
    exempt_channel_mentions = []
    for cid in exempt_channels_from_ai_check:
        channel = guild.get_channel(cid)
        exempt_channel_mentions.append(channel.mention if channel else f"未知频道 ({cid})")

    embed = discord.Embed(title="⚙️ AI 内容检测豁免列表 (当前内存)", color=discord.Color.light_grey(), timestamp=discord.utils.utcnow())
    user_list_str = "\n".join(exempt_user_mentions) if exempt_user_mentions else "无"
    channel_list_str = "\n".join(exempt_channel_mentions) if exempt_channel_mentions else "无"
    embed.add_field(name="豁免用户", value=user_list_str[:1024], inline=False) # Max field length 1024
    embed.add_field(name="豁免频道", value=channel_list_str[:1024], inline=False)
    embed.set_footer(text="注意：此列表存储在内存中，机器人重启后会清空（除非使用数据库）。")
    await interaction.followup.send(embed=embed, ephemeral=True)

@manage_group.command(name="删讯息", description="删除指定用户在当前频道的最近消息 (需要管理消息权限)。")
@app_commands.describe(user="要删除其消息的目标用户。", amount="要检查并删除的最近消息数量 (1 到 100)。")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
async def manage_delete_user_messages(interaction: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 1, 100]):
    await interaction.response.defer(ephemeral=True)
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel): await interaction.followup.send("❌ 此命令只能在文字频道中使用。", ephemeral=True); return

    deleted_count = 0
    try:
        deleted_messages = await channel.purge(limit=amount, check=lambda m: m.author == user, reason=f"由 {interaction.user} 执行 /管理 删讯息")
        deleted_count = len(deleted_messages)
        await interaction.followup.send(f"✅ 成功在频道 {channel.mention} 中删除了用户 {user.mention} 的 {deleted_count} 条消息。", ephemeral=True)
        print(f"[审核操作] 用户 {interaction.user} 在频道 #{channel.name} 删除了用户 {user.name} 的 {deleted_count} 条消息。")
        log_embed = discord.Embed(title="🗑️ 用户消息删除", color=discord.Color.light_grey(), timestamp=discord.utils.utcnow())
        log_embed.add_field(name="执行者", value=interaction.user.mention, inline=True); log_embed.add_field(name="目标用户", value=user.mention, inline=True)
        log_embed.add_field(name="频道", value=channel.mention, inline=True); log_embed.add_field(name="删除数量", value=str(deleted_count), inline=True)
        log_embed.set_footer(text=f"执行者 ID: {interaction.user.id} | 目标用户 ID: {user.id}")
        await send_to_public_log(interaction.guild, log_embed, log_type="Delete User Messages")
    except discord.Forbidden: await interaction.followup.send(f"⚙️ 删除消息失败：机器人缺少在频道 {channel.mention} 中删除消息的权限。", ephemeral=True)
    except Exception as e: print(f"执行 /管理 删讯息 时出错: {e}"); await interaction.followup.send(f"⚙️ 删除消息时发生未知错误: {e}", ephemeral=True)

@manage_group.command(name="频道名", description="修改当前频道的名称 (需要管理频道权限)。")
@app_commands.describe(new_name="频道的新名称。")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.checks.bot_has_permissions(manage_channels=True)
async def manage_channel_name(interaction: discord.Interaction, new_name: str):
    channel = interaction.channel
    if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel, discord.Thread)):
        await interaction.response.send_message("❌ 此命令只能在文字/语音/分类频道或讨论串中使用。", ephemeral=True); return
    await interaction.response.defer(ephemeral=False)
    old_name = channel.name
    if len(new_name) > 100 or len(new_name) < 1: await interaction.followup.send("❌ 频道名称长度必须在 1 到 100 个字符之间。", ephemeral=True); return
    if not new_name.strip(): await interaction.followup.send("❌ 频道名称不能为空。", ephemeral=True); return

    try:
        await channel.edit(name=new_name, reason=f"由 {interaction.user} 修改")
        await interaction.followup.send(f"✅ 频道名称已从 `{old_name}` 修改为 `{new_name}`。", ephemeral=False)
        print(f"[管理操作] 用户 {interaction.user} 将频道 #{old_name} ({channel.id}) 重命名为 '{new_name}'。")
    except discord.Forbidden: await interaction.followup.send(f"⚙️ 修改频道名称失败：机器人缺少管理频道 {channel.mention} 的权限。", ephemeral=True)
    except Exception as e: print(f"执行 /管理 频道名 时出错: {e}"); await interaction.followup.send(f"⚙️ 修改频道名称时发生未知错误: {e}", ephemeral=True)

@manage_group.command(name="禁言", description="暂时或永久禁言成员 (需要 '超时成员' 权限)。")
@app_commands.describe(user="要禁言的目标用户。", duration_minutes="禁言的分钟数 (输入 0 表示永久禁言，即最长28天)。", reason="(可选) 禁言的原因。")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.checks.bot_has_permissions(moderate_members=True)
async def manage_mute(interaction: discord.Interaction, user: discord.Member, duration_minutes: int, reason: str = "未指定原因"):
    guild = interaction.guild
    author = interaction.user
    await interaction.response.defer(ephemeral=False)
    if user == author: await interaction.followup.send("❌ 你不能禁言自己。", ephemeral=True); return
    if user.bot: await interaction.followup.send("❌ 不能禁言机器人。", ephemeral=True); return
    if user.id == guild.owner_id: await interaction.followup.send("❌ 不能禁言服务器所有者。", ephemeral=True); return
    if user.is_timed_out():
         current_timeout = user.timed_out_until; timeout_timestamp = f"<t:{int(current_timeout.timestamp())}:R>" if current_timeout else "未知时间"
         await interaction.followup.send(f"ℹ️ 用户 {user.mention} 当前已被禁言，预计解除时间：{timeout_timestamp}。", ephemeral=True); return
    if isinstance(author, discord.Member) and author.id != guild.owner_id:
        if user.top_role >= author.top_role: await interaction.followup.send(f"🚫 你无法禁言层级等于或高于你的成员 ({user.mention})。", ephemeral=True); return
    if user.top_role >= guild.me.top_role and guild.me.id != guild.owner_id: await interaction.followup.send(f"🚫 机器人无法禁言层级等于或高于自身的成员 ({user.mention})。", ephemeral=True); return
    if duration_minutes < 0: await interaction.followup.send("❌ 禁言时长不能为负数。", ephemeral=True); return

    max_duration = datetime.timedelta(days=28); timeout_duration = None; duration_text = ""
    if duration_minutes == 0: timeout_duration = max_duration; duration_text = "永久 (最长28天)"
    else:
        requested_duration = datetime.timedelta(minutes=duration_minutes)
        if requested_duration > max_duration: timeout_duration = max_duration; duration_text = f"{duration_minutes} 分钟 (限制为28天)"; await interaction.followup.send(f"⚠️ 禁言时长超过 Discord 上限，已自动设为28天。", ephemeral=True)
        else: timeout_duration = requested_duration; duration_text = f"{duration_minutes} 分钟"

    try:
        await user.timeout(timeout_duration, reason=f"由 {author.display_name} 禁言，原因: {reason}")
        timeout_until = discord.utils.utcnow() + timeout_duration if timeout_duration else None
        timeout_timestamp = f" (<t:{int(timeout_until.timestamp())}:R> 解除)" if timeout_until else ""
        response_msg = f"✅ 用户 {user.mention} 已被成功禁言 **{duration_text}**{timeout_timestamp}。\n原因: {reason}"
        # Check response status before sending followup
        try: await interaction.followup.send(response_msg, ephemeral=False)
        except discord.NotFound: # If original response gone, try editing deferral msg (less ideal)
            try: await interaction.edit_original_response(content=response_msg)
            except: print(f"WARN: Could not send mute confirmation for {user.id}") # Log if edit fails too
        print(f"[审核操作] 用户 {author} 禁言了用户 {user} {duration_text}。原因: {reason}")
        log_embed = discord.Embed(title="🔇 用户禁言", color=discord.Color.dark_orange(), timestamp=discord.utils.utcnow())
        log_embed.add_field(name="执行者", value=author.mention, inline=True); log_embed.add_field(name="被禁言用户", value=user.mention, inline=True)
        log_embed.add_field(name="持续时间", value=duration_text, inline=False)
        if timeout_until: log_embed.add_field(name="预计解除时间", value=f"<t:{int(timeout_until.timestamp())}:F> (<t:{int(timeout_until.timestamp())}:R>)", inline=False)
        log_embed.add_field(name="原因", value=reason, inline=False)
        log_embed.set_footer(text=f"执行者 ID: {author.id} | 用户 ID: {user.id}")
        await send_to_public_log(guild, log_embed, log_type="Mute Member")
    except discord.Forbidden: await interaction.followup.send(f"⚙️ 禁言用户 {user.mention} 失败：机器人权限不足或层级不够。", ephemeral=True)
    except Exception as e: print(f"执行 /管理 禁言 时出错: {e}"); await interaction.followup.send(f"⚙️ 禁言用户 {user.mention} 时发生未知错误: {e}", ephemeral=True)

@manage_group.command(name="踢出", description="将成员踢出服务器 (需要 '踢出成员' 权限)。")
@app_commands.describe(user="要踢出的目标用户。", reason="(可选) 踢出的原因。")
@app_commands.checks.has_permissions(kick_members=True)
@app_commands.checks.bot_has_permissions(kick_members=True)
async def manage_kick(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    guild = interaction.guild
    author = interaction.user
    await interaction.response.defer(ephemeral=False)
    if user == author: await interaction.followup.send("❌ 你不能踢出自己。", ephemeral=True); return
    if user.id == guild.owner_id: await interaction.followup.send("❌ 不能踢出服务器所有者。", ephemeral=True); return
    if user.id == bot.user.id: await interaction.followup.send("❌ 不能踢出机器人自己。", ephemeral=True); return
    if isinstance(author, discord.Member) and author.id != guild.owner_id:
        if user.top_role >= author.top_role: await interaction.followup.send(f"🚫 你无法踢出层级等于或高于你的成员 ({user.mention})。", ephemeral=True); return
    if user.top_role >= guild.me.top_role and guild.me.id != guild.owner_id: await interaction.followup.send(f"🚫 机器人无法踢出层级等于或高于自身的成员 ({user.mention})。", ephemeral=True); return

    kick_reason_full = f"由 {author.display_name} 踢出，原因: {reason}"
    dm_sent = False
    try:
        try: await user.send(f"你已被管理员 **{author.display_name}** 从服务器 **{guild.name}** 中踢出。\n原因: {reason}"); dm_sent = True
        except Exception as dm_err: print(f"   - 发送踢出私信给 {user.name} 时发生错误: {dm_err}")
        await user.kick(reason=kick_reason_full)
        dm_status = "(已尝试私信通知)" if dm_sent else "(私信通知失败)"
        await interaction.followup.send(f"👢 用户 {user.mention} (`{user}`) 已被成功踢出服务器 {dm_status}。\n原因: {reason}", ephemeral=False)
        print(f"[审核操作] 用户 {author} 踢出了用户 {user}。原因: {reason}")
        log_embed = discord.Embed(title="👢 用户踢出", color=discord.Color.dark_orange(), timestamp=discord.utils.utcnow())
        log_embed.add_field(name="执行者", value=author.mention, inline=True); log_embed.add_field(name="被踢出用户", value=f"{user.mention} (`{user}`)", inline=True)
        log_embed.add_field(name="私信状态", value="成功" if dm_sent else "失败", inline=True); log_embed.add_field(name="原因", value=reason, inline=False)
        log_embed.set_footer(text=f"执行者 ID: {author.id} | 用户 ID: {user.id}")
        await send_to_public_log(guild, log_embed, log_type="Kick Member")
    except discord.Forbidden: await interaction.followup.send(f"⚙️ 踢出用户 {user.mention} 失败：机器人权限不足或层级不够。", ephemeral=True)
    except Exception as e: print(f"执行 /管理 踢出 时出错: {e}"); await interaction.followup.send(f"⚙️ 踢出用户 {user.mention} 时发生未知错误: {e}", ephemeral=True)

@manage_group.command(name="封禁", description="永久封禁成员 (需要 '封禁成员' 权限)。")
@app_commands.describe(user_id="要封禁的用户 ID (使用 ID 防止误操作)。", delete_message_days="删除该用户过去多少天的消息 (0-7，可选，默认为0)。", reason="(可选) 封禁的原因。")
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.checks.bot_has_permissions(ban_members=True)
async def manage_ban(interaction: discord.Interaction, user_id: str, delete_message_days: app_commands.Range[int, 0, 7] = 0, reason: str = "未指定原因"):
    guild = interaction.guild
    author = interaction.user
    await interaction.response.defer(ephemeral=False)
    try: target_user_id = int(user_id)
    except ValueError: await interaction.followup.send("❌ 无效的用户 ID 格式。", ephemeral=True); return
    if target_user_id == author.id: await interaction.followup.send("❌ 你不能封禁自己。", ephemeral=True); return
    if target_user_id == guild.owner_id: await interaction.followup.send("❌ 不能封禁服务器所有者。", ephemeral=True); return
    if target_user_id == bot.user.id: await interaction.followup.send("❌ 不能封禁机器人自己。", ephemeral=True); return

    banned_user_display = f"用户 ID {target_user_id}"; is_already_banned = False
    try:
        ban_entry = await guild.fetch_ban(discord.Object(id=target_user_id))
        banned_user = ban_entry.user; banned_user_display = f"**{banned_user}** (ID: {target_user_id})"; is_already_banned = True
    except discord.NotFound: pass # Not banned
    except Exception as fetch_err: print(f"检查用户 {target_user_id} 封禁状态时出错: {fetch_err}")
    if is_already_banned: await interaction.followup.send(f"ℹ️ 用户 {banned_user_display} 已经被封禁了。", ephemeral=True); return

    target_member = guild.get_member(target_user_id)
    if target_member:
        banned_user_display = f"{target_member.mention} (`{target_member}`)"
        if isinstance(author, discord.Member) and author.id != guild.owner_id:
            if target_member.top_role >= author.top_role: await interaction.followup.send(f"🚫 你无法封禁层级等于或高于你的成员 ({target_member.mention})。", ephemeral=True); return
        if target_member.top_role >= guild.me.top_role and guild.me.id != guild.owner_id: await interaction.followup.send(f"🚫 机器人无法封禁层级等于或高于自身的成员 ({target_member.mention})。", ephemeral=True); return
    else: # Try fetching user info for better display name
        try: user_obj = await bot.fetch_user(target_user_id); banned_user_display = f"**{user_obj}** (ID: {target_user_id})"
        except: pass # Keep ID display if fetch fails

    ban_reason_full = f"由 {author.display_name} 封禁，原因: {reason}"
    try:
        user_to_ban = discord.Object(id=target_user_id)
        await guild.ban(user_to_ban, reason=ban_reason_full, delete_message_days=delete_message_days)
        delete_days_text = f"并删除了其过去 {delete_message_days} 天的消息" if delete_message_days > 0 else ""
        await interaction.followup.send(f"🚫 用户 {banned_user_display} 已被成功永久封禁{delete_days_text}。\n原因: {reason}", ephemeral=False)
        print(f"[审核操作] 用户 {author} 封禁了 {banned_user_display}。原因: {reason}")
        log_embed = discord.Embed(title="🚫 用户封禁", color=discord.Color.dark_red(), timestamp=discord.utils.utcnow())
        log_embed.add_field(name="执行者", value=author.mention, inline=True); log_embed.add_field(name="被封禁用户", value=banned_user_display, inline=True)
        log_embed.add_field(name="原因", value=reason, inline=False)
        if delete_message_days > 0: log_embed.add_field(name="消息删除", value=f"删除了过去 {delete_message_days} 天的消息", inline=True)
        log_embed.set_footer(text=f"执行者 ID: {author.id} | 用户 ID: {target_user_id}")
        await send_to_public_log(guild, log_embed, log_type="Ban Member")
    except discord.Forbidden: await interaction.followup.send(f"⚙️ 封禁用户 ID {target_user_id} 失败：机器人权限不足或层级不够。", ephemeral=True)
    except discord.NotFound: await interaction.followup.send(f"❓ 封禁失败：找不到用户 ID 为 {target_user_id} 的用户。", ephemeral=True)
    except Exception as e: print(f"执行 /管理 封禁 时出错: {e}"); await interaction.followup.send(f"⚙️ 封禁用户 ID {target_user_id} 时发生未知错误: {e}", ephemeral=True)

@manage_group.command(name="解封", description="解除对用户的封禁 (需要 '封禁成员' 权限)。")
@app_commands.describe(user_id="要解除封禁的用户 ID。", reason="(可选) 解除封禁的原因。")
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.checks.bot_has_permissions(ban_members=True)
async def manage_unban(interaction: discord.Interaction, user_id: str, reason: str = "管理员酌情处理"):
    guild = interaction.guild
    author = interaction.user
    await interaction.response.defer(ephemeral=False)
    try: target_user_id = int(user_id)
    except ValueError: await interaction.followup.send("❌ 无效的用户 ID 格式。", ephemeral=True); return

    user_to_unban = None; user_display = f"用户 ID {target_user_id}"
    try:
        ban_entry = await guild.fetch_ban(discord.Object(id=target_user_id))
        user_to_unban = ban_entry.user; user_display = f"**{user_to_unban}** (ID: {target_user_id})"
    except discord.NotFound: await interaction.followup.send(f"ℹ️ {user_display} 当前并未被此服务器封禁。", ephemeral=True); return
    except discord.Forbidden: await interaction.followup.send(f"⚙️ 检查封禁状态失败：机器人缺少查看封禁列表的权限。", ephemeral=True); return
    except Exception as fetch_err: print(f"获取用户 {target_user_id} 封禁信息时出错: {fetch_err}"); await interaction.followup.send(f"⚙️ 获取封禁信息时出错: {fetch_err}", ephemeral=True); return

    unban_reason_full = f"由 {author.display_name} 解除封禁，原因: {reason}"
    try:
        await guild.unban(user_to_unban, reason=unban_reason_full)
        await interaction.followup.send(f"✅ 用户 {user_display} 已被成功解除封禁。\n原因: {reason}", ephemeral=False)
        print(f"[审核操作] 用户 {author} 解除了对 {user_display} 的封禁。原因: {reason}")
        log_embed = discord.Embed(title="✅ 用户解封", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        log_embed.add_field(name="执行者", value=author.mention, inline=True); log_embed.add_field(name="被解封用户", value=user_display, inline=True)
        log_embed.add_field(name="原因", value=reason, inline=False)
        log_embed.set_footer(text=f"执行者 ID: {author.id} | 用户 ID: {target_user_id}")
        await send_to_public_log(guild, log_embed, log_type="Unban Member")
    except discord.Forbidden: await interaction.followup.send(f"⚙️ 解封 {user_display} 失败：机器人权限不足。", ephemeral=True)
    except Exception as e: print(f"执行 /管理 解封 时出错: {e}"); await interaction.followup.send(f"⚙️ 解封 {user_display} 时发生未知错误: {e}", ephemeral=True)

@manage_group.command(name="人数频道", description="创建或更新一个显示服务器成员人数的语音频道。")
@app_commands.describe(channel_name_template="(可选) 频道名称的模板，用 '{count}' 代表人数。")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.checks.bot_has_permissions(manage_channels=True, connect=True)
async def manage_member_count_channel(interaction: discord.Interaction, channel_name_template: str = "📊｜成员人数: {count}"):
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True)
    # 使用 temp_vc_settings 存储人数频道信息
    existing_channel_id = get_setting(temp_vc_settings, guild.id, "member_count_channel_id")
    existing_template = get_setting(temp_vc_settings, guild.id, "member_count_template")
    existing_channel = guild.get_channel(existing_channel_id) if existing_channel_id else None

    member_count = guild.member_count
    try:
        new_name = channel_name_template.format(count=member_count)
        if len(new_name) > 100: await interaction.followup.send(f"❌ 失败：生成的频道名称 '{new_name}' 超过100字符。", ephemeral=True); return
        if not new_name.strip(): await interaction.followup.send(f"❌ 失败：生成的频道名称不能为空。", ephemeral=True); return
    except KeyError: await interaction.followup.send("❌ 失败：频道名称模板无效，必须包含 `{count}`。", ephemeral=True); return
    except Exception as format_err: await interaction.followup.send(f"❌ 失败：处理模板时出错: {format_err}", ephemeral=True); return

    if existing_channel and isinstance(existing_channel, discord.VoiceChannel):
        if existing_channel.name == new_name and existing_template == channel_name_template:
            await interaction.followup.send(f"ℹ️ 人数频道 {existing_channel.mention} 无需更新 (当前: {member_count})。", ephemeral=True); return
        try:
            await existing_channel.edit(name=new_name, reason="更新服务器成员人数")
            set_setting(temp_vc_settings, guild.id, "member_count_template", channel_name_template)
            await interaction.followup.send(f"✅ 已更新人数频道 {existing_channel.mention} 为 `{new_name}`。", ephemeral=True)
            print(f"[管理操作] 服务器 {guild.id} 人数频道 ({existing_channel_id}) 更新为 '{new_name}'。")
        except discord.Forbidden: await interaction.followup.send(f"⚙️ 更新频道 {existing_channel.mention} 失败：权限不足。", ephemeral=True)
        except Exception as e: print(f"更新人数频道时出错: {e}"); await interaction.followup.send(f"⚙️ 更新频道时发生未知错误: {e}", ephemeral=True)
    else: # Create new channel
        try:
            overwrites = {guild.default_role: discord.PermissionOverwrite(connect=False), guild.me: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True)}
            new_channel = await guild.create_voice_channel(name=new_name, overwrites=overwrites, position=0, reason="创建服务器成员人数统计频道")
            set_setting(temp_vc_settings, guild.id, "member_count_channel_id", new_channel.id)
            set_setting(temp_vc_settings, guild.id, "member_count_template", channel_name_template)
            await interaction.followup.send(f"✅ 已创建成员人数统计频道: {new_channel.mention}。", ephemeral=True)
            print(f"[管理操作] 服务器 {guild.id} 创建了成员人数频道 '{new_name}' ({new_channel.id})。")
        except discord.Forbidden: await interaction.followup.send(f"⚙️ 创建人数频道失败：权限不足。", ephemeral=True)
        except Exception as e: print(f"创建人数频道时出错: {e}"); await interaction.followup.send(f"⚙️ 创建人数频道时发生未知错误: {e}", ephemeral=True)


# --- Temporary Voice Channel Command Group ---
voice_group = app_commands.Group(name="语音声道", description="临时语音频道相关指令")

@voice_group.command(name="设定母频道", description="设置一个语音频道，用户加入后会自动创建临时频道 (需管理频道权限)。")
@app_commands.describe(master_channel="选择一个语音频道作为创建入口 (母频道)。", category="(可选) 选择一个分类，新创建的临时频道将放置在此分类下。")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.checks.bot_has_permissions(manage_channels=True, move_members=True, view_channel=True) # Added view_channel
async def voice_set_master(interaction: discord.Interaction, master_channel: discord.VoiceChannel, category: Optional[discord.CategoryChannel] = None):
    guild_id = interaction.guild_id
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True)
    bot_member = guild.me
    if not master_channel.permissions_for(bot_member).view_channel: await interaction.followup.send(f"❌ 设置失败：机器人无法看到母频道 {master_channel.mention}！", ephemeral=True); return
    target_category = category if category else master_channel.category
    if not target_category: await interaction.followup.send(f"❌ 设置失败：找不到有效的分类 (母频道 {master_channel.mention} 可能不在分类下，且未指定)。", ephemeral=True); return
    cat_perms = target_category.permissions_for(bot_member)
    missing_perms = [p for p, needed in {"管理频道": cat_perms.manage_channels, "移动成员": cat_perms.move_members, "查看频道": cat_perms.view_channel}.items() if not needed]
    if missing_perms: await interaction.followup.send(f"❌ 设置失败：机器人在分类 **{target_category.name}** 中缺少权限: {', '.join(missing_perms)}！", ephemeral=True); return

    set_setting(temp_vc_settings, guild_id, "master_channel_id", master_channel.id)
    set_setting(temp_vc_settings, guild_id, "category_id", target_category.id)
    cat_name_text = f" 在分类 **{target_category.name}** 下"
    await interaction.followup.send(f"✅ 临时语音频道的母频道已成功设置为 {master_channel.mention}{cat_name_text}。", ephemeral=True)
    print(f"[临时语音] 服务器 {guild_id}: 母频道={master_channel.id}, 分类={target_category.id}")

def is_temp_vc_owner(interaction: discord.Interaction) -> bool:
    if not interaction.user.voice or not interaction.user.voice.channel: return False
    user_vc = interaction.user.voice.channel
    return user_vc.id in temp_vc_owners and temp_vc_owners.get(user_vc.id) == interaction.user.id

@voice_group.command(name="设定权限", description="(房主专用) 修改你创建的临时语音频道中某个成员或身份组的权限。")
@app_commands.describe(target="要修改权限的目标用户或身份组。", allow_connect="(可选) 是否允许连接？", allow_speak="(可选) 是否允许说话？", allow_stream="(可选) 是否允许直播？", allow_video="(可选) 是否允许开启摄像头？")
async def voice_set_perms(interaction: discord.Interaction, target: Union[discord.Member, discord.Role], allow_connect: Optional[bool]=None, allow_speak: Optional[bool]=None, allow_stream: Optional[bool]=None, allow_video: Optional[bool]=None):
    await interaction.response.defer(ephemeral=True)
    user_vc = interaction.user.voice.channel if interaction.user.voice else None
    if not user_vc or not is_temp_vc_owner(interaction): await interaction.followup.send("❌ 此命令只能在你创建的临时语音频道中使用。", ephemeral=True); return
    if not user_vc.permissions_for(interaction.guild.me).manage_permissions: await interaction.followup.send(f"⚙️ 操作失败：机器人缺少在频道 {user_vc.mention} 中 '管理权限' 的能力。", ephemeral=True); return
    if target == interaction.user: await interaction.followup.send("❌ 你不能修改自己的权限。", ephemeral=True); return
    if isinstance(target, discord.Role) and target == interaction.guild.default_role: await interaction.followup.send("❌ 不能修改 `@everyone` 的权限。", ephemeral=True); return

    overwrites = user_vc.overwrites_for(target); perms_changed = []
    if allow_connect is not None: overwrites.connect = allow_connect; perms_changed.append(f"连接: {'✅' if allow_connect else '❌'}")
    if allow_speak is not None: overwrites.speak = allow_speak; perms_changed.append(f"说话: {'✅' if allow_speak else '❌'}")
    if allow_stream is not None: overwrites.stream = allow_stream; perms_changed.append(f"直播: {'✅' if allow_stream else '❌'}")
    if allow_video is not None: overwrites.video = allow_video; perms_changed.append(f"视频: {'✅' if allow_video else '❌'}")
    if not perms_changed: await interaction.followup.send("⚠️ 你没有指定任何要修改的权限。", ephemeral=True); return

    try:
        await user_vc.set_permissions(target, overwrite=overwrites, reason=f"由房主 {interaction.user.name} 修改权限")
        target_mention = target.mention if isinstance(target, discord.Member) else f"`@ {target.name}`"
        await interaction.followup.send(f"✅ 已更新 **{target_mention}** 在频道 {user_vc.mention} 的权限：\n{', '.join(perms_changed)}", ephemeral=True)
        print(f"[临时语音] 房主 {interaction.user} 修改了频道 {user_vc.id} 中 {target} 的权限: {', '.join(perms_changed)}")
    except discord.Forbidden: await interaction.followup.send(f"⚙️ 设置权限失败：机器人权限不足或层级不够。", ephemeral=True)
    except Exception as e: print(f"执行 /语音 设定权限 时出错: {e}"); await interaction.followup.send(f"⚙️ 设置权限时发生未知错误: {e}", ephemeral=True)

@voice_group.command(name="转让", description="(房主专用) 将你创建的临时语音频道所有权转让给频道内的其他用户。")
@app_commands.describe(new_owner="选择要接收所有权的新用户 (该用户必须在频道内)。")
async def voice_transfer(interaction: discord.Interaction, new_owner: discord.Member):
    await interaction.response.defer(ephemeral=False)
    user = interaction.user; user_vc = user.voice.channel if user.voice else None
    if not user_vc or not is_temp_vc_owner(interaction): await interaction.followup.send("❌ 此命令只能在你创建的临时语音频道中使用。", ephemeral=True); return
    if new_owner.bot: await interaction.followup.send("❌ 不能转让给机器人。", ephemeral=True); return
    if new_owner == user: await interaction.followup.send("❌ 不能转让给自己。", ephemeral=True); return
    if not new_owner.voice or new_owner.voice.channel != user_vc: await interaction.followup.send(f"❌ 目标用户 {new_owner.mention} 必须在你的频道 ({user_vc.mention}) 内。", ephemeral=True); return
    if not user_vc.permissions_for(interaction.guild.me).manage_permissions: await interaction.followup.send(f"⚙️ 操作失败：机器人缺少 '管理权限' 能力。", ephemeral=True); return

    try:
        new_owner_overwrites = discord.PermissionOverwrite(manage_channels=True, manage_permissions=True, move_members=True, connect=True, speak=True, stream=True, use_voice_activation=True, priority_speaker=True, mute_members=True, deafen_members=True, use_embedded_activities=True, video=True)
        old_owner_overwrites = discord.PermissionOverwrite() # Clear old owner's special perms
        await user_vc.set_permissions(new_owner, overwrite=new_owner_overwrites, reason=f"所有权由 {user.name} 转让")
        await user_vc.set_permissions(user, overwrite=old_owner_overwrites, reason=f"所有权转让给 {new_owner.name}")
        temp_vc_owners[user_vc.id] = new_owner.id
        await interaction.followup.send(f"✅ 频道 {user_vc.mention} 的所有权已成功转让给 {new_owner.mention}！", ephemeral=False)
        print(f"[临时语音] 频道 {user_vc.id} 所有权从 {user.id} 转让给 {new_owner.id}")
    except discord.Forbidden: await interaction.followup.send(f"⚙️ 转让失败：机器人权限不足。", ephemeral=True)
    except Exception as e: print(f"执行 /语音 转让 时出错: {e}"); await interaction.followup.send(f"⚙️ 转让时发生未知错误: {e}", ephemeral=True)

@voice_group.command(name="房主", description="(成员使用) 如果原房主已离开频道，尝试获取该临时语音频道的所有权。")
async def voice_claim(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    user = interaction.user; user_vc = user.voice.channel if user.voice else None
    if not user_vc or user_vc.id not in temp_vc_created: await interaction.followup.send("❌ 此命令只能在临时语音频道中使用。", ephemeral=True); return

    current_owner_id = temp_vc_owners.get(user_vc.id)
    if current_owner_id == user.id: await interaction.followup.send("ℹ️ 你已经是房主了。", ephemeral=True); return

    owner_is_present = False; original_owner = None
    if current_owner_id:
        original_owner = interaction.guild.get_member(current_owner_id)
        if original_owner and original_owner.voice and original_owner.voice.channel == user_vc: owner_is_present = True
    if owner_is_present: await interaction.followup.send(f"❌ 无法获取所有权：原房主 {original_owner.mention} 仍在频道中。", ephemeral=True); return
    if not user_vc.permissions_for(interaction.guild.me).manage_permissions: await interaction.followup.send(f"⚙️ 操作失败：机器人缺少 '管理权限' 能力。", ephemeral=True); return

    try:
        new_owner_overwrites = discord.PermissionOverwrite(manage_channels=True, manage_permissions=True, move_members=True, connect=True, speak=True, stream=True, use_voice_activation=True, priority_speaker=True, mute_members=True, deafen_members=True, use_embedded_activities=True, video=True)
        await user_vc.set_permissions(user, overwrite=new_owner_overwrites, reason=f"由 {user.name} 获取房主权限")
        if original_owner: # Reset old owner perms if they existed
             try: await user_vc.set_permissions(original_owner, overwrite=None, reason="原房主离开，重置权限")
             except Exception as reset_e: print(f"   - 重置原房主 {original_owner.id} 权限时出错: {reset_e}")
        temp_vc_owners[user_vc.id] = user.id
        await interaction.followup.send(f"✅ 恭喜 {user.mention}！你已成功获取频道 {user_vc.mention} 的房主权限！", ephemeral=False)
        print(f"[临时语音] 用户 {user.id} 获取了频道 {user_vc.id} 的房主权限 (原房主: {current_owner_id})")
    except discord.Forbidden: await interaction.followup.send(f"⚙️ 获取房主权限失败：机器人权限不足。", ephemeral=True)
    except Exception as e: print(f"执行 /语音 房主 时出错: {e}"); await interaction.followup.send(f"⚙️ 获取房主权限时发生未知错误: {e}", ephemeral=True)


# --- Add the command groups to the bot tree ---
bot.tree.add_command(manage_group)
bot.tree.add_command(voice_group)

# --- Run the Bot ---
if __name__ == "__main__":
    print("正在启动机器人...")
    if not BOT_TOKEN:
        print("❌ 致命错误：无法启动，因为 DISCORD_BOT_TOKEN 未设置。")
        exit()

    if not DEEPSEEK_API_KEY: print("⚠️ 警告：DEEPSEEK_API_KEY 未设置，AI 内容审核功能将不可用。")

    async def main():
        # Initialize aiohttp session within async context
        if AIOHTTP_AVAILABLE:
            bot.http_session = aiohttp.ClientSession()
            print("已创建 aiohttp 会话。")
        else:
            bot.http_session = None # Indicate session is not available

        try:
            await bot.start(BOT_TOKEN)
        except discord.LoginFailure:
            print("❌ 致命错误：登录失败。提供的 DISCORD_BOT_TOKEN 无效。")
        except discord.PrivilegedIntentsRequired:
            print("❌ 致命错误：机器人缺少必要的特权 Intents (Members, Message Content, Guilds)。请在 Discord 开发者门户中启用它们！")
        except Exception as e:
            print(f"❌ 机器人启动过程中发生致命错误: {e}")
        finally:
            # Clean up session when bot closes
            if hasattr(bot, 'http_session') and bot.http_session:
                await bot.http_session.close()
                print("已关闭 aiohttp 会话。")
            await bot.close() # Ensure bot connection is closed properly

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n收到退出信号，正在关闭机器人...")
    except Exception as main_err:
        print(f"\n运行主程序时发生未捕获错误: {main_err}")

# --- End of Complete Code ---