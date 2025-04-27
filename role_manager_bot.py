# slash_role_manager_bot.py (FINAL COMPLETE CODE v22 - Chinese AI Results & Bug Fix)

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
    1362713317222912140, # <--- 替换! 示例 ID
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

# --- Temporary Voice Channel Config & Storage (In-Memory) ---
temp_vc_settings = {}  # {guild_id: {"master_channel_id": id, "category_id": id, ...}}
temp_vc_owners = {}    # {channel_id: owner_user_id}
temp_vc_created = set()  # {channel_id1, channel_id2, ...}

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
def get_setting(guild_id: int, key: str):
    """获取服务器设置（内存模拟）"""
    return temp_vc_settings.get(guild_id, {}).get(key)

def set_setting(guild_id: int, key: str, value):
    """设置服务器设置（内存模拟）"""
    if guild_id not in temp_vc_settings:
        temp_vc_settings[guild_id] = {}
    temp_vc_settings[guild_id][key] = value
    print(f"[内存设置更新] 服务器 {guild_id}: {key}={value}")

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

        print(f"DEBUG: DeepSeek 对 '{message_content[:30]}...' 的响应: {api_response_text}")

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

# --- Event: Bot Ready ---
@bot.event
async def on_ready():
    print(f'以 {bot.user.name} ({bot.user.id}) 身份登录')
    print('正在同步应用程序命令...')
    try:
        # 同步全局命令。如果只想同步特定服务器，使用：
        # await bot.tree.sync(guild=discord.Object(id=YOUR_GUILD_ID))
        synced = await bot.tree.sync()
        print(f'已全局同步 {len(synced)} 个应用程序命令。')
    except Exception as e:
        print(f'同步命令时出错: {e}')
    print('机器人已准备就绪！')
    print('------')
    # 设置机器人状态
    await bot.change_presence(activity=discord.Game(name="/help 显示帮助"))

# --- Event: Command Error Handling (Legacy Prefix Commands) ---
@bot.event
async def on_command_error(ctx, error):
    # 这个主要处理旧的 ! 前缀命令错误，现在用得少了
    if isinstance(error, commands.CommandNotFound):
        return # 忽略未找到的旧命令
    elif isinstance(error, commands.MissingPermissions):
        try:
            await ctx.send(f"🚫 你缺少使用此旧命令所需的权限: {error.missing_permissions}")
        except discord.Forbidden:
            pass # 无法发送消息就算了
    elif isinstance(error, commands.BotMissingPermissions):
         try:
            await ctx.send(f"🤖 我缺少执行此旧命令所需的权限: {error.missing_permissions}")
         except discord.Forbidden:
             pass
    else:
        print(f"处理旧命令 '{ctx.command}' 时出错: {error}")

# --- Event: App Command Error Handling (Slash Commands) ---
# 这个函数会捕获斜线命令执行中的错误
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
        print(f"指令 '{interaction.command.name if interaction.command else '未知'}' 执行失败: {original}") # 在后台打印详细错误
        if isinstance(original, discord.Forbidden):
            error_message = f"🚫 Discord权限错误：我无法执行此操作（通常是身份组层级问题或频道权限不足）。"
        elif isinstance(original, discord.HTTPException):
             error_message = f"🌐 网络错误：与 Discord API 通信时发生问题 (HTTP {original.status})。"
        else:
            error_message = f"⚙️ 执行指令时发生内部错误。请联系管理员。" # 对用户显示通用错误
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
    verification_channel_id = 1352886274691956756 # <--- 替换! 验证频道 ID

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
                embed = discord.Embed(
                    title=f"🎉 欢迎来到 {guild.name}! 🎉",
                    description=f"你好 {member.mention}! 很高兴你能加入 **GJ Team**！\n\n"
                                f"👇 **开始之前，请务必查看:**\n"
                                f"- 服务器规则: <#{rules_channel_id}>\n"
                                f"- 身份组信息: <#{roles_info_channel_id}>\n"
                                f"- TSB实力认证: <#{verification_channel_id}>\n\n" # 使用频道提及
                                f"祝你在 **GJ Team** 玩得愉快！",
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
        print(f"⚠️ 在服务器 {guild.name} 中找不到欢迎频道 ID: {welcome_channel_id}。")


# --- Event: On Message - Handles Content Check, Spam ---
# !!! 这是核心的消息处理逻辑 !!!
@bot.event
async def on_message(message: discord.Message):
    # --- 基本过滤 ---
    # 1. 忽略私聊消息
    if not message.guild:
        return
    # 2. 忽略机器人自己或其他机器人发的消息 (但保留对特定机器人刷屏的检测逻辑)
    #    对普通消息处理流程忽略机器人，后面会单独处理机器人刷屏
    if message.author.bot and message.author.id != bot.user.id:
        # 转到机器人刷屏检测逻辑
        pass # 让它继续往下走，进入机器人刷屏检测部分
    elif message.author.id == bot.user.id:
         return # 忽略自己发的消息

    # --- 获取常用变量 ---
    now = datetime.datetime.now(datetime.timezone.utc)
    author = message.author
    author_id = author.id
    guild = message.guild
    channel = message.channel
    # 尝试获取 Member 对象，后续权限检查等可能需要
    member = guild.get_member(author_id) # 比 message.author 更可靠，包含服务器特定信息

    # --- 忽略管理员/版主的消息 (基于'管理消息'权限) ---
    if member and channel.permissions_for(member).manage_messages:
        # print(f"DEBUG: 跳过对管理员/版主 {author.name} 的消息检查。") # 可选的调试信息
        return # 管理员/版主的消息直接放行，不进行后续检查

    # --- 标记是否需要进行内容检查 (AI + 本地违禁词) ---
    perform_content_check = True
    # 检查用户豁免
    if author_id in exempt_users_from_ai_check:
        perform_content_check = False
        # print(f"DEBUG: 用户 {author.name} ({author_id}) 在 AI 豁免名单中，跳过内容检查。")
    # 检查频道豁免
    elif channel.id in exempt_channels_from_ai_check:
        perform_content_check = False
        # print(f"DEBUG: 频道 #{channel.name} ({channel.id}) 在 AI 豁免名单中，跳过内容检查。")

    # --- 执行内容检查 (仅当未被豁免时) ---
    if perform_content_check:
        # --- 1. DeepSeek API 内容审核 (主要检查) ---
        # violation_type 现在预期是中文违规类型或 None
        violation_type = await check_message_with_deepseek(message.content)

        if violation_type: # 如果返回了非 None 值，说明检测到严重违规
            print(f"🚫 API 违规 ({violation_type}): 用户 {author} 在频道 #{channel.name}")
            reason_api = f"自动检测到违规内容 ({violation_type})"
            delete_success = False
            try:
                # 检查机器人是否有删除消息的权限
                if channel.permissions_for(guild.me).manage_messages:
                    await message.delete()
                    print("   - 已删除违规消息 (API 检测)。")
                    delete_success = True
                else:
                    print("   - 机器人缺少 '管理消息' 权限，无法删除。")
            except discord.NotFound:
                 print("   - 尝试删除消息时未找到该消息 (可能已被删除)。")
                 delete_success = True # 视为已处理
            except discord.Forbidden:
                 print("   - 尝试删除消息时权限不足。")
            except Exception as del_e:
                print(f"   - 删除消息时发生错误 (API 检测): {del_e}")

            # 准备通知管理员
            mod_mentions = " ".join([f"<@&{role_id}>" for role_id in MOD_ALERT_ROLE_IDS])
            log_embed_api = discord.Embed(
                title=f"🚨 自动内容审核提醒 ({violation_type}) 🚨",
                color=discord.Color.dark_red(),
                timestamp=now
            )
            log_embed_api.add_field(name="用户", value=f"{author.mention} ({author_id})", inline=False)
            log_embed_api.add_field(name="频道", value=channel.mention, inline=False)
            log_embed_api.add_field(name="内容摘要", value=f"```{message.content[:1000]}```", inline=False) # 限制长度
            log_embed_api.add_field(name="消息状态", value="已删除" if delete_success else "删除失败/无权限", inline=True)
            log_embed_api.add_field(name="消息链接", value=f"[原始链接]({message.jump_url}) (可能已删除)", inline=True)
            log_embed_api.add_field(name="建议操作", value=f"{mod_mentions} 请管理员审核并处理！", inline=False)

            # 发送到公共日志频道
            await send_to_public_log(guild, log_embed_api, log_type=f"API Violation ({violation_type})")

            return # 处理完 API 违规后，停止对该消息的后续处理

        # --- 2. 本地违禁词检测 (可选的后备检查) ---
        # 只有在 DeepSeek API 认为安全或轻微违规 (violation_type is None)
        # 且本地违禁词列表不为空时，才进行此检查
        if not violation_type and BAD_WORDS_LOWER:
            content_lower = message.content.lower()
            triggered_bad_word = None
            for word in BAD_WORDS_LOWER:
                # 简单的包含检查，对于某些词可能需要更精确的匹配（例如使用正则表达式或词边界）
                if word in content_lower:
                    triggered_bad_word = word
                    break # 找到一个就停止

            if triggered_bad_word:
                print(f"🚫 本地违禁词: '{triggered_bad_word}' 来自用户 {message.author} 在频道 #{channel.name}")
                guild_offenses = user_first_offense_reminders.setdefault(guild.id, {})
                user_offenses = guild_offenses.setdefault(author_id, set())

                # --- 初犯提醒 ---
                if triggered_bad_word not in user_offenses:
                    user_offenses.add(triggered_bad_word)
                    print(f"   - '{triggered_bad_word}' 为该用户初犯，发送提醒。")
                    try:
                        # !!! 重要：替换为你的规则频道 ID !!!
                        rules_ch_id = 1280026139326283799 # <--- 替换! 你的规则频道 ID
                        rules_ch_mention = f"<#{rules_ch_id}>" if rules_ch_id and rules_ch_id != 123456789012345679 else "#规则" # Fallback

                        reminder_msg = await channel.send(
                            f"{author.mention}，请注意你的言辞并遵守服务器规则 ({rules_ch_mention})。本次仅为提醒，再犯将可能受到警告。",
                            delete_after=25 # 25秒后自动删除提醒消息
                        )
                    except discord.Forbidden:
                         print("   - 发送违禁词提醒失败：机器人缺少在当前频道发送消息的权限。")
                    except Exception as remind_err:
                        print(f"   - 发送违禁词提醒时发生错误: {remind_err}")
                    # 尝试删除触发的消息
                    try:
                        if channel.permissions_for(guild.me).manage_messages:
                            await message.delete()
                            print("   - 已删除包含初犯违禁词的消息。")
                    except Exception:
                         print("   - 删除初犯违禁词消息时出错或无权限。")

                    return # 发送提醒后，停止处理该消息

                # --- 累犯 -> 发出警告 ---
                else:
                    print(f"   - '{triggered_bad_word}' 为该用户累犯，发出警告。")
                    reason = f"自动警告：再次使用不当词语 '{triggered_bad_word}'"
                    user_warnings[author_id] = user_warnings.get(author_id, 0) + 1
                    warning_count = user_warnings[author_id]
                    print(f"   - 用户当前警告次数: {warning_count}/{KICK_THRESHOLD}")

                    # 准备警告 Embed
                    warn_embed = discord.Embed(color=discord.Color.orange(), timestamp=now)
                    warn_embed.set_author(name=f"自动警告发出 (不当言语)", icon_url=bot.user.display_avatar.url)
                    warn_embed.add_field(name="用户", value=f"{author.mention} ({author_id})", inline=False)
                    warn_embed.add_field(name="原因", value=reason, inline=False)
                    warn_embed.add_field(name="当前警告次数", value=f"{warning_count}/{KICK_THRESHOLD}", inline=False)
                    warn_embed.add_field(name="触发消息", value=f"[{message.content[:50]}...]({message.jump_url})", inline=False) # 简短内容和链接

                    kick_performed_bw = False # 标记是否执行了踢出

                    # 检查是否达到踢出阈值
                    if warning_count >= KICK_THRESHOLD:
                        warn_embed.title = "🚨 警告已达上限 - 自动踢出 (不当言语) 🚨"
                        warn_embed.color = discord.Color.red()
                        warn_embed.add_field(name="处理措施", value="用户已被自动踢出服务器", inline=False)
                        print(f"   - 用户 {author} 因不当言语达到踢出阈值。")

                        if member: # 确保有 Member 对象才能踢出
                            bot_member = guild.me
                            kick_reason_bw = f"自动踢出：因使用不当言语累计达到 {KICK_THRESHOLD} 次警告。"
                            # 检查踢出权限和层级
                            can_kick = bot_member.guild_permissions.kick_members and \
                                       (bot_member.top_role > member.top_role or bot_member == guild.owner)

                            if can_kick:
                                try:
                                    # 尝试私信通知用户
                                    try:
                                        await member.send(f"由于在服务器 **{guild.name}** 中累计达到 {KICK_THRESHOLD} 次不当言语警告（最后触发词：'{triggered_bad_word}'），你已被自动踢出。")
                                    except discord.Forbidden:
                                        print(f"   - 无法向用户 {member.name} 发送踢出私信 (权限不足或用户设置)。")
                                    except Exception as dm_err:
                                        print(f"   - 发送踢出私信给 {member.name} 时发生错误: {dm_err}")

                                    # 执行踢出
                                    await member.kick(reason=kick_reason_bw)
                                    print(f"   - 已成功踢出用户 {member.name} (不当言语)。")
                                    kick_performed_bw = True
                                    user_warnings[author_id] = 0 # 踢出成功后重置警告次数
                                    warn_embed.add_field(name="踢出状态", value="✅ 成功", inline=False)
                                except discord.Forbidden:
                                    print(f"   - 踢出用户 {member.name} 失败：机器人权限不足。")
                                    warn_embed.add_field(name="踢出状态", value="❌ 失败 (权限不足)", inline=False)
                                except discord.HTTPException as kick_http_err:
                                    print(f"   - 踢出用户 {member.name} 时发生网络错误: {kick_http_err}")
                                    warn_embed.add_field(name="踢出状态", value=f"❌ 失败 (网络错误 {kick_http_err.status})", inline=False)
                                except Exception as kick_err:
                                    print(f"   - 踢出用户 {member.name} 时发生未知错误: {kick_err}")
                                    warn_embed.add_field(name="踢出状态", value=f"❌ 失败 ({kick_err})", inline=False)
                            else:
                                print(f"   - 无法踢出用户 {member.name}：机器人权限不足或层级不够。")
                                warn_embed.add_field(name="踢出状态", value="❌ 失败 (权限/层级不足)", inline=False)
                        else:
                            print(f"   - 无法获取用户 {author_id} 的 Member 对象，无法执行踢出。")
                            warn_embed.add_field(name="踢出状态", value="❌ 失败 (无法获取成员对象)", inline=False)
                    else: # 未达到踢出阈值，仅警告
                        warn_embed.title = "⚠️ 自动警告已发出 (不当言语) ⚠️"

                    # 无论是否踢出，都发送日志
                    await send_to_public_log(guild, warn_embed, log_type="Auto Warn (Bad Word)")

                     # 尝试删除触发的消息
                    try:
                        if channel.permissions_for(guild.me).manage_messages:
                            await message.delete()
                            print("   - 已删除包含累犯违禁词的消息。")
                    except Exception:
                         print("   - 删除累犯违禁词消息时出错或无权限。")

                    # 如果没有被踢出，在频道内发送一个简短的公开警告
                    if not kick_performed_bw:
                        try:
                            await channel.send(
                                f"⚠️ {author.mention}，你的言论再次触发警告 (不当言语)。当前警告次数: {warning_count}/{KICK_THRESHOLD}",
                                delete_after=20 # 20秒后自动删除
                            )
                        except Exception as e:
                            print(f"   - 发送频道内警告消息时出错: {e}")

                    return # 处理完违禁词后，停止处理该消息

    # --- END OF CONTENT CHECK BLOCK ---


    # --- Bot Spam Detection Logic ---
    # 只有当消息发送者是机器人时才执行
    if message.author.bot and message.author.id != bot.user.id:
        bot_author_id = message.author.id
        bot_message_timestamps.setdefault(bot_author_id, [])
        bot_message_timestamps[bot_author_id].append(now)
        # 清理旧的时间戳
        time_limit_bot = now - datetime.timedelta(seconds=BOT_SPAM_TIME_WINDOW_SECONDS)
        bot_message_timestamps[bot_author_id] = [ts for ts in bot_message_timestamps[bot_author_id] if ts > time_limit_bot]

        # 检查时间窗口内的消息数量
        if len(bot_message_timestamps[bot_author_id]) >= BOT_SPAM_COUNT_THRESHOLD:
            print(f"🚨 检测到机器人刷屏! Bot: {message.author} ({bot_author_id}) 在频道 #{channel.name}")
            bot_message_timestamps[bot_author_id] = [] # 检测到后重置时间戳列表
            mod_mentions = " ".join([f"<@&{role_id}>" for role_id in MOD_ALERT_ROLE_IDS])
            action_summary = "正在尝试自动处理..." # 初始状态

            spamming_bot_member = guild.get_member(bot_author_id) # 获取刷屏机器人的 Member 对象
            my_bot_member = guild.me # 机器人自己的 Member 对象
            kick_succeeded = False
            role_removal_succeeded = False

            if spamming_bot_member:
                # 尝试踢出
                can_kick_bot = my_bot_member.guild_permissions.kick_members and \
                               (my_bot_member.top_role > spamming_bot_member.top_role) # 不能踢同级或更高级

                if can_kick_bot:
                    try:
                        await spamming_bot_member.kick(reason="自动踢出：检测到机器人刷屏")
                        action_summary = "**➡️ 自动操作：已成功踢出该机器人。**"
                        kick_succeeded = True
                        print(f"   - 已成功踢出刷屏机器人 {spamming_bot_member.name}。")
                    except discord.Forbidden:
                        action_summary = "**➡️ 自动操作：尝试踢出失败 (权限问题)。**"
                        print(f"   - 踢出机器人 {spamming_bot_member.name} 失败 (Forbidden)。")
                    except Exception as kick_err:
                        action_summary = f"**➡️ 自动操作：尝试踢出时发生错误: {kick_err}**"
                        print(f"   - 踢出机器人 {spamming_bot_member.name} 时出错: {kick_err}")
                elif my_bot_member.guild_permissions.kick_members:
                     action_summary = "**➡️ 自动操作：无法踢出 (目标机器人层级不低于我)。**"
                     print(f"   - 无法踢出机器人 {spamming_bot_member.name} (层级不足)。")
                else:
                    action_summary = "**➡️ 自动操作：机器人缺少“踢出成员”权限，无法尝试踢出。**"
                    print("   - 机器人缺少踢出权限。")

                # 如果踢出未成功，尝试移除其身份组 (作为备选方案)
                can_manage_roles = my_bot_member.guild_permissions.manage_roles
                if not kick_succeeded and can_manage_roles:
                    # 找出所有低于机器人自身最高身份组的、非 @everyone 的身份组
                    roles_to_try_removing = [
                        r for r in spamming_bot_member.roles
                        if r != guild.default_role and r < my_bot_member.top_role
                    ]
                    if roles_to_try_removing:
                        print(f"   - 尝试移除机器人 {spamming_bot_member.name} 的身份组: {[r.name for r in roles_to_try_removing]}")
                        try:
                            await spamming_bot_member.remove_roles(*roles_to_try_removing, reason="自动移除身份组：检测到机器人刷屏")
                            role_removal_succeeded = True
                            # 更新行动摘要
                            if kick_succeeded: # 虽然不太可能，但以防万一
                                 action_summary += "\n**➡️ 自动操作：另外，也尝试移除了其身份组。**"
                            else:
                                 action_summary = "**➡️ 自动操作：踢出失败/无法踢出，但已尝试移除该机器人的身份组。**"

                            print(f"   - 已成功移除机器人 {spamming_bot_member.name} 的部分身份组。")
                        except discord.Forbidden:
                            if kick_succeeded: action_summary += "\n**➡️ 自动操作：尝试移除身份组失败 (权限/层级问题)。**"
                            else: action_summary = "**➡️ 自动操作：尝试移除身份组失败 (权限/层级问题)。**"
                            print(f"   - 移除机器人 {spamming_bot_member.name} 身份组失败 (Forbidden/层级)。")
                        except Exception as role_err:
                             if kick_succeeded: action_summary += f"\n**➡️ 自动操作：尝试移除身份组时出错: {role_err}**"
                             else: action_summary = f"**➡️ 自动操作：尝试移除身份组时出错: {role_err}**"
                             print(f"   - 移除机器人 {spamming_bot_member.name} 身份组时出错: {role_err}")
                    else:
                        print(f"   - 未找到低于机器人自身层级的身份组可供移除 (机器人 {spamming_bot_member.name})。")
                        if not kick_succeeded: action_summary = "**➡️ 自动操作：踢出失败/无法踢出，且未找到可移除的低层级身份组。**"

                elif not kick_succeeded and not can_manage_roles:
                    print("   - 机器人也缺少“管理身份组”权限。")
                    if not kick_succeeded: action_summary = "**➡️ 自动操作：无法踢出，且机器人缺少管理身份组权限。**"


            else: # 无法获取刷屏机器人的 Member 对象
                action_summary = "**➡️ 自动操作：无法获取该机器人成员对象，无法执行操作。**"
                print(f"   - 无法找到 ID 为 {bot_author_id} 的机器人成员对象。")

            # 发送警报给管理员
            final_alert = (
                f"🚨 **机器人刷屏警报!** 🚨\n"
                f"机器人: {message.author.mention} ({bot_author_id})\n"
                f"频道: {channel.mention}\n"
                f"{action_summary}\n" # 显示自动处理结果
                f"{mod_mentions} 请管理员关注并采取进一步措施！"
            )
            try:
                await channel.send(final_alert)
                print(f"   - 已发送机器人刷屏警报。")
            except Exception as alert_err:
                print(f"   - 发送机器人刷屏警报时出错: {alert_err}")

            # 尝试删除该机器人最近的消息
            deleted_count = 0
            if channel.permissions_for(guild.me).manage_messages:
                print(f"   - 尝试自动清理来自 {message.author.name} 的刷屏消息...")
                try:
                    # 检查稍微多一点的消息，以防万一
                    limit_check = BOT_SPAM_COUNT_THRESHOLD * 3
                    # 删除特定机器人在特定时间窗口之后的消息
                    deleted_messages = await channel.purge(
                        limit=limit_check,
                        check=lambda m: m.author.id == bot_author_id,
                        after=now - datetime.timedelta(seconds=BOT_SPAM_TIME_WINDOW_SECONDS * 2), # 删除时间范围稍长一点
                        reason="自动清理机器人刷屏消息"
                    )
                    deleted_count = len(deleted_messages)
                    print(f"   - 成功删除了 {deleted_count} 条来自 {message.author.name} 的消息。")
                    if deleted_count > 0:
                        try:
                           await channel.send(f"🧹 已自动清理 {deleted_count} 条来自 {message.author.mention} 的刷屏消息。", delete_after=15)
                        except Exception as send_err:
                           print(f"   - 发送清理确认消息时出错: {send_err}")
                except discord.Forbidden:
                     print(f"   - 清理机器人消息失败：机器人缺少 '管理消息' 权限。")
                except discord.HTTPException as http_err:
                      print(f"   - 清理机器人消息时发生网络错误: {http_err}")
                except Exception as del_err:
                    print(f"   - 清理机器人消息过程中发生错误: {del_err}")
            else:
                print("   - 机器人缺少 '管理消息' 权限，无法清理机器人刷屏。")

            return # 处理完机器人刷屏后停止

    # --- 4. User Spam Detection Logic ---
    # 这个逻辑对所有非机器人用户都执行，无论是否被内容豁免
    if not message.author.bot: # 再次确认是用户
        user_message_timestamps.setdefault(author_id, [])
        user_warnings.setdefault(author_id, 0) # 确保用户在警告字典中

        user_message_timestamps[author_id].append(now)
        # 清理旧的时间戳
        time_limit_user = now - datetime.timedelta(seconds=SPAM_TIME_WINDOW_SECONDS)
        user_message_timestamps[author_id] = [ts for ts in user_message_timestamps[author_id] if ts > time_limit_user]

        # 检查时间窗口内的消息数量
        if len(user_message_timestamps[author_id]) >= SPAM_COUNT_THRESHOLD:
            print(f"🚨 检测到用户刷屏! 用户: {author} ({author_id}) 在频道 #{channel.name}")
            user_warnings[author_id] += 1
            warning_count = user_warnings[author_id]
            print(f"   - 用户当前警告次数 (刷屏): {warning_count}/{KICK_THRESHOLD}")
            user_message_timestamps[author_id] = [] # 检测到刷屏后重置时间戳列表

            # 准备日志 Embed
            log_embed_user = discord.Embed(color=discord.Color.orange(), timestamp=now)
            log_embed_user.set_author(name=f"自动警告发出 (用户刷屏)", icon_url=bot.user.display_avatar.url)
            log_embed_user.add_field(name="用户", value=f"{author.mention} ({author_id})", inline=False)
            log_embed_user.add_field(name="频道", value=channel.mention, inline=True)
            log_embed_user.add_field(name="触发消息数", value=f"≥ {SPAM_COUNT_THRESHOLD} 条 / {SPAM_TIME_WINDOW_SECONDS} 秒", inline=True)
            log_embed_user.add_field(name="当前警告次数", value=f"{warning_count}/{KICK_THRESHOLD}", inline=False)
            # 链接到触发阈值的最后一条消息
            log_embed_user.add_field(name="最后消息链接", value=f"[点击跳转]({message.jump_url})", inline=False)

            kick_performed_spam = False # 标记是否执行了踢出

            # 检查是否达到踢出阈值
            if warning_count >= KICK_THRESHOLD:
                log_embed_user.title = "🚨 警告已达上限 - 自动踢出 (用户刷屏) 🚨"
                log_embed_user.color = discord.Color.red()
                log_embed_user.add_field(name="处理措施", value="用户已被自动踢出服务器", inline=False)
                print(f"   - 用户 {author} 因刷屏达到踢出阈值。")

                if member: # 确保有 Member 对象
                    bot_member = guild.me
                    kick_reason_spam = f"自动踢出：因刷屏累计达到 {KICK_THRESHOLD} 次警告。"
                     # 检查踢出权限和层级
                    can_kick_user = bot_member.guild_permissions.kick_members and \
                                    (bot_member.top_role > member.top_role or bot_member == guild.owner)

                    if can_kick_user:
                        try:
                             # 尝试私信通知用户
                            try:
                                await member.send(f"由于在服务器 **{guild.name}** 中累计达到 {KICK_THRESHOLD} 次刷屏警告，你已被自动踢出。")
                            except discord.Forbidden:
                                print(f"   - 无法向用户 {member.name} 发送踢出私信 (权限不足或用户设置)。")
                            except Exception as dm_err:
                                print(f"   - 发送踢出私信给 {member.name} 时发生错误: {dm_err}")

                            # 执行踢出
                            await member.kick(reason=kick_reason_spam)
                            print(f"   - 已成功踢出用户 {member.name} (用户刷屏)。")
                            kick_performed_spam = True
                            user_warnings[author_id] = 0 # 踢出成功后重置警告次数
                            log_embed_user.add_field(name="踢出状态", value="✅ 成功", inline=False)
                        except discord.Forbidden:
                            print(f"   - 踢出用户 {member.name} 失败：机器人权限不足。")
                            log_embed_user.add_field(name="踢出状态", value="❌ 失败 (权限不足)", inline=False)
                        except discord.HTTPException as kick_http_err:
                             print(f"   - 踢出用户 {member.name} 时发生网络错误: {kick_http_err}")
                             log_embed_user.add_field(name="踢出状态", value=f"❌ 失败 (网络错误 {kick_http_err.status})", inline=False)
                        except Exception as kick_err:
                            print(f"   - 踢出用户 {member.name} 时发生未知错误: {kick_err}")
                            log_embed_user.add_field(name="踢出状态", value=f"❌ 失败 ({kick_err})", inline=False)
                    else:
                        print(f"   - 无法踢出用户 {member.name}：机器人权限不足或层级不够。")
                        log_embed_user.add_field(name="踢出状态", value="❌ 失败 (权限/层级不足)", inline=False)
                else:
                    print(f"   - 无法获取用户 {author_id} 的 Member 对象，无法执行踢出。")
                    log_embed_user.add_field(name="踢出状态", value="❌ 失败 (无法获取成员对象)", inline=False)
            else: # 未达到踢出阈值，仅警告
                log_embed_user.title = "⚠️ 自动警告已发出 (用户刷屏) ⚠️"

            # 发送日志
            await send_to_public_log(guild, log_embed_user, log_type="Auto Warn (User Spam)")

            # 如果用户没有被踢出，在频道内发送公开警告
            if not kick_performed_spam:
                try:
                    await message.channel.send(
                        f"⚠️ {author.mention}，检测到你发送消息过于频繁，请减缓速度！(警告 {warning_count}/{KICK_THRESHOLD})",
                        delete_after=15 # 15秒后自动删除
                    )
                except Exception as warn_err:
                    print(f"   - 发送用户刷屏警告消息时出错: {warn_err}")

            # 可选：尝试删除用户的刷屏消息 (比清理机器人消息更复杂，可能误删)
            # 谨慎使用，可能需要更精细的逻辑
            # if channel.permissions_for(guild.me).manage_messages:
            #    try:
            #        # 尝试删除该用户在时间窗口内的消息
            #        await channel.purge(limit=SPAM_COUNT_THRESHOLD * 2,
            #                            check=lambda m: m.author.id == author_id,
            #                            after=time_limit_user,
            #                            reason="自动清理用户刷屏消息")
            #        print(f"   - 尝试清理了用户 {author.name} 的部分刷屏消息。")
            #    except Exception as clean_err:
            #        print(f"   - 清理用户刷屏消息时出错: {clean_err}")

            return # 处理完用户刷屏后停止


# --- Event: Voice State Update ---
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    guild = member.guild
    # 从内存设置中读取母频道ID和分类ID
    master_vc_id = get_setting(guild.id, "master_channel_id")
    category_id = get_setting(guild.id, "category_id")

    # 如果未设置母频道，则直接返回
    if not master_vc_id:
        return

    master_channel = guild.get_channel(master_vc_id)
    # 校验母频道是否存在且为语音频道
    if not master_channel or not isinstance(master_channel, discord.VoiceChannel):
        print(f"⚠️ 临时语音：服务器 {guild.name} 的母频道 ID ({master_vc_id}) 无效或不是语音频道。")
        # 可以考虑在此处清除无效的设置： set_setting(guild.id, "master_channel_id", None)
        return

    category = None
    if category_id:
        category = guild.get_channel(category_id)
        # 校验分类是否存在且为分类频道
        if not category or not isinstance(category, discord.CategoryChannel):
            print(f"⚠️ 临时语音：服务器 {guild.name} 配置的分类 ID ({category_id}) 无效或不是分类频道，将尝试在母频道所在分类创建。")
            category = master_channel.category # Fallback to master channel's category
    else:
        category = master_channel.category # If no category set, use master channel's category

    # --- 用户加入母频道 -> 创建临时频道 ---
    if after.channel == master_channel:
        # 检查机器人是否有创建频道和移动成员的权限
        if not category or not category.permissions_for(guild.me).manage_channels or \
           not category.permissions_for(guild.me).move_members:
            print(f"❌ 临时语音创建失败：机器人在分类 '{category.name if category else '未知'}' 中缺少 '管理频道' 或 '移动成员' 权限。 ({member.name})")
            # 可以尝试给用户发私信提示权限问题
            try: await member.send(f"抱歉，我在服务器 **{guild.name}** 中创建临时语音频道所需的权限不足，请联系管理员检查我在分类 '{category.name if category else '默认'}' 中的权限。")
            except: pass
            return

        print(f"🔊 用户 {member.name} 加入了母频道 ({master_channel.name})，准备创建临时频道...")
        try:
            # 设置新频道的权限覆盖
            # - @everyone: 默认允许连接和说话 (可以根据需要调整)
            # - 频道创建者 (member): 给予管理频道、管理权限(覆写)、移动成员的权限
            # - 机器人自己: 确保有管理权限，以便后续操作（如删除）
            owner_overwrites = discord.PermissionOverwrite(
                manage_channels=True,    # 管理频道 (改名, 删频道等)
                manage_permissions=True, # 管理权限 (覆写别人的权限)
                move_members=True,       # 移动成员
                connect=True,            # 允许连接
                speak=True,              # 允许说话
                stream=True,             # 允许直播
                use_voice_activation=True, # 允许使用语音活动检测
                priority_speaker=True,   # 允许优先发言
                mute_members=True,       # 允许闭麦成员
                deafen_members=True,     # 允许闭麦成员
                use_embedded_activities=True # 允许使用活动
            )
            everyone_overwrites = discord.PermissionOverwrite(
                connect=True, # 默认允许其他人连接
                speak=True    # 默认允许其他人说话
                # 其他权限可以根据需要设置默认值，例如 speak=False 初始禁言
            )
            bot_overwrites = discord.PermissionOverwrite(
                manage_channels=True,
                manage_permissions=True,
                move_members=True,
                connect=True,
                view_channel=True
            )

            # 临时频道名称，可以使用用户的显示名称
            temp_channel_name = f"🎮 {member.display_name} 的频道" # 使用 display_name
            if len(temp_channel_name) > 100: # 检查名称长度
                temp_channel_name = temp_channel_name[:97] + "..."

            # 创建语音频道
            new_channel = await guild.create_voice_channel(
                name=temp_channel_name,
                category=category, # 在指定的分类下创建
                overwrites={
                    guild.default_role: everyone_overwrites, # @everyone 的权限
                    member: owner_overwrites,                 # 频道主的权限
                    guild.me: bot_overwrites                  # 机器人自己的权限
                },
                reason=f"由 {member.name} 加入母频道自动创建的临时语音频道"
            )
            print(f"   ✅ 已创建临时频道: {new_channel.name} ({new_channel.id})")

            # 尝试将用户移动到新创建的频道
            try:
                await member.move_to(new_channel, reason="移动到新创建的临时频道")
                print(f"   ✅ 已将 {member.name} 移动到频道 {new_channel.name}。")
                # 记录频道所有者和创建状态
                temp_vc_owners[new_channel.id] = member.id
                temp_vc_created.add(new_channel.id)
            except discord.Forbidden:
                 print(f"   ❌ 将 {member.name} 移动到新频道失败：机器人权限不足。")
                 # 移动失败也应该尝试删除刚创建的频道，避免留下空频道
                 try: await new_channel.delete(reason="移动用户失败，自动删除")
                 except: pass
            except discord.HTTPException as move_err:
                 print(f"   ❌ 将 {member.name} 移动到新频道时发生网络错误: {move_err}")
                 try: await new_channel.delete(reason="移动用户网络错误，自动删除")
                 except: pass
            except Exception as move_e:
                print(f"   ❌ 将 {member.name} 移动到新频道时发生未知错误: {move_e}")
                try: await new_channel.delete(reason="移动用户未知错误，自动删除")
                except: pass

        except discord.Forbidden:
            print(f"   ❌ 创建临时语音频道失败：机器人权限不足 (无法在分类 '{category.name if category else '未知'}' 中创建频道)。")
        except discord.HTTPException as create_http_err:
             print(f"   ❌ 创建临时语音频道时发生网络错误: {create_http_err}")
        except Exception as e:
            print(f"   ❌ 创建临时语音频道时发生未知错误: {e}")

    # --- 用户离开临时频道 -> 检查是否为空并删除 ---
    # before.channel 存在，并且是记录在案的临时频道
    if before.channel and before.channel.id in temp_vc_created:
        # 加一个小延迟，防止快速进出导致判断错误
        await asyncio.sleep(1) # 延迟1秒

        # 重新获取频道对象，确保它仍然存在
        channel_to_check = guild.get_channel(before.channel.id)

        if channel_to_check and isinstance(channel_to_check, discord.VoiceChannel):
            # 检查频道内是否还有非机器人的成员
            # 使用 any() 和生成器表达式提高效率
            is_empty = not any(m for m in channel_to_check.members if not m.bot)

            if is_empty:
                print(f"🔊 临时频道 {channel_to_check.name} ({channel_to_check.id}) 已空，准备删除...")
                try:
                    # 检查机器人是否有删除权限
                    if channel_to_check.permissions_for(guild.me).manage_channels:
                        await channel_to_check.delete(reason="临时语音频道为空，自动删除")
                        print(f"   ✅ 已成功删除频道 {channel_to_check.name}。")
                    else:
                         print(f"   ❌ 删除频道 {channel_to_check.name} 失败：机器人缺少 '管理频道' 权限。")

                except discord.NotFound:
                     print(f"   ℹ️ 尝试删除频道 {channel_to_check.name} 时未找到该频道 (可能已被手动删除)。")
                except discord.Forbidden:
                     print(f"   ❌ 删除频道 {channel_to_check.name} 失败：机器人权限不足。")
                except discord.HTTPException as delete_http_err:
                      print(f"   ❌ 删除频道 {channel_to_check.name} 时发生网络错误: {delete_http_err}")
                except Exception as e:
                    print(f"   ❌ 删除频道 {channel_to_check.name} 时发生未知错误: {e}")
                finally:
                    # 无论删除是否成功，都清理内存中的记录
                    if channel_to_check.id in temp_vc_owners:
                        del temp_vc_owners[channel_to_check.id]
                    if channel_to_check.id in temp_vc_created:
                        temp_vc_created.remove(channel_to_check.id)
                    print(f"   - 已清理频道 {channel_to_check.id} 的内存记录。")
            else:
                # print(f"   ℹ️ 临时频道 {channel_to_check.name} 仍有成员，不删除。")
                pass # 还有人，不删除
        else:
            # 如果频道在延迟后找不到了（可能被手动删了）
            print(f"   ℹ️ 临时频道 {before.channel.id} 在检查时已不存在或不再是语音频道。")
            # 清理内存记录
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
            "`... 公告频道 [频道]` - 设置/查看公告频道\n"
            "`... 纪录频道 [频道]` - 设置/查看日志频道\n"
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
@app_commands.checks.has_permissions(manage_roles=True) # 需要管理身份组权限
@app_commands.checks.bot_has_permissions(manage_roles=True) # 机器人也需要
async def slash_createrole(interaction: discord.Interaction, role_name: str):
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True) # 延迟响应，并设为临时

    if not guild:
        await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True)
        return

    # 检查身份组是否已存在
    existing_role = get(guild.roles, name=role_name)
    if existing_role:
        await interaction.followup.send(f"❌ 身份组 **{role_name}** 已经存在！", ephemeral=True)
        return

    # 检查名称长度
    if len(role_name) > 100:
        await interaction.followup.send("❌ 身份组名称过长（最多100个字符）。", ephemeral=True)
        return
    if not role_name.strip():
         await interaction.followup.send("❌ 身份组名称不能为空。", ephemeral=True)
         return

    try:
        # 创建身份组
        new_role = await guild.create_role(
            name=role_name,
            reason=f"由用户 {interaction.user} ({interaction.user.id}) 通过 /createrole 命令创建"
        )
        # 发送公开成功的消息
        await interaction.followup.send(f"✅ 已成功创建身份组: {new_role.mention}", ephemeral=False) # 公开消息
        print(f"[身份组操作] 用户 {interaction.user} 创建了身份组 '{new_role.name}' ({new_role.id})")
    except discord.Forbidden:
         await interaction.followup.send(f"⚙️ 创建身份组 **{role_name}** 失败：机器人权限不足。", ephemeral=True)
    except discord.HTTPException as http_err:
         await interaction.followup.send(f"⚙️ 创建身份组 **{role_name}** 时发生网络错误: {http_err}", ephemeral=True)
    except Exception as e:
        print(f"执行 /createrole 时出错: {e}")
        await interaction.followup.send(f"⚙️ 创建身份组 **{role_name}** 时发生未知错误: {e}", ephemeral=True)


@bot.tree.command(name="deleterole", description="根据精确名称删除一个现有的身份组。")
@app_commands.describe(role_name="要删除的身份组的确切名称。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_deleterole(interaction: discord.Interaction, role_name: str):
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True) # 临时响应

    if not guild:
        await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True)
        return

    # 查找身份组
    role_to_delete = get(guild.roles, name=role_name)
    if not role_to_delete:
        await interaction.followup.send(f"❓ 找不到名为 **{role_name}** 的身份组。", ephemeral=True)
        return

    # 检查是否是 @everyone
    if role_to_delete == guild.default_role:
        await interaction.followup.send("🚫 不能删除 `@everyone` 身份组。", ephemeral=True)
        return

    # 检查是否是机器人管理的身份组 (例如集成、Bot自己的身份组)
    if role_to_delete.is_integration() or role_to_delete.is_bot_managed():
         await interaction.followup.send(f"⚠️ 不能删除由集成或机器人管理的身份组 {role_to_delete.mention}。", ephemeral=True)
         return
    if role_to_delete.is_premium_subscriber():
          await interaction.followup.send(f"⚠️ 不能删除 Nitro Booster 身份组 {role_to_delete.mention}。", ephemeral=True)
          return

    # 检查机器人层级是否足够删除该身份组
    if role_to_delete >= guild.me.top_role and guild.me.id != guild.owner_id:
        await interaction.followup.send(f"🚫 无法删除身份组 {role_to_delete.mention}：我的身份组层级低于或等于它。", ephemeral=True)
        return

    try:
        deleted_role_name = role_to_delete.name # 先保存名字
        await role_to_delete.delete(
            reason=f"由用户 {interaction.user} ({interaction.user.id}) 通过 /deleterole 命令删除"
        )
        await interaction.followup.send(f"✅ 已成功删除身份组: **{deleted_role_name}**", ephemeral=False) # 公开消息
        print(f"[身份组操作] 用户 {interaction.user} 删除了身份组 '{deleted_role_name}' ({role_to_delete.id})")
    except discord.Forbidden:
        await interaction.followup.send(f"⚙️ 删除身份组 **{role_name}** 失败：机器人权限不足。", ephemeral=True)
    except discord.HTTPException as http_err:
         await interaction.followup.send(f"⚙️ 删除身份组 **{role_name}** 时发生网络错误: {http_err}", ephemeral=True)
    except Exception as e:
        print(f"执行 /deleterole 时出错: {e}")
        await interaction.followup.send(f"⚙️ 删除身份组 **{role_name}** 时发生未知错误: {e}", ephemeral=True)


@bot.tree.command(name="giverole", description="将一个现有的身份组分配给指定成员。")
@app_commands.describe(user="要给予身份组的用户。", role_name="要分配的身份组的确切名称。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_giverole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True) # 临时响应

    if not guild:
        await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True)
        return

    # 查找身份组
    role_to_give = get(guild.roles, name=role_name)
    if not role_to_give:
        await interaction.followup.send(f"❓ 找不到名为 **{role_name}** 的身份组。", ephemeral=True)
        return

     # 不能赋予 @everyone
    if role_to_give == guild.default_role:
        await interaction.followup.send("🚫 不能手动赋予 `@everyone` 身份组。", ephemeral=True)
        return

    # 检查机器人层级是否足够分配
    if role_to_give >= guild.me.top_role and guild.me.id != guild.owner_id:
        await interaction.followup.send(f"🚫 无法分配身份组 {role_to_give.mention}：我的身份组层级低于或等于它。", ephemeral=True)
        return

    # 检查执行者层级是否足够分配 (如果执行者不是服务器所有者)
    if isinstance(interaction.user, discord.Member) and interaction.user.id != guild.owner_id:
        if role_to_give >= interaction.user.top_role:
            await interaction.followup.send(f"🚫 你无法分配层级等于或高于你自己的身份组 ({role_to_give.mention})。", ephemeral=True)
            return

    # 检查用户是否已拥有该身份组
    if role_to_give in user.roles:
        await interaction.followup.send(f"ℹ️ 用户 {user.mention} 已经拥有身份组 {role_to_give.mention}。", ephemeral=True)
        return

    try:
        await user.add_roles(
            role_to_give,
            reason=f"由用户 {interaction.user} ({interaction.user.id}) 通过 /giverole 命令赋予"
        )
        await interaction.followup.send(f"✅ 已成功将身份组 {role_to_give.mention} 赋予给 {user.mention}。", ephemeral=False) # 公开消息
        print(f"[身份组操作] 用户 {interaction.user} 将身份组 '{role_to_give.name}' ({role_to_give.id}) 赋予了用户 {user.name} ({user.id})")
    except discord.Forbidden:
        await interaction.followup.send(f"⚙️ 赋予身份组 **{role_name}** 给 {user.mention} 失败：机器人权限不足。", ephemeral=True)
    except discord.HTTPException as http_err:
         await interaction.followup.send(f"⚙️ 赋予身份组 **{role_name}** 给 {user.mention} 时发生网络错误: {http_err}", ephemeral=True)
    except Exception as e:
        print(f"执行 /giverole 时出错: {e}")
        await interaction.followup.send(f"⚙️ 赋予身份组 **{role_name}** 给 {user.mention} 时发生未知错误: {e}", ephemeral=True)


@bot.tree.command(name="takerole", description="从指定成员移除一个特定的身份组。")
@app_commands.describe(user="要移除其身份组的用户。", role_name="要移除的身份组的确切名称。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_takerole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True) # 临时响应

    if not guild:
        await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True)
        return

    # 查找身份组
    role_to_take = get(guild.roles, name=role_name)
    if not role_to_take:
        await interaction.followup.send(f"❓ 找不到名为 **{role_name}** 的身份组。", ephemeral=True)
        return

    # 不能移除 @everyone
    if role_to_take == guild.default_role:
        await interaction.followup.send("🚫 不能移除 `@everyone` 身份组。", ephemeral=True)
        return

    # 检查是否是机器人管理的身份组
    if role_to_take.is_integration() or role_to_take.is_bot_managed():
         await interaction.followup.send(f"⚠️ 不能手动移除由集成或机器人管理的身份组 {role_to_take.mention}。", ephemeral=True)
         return
    if role_to_take.is_premium_subscriber():
          await interaction.followup.send(f"⚠️ 不能手动移除 Nitro Booster 身份组 {role_to_take.mention}。", ephemeral=True)
          return

    # 检查机器人层级是否足够移除
    if role_to_take >= guild.me.top_role and guild.me.id != guild.owner_id:
        await interaction.followup.send(f"🚫 无法移除身份组 {role_to_take.mention}：我的身份组层级低于或等于它。", ephemeral=True)
        return

    # 检查执行者层级是否足够移除 (如果执行者不是服务器所有者)
    if isinstance(interaction.user, discord.Member) and interaction.user.id != guild.owner_id:
         if role_to_take >= interaction.user.top_role:
             await interaction.followup.send(f"🚫 你无法移除层级等于或高于你自己的身份组 ({role_to_take.mention})。", ephemeral=True)
             return

    # 检查用户是否拥有该身份组
    if role_to_take not in user.roles:
        await interaction.followup.send(f"ℹ️ 用户 {user.mention} 并未拥有身份组 {role_to_take.mention}。", ephemeral=True)
        return

    try:
        await user.remove_roles(
            role_to_take,
            reason=f"由用户 {interaction.user} ({interaction.user.id}) 通过 /takerole 命令移除"
        )
        await interaction.followup.send(f"✅ 已成功从 {user.mention} 移除身份组 {role_to_take.mention}。", ephemeral=False) # 公开消息
        print(f"[身份组操作] 用户 {interaction.user} 从用户 {user.name} ({user.id}) 移除了身份组 '{role_to_take.name}' ({role_to_take.id})")
    except discord.Forbidden:
        await interaction.followup.send(f"⚙️ 从 {user.mention} 移除身份组 **{role_name}** 失败：机器人权限不足。", ephemeral=True)
    except discord.HTTPException as http_err:
         await interaction.followup.send(f"⚙️ 从 {user.mention} 移除身份组 **{role_name}** 时发生网络错误: {http_err}", ephemeral=True)
    except Exception as e:
        print(f"执行 /takerole 时出错: {e}")
        await interaction.followup.send(f"⚙️ 从 {user.mention} 移除身份组 **{role_name}** 时发生未知错误: {e}", ephemeral=True)


@bot.tree.command(name="createseparator", description="创建一个用于视觉分隔的特殊身份组。")
@app_commands.describe(label="要在分隔线中显示的文字标签 (例如 '成员信息', '游戏身份')。")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def slash_createseparator(interaction: discord.Interaction, label: str):
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True) # 临时响应

    if not guild:
        await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True)
        return

    # 格式化分隔线名称
    separator_name_up = f"▲─────{label}─────"
    separator_name_down = f"▽─────{label}─────" # 可以考虑也创建对应的下分隔线，或者让用户手动创建

    # 检查名称长度
    if len(separator_name_up) > 100 or len(separator_name_down) > 100:
        await interaction.followup.send(f"❌ 标签文字过长，导致分隔线名称超过100字符限制。", ephemeral=True)
        return
    if not label.strip():
         await interaction.followup.send(f"❌ 标签不能为空。", ephemeral=True)
         return

    # 检查是否已存在
    if get(guild.roles, name=separator_name_up) or get(guild.roles, name=separator_name_down):
        await interaction.followup.send(f"⚠️ 似乎已存在基于标签 **{label}** 的分隔线身份组！", ephemeral=True)
        return

    try:
        # 创建上分隔线
        new_role_up = await guild.create_role(
            name=separator_name_up,
            permissions=discord.Permissions.none(), # 无任何权限
            color=discord.Color.default(), # 默认颜色，或指定灰色 discord.Color.light_grey()
            hoist=False, # 不在成员列表中单独显示
            mentionable=False, # 不可提及
            reason=f"由 {interaction.user} 创建的分隔线 (上)"
        )
        # (可选) 创建下分隔线
        # new_role_down = await guild.create_role(name=separator_name_down, ...)

        await interaction.followup.send(
            f"✅ 已成功创建分隔线身份组: **{new_role_up.name}**\n"
            # f"和 **{new_role_down.name}**\n" # 如果创建了下分隔线
            f"**重要提示:** 请前往 **服务器设置 -> 身份组**，手动将此身份组拖动到你希望的位置！",
            ephemeral=False # 公开消息，让其他人也能看到提示
        )
        print(f"[身份组操作] 用户 {interaction.user} 创建了分隔线 '{new_role_up.name}' ({new_role_up.id})")

    except discord.Forbidden:
         await interaction.followup.send(f"⚙️ 创建分隔线失败：机器人权限不足。", ephemeral=True)
    except discord.HTTPException as http_err:
         await interaction.followup.send(f"⚙️ 创建分隔线时发生网络错误: {http_err}", ephemeral=True)
    except Exception as e:
        print(f"执行 /createseparator 时出错: {e}")
        await interaction.followup.send(f"⚙️ 创建分隔线时发生未知错误: {e}", ephemeral=True)


# --- Moderation Commands ---
@bot.tree.command(name="clear", description="清除当前频道中指定数量的消息 (1-100)。")
@app_commands.describe(amount="要删除的消息数量 (1 到 100 之间)。")
@app_commands.checks.has_permissions(manage_messages=True) # 需要管理消息权限
@app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True) # 机器人需要读和删
async def slash_clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    channel = interaction.channel # 获取当前频道
    # 检查是否是文字频道
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("❌ 此命令只能在文字频道中使用。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True) # 临时响应

    try:
        # 使用 channel.purge 来批量删除消息
        # 注意：purge 不能删除超过 14 天的消息
        deleted_messages = await channel.purge(limit=amount)
        deleted_count = len(deleted_messages)
        await interaction.followup.send(f"✅ 已成功删除 {deleted_count} 条消息。", ephemeral=True) # 仅执行者可见
        print(f"[审核操作] 用户 {interaction.user} 在频道 #{channel.name} 清除了 {deleted_count} 条消息。")

        # 可选：在公共日志频道记录清除操作
        log_embed = discord.Embed(
            title="🧹 消息清除操作",
            color=discord.Color.light_grey(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        log_embed.add_field(name="执行者", value=interaction.user.mention, inline=True)
        log_embed.add_field(name="频道", value=channel.mention, inline=True)
        log_embed.add_field(name="清除数量", value=str(deleted_count), inline=True)
        log_embed.set_footer(text=f"执行者 ID: {interaction.user.id}")
        await send_to_public_log(interaction.guild, log_embed, log_type="Clear Messages")

    except discord.Forbidden:
        await interaction.followup.send(f"⚙️ 清除消息失败：机器人缺少在频道 {channel.mention} 中删除消息的权限。", ephemeral=True)
    except discord.HTTPException as http_err:
         await interaction.followup.send(f"⚙️ 清除消息时发生网络错误: {http_err}", ephemeral=True)
    except Exception as e:
        print(f"执行 /clear 时出错: {e}")
        await interaction.followup.send(f"⚙️ 清除消息时发生未知错误: {e}", ephemeral=True)


@bot.tree.command(name="warn", description="手动向用户发出一次警告 (累计达到阈值会被踢出)。")
@app_commands.describe(user="要警告的用户。", reason="警告的原因 (可选)。")
@app_commands.checks.has_permissions(kick_members=True) # 通常警告权限和踢出权限绑定
async def slash_warn(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    guild = interaction.guild
    author = interaction.user # 指令发起者
    await interaction.response.defer(ephemeral=False) # 默认公开响应，因为涉及警告

    if not guild:
        await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True); return
    if user.bot:
        await interaction.followup.send("❌ 不能警告机器人。", ephemeral=True); return
    if user == author:
        await interaction.followup.send("❌ 你不能警告自己。", ephemeral=True); return

    # 检查层级 (执行者不能警告同级或更高级别的成员，除非是服主)
    if isinstance(author, discord.Member) and author.id != guild.owner_id:
        if user.top_role >= author.top_role:
             await interaction.followup.send(f"🚫 你无法警告层级等于或高于你的成员 ({user.mention})。", ephemeral=True)
             return

    # 更新用户警告次数 (内存存储)
    user_id = user.id
    user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
    warning_count = user_warnings[user_id]

    print(f"[审核操作] 用户 {author} 手动警告了用户 {user}。原因: {reason}。新警告次数: {warning_count}/{KICK_THRESHOLD}")

    # 创建警告 Embed
    embed = discord.Embed(color=discord.Color.orange()) # 橙色表示警告
    embed.set_author(name=f"由 {author.display_name} 发出警告", icon_url=author.display_avatar.url)
    embed.add_field(name="被警告用户", value=f"{user.mention} ({user.id})", inline=False)
    embed.add_field(name="警告原因", value=reason, inline=False)
    embed.add_field(name="当前警告次数", value=f"**{warning_count}** / {KICK_THRESHOLD}", inline=False)
    embed.timestamp = discord.utils.utcnow()

    kick_performed = False # 标记是否执行了踢出

    # 检查是否达到踢出阈值
    if warning_count >= KICK_THRESHOLD:
        embed.title = "🚨 警告已达上限 - 用户已被踢出 🚨"
        embed.color = discord.Color.red() # 红色表示严重处理
        embed.add_field(name="处理措施", value="已自动踢出服务器", inline=False)
        print(f"   - 用户 {user.name} 因手动警告达到踢出阈值。")

        bot_member = guild.me
        # 检查机器人是否有权限踢出该用户
        can_kick = bot_member.guild_permissions.kick_members and \
                   (bot_member.top_role > user.top_role or bot_member == guild.owner)

        if can_kick:
            kick_reason_warn = f"自动踢出：因累计达到 {KICK_THRESHOLD} 次警告 (最后一次由 {author.display_name} 手动发出，原因：{reason})。"
            try:
                # 尝试私信通知
                try:
                    await user.send(f"由于在服务器 **{guild.name}** 中累计达到 {KICK_THRESHOLD} 次警告（最后由 {author.display_name} 发出警告，原因：{reason}），你已被踢出。")
                except Exception as dm_err:
                    print(f"   - 无法向用户 {user.name} 发送踢出私信 (手动警告): {dm_err}")

                # 执行踢出
                await user.kick(reason=kick_reason_warn)
                print(f"   - 已成功踢出用户 {user.name} (手动警告达到上限)。")
                kick_performed = True
                user_warnings[user_id] = 0 # 踢出后重置警告次数
                embed.add_field(name="踢出状态", value="✅ 成功", inline=False)
            except discord.Forbidden:
                 print(f"   - 踢出用户 {user.name} 失败：机器人权限不足。")
                 embed.add_field(name="踢出状态", value="❌ 失败 (权限不足)", inline=False)
            except discord.HTTPException as kick_http:
                 print(f"   - 踢出用户 {user.name} 时发生网络错误: {kick_http}")
                 embed.add_field(name="踢出状态", value=f"❌ 失败 (网络错误 {kick_http.status})", inline=False)
            except Exception as kick_err:
                print(f"   - 踢出用户 {user.name} 时发生未知错误: {kick_err}")
                embed.add_field(name="踢出状态", value=f"❌ 失败 ({kick_err})", inline=False)
        else:
            print(f"   - 无法踢出用户 {user.name}：机器人权限不足或层级不够。")
            embed.add_field(name="踢出状态", value="❌ 失败 (权限/层级不足)", inline=False)
            embed.add_field(name="提醒", value=f"<@&{MOD_ALERT_ROLE_IDS[0] if MOD_ALERT_ROLE_IDS else '管理员'}> 请手动处理！", inline=False) # 提醒管理员手动处理

    else: # 未达到踢出阈值
        embed.title = "⚠️ 手动警告已发出 ⚠️"
        embed.add_field(name="后续处理", value=f"该用户再收到 {KICK_THRESHOLD - warning_count} 次警告将被自动踢出。", inline=False)

    # 发送 Embed 到当前频道 (公开) 和公共日志频道
    await interaction.followup.send(embed=embed) # 在当前频道发送
    await send_to_public_log(guild, embed, log_type="Manual Warn") # 发送到日志频道


@bot.tree.command(name="unwarn", description="移除用户的一次警告记录。")
@app_commands.describe(user="要移除其警告的用户。", reason="移除警告的原因 (可选)。")
@app_commands.checks.has_permissions(kick_members=True) # 通常和警告权限一致
async def slash_unwarn(interaction: discord.Interaction, user: discord.Member, reason: str = "管理员酌情处理"):
    guild = interaction.guild
    author = interaction.user
    await interaction.response.defer(ephemeral=True) # 默认临时响应

    if not guild:
        await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True); return
    if user.bot:
        await interaction.followup.send("❌ 机器人没有警告记录。", ephemeral=True); return

    user_id = user.id
    current_warnings = user_warnings.get(user_id, 0)

    if current_warnings <= 0:
        await interaction.followup.send(f"ℹ️ 用户 {user.mention} 当前没有警告记录可移除。", ephemeral=True)
        return

    # 减少警告次数
    user_warnings[user_id] = current_warnings - 1
    new_warning_count = user_warnings[user_id]

    print(f"[审核操作] 用户 {author} 移除了用户 {user} 的一次警告。原因: {reason}。新警告次数: {new_warning_count}/{KICK_THRESHOLD}")

    # 创建移除警告的 Embed
    embed = discord.Embed(
        title="✅ 警告已移除 ✅",
        color=discord.Color.green(), # 绿色表示正面操作
        timestamp=discord.utils.utcnow()
    )
    embed.set_author(name=f"由 {author.display_name} 操作", icon_url=author.display_avatar.url)
    embed.add_field(name="用户", value=f"{user.mention} ({user.id})", inline=False)
    embed.add_field(name="移除原因", value=reason, inline=False)
    embed.add_field(name="新的警告次数", value=f"**{new_warning_count}** / {KICK_THRESHOLD}", inline=False)

    # 发送到公共日志频道
    await send_to_public_log(guild, embed, log_type="Manual Unwarn")

    # 给执行者发送确认信息
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
@app_commands.checks.has_permissions(manage_guild=True) # 需要管理服务器权限才能发公告
@app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True) # 机器人需要发送和嵌入权限
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
    await interaction.response.defer(ephemeral=True) # 临时响应，告知执行者结果

    if not guild:
         await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True); return

    # --- 参数验证和处理 ---
    embed_color = discord.Color.blue() # 默认颜色
    valid_image = None
    validation_warnings = [] # 收集验证问题

    # 处理颜色
    if color:
        try:
            # 去掉可能的 '#' 或 '0x' 前缀
            clr_hex = color.lstrip('#').lstrip('0x')
            embed_color = discord.Color(int(clr_hex, 16))
        except ValueError:
            validation_warnings.append(f"⚠️ 无效的颜色代码 '{color}'。已使用默认蓝色。")
            embed_color = discord.Color.blue() # 出错时强制使用默认

    # 处理图片 URL
    if image_url:
        # 简单检查是否是 http/https 链接
        if image_url.startswith(('http://', 'https://')):
            # 尝试访问 URL 头部信息，简单验证链接是否可能有效且是图片
            # 注意：这并不能完全保证图片能正常显示在 Discord 中
            try:
                head_resp = requests.head(image_url, timeout=5, allow_redirects=True)
                if head_resp.status_code == 200 :
                     content_type = head_resp.headers.get('Content-Type', '').lower()
                     if 'image' in content_type:
                         valid_image = image_url
                     else:
                          validation_warnings.append(f"⚠️ 图片 URL '{image_url}' 返回的不是图片类型 ('{content_type}')。图片可能无法正常显示。")
                          valid_image = image_url # 仍然尝试使用，但给出警告
                else:
                     validation_warnings.append(f"⚠️ 图片 URL '{image_url}' 无法访问 (状态码: {head_resp.status_code})。图片将不会被添加。")
            except requests.exceptions.RequestException as req_err:
                 validation_warnings.append(f"⚠️ 验证图片 URL '{image_url}' 时出错: {req_err}。图片将不会被添加。")
        else:
            validation_warnings.append(f"⚠️ 无效的图片 URL 格式 '{image_url}' (必须以 http:// 或 https:// 开头)。图片将不会被添加。")

    # 如果有验证警告，先通知执行者
    if validation_warnings:
        await interaction.followup.send("\n".join(validation_warnings), ephemeral=True)
        # 这里不 return，让公告继续发送，但用户已知晓问题

    # 创建 Embed 对象
    embed = discord.Embed(
        title=f"**{title}**", # 标题加粗
        description=message.replace('\\n', '\n'), # 处理换行符
        color=embed_color,
        timestamp=discord.utils.utcnow() # 添加时间戳
    )
    # 设置页脚
    embed.set_footer(
        text=f"由 {author.display_name} 发布 | {guild.name}",
        icon_url=guild.icon.url if guild.icon else bot.user.display_avatar.url # 优先用服务器图标
    )
    # 如果有有效的图片 URL，设置图片
    if valid_image:
        embed.set_image(url=valid_image)

    # 准备提及内容
    ping_content = None
    if ping_role:
        # 检查身份组是否可以被提及
        if ping_role.mentionable or author.guild_permissions.mention_everyone:
            ping_content = ping_role.mention
        else:
            # 如果身份组不可提及，且用户没有@everyone权限，则只发送文本名称，并通知执行者
             await interaction.followup.send(f"⚠️ 身份组 {ping_role.name} 不可提及，且你没有 '提及 @everyone...' 权限。公告中将不会实际提及该身份组。", ephemeral=True)
             ping_content = f"(提及 **{ping_role.name}**)" # 在文本中说明


    # 发送公告
    try:
        # 再次检查机器人是否有在目标频道发送消息和嵌入链接的权限
        target_perms = channel.permissions_for(guild.me)
        if not target_perms.send_messages or not target_perms.embed_links:
            await interaction.followup.send(f"❌ 发送失败：机器人缺少在频道 {channel.mention} 发送消息或嵌入链接的权限。", ephemeral=True)
            return

        # 发送消息
        await channel.send(content=ping_content, embed=embed)

        # 向执行者发送最终确认
        success_message = f"✅ 公告已成功发送到频道 {channel.mention}！"
        # 如果之前有验证警告，可以附加到成功消息后
        # if validation_warnings:
        #    success_message += "\n" + "\n".join(validation_warnings)
        await interaction.followup.send(success_message, ephemeral=True)
        print(f"[公告] 用户 {author} 在频道 #{channel.name} 发布了公告: '{title}'")

    except discord.Forbidden:
         await interaction.followup.send(f"❌ 发送失败：机器人缺少在频道 {channel.mention} 发送消息或嵌入链接的权限。", ephemeral=True)
    except discord.HTTPException as http_err:
         await interaction.followup.send(f"❌ 发送公告时发生网络错误: {http_err}", ephemeral=True)
    except Exception as e:
        print(f"执行 /announce 时出错: {e}")
        await interaction.followup.send(f"❌ 发送公告时发生未知错误: {e}", ephemeral=True)


# --- Management Command Group Definitions ---
# 创建一个指令组 '/管理'
manage_group = app_commands.Group(name="管理", description="服务器高级管理相关指令 (需要相应权限)")

@manage_group.command(name="公告频道", description="设置或查看用于发布服务器公告的默认频道。")
@app_commands.describe(channel="(可选) 选择一个新的频道作为公告频道。留空则查看当前设置。")
@app_commands.checks.has_permissions(administrator=True) # 通常设为管理员权限
async def manage_announce_channel(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    guild_id = interaction.guild_id
    await interaction.response.defer(ephemeral=True)

    if channel:
        # 检查机器人是否有在该频道发送消息的权限
        perms = channel.permissions_for(interaction.guild.me)
        if not perms.send_messages or not perms.embed_links:
             await interaction.followup.send(f"⚠️ 已尝试设置 {channel.mention}，但机器人缺少在该频道发送消息或嵌入链接的权限！请先授予权限。", ephemeral=True)
             # 仍然保存设置，但给出警告
        set_setting(guild_id, "announce_channel_id", channel.id) # 使用内存存储
        await interaction.followup.send(f"✅ 服务器公告频道已更新为 {channel.mention}。", ephemeral=True)
        print(f"[设置] 服务器 {guild_id} 公告频道设置为 {channel.id}")
    else:
        # 查看当前设置
        ch_id = get_setting(guild_id, "announce_channel_id")
        current_ch = interaction.guild.get_channel(ch_id) if ch_id else None
        if current_ch:
            await interaction.followup.send(f"ℹ️ 当前服务器公告频道为: {current_ch.mention}", ephemeral=True)
        else:
            await interaction.followup.send("ℹ️ 当前未设置服务器公告频道。", ephemeral=True)


@manage_group.command(name="纪录频道", description="设置或查看用于记录机器人操作和事件的日志频道。")
@app_commands.describe(channel="(可选) 选择一个新的频道作为日志频道。留空则查看当前设置。")
@app_commands.checks.has_permissions(administrator=True)
async def manage_log_channel(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
     guild_id = interaction.guild_id
     await interaction.response.defer(ephemeral=True)

     if channel:
         # 尝试在设置前发送一条消息，以验证权限
         try:
             test_msg = await channel.send("⚙️ 正在设置此频道为机器人日志频道...")
             # 如果发送成功，再保存设置
             set_setting(guild_id, "log_channel_id", channel.id) # 使用内存存储
             await test_msg.edit(content=f"✅ 此频道已成功设置为机器人日志频道。") # 编辑消息确认
             await interaction.followup.send(f"✅ 机器人日志频道已成功设置为 {channel.mention}。", ephemeral=True)
             print(f"[设置] 服务器 {guild_id} 日志频道设置为 {channel.id}")
         except discord.Forbidden:
             await interaction.followup.send(f"❌ 设置失败：机器人缺少在频道 {channel.mention} 发送消息的权限！请先授予权限。", ephemeral=True)
         except Exception as e:
             await interaction.followup.send(f"❌ 设置日志频道时发生错误: {e}", ephemeral=True)
     else:
         # 查看当前设置
         ch_id = get_setting(guild_id, "log_channel_id")
         current_ch = interaction.guild.get_channel(ch_id) if ch_id else None
         if current_ch:
             await interaction.followup.send(f"ℹ️ 当前机器人日志频道为: {current_ch.mention}", ephemeral=True)
         else:
             await interaction.followup.send("ℹ️ 当前未设置机器人日志频道。", ephemeral=True)


@manage_group.command(name="ai豁免-添加用户", description="将用户添加到 AI 内容检测的豁免列表 (管理员)。")
@app_commands.describe(user="要添加到豁免列表的用户。")
@app_commands.checks.has_permissions(administrator=True) # 仅管理员可操作
async def manage_ai_exempt_user_add(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)
    if user.bot:
        await interaction.followup.send("❌ 不能将机器人添加到豁免列表。", ephemeral=True); return

    user_id = user.id
    if user_id in exempt_users_from_ai_check:
        await interaction.followup.send(f"ℹ️ 用户 {user.mention} 已在 AI 检测豁免列表中。", ephemeral=True)
    else:
        exempt_users_from_ai_check.add(user_id)
        # !!! 在实际应用中，这里应该将 user_id 保存到数据库或持久化存储 !!!
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
        # !!! 在实际应用中，这里应该从数据库或持久化存储中移除 user_id !!!
        await interaction.followup.send(f"✅ 已将用户 {user.mention} 从 AI 内容检测豁免列表中移除。", ephemeral=True)
        print(f"[AI豁免] 管理员 {interaction.user} 从豁免列表移除了用户 {user.name}({user_id})。")
    else:
        await interaction.followup.send(f"ℹ️ 用户 {user.mention} 不在 AI 检测豁免列表中。", ephemeral=True)


@manage_group.command(name="ai豁免-添加频道", description="将频道添加到 AI 内容检测的豁免列表 (管理员)。")
@app_commands.describe(channel="要添加到豁免列表的文字频道。")
@app_commands.checks.has_permissions(administrator=True)
async def manage_ai_exempt_channel_add(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    channel_id = channel.id
    if channel_id in exempt_channels_from_ai_check:
        await interaction.followup.send(f"ℹ️ 频道 {channel.mention} 已在 AI 检测豁免列表中。", ephemeral=True)
    else:
        exempt_channels_from_ai_check.add(channel_id)
        # !!! 在实际应用中，这里应该将 channel_id 保存到数据库或持久化存储 !!!
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
        # !!! 在实际应用中，这里应该从数据库或持久化存储中移除 channel_id !!!
        await interaction.followup.send(f"✅ 已将频道 {channel.mention} 从 AI 内容检测豁免列表中移除。", ephemeral=True)
        print(f"[AI豁免] 管理员 {interaction.user} 从豁免列表移除了频道 #{channel.name}({channel_id})。")
    else:
        await interaction.followup.send(f"ℹ️ 频道 {channel.mention} 不在 AI 检测豁免列表中。", ephemeral=True)


@manage_group.command(name="ai豁免-查看列表", description="查看当前 AI 内容检测的豁免用户和频道列表 (管理员)。")
@app_commands.checks.has_permissions(administrator=True)
async def manage_ai_exempt_list(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    if not guild: await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True); return

    # 获取豁免用户和频道的提及字符串
    exempt_user_mentions = [f"<@{uid}> ({guild.get_member(uid).name if guild.get_member(uid) else '未知用户'})" for uid in exempt_users_from_ai_check]
    exempt_channel_mentions = [f"<#{cid}>" for cid in exempt_channels_from_ai_check]

    embed = discord.Embed(
        title="⚙️ AI 内容检测豁免列表 (当前内存)",
        color=discord.Color.light_grey(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    # 使用 code block 防止提及
    user_list_str = "\n".join(exempt_user_mentions) if exempt_user_mentions else "无"
    channel_list_str = "\n".join(exempt_channel_mentions) if exempt_channel_mentions else "无"

    embed.add_field(name="豁免用户", value=f"```{user_list_str[:1000]}```" if user_list_str != "无" else "无", inline=False) # 限制长度
    embed.add_field(name="豁免频道", value=f"{channel_list_str[:1000]}" if channel_list_str != "无" else "无", inline=False) # 限制长度
    embed.set_footer(text="注意：此列表存储在内存中，机器人重启后会清空（除非使用数据库）。")

    await interaction.followup.send(embed=embed, ephemeral=True)


@manage_group.command(name="删讯息", description="删除指定用户在当前频道的最近消息 (需要管理消息权限)。")
@app_commands.describe(
    user="要删除其消息的目标用户。",
    amount="要检查并删除的最近消息数量 (1 到 100)。"
)
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
async def manage_delete_user_messages(interaction: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 1, 100]):
    await interaction.response.defer(ephemeral=True) # 临时响应
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.followup.send("❌ 此命令只能在文字频道中使用。", ephemeral=True)
        return

    deleted_count = 0
    try:
        # 使用 channel.purge 的 check 参数来指定只删除特定用户的消息
        deleted_messages = await channel.purge(
            limit=amount,
            check=lambda m: m.author == user, # 只删除目标用户的消息
            reason=f"由 {interaction.user} 执行 /管理 删讯息 操作"
        )
        deleted_count = len(deleted_messages)
        await interaction.followup.send(f"✅ 成功在频道 {channel.mention} 中删除了用户 {user.mention} 的 {deleted_count} 条消息。", ephemeral=True)
        print(f"[审核操作] 用户 {interaction.user} 在频道 #{channel.name} 删除了用户 {user.name} 的 {deleted_count} 条消息。")

        # 可选：记录到日志
        log_embed = discord.Embed(
            title="🗑️ 用户消息删除",
            color=discord.Color.light_grey(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        log_embed.add_field(name="执行者", value=interaction.user.mention, inline=True)
        log_embed.add_field(name="目标用户", value=user.mention, inline=True)
        log_embed.add_field(name="频道", value=channel.mention, inline=True)
        log_embed.add_field(name="删除数量", value=str(deleted_count), inline=True)
        log_embed.set_footer(text=f"执行者 ID: {interaction.user.id} | 目标用户 ID: {user.id}")
        await send_to_public_log(interaction.guild, log_embed, log_type="Delete User Messages")

    except discord.Forbidden:
         await interaction.followup.send(f"⚙️ 删除消息失败：机器人缺少在频道 {channel.mention} 中删除消息的权限。", ephemeral=True)
    except discord.HTTPException as http_err:
         await interaction.followup.send(f"⚙️ 删除消息时发生网络错误: {http_err}", ephemeral=True)
    except Exception as e:
        print(f"执行 /管理 删讯息 时出错: {e}")
        await interaction.followup.send(f"⚙️ 删除消息时发生未知错误: {e}", ephemeral=True)


@manage_group.command(name="频道名", description="修改当前文字频道的名称 (需要管理频道权限)。")
@app_commands.describe(new_name="频道的新名称。")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.checks.bot_has_permissions(manage_channels=True)
async def manage_channel_name(interaction: discord.Interaction, new_name: str):
    channel = interaction.channel # 获取当前频道
    if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel)): # 适用于文本、语音、分类
        await interaction.response.send_message("❌ 此命令只能在文字频道、语音频道或分类频道中使用。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False) # 公开响应，因为频道名改变是可见的
    old_name = channel.name

    if len(new_name) > 100 or len(new_name) < 1:
         await interaction.followup.send("❌ 频道名称长度必须在 1 到 100 个字符之间。", ephemeral=True)
         return
    if not new_name.strip():
        await interaction.followup.send("❌ 频道名称不能为空。", ephemeral=True)
        return

    try:
        await channel.edit(
            name=new_name,
            reason=f"由用户 {interaction.user} 通过 /管理 频道名 命令修改"
        )
        await interaction.followup.send(f"✅ 频道名称已从 `{old_name}` 修改为 `{new_name}`。", ephemeral=False)
        print(f"[管理操作] 用户 {interaction.user} 将频道 #{old_name} ({channel.id}) 重命名为 '{new_name}'。")
    except discord.Forbidden:
         await interaction.followup.send(f"⚙️ 修改频道名称失败：机器人缺少管理频道 {channel.mention} 的权限。", ephemeral=True)
    except discord.HTTPException as http_err:
         await interaction.followup.send(f"⚙️ 修改频道名称时发生网络错误: {http_err}", ephemeral=True)
    except Exception as e:
        print(f"执行 /管理 频道名 时出错: {e}")
        await interaction.followup.send(f"⚙️ 修改频道名称时发生未知错误: {e}", ephemeral=True)


@manage_group.command(name="禁言", description="暂时或永久禁言成员 (需要 '超时成员' 权限)。")
@app_commands.describe(
    user="要禁言的目标用户。",
    duration_minutes="禁言的分钟数 (输入 0 表示永久禁言，即最长28天)。",
    reason="(可选) 禁言的原因。"
)
@app_commands.checks.has_permissions(moderate_members=True) # 超时权限
@app_commands.checks.bot_has_permissions(moderate_members=True)
async def manage_mute(interaction: discord.Interaction, user: discord.Member, duration_minutes: int, reason: str = "未指定原因"):
    await interaction.response.defer(ephemeral=False) # 禁言操作通常公开
    guild = interaction.guild
    author = interaction.user

    # --- 基础检查 ---
    if user == author:
        await interaction.followup.send("❌ 你不能禁言自己。", ephemeral=True); return
    if user.bot:
        await interaction.followup.send("❌ 不能禁言机器人。", ephemeral=True); return
    if user.id == guild.owner_id:
         await interaction.followup.send("❌ 不能禁言服务器所有者。", ephemeral=True); return
    # 检查是否已经在禁言中
    if user.is_timed_out():
         await interaction.followup.send(f"ℹ️ 用户 {user.mention} 当前已被禁言。", ephemeral=True); return
    # 检查层级
    if isinstance(author, discord.Member) and author.id != guild.owner_id:
        if user.top_role >= author.top_role:
            await interaction.followup.send(f"🚫 你无法禁言层级等于或高于你的成员 ({user.mention})。", ephemeral=True); return
    # 检查机器人层级
    if user.top_role >= guild.me.top_role and guild.me.id != guild.owner_id:
         await interaction.followup.send(f"🚫 机器人无法禁言层级等于或高于自身的成员 ({user.mention})。", ephemeral=True); return


    # --- 计算禁言时长 ---
    if duration_minutes < 0:
        await interaction.followup.send("❌ 禁言时长不能为负数。", ephemeral=True); return

    max_duration = datetime.timedelta(days=28) # Discord API 限制
    timeout_duration: Optional[datetime.timedelta] = None
    duration_text = ""

    if duration_minutes == 0:
        # "永久" 禁言，实际为 API 上限 28 天
        timeout_duration = max_duration
        duration_text = "永久 (最长28天)"
    else:
        requested_duration = datetime.timedelta(minutes=duration_minutes)
        if requested_duration > max_duration:
            timeout_duration = max_duration
            duration_text = f"{duration_minutes} 分钟 (已限制为最长28天)"
        else:
            timeout_duration = requested_duration
            duration_text = f"{duration_minutes} 分钟"

    # --- 执行禁言 ---
    try:
        await user.timeout(timeout_duration, reason=f"由 {author.display_name} ({author.id}) 禁言，原因: {reason}")

        # 发送确认消息
        timeout_until = discord.utils.utcnow() + timeout_duration if timeout_duration else None
        timeout_timestamp = f" (<t:{int(timeout_until.timestamp())}:R> 解除)" if timeout_until else ""

        await interaction.followup.send(f"✅ 用户 {user.mention} 已被成功禁言 **{duration_text}**{timeout_timestamp}。\n原因: {reason}", ephemeral=False)
        print(f"[审核操作] 用户 {author} 禁言了用户 {user} {duration_text}。原因: {reason}")

        # 可选：记录到日志
        log_embed = discord.Embed(
            title="🔇 用户禁言",
            color=discord.Color.dark_orange(),
            timestamp=discord.utils.utcnow()
        )
        log_embed.add_field(name="执行者", value=author.mention, inline=True)
        log_embed.add_field(name="被禁言用户", value=user.mention, inline=True)
        log_embed.add_field(name="持续时间", value=duration_text, inline=False)
        if timeout_until:
             log_embed.add_field(name="预计解除时间", value=f"<t:{int(timeout_until.timestamp())}:F>", inline=False)
        log_embed.add_field(name="原因", value=reason, inline=False)
        log_embed.set_footer(text=f"执行者 ID: {author.id} | 用户 ID: {user.id}")
        await send_to_public_log(guild, log_embed, log_type="Mute Member")

    except discord.Forbidden:
         await interaction.followup.send(f"⚙️ 禁言用户 {user.mention} 失败：机器人权限不足或层级不够。", ephemeral=True)
    except discord.HTTPException as http_err:
         await interaction.followup.send(f"⚙️ 禁言用户 {user.mention} 时发生网络错误: {http_err}", ephemeral=True)
    except Exception as e:
        print(f"执行 /管理 禁言 时出错: {e}")
        await interaction.followup.send(f"⚙️ 禁言用户 {user.mention} 时发生未知错误: {e}", ephemeral=True)


@manage_group.command(name="踢出", description="将成员踢出服务器 (需要 '踢出成员' 权限)。")
@app_commands.describe(user="要踢出的目标用户。", reason="(可选) 踢出的原因。")
@app_commands.checks.has_permissions(kick_members=True)
@app_commands.checks.bot_has_permissions(kick_members=True)
async def manage_kick(interaction: discord.Interaction, user: discord.Member, reason: str = "未指定原因"):
    await interaction.response.defer(ephemeral=False) # 踢出是重要操作，公开响应
    guild = interaction.guild
    author = interaction.user

    # --- 基础检查 ---
    if user == author:
        await interaction.followup.send("❌ 你不能踢出自己。", ephemeral=True); return
    if user.id == guild.owner_id:
         await interaction.followup.send("❌ 不能踢出服务器所有者。", ephemeral=True); return
    if user.id == bot.user.id:
         await interaction.followup.send("❌ 不能踢出机器人自己。", ephemeral=True); return
    # 检查层级
    if isinstance(author, discord.Member) and author.id != guild.owner_id:
        if user.top_role >= author.top_role:
            await interaction.followup.send(f"🚫 你无法踢出层级等于或高于你的成员 ({user.mention})。", ephemeral=True); return
    # 检查机器人层级
    if user.top_role >= guild.me.top_role and guild.me.id != guild.owner_id:
         await interaction.followup.send(f"🚫 机器人无法踢出层级等于或高于自身的成员 ({user.mention})。", ephemeral=True); return

    # --- 执行踢出 ---
    kick_reason_full = f"由 {author.display_name} ({author.id}) 踢出，原因: {reason}"
    try:
        # 尝试私信通知用户
        try:
            dm_message = f"你已被管理员 **{author.display_name}** 从服务器 **{guild.name}** 中踢出。\n原因: {reason}"
            await user.send(dm_message)
            print(f"   - 已向用户 {user.name} 发送踢出通知私信。")
        except discord.Forbidden:
            print(f"   - 无法向用户 {user.name} 发送踢出私信 (权限不足或用户设置)。")
        except Exception as dm_err:
            print(f"   - 发送踢出私信给 {user.name} 时发生错误: {dm_err}")

        # 执行踢出
        await user.kick(reason=kick_reason_full)

        # 发送确认消息
        await interaction.followup.send(f"👢 用户 {user.mention} (`{user}`) 已被成功踢出服务器。\n原因: {reason}", ephemeral=False)
        print(f"[审核操作] 用户 {author} 踢出了用户 {user}。原因: {reason}")

        # 可选：记录到日志
        log_embed = discord.Embed(
            title="👢 用户踢出",
            color=discord.Color.dark_orange(),
            timestamp=discord.utils.utcnow()
        )
        log_embed.add_field(name="执行者", value=author.mention, inline=True)
        log_embed.add_field(name="被踢出用户", value=f"{user.mention} (`{user}`)", inline=True)
        log_embed.add_field(name="原因", value=reason, inline=False)
        log_embed.set_footer(text=f"执行者 ID: {author.id} | 用户 ID: {user.id}")
        await send_to_public_log(guild, log_embed, log_type="Kick Member")

    except discord.Forbidden:
         await interaction.followup.send(f"⚙️ 踢出用户 {user.mention} 失败：机器人权限不足或层级不够。", ephemeral=True)
    except discord.HTTPException as http_err:
         await interaction.followup.send(f"⚙️ 踢出用户 {user.mention} 时发生网络错误: {http_err}", ephemeral=True)
    except Exception as e:
        print(f"执行 /管理 踢出 时出错: {e}")
        await interaction.followup.send(f"⚙️ 踢出用户 {user.mention} 时发生未知错误: {e}", ephemeral=True)


@manage_group.command(name="封禁", description="永久封禁成员 (需要 '封禁成员' 权限)。")
@app_commands.describe(
    user_id="要封禁的用户 ID (使用 ID 防止误操作)。",
    delete_message_days="删除该用户过去多少天的消息 (0-7，可选，默认为0)。",
    reason="(可选) 封禁的原因。"
)
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.checks.bot_has_permissions(ban_members=True)
async def manage_ban(interaction: discord.Interaction, user_id: str, delete_message_days: app_commands.Range[int, 0, 7] = 0, reason: str = "未指定原因"):
    await interaction.response.defer(ephemeral=False) # 封禁是重要操作，公开响应
    guild = interaction.guild
    author = interaction.user

    # --- 验证 User ID ---
    try:
        target_user_id = int(user_id)
    except ValueError:
        await interaction.followup.send("❌ 无效的用户 ID 格式。请输入纯数字的用户 ID。", ephemeral=True); return

    # --- 基础检查 ---
    if target_user_id == author.id:
        await interaction.followup.send("❌ 你不能封禁自己。", ephemeral=True); return
    if target_user_id == guild.owner_id:
         await interaction.followup.send("❌ 不能封禁服务器所有者。", ephemeral=True); return
    if target_user_id == bot.user.id:
         await interaction.followup.send("❌ 不能封禁机器人自己。", ephemeral=True); return

    # 检查用户是否已被封禁
    try:
        await guild.fetch_ban(discord.Object(id=target_user_id))
        # 如果上面没有抛出 NotFound 异常，说明用户已被封禁
        banned_user = await bot.fetch_user(target_user_id) # 尝试获取用户信息以显示名称
        await interaction.followup.send(f"ℹ️ 用户 **{banned_user.name if banned_user else '未知用户'}** (ID: {target_user_id}) 已经被封禁了。", ephemeral=True)
        return
    except discord.NotFound:
        # 用户未被封禁，可以继续
        pass
    except Exception as fetch_err:
         print(f"检查用户 {target_user_id} 封禁状态时出错: {fetch_err}") # 后台记录错误，但继续尝试封禁

    # 尝试获取成员对象以检查层级（如果用户在服务器内）
    target_member = guild.get_member(target_user_id)
    if target_member:
        # 检查执行者层级
        if isinstance(author, discord.Member) and author.id != guild.owner_id:
            if target_member.top_role >= author.top_role:
                await interaction.followup.send(f"🚫 你无法封禁层级等于或高于你的成员 ({target_member.mention})。", ephemeral=True); return
        # 检查机器人层级
        if target_member.top_role >= guild.me.top_role and guild.me.id != guild.owner_id:
             await interaction.followup.send(f"🚫 机器人无法封禁层级等于或高于自身的成员 ({target_member.mention})。", ephemeral=True); return

    # --- 执行封禁 ---
    ban_reason_full = f"由 {author.display_name} ({author.id}) 封禁，原因: {reason}"
    try:
        # Discord 需要一个 User 对象来封禁，即使该用户不在服务器内
        user_to_ban = discord.Object(id=target_user_id) # 创建一个只有 ID 的对象
        await guild.ban(user_to_ban, reason=ban_reason_full, delete_message_days=delete_message_days)

        # 尝试获取用户信息以显示名称
        banned_user_info = await bot.fetch_user(target_user_id)
        user_display = f"{banned_user_info.name}#{banned_user_info.discriminator}" if banned_user_info else "未知用户"

        # 发送确认消息
        delete_days_text = f"并删除了其过去 {delete_message_days} 天的消息" if delete_message_days > 0 else ""
        await interaction.followup.send(f"🚫 用户 **{user_display}** (ID: {target_user_id}) 已被成功永久封禁{delete_days_text}。\n原因: {reason}", ephemeral=False)
        print(f"[审核操作] 用户 {author} 封禁了用户 ID {target_user_id} ({user_display})。原因: {reason}")

        # 可选：记录到日志
        log_embed = discord.Embed(
            title="🚫 用户封禁",
            color=discord.Color.dark_red(),
            timestamp=discord.utils.utcnow()
        )
        log_embed.add_field(name="执行者", value=author.mention, inline=True)
        log_embed.add_field(name="被封禁用户", value=f"{user_display} ({target_user_id})", inline=True)
        log_embed.add_field(name="原因", value=reason, inline=False)
        if delete_message_days > 0:
             log_embed.add_field(name="消息删除", value=f"删除了过去 {delete_message_days} 天的消息", inline=True)
        log_embed.set_footer(text=f"执行者 ID: {author.id} | 用户 ID: {target_user_id}")
        await send_to_public_log(guild, log_embed, log_type="Ban Member")

    except discord.Forbidden:
         await interaction.followup.send(f"⚙️ 封禁用户 ID {target_user_id} 失败：机器人权限不足或层级不够。", ephemeral=True)
    except discord.NotFound:
         # 这通常意味着提供的 User ID 无效或不存在于 Discord
         await interaction.followup.send(f"❓ 封禁失败：找不到用户 ID 为 {target_user_id} 的用户。", ephemeral=True)
    except discord.HTTPException as http_err:
         await interaction.followup.send(f"⚙️ 封禁用户 ID {target_user_id} 时发生网络错误: {http_err}", ephemeral=True)
    except Exception as e:
        print(f"执行 /管理 封禁 时出错: {e}")
        await interaction.followup.send(f"⚙️ 封禁用户 ID {target_user_id} 时发生未知错误: {e}", ephemeral=True)


@manage_group.command(name="解封", description="解除对用户的封禁 (需要 '封禁成员' 权限)。")
@app_commands.describe(user_id="要解除封禁的用户 ID。", reason="(可选) 解除封禁的原因。")
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.checks.bot_has_permissions(ban_members=True)
async def manage_unban(interaction: discord.Interaction, user_id: str, reason: str = "管理员酌情处理"):
    await interaction.response.defer(ephemeral=False) # 解封是重要操作，公开响应
    guild = interaction.guild
    author = interaction.user

    # --- 验证 User ID ---
    try:
        target_user_id = int(user_id)
    except ValueError:
        await interaction.followup.send("❌ 无效的用户 ID 格式。请输入纯数字的用户 ID。", ephemeral=True); return

    # --- 检查用户是否真的被封禁 ---
    try:
        ban_entry = await guild.fetch_ban(discord.Object(id=target_user_id))
        user_to_unban = ban_entry.user # 获取被封禁的 User 对象
    except discord.NotFound:
        # 用户未被封禁
        await interaction.followup.send(f"ℹ️ 用户 ID {target_user_id} 当前并未被此服务器封禁。", ephemeral=True)
        return
    except discord.Forbidden:
         await interaction.followup.send(f"⚙️ 检查封禁状态失败：机器人缺少查看封禁列表的权限。", ephemeral=True)
         return
    except Exception as fetch_err:
         print(f"获取用户 {target_user_id} 封禁信息时出错: {fetch_err}")
         await interaction.followup.send(f"⚙️ 获取封禁信息时出错: {fetch_err}", ephemeral=True)
         return

    # --- 执行解封 ---
    unban_reason_full = f"由 {author.display_name} ({author.id}) 解除封禁，原因: {reason}"
    try:
        await guild.unban(user_to_unban, reason=unban_reason_full)

        # 发送确认消息
        user_display = f"{user_to_unban.name}#{user_to_unban.discriminator}"
        await interaction.followup.send(f"✅ 用户 **{user_display}** (ID: {target_user_id}) 已被成功解除封禁。\n原因: {reason}", ephemeral=False)
        print(f"[审核操作] 用户 {author} 解除了对用户 ID {target_user_id} ({user_display}) 的封禁。原因: {reason}")

        # 可选：记录到日志
        log_embed = discord.Embed(
            title="✅ 用户解封",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        log_embed.add_field(name="执行者", value=author.mention, inline=True)
        log_embed.add_field(name="被解封用户", value=f"{user_display} ({target_user_id})", inline=True)
        log_embed.add_field(name="原因", value=reason, inline=False)
        log_embed.set_footer(text=f"执行者 ID: {author.id} | 用户 ID: {target_user_id}")
        await send_to_public_log(guild, log_embed, log_type="Unban Member")

    except discord.Forbidden:
         await interaction.followup.send(f"⚙️ 解封用户 ID {target_user_id} 失败：机器人权限不足。", ephemeral=True)
    except discord.HTTPException as http_err:
         await interaction.followup.send(f"⚙️ 解封用户 ID {target_user_id} 时发生网络错误: {http_err}", ephemeral=True)
    except Exception as e:
        print(f"执行 /管理 解封 时出错: {e}")
        await interaction.followup.send(f"⚙️ 解封用户 ID {target_user_id} 时发生未知错误: {e}", ephemeral=True)


@manage_group.command(name="人数频道", description="创建或更新一个显示服务器成员人数的语音频道。")
@app_commands.describe(channel_name_template="(可选) 频道名称的模板，用 '{count}' 代表人数。")
@app_commands.checks.has_permissions(manage_channels=True) # 需要管理频道权限
@app_commands.checks.bot_has_permissions(manage_channels=True)
async def manage_member_count_channel(interaction: discord.Interaction, channel_name_template: str = "📊｜成员人数: {count}"):
    await interaction.response.defer(ephemeral=True) # 临时响应
    guild = interaction.guild

    # 从内存设置中获取已存在的频道 ID 和模板
    existing_channel_id = get_setting(guild.id, "member_count_channel_id")
    existing_template = get_setting(guild.id, "member_count_template")
    existing_channel = guild.get_channel(existing_channel_id) if existing_channel_id else None

    # 获取当前成员数并生成新名称
    member_count = guild.member_count # 获取准确的成员数
    try:
        new_name = channel_name_template.format(count=member_count)
        if len(new_name) > 100:
             await interaction.followup.send(f"❌ 失败：生成的频道名称 '{new_name}' 超过100字符限制，请缩短模板。", ephemeral=True)
             return
        if not new_name.strip():
             await interaction.followup.send(f"❌ 失败：生成的频道名称不能为空。", ephemeral=True)
             return
    except KeyError:
         await interaction.followup.send("❌ 失败：频道名称模板无效，必须包含 `{count}`。", ephemeral=True)
         return
    except Exception as format_err:
         await interaction.followup.send(f"❌ 失败：处理频道名称模板时出错: {format_err}", ephemeral=True)
         return

    # 检查是否需要更新或创建
    if existing_channel and isinstance(existing_channel, discord.VoiceChannel):
        # 更新现有频道
        # 检查名称或模板是否真的改变了
        if existing_channel.name == new_name and existing_template == channel_name_template:
             await interaction.followup.send(f"ℹ️ 成员人数频道 {existing_channel.mention} 的名称和模板无需更新。", ephemeral=True)
             return
        try:
            await existing_channel.edit(name=new_name, reason="更新服务器成员人数")
            set_setting(guild.id, "member_count_template", channel_name_template) # 更新模板设置
            await interaction.followup.send(f"✅ 已成功更新成员人数频道 {existing_channel.mention} 的名称为 `{new_name}`。", ephemeral=True)
            print(f"[管理操作] 服务器 {guild.id} 的成员人数频道 ({existing_channel_id}) 已更新为 '{new_name}'。")
        except discord.Forbidden:
             await interaction.followup.send(f"⚙️ 更新频道 {existing_channel.mention} 失败：机器人缺少管理频道的权限。", ephemeral=True)
        except discord.HTTPException as http_err:
             await interaction.followup.send(f"⚙️ 更新频道 {existing_channel.mention} 时发生网络错误: {http_err}", ephemeral=True)
        except Exception as e:
            print(f"更新人数频道时出错: {e}")
            await interaction.followup.send(f"⚙️ 更新频道 {existing_channel.mention} 时发生未知错误: {e}", ephemeral=True)
    else:
        # 创建新频道
        try:
            # 设置权限：阻止 @everyone 连接，但允许机器人连接和管理
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False),
                guild.me: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True)
            }
            new_channel = await guild.create_voice_channel(
                name=new_name,
                overwrites=overwrites,
                reason="创建服务器成员人数统计频道"
            )
            # 保存新频道的 ID 和模板到内存设置
            set_setting(guild.id, "member_count_channel_id", new_channel.id)
            set_setting(guild.id, "member_count_template", channel_name_template)
            await interaction.followup.send(f"✅ 已成功创建成员人数统计频道: {new_channel.mention}。", ephemeral=True)
            print(f"[管理操作] 服务器 {guild.id} 创建了成员人数频道 '{new_name}' ({new_channel.id})。")
        except discord.Forbidden:
             await interaction.followup.send(f"⚙️ 创建人数频道失败：机器人缺少创建频道或设置权限的权限。", ephemeral=True)
        except discord.HTTPException as http_err:
             await interaction.followup.send(f"⚙️ 创建人数频道时发生网络错误: {http_err}", ephemeral=True)
        except Exception as e:
            print(f"创建人数频道时出错: {e}")
            await interaction.followup.send(f"⚙️ 创建人数频道时发生未知错误: {e}", ephemeral=True)


# --- Temporary Voice Channel Command Group ---
voice_group = app_commands.Group(name="语音声道", description="临时语音频道相关指令")

@voice_group.command(name="设定母频道", description="设置一个语音频道，用户加入后会自动创建临时频道 (需管理频道权限)。")
@app_commands.describe(
    master_channel="选择一个语音频道作为创建入口 (母频道)。",
    category="(可选) 选择一个分类，新创建的临时频道将放置在此分类下。"
)
@app_commands.checks.has_permissions(manage_channels=True) # 需要管理频道权限来设置
@app_commands.checks.bot_has_permissions(manage_channels=True, move_members=True) # 机器人需要创建频道和移动成员
async def voice_set_master(interaction: discord.Interaction, master_channel: discord.VoiceChannel, category: Optional[discord.CategoryChannel] = None):
    guild_id = interaction.guild_id
    await interaction.response.defer(ephemeral=True) # 临时响应

    # 检查机器人是否对母频道和目标分类有足够权限
    bot_member = interaction.guild.me
    if not master_channel.permissions_for(bot_member).view_channel:
        await interaction.followup.send(f"❌ 设置失败：机器人无法看到母频道 {master_channel.mention}！请检查权限。", ephemeral=True)
        return

    target_category = category if category else master_channel.category
    if not target_category:
         await interaction.followup.send(f"❌ 设置失败：找不到有效的分类来创建频道 (母频道 {master_channel.mention} 可能不在任何分类下，且你未指定分类)。", ephemeral=True)
         return

    cat_perms = target_category.permissions_for(bot_member)
    if not cat_perms.manage_channels or not cat_perms.move_members or not cat_perms.view_channel:
        missing_perms = []
        if not cat_perms.manage_channels: missing_perms.append("管理频道")
        if not cat_perms.move_members: missing_perms.append("移动成员")
        if not cat_perms.view_channel: missing_perms.append("查看频道")
        await interaction.followup.send(f"❌ 设置失败：机器人在目标分类 **{target_category.name}** 中缺少必要的权限: {', '.join(missing_perms)}！", ephemeral=True)
        return

    # 保存设置到内存
    set_setting(guild_id, "master_channel_id", master_channel.id)
    set_setting(guild_id, "category_id", target_category.id) # 保存最终使用的分类ID

    cat_name_text = f" 在分类 **{target_category.name}** 下"
    await interaction.followup.send(f"✅ 临时语音频道的母频道已成功设置为 {master_channel.mention}{cat_name_text}。", ephemeral=True)
    print(f"[临时语音] 服务器 {guild_id}: 母频道设置为 {master_channel.id}, 分类设置为 {target_category.id}")


# --- Helper to check if user is the owner of the temp VC they are in ---
def is_temp_vc_owner(interaction: discord.Interaction) -> bool:
    """检查交互发起者是否是其所在临时语音频道的创建者"""
    # 检查用户是否在语音频道中
    if not interaction.user.voice or not interaction.user.voice.channel:
        return False
    user_vc = interaction.user.voice.channel
    # 检查该频道是否是记录在案的临时频道，并且所有者是当前用户
    return user_vc.id in temp_vc_owners and temp_vc_owners.get(user_vc.id) == interaction.user.id


@voice_group.command(name="设定权限", description="(房主专用) 修改你创建的临时语音频道中某个成员或身份组的权限。")
@app_commands.describe(
    target="要修改权限的目标用户或身份组。",
    allow_connect="(可选) 是否允许连接到频道？",
    allow_speak="(可选) 是否允许在频道中说话？",
    allow_stream="(可选) 是否允许在频道中直播？",
    allow_video="(可选) 是否允许在频道中开启摄像头？"
)
async def voice_set_perms(
    interaction: discord.Interaction,
    target: Union[discord.Member, discord.Role], # 允许选择用户或身份组
    allow_connect: Optional[bool] = None,
    allow_speak: Optional[bool] = None,
    allow_stream: Optional[bool] = None,
    allow_video: Optional[bool] = None):

    await interaction.response.defer(ephemeral=True) # 临时响应

    # 检查用户是否在自己的临时频道中
    user_vc = interaction.user.voice.channel if interaction.user.voice else None
    if not user_vc or not is_temp_vc_owner(interaction):
        await interaction.followup.send("❌ 此命令只能在你创建的临时语音频道中使用。", ephemeral=True)
        return

    # 检查机器人是否有管理权限的权限
    if not user_vc.permissions_for(interaction.guild.me).manage_permissions:
         await interaction.followup.send(f"⚙️ 操作失败：机器人缺少在频道 {user_vc.mention} 中 '管理权限' 的能力。", ephemeral=True)
         return

    # 获取目标当前的权限覆写设置
    # 如果目标没有显式设置，会创建一个新的 Overwrite 对象
    overwrites = user_vc.overwrites_for(target)
    perms_changed = [] # 记录哪些权限被修改了

    # 根据用户的输入更新权限设置
    if allow_connect is not None:
        overwrites.connect = allow_connect
        perms_changed.append(f"连接: {'✅' if allow_connect else '❌'}")
    if allow_speak is not None:
        overwrites.speak = allow_speak
        perms_changed.append(f"说话: {'✅' if allow_speak else '❌'}")
    if allow_stream is not None:
        overwrites.stream = allow_stream
        perms_changed.append(f"直播: {'✅' if allow_stream else '❌'}")
    if allow_video is not None:
        overwrites.video = allow_video
        perms_changed.append(f"视频: {'✅' if allow_video else '❌'}")

    # 如果用户没有指定任何要修改的权限
    if not perms_changed:
        await interaction.followup.send("⚠️ 你没有指定任何要修改的权限。", ephemeral=True)
        return

    # 应用权限更改
    try:
        await user_vc.set_permissions(
            target,
            overwrite=overwrites, # 应用修改后的权限覆写
            reason=f"由临时频道房主 {interaction.user.name} ({interaction.user.id}) 修改权限"
        )
        target_mention = target.mention if isinstance(target, discord.Member) else target.name
        await interaction.followup.send(f"✅ 已成功更新 **{target_mention}** 在频道 {user_vc.mention} 的权限：\n{', '.join(perms_changed)}", ephemeral=True)
        print(f"[临时语音] 房主 {interaction.user} 修改了频道 {user_vc.id} 中 {target} 的权限: {', '.join(perms_changed)}")
    except discord.Forbidden:
         await interaction.followup.send(f"⚙️ 设置权限失败：机器人缺少在频道 {user_vc.mention} 中修改权限的权限。", ephemeral=True)
    except discord.HTTPException as http_err:
         await interaction.followup.send(f"⚙️ 设置权限时发生网络错误: {http_err}", ephemeral=True)
    except Exception as e:
        print(f"执行 /语音声道 设定权限 时出错: {e}")
        await interaction.followup.send(f"⚙️ 设置权限时发生未知错误: {e}", ephemeral=True)


@voice_group.command(name="转让", description="(房主专用) 将你创建的临时语音频道所有权转让给频道内的其他用户。")
@app_commands.describe(new_owner="选择要接收所有权的新用户 (该用户必须在频道内)。")
async def voice_transfer(interaction: discord.Interaction, new_owner: discord.Member):
    await interaction.response.defer(ephemeral=False) # 转让是公开可见的操作
    user = interaction.user # 当前房主
    user_vc = user.voice.channel if user.voice else None

    # 检查是否是房主
    if not user_vc or not is_temp_vc_owner(interaction):
        await interaction.followup.send("❌ 此命令只能在你创建的临时语音频道中使用。", ephemeral=True)
        return

    # 检查目标用户
    if new_owner.bot:
        await interaction.followup.send("❌ 不能将所有权转让给机器人。", ephemeral=True); return
    if new_owner == user:
        await interaction.followup.send("❌ 你不能将所有权转让给自己。", ephemeral=True); return
    # 检查目标用户是否在同一个频道内
    if not new_owner.voice or new_owner.voice.channel != user_vc:
        await interaction.followup.send(f"❌ 目标用户 {new_owner.mention} 必须在你的临时频道 ({user_vc.mention}) 内才能接收所有权。", ephemeral=True); return

    # 检查机器人是否有管理权限的权限
    if not user_vc.permissions_for(interaction.guild.me).manage_permissions:
         await interaction.followup.send(f"⚙️ 操作失败：机器人缺少在频道 {user_vc.mention} 中 '管理权限' 的能力来完成转让。", ephemeral=True)
         return

    try:
        # 定义新房主的权限 (与创建时相同)
        new_owner_overwrites = discord.PermissionOverwrite(
            manage_channels=True, manage_permissions=True, move_members=True,
            connect=True, speak=True, stream=True, use_voice_activation=True,
            priority_speaker=True, mute_members=True, deafen_members=True, use_embedded_activities=True, video=True # 增加了 video=True
        )
        # 定义旧房主的权限 (恢复默认或移除特殊权限)
        # 使用 None 会继承分类权限，或者创建一个空的 Overwrite 对象来清除显式设置
        old_owner_overwrites = discord.PermissionOverwrite() # 清除旧房主的特殊权限

        # 原子地更新两个用户的权限
        # 注意：如果频道权限复杂，可能需要更精细地处理旧房主的权限，而不是完全清除
        await user_vc.set_permissions(new_owner, overwrite=new_owner_overwrites, reason=f"所有权由 {user.name} 转让给 {new_owner.name}")
        await user_vc.set_permissions(user, overwrite=old_owner_overwrites, reason=f"所有权已转让给 {new_owner.name}")

        # 更新内存中的所有者记录
        temp_vc_owners[user_vc.id] = new_owner.id

        await interaction.followup.send(f"✅ 频道 {user_vc.mention} 的所有权已成功转让给 {new_owner.mention}！", ephemeral=False)
        print(f"[临时语音] 频道 {user_vc.id} 的所有权从 {user.id} 转让给了 {new_owner.id}")

    except discord.Forbidden:
         await interaction.followup.send(f"⚙️ 转让所有权失败：机器人缺少在频道 {user_vc.mention} 中修改权限的权限。", ephemeral=True)
    except discord.HTTPException as http_err:
         await interaction.followup.send(f"⚙️ 转让所有权时发生网络错误: {http_err}", ephemeral=True)
    except Exception as e:
        print(f"执行 /语音声道 转让 时出错: {e}")
        await interaction.followup.send(f"⚙️ 转让所有权时发生未知错误: {e}", ephemeral=True)


@voice_group.command(name="房主", description="(成员使用) 如果原房主已离开频道，尝试获取该临时语音频道的所有权。")
async def voice_claim(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False) # 尝试获取房主权是公开的
    user = interaction.user # 指令发起者
    user_vc = user.voice.channel if user.voice else None

    # 检查用户是否在临时频道内
    if not user_vc or user_vc.id not in temp_vc_created:
        await interaction.followup.send("❌ 此命令只能在临时语音频道中使用。", ephemeral=True)
        return

    current_owner_id = temp_vc_owners.get(user_vc.id)

    # 如果用户已经是房主
    if current_owner_id == user.id:
        await interaction.followup.send("ℹ️ 你已经是这个频道的房主了。", ephemeral=True)
        return

    # 检查原房主是否还在频道内
    owner_is_present = False
    original_owner = None # 保存原房主对象，后面可能需要重置其权限
    if current_owner_id:
        original_owner = interaction.guild.get_member(current_owner_id)
        if original_owner and original_owner.voice and original_owner.voice.channel == user_vc:
            owner_is_present = True

    if owner_is_present:
        await interaction.followup.send(f"❌ 无法获取所有权：原房主 {original_owner.mention} 仍然在频道中。", ephemeral=True)
        return

    # 检查机器人是否有管理权限的权限
    if not user_vc.permissions_for(interaction.guild.me).manage_permissions:
         await interaction.followup.send(f"⚙️ 操作失败：机器人缺少在频道 {user_vc.mention} 中 '管理权限' 的能力来授予你房主权限。", ephemeral=True)
         return

    # --- 执行获取房主权限 ---
    try:
        # 定义新房主的权限 (与创建时相同)
        new_owner_overwrites = discord.PermissionOverwrite(
            manage_channels=True, manage_permissions=True, move_members=True,
            connect=True, speak=True, stream=True, use_voice_activation=True,
            priority_speaker=True, mute_members=True, deafen_members=True, use_embedded_activities=True, video=True
        )

        # 将房主权限授予请求者
        await user_vc.set_permissions(user, overwrite=new_owner_overwrites, reason=f"由 {user.name} ({user.id}) 获取房主权限")

        # (可选但推荐) 如果存在原房主，并且原房主不在频道内，尝试重置原房主的特殊权限
        if original_owner:
             try:
                 # 使用 None 会让其权限继承自分类或 @everyone
                 await user_vc.set_permissions(original_owner, overwrite=None, reason="原房主离开频道，重置其特殊权限")
                 print(f"   - 已尝试重置原房主 {original_owner.id} 在频道 {user_vc.id} 的特殊权限。")
             except Exception as reset_e:
                 # 重置失败通常不影响新房主获取权限，后台记录即可
                 print(f"   - 尝试重置原房主 {original_owner.id} 权限时出错 (可能已离开服务器): {reset_e}")

        # 更新内存中的所有者记录
        temp_vc_owners[user_vc.id] = user.id

        await interaction.followup.send(f"✅ 恭喜 {user.mention}！你已成功获取频道 {user_vc.mention} 的房主权限！", ephemeral=False)
        print(f"[临时语音] 用户 {user.id} 获取了频道 {user_vc.id} 的房主权限 (原房主: {current_owner_id})")

    except discord.Forbidden:
         await interaction.followup.send(f"⚙️ 获取房主权限失败：机器人缺少在频道 {user_vc.mention} 中修改权限的权限。", ephemeral=True)
    except discord.HTTPException as http_err:
         await interaction.followup.send(f"⚙️ 获取房主权限时发生网络错误: {http_err}", ephemeral=True)
    except Exception as e:
        print(f"执行 /语音声道 房主 时出错: {e}")
        await interaction.followup.send(f"⚙️ 获取房主权限时发生未知错误: {e}", ephemeral=True)


# --- Add the command groups to the bot tree ---
# 确保在定义完指令组和 bot 对象之后，在全局作用域添加它们
bot.tree.add_command(manage_group)
bot.tree.add_command(voice_group)

# --- Run the Bot ---
if __name__ == "__main__":
    print("正在启动机器人...")
    if not BOT_TOKEN:
        print("错误：无法启动，因为 DISCORD_BOT_TOKEN 未设置。")
    elif not DEEPSEEK_API_KEY:
         print("警告：DEEPSEEK_API_KEY 未设置，AI 内容审核功能将不可用。")
         print("机器人将继续启动，但无法执行 AI 内容检查。")
         try:
             bot.run(BOT_TOKEN)
         except discord.LoginFailure: print("❌ 致命错误：登录失败。提供的 DISCORD_BOT_TOKEN 无效。")
         except discord.PrivilegedIntentsRequired: print("❌ 致命错误：机器人缺少必要的特权 Intents (Members, Message Content)。请在 Discord 开发者门户中启用它们！")
         except Exception as e: print(f"❌ 机器人启动过程中发生致命错误: {e}")
    else:
        try:
            # 运行机器人，使用从环境变量加载的 Token
            bot.run(BOT_TOKEN)
        except discord.LoginFailure:
            print("❌ 致命错误：登录失败。提供的 DISCORD_BOT_TOKEN 无效。")
        except discord.PrivilegedIntentsRequired:
            print("❌ 致命错误：机器人缺少必要的特权 Intents (Members, Message Content)。请在 Discord 开发者门户中启用它们！")
        except Exception as e:
            print(f"❌ 机器人启动过程中发生致命错误: {e}")

# --- End of Complete Code ---