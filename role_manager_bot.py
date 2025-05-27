# slash_role_manager_bot.py (FINAL COMPLETE CODE v23 - Ticket Tool Added)

import discord
from discord import app_commands, ui # Added ui
from discord.ext import commands
from discord.utils import get
import os
from dotenv import load_dotenv
import time # 用于计算 API 延迟
import datetime
import asyncio
from typing import Optional, Union, Any, Dict, List # 根据你的实际使用情况添加 List 等
import requests # Required for DeepSeek API & Announce fallback
import json     # Required for DeepSeek API
try:
    import aiohttp # Preferred for async requests in announce
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    print("⚠️ 警告: 未安装 'aiohttp' 库。 /announce 中的图片URL验证将使用 'requests' (可能阻塞)。建议运行: pip install aiohttp")

import io
import html
from collections import deque
import sys

# 在尝试获取环境变量之前加载 .env 文件
# 指定 .env 文件的路径
dotenv_path = '/etc/discord-bot/gjteam.env' # 或者你可以创建一个在项目根目录的 .env 文件用于本地开发
load_dotenv(dotenv_path=dotenv_path)

# --- Configuration ---
# !!! 重要：从环境变量加载 Bot Token !!!
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ 致命错误：未设置 DISCORD_BOT_TOKEN 环境变量。")
    print("   请在你的托管环境（例如 Railway Variables）中设置此变量。")
    exit()

# !!! 重要：从环境变量加载重启密码 !!!
RESTART_PASSWORD = os.environ.get("BOT_RESTART_PASSWORD")
if not RESTART_PASSWORD:
    print("⚠️ 警告：未设置 BOT_RESTART_PASSWORD 环境变量。/管理 restart 指令将不可用。")

# !!! 重要：从环境变量加载 DeepSeek API Key !!!
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    print("⚠️ 警告：未设置 DEEPSEEK_API_KEY 环境变量。DeepSeek 内容审核功能将被禁用。")

# !!! 重要：确认 DeepSeek API 端点和模型名称 !!!
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions" # <--- 确认 DeepSeek API URL!
DEEPSEEK_MODEL = "deepseek-chat" # <--- 替换为你希望使用的 DeepSeek 模型!

COMMAND_PREFIX = "!" # 旧版前缀（现在主要使用斜线指令）

# --- 新增：AI 对话功能配置与存储 ---
# 用于存储被设置为 AI DEP 频道的配置
# 结构: {channel_id: {"model": "model_id_str", "system_prompt": "optional_system_prompt_str", "history_key": "unique_history_key_for_channel"}}
ai_dep_channels_config = {} 

# 用于存储所有类型的对话历史 (包括公共 AI 频道、私聊等)
# 结构: {history_key: deque_object}
conversation_histories = {} # 注意：这个变量名可能与你之前代码中的不同，确保一致性

# 定义可用于 AI 对话的模型
AVAILABLE_AI_DIALOGUE_MODELS = {
    "deepseek-chat": "通用对话模型 (DeepSeek Chat)",
    "deepseek-coder": "代码生成模型 (DeepSeek Coder)",
    "deepseek-reasoner": "推理模型 (DeepSeek Reasoner - 支持思维链)"
}
DEFAULT_AI_DIALOGUE_MODEL = "deepseek-chat" 
MAX_AI_HISTORY_TURNS = 10 # AI 对话功能的最大历史轮数 (每轮包含用户和AI的发言)

# 用于追踪用户创建的私聊AI频道
# 结构: {channel_id: {"user_id": user_id, "model": "model_id", "history_key": "unique_key", "guild_id": guild_id, "channel_id": channel_id}}
active_private_ai_chats = {} 
# --- AI 对话功能配置与存储结束 ---

# --- 新增：服务器专属AI知识库 ---
# 结构: {guild_id: List[str]}
guild_knowledge_bases = {}
MAX_KB_ENTRIES_PER_GUILD = 50 
MAX_KB_ENTRY_LENGTH = 1000   
MAX_KB_DISPLAY_ENTRIES = 15 
# --- 服务器专属AI知识库结束 ---

# --- (在你的配置区域，可以放在 guild_knowledge_bases 附近) ---

# --- 新增：服务器独立FAQ/帮助系统 ---
# 结构: {guild_id: List[Dict[str, str]]}  每个字典包含 "keyword" 和 "answer"
# 或者更简单：{guild_id: Dict[str, str]}  其中 key 是关键词，value 是答案
# 我们先用简单的 Dict[str, str] 结构，一个关键词对应一个答案。
# 如果需要更复杂的，比如一个关键词对应多个答案片段，或带标题的条目，可以调整。
server_faqs = {}
MAX_FAQ_ENTRIES_PER_GUILD = 100 # 每个服务器FAQ的最大条目数
MAX_FAQ_KEYWORD_LENGTH = 50    # 单个FAQ关键词的最大长度
MAX_FAQ_ANSWER_LENGTH = 1500   # 单个FAQ答案的最大长度
MAX_FAQ_LIST_DISPLAY = 20      # /faq list 中显示的最大条目数
# --- 服务器独立FAQ/帮助系统结束 ---

# --- (在你现有的配置区域) ---

# --- 服务器内匿名中介私信系统 ---
# 结构: {message_id_sent_to_user_dm: {"initiator_id": int, "target_id": int, "original_channel_id": int, "guild_id": int}}
# message_id_sent_to_user_dm 是机器人发送给目标用户的初始私信的ID，用于追踪回复
ANONYMOUS_RELAY_SESSIONS = {}
# 可选：为了让发起者在频道内回复，可能需要一个更持久的会话ID
# {relay_session_id (e.g., unique_string): {"initiator_id": int, "target_id": int, "original_channel_id": int, "guild_id": int, "last_target_dm_message_id": int}}
# 为简化，我们先基于初始DM的message_id

# 允许使用此功能的身份组 (可选, 如果不设置则所有成员可用，但需谨慎)
ANONYMOUS_RELAY_ALLOWED_ROLE_IDS = [] # 例如: [1234567890] 如果需要限制
# --- 服务器内匿名中介私信系统结束 ---

# --- Intents Configuration ---
# 确保这些也在 Discord 开发者门户中启用了！
intents = discord.Intents.default()
intents.members = True      # 需要用于 on_member_join, 成员信息, 成员指令
intents.message_content = True # 需要用于 on_message 刷屏/违禁词检测
intents.voice_states = True # 需要用于临时语音频道功能
intents.guilds = True       # 需要用于票据功能和其他服务器信息获取

# --- Bot Initialization ---
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)
bot.closing_tickets_in_progress = set() # Add this line
bot.approved_bot_whitelist = {} # {guild_id: set(bot_id1, bot_id2)} # <--- 新增这一行
bot.persistent_views_added_in_setup = False

class CloseTicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Buttons inside tickets should persist

    @ui.button(label="关闭票据", style=discord.ButtonStyle.danger, custom_id="close_ticket_button")
    async def close_button(self, interaction: discord.Interaction, button: ui.Button):
        # Defer first to acknowledge
        try:
            if not interaction.response.is_done(): # Check if already responded/deferred
                await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            print(f"DEBUG: CloseTicket: Interaction {interaction.id} not found on defer, likely channel gone or interaction stale.")
            return # Cannot proceed if interaction is invalid
        except discord.HTTPException as e:
            print(f"DEBUG: CloseTicket: HTTPException on defer for interaction {interaction.id}: {e}")
            # If defer fails, we might still be able to use followup if it was already deferred by a previous attempt.
            # However, if it's the first attempt and defer fails, followup will also likely fail.
            if not interaction.response.is_done(): # If defer truly failed and it wasn't already done
                 print(f"DEBUG: CloseTicket: Deferral failed critically for interaction {interaction.id}. Aborting.")
                 return
        except Exception as e: # Catch any other deferral errors
            print(f"DEBUG: CloseTicket: Generic error deferring interaction {interaction.id}: {e}")
            if not interaction.response.is_done():
                print(f"DEBUG: CloseTicket: Deferral failed critically (generic) for interaction {interaction.id}. Aborting.")
                return

        guild = interaction.guild
        channel = interaction.channel # This is the ticket channel
        user = interaction.user # The user clicking the close button

        if not guild or not isinstance(channel, discord.TextChannel):
            try: await interaction.followup.send("❌ 操作无法在此处完成。", ephemeral=True)
            except Exception as fe: print(f"Debug: Followup error in initial check: {fe}")
            return

        # Re-entry guard
        if channel.id in bot.closing_tickets_in_progress:
            print(f"DEBUG: CloseTicket: Channel {channel.id} already in closing_tickets_in_progress. User: {user.id}")
            try: await interaction.followup.send("⏳ 此票据已在关闭处理中，请稍候。", ephemeral=True)
            except Exception as fe: print(f"Debug: Followup error for re-entry guard: {fe}")
            return
        
        bot.closing_tickets_in_progress.add(channel.id)
        print(f"DEBUG: CloseTicket: Added channel {channel.id} to closing_tickets_in_progress by user {user.id}.")

        try:
            # --- Original logic from here ---
            creator_id = None
            guild_tickets = open_tickets.get(guild.id, {})
            for uid, chan_id in guild_tickets.items():
                if chan_id == channel.id:
                    creator_id = uid
                    break
            
            print(f"DEBUG: CloseTicket: Processing close for channel {channel.name} ({channel.id}), creator_id: {creator_id}")

            # --- 生成聊天记录 ---
            transcript_html_content = None
            sanitized_channel_name = "".join(c for c in str(channel.name) if c.isalnum() or c in ('-', '_')).lower()
            if not sanitized_channel_name: sanitized_channel_name = f"ticket-{channel.id}"
            transcript_filename = f"transcript-{sanitized_channel_name}-{channel.id}.html"
            
            transcript_generation_message_to_closer = "" 
            transcript_dm_sent_to_closer = False
            transcript_sent_to_admin_channel = False

            try:
                print(f"DEBUG: CloseTicket: Generating transcript for {channel.id}")
                transcript_html_content = await generate_ticket_transcript_html(channel)
                if transcript_html_content is None: 
                    transcript_generation_message_to_closer = "⚠️ 未能生成票据聊天记录副本 (可能读取错误或频道为空)。"
                    print(f"DEBUG: CloseTicket: Transcript generation for {channel.id} returned None.")
                else:
                    print(f"DEBUG: CloseTicket: Transcript generated for {channel.id}, length approx {len(transcript_html_content)}")
            except Exception as e:
                print(f"   - ❌ 生成频道 {channel.id} 的聊天记录时发生错误: {e}")
                transcript_generation_message_to_closer = "⚠️ 生成票据聊天记录副本时发生内部错误。"

            # 1. 尝试将聊天记录私信给关闭者
            if transcript_html_content:
                try:
                    html_file_bytes = transcript_html_content.encode('utf-8')
                    transcript_file_obj = discord.File(io.BytesIO(html_file_bytes), filename=transcript_filename)
                    print(f"DEBUG: CloseTicket: Attempting to DM transcript to user {user.id} for channel {channel.id}")
                    await user.send(
                        f"你好 {user.mention}，你关闭的票据 **#{channel.name}** (ID: {channel.id}) 的聊天记录副本如下：", 
                        file=transcript_file_obj
                    )
                    print(f"   - ✅ 已将票据 {channel.name} 的聊天记录私信给关闭者 {user.name} ({user.id})")
                    transcript_generation_message_to_closer = "聊天记录副本已通过私信发送给你。"
                    transcript_dm_sent_to_closer = True
                except discord.Forbidden:
                    print(f"   - ⚠️ 无法将聊天记录私信给关闭者 {user.name} ({user.id})：用户可能关闭了私信或屏蔽了机器人。")
                    transcript_generation_message_to_closer = "⚠️ 无法将聊天记录私信给你 (可能关闭了私信)。文件已生成但未发送。"
                except Exception as e:
                    print(f"   - ❌ 发送聊天记录给关闭者 {user.name} ({user.id}) 时发生错误: {e}")
                    transcript_generation_message_to_closer = f"⚠️ 尝试私信聊天记录副本时发生错误: {e}"
            elif not transcript_generation_message_to_closer: 
                transcript_generation_message_to_closer = "⚠️ 未能生成票据聊天记录副本 (频道可能为空或读取错误)。"
            
            print(f"DEBUG: CloseTicket: After DM attempt. transcript_dm_sent_to_closer={transcript_dm_sent_to_closer}")

            # 2. 尝试将聊天记录发送到管理员/日志频道
            admin_log_channel_id_for_transcript = PUBLIC_WARN_LOG_CHANNEL_ID
            admin_log_channel_object = None
            print(f"DEBUG: CloseTicket: Attempting to send transcript to admin channel ID: {admin_log_channel_id_for_transcript}")

            if transcript_html_content and admin_log_channel_id_for_transcript and admin_log_channel_id_for_transcript != 1363523347169939578: 
                print(f"DEBUG: CloseTicket: Condition for admin send is TRUE. Fetching admin channel.")
                admin_log_channel_object = guild.get_channel(admin_log_channel_id_for_transcript)
                print(f"DEBUG: CloseTicket: Admin channel object: {admin_log_channel_object} (type: {type(admin_log_channel_object)})")

                if admin_log_channel_object and isinstance(admin_log_channel_object, discord.TextChannel):
                    print(f"DEBUG: CloseTicket: Admin channel is a valid TextChannel. Checking permissions.")
                    bot_perms = admin_log_channel_object.permissions_for(guild.me)
                    print(f"DEBUG: CloseTicket: Bot perms in admin channel: attach_files={bot_perms.attach_files}, send_messages={bot_perms.send_messages}") # MODIFIED HERE
                    if bot_perms.attach_files and bot_perms.send_messages: # MODIFIED HERE
                        try:
                            html_file_bytes_for_admin = transcript_html_content.encode('utf-8')
                            transcript_file_obj_for_admin = discord.File(io.BytesIO(html_file_bytes_for_admin), filename=transcript_filename)
                            
                            creator_mention_log = f"<@{creator_id}>" if creator_id else "未知"
                            try: 
                                if creator_id:
                                    creator_user_obj_temp = await bot.fetch_user(creator_id)
                                    creator_mention_log = f"{creator_user_obj_temp.mention} (`{creator_user_obj_temp}`)"
                            except Exception as fetch_exc: 
                                print(f"DEBUG: CloseTicket: Failed to fetch creator_user_obj_temp: {fetch_exc}")
                                pass # Keep basic mention if fetch fails

                            admin_message_content = (
                                f"票据 **#{channel.name}** (ID: `{channel.id}`) 已由 {user.mention} 关闭。\n"
                                f"创建者: {creator_mention_log}.\n"
                                f"聊天记录副本见附件。"
                            )
                            print(f"DEBUG: CloseTicket: Sending transcript to admin channel {admin_log_channel_object.name}")
                            await admin_log_channel_object.send(content=admin_message_content, file=transcript_file_obj_for_admin)
                            print(f"   - ✅ 已将票据 {channel.name} 的聊天记录发送到管理频道 {admin_log_channel_object.name} ({admin_log_channel_id_for_transcript})")
                            transcript_sent_to_admin_channel = True
                        except discord.Forbidden:
                            print(f"   - ❌ 发送聊天记录到管理频道 {admin_log_channel_id_for_transcript} 失败：机器人缺少发送文件/消息权限。")
                        except Exception as log_send_e:
                            print(f"   - ❌ 发送聊天记录到管理频道 {admin_log_channel_id_for_transcript} 时发生错误: {log_send_e}")
                    else:
                        print(f"   - ⚠️ 无法发送聊天记录到管理频道 {admin_log_channel_id_for_transcript}：机器人缺少发送文件/消息权限。")
                elif admin_log_channel_id_for_transcript and admin_log_channel_id_for_transcript != 1363523347169939578 :
                    print(f"   - ⚠️ 管理员日志频道ID ({admin_log_channel_id_for_transcript}) 无效或不是文本频道，无法发送聊天记录。")
            elif transcript_html_content and (not admin_log_channel_id_for_transcript or admin_log_channel_id_for_transcript == 1363523347169939578):
                print(f"   - ℹ️ 未配置有效的公共日志频道ID (或为示例ID)，跳过发送聊天记录给管理员。")
            else:
                print(f"DEBUG: CloseTicket: Conditions for sending to admin channel not met. transcript_html_content: {transcript_html_content is not None}, admin_log_channel_id_for_transcript: {admin_log_channel_id_for_transcript}")


            # --- 在票据频道中宣布关闭 ---
            public_close_message_parts = [f"⏳ {user.mention} 已请求关闭此票据。"]
            # ... (rest of public_close_message_parts logic) ...
            if transcript_dm_sent_to_closer: public_close_message_parts.append("聊天记录副本已发送给关闭者。")
            elif transcript_html_content: public_close_message_parts.append("尝试发送聊天记录副本给关闭者失败。")
            else: public_close_message_parts.append("未能生成聊天记录副本。")
            
            if transcript_sent_to_admin_channel: public_close_message_parts.append("聊天记录副本已发送给管理员。")
            elif transcript_html_content and admin_log_channel_id_for_transcript and admin_log_channel_id_for_transcript != 1363523347169939578:
                public_close_message_parts.append("尝试发送聊天记录副本给管理员失败。")
                
            public_close_message_parts.append("频道将在几秒后删除...")
            final_public_close_message = "\n".join(public_close_message_parts)
            
            try:
                print(f"DEBUG: CloseTicket: Sending close announcement to ticket channel {channel.id}")
                await channel.send(final_public_close_message)
            except discord.Forbidden:
                print(f"   - ⚠️ 无法在票据频道 {channel.name} 发送关闭通知 (权限不足)。")
            except discord.NotFound:
                print(f"   - ⚠️ 无法在票据频道 {channel.name} 发送关闭通知 (频道未找到 - 可能已被其他进程删除)。")
            except Exception as e:
                print(f"   - ⚠️ 在票据频道 {channel.name} 发送关闭通知时出错: {e}")


            print(f"[票据] 用户 {user} ({user.id}) 关闭了票据频道 #{channel.name} ({channel.id})")

            # --- 记录日志 (到公共日志频道) ---
            log_embed = discord.Embed(
                title="🎫 票据已关闭",
                description=f"票据频道 **#{channel.name}** 已被关闭。",
                color=discord.Color.greyple(),
                timestamp=discord.utils.utcnow()
            )
            # ... (rest of log_embed fields) ...
            log_embed.add_field(name="关闭者", value=user.mention, inline=True)
            log_embed.add_field(name="频道 ID", value=str(channel.id), inline=True)
            if creator_id:
                creator_display = f"<@{creator_id}>"
                try:
                    creator_user_obj = await bot.fetch_user(creator_id)
                    creator_display = f"{creator_user_obj.mention} (`{creator_user_obj}`)"
                except Exception as fetch_creator_err: 
                     print(f"DEBUG: CloseTicket: Failed to fetch creator user object for log: {fetch_creator_err}")
                     pass 
                log_embed.add_field(name="创建者", value=creator_display, inline=True)
            
            transcript_log_parts = []
            if transcript_html_content:
                transcript_log_parts.append("已生成。")
                if transcript_dm_sent_to_closer: transcript_log_parts.append("已私信关闭者。")
                else: transcript_log_parts.append("私信关闭者失败。")
                if transcript_sent_to_admin_channel: transcript_log_parts.append("已发送至管理频道。")
                elif admin_log_channel_id_for_transcript and admin_log_channel_id_for_transcript != 1363523347169939578:
                    transcript_log_parts.append("发送至管理频道失败。")
                else: 
                    transcript_log_parts.append("未发送至管理频道(未配置或为示例ID)。")
            else:
                transcript_log_parts.append("未生成。")
            log_embed.add_field(name="聊天记录状态", value=" ".join(transcript_log_parts).strip(), inline=False)
            
            print(f"DEBUG: CloseTicket: Sending 'Ticket Closed' log to public log channel for {channel.id}")
            await send_to_public_log(guild, log_embed, log_type="Ticket Closed")


            # 从 open_tickets 中移除记录
            if creator_id and guild.id in open_tickets and creator_id in open_tickets[guild.id]:
                if open_tickets[guild.id].get(creator_id) == channel.id: # .get for safety
                    del open_tickets[guild.id][creator_id]
                    print(f"   - 已从 open_tickets 移除记录 (用户: {creator_id}, 频道: {channel.id})")
                else:
                    print(f"DEBUG: CloseTicket: Mismatch or missing entry in open_tickets for creator {creator_id}, channel {channel.id}. Current: {open_tickets[guild.id].get(creator_id)}")
            elif creator_id:
                 print(f"DEBUG: CloseTicket: Guild {guild.id} or creator {creator_id} not in open_tickets for channel {channel.id}. open_tickets[guild]: {open_tickets.get(guild.id)}")


            # 延迟并删除频道
            print(f"DEBUG: CloseTicket: Sleeping for 7 seconds before deleting channel {channel.id}")
            await asyncio.sleep(7) 
            delete_status_message = ""
            try:
                print(f"DEBUG: CloseTicket: Attempting to delete channel {channel.name} ({channel.id})")
                await channel.delete(reason=f"票据由 {user.name} 关闭")
                print(f"   - 已成功删除票据频道 #{channel.name}")
                delete_status_message = "✅ 票据频道已成功删除。"
            except discord.Forbidden:
                print(f"   - 删除票据频道 #{channel.name} 失败：机器人缺少权限。")
                delete_status_message = "❌ 无法删除频道：机器人缺少权限。"
            except discord.NotFound:
                print(f"   - 删除票据频道 #{channel.name} 失败：频道未找到 (可能已被删除)。")
                delete_status_message = "ℹ️ 票据频道似乎已被删除。" 
            except Exception as e:
                print(f"   - 删除票据频道 #{channel.name} 时发生错误: {e}")
                delete_status_message = f"❌ 删除频道时发生错误: {e}"

            # --- 给关闭者的最终反馈 ---
            final_followup_parts = [delete_status_message, transcript_generation_message_to_closer]
            # ... (rest of final_followup_parts logic) ...
            admin_send_feedback_to_closer = ""
            if transcript_html_content: 
                if transcript_sent_to_admin_channel:
                    admin_send_feedback_to_closer = "聊天记录副本也已发送至管理频道。"
                elif admin_log_channel_id_for_transcript and admin_log_channel_id_for_transcript != 1363523347169939578:
                    admin_send_feedback_to_closer = "尝试发送聊天记录至管理频道失败。"
            
            if admin_send_feedback_to_closer:
                final_followup_parts.append(admin_send_feedback_to_closer)

            final_followup_message_str = "\n".join(filter(None, final_followup_parts)).strip()
            print(f"DEBUG: CloseTicket: Final followup message for {user.id}: '{final_followup_message_str}'")

            try:
                if final_followup_message_str: 
                    # Check if interaction is still valid before followup
                    if interaction.response.is_done():
                        await interaction.followup.send(final_followup_message_str, ephemeral=True)
                    else:
                        # This case should be rare if defer was successful.
                        # It implies the interaction might have expired or original message deleted.
                        print(f"DEBUG: CloseTicket: Interaction {interaction.id} was not 'done' before final followup. Trying to send DM fallback.")
                        if not transcript_dm_sent_to_closer: # Avoid double DM if transcript already sent this info
                             await user.send(f"关于票据 **#{channel.name}** ({channel.id}) 的关闭状态：\n{final_followup_message_str}")

            except discord.NotFound:
                 print(f"   - ⚠️ 无法发送最终关闭票据的 follow-up 给 {user.name}: Interaction or original message not found.")
                 if not transcript_dm_sent_to_closer: # Fallback DM
                    try: await user.send(f"关于票据 **#{channel.name}** ({channel.id}) 的关闭状态：\n{final_followup_message_str}")
                    except Exception as dm_fallback_err: print(f"   - ⚠️ 尝试通过私信发送最终状态给 {user.name} 也失败了: {dm_fallback_err}")
            except discord.HTTPException as e: 
                print(f"   - ⚠️ 无法发送最终关闭票据的 follow-up 给 {user.name}: {e}. 消息是: '{final_followup_message_str}'")
                if not transcript_dm_sent_to_closer:
                    try: await user.send(f"关于票据 **#{channel.name}** ({channel.id}) 的关闭状态：\n{final_followup_message_str}")
                    except Exception as dm_fallback_err: print(f"   - ⚠️ 尝试通过私信发送最终状态给 {user.name} 也失败了: {dm_fallback_err}")

        except Exception as e_outer:
            print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            print(f"CRITICAL ERROR in close_ticket_button for channel {channel.id if channel and hasattr(channel, 'id') else 'UnknownCh'}: {type(e_outer).__name__} - {str(e_outer)}")
            import traceback
            traceback.print_exc()
            print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            try:
                error_msg_to_user = f"❌ 关闭票据时发生严重内部错误 ({type(e_outer).__name__})。频道可能未被删除。请联系管理员。"
                if interaction.response.is_done():
                    await interaction.followup.send(error_msg_to_user, ephemeral=True)
                # else: # If defer failed and it wasn't already done, this is tricky.
                #    await interaction.response.send_message(error_msg_to_user, ephemeral=True)
            except Exception as e_followup_fail_critical:
                print(f"DEBUG: CloseTicket: Failed to send CRITICAL ERROR followup to user: {e_followup_fail_critical}")
        finally:
            bot.closing_tickets_in_progress.discard(channel.id) # Ensure it's removed
            print(f"DEBUG: CloseTicket: Removed channel {channel.id if channel and hasattr(channel, 'id') else 'UnknownCh'} from closing_tickets_in_progress.")

            # View for the initial "Create Ticket" button (Persistent)
class CreateTicketView(ui.View):
    # ... (这个类的其他部分保持不变) ...
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="➡️ 开票-认证", style=discord.ButtonStyle.primary, custom_id="create_verification_ticket")
    async def create_ticket_button(self, interaction: discord.Interaction, button: ui.Button):
        # ... (这个方法保持不变) ...
        guild = interaction.guild
        user = interaction.user
        if not guild: return 

        print(f"[票据] 用户 {user} ({user.id}) 在服务器 {guild.id} 点击了创建票据按钮。")
        await interaction.response.defer(ephemeral=True) 

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
            return

        staff_roles = [guild.get_role(role_id) for role_id in staff_role_ids]
        staff_roles = [role for role in staff_roles if role] 
        if not staff_roles:
             await interaction.followup.send("❌ 抱歉，配置的票据员工身份组无效或已被删除。请联系管理员。", ephemeral=True)
             print(f"   - 票据创建失败：服务器 {guild.id} 配置的员工身份组 ({staff_role_ids}) 均无效。")
             return

        guild_tickets = open_tickets.setdefault(guild.id, {})
        if user.id in guild_tickets:
            existing_channel_id = guild_tickets[user.id]
            existing_channel = guild.get_channel(existing_channel_id)
            if existing_channel:
                 await interaction.followup.send(f"⚠️ 你已经有一个开启的票据：{existing_channel.mention}。请先处理完当前的票据。", ephemeral=True)
                 print(f"   - 票据创建失败：用户 {user.id} 已有票据频道 {existing_channel_id}")
                 return
            else:
                 print(f"   - 清理无效票据记录：用户 {user.id} 的票据频道 {existing_channel_id} 不存在。")
                 del guild_tickets[user.id]

        bot_perms = ticket_category.permissions_for(guild.me)
        if not bot_perms.manage_channels or not bot_perms.manage_permissions:
             await interaction.followup.send("❌ 创建票据失败：机器人缺少在票据分类中 '管理频道' 或 '管理权限' 的权限。", ephemeral=True)
             print(f"   - 票据创建失败：机器人在分类 {ticket_category.id} 缺少权限。")
             return

        ticket_count = get_setting(ticket_settings, guild.id, "ticket_count") or 0
        ticket_count += 1
        set_setting(ticket_settings, guild.id, "ticket_count", ticket_count)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False), 
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True), 
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_permissions=True, embed_links=True, read_message_history=True) 
        }
        staff_mentions = []
        for role in staff_roles:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True, attach_files=True, embed_links=True)
            staff_mentions.append(role.mention)
        staff_mention_str = " ".join(staff_mentions)

        sanitized_username = "".join(c for c in user.name if c.isalnum() or c in ('-', '_')).lower()
        if not sanitized_username: sanitized_username = "user" 
        channel_name = f"认证-{ticket_count:04d}-{sanitized_username}"[:100] 
        new_channel = None 
        try:
            new_channel = await guild.create_text_channel(
                name=channel_name,
                category=ticket_category,
                overwrites=overwrites,
                topic=f"用户 {user.id} ({user}) 的认证票据 | 创建时间: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
                reason=f"用户 {user.name} 创建认证票据"
            )
            print(f"   - 已成功创建票据频道: #{new_channel.name} ({new_channel.id})")

            guild_tickets[user.id] = new_channel.id

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

            await new_channel.send(content=f"{user.mention} {staff_mention_str}", embed=welcome_embed, view=CloseTicketView()) # <--- 注意这里传递的是新实例化的CloseTicketView

            await interaction.followup.send(f"✅ 你的认证票据已创建：{new_channel.mention}", ephemeral=True)

        except discord.Forbidden:
             await interaction.followup.send("❌ 创建票据失败：机器人权限不足，无法创建频道或设置权限。", ephemeral=True)
             print(f"   - 票据创建失败：机器人在创建频道时权限不足。")
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
            if new_channel:
                try: await new_channel.delete(reason="创建过程中出错")
                except: pass
# --- 新增：机器人白名单文件存储 (可选, 但推荐) ---
BOT_WHITELIST_FILE = "bot_whitelist.json" # <--- 新增这一行 (如果使用文件存储)

# --- 经济系统配置 ---
ECONOMY_ENABLED = True  # 经济系统全局开关
ECONOMY_CURRENCY_NAME = "金币"
ECONOMY_CURRENCY_SYMBOL = "💰"
ECONOMY_DEFAULT_BALANCE = 100  # 新用户首次查询时的默认余额
ECONOMY_CHAT_EARN_DEFAULT_AMOUNT = 1
ECONOMY_CHAT_EARN_DEFAULT_COOLDOWN_SECONDS = 60  # 1 分钟
ECONOMY_DATA_FILE = "economy_data.json"
ECONOMY_MAX_SHOP_ITEMS_PER_PAGE = 5 # 减少以便更好地显示
ECONOMY_MAX_LEADERBOARD_USERS = 10
ECONOMY_TRANSFER_TAX_PERCENT = 1 # 示例: 转账收取 1% 手续费。设为 0 则无手续费。
ECONOMY_MIN_TRANSFER_AMOUNT = 10 # 最低转账金额

# --- 经济系统数据存储 (内存中，通过 JSON 持久化) ---
# {guild_id: {user_id: balance}}
user_balances: Dict[int, Dict[int, int]] = {}

# {guild_id: {item_slug: {"name": str, "price": int, "description": str, "role_id": Optional[int], "stock": int (-1 代表无限), "purchase_message": Optional[str]}}}
shop_items: Dict[int, Dict[str, Dict[str, Any]]] = {}

# {guild_id: {"chat_earn_amount": int, "chat_earn_cooldown": int}} # 存储覆盖默认值的设置
guild_economy_settings: Dict[int, Dict[str, int]] = {}

# {guild_id: {user_id: last_earn_timestamp_float}}
last_chat_earn_times: Dict[int, Dict[int, float]] = {}


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
PUBLIC_WARN_LOG_CHANNEL_ID = 1374390176591122582 # <--- 替换! 示例 ID

# !!! 重要：替换成你的启动通知频道ID !!!
STARTUP_MESSAGE_CHANNEL_ID = 1374390176591122582 # <--- 替换! 示例 ID (例如: 138000000000000000)
                                # 如果为 0 或未配置，则不发送启动消息

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


    pass

# --- 新增：通用的 DeepSeek API 请求函数 (用于AI对话功能) ---
async def get_deepseek_dialogue_response(session, api_key, model, messages_for_api, max_tokens_override=None):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    payload = {"model": model, "messages": messages_for_api}
    if model == "deepseek-reasoner":
        if max_tokens_override and isinstance(max_tokens_override, int) and max_tokens_override > 0:
            payload["max_tokens"] = max_tokens_override 
    elif max_tokens_override and isinstance(max_tokens_override, int) and max_tokens_override > 0: 
        payload["max_tokens"] = max_tokens_override

    cleaned_messages_for_api = []
    for msg in messages_for_api:
        cleaned_msg = msg.copy() 
        if "reasoning_content" in cleaned_msg:
            del cleaned_msg["reasoning_content"]
        cleaned_messages_for_api.append(cleaned_msg)
    payload["messages"] = cleaned_messages_for_api

    print(f"[AI DIALOGUE] Requesting: model='{model}', msgs_count={len(cleaned_messages_for_api)}") 
    if cleaned_messages_for_api: print(f"[AI DIALOGUE] First message for API: {cleaned_messages_for_api[0]}")

    try:
        async with session.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=300) as response:
            raw_response_text = await response.text()
            try: response_data = json.loads(raw_response_text)
            except json.JSONDecodeError:
                print(f"[AI DIALOGUE] ERROR: Failed JSON decode. Status: {response.status}. Text: {raw_response_text[:200]}...")
                return None, None, f"无法解析响应(状态{response.status})"

            if response.status == 200:
                if response_data.get("choices") and len(response_data["choices"]) > 0:
                    message_data = response_data["choices"][0].get("message", {})
                    usage = response_data.get("usage")
                    
                    reasoning_content_api = None
                    final_content_api = message_data.get("content")

                    if model == "deepseek-reasoner":
                        reasoning_content_api = message_data.get("reasoning_content")
                        if reasoning_content_api is None: print(f"[AI DIALOGUE] DEBUG: Model '{model}' did not return 'reasoning_content'.")
                    
                    display_response = ""
                    if reasoning_content_api:
                        display_response += f"🤔 **思考过程:**\n```\n{reasoning_content_api.strip()}\n```\n\n"
                    
                    if final_content_api:
                        prefix = "💬 **最终回答:**\n" if reasoning_content_api else "" 
                        display_response += f"{prefix}{final_content_api.strip()}"
                    elif reasoning_content_api and not final_content_api: 
                        print(f"[AI DIALOGUE] WARNING: Model '{model}' returned reasoning but no final content.")
                    elif not final_content_api and not reasoning_content_api:
                        print(f"[AI DIALOGUE] ERROR: API for model '{model}' missing 'content' & 'reasoning_content'. Data: {message_data}")
                        return None, None, "API返回数据不完整(内容和思考过程均缺失)"

                    if not display_response.strip():
                        print(f"[AI DIALOGUE] ERROR: Generated 'display_response' is empty for model '{model}'.")
                        return None, None, "API生成的回复内容为空"

                    print(f"[AI DIALOGUE] INFO: Success for model '{model}'. Usage: {usage}")
                    return display_response.strip(), final_content_api, None 
                else:
                    print(f"[AI DIALOGUE] ERROR: API response missing 'choices' for model '{model}': {response_data}")
                    return None, None, f"意外响应结构：{response_data}"
            else:
                error_detail = response_data.get("error", {}).get("message", f"未知错误(状态{response.status})")
                print(f"[AI DIALOGUE] ERROR: API error (Status {response.status}) for model '{model}': {error_detail}. Resp: {raw_response_text[:200]}")
                user_error_msg = f"API调用出错(状态{response.status}): {error_detail}"
                if response.status == 400:
                    user_error_msg += "\n(提示:400通常因格式错误或在上下文中传入了`reasoning_content`)"
                return None, None, user_error_msg
    except aiohttp.ClientConnectorError as e:
        print(f"[AI DIALOGUE] ERROR: Network error: {e}")
        return None, None, "无法连接API"
    except asyncio.TimeoutError:
        print("[AI DIALOGUE] ERROR: API request timed out.")
        return None, None, "API连接超时"
    except Exception as e:
        print(f"[AI DIALOGUE] EXCEPTION: Unexpected API call error: {type(e).__name__} - {str(e)}")
        import traceback
        traceback.print_exc()
        return None, None, f"未知API错误: {str(e)}"

# --- (get_deepseek_dialogue_response 函数定义结束) ---

# --- Helper Function: Generate HTML Transcript for Tickets ---
# async def generate_ticket_transcript_html(channel: discord.TextChannel) -> Optional[str]:
# ... (接下来的函数定义)
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

        # --- Helper Function: Generate HTML Transcript for Tickets ---
async def generate_ticket_transcript_html(channel: discord.TextChannel) -> Optional[str]:
    """Generates an HTML transcript for the given text channel."""
    if not isinstance(channel, discord.TextChannel):
        return None

    messages_history = []
    # Fetch all messages, oldest first.
    async for message in channel.history(limit=None, oldest_first=True):
        messages_history.append(message)

    if not messages_history:
        return f"""
        <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>票据记录 - {html.escape(channel.name)}</title>
        <style>body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #2C2F33; color: #DCDDDE; text-align: center; }} 
        .container {{ background-color: #36393F; padding: 20px; border-radius: 8px; display: inline-block; }}</style></head>
        <body><div class="container"><h1>票据 #{html.escape(channel.name)}</h1><p>此票据中没有消息。</p></div></body></html>
        """

    message_html_blocks = []
    for msg in messages_history:
        author_name_full = html.escape(f"{msg.author.name}#{msg.author.discriminator if msg.author.discriminator != '0' else ''}")
        author_id = msg.author.id
        avatar_url = msg.author.display_avatar.url
        timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        
        content_escaped = ""
        is_system_message = msg.type != discord.MessageType.default and msg.type != discord.MessageType.reply

        if is_system_message:
            if msg.system_content:
                content_escaped = f"<em>系统消息: {html.escape(msg.system_content)}</em>"
            else:
                content_escaped = f"<em>(系统消息: {msg.type.name})</em>"
        elif msg.content:
            content_escaped = html.escape(msg.content).replace("\n", "<br>")

        attachments_html = ""
        if msg.attachments:
            links = []
            for attachment in msg.attachments:
                links.append(f'<a href="{attachment.url}" target="_blank" rel="noopener noreferrer">[{html.escape(attachment.filename)}]</a>')
            attachments_html = f'<div class="attachments">附件: {", ".join(links)}</div>'

        embeds_html = ""
        if msg.embeds:
            embed_parts = []
            for embed_idx, embed in enumerate(msg.embeds):
                embed_str = f'<div class="embed embed-{embed_idx+1}">'
                if embed.title:
                    embed_str += f'<div class="embed-title">{html.escape(embed.title)}</div>'
                if embed.description:
                    escaped_description = html.escape(embed.description).replace("\n", "<br>")
                    embed_str += f'<div class="embed-description">{escaped_description}</div>'
                
                fields_html = ""
                if embed.fields:
                    fields_html += '<div class="embed-fields">'
                    for field in embed.fields:
                        field_name = html.escape(field.name) if field.name else " "
                        field_value = html.escape(field.value).replace("\n", "<br>") if field.value else " "
                        inline_class = " embed-field-inline" if field.inline else ""
                        fields_html += f'<div class="embed-field{inline_class}"><strong>{field_name}</strong><br>{field_value}</div>'
                    fields_html += '</div>'
                embed_str += fields_html

                if embed.footer and embed.footer.text:
                    embed_str += f'<div class="embed-footer">{html.escape(embed.footer.text)}</div>'
                if embed.author and embed.author.name:
                    embed_str += f'<div class="embed-author">作者: {html.escape(embed.author.name)}</div>'
                if not embed.title and not embed.description and not embed.fields:
                    embed_str += '<em>(嵌入内容)</em>'
                embed_str += '</div>'
                embed_parts.append(embed_str)
            embeds_html = "".join(embed_parts)

        message_block = f"""
        <div class="message {'system-message' if is_system_message else ''}">
            <div class="message-header">
                <img src="{avatar_url}" alt="{html.escape(msg.author.name)}'s avatar" class="author-avatar">
                <div class="author-details">
                    <span class="author" title="User ID: {author_id}">{author_name_full}</span>
                </div>
                <span class="timestamp">{timestamp}</span>
            </div>
            <div class="content-area">
                {f'<div class="content"><p>{content_escaped}</p></div>' if content_escaped else ""}
                {attachments_html}
                {embeds_html}
            </div>
        </div>
        """
        message_html_blocks.append(message_block)

    full_html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>票据记录 - {html.escape(channel.name)}</title>
        <style>
            body {{ font-family: 'Whitney', 'Helvetica Neue', Helvetica, Arial, sans-serif; margin: 0; padding: 0; background-color: #36393f; color: #dcddde; font-size: 16px; line-height: 1.6; }}
            .container {{ max-width: 90%; width: 800px; margin: 20px auto; background-color: #36393f; padding: 20px; border-radius: 8px; box-shadow: 0 0 15px rgba(0,0,0,0.5); }}
            .header {{ text-align: center; border-bottom: 1px solid #4f545c; padding-bottom: 15px; margin-bottom: 20px; }}
            .header h1 {{ color: #ffffff; margin: 0 0 5px 0; font-size: 24px; }}
            .header p {{ font-size: 12px; color: #b9bbbe; margin: 0; }}
            .message {{ display: flex; flex-direction: column; padding: 12px 0; border-top: 1px solid #40444b; }}
            .message:first-child {{ border-top: none; }}
            .message-header {{ display: flex; align-items: center; margin-bottom: 6px; }}
            .author-avatar {{ width: 40px; height: 40px; border-radius: 50%; margin-right: 12px; background-color: #2f3136; }}
            .author-details {{ display: flex; flex-direction: column; flex-grow: 1; }}
            .author {{ font-weight: 500; color: #ffffff; font-size: 1em; }}
            .timestamp {{ font-size: 0.75em; color: #72767d; margin-left: 8px; white-space: nowrap; }}
            .content-area {{ margin-left: 52px; /* Align with author name, after avatar */ }}
            .content p {{ margin: 0 0 5px 0; white-space: pre-wrap; word-wrap: break-word; color: #dcddde; }}
            .attachments, .embed {{ margin-top: 8px; font-size: 0.9em; }}
            .attachments {{ padding: 5px; background-color: #2f3136; border-radius: 3px; }}
            .attachment a {{ color: #00aff4; text-decoration: none; margin-right: 5px; }}
            .attachment a:hover {{ text-decoration: underline; }}
            .embed {{ border-left: 4px solid #4f545c; padding: 10px; background-color: #2f3136; border-radius: 4px; margin-bottom: 5px; }}
            .embed-title {{ font-weight: bold; color: #ffffff; margin-bottom: 4px; }}
            .embed-description {{ color: #b9bbbe; font-size: 0.95em; }}
            .embed-fields {{ display: flex; flex-wrap: wrap; margin-top: 8px; }}
            .embed-field {{ padding: 5px; margin-bottom: 5px; flex-basis: 100%; }}
            .embed-field-inline {{ flex-basis: calc(50% - 10px); margin-right: 10px; }} /* Adjust for closer to Discord layout */
            .embed-field strong {{ color: #ffffff; }}
            .embed-footer, .embed-author {{ font-size: 0.8em; color: #72767d; margin-top: 5px; }}
            .system-message .content p {{ font-style: italic; color: #72767d; }}
            em {{ color: #b9bbbe; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>票据记录: #{html.escape(channel.name)}</h1>
                <p>服务器: {html.escape(channel.guild.name)} ({channel.guild.id})</p>
                <p>频道 ID: {channel.id}</p>
                <p>生成时间: {datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}</p>
            </div>
            {''.join(message_html_blocks)}
        </div>
    </body>
    </html>
    """
    return full_html_template.strip()

# --- 经济系统：持久化 ---
def load_economy_data():
    global user_balances, shop_items, guild_economy_settings, last_chat_earn_times
    if not ECONOMY_ENABLED:
        return
    try:
        if os.path.exists(ECONOMY_DATA_FILE):
            with open(ECONOMY_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 将字符串键转换回整数类型的 guild_id 和 user_id
                user_balances = {int(gid): {int(uid): bal for uid, bal in u_bals.items()} for gid, u_bals in data.get("user_balances", {}).items()}
                shop_items = {int(gid): items for gid, items in data.get("shop_items", {}).items()} # item_slug 保持为字符串
                guild_economy_settings = {int(gid): settings for gid, settings in data.get("guild_economy_settings", {}).items()}
                last_chat_earn_times = {int(gid): {int(uid): ts for uid, ts in u_times.items()} for gid, u_times in data.get("last_chat_earn_times", {}).items()}
                print(f"[经济系统] 成功从 {ECONOMY_DATA_FILE} 加载数据。")
    except json.JSONDecodeError:
        print(f"[经济系统错误] 解析 {ECONOMY_DATA_FILE} 的 JSON 失败。将以空数据启动。")
    except Exception as e:
        print(f"[经济系统错误] 加载经济数据失败: {e}")

def save_economy_data():
    if not ECONOMY_ENABLED:
        return
    try:
        # 准备要保存到 JSON 的数据 (确保键是字符串，如果它们是从整数转换过来的)
        data_to_save = {
            "user_balances": {str(gid): {str(uid): bal for uid, bal in u_bals.items()} for gid, u_bals in user_balances.items()},
            "shop_items": {str(gid): items for gid, items in shop_items.items()},
            "guild_economy_settings": {str(gid): settings for gid, settings in guild_economy_settings.items()},
            "last_chat_earn_times": {str(gid): {str(uid): ts for uid, ts in u_times.items()} for gid, u_times in last_chat_earn_times.items()}
        }
        with open(ECONOMY_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=4, ensure_ascii=False)
        # print(f"[经济系统] 成功保存数据到 {ECONOMY_DATA_FILE}") # 每次保存都打印可能过于频繁
    except Exception as e:
        print(f"[经济系统错误] 保存经济数据失败: {e}")

# --- 经济系统：辅助函数 ---
def get_user_balance(guild_id: int, user_id: int) -> int:
    return user_balances.get(guild_id, {}).get(user_id, ECONOMY_DEFAULT_BALANCE)

def update_user_balance(guild_id: int, user_id: int, amount: int, is_delta: bool = True) -> bool:
    """
    更新用户余额。
    如果 is_delta 为 True，则 amount 会被加到或从当前余额中减去。
    如果 is_delta 为 False，则 amount 成为新的余额。
    如果操作成功（例如，用 delta 更新时不会导致余额低于零），则返回 True，否则返回 False。
    """
    if guild_id not in user_balances:
        user_balances[guild_id] = {}
    
    current_balance = user_balances[guild_id].get(user_id, ECONOMY_DEFAULT_BALANCE)

    if is_delta:
        if current_balance + amount < 0:
            # 如果尝试花费超过现有金额，则操作失败
            return False 
        user_balances[guild_id][user_id] = current_balance + amount
    else: # 设置绝对余额
        if amount < 0: amount = 0 # 余额不能为负
        user_balances[guild_id][user_id] = amount
    
    # print(f"[经济系统] 用户 {user_id} 在服务器 {guild_id} 的余额已更新: {user_balances[guild_id][user_id]}")
    # save_economy_data() # 每次余额更新都保存可能过于频繁，应在特定事件后保存。
    return True

def get_guild_chat_earn_config(guild_id: int) -> Dict[str, int]:
    defaults = {
        "amount": ECONOMY_CHAT_EARN_DEFAULT_AMOUNT,
        "cooldown": ECONOMY_CHAT_EARN_DEFAULT_COOLDOWN_SECONDS
    }
    if guild_id in guild_economy_settings:
        config = guild_economy_settings[guild_id]
        return {
            "amount": config.get("chat_earn_amount", defaults["amount"]), # 确保键名匹配
            "cooldown": config.get("chat_earn_cooldown", defaults["cooldown"]) # 确保键名匹配
        }
    return defaults
# --- 辅助函数 (如果还没有，添加 get_item_slug) ---
def get_item_slug(item_name: str) -> str:
    return "_".join(item_name.lower().split()).strip() # 简单的 slug：小写，空格转下划线

# --- 定义商店购买按钮的视图 ---
class ShopItemBuyView(discord.ui.View):
    def __init__(self, items_on_page: Dict[str, Dict[str, Any]], guild_id: int):
        super().__init__(timeout=None) # 持久视图或根据需要设置超时

        for slug, item_data in items_on_page.items():
            # 为每个物品创建一个购买按钮
            # custom_id 格式: buy_<guild_id>_<item_slug>
            buy_button = discord.ui.Button(
                label=f"购买 {item_data['name']} ({ECONOMY_CURRENCY_SYMBOL}{item_data['price']})",
                style=discord.ButtonStyle.green,
                custom_id=f"shop_buy_{guild_id}_{slug}", # 确保 custom_id 唯一且可解析
                emoji="🛒" # 可选的表情符号
            )
            # 按钮的回调将在 Cog 中通过 on_interaction 监听 custom_id 来处理，
            # 或者，如果你想直接在这里定义回调（不推荐用于大量动态按钮）：
            # async def button_callback(interaction: discord.Interaction, current_slug=slug): # 使用默认参数捕获slug
            #     # 这个回调逻辑会变得复杂，因为需要访问 GuildMusicState 等
            #     # 更好的方式是在主 Cog 中监听 custom_id
            #     await interaction.response.send_message(f"你点击了购买 {current_slug}", ephemeral=True)
            # buy_button.callback = button_callback
            self.add_item(buy_button)

async def grant_item_purchase(interaction: discord.Interaction, user: discord.Member, item_data: Dict[str, Any]):
    """处理购买物品的效果。"""
    guild = interaction.guild
    
    # 如果指定，则授予身份组
    role_id = item_data.get("role_id")
    if role_id:
        role = guild.get_role(role_id)
        if role:
            if role not in user.roles:
                try:
                    await user.add_roles(role, reason=f"从商店购买了 '{item_data['name']}'")
                    # print(f"[经济系统] 身份组 '{role.name}' 已授予给用户 {user.name} (物品: '{item_data['name']}')。")
                except discord.Forbidden:
                    await interaction.followup.send(f"⚠️ 我无法为你分配 **{role.name}** 身份组，请联系管理员检查我的权限和身份组层级。", ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(f"⚠️ 分配身份组时发生错误: {e}", ephemeral=True)
            # else: # 用户已拥有该身份组
                # print(f"[经济系统] 用户 {user.name} 已拥有物品 '{item_data['name']}' 的身份组。")
        else:
            await interaction.followup.send(f"⚠️ 物品 **{item_data['name']}** 关联的身份组ID `{role_id}` 无效或已被删除，请联系管理员。", ephemeral=True)
            print(f"[经济系统错误] 服务器 {guild.id} 的物品 '{item_data['name']}' 关联的身份组ID {role_id} 无效。")

    # 如果指定，则发送自定义购买消息
    purchase_message = item_data.get("purchase_message")
    if purchase_message:
        try:
            # 替换消息中的占位符
            formatted_message = purchase_message.replace("{user}", user.mention).replace("{item_name}", item_data['name'])
            await user.send(f"🎉 关于你在 **{guild.name}** 商店的购买：\n{formatted_message}")
        except discord.Forbidden:
            await interaction.followup.send(f"ℹ️ 你购买了 **{item_data['name']}**！但我无法私信你发送额外信息（可能关闭了私信）。", ephemeral=True)
        except Exception as e:
            print(f"[经济系统错误] 发送物品 '{item_data['name']}' 的购买私信给用户 {user.id} 时出错: {e}")
# --- Ticket Tool UI Views ---

@bot.event
async def on_interaction(interaction: discord.Interaction):
    # 首先，让默认的指令树处理器处理斜杠指令和已注册的组件交互
    # await bot.process_application_commands(interaction) # discord.py v2.0+
    # 对于 discord.py 的旧版本或如果你想更明确地处理，可以保留或调整
    # 如果你的按钮回调是直接定义在 View 类中的，这部分可能不需要显式处理

    # 处理自定义的商店购买按钮
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id")
        if custom_id and custom_id.startswith("shop_buy_"):
            # 解析 custom_id: shop_buy_<guild_id>_<item_slug>
            parts = custom_id.split("_")
            if len(parts) >= 4: # shop, buy, guildid, slug (slug可能含下划线)
                try:
                    action_guild_id = int(parts[2])
                    item_slug_to_buy = "_".join(parts[3:]) # 重新组合 slug
                    
                    # 确保交互的 guild_id 与按钮中的 guild_id 一致
                    if interaction.guild_id != action_guild_id:
                        await interaction.response.send_message("❌ 按钮似乎来自其他服务器。", ephemeral=True)
                        return

                    # --- 执行购买逻辑 (与 /eco buy 非常相似) ---
                    if not ECONOMY_ENABLED:
                        await interaction.response.send_message("经济系统当前未启用。", ephemeral=True)
                        return

                    # 确保先响应交互，避免超时
                    await interaction.response.defer(ephemeral=True, thinking=True) # thinking=True 显示"思考中"

                    guild_id = interaction.guild_id
                    user = interaction.user # interaction.user 就是点击按钮的用户 (discord.Member)

                    # item_to_buy_data = shop_items.get(guild_id, {}).get(item_slug_to_buy) # 内存版本
                    item_to_buy_data = database.db_get_shop_item(guild_id, item_slug_to_buy) # 数据库版本

                    if not item_to_buy_data:
                        await interaction.followup.send(f"❌ 无法找到物品 `{item_slug_to_buy}`。可能已被移除。", ephemeral=True)
                        return

                    item_price = item_to_buy_data['price']
                    # user_balance = get_user_balance(guild_id, user.id) # 内存版本
                    user_balance = database.db_get_user_balance(guild_id, user.id, ECONOMY_DEFAULT_BALANCE) # 数据库版本

                    if user_balance < item_price:
                        await interaction.followup.send(f"❌ 你的{ECONOMY_CURRENCY_NAME}不足以购买 **{item_to_buy_data['name']}** (需要 {item_price}，你有 {user_balance})。", ephemeral=True)
                        return

                    item_stock = item_to_buy_data.get("stock", -1)
                    if item_stock == 0:
                        await interaction.followup.send(f"❌ 抱歉，物品 **{item_to_buy_data['name']}** 已售罄。", ephemeral=True)
                        return
                    
                    granted_role_id = item_to_buy_data.get("role_id")
                    if granted_role_id and isinstance(user, discord.Member):
                        if discord.utils.get(user.roles, id=granted_role_id):
                            await interaction.followup.send(f"ℹ️ 你已经拥有物品 **{item_to_buy_data['name']}** 关联的身份组了。", ephemeral=True)
                            return
                    
                    # 使用数据库的事务进行购买
                    conn = database.get_db_connection()
                    purchase_successful = False
                    try:
                        conn.execute("BEGIN")
                        balance_updated = database.db_update_user_balance(guild_id, user.id, -item_price, default_balance=ECONOMY_DEFAULT_BALANCE)
                        
                        stock_updated_or_not_needed = True
                        if balance_updated and item_stock != -1:
                            new_stock = item_to_buy_data.get("stock", 0) - 1
                            if not database.db_update_shop_item_stock(guild_id, item_slug_to_buy, new_stock): # 这个函数在 database.py 中
                                 stock_updated_or_not_needed = False
                        
                        if balance_updated and stock_updated_or_not_needed:
                            conn.commit()
                            purchase_successful = True
                        else:
                            conn.rollback()
                    except Exception as db_exc:
                        if conn: conn.rollback()
                        print(f"[Shop Buy Button DB Error] {db_exc}")
                        await interaction.followup.send(f"❌ 购买时发生数据库错误。", ephemeral=True)
                        return # 退出，不继续
                    finally:
                        if conn: conn.close()

                    if purchase_successful:
                        await grant_item_purchase(interaction, user, item_to_buy_data) # 这个函数负责授予身份组和发送私信
                        await interaction.followup.send(f"🎉 恭喜！你已成功购买 **{item_to_buy_data['name']}**！", ephemeral=True)
                        print(f"[Economy][Button Buy] User {user.id} bought '{item_to_buy_data['name']}' for {item_price} in guild {guild_id}.")
                        
                        # 可选: 更新原始商店消息中的库存显示（如果适用且可行）
                        # 这比较复杂，因为需要找到原始消息并修改其 embed 或 view
                        # 简单的做法是让用户重新执行 /eco shop 查看最新库存
                    else:
                        await interaction.followup.send(f"❌ 购买失败，更新数据时发生错误。请重试。", ephemeral=True)

                except ValueError: # int(parts[2]) 转换失败
                    await interaction.response.send_message("❌ 按钮ID格式错误。",ephemeral=True)
                except Exception as e_button:
                    print(f"Error processing shop_buy button: {e_button}")
                    if not interaction.response.is_done():
                        await interaction.response.send_message("处理购买时发生未知错误。",ephemeral=True)
                    else:
                        await interaction.followup.send("处理购买时发生未知错误。",ephemeral=True)
            # 你可以在这里添加 else if 来处理其他 custom_id 的组件
        # else: # 如果不是组件交互，或者 custom_id 不匹配，则让默认的指令树处理
    # 重要：如果你的机器人也使用了 cogs，并且 cog 中有自己的 on_interaction 监听器，
    # 或者你的按钮回调是直接在 View 中定义的，你需要确保这里的 on_interaction 不会干扰它们。
    # 一种常见的做法是在 Cog 的 listener 中返回，或者在这里只处理未被其他地方处理的交互。
    # 对于简单的单文件机器人，这种方式可以工作。
    # 如果你的 discord.py 版本较高，并且正确使用了 bot.process_application_commands，
    # 那么已注册的视图回调会自动被调用，你可能只需要处理这种动态生成的、没有直接回调的按钮。
    # 为了安全，先确保 bot.process_application_commands 或类似的东西被调用。
    # 如果你的指令树可以正常处理已注册的 view 回调，那么上面的 on_interaction 只需要 shop_buy_ 部分。
    # 很多现代 discord.py 模板会为你处理这个。

    # 确保其他交互（如其他按钮、选择菜单、模态框）也能被正常处理
    # 如果你的 bot 对象有 process_application_commands，调用它
    if hasattr(bot, "process_application_commands"):
         await bot.process_application_commands(interaction)
    # 否则，你可能需要依赖 discord.py 内置的事件分发，或者自己实现更复杂的路由

# View for the button to close a ticket
# View for the button to close a ticket




# --- Event: Bot Ready ---
@bot.event
async def on_ready():
    print(f'以 {bot.user.name} ({bot.user.id}) 身份登录')

    if ECONOMY_ENABLED: # 添加此块
        load_economy_data()
        print("[经济系统] 系统已初始化。")

    print('正在同步应用程序命令...')
    try:
        synced = await bot.tree.sync()
        print(f'已全局同步 {len(synced)} 个应用程序命令。')
    except Exception as e:
        print(f'同步命令时出错: {e}')

    # --- 检查持久化视图注册状态 (由 setup_hook 处理) ---
    if hasattr(bot, 'persistent_views_added_in_setup') and bot.persistent_views_added_in_setup:
        print("ℹ️ 持久化视图 (CreateTicketView, CloseTicketView) 已由 setup_hook 正确注册。")
    else:
        # 这种情况理论上不应该发生，如果发生了，说明 setup_hook 可能有其他问题
        print("⚠️ 警告：持久化视图似乎未在 setup_hook 中注册。请检查 setup_hook 的执行日志和逻辑。")
        # （可选）如果你非常担心，并且希望有一个备用方案，可以取消下面代码的注释，
        # 但这通常不推荐，因为它掩盖了 setup_hook 可能存在的问题。
        # print("尝试在 on_ready 中作为备用方案注册视图...")
        # try:
        #     # 使用一个不同的标志名，以避免与 setup_hook 中的标志混淆
        #     if not hasattr(bot, 'views_added_in_on_ready_fallback'):
        #         bot.add_view(CreateTicketView()) # 确保 CreateTicketView 在此仍然可访问
        #         bot.add_view(CloseTicketView())  # 确保 CloseTicketView 在此仍然可访问
        #         bot.views_added_in_on_ready_fallback = True
        #         print("✅ 已在 on_ready 中作为备用方案注册持久化视图。")
        # except NameError:
        #     print("❌ 在 on_ready 中备用注册视图失败：找不到视图类定义（这不应该发生）。")
        # except Exception as e_on_ready_view_add:
        #     print(f"❌ 在 on_ready 中备用注册视图时发生未知错误: {e_on_ready_view_add}")

    # --- 初始化 aiohttp session ---
    if AIOHTTP_AVAILABLE and not hasattr(bot, 'http_session'):
         bot.http_session = aiohttp.ClientSession()
         print("已创建 aiohttp 会话。")

    print('机器人已准备就绪！')
    print('------')
    # 设置机器人状态
    await bot.change_presence(activity=discord.Game(name="/help 显示帮助"))

    # --- 发送启动通知 ---
    if STARTUP_MESSAGE_CHANNEL_ID and STARTUP_MESSAGE_CHANNEL_ID != 0: # Check if configured and not placeholder
        startup_channel = None
        # Try to find the channel in any guild the bot is in
        for guild in bot.guilds:
            channel = guild.get_channel(STARTUP_MESSAGE_CHANNEL_ID)
            if channel and isinstance(channel, discord.TextChannel):
                startup_channel = channel
                break
        
        if startup_channel:
            bot_perms = startup_channel.permissions_for(startup_channel.guild.me)
            if bot_perms.send_messages and bot_perms.embed_links:
                features_list = [
                    "深度内容审查 (DeepSeek AI)",
                    "本地违禁词检测与自动警告",
                    "用户刷屏行为监测与自动警告/踢出",
                    "机器人刷屏行为监测",
                    "临时语音频道自动管理",
                    "票据系统支持",
                    "机器人白名单与自动踢出 (未授权Bot)",
                    "所有可疑行为将被记录并通知管理员"
                ]
                features_text = "\n".join([f"- {feature}" for feature in features_list])

                embed = discord.Embed(
                    title="🚨 GJ Team 高级监控系统已激活 🚨",
                    description=(
                        f"**本服务器由 {bot.user.name} 全天候监控中。**\n\n"
                        "系统已成功启动并加载以下模块：\n"
                        f"{features_text}\n\n"
                        "**请各位用户自觉遵守服务器规定，共同维护良好环境。**\n"
                        "任何违规行为都可能导致自动警告、禁言、踢出乃至封禁处理。\n"
                        "**所有操作均有详细日志记录。**"
                    ),
                    color=discord.Color.dark_red(),
                    timestamp=discord.utils.utcnow()
                )
                if bot.user.avatar:
                    embed.set_thumbnail(url=bot.user.display_avatar.url)
                embed.set_footer(text="请谨慎发言 | Behave yourselves!")
                try:
                    await startup_channel.send(embed=embed)
                    print(f"✅ 已成功发送启动通知到频道 #{startup_channel.name} ({startup_channel.id})")
                except discord.Forbidden:
                    print(f"❌ 发送启动通知失败：机器人缺少在频道 {STARTUP_MESSAGE_CHANNEL_ID} 发送消息或嵌入链接的权限。")
                except Exception as e:
                    print(f"❌ 发送启动通知时发生错误: {e}")
            else:
                print(f"❌ 发送启动通知失败：机器人在频道 {STARTUP_MESSAGE_CHANNEL_ID} 缺少发送消息或嵌入链接的权限。")
        else:
            print(f"⚠️ 未找到用于发送启动通知的频道 ID: {STARTUP_MESSAGE_CHANNEL_ID}。请检查配置。")
    elif STARTUP_MESSAGE_CHANNEL_ID == 0: # Explicitly 0 means don't send
        print(f"ℹ️ STARTUP_MESSAGE_CHANNEL_ID 设置为0，跳过发送启动通知。")
    # --- 启动通知结束 ---

# 初始化持久化视图标志
bot.persistent_views_added = False

# 为加载 cogs 添加 setup_hook
async def setup_hook_for_bot(): # 重命名以避免与 bot 实例上的属性冲突
    print("正在运行 setup_hook...")
    
    # 加载音乐 Cog
    try:
        await bot.load_extension("music_cog") # 假设 music_cog.py 在同一目录
        print("MusicCog 扩展已通过 setup_hook 成功加载。")
    except commands.ExtensionAlreadyLoaded:
        print("MusicCog 扩展已被加载过。")
    except commands.ExtensionNotFound:
        print("错误：找不到 music_cog 扩展文件 (music_cog.py)。请确保它在正确的位置。")
    except Exception as e:
        print(f"加载 music_cog 扩展失败: {type(e).__name__} - {e}")
        import traceback
        traceback.print_exc()

    # 注册持久化视图 (例如你的票据系统按钮)
    # 确保 CreateTicketView 和 CloseTicketView 类定义在 setup_hook_for_bot 定义之前
    # 或者它们是从其他文件正确导入的
    if not hasattr(bot, 'persistent_views_added_in_setup') or not bot.persistent_views_added_in_setup:
        # 假设 CreateTicketView 和 CloseTicketView 已经定义或导入
        bot.add_view(CreateTicketView()) 
        bot.add_view(CloseTicketView()) 
        # MusicCog 中的按钮是动态添加到消息上的，不需要在这里全局注册
        bot.persistent_views_added_in_setup = True
        print("持久化视图 (CreateTicketView, CloseTicketView) 已在 setup_hook 中注册。")
    
    # 注意：应用命令的同步 (bot.tree.sync()) 通常在 on_ready 中进行，
    # 或者在所有 cogs 加载完毕后进行一次。
    # MusicCog 内部已经通过 bot.tree.add_command(self.music_group) 将其命令组添加到了树中。
    # 所以你现有的 on_ready 中的 bot.tree.sync() 应该可以处理这些新命令。

bot.setup_hook = setup_hook_for_bot # 将钩子函数赋给 bot 实例




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
    welcome_channel_id = 1374384063627923466      # <--- 替换! 欢迎频道 ID
    rules_channel_id = 1374384733743616020        # <--- 替换! 规则频道 ID
    roles_info_channel_id = 1374380842024964288   # <--- 替换! 身份组信息频道 ID
    verification_channel_id = 1374375801323262073 # <--- 替换! 验证频道 ID (或票据开启频道)

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

    # --- 新增/替换：严格的机器人加入控制 ---
    if member.bot and member.id != bot.user.id: # 如果加入的是机器人 (且不是自己的机器人)
        guild_whitelist = bot.approved_bot_whitelist.get(guild.id, set())

        if member.id not in guild_whitelist:
            print(f"[Bot Control] 未经批准的机器人 {member.name} ({member.id}) 尝试加入服务器 {guild.name}。正在踢出...")
            kick_reason = "未经授权的机器人自动踢出。请联系服务器所有者将其ID加入白名单后重试。"
            try:
                if guild.me.guild_permissions.kick_members:
                    if guild.owner:
                        try:
                            owner_embed = discord.Embed(
                                title="🚫 未授权机器人被自动踢出",
                                description=(
                                    f"机器人 **{member.name}** (`{member.id}`) 尝试加入服务器 **{guild.name}** 但未在白名单中，已被自动踢出。\n\n"
                                    f"如果这是一个你信任的机器人，请使用以下指令将其ID添加到白名单：\n"
                                    f"`/管理 bot_whitelist add {member.id}`"
                                ),
                                color=discord.Color.red(),
                                timestamp=discord.utils.utcnow()
                            )
                            await guild.owner.send(embed=owner_embed)
                            print(f"  - 已通知服务器所有者 ({guild.owner.name}) 关于机器人 {member.name} 的自动踢出。")
                        except discord.Forbidden:
                            print(f"  - 无法私信通知服务器所有者 ({guild.owner.name})：TA可能关闭了私信或屏蔽了机器人。")
                        except Exception as dm_e:
                            print(f"  - 私信通知服务器所有者时发生错误: {dm_e}")

                    await member.kick(reason=kick_reason)
                    print(f"  - ✅ 成功踢出机器人 {member.name} ({member.id})。")

                    log_embed = discord.Embed(title="🤖 未授权机器人被踢出", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
                    log_embed.add_field(name="机器人", value=f"{member.mention} (`{member.id}`)", inline=False)
                    log_embed.add_field(name="服务器", value=guild.name, inline=False)
                    log_embed.add_field(name="操作", value="自动踢出 (不在白名单)", inline=False)
                    await send_to_public_log(guild, log_embed, "Unauthorized Bot Kicked")
                else:
                    print(f"  - ❌ 无法踢出机器人 {member.name}：机器人缺少 '踢出成员' 权限。")
                    if guild.owner:
                        try: await guild.owner.send(f"⚠️ 警告：机器人 **{member.name}** (`{member.id}`) 尝试加入服务器 **{guild.name}** 但我缺少踢出它的权限！请手动处理或授予我 '踢出成员' 权限。")
                        except: pass
            except discord.Forbidden:
                print(f"  - ❌ 无法踢出机器人 {member.name}：权限不足 (可能是层级问题)。")
            except Exception as e:
                print(f"  - ❌ 踢出机器人 {member.name} 时发生未知错误: {e}")
        else:
            print(f"[Bot Control] 已批准的机器人 {member.name} ({member.id}) 加入了服务器 {guild.name}。")
            if guild.owner:
                try:
                    await guild.owner.send(f"ℹ️ 白名单中的机器人 **{member.name}** (`{member.id}`) 已加入你的服务器 **{guild.name}**。")
                except: pass
            log_embed = discord.Embed(title="🤖 白名单机器人加入", color=discord.Color.green(), timestamp=discord.utils.utcnow())
            log_embed.add_field(name="机器人", value=f"{member.mention} (`{member.id}`)", inline=False)
            log_embed.add_field(name="服务器", value=guild.name, inline=False)
            log_embed.add_field(name="状态", value="允许加入 (在白名单中)", inline=False)
            await send_to_public_log(guild, log_embed, "Whitelisted Bot Joined")
    # --- 严格的机器人加入控制结束 ---
# role_manager_bot.py

# ... (在你所有命令定义和辅助函数定义之后，但在 Run the Bot 之前) ...



# --- 新增：处理 AI 对话的辅助函数 (你之前已经添加了这个，确保它在 on_message 之前) ---
async def handle_ai_dialogue(message: discord.Message, is_private_chat: bool = False, dep_channel_config: Optional[dict] = None):
    """
    处理来自 AI DEP 频道或 AI 私聊频道的用户消息，并与 DeepSeek AI 交互。
    :param message: discord.Message 对象
    :param is_private_chat: bool, 是否为私聊频道
    :param dep_channel_config: dict, 如果是DEP频道，则传入其配置
    """
    user = message.author
    channel = message.channel
    guild = message.guild # guild is part of message object

    user_prompt_text = message.content.strip()
    if not user_prompt_text:
        if message.attachments: print(f"[AI DIALOGUE HANDLER] Message in {channel.id} from {user.id} has attachments but no text, ignoring.")
        return

    history_key = None
    dialogue_model = None
    system_prompt_for_api = None # 这是从DEP频道配置中获取的原始系统提示

    if is_private_chat:
        chat_info = active_private_ai_chats.get(channel.id)
        if not chat_info :
            print(f"[AI DIALOGUE HANDLER] Private chat {channel.id} - chat_info not found in active_private_ai_chats dict.")
            return
        
        if chat_info.get("user_id") != user.id and user.id != bot.user.id:
             print(f"[AI DIALOGUE HANDLER] Private chat {channel.id} - message from non-owner {user.id} (owner: {chat_info.get('user_id')}). Ignoring.")
             return

        history_key = chat_info.get("history_key")
        dialogue_model = chat_info.get("model", DEFAULT_AI_DIALOGUE_MODEL)
        # 私聊通常没有频道特定的 system_prompt_for_api，但如果以后需要，可以在此添加
    elif dep_channel_config:
        history_key = dep_channel_config.get("history_key")
        dialogue_model = dep_channel_config.get("model", DEFAULT_AI_DIALOGUE_MODEL)
        system_prompt_for_api = dep_channel_config.get("system_prompt") # 获取频道配置的系统提示
    else:
        print(f"[AI DIALOGUE HANDLER ERROR] Called without private_chat flag or dep_channel_config for channel {channel.id}")
        return

    if not history_key or not dialogue_model:
        print(f"[AI DIALOGUE HANDLER ERROR] Missing history_key or dialogue_model for channel {channel.id}. HK:{history_key}, DM:{dialogue_model}")
        try: await channel.send("❌ AI 对话关键配置丢失，请联系管理员。", delete_after=10)
        except: pass
        return
    
    if history_key not in conversation_histories:
        conversation_histories[history_key] = deque(maxlen=MAX_AI_HISTORY_TURNS * 2)
    history_deque = conversation_histories[history_key]

    api_messages = []

    # --- 整合服务器知识库和频道系统提示 ---
    knowledge_base_content = ""
    # 确保 guild_knowledge_bases 已在文件顶部定义
    if guild and guild.id in guild_knowledge_bases and guild_knowledge_bases[guild.id]:
        knowledge_base_content += "\n\n--- 服务器知识库信息 (请优先参考以下内容回答服务器特定问题) ---\n"
        for i, entry in enumerate(guild_knowledge_bases[guild.id]):
            knowledge_base_content += f"{i+1}. {entry}\n"
        knowledge_base_content += "--- 服务器知识库信息结束 ---\n"

    effective_system_prompt = ""
    if system_prompt_for_api: # 使用从DEP频道配置中获取的 system_prompt_for_api
        effective_system_prompt = system_prompt_for_api
    
    if knowledge_base_content: # 将知识库内容附加到（或构成）系统提示
        if effective_system_prompt:
            effective_system_prompt += knowledge_base_content
        else:
            effective_system_prompt = knowledge_base_content.strip()

    if effective_system_prompt:
        api_messages.append({"role": "system", "content": effective_system_prompt})
    # --- 服务器知识库与系统提示整合结束 ---
    
    for msg_entry in history_deque:
        if msg_entry.get("role") in ["user", "assistant"] and "content" in msg_entry and msg_entry.get("content") is not None:
            api_messages.append({"role": msg_entry["role"], "content": msg_entry["content"]})
    
    api_messages.append({"role": "user", "content": user_prompt_text})

    # 更新的 print 语句
    print(f"[AI DIALOGUE HANDLER] Processing for {('Private' if is_private_chat else 'DEP')} Channel {channel.id}, User {user.id}, Model {dialogue_model}, HistKey {history_key}, SysP: {effective_system_prompt != ''}")

    try:
        async with channel.typing():
            # 确保 aiohttp 已导入
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
                response_embed_text, final_content_hist, api_error = await get_deepseek_dialogue_response(
                    session, DEEPSEEK_API_KEY, dialogue_model, api_messages
                )
        
        if api_error:
            try: await channel.send(f"🤖 处理您的请求时出现错误：\n`{api_error}`")
            except: pass
            return

        if response_embed_text:
            history_deque.append({"role": "user", "content": user_prompt_text})
            if final_content_hist is not None:
                history_deque.append({"role": "assistant", "content": final_content_hist})
            else:
                 print(f"[AI DIALOGUE HANDLER] No 'final_content_hist' (was None) to add to history. HK: {history_key}")

            embed = discord.Embed(
                color=discord.Color.blue() if is_private_chat else discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            author_name_prefix = f"{user.display_name} " if not is_private_chat else ""
            model_display_name_parts = dialogue_model.split('-')
            model_short_name = model_display_name_parts[-1].capitalize() if len(model_display_name_parts) > 1 else dialogue_model.capitalize()
            embed_author_name = f"{author_name_prefix}与 {model_short_name} 对话中"

            if user.avatar:
                embed.set_author(name=embed_author_name, icon_url=user.display_avatar.url)
            else:
                embed.set_author(name=embed_author_name)

            if not is_private_chat:
                 embed.add_field(name="👤 提问者", value=user.mention, inline=False)
            
            q_display = user_prompt_text
            if len(q_display) > 1000 : q_display = q_display[:1000] + "..."
            embed.add_field(name=f"💬 {('你的' if is_private_chat else '')}问题:", value=f"```{q_display}```", inline=False)
            
            if len(response_embed_text) <= 4050:
                embed.description = response_embed_text
            else:
                embed.add_field(name="🤖 AI 回复 (部分):", value=response_embed_text[:1020] + "...", inline=False)
                print(f"[AI DIALOGUE HANDLER] WARN: AI response for {channel.id} was very long and truncated for Embed field.")

            footer_model_info = dialogue_model
            # 更新的 footer 文本逻辑
            if effective_system_prompt and not is_private_chat : # 如果存在有效的系统提示 (可能包含知识库)
                footer_model_info += " (有系统提示/知识库)"
            elif effective_system_prompt and is_private_chat : # 私聊也可能有知识库影响
                footer_model_info += " (受知识库影响)"


            if bot.user.avatar:
                embed.set_footer(text=f"模型: {footer_model_info} | {bot.user.name}", icon_url=bot.user.display_avatar.url)
            else:
                embed.set_footer(text=f"模型: {footer_model_info} | {bot.user.name}")
            
            try: await channel.send(embed=embed)
            except Exception as send_e: print(f"[AI DIALOGUE HANDLER] Error sending embed to {channel.id}: {send_e}")

        else:
            print(f"[AI DIALOGUE HANDLER ERROR] 'response_embed_text' was None/empty after no API error. HK: {history_key}")
            try: await channel.send("🤖 抱歉，AI 未能生成有效的回复内容。")
            except: pass

    except Exception as e:
        print(f"[AI DIALOGUE HANDLER EXCEPTION] Unexpected error in channel {channel.id}. User: {user.id}. Error: {type(e).__name__} - {str(e)}")
        import traceback
        traceback.print_exc()
        try:
            await channel.send(f"🤖 处理消息时发生内部错误 ({type(e).__name__})，请联系管理员。")
        except Exception as send_err:
            print(f"[AI DIALOGUE HANDLER SEND ERROR] Could not send internal error to channel {channel.id}. Secondary: {send_err}")
# --- (handle_ai_dialogue 函数定义结束) ---


# --- Event: On Message - Handles AI Dialogues, Content Check, Spam ---
@bot.event
async def on_message(message: discord.Message):
    # --- 首先处理来自用户的私信，判断是否为 RelayMsg 回复 ---
    if isinstance(message.channel, discord.DMChannel) and message.author.id != bot.user.id:
        # 检查这条DM是否是对我们发送的初始匿名消息的回复
        if message.reference and message.reference.message_id in ANONYMOUS_RELAY_SESSIONS:
            session_info = ANONYMOUS_RELAY_SESSIONS[message.reference.message_id]
            
            # 确保回复者是当时的目标用户 (理论上应该是，因为是回复特定消息)
            if message.author.id == session_info["target_id"]:
                original_channel_id = session_info["original_channel_id"]
                initiator_id = session_info["initiator_id"]
                target_id = session_info["target_id"] # 就是 message.author.id
                initiator_display_name = session_info["initiator_display_name"]
                guild_id = session_info["guild_id"]

                guild = bot.get_guild(guild_id)
                if not guild:
                    print(f"[RelayMsg ERROR] Guild {guild_id} not found for session from DM {message.reference.message_id}")
                    return

                original_channel = guild.get_channel(original_channel_id)
                if not original_channel or not isinstance(original_channel, discord.TextChannel): # 或 Thread
                    print(f"[RelayMsg ERROR] Original channel {original_channel_id} not found or not text/thread for session.")
                    # 可以考虑私信通知发起者，他的原始频道找不到了
                    return

                # 构建要转发到服务器频道的消息
                # 注意：这里 target_user.display_name 是公开的
                target_user_obj = await bot.fetch_user(target_id) # 获取最新的用户信息
                
                reply_embed = discord.Embed(
                    title=f"💬 来自 {target_user_obj.display_name if target_user_obj else f'用户 {target_id}'} 的回复",
                    description=f"```\n{message.content}\n```",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                reply_embed.set_footer(text=f"此回复针对由 {initiator_display_name} 发起的匿名消息")
                if message.attachments:
                    # 简单处理第一个附件作为图片预览，更复杂的附件处理需要更多代码
                    if message.attachments[0].content_type and message.attachments[0].content_type.startswith('image/'):
                         reply_embed.set_image(url=message.attachments[0].url)
                    else:
                        reply_embed.add_field(name="📎 附件", value=f"[{message.attachments[0].filename}]({message.attachments[0].url})", inline=False)


                try:
                    await original_channel.send(
                        content=f"<@{initiator_id}>，你收到了对匿名消息的回复：", # Ping 发起者
                        embed=reply_embed
                    )
                    print(f"[RelayMsg] Relayed reply from Target {target_id} (DM) to Initiator {initiator_id} in channel {original_channel_id}")
                    # 可选：私信用户B，告知他们的回复已成功转发
                    await message.author.send("✅ 你的回复已成功转发。", delete_after=30)

                    # 更新会话信息，以便频道内可以通过 /relaymsg reply 回复
                    # 为了简单，这里我们不再追踪 message.id，而是让用户在频道内指定目标用户进行回复
                    # 如果要做更复杂的会话追踪，ANONYMOUS_RELAY_SESSIONS 结构需要调整

                except discord.Forbidden:
                    print(f"[RelayMsg ERROR] Bot lacks permission to send message in original channel {original_channel_id}")
                    # 可以尝试私信通知发起者转发失败
                except Exception as e:
                    print(f"[RelayMsg ERROR] Relaying DM reply: {e}")
                return # 处理完这条DM回复后，不再进行后续的on_message逻辑


    # --- 基本过滤 ---
    if not message.guild or message.author.bot:
        return 
    
    if message.interaction is not None: # 忽略斜杠命令的交互消息本身
        return

    # 忽略以机器人命令前缀或斜杠开头的消息 (这些由命令系统处理)
    # 注意：如果你的AI DEP频道或私聊频道也允许使用其他命令，这里的逻辑可能需要调整
    if message.content.startswith(COMMAND_PREFIX) or message.content.startswith('/'):
        # 如果你还用旧的前缀命令，可以让它们继续处理
        # For example: await bot.process_commands(message)
        return # 通常命令不应被后续逻辑处理

    author = message.author
    author_id = author.id
    guild = message.guild
    channel = message.channel
    now = discord.utils.utcnow() 
    
    # --- 1. 检查是否为配置的 AI DEP 频道的消息 ---
    if channel.id in ai_dep_channels_config:
        print(f"[OnMessage] Message in AI DEP Channel: {channel.id} from {author_id}")
        dep_config = ai_dep_channels_config[channel.id]
        # 确保 handle_ai_dialogue 定义在 on_message 之前
        await handle_ai_dialogue(message, is_private_chat=False, dep_channel_config=dep_config)
        return # 处理完AI DEP频道消息后，不再进行后续的语言审查或刷屏检测

    # --- 2. 检查是否为用户创建的 AI 私聊频道的消息 ---
    if channel.id in active_private_ai_chats:
        print(f"[OnMessage] Message in Private AI Chat: {channel.id} from {author_id}")
        await handle_ai_dialogue(message, is_private_chat=True)
        return # 处理完AI私聊消息后，不再进行后续的语言审查或刷屏检测

    # --- 3. 原有的语言违规检测、本地违禁词、刷屏检测等逻辑 ---
    # 只有当消息不是来自AI DEP频道或AI私聊频道时，才执行以下逻辑
    
    member = guild.get_member(author_id) 

    is_mod_or_admin = False
    if member and isinstance(channel, (discord.TextChannel, discord.Thread)) and channel.permissions_for(member).manage_messages:
        is_mod_or_admin = True
    
    # --- 内容审查 和 本地违禁词 (根据你的豁免逻辑决定是否执行) ---
    if not is_mod_or_admin: # 或者更精细的豁免检查
        perform_content_check = True
        if author_id in exempt_users_from_ai_check: perform_content_check = False
        elif channel.id in exempt_channels_from_ai_check: perform_content_check = False
        
        if perform_content_check:
            # --- 3a. DeepSeek API 内容审查 (使用你原有的 check_message_with_deepseek) ---
            # 这个函数使用全局的 DEEPSEEK_MODEL (你为审查配置的那个)
            violation_type_from_api_check = await check_message_with_deepseek(message.content) # 重命名变量以避免冲突
            if violation_type_from_api_check:
                print(f"[OnMessage] VIOLATION (API Content Check): User {author_id} in #{channel.name}. Type: {violation_type_from_api_check}")
                delete_success = False
                try:
                    if channel.permissions_for(guild.me).manage_messages:
                        await message.delete()
                        delete_success = True
                        print(f"   - Deleted message (API Violation) by {author_id}")
                except Exception as del_e: print(f"   - Error deleting message (API violation): {del_e}")
                
                mod_mentions = " ".join([f"<@&{role_id}>" for role_id in MOD_ALERT_ROLE_IDS])
                log_embed_api = discord.Embed(title=f"🚨 自动内容审核 ({violation_type_from_api_check}) 🚨", color=discord.Color.dark_red(), timestamp=now)
                log_embed_api.add_field(name="用户", value=f"{author.mention} ({author_id})", inline=False)
                log_embed_api.add_field(name="频道", value=channel.mention, inline=False)
                log_embed_api.add_field(name="内容摘要", value=f"```{message.content[:1000]}```", inline=False)
                log_embed_api.add_field(name="消息状态", value="已删除" if delete_success else "删除失败/无权限", inline=True)
                log_embed_api.add_field(name="消息链接", value=f"[原始链接]({message.jump_url}) (可能已删除)", inline=True)
                log_embed_api.add_field(name="建议操作", value=f"{mod_mentions} 请管理员审核！", inline=False)
                await send_to_public_log(guild, log_embed_api, log_type=f"API Violation ({violation_type_from_api_check})")
                return 

            # --- 3b. 本地违禁词检测 (如果API未检测到严重违规) ---
            if not violation_type_from_api_check and BAD_WORDS_LOWER: 
                content_lower = message.content.lower()
                triggered_bad_word = None
                for word_bw in BAD_WORDS_LOWER: # 避免与外层 word 冲突
                    if word_bw in content_lower:
                        triggered_bad_word = word_bw
                        break
                if triggered_bad_word:
                    print(f"[OnMessage] VIOLATION (Local Bad Word): '{triggered_bad_word}' from {author_id} in #{channel.name}")
                    guild_offenses = user_first_offense_reminders.setdefault(guild.id, {})
                    user_offenses = guild_offenses.setdefault(author_id, set())

                    if triggered_bad_word not in user_offenses: 
                        user_offenses.add(triggered_bad_word)
                        print(f"   - '{triggered_bad_word}' is first offense for user {author_id}, sending reminder.")
                        try:
                            rules_ch_id = 1280026139326283799 # 你定义的规则频道ID
                            rules_ch_mention = f"<#{rules_ch_id}>" if rules_ch_id and rules_ch_id != 1280026139326283799 else "#规则" # 修正ID比较
                            await channel.send(
                                f"{author.mention}，请注意你的言辞并遵守服务器规则 ({rules_ch_mention})。本次仅为提醒，再犯将可能受到警告。",
                                delete_after=25
                            )
                        except Exception as remind_err: print(f"   - Error sending bad word reminder: {remind_err}")
                        try:
                            if channel.permissions_for(guild.me).manage_messages: await message.delete()
                        except Exception: pass 
                        return 
                    else: 
                        print(f"   - '{triggered_bad_word}' is repeat offense for user {author_id}, issuing warning.")
                        reason_bw_warn = f"自动警告：再次使用不当词语 '{triggered_bad_word}'"
                        
                        if author_id not in user_warnings: user_warnings[author_id] = 0 # 初始化
                        user_warnings[author_id] += 1
                        warning_count_bw = user_warnings[author_id]
                        print(f"   - User {author_id} current warnings: {warning_count_bw}/{KICK_THRESHOLD}")

                        warn_embed_bw = discord.Embed(color=discord.Color.orange(), timestamp=now)
                        # ... (构建你的 warn_embed_bw，包括踢出逻辑，与你原来代码一致) ...
                        # 例如:
                        warn_embed_bw.set_author(name=f"自动警告发出 (不当言语)", icon_url=bot.user.display_avatar.url if bot.user.avatar else None)
                        warn_embed_bw.add_field(name="用户", value=f"{author.mention} ({author_id})", inline=False)
                        warn_embed_bw.add_field(name="原因", value=reason_bw_warn, inline=False)
                        warn_embed_bw.add_field(name="当前警告次数", value=f"{warning_count_bw}/{KICK_THRESHOLD}", inline=False)
                        warn_embed_bw.add_field(name="触发消息", value=f"[{message.content[:50]}...]({message.jump_url})", inline=False)
                        
                        kick_performed_bad_word = False
                        if warning_count_bw >= KICK_THRESHOLD:
                            warn_embed_bw.title = "🚨 警告已达上限 - 自动踢出 (不当言语) 🚨"
                            warn_embed_bw.color = discord.Color.red()
                            # ... (你的踢出逻辑) ...
                            if member and guild.me.guild_permissions.kick_members and (guild.me.top_role > member.top_role or guild.me == guild.owner):
                                try:
                                    await member.kick(reason=f"自动踢出: 不当言语警告达上限 ({triggered_bad_word})")
                                    kick_performed_bad_word = True
                                    user_warnings[author_id] = 0 # 重置警告
                                    warn_embed_bw.add_field(name="踢出状态",value="✅ 成功", inline=False)
                                    print(f"   - User {author_id} kicked for bad words.")
                                except Exception as kick_e_bw:
                                    warn_embed_bw.add_field(name="踢出状态",value=f"❌ 失败 ({kick_e_bw})", inline=False)
                                    print(f"   - Failed to kick user {author_id} for bad words: {kick_e_bw}")
                            else:
                                warn_embed_bw.add_field(name="踢出状态",value="❌ 失败 (权限/层级不足)", inline=False)


                        await send_to_public_log(guild, warn_embed_bw, log_type="Auto Warn (Bad Word)")
                        try:
                            if channel.permissions_for(guild.me).manage_messages: await message.delete()
                        except Exception: pass
                        if not kick_performed_bad_word:
                            try:
                                await channel.send(f"⚠️ {author.mention}，你的言论再次触发警告 (不当言语)。当前警告次数: {warning_count_bw}/{KICK_THRESHOLD}", delete_after=20)
                            except Exception as e_chan_warn: print(f"   - Error sending channel warning for bad word: {e_chan_warn}")
                        return 

    # --- 4. 用户刷屏检测逻辑 ---
    if not is_mod_or_admin: # 通常刷屏检测也豁免管理员
        user_message_timestamps.setdefault(author_id, deque(maxlen=SPAM_COUNT_THRESHOLD + 5)) # 使用 deque
        if author_id not in user_warnings: user_warnings[author_id] = 0 # 初始化

        current_time_dt_spam = datetime.datetime.now(datetime.timezone.utc) 
        user_message_timestamps[author_id].append(current_time_dt_spam) 
        
        time_limit_user_spam = current_time_dt_spam - datetime.timedelta(seconds=SPAM_TIME_WINDOW_SECONDS)
        
        # 计算在时间窗口内的消息数量
        recent_messages_count = sum(1 for ts in user_message_timestamps[author_id] if ts > time_limit_user_spam)

        if recent_messages_count >= SPAM_COUNT_THRESHOLD:
            print(f"[OnMessage] SPAM (User): {author_id} in #{channel.name}")
            user_warnings[author_id] += 1 
            warning_count_spam = user_warnings[author_id]
            print(f"   - User {author_id} current warnings (spam): {warning_count_spam}/{KICK_THRESHOLD}")
            
            # 清空该用户的记录以避免连续触发，或者只移除最旧的几个
            user_message_timestamps[author_id].clear() # 简单粗暴清空

            log_embed_user_spam = discord.Embed(color=discord.Color.orange(), timestamp=now)
            # ... (构建你的 log_embed_user_spam，包括踢出逻辑，与你原来代码一致) ...
            log_embed_user_spam.set_author(name=f"自动警告发出 (用户刷屏)", icon_url=bot.user.display_avatar.url if bot.user.avatar else None)
            log_embed_user_spam.add_field(name="用户", value=f"{author.mention} ({author_id})", inline=False)
            # ... (其他字段和踢出逻辑) ...
            kick_performed_spam = False
            if warning_count_spam >= KICK_THRESHOLD:
                log_embed_user_spam.title = "🚨 警告已达上限 - 自动踢出 (用户刷屏) 🚨"
                # ... (你的踢出逻辑) ...
                if member and guild.me.guild_permissions.kick_members and (guild.me.top_role > member.top_role or guild.me == guild.owner):
                    try:
                        await member.kick(reason="自动踢出: 刷屏警告达上限")
                        kick_performed_spam = True
                        user_warnings[author_id] = 0
                        log_embed_user_spam.add_field(name="踢出状态", value="✅ 成功", inline=False)
                        print(f"   - User {author_id} kicked for spam.")
                    except Exception as kick_e_spam:
                         log_embed_user_spam.add_field(name="踢出状态", value=f"❌ 失败 ({kick_e_spam})", inline=False)
                         print(f"   - Failed to kick {author_id} for spam: {kick_e_spam}")
                else:
                    log_embed_user_spam.add_field(name="踢出状态", value="❌ 失败 (权限/层级不足)", inline=False)


            await send_to_public_log(guild, log_embed_user_spam, log_type="Auto Warn (User Spam)")
            if not kick_performed_spam:
                try:
                    await message.channel.send(f"⚠️ {author.mention}，检测到你发送消息过于频繁，请减缓速度！(警告 {warning_count_spam}/{KICK_THRESHOLD})", delete_after=15)
                except Exception as warn_err_spam: print(f"   - Error sending user spam warning: {warn_err_spam}")
            return 

                # --- 经济系统：聊天赚钱 (在末尾添加此部分) ---
    if ECONOMY_ENABLED and \
       message.guild and \
       not message.author.bot and \
       not message.content.startswith(COMMAND_PREFIX) and \
       not message.content.startswith('/') and \
       not (message.channel.id in ai_dep_channels_config or message.channel.id in active_private_ai_chats):
        # 仅对实际内容（不仅仅是短消息或没有文本的贴纸）进行奖励
        if len(message.content) > 5 or message.attachments or message.stickers: # 最小长度或包含媒体
            guild_id = message.guild.id
            user_id = message.author.id
            
            config = get_guild_chat_earn_config(guild_id)
            earn_amount = config["amount"]
            cooldown_seconds = config["cooldown"]

            if earn_amount > 0:
                now = time.time()
                
                if guild_id not in last_chat_earn_times:
                    last_chat_earn_times[guild_id] = {}
                
                last_earn = last_chat_earn_times[guild_id].get(user_id, 0)

                if now - last_earn > cooldown_seconds:
                    if update_user_balance(guild_id, user_id, earn_amount):
                        last_chat_earn_times[guild_id][user_id] = now
                        # print(f"[经济系统] 用户 {user_id} 在服务器 {guild_id} 通过聊天赚取了 {earn_amount} {ECONOMY_CURRENCY_NAME}。")
                        # 可选：发送非常细微的确认或记录，但避免刷屏聊天
                        # await message.add_reaction("🪙") # 示例：细微的反应 - 可能过多
                        # save_economy_data() # 每次赚钱都保存可能导致 I/O 过于密集。
    
    # --- (如果你在末尾有 bot.process_commands(message)，请保留它) ---
    # pass # 如果没有 process_commands

    # --- 5. Bot 刷屏检测逻辑 (如果需要，并且确保它在你原有逻辑中是工作的) ---
    # 注意：这个逻辑块通常应该在 on_message 的最开始处理，因为它只针对其他机器人。
    # 但为了保持你原有结构的顺序，我先放在这里。如果你的机器人不应该响应其他机器人刷屏，
    # 那么在文件开头的 if message.author.bot: return 就可以处理。
    # 如果你需要检测其他机器人刷屏并采取行动，这里的逻辑需要被激活并仔细测试。
    
    # if message.author.bot and message.author.id != bot.user.id: # 已在开头排除自己
    #     bot_author_id = message.author.id
    #     bot_message_timestamps.setdefault(bot_author_id, deque(maxlen=BOT_SPAM_COUNT_THRESHOLD + 5))
    #     current_time_dt_bot_spam = datetime.datetime.now(datetime.timezone.utc)
    #     bot_message_timestamps[bot_author_id].append(current_time_dt_bot_spam)
        
    #     time_limit_bot_spam = current_time_dt_bot_spam - datetime.timedelta(seconds=BOT_SPAM_TIME_WINDOW_SECONDS)
    #     recent_bot_messages_count = sum(1 for ts in bot_message_timestamps[bot_author_id] if ts > time_limit_bot_spam)

    #     if recent_bot_messages_count >= BOT_SPAM_COUNT_THRESHOLD:
    #         print(f"[OnMessage] SPAM (Bot): {bot_author_id} in #{channel.name}")
    #         bot_message_timestamps[bot_author_id].clear()
    #         # ... (你原来的机器人刷屏处理逻辑，例如发送警告给管理员，尝试踢出或移除权限) ...
    #         return

    # 如果消息未被以上任何一个特定逻辑处理
    # 并且你还使用了旧的前缀命令，可以在这里处理 (通常现在不推荐与斜杠命令混用)
    # if message.content.startswith(COMMAND_PREFIX):
    #    await bot.process_commands(message)
    pass
# --- (on_message 函数定义结束) ---


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
            owner_overwrites = discord.PermissionOverwrite(manage_channels=True, manage_permissions=True, move_members=True, connect=True, speak=True, stream=True, use_voice_activation=True, priority_speaker=True, mute_members=True, deafen_members=True, use_embedded_activities=True)
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
            "`/unwarn [用户] [原因]` - 移除用户一次警告\n"  # <--- 确保这里有换行符
            "`/notify_member [用户] [消息内容]` - 通过机器人向指定成员发送私信。" # <--- 新增这行
        ),
        inline=False
    )

    embed.add_field(
        name="🕵️ 匿名中介私信 (/relaymsg ...)",
        value=(
            "`... send [目标用户] [消息]` - 通过机器人向指定成员发送匿名消息。\n"
            "*接收方可以直接回复机器人私信，回复将被转发回你发起命令的频道。*"
            # 如果未来添加频道内回复功能，可以在此补充
        ),
        inline=False
    )

    # AI 对话与知识库
    embed.add_field(
        name="🤖 AI 对话与知识库 (/ai ...)", # 更新字段标题
        value=(
            "`... setup_dep_channel [频道] [模型] [系统提示]` - 设置AI直接对话频道\n"
            "`... clear_dep_history` - 清除当前AI频道对话历史\n"
            "`... create_private_chat [模型] [初始问题]` - 创建AI私聊频道\n"
            "`... close_private_chat` - 关闭你的AI私聊频道\n"
            "**AI知识库管理 (管理员):**\n" # 新增小标题
            "`... kb_add [内容]` - 添加知识到AI知识库\n"
            "`... kb_list` - 查看AI知识库条目\n"
            "`... kb_remove [序号]` - 移除指定知识条目\n"
            "`... kb_clear` - 清空服务器AI知识库"
        ),
        inline=False
    )

    # FAQ/帮助系统
    embed.add_field(
        name="❓ FAQ/帮助 (/faq ...)",
        value=(
            "`... search [关键词]` - 搜索FAQ/帮助信息\n"
            "**管理员指令:**\n"
            "`... add [关键词] [答案]` - 添加新的FAQ条目\n"
            "`... remove [关键词]` - 移除FAQ条目\n"
            "`... list` - 列出所有FAQ关键词"
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


    # --- 将经济系统指令添加到帮助信息 ---
    embed.add_field(
        name=f"{ECONOMY_CURRENCY_SYMBOL} {ECONOMY_CURRENCY_NAME}系统 (/eco ...)",
        value=(
            f"`... balance ([用户])` - 查看你或他人的{ECONOMY_CURRENCY_NAME}余额。\n"
            f"`... transfer <用户> <金额>` - 向其他用户转账{ECONOMY_CURRENCY_NAME}。\n"
            f"`... shop` - 查看商店中的可用物品。\n"
            f"`... buy <物品名称或ID>` - 从商店购买物品。\n"
            f"`... leaderboard` - 显示{ECONOMY_CURRENCY_NAME}排行榜。"
        ),
        inline=False
    )

    embed.add_field(
        name="⚙️ 高级管理指令 (/管理 ...)",
        value=(
            "`... 票据设定 ...`\n" # 保持此项简洁
            # ... (其他现有的管理员指令) ...
            f"`... eco_admin give <用户> <金额>` - 给予用户{ECONOMY_CURRENCY_NAME}。\n"
            f"`... eco_admin take <用户> <金额>` - 移除用户{ECONOMY_CURRENCY_NAME}。\n"
            f"`... eco_admin set <用户> <金额>` - 设置用户{ECONOMY_CURRENCY_NAME}。\n"
            f"`... eco_admin config_chat_earn <金额> <冷却>` - 配置聊天收益。\n"
            f"`... eco_admin add_shop_item <名称> <价格> ...` - 添加商店物品。\n"
            f"`... eco_admin remove_shop_item <物品>` - 移除商店物品。\n"
            f"`... eco_admin edit_shop_item <物品> ...` - 编辑商店物品。"
            # ... (你现有的 /管理 帮助信息的其余部分) ...
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
    embed.add_field(
        name="ℹ️ 其他",
        value=(
            "`/help` - 显示此帮助信息\n"
            "`/ping` - 查看机器人与服务器的延迟"  # <--- 新增这行
        ),
        inline=False
    )

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
    # --- (在这里或类似位置添加以下代码) ---

@bot.tree.command(name="notify_member", description="通过机器人向指定成员发送私信 (需要管理服务器权限)。")
@app_commands.describe(
    member="要接收私信的成员。",
    message_content="要发送的私信内容。"
)
@app_commands.checks.has_permissions(manage_guild=True) # 只有拥有“管理服务器”权限的用户才能使用
async def slash_notify_member(interaction: discord.Interaction, member: discord.Member, message_content: str):
    guild = interaction.guild
    author = interaction.user
    await interaction.response.defer(ephemeral=True) # 回复设为临时，仅执行者可见

    if not guild:
        await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True)
        return
    if member.bot:
        await interaction.followup.send("❌ 不能向机器人发送私信。", ephemeral=True)
        return
    if member == author:
        await interaction.followup.send("❌ 你不能给自己发送私信。", ephemeral=True)
        return
    if len(message_content) > 1900: # Discord DM 限制为 2000，留一些余量
        await interaction.followup.send("❌ 消息内容过长 (最多约1900字符)。", ephemeral=True)
        return

    # 创建私信的 Embed 消息
    dm_embed = discord.Embed(
        title=f"来自服务器 {guild.name} 管理员的消息",
        description=message_content,
        color=discord.Color.blue(), # 你可以自定义颜色
        timestamp=discord.utils.utcnow()
    )
    dm_embed.set_footer(text=f"发送者: {author.display_name}")
    if author.avatar: # 如果发送者有头像，则使用
        dm_embed.set_author(name=f"来自 {author.display_name}", icon_url=author.display_avatar.url)
    else:
        dm_embed.set_author(name=f"来自 {author.display_name}")

    try:
        await member.send(embed=dm_embed)
        await interaction.followup.send(f"✅ 已成功向 {member.mention} 发送私信。", ephemeral=True)
        print(f"[通知] 用户 {author} ({author.id}) 通过机器人向 {member.name} ({member.id}) 发送了私信。")

        # （可选）在公共日志频道记录操作 (不记录具体内容，保护隐私)
        log_embed_public = discord.Embed(
            title="📬 成员私信已发送",
            description=f"管理员通过机器人向成员发送了一条私信。",
            color=discord.Color.blurple(), # 和私信颜色区分
            timestamp=discord.utils.utcnow()
        )
        log_embed_public.add_field(name="执行管理员", value=author.mention, inline=True)
        log_embed_public.add_field(name="接收成员", value=member.mention, inline=True)
        log_embed_public.set_footer(text=f"执行者 ID: {author.id} | 接收者 ID: {member.id}")
        await send_to_public_log(guild, log_embed_public, log_type="Member DM Sent")

    except discord.Forbidden:
        await interaction.followup.send(f"❌ 无法向 {member.mention} 发送私信。可能原因：该用户关闭了来自服务器成员的私信，或屏蔽了机器人。", ephemeral=True)
        print(f"[通知失败] 无法向 {member.name} ({member.id}) 发送私信 (Forbidden)。")
    except discord.HTTPException as e:
        await interaction.followup.send(f"❌ 发送私信给 {member.mention} 时发生网络错误: {e}", ephemeral=True)
        print(f"[通知失败] 发送私信给 {member.name} ({member.id}) 时发生HTTP错误: {e}")
    except Exception as e:
        await interaction.followup.send(f"❌ 发送私信时发生未知错误: {e}", ephemeral=True)
        print(f"[通知失败] 发送私信给 {member.name} ({member.id}) 时发生未知错误: {e}")
        # ... (你现有的 slash_notify_member 指令的完整代码) ...
    except Exception as e:
        await interaction.followup.send(f"❌ 发送私信时发生未知错误: {e}", ephemeral=True)
        print(f"[通知失败] 发送私信给 {member.name} ({member.id}) 时发生未知错误: {e}")


# ↓↓↓↓ 在这里粘贴新的 ping 指令的完整代码 ↓↓↓↓
@bot.tree.command(name="ping", description="检查机器人与 Discord 服务器的延迟。")
async def slash_ping(interaction: discord.Interaction):
    """显示机器人的延迟信息。"""
    # defer=True 使得交互立即得到响应，机器人有更多时间处理
    # ephemeral=True 使得这条消息只有发送者可见
    await interaction.response.defer(ephemeral=True)

    # 1. WebSocket 延迟 (机器人与Discord网关的连接延迟)
    websocket_latency = bot.latency
    websocket_latency_ms = round(websocket_latency * 1000)

    # 2. API 延迟 (发送一条消息并测量所需时间)
    # 我们将发送初始回复，然后编辑它来计算延迟
    start_time = time.monotonic()
    # 发送一个占位消息，后续会编辑它
    # 注意：因为我们已经 defer() 了，所以第一次发送必须用 followup()
    message_to_edit = await interaction.followup.send("正在 Ping API...", ephemeral=True)
    end_time = time.monotonic()
    api_latency_ms = round((end_time - start_time) * 1000)


    # 创建最终的 Embed 消息
    embed = discord.Embed(
        title="🏓 Pong!",
        color=discord.Color.green(), # 你可以自定义颜色
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="📡 WebSocket 延迟", value=f"{websocket_latency_ms} ms", inline=True)
    embed.add_field(name="↔️ API 消息延迟", value=f"{api_latency_ms} ms", inline=True)
    embed.set_footer(text=f"请求者: {interaction.user.display_name}")

    # 编辑之前的占位消息，显示完整的延迟信息
    await message_to_edit.edit(content=None, embed=embed)

    print(f"[状态] 用户 {interaction.user} 执行了 /ping。WebSocket: {websocket_latency_ms}ms, API: {api_latency_ms}ms")
# ↑↑↑↑ 新的 ping 指令代码结束 ↑↑↑↑

# ... (在你现有的 /ping 命令或其他独立斜杠命令定义之后) ...

# --- 新增：AI 对话功能指令组 ---
ai_group = app_commands.Group(name="ai", description="与 DeepSeek AI 交互的指令")

# --- Command: /ai setup_dep_channel ---
@ai_group.command(name="setup_dep_channel", description="[管理员] 将当前频道或指定频道设置为AI直接对话频道")
@app_commands.describe(
    channel="要设置为AI对话的文字频道 (默认为当前频道)",
    model_id="(可选)为此频道指定AI模型 (默认使用通用对话模型)",
    system_prompt="(可选)为此频道设置一个系统级提示 (AI会优先考虑)"
)
@app_commands.choices(model_id=[
    app_commands.Choice(name=desc, value=mid) for mid, desc in AVAILABLE_AI_DIALOGUE_MODELS.items()
])
@app_commands.checks.has_permissions(manage_guild=True) 
async def ai_setup_dep_channel(interaction: discord.Interaction, 
                               channel: Optional[discord.TextChannel] = None, 
                               model_id: Optional[app_commands.Choice[str]] = None,
                               system_prompt: Optional[str] = None):
    target_channel = channel if channel else interaction.channel
    if not isinstance(target_channel, discord.TextChannel):
        await interaction.response.send_message("❌ 目标必须是一个文字频道。", ephemeral=True)
        return

    chosen_model_id = model_id.value if model_id else DEFAULT_AI_DIALOGUE_MODEL
    
    history_key_for_channel = f"ai_dep_channel_{target_channel.id}"
    ai_dep_channels_config[target_channel.id] = {
        "model": chosen_model_id,
        "system_prompt": system_prompt,
        "history_key": history_key_for_channel
    }
    if history_key_for_channel not in conversation_histories:
        conversation_histories[history_key_for_channel] = deque(maxlen=MAX_AI_HISTORY_TURNS * 2) 

    print(f"[AI SETUP] Channel {target_channel.name} ({target_channel.id}) configured for AI. Model: {chosen_model_id}, SysPrompt: {system_prompt is not None}")
    await interaction.response.send_message(
        f"✅ 频道 {target_channel.mention} 已成功设置为 AI 直接对话频道！\n"
        f"- 使用模型: `{chosen_model_id}`\n"
        f"- 系统提示: `{'已设置' if system_prompt else '未使用'}`\n"
        f"用户现在可以在此频道直接向 AI提问。",
        ephemeral=True
    )

@ai_setup_dep_channel.error
async def ai_setup_dep_channel_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("🚫 你需要“管理服务器”权限才能设置AI频道。", ephemeral=True)
    else:
        print(f"[AI SETUP ERROR] /ai setup_dep_channel: {error}")
        await interaction.response.send_message(f"设置AI频道时发生错误: {type(error).__name__}", ephemeral=True)

# --- Command: /ai kb_add ---
@ai_group.command(name="kb_add", description="[管理员] 添加一条知识到服务器的AI知识库")
@app_commands.describe(content="要添加的知识内容 (例如：服务器规则、常见问题解答)")
@app_commands.checks.has_permissions(manage_guild=True)
async def ai_kb_add(interaction: discord.Interaction, content: str):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("此命令只能在服务器内使用。", ephemeral=True)
        return

    if len(content) > MAX_KB_ENTRY_LENGTH: # 使用之前定义的常量
        await interaction.response.send_message(f"❌ 内容过长，单个知识条目不能超过 {MAX_KB_ENTRY_LENGTH} 个字符。", ephemeral=True)
        return
    if len(content.strip()) < 10: 
        await interaction.response.send_message(f"❌ 内容过短，请输入有意义的知识条目 (至少10字符)。", ephemeral=True)
        return

    # 确保 guild_knowledge_bases 已在文件顶部定义
    guild_kb = guild_knowledge_bases.setdefault(guild.id, [])
    if len(guild_kb) >= MAX_KB_ENTRIES_PER_GUILD: # 使用之前定义的常量
        await interaction.response.send_message(f"❌ 服务器知识库已满 ({len(guild_kb)}/{MAX_KB_ENTRIES_PER_GUILD} 条)。请先移除一些旧条目。", ephemeral=True)
        return

    guild_kb.append(content.strip())
    print(f"[AI KB] Guild {guild.id}: User {interaction.user.id} added entry. New count: {len(guild_kb)}")
    await interaction.response.send_message(f"✅ 已成功添加知识条目到服务器AI知识库 (当前共 {len(guild_kb)} 条)。\n内容预览: ```{content[:150]}{'...' if len(content)>150 else ''}```", ephemeral=True)

# --- Command: /ai kb_list ---
@ai_group.command(name="kb_list", description="[管理员] 列出当前服务器AI知识库中的条目")
@app_commands.checks.has_permissions(manage_guild=True)
async def ai_kb_list(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("此命令只能在服务器内使用。", ephemeral=True)
        return

    guild_kb = guild_knowledge_bases.get(guild.id, [])
    if not guild_kb:
        await interaction.response.send_message("ℹ️ 当前服务器的AI知识库是空的。", ephemeral=True)
        return

    embed = discord.Embed(title=f"服务器AI知识库 - {guild.name}", color=discord.Color.blue(), timestamp=discord.utils.utcnow())
    
    description_parts = [f"当前共有 **{len(guild_kb)}** 条知识。显示前 {min(len(guild_kb), MAX_KB_DISPLAY_ENTRIES)} 条：\n"] # 使用常量
    for i, entry in enumerate(guild_kb[:MAX_KB_DISPLAY_ENTRIES]): # 使用常量
        preview = entry[:80] + ('...' if len(entry) > 80 else '') 
        description_parts.append(f"**{i+1}.** ```{preview}```")
    
    if len(guild_kb) > MAX_KB_DISPLAY_ENTRIES: # 使用常量
        description_parts.append(f"\n*还有 {len(guild_kb) - MAX_KB_DISPLAY_ENTRIES} 条未在此处完整显示。*")
    
    embed.description = "\n".join(description_parts)
    embed.set_footer(text=f"使用 /ai kb_remove [序号] 来移除条目。")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Command: /ai kb_remove ---
@ai_group.command(name="kb_remove", description="[管理员] 从服务器AI知识库中移除指定序号的条目")
@app_commands.describe(index="要移除的知识条目的序号 (从 /ai kb_list 中获取)")
@app_commands.checks.has_permissions(manage_guild=True)
async def ai_kb_remove(interaction: discord.Interaction, index: int):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("此命令只能在服务器内使用。", ephemeral=True)
        return

    guild_kb = guild_knowledge_bases.get(guild.id, [])
    if not guild_kb:
        await interaction.response.send_message("ℹ️ 当前服务器的AI知识库是空的，无法移除。", ephemeral=True)
        return

    if not (1 <= index <= len(guild_kb)):
        await interaction.response.send_message(f"❌ 无效的序号。请输入 1 到 {len(guild_kb)} 之间的数字。", ephemeral=True)
        return

    removed_entry = guild_kb.pop(index - 1) 
    print(f"[AI KB] Guild {guild.id}: User {interaction.user.id} removed entry #{index}. New count: {len(guild_kb)}")
    await interaction.response.send_message(f"✅ 已成功从知识库中移除第 **{index}** 条知识。\n被移除内容预览: ```{removed_entry[:150]}{'...' if len(removed_entry)>150 else ''}```", ephemeral=True)

# --- Command: /ai kb_clear ---
@ai_group.command(name="kb_clear", description="[管理员] 清空当前服务器的所有AI知识库条目")
@app_commands.checks.has_permissions(manage_guild=True)
async def ai_kb_clear(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("此命令只能在服务器内使用。", ephemeral=True)
        return

    if guild.id in guild_knowledge_bases and guild_knowledge_bases[guild.id]:
        count_cleared = len(guild_knowledge_bases[guild.id])
        guild_knowledge_bases[guild.id] = [] 
        print(f"[AI KB] Guild {guild.id}: User {interaction.user.id} cleared all {count_cleared} knowledge base entries.")
        await interaction.response.send_message(f"✅ 已成功清空服务器AI知识库中的全部 **{count_cleared}** 条知识。", ephemeral=True)
    else:
        await interaction.response.send_message("ℹ️ 当前服务器的AI知识库已经是空的。", ephemeral=True)
# --- Command: /ai clear_dep_history ---
@ai_group.command(name="clear_dep_history", description="清除当前AI直接对话频道的对话历史")
async def ai_clear_dep_history(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    if channel_id not in ai_dep_channels_config:
        await interaction.response.send_message("❌ 此频道未被设置为 AI 直接对话频道。", ephemeral=True)
        return

    config = ai_dep_channels_config[channel_id]
    history_key = config.get("history_key")

    if history_key and history_key in conversation_histories:
        conversation_histories[history_key].clear()
        print(f"[AI HISTORY] Cleared history for DEP channel {channel_id} (Key: {history_key}) by {interaction.user.id}")
        await interaction.response.send_message("✅ 当前 AI 对话频道的历史记录已清除。", ephemeral=False) 
    else:
        await interaction.response.send_message("ℹ️ 未找到此频道的历史记录或历史键配置错误。", ephemeral=True)

# --- Command: /ai create_private_chat ---
@ai_group.command(name="create_private_chat", description="创建一个与AI的私密聊天频道")
@app_commands.describe(
    model_id="(可选)为私聊指定AI模型",
    initial_question="(可选)创建频道后直接向AI提出的第一个问题"
)
@app_commands.choices(model_id=[
    app_commands.Choice(name=desc, value=mid) for mid, desc in AVAILABLE_AI_DIALOGUE_MODELS.items()
])
async def ai_create_private_chat(interaction: discord.Interaction, 
                                 model_id: Optional[app_commands.Choice[str]] = None,
                                 initial_question: Optional[str] = None):
    user = interaction.user
    guild = interaction.guild
    if not guild: 
        await interaction.response.send_message("此命令似乎不在服务器中执行。", ephemeral=True)
        return

    for chat_id_key, chat_info_val in list(active_private_ai_chats.items()): # Iterate over a copy for safe deletion
        if chat_info_val.get("user_id") == user.id and chat_info_val.get("guild_id") == guild.id:
            existing_channel = guild.get_channel(chat_info_val.get("channel_id"))
            if existing_channel:
                await interaction.response.send_message(f"⚠️ 你已经有一个开启的AI私聊频道：{existing_channel.mention}。\n请先使用 `/ai close_private_chat` 关闭它。", ephemeral=True)
                return
            else: 
                print(f"[AI PRIVATE] Cleaning up stale private chat record for user {user.id}, channel ID {chat_info_val.get('channel_id')}")
                if chat_info_val.get("history_key") in conversation_histories:
                    del conversation_histories[chat_info_val.get("history_key")]
                if chat_id_key in active_private_ai_chats: # chat_id_key is channel_id
                     del active_private_ai_chats[chat_id_key]


    chosen_model_id = model_id.value if model_id else DEFAULT_AI_DIALOGUE_MODEL
    
    await interaction.response.defer(ephemeral=True) 

    category_name_config = "AI Private Chats" # Name for the category
    category = discord.utils.get(guild.categories, name=category_name_config) 
    if not category:
        try:
            bot_member = guild.me
            bot_perms_in_cat = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, view_channel=True)
            everyone_perms_in_cat = discord.PermissionOverwrite(read_messages=False, view_channel=False)
            category_overwrites = {
                guild.me: bot_perms_in_cat,
                guild.default_role: everyone_perms_in_cat
            }
            category = await guild.create_category(category_name_config, overwrites=category_overwrites, reason="Category for AI Private Chats")
            print(f"[AI PRIVATE] Created category '{category_name_config}' in guild {guild.id}")
        except discord.Forbidden:
            print(f"[AI PRIVATE ERROR] Failed to create '{category_name_config}' category in {guild.id}: Bot lacks permissions.")
            await interaction.followup.send("❌ 创建私聊频道失败：机器人无法创建所需分类。请检查机器人是否有“管理频道”权限。", ephemeral=True)
            return
        except Exception as e:
            print(f"[AI PRIVATE ERROR] Error creating category: {e}")
            await interaction.followup.send(f"❌ 创建私聊频道失败：{e}", ephemeral=True)
            return

    channel_name = f"ai-{user.name[:20].lower().replace(' ','-')}-{user.id % 1000}" # Ensure lowercase and no spaces for channel name
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, embed_links=True, attach_files=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True, manage_messages=True) 
    }

    new_channel = None # Define before try block
    try:
        new_channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites, topic=f"AI私聊频道，创建者: {user.display_name}, 模型: {chosen_model_id}")
        
        history_key_private = f"ai_private_chat_{new_channel.id}"
        active_private_ai_chats[new_channel.id] = { # Use new_channel.id as the key
            "user_id": user.id,
            "model": chosen_model_id,
            "history_key": history_key_private,
            "guild_id": guild.id,
            "channel_id": new_channel.id 
        }
        if history_key_private not in conversation_histories:
            conversation_histories[history_key_private] = deque(maxlen=MAX_AI_HISTORY_TURNS * 2)

        print(f"[AI PRIVATE] Created private AI channel {new_channel.name} ({new_channel.id}) for user {user.id}. Model: {chosen_model_id}")
        
        initial_message_content = (
            f"你好 {user.mention}！这是一个你的专属AI私聊频道。\n"
            f"- 当前使用模型: `{chosen_model_id}`\n"
            f"- 直接在此输入你的问题即可与AI对话。\n"
            f"- 使用 `/ai close_private_chat` 可以关闭此频道。\n"
            f"Enjoy! ✨"
        )
        await new_channel.send(initial_message_content)
        await interaction.followup.send(f"✅ 你的AI私聊频道已创建：{new_channel.mention}", ephemeral=True)

        if initial_question: 
            print(f"[AI PRIVATE] Sending initial question from {user.id} to {new_channel.id}: {initial_question}")
            # Simulate a message object for handle_ai_dialogue
            # This is a bit hacky, a cleaner way might be to directly call API and format
            class MinimalMessage:
                def __init__(self, author, channel, content, guild):
                    self.author = author
                    self.channel = channel
                    self.content = content
                    self.guild = guild
                    self.attachments = [] # Assume no attachments for initial question
                    self.stickers = []  # Assume no stickers
                    # Add other attributes if your handle_ai_dialogue strict checks them
                    self.id = discord.utils.time_snowflake(discord.utils.utcnow()) # Fake ID
                    self.interaction = None # Not from an interaction

            mock_message_obj = MinimalMessage(author=user, channel=new_channel, content=initial_question, guild=guild)
            async with new_channel.typing():
                await handle_ai_dialogue(mock_message_obj, is_private_chat=True)

    except discord.Forbidden:
        print(f"[AI PRIVATE ERROR] Failed to create private channel for {user.id}: Bot lacks permissions.")
        await interaction.followup.send("❌ 创建私聊频道失败：机器人权限不足。", ephemeral=True)
        if new_channel and new_channel.id in active_private_ai_chats: # Clean up if entry was made
            del active_private_ai_chats[new_channel.id]
    except Exception as e:
        print(f"[AI PRIVATE ERROR] Error creating private channel: {e}")
        import traceback
        traceback.print_exc()
        await interaction.followup.send(f"❌ 创建私聊频道时发生未知错误: {type(e).__name__}", ephemeral=True)
        if new_channel and new_channel.id in active_private_ai_chats: # Clean up if entry was made
            del active_private_ai_chats[new_channel.id]


# --- Command: /ai close_private_chat ---
@ai_group.command(name="close_private_chat", description="关闭你创建的AI私密聊天频道")
async def ai_close_private_chat(interaction: discord.Interaction):
    channel = interaction.channel
    user = interaction.user

    if not (isinstance(channel, discord.TextChannel) and channel.id in active_private_ai_chats):
        await interaction.response.send_message("❌ 此命令只能在你创建的AI私密聊天频道中使用。", ephemeral=True)
        return

    chat_info = active_private_ai_chats.get(channel.id)
    if not chat_info or chat_info.get("user_id") != user.id:
        await interaction.response.send_message("❌ 你不是此AI私密聊天频道的创建者。", ephemeral=True)
        return

    # Deferring here might be an issue if channel is deleted quickly
    # await interaction.response.send_message("⏳ 频道准备关闭...", ephemeral=True) # Ephemeral response
    
    history_key_to_clear = chat_info.get("history_key")
    if history_key_to_clear and history_key_to_clear in conversation_histories:
        del conversation_histories[history_key_to_clear]
        print(f"[AI PRIVATE] Cleared history for private chat {channel.id} (Key: {history_key_to_clear}) during closure.")
    
    if channel.id in active_private_ai_chats:
        del active_private_ai_chats[channel.id]
        print(f"[AI PRIVATE] Removed active private chat entry for channel {channel.id}")

    try:
        # Send confirmation in channel before deleting
        await channel.send(f"此AI私密聊天频道由 {user.mention} 请求关闭，将在大约 5 秒后删除。")
        # Respond to interaction *before* sleep and delete
        await interaction.response.send_message("频道关闭请求已收到，将在几秒后删除。",ephemeral=True)
        await asyncio.sleep(5)
        await channel.delete(reason=f"AI Private Chat closed by owner {user.name}")
        print(f"[AI PRIVATE] Successfully deleted private AI channel {channel.name} ({channel.id})")
        try: # Attempt to DM user as a final confirmation
            await user.send(f"你创建的AI私聊频道 `#{channel.name}` 已成功关闭和删除。")
        except discord.Forbidden:
            print(f"[AI PRIVATE] Could not DM user {user.id} about channel closure.")
    except discord.NotFound:
        print(f"[AI PRIVATE] Channel {channel.id} already deleted before final action.")
        if not interaction.response.is_done(): # If we haven't responded yet
             await interaction.response.send_message("频道似乎已被删除。",ephemeral=True)
    except discord.Forbidden:
        print(f"[AI PRIVATE ERROR] Bot lacks permission to delete channel {channel.id} or send messages in it.")
        if not interaction.response.is_done():
             await interaction.response.send_message("❌ 关闭频道时出错：机器人权限不足。", ephemeral=True)
    except Exception as e:
        print(f"[AI PRIVATE ERROR] Error closing private chat {channel.id}: {e}")
        if not interaction.response.is_done():
             await interaction.response.send_message(f"❌ 关闭频道时发生未知错误: {type(e).__name__}", ephemeral=True)


# 将新的指令组添加到 bot tree
# 这个应该在你的 on_ready 或者 setup_hook 中进行一次性添加，或者在文件末尾（如果 bot.tree 已经定义）
# 为了确保它被添加，我们暂时放在这里，但理想位置是在所有指令定义完后，机器人启动前。
# 如果你已经在其他地方有 bot.tree.add_command(manage_group) 等，就和它们放在一起。
# bot.tree.add_command(ai_group) # 我们会在文件末尾统一添加

# --- (在你所有指令组如 manage_group, voice_group, ai_group 定义完成之后，但在 bot.tree.add_command 系列语句之前) ---

# --- 新增：FAQ/帮助 指令组 ---
faq_group = app_commands.Group(name="faq", description="服务器FAQ与帮助信息管理和查询")

# --- Command: /faq add ---
@faq_group.command(name="add", description="[管理员] 添加一个新的FAQ条目 (关键词和答案)")
@app_commands.describe(
    keyword="用户搜索时使用的关键词 (简短，唯一)",
    answer="对应关键词的答案/帮助信息"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def faq_add(interaction: discord.Interaction, keyword: str, answer: str):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("此命令只能在服务器内使用。", ephemeral=True)
        return

    keyword = keyword.lower().strip() 
    if not keyword:
        await interaction.response.send_message("❌ 关键词不能为空。", ephemeral=True)
        return
    if len(keyword) > MAX_FAQ_KEYWORD_LENGTH: # 使用之前定义的常量
        await interaction.response.send_message(f"❌ 关键词过长 (最多 {MAX_FAQ_KEYWORD_LENGTH} 字符)。", ephemeral=True)
        return
    if len(answer) > MAX_FAQ_ANSWER_LENGTH: # 使用之前定义的常量
        await interaction.response.send_message(f"❌ 答案内容过长 (最多 {MAX_FAQ_ANSWER_LENGTH} 字符)。", ephemeral=True)
        return
    if len(answer.strip()) < 10:
         await interaction.response.send_message(f"❌ 答案内容过短 (至少10字符)。", ephemeral=True)
         return

    # 确保 server_faqs 已在文件顶部定义
    guild_faqs = server_faqs.setdefault(guild.id, {})
    if keyword in guild_faqs:
        await interaction.response.send_message(f"⚠️ 关键词 **'{keyword}'** 已存在。如需修改，请先移除旧条目。", ephemeral=True)
        return
    if len(guild_faqs) >= MAX_FAQ_ENTRIES_PER_GUILD: # 使用之前定义的常量
        await interaction.response.send_message(f"❌ 服务器FAQ条目已达上限 ({len(guild_faqs)}/{MAX_FAQ_ENTRIES_PER_GUILD} 条)。", ephemeral=True)
        return

    guild_faqs[keyword] = answer.strip()
    print(f"[FAQ] Guild {guild.id}: User {interaction.user.id} added FAQ for keyword '{keyword}'.")
    await interaction.response.send_message(f"✅ FAQ 条目已添加！\n关键词: **{keyword}**\n答案预览: ```{answer[:150]}{'...' if len(answer)>150 else ''}```", ephemeral=True)

# --- Command: /faq remove ---
@faq_group.command(name="remove", description="[管理员] 移除一个FAQ条目")
@app_commands.describe(keyword="要移除的FAQ条目的关键词")
@app_commands.checks.has_permissions(manage_guild=True)
async def faq_remove(interaction: discord.Interaction, keyword: str):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("此命令只能在服务器内使用。", ephemeral=True)
        return

    keyword = keyword.lower().strip()
    guild_faqs = server_faqs.get(guild.id, {})

    if keyword not in guild_faqs:
        await interaction.response.send_message(f"❌ 未找到关键词为 **'{keyword}'** 的FAQ条目。", ephemeral=True)
        return

    removed_answer = guild_faqs.pop(keyword)
    if not guild_faqs: 
        if guild.id in server_faqs:
            del server_faqs[guild.id]

    print(f"[FAQ] Guild {guild.id}: User {interaction.user.id} removed FAQ for keyword '{keyword}'.")
    await interaction.response.send_message(f"✅ 已成功移除关键词为 **'{keyword}'** 的FAQ条目。\n被移除答案预览: ```{removed_answer[:150]}{'...' if len(removed_answer)>150 else ''}```", ephemeral=True)

# --- Command: /faq list ---
@faq_group.command(name="list", description="[管理员] 列出所有FAQ关键词和部分答案")
@app_commands.checks.has_permissions(manage_guild=True) 
async def faq_list(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("此命令只能在服务器内使用。", ephemeral=True)
        return

    guild_faqs = server_faqs.get(guild.id, {})
    if not guild_faqs:
        await interaction.response.send_message("ℹ️ 当前服务器的FAQ列表是空的。", ephemeral=True)
        return

    embed = discord.Embed(title=f"服务器FAQ列表 - {guild.name}", color=discord.Color.teal(), timestamp=discord.utils.utcnow())
    
    description_parts = [f"当前共有 **{len(guild_faqs)}** 条FAQ。显示前 {min(len(guild_faqs), MAX_FAQ_LIST_DISPLAY)} 条：\n"] # 使用常量
    count = 0
    for kw, ans in guild_faqs.items():
        if count >= MAX_FAQ_LIST_DISPLAY: # 使用常量
            break
        ans_preview = ans[:60] + ('...' if len(ans) > 60 else '')
        description_parts.append(f"🔑 **{kw}**: ```{ans_preview}```")
        count += 1
    
    if len(guild_faqs) > MAX_FAQ_LIST_DISPLAY: # 使用常量
        description_parts.append(f"\n*还有 {len(guild_faqs) - MAX_FAQ_LIST_DISPLAY} 条未在此处完整显示。*")
    
    embed.description = "\n".join(description_parts)
    embed.set_footer(text="用户可使用 /faq search <关键词> 来查询。")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Command: /faq search (对所有用户开放) ---
@faq_group.command(name="search", description="搜索FAQ/帮助信息")
@app_commands.describe(keyword="你想要查询的关键词")
async def faq_search(interaction: discord.Interaction, keyword: str):
    guild = interaction.guild
    if not guild: 
        await interaction.response.send_message("此命令似乎不在服务器中执行。", ephemeral=True)
        return

    keyword = keyword.lower().strip()
    guild_faqs = server_faqs.get(guild.id, {})

    if not guild_faqs:
        await interaction.response.send_message("ℹ️ 本服务器尚未配置FAQ信息。", ephemeral=True)
        return

    answer = guild_faqs.get(keyword)

    if not answer:
        possible_matches = []
        for kw, ans_val in guild_faqs.items():
            if keyword in kw or kw in keyword: 
                possible_matches.append((kw, ans_val))
        
        if len(possible_matches) == 1: 
            answer = possible_matches[0][1]
            keyword = possible_matches[0][0] 
        elif len(possible_matches) > 1:
            match_list_str = "\n".join([f"- `{match[0]}`" for match in possible_matches[:5]]) 
            await interaction.response.send_message(f"🤔 找到了多个可能的匹配项，请尝试更精确的关键词：\n{match_list_str}", ephemeral=True)
            return

    if answer:
        embed = discord.Embed(
            title=f"💡 FAQ: {keyword.capitalize()}",
            description=answer,
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"由 {guild.name} 提供")
        await interaction.response.send_message(embed=embed, ephemeral=False) 
    else:
        await interaction.response.send_message(f"😕 未找到与 **'{keyword}'**相关的FAQ信息。请尝试其他关键词或联系管理员。", ephemeral=True)

# --- FAQ/帮助 指令组结束 ---

# --- (在你其他指令组如 manage_group, ai_group, faq_group 定义完成之后) ---

relay_msg_group = app_commands.Group(name="relaymsg", description="服务器内匿名中介私信功能")

@relay_msg_group.command(name="send", description="向服务器内另一位成员发送一条匿名消息。")
@app_commands.describe(
    target_user="你要向其发送匿名消息的成员。",
    message="你要发送的消息内容。"
)
async def relay_msg_send(interaction: discord.Interaction, target_user: discord.Member, message: str):
    await interaction.response.defer(ephemeral=True) # 初始响应对发起者临时可见

    guild = interaction.guild
    initiator = interaction.user # 发起者

    if not guild:
        await interaction.followup.send("❌ 此命令只能在服务器频道中使用。", ephemeral=True)
        return
    if target_user.bot:
        await interaction.followup.send("❌ 不能向机器人发送匿名消息。", ephemeral=True)
        return
    if target_user == initiator:
        await interaction.followup.send("❌ 你不能给自己发送匿名消息。", ephemeral=True)
        return
    
    # 可选：检查发起者是否有权使用此功能
    if ANONYMOUS_RELAY_ALLOWED_ROLE_IDS:
        can_use = False
        if isinstance(initiator, discord.Member):
            for role_id in ANONYMOUS_RELAY_ALLOWED_ROLE_IDS:
                if discord.utils.get(initiator.roles, id=role_id):
                    can_use = True
                    break
        if not can_use:
            await interaction.followup.send("🚫 你没有权限使用此功能。", ephemeral=True)
            return

    if len(message) > 1800: # 留一些空间给机器人的提示信息
        await interaction.followup.send("❌ 消息内容过长 (最多约1800字符)。", ephemeral=True)
        return

    dm_embed = discord.Embed(
        title=f"✉️ 一条来自 {guild.name} 的消息",
        description=f"```\n{message}\n```\n\n"
                    f"ℹ️ 这是一条通过服务器机器人转发的消息。\n"
                    f"你可以直接在此私信中 **回复这条消息** 来回应，你的回复也会通过机器人转发。\n"
                    f"*(你的身份对消息来源者是可见的，但消息来源者的身份对你是匿名的)*", # 或者调整匿名性措辞
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    dm_embed.set_footer(text=f"消息来自服务器: {guild.name}")

    try:
        sent_dm_message = await target_user.send(embed=dm_embed)
        # 记录这个会话，使用机器人发送的DM消息ID作为键
        ANONYMOUS_RELAY_SESSIONS[sent_dm_message.id] = {
            "initiator_id": initiator.id,
            "target_id": target_user.id,
            "original_channel_id": interaction.channel_id, # 记录发起命令的频道
            "guild_id": guild.id,
            "initiator_display_name": initiator.display_name # 用于在频道内显示谁发起了对某人的匿名消息
        }
        await interaction.followup.send(f"✅ 你的匿名消息已通过机器人发送给 {target_user.mention}。请等待对方在私信中回复。", ephemeral=True)
        print(f"[RelayMsg] Initiator {initiator.id} sent message to Target {target_user.id} via DM {sent_dm_message.id}. Original channel: {interaction.channel_id}")

    except discord.Forbidden:
        await interaction.followup.send(f"❌ 无法向 {target_user.mention} 发送私信。对方可能关闭了私信或屏蔽了机器人。", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ 发送私信时发生错误: {e}", ephemeral=True)
        print(f"[RelayMsg ERROR] Sending DM to {target_user.id}: {e}")

# 将新的指令组添加到 bot tree (这会在文件末尾统一做)

# --- Management Command Group Definitions ---
# manage_group = app_commands.Group(...)
# ... (你现有的 manage_group 指令)

# --- Management Command Group Definitions ---
manage_group = app_commands.Group(name="管理", description="服务器高级管理相关指令 (需要相应权限)")
# ... (后续的 manage_group 指令组代码) ...


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

    # --- 新增：重启机器人指令 ---
@manage_group.command(name="restart", description="[服主专用] 重启机器人 (需要密码)。")
@app_commands.describe(password="重启机器人所需的密码。")
async def manage_restart_bot(interaction: discord.Interaction, password: str):
    # 确保只有服务器所有者能执行
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("🚫 只有服务器所有者才能重启机器人。", ephemeral=True)
        return

    if not RESTART_PASSWORD:
        await interaction.response.send_message("⚙️ 重启功能未配置密码，无法执行。", ephemeral=True)
        print("⚠️ /管理 restart: RESTART_PASSWORD 未设置，无法执行。")
        return

    if password == RESTART_PASSWORD:
        await interaction.response.send_message("✅ 收到重启指令。机器人将尝试关闭并等待外部进程重启...", ephemeral=True)
        print(f"机器人重启由 {interaction.user.name} ({interaction.user.id}) 发起。")

        # 准备日志 Embed
        log_embed_restart = discord.Embed(title="🤖 机器人重启中...",
                                  description=f"由 {interaction.user.mention} 发起。\n机器人将很快关闭，请等待外部服务（如systemd）自动重启。",
                                  color=discord.Color.orange(),
                                  timestamp=discord.utils.utcnow())
        if bot.user.avatar:
            log_embed_restart.set_thumbnail(url=bot.user.display_avatar.url)

        # 尝试发送重启通知到日志频道
        # 你可以使用 send_to_public_log 函数，或者直接发送到一个指定的频道
        # 为了简单起见，并且 send_to_public_log 依赖 PUBLIC_WARN_LOG_CHANNEL_ID，我们这里直接尝试发送
        # 你可以根据需要调整这里的日志发送逻辑
        log_channel_for_restart_notice = None
        # 优先使用 STARTUP_MESSAGE_CHANNEL_ID，因为它更可能是机器人状态通知的地方
        if STARTUP_MESSAGE_CHANNEL_ID and STARTUP_MESSAGE_CHANNEL_ID != 0: # 确保已配置且不是占位符
            channel_obj = bot.get_channel(STARTUP_MESSAGE_CHANNEL_ID)
            if channel_obj and isinstance(channel_obj, discord.TextChannel):
                log_channel_for_restart_notice = channel_obj
        
        # 如果启动频道无效或未配置，尝试公共日志频道
        if not log_channel_for_restart_notice and PUBLIC_WARN_LOG_CHANNEL_ID:
             # 确保 PUBLIC_WARN_LOG_CHANNEL_ID 不是你之前用作示例的ID (1374390176591122582)
             # 更好的做法是，如果这个ID在你的 .env 中被正确设置了，这里就不需要这个特定数字的检查
             # 假设 PUBLIC_WARN_LOG_CHANNEL_ID 是从 .env 正确读取的
             if PUBLIC_WARN_LOG_CHANNEL_ID != 1374390176591122582: # 移除或调整此硬编码检查
                channel_obj = bot.get_channel(PUBLIC_WARN_LOG_CHANNEL_ID)
                if channel_obj and isinstance(channel_obj, discord.TextChannel):
                    log_channel_for_restart_notice = channel_obj

        if log_channel_for_restart_notice:
            try:
                # 检查机器人是否有权限在目标频道发送消息和嵌入
                bot_member_for_perms = log_channel_for_restart_notice.guild.me
                if log_channel_for_restart_notice.permissions_for(bot_member_for_perms).send_messages and \
                   log_channel_for_restart_notice.permissions_for(bot_member_for_perms).embed_links:
                    await log_channel_for_restart_notice.send(embed=log_embed_restart)
                    print(f"  - 已发送重启通知到频道 #{log_channel_for_restart_notice.name}")
                else:
                    print(f"  - 发送重启通知到频道 #{log_channel_for_restart_notice.name} 失败：缺少发送或嵌入权限。")
            except discord.Forbidden:
                print(f"  - 发送重启通知到频道 #{log_channel_for_restart_notice.name} 失败：权限不足。")
            except Exception as e_log_send:
                print(f"  - 发送重启通知到频道时发生错误: {e_log_send}")
        else:
            print("  - 未找到合适的频道发送重启通知。")


        await bot.change_presence(status=discord.Status.invisible) # 可选：表示正在关闭
        # 清理 aiohttp 会话 (如果存在)
        if hasattr(bot, 'http_session') and bot.http_session and not bot.http_session.closed:
            await bot.http_session.close()
            print("  - aiohttp 会话已关闭。")
        
        await bot.close() # 优雅地关闭与 Discord 的连接
        print("机器人正在关闭以进行重启... 请确保你的托管服务 (如 systemd) 会自动重启脚本。")
        sys.exit(0) # 0 表示成功退出，systemd (如果配置为 Restart=always) 会重启它
    else:
        await interaction.response.send_message("❌ 密码错误，重启取消。", ephemeral=True)
        print(f"用户 {interaction.user.name} 尝试重启机器人但密码错误。")

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

# ... (你已有的 /管理 禁言, /管理 踢出, /管理 人数频道 等指令) ...

# --- 新增：机器人白名单管理指令 (作为 /管理 下的子命令组) ---
# First, define the subcommand group under manage_group
bot_whitelist_group = app_commands.Group(name="bot_whitelist", description="[服主专用] 管理机器人白名单。", parent=manage_group)

# Now, define commands under this new bot_whitelist_group

@bot_whitelist_group.command(name="add", description="[服主专用] 添加一个机器人ID到白名单。")
@app_commands.describe(bot_user_id="要添加到白名单的机器人用户ID。")
async def whitelist_add_cmd(interaction: discord.Interaction, bot_user_id: str): # Renamed function to avoid conflict
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("🚫 只有服务器所有者才能管理机器人白名单。", ephemeral=True)
        return
    
    try:
        target_bot_id = int(bot_user_id)
    except ValueError:
        await interaction.response.send_message("❌ 无效的机器人用户ID格式。请输入纯数字ID。", ephemeral=True)
        return

    if target_bot_id == bot.user.id:
        await interaction.response.send_message("ℹ️ 你不能将此机器人本身添加到白名单（它总是允许的）。", ephemeral=True)
        return

    guild_id = interaction.guild_id
    if guild_id not in bot.approved_bot_whitelist:
        bot.approved_bot_whitelist[guild_id] = set()

    if target_bot_id in bot.approved_bot_whitelist[guild_id]:
        await interaction.response.send_message(f"ℹ️ 机器人ID `{target_bot_id}` 已经在白名单中了。", ephemeral=True)
    else:
        bot.approved_bot_whitelist[guild_id].add(target_bot_id)
        bot_name_display = f"ID `{target_bot_id}`"
        try:
            added_bot_user = await bot.fetch_user(target_bot_id)
            if added_bot_user and added_bot_user.bot:
                bot_name_display = f"机器人 **{added_bot_user.name}** (`{target_bot_id}`)"
            elif added_bot_user: 
                 await interaction.response.send_message(f"⚠️ 用户ID `{target_bot_id}` ({added_bot_user.name}) 不是一个机器人。白名单仅用于机器人。", ephemeral=True)
                 bot.approved_bot_whitelist[guild_id].discard(target_bot_id)
                 return
        except discord.NotFound:
            print(f"[Whitelist] Bot ID {target_bot_id} not found by fetch_user, but added to whitelist.")
        except Exception as e:
            print(f"[Whitelist] Error fetching bot user {target_bot_id}: {e}")

        await interaction.response.send_message(f"✅ {bot_name_display} 已成功添加到机器人白名单。下次它加入时将被允许。", ephemeral=True)
        print(f"[Whitelist] 服务器 {guild_id}: 所有者 {interaction.user.name} 添加了机器人ID {target_bot_id} 到白名单。")
        save_bot_whitelist_to_file()

@bot_whitelist_group.command(name="remove", description="[服主专用] 从白名单中移除一个机器人ID。")
@app_commands.describe(bot_user_id="要从白名单中移除的机器人用户ID。")
async def whitelist_remove_cmd(interaction: discord.Interaction, bot_user_id: str): # Renamed function
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("🚫 只有服务器所有者才能管理机器人白名单。", ephemeral=True)
        return

    try:
        target_bot_id = int(bot_user_id)
    except ValueError:
        await interaction.response.send_message("❌ 无效的机器人用户ID格式。请输入纯数字ID。", ephemeral=True)
        return

    guild_id = interaction.guild_id
    if guild_id not in bot.approved_bot_whitelist or target_bot_id not in bot.approved_bot_whitelist[guild_id]:
        await interaction.response.send_message(f"ℹ️ 机器人ID `{target_bot_id}` 不在白名单中。", ephemeral=True)
    else:
        bot.approved_bot_whitelist[guild_id].discard(target_bot_id)
        if not bot.approved_bot_whitelist[guild_id]:
            del bot.approved_bot_whitelist[guild_id]

        bot_name_display = f"ID `{target_bot_id}`"
        try:
            removed_bot_user = await bot.fetch_user(target_bot_id)
            if removed_bot_user: bot_name_display = f"机器人 **{removed_bot_user.name}** (`{target_bot_id}`)"
        except: pass

        await interaction.response.send_message(f"✅ {bot_name_display} 已成功从机器人白名单中移除。下次它加入时将被踢出（除非再次添加）。", ephemeral=True)
        print(f"[Whitelist] 服务器 {guild_id}: 所有者 {interaction.user.name} 从白名单移除了机器人ID {target_bot_id}。")
        save_bot_whitelist_to_file()

@bot_whitelist_group.command(name="list", description="[服主专用] 查看当前机器人白名单列表。")
async def whitelist_list_cmd(interaction: discord.Interaction): # Renamed function
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("🚫 只有服务器所有者才能管理机器人白名单。", ephemeral=True)
        return

    guild_id = interaction.guild_id
    guild_whitelist = bot.approved_bot_whitelist.get(guild_id, set())

    embed = discord.Embed(title=f"机器人白名单 - {interaction.guild.name}", color=discord.Color.blue(), timestamp=discord.utils.utcnow())
    if not guild_whitelist:
        embed.description = "目前没有机器人被添加到白名单。"
    else:
        description_lines = ["以下机器人ID被允许加入本服务器："]
        if not guild_whitelist:
            description_lines.append("列表为空。")
        else:
            for bot_id in guild_whitelist:
                try:
                    b_user = await bot.fetch_user(bot_id)
                    description_lines.append(f"- **{b_user.name if b_user else '未知用户'}** (`{bot_id}`) {'(Bot)' if b_user and b_user.bot else '(Not a Bot - Should be removed?)' if b_user else ''}")
                except discord.NotFound:
                    description_lines.append(f"- 未知机器人 (`{bot_id}`)")
                except Exception:
                    description_lines.append(f"- ID `{bot_id}` (获取信息失败)")
        embed.description = "\n".join(description_lines)
    embed.set_footer(text="注意：此白名单存储在内存中，机器人重启后会清空（除非实现持久化存储）。")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- 机器人白名单管理指令结束 ---

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
        new_owner_overwrites = discord.PermissionOverwrite(manage_channels=True, manage_permissions=True, move_members=True,connect=True, speak=True, stream=True, use_voice_activation=True, priority_speaker=True, mute_members=True, deafen_members=True, use_embedded_activities=True)
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
        new_owner_overwrites = discord.PermissionOverwrite(manage_channels=True, manage_permissions=True, move_members=True, connect=True, speak=True, stream=True, use_voice_activation=True, priority_speaker=True, mute_members=True, deafen_members=True, use_embedded_activities=True)
        await user_vc.set_permissions(user, overwrite=new_owner_overwrites, reason=f"由 {user.name} 获取房主权限")
        if original_owner: # Reset old owner perms if they existed
             try: await user_vc.set_permissions(original_owner, overwrite=None, reason="原房主离开，重置权限")
             except Exception as reset_e: print(f"   - 重置原房主 {original_owner.id} 权限时出错: {reset_e}")
        temp_vc_owners[user_vc.id] = user.id
        await interaction.followup.send(f"✅ 恭喜 {user.mention}！你已成功获取频道 {user_vc.mention} 的房主权限！", ephemeral=False)
        print(f"[临时语音] 用户 {user.id} 获取了频道 {user_vc.id} 的房主权限 (原房主: {current_owner_id})")
    except discord.Forbidden: await interaction.followup.send(f"⚙️ 获取房主权限失败：机器人权限不足。", ephemeral=True)
    except Exception as e: print(f"执行 /语音 房主 时出错: {e}"); await interaction.followup.send(f"⚙️ 获取房主权限时发生未知错误: {e}", ephemeral=True)

# --- 经济系统斜杠指令组 ---
eco_group = app_commands.Group(name="eco", description=f"与{ECONOMY_CURRENCY_NAME}和商店相关的指令。")

@eco_group.command(name="balance", description=f"查看你或其他用户的{ECONOMY_CURRENCY_NAME}余额。")
@app_commands.describe(user=f"(可选) 要查看其余额的用户。")
async def eco_balance(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    if not ECONOMY_ENABLED:
        await interaction.response.send_message("经济系统当前未启用。", ephemeral=True)
        return
    
    target_user = user if user else interaction.user
    guild_id = interaction.guild_id

    if not guild_id:
        await interaction.response.send_message("此命令只能在服务器中使用。", ephemeral=True)
        return
        
    if target_user.bot:
        await interaction.response.send_message(f"🤖 机器人没有{ECONOMY_CURRENCY_NAME}余额。", ephemeral=True)
        return

    balance = get_user_balance(guild_id, target_user.id)
    
    embed = discord.Embed(
        title=f"{ECONOMY_CURRENCY_SYMBOL} {target_user.display_name}的余额",
        description=f"**{balance}** {ECONOMY_CURRENCY_NAME}",
        color=discord.Color.gold()
    )
    if target_user.avatar:
        embed.set_thumbnail(url=target_user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed, ephemeral=True if user else False)

@eco_group.command(name="transfer", description=f"向其他用户转账{ECONOMY_CURRENCY_NAME}。")
@app_commands.describe(
    receiver=f"接收{ECONOMY_CURRENCY_NAME}的用户。",
    amount=f"要转账的{ECONOMY_CURRENCY_NAME}数量。"
)
async def eco_transfer(interaction: discord.Interaction, receiver: discord.Member, amount: app_commands.Range[int, ECONOMY_MIN_TRANSFER_AMOUNT, None]):
    if not ECONOMY_ENABLED:
        await interaction.response.send_message("经济系统当前未启用。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = interaction.guild_id
    sender = interaction.user

    if not guild_id:
        await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True); return
    if sender.id == receiver.id:
        await interaction.followup.send(f"❌ 你不能给自己转账。", ephemeral=True); return
    if receiver.bot:
        await interaction.followup.send(f"❌ 你不能向机器人转账。", ephemeral=True); return
    if amount <= 0:
        await interaction.followup.send(f"❌ 转账金额必须大于0。", ephemeral=True); return

    sender_balance = get_user_balance(guild_id, sender.id)
    
    tax_amount = 0
    if ECONOMY_TRANSFER_TAX_PERCENT > 0:
        tax_amount = int(amount * (ECONOMY_TRANSFER_TAX_PERCENT / 100))
        if tax_amount < 1 and amount > 0 : tax_amount = 1 # 如果启用了手续费且金额为正，则手续费至少为1

    total_deduction = amount + tax_amount

    if sender_balance < total_deduction:
        await interaction.followup.send(f"❌ 你的{ECONOMY_CURRENCY_NAME}不足以完成转账（需要 {total_deduction} {ECONOMY_CURRENCY_NAME}，包含手续费）。", ephemeral=True)
        return

    if update_user_balance(guild_id, sender.id, -total_deduction) and \
       update_user_balance(guild_id, receiver.id, amount):
        save_economy_data() # 成功交易后保存
        
        response_msg = f"✅ 你已成功向 {receiver.mention} 转账 **{amount}** {ECONOMY_CURRENCY_NAME}。"
        if tax_amount > 0:
            response_msg += f"\n手续费: **{tax_amount}** {ECONOMY_CURRENCY_NAME}。"
        await interaction.followup.send(response_msg, ephemeral=True)

        try:
            dm_embed = discord.Embed(
                title=f"{ECONOMY_CURRENCY_SYMBOL} 你收到一笔转账！",
                description=f"{sender.mention} 向你转账了 **{amount}** {ECONOMY_CURRENCY_NAME}。",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            dm_embed.set_footer(text=f"来自服务器: {interaction.guild.name}")
            await receiver.send(embed=dm_embed)
        except discord.Forbidden:
            await interaction.followup.send(f"ℹ️ 已成功转账，但无法私信通知 {receiver.mention} (TA可能关闭了私信)。",ephemeral=True)
        except Exception as e:
            print(f"[经济系统错误] 发送转账私信给 {receiver.id} 时出错: {e}")
        
        print(f"[经济系统] 转账: {sender.id} -> {receiver.id}, 金额: {amount}, 手续费: {tax_amount}, 服务器: {guild_id}")
    else:
        await interaction.followup.send(f"❌ 转账失败，发生内部错误。请重试或联系管理员。", ephemeral=True)

# --- 修改 /eco shop 指令 ---
@eco_group.command(name="shop", description=f"查看可用物品的商店。")
async def eco_shop(interaction: discord.Interaction):
    if not ECONOMY_ENABLED:
        await interaction.response.send_message("经济系统当前未启用。", ephemeral=True)
        return
    
    guild_id = interaction.guild_id
    if not guild_id:
        await interaction.response.send_message("此命令只能在服务器中使用。", ephemeral=True)
        return

    # guild_shop_items = shop_items.get(guild_id, {}) # 如果使用内存字典
    guild_shop_items = database.db_get_shop_items(guild_id) # 如果使用数据库

    if not guild_shop_items:
        await interaction.response.send_message(f"商店目前是空的。让管理员添加一些物品吧！", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"{ECONOMY_CURRENCY_SYMBOL} {interaction.guild.name} 商店",
        color=discord.Color.blurple()
    )
    # 你可以在这里设置商店的通用插图
    # embed.set_image(url="你的商店插图URL") # 例如
    # embed.set_thumbnail(url="你的商店缩略图URL")

    description_parts = []
    items_for_view = {} # 存储当前页面/所有物品以便创建按钮

    # 简单实现，先显示所有物品的描述，按钮会根据这些物品创建
    # 如果物品过多，这里也需要分页逻辑来决定哪些物品放入 items_for_view
    # 暂时我们假设物品数量不多
    for slug, item in guild_shop_items.items():
        stock_info = f"(库存: {item['stock']})" if item.get('stock', -1) != -1 else "(无限库存)"
        role_name_info = ""
        if item.get("role_id"):
            role = interaction.guild.get_role(item['role_id'])
            if role:
                role_name_info = f" (奖励身份组: **{role.name}**)"
        
        description_parts.append(
            f"🛍️ **{item['name']}** - {ECONOMY_CURRENCY_SYMBOL}**{item['price']}** {stock_info}\n"
            f"   📝 *{item.get('description', '无描述')}*{role_name_info}\n"
            # f"   ID: `{slug}`\n" # 用户不需要看到slug，按钮会处理它
        )
        items_for_view[slug] = item # 添加到用于视图的字典

    if not description_parts:
        await interaction.response.send_message(f"商店中没有可显示的物品。", ephemeral=True)
        return

    embed.description = "\n".join(description_parts[:ECONOMY_MAX_SHOP_ITEMS_PER_PAGE * 2]) # 限制描述长度
    if len(description_parts) > ECONOMY_MAX_SHOP_ITEMS_PER_PAGE * 2:
        embed.description += "\n\n*还有更多物品...*"

    embed.set_footer(text=f"点击下方按钮直接购买物品。")
    
    # 创建并发送带有按钮的视图
    view = ShopItemBuyView(items_for_view, guild_id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=False)


@eco_group.command(name="buy", description=f"从商店购买一件物品。")
@app_commands.describe(item_identifier=f"要购买的物品的名称或ID (商店列表中的`ID`)。")
async def eco_buy(interaction: discord.Interaction, item_identifier: str):
    if not ECONOMY_ENABLED:
        await interaction.response.send_message("经济系统当前未启用。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = interaction.guild_id
    user = interaction.user

    if not guild_id:
        await interaction.followup.send("此命令只能在服务器中使用。", ephemeral=True); return

    guild_shop_items = shop_items.get(guild_id, {})
    item_slug_to_buy = get_item_slug(item_identifier) # 首先尝试 slug
    item_to_buy_data = guild_shop_items.get(item_slug_to_buy)

    if not item_to_buy_data: # 如果通过 slug 未找到，则尝试精确名称（不太可靠）
        for slug, data_val in guild_shop_items.items():
            if data_val['name'].lower() == item_identifier.lower():
                item_to_buy_data = data_val
                item_slug_to_buy = slug
                break
    
    if not item_to_buy_data:
        await interaction.followup.send(f"❌ 未在商店中找到名为或ID为 **'{item_identifier}'** 的物品。", ephemeral=True)
        return

    item_price = item_to_buy_data['price']
    user_balance = get_user_balance(guild_id, user.id)

    if user_balance < item_price:
        await interaction.followup.send(f"❌ 你的{ECONOMY_CURRENCY_NAME}不足以购买 **{item_to_buy_data['name']}** (需要 {item_price}，你有 {user_balance})。", ephemeral=True)
        return

    # 检查库存
    item_stock = item_to_buy_data.get("stock", -1)
    if item_stock == 0: # 显式为 0 表示已售罄
        await interaction.followup.send(f"❌ 抱歉，物品 **{item_to_buy_data['name']}** 已售罄。", ephemeral=True)
        return

    # 如果物品授予身份组，检查用户是否已拥有
    granted_role_id = item_to_buy_data.get("role_id")
    if granted_role_id and isinstance(user, discord.Member): # 确保 user 是 Member 对象
        if discord.utils.get(user.roles, id=granted_role_id):
            await interaction.followup.send(f"ℹ️ 你已经拥有物品 **{item_to_buy_data['name']}** 关联的身份组了。", ephemeral=True)
            return


    if update_user_balance(guild_id, user.id, -item_price):
        # 如果不是无限库存，则更新库存
        if item_stock != -1:
            shop_items[guild_id][item_slug_to_buy]["stock"] = item_stock - 1
        
        save_economy_data() # 成功购买并更新库存后保存

        await grant_item_purchase(interaction, user, item_to_buy_data) # 处理身份组授予和自定义消息
        
        await interaction.followup.send(f"🎉 恭喜！你已成功购买 **{item_to_buy_data['name']}**！", ephemeral=True)
        print(f"[经济系统] 购买: 用户 {user.id} 在服务器 {guild_id} 以 {item_price} 购买了 '{item_to_buy_data['name']}'。")
    else:
        await interaction.followup.send(f"❌ 购买失败，发生内部错误。请重试或联系管理员。", ephemeral=True)

@eco_group.command(name="leaderboard", description=f"显示服务器中{ECONOMY_CURRENCY_NAME}排行榜。")
async def eco_leaderboard(interaction: discord.Interaction):
    if not ECONOMY_ENABLED:
        await interaction.response.send_message("经济系统当前未启用。", ephemeral=True)
        return

    guild_id = interaction.guild_id
    if not guild_id:
        await interaction.response.send_message("此命令只能在服务器中使用。", ephemeral=True)
        return

    guild_balances = user_balances.get(guild_id, {})
    if not guild_balances:
        await interaction.response.send_message(f"本服务器还没有人拥有{ECONOMY_CURRENCY_NAME}记录。", ephemeral=True)
        return

    # 按余额降序排序用户。items() 返回 (user_id, balance)
    sorted_users = sorted(guild_balances.items(), key=lambda item: item[1], reverse=True)
    
    embed = discord.Embed(
        title=f"{ECONOMY_CURRENCY_SYMBOL} {interaction.guild.name} {ECONOMY_CURRENCY_NAME}排行榜",
        color=discord.Color.gold()
    )
    
    description_lines = []
    rank_emojis = ["🥇", "🥈", "🥉"] 
    
    for i, (user_id, balance) in enumerate(sorted_users[:ECONOMY_MAX_LEADERBOARD_USERS]):
        member = interaction.guild.get_member(user_id)
        member_display = member.mention if member else f"用户ID({user_id})"
        rank_prefix = rank_emojis[i] if i < len(rank_emojis) else f"**{i+1}.**"
        description_lines.append(f"{rank_prefix} {member_display} - {ECONOMY_CURRENCY_SYMBOL} **{balance}**")
        
    if not description_lines:
        embed.description = "排行榜当前为空。"
    else:
        embed.description = "\n".join(description_lines)
        
    embed.set_footer(text=f"显示前 {ECONOMY_MAX_LEADERBOARD_USERS} 名。")
    await interaction.response.send_message(embed=embed, ephemeral=False)


# --- 管理员经济系统指令组 (/管理 的子指令组) ---
eco_admin_group = app_commands.Group(name="eco_admin", description=f"管理员经济系统管理指令。", parent=manage_group)

@eco_admin_group.command(name="give", description=f"给予用户指定数量的{ECONOMY_CURRENCY_NAME}。")
@app_commands.describe(user="要给予货币的用户。", amount=f"要给予的{ECONOMY_CURRENCY_NAME}数量。")
@app_commands.checks.has_permissions(manage_guild=True)
async def eco_admin_give(interaction: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 1, None]):
    if not ECONOMY_ENABLED: await interaction.response.send_message("经济系统当前未启用。", ephemeral=True); return
    guild_id = interaction.guild_id
    if user.bot: await interaction.response.send_message(f"❌ 不能给机器人{ECONOMY_CURRENCY_NAME}。", ephemeral=True); return

    if update_user_balance(guild_id, user.id, amount):
        save_economy_data()
        await interaction.response.send_message(f"✅ 已成功给予 {user.mention} **{amount}** {ECONOMY_CURRENCY_NAME}。\n其新余额为: {get_user_balance(guild_id, user.id)} {ECONOMY_CURRENCY_NAME}。", ephemeral=False)
        print(f"[经济系统管理员] {interaction.user.id} 在服务器 {guild_id} 给予了 {user.id} {amount} {ECONOMY_CURRENCY_NAME}。")
    else: await interaction.response.send_message(f"❌ 操作失败。", ephemeral=True)

@eco_admin_group.command(name="take", description=f"从用户处移除指定数量的{ECONOMY_CURRENCY_NAME}。")
@app_commands.describe(user="要移除其货币的用户。", amount=f"要移除的{ECONOMY_CURRENCY_NAME}数量。")
@app_commands.checks.has_permissions(manage_guild=True)
async def eco_admin_take(interaction: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 1, None]):
    if not ECONOMY_ENABLED: await interaction.response.send_message("经济系统当前未启用。", ephemeral=True); return
    guild_id = interaction.guild_id
    if user.bot: await interaction.response.send_message(f"❌ 机器人没有{ECONOMY_CURRENCY_NAME}。", ephemeral=True); return

    current_bal = get_user_balance(guild_id, user.id)
    if current_bal < amount :
        # 选项：只拿走他们拥有的？还是失败？为了明确，我们选择失败。
        await interaction.response.send_message(f"❌ 用户 {user.mention} 只有 {current_bal} {ECONOMY_CURRENCY_NAME}，无法移除 {amount}。", ephemeral=True)
        return

    if update_user_balance(guild_id, user.id, -amount):
        save_economy_data()
        await interaction.response.send_message(f"✅ 已成功从 {user.mention} 处移除 **{amount}** {ECONOMY_CURRENCY_NAME}。\n其新余额为: {get_user_balance(guild_id, user.id)} {ECONOMY_CURRENCY_NAME}。", ephemeral=False)
        print(f"[经济系统管理员] {interaction.user.id} 在服务器 {guild_id} 从 {user.id} 处移除了 {amount} {ECONOMY_CURRENCY_NAME}。")
    else: await interaction.response.send_message(f"❌ 操作失败。", ephemeral=True)


@eco_admin_group.command(name="set", description=f"设置用户{ECONOMY_CURRENCY_NAME}为指定数量。")
@app_commands.describe(user="要设置其余额的用户。", amount=f"要设置的{ECONOMY_CURRENCY_NAME}数量。")
@app_commands.checks.has_permissions(manage_guild=True)
async def eco_admin_set(interaction: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 0, None]):
    if not ECONOMY_ENABLED: await interaction.response.send_message("经济系统当前未启用。", ephemeral=True); return
    guild_id = interaction.guild_id
    if user.bot: await interaction.response.send_message(f"❌ 机器人没有{ECONOMY_CURRENCY_NAME}。", ephemeral=True); return

    if update_user_balance(guild_id, user.id, amount, is_delta=False):
        save_economy_data()
        await interaction.response.send_message(f"✅ 已成功将 {user.mention} 的余额设置为 **{amount}** {ECONOMY_CURRENCY_NAME}。", ephemeral=False)
        print(f"[经济系统管理员] {interaction.user.id} 在服务器 {guild_id} 将用户 {user.id} 的余额设置为 {amount}。")
    else: await interaction.response.send_message(f"❌ 操作失败。", ephemeral=True)

@eco_admin_group.command(name="config_chat_earn", description="配置聊天获取货币的金额和冷却时间。")
@app_commands.describe(
    amount=f"每条符合条件的聊天消息奖励的{ECONOMY_CURRENCY_NAME}数量 (0禁用)。",
    cooldown_seconds="两次聊天奖励之间的冷却时间 (秒)。"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def eco_admin_config_chat_earn(interaction: discord.Interaction, amount: app_commands.Range[int, 0, None], cooldown_seconds: app_commands.Range[int, 5, None]):
    if not ECONOMY_ENABLED: await interaction.response.send_message("经济系统当前未启用。", ephemeral=True); return
    guild_id = interaction.guild_id
    
    guild_economy_settings[guild_id] = {
        "chat_earn_amount": amount,
        "chat_earn_cooldown": cooldown_seconds
    }
    save_economy_data()
    status = "启用" if amount > 0 else "禁用"
    await interaction.response.send_message(
        f"✅ 聊天赚取{ECONOMY_CURRENCY_NAME}已配置：\n"
        f"- 状态: **{status}**\n"
        f"- 每条消息奖励: **{amount}** {ECONOMY_CURRENCY_NAME}\n"
        f"- 冷却时间: **{cooldown_seconds}** 秒",
        ephemeral=True
    )
    print(f"[经济系统管理员] 服务器 {guild_id} 聊天赚钱配置已由 {interaction.user.id} 更新：金额={amount}, 冷却={cooldown_seconds}")

@eco_admin_group.command(name="add_shop_item", description="向商店添加新物品。")
@app_commands.describe(
    name="物品的名称 (唯一)。",
    price=f"物品的价格 ({ECONOMY_CURRENCY_NAME})。",
    description="物品的简短描述。",
    role="(可选) 购买此物品后授予的身份组。",
    stock="(可选) 物品的库存数量 (-1 表示无限，默认为无限)。",
    purchase_message="(可选) 购买成功后私信给用户的额外消息。"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def eco_admin_add_shop_item(
    interaction: discord.Interaction, 
    name: str, 
    price: app_commands.Range[int, 0, None], 
    description: str,
    role: Optional[discord.Role] = None,
    stock: Optional[int] = -1,
    purchase_message: Optional[str] = None
):
    if not ECONOMY_ENABLED: await interaction.response.send_message("经济系统当前未启用。", ephemeral=True); return
    guild_id = interaction.guild_id
    item_slug = get_item_slug(name)

    if guild_id not in shop_items:
        shop_items[guild_id] = {}
    
    if item_slug in shop_items[guild_id]:
        await interaction.response.send_message(f"❌ 商店中已存在名为/ID为 **'{name}'** (`{item_slug}`) 的物品。", ephemeral=True)
        return

    shop_items[guild_id][item_slug] = {
        "name": name,
        "price": price,
        "description": description,
        "role_id": role.id if role else None,
        "stock": stock if stock is not None else -1,
        "purchase_message": purchase_message
    }
    save_economy_data()
    await interaction.response.send_message(f"✅ 物品 **{name}** (`{item_slug}`) 已成功添加到商店！", ephemeral=True)
    print(f"[经济系统管理员] 服务器 {guild_id} 物品已添加: {name} (Slug: {item_slug})，操作者: {interaction.user.id}")


@eco_admin_group.command(name="remove_shop_item", description="从商店移除物品。")
@app_commands.describe(item_identifier="要移除的物品的名称或ID。")
@app_commands.checks.has_permissions(manage_guild=True)
async def eco_admin_remove_shop_item(interaction: discord.Interaction, item_identifier: str):
    if not ECONOMY_ENABLED: await interaction.response.send_message("经济系统当前未启用。", ephemeral=True); return
    guild_id = interaction.guild_id
    item_slug_to_remove = get_item_slug(item_identifier)
    
    item_removed_data = None
    if guild_id in shop_items and item_slug_to_remove in shop_items[guild_id]:
        item_removed_data = shop_items[guild_id].pop(item_slug_to_remove)
    else: # 如果通过 slug 未找到，则尝试名称
        found_by_name = False
        for slug, data_val in shop_items.get(guild_id, {}).items():
            if data_val['name'].lower() == item_identifier.lower():
                item_removed_data = shop_items[guild_id].pop(slug)
                item_slug_to_remove = slug # 更新 slug 以便记录
                found_by_name = True
                break
        if not found_by_name:
             await interaction.response.send_message(f"❌ 未在商店中找到名为或ID为 **'{item_identifier}'** 的物品。", ephemeral=True)
             return

    if item_removed_data:
        if not shop_items[guild_id]: # 如果移除了最后一个物品，则删除服务器条目
            del shop_items[guild_id]
        save_economy_data()
        await interaction.response.send_message(f"✅ 物品 **{item_removed_data['name']}** (`{item_slug_to_remove}`) 已成功从商店移除。", ephemeral=True)
        print(f"[经济系统管理员] 服务器 {guild_id} 物品已移除: {item_removed_data['name']} (Slug: {item_slug_to_remove})，操作者: {interaction.user.id}")
    # else 情况已在上面的检查中处理

@eco_admin_group.command(name="edit_shop_item", description="编辑商店中现有物品的属性。")
@app_commands.describe(
    item_identifier="要编辑的物品的当前名称或ID。",
    new_price=f"(可选) 新的价格 ({ECONOMY_CURRENCY_NAME})。",
    new_description="(可选) 新的描述。",
    new_stock="(可选) 新的库存数量 (-1 表示无限)。",
    new_purchase_message="(可选) 新的购买成功私信消息。"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def eco_admin_edit_shop_item(
    interaction: discord.Interaction,
    item_identifier: str,
    new_price: Optional[app_commands.Range[int, 0, None]] = None,
    new_description: Optional[str] = None,
    new_stock: Optional[int] = None,
    new_purchase_message: Optional[str] = None
):
    if not ECONOMY_ENABLED:
        await interaction.response.send_message("经济系统当前未启用。", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    guild_id = interaction.guild_id

    if new_price is None and new_description is None and new_stock is None and new_purchase_message is None:
        await interaction.followup.send("❌ 你至少需要提供一个要修改的属性。", ephemeral=True)
        return

    guild_shop = shop_items.get(guild_id, {})
    item_slug_to_edit = get_item_slug(item_identifier)
    item_data = guild_shop.get(item_slug_to_edit)

    if not item_data: # 尝试通过名称查找
        for slug, data_val in guild_shop.items():
            if data_val['name'].lower() == item_identifier.lower():
                item_data = data_val
                item_slug_to_edit = slug
                break
    
    if not item_data:
        await interaction.followup.send(f"❌ 未在商店中找到名为或ID为 **'{item_identifier}'** 的物品。", ephemeral=True)
        return

    updated_fields = []
    if new_price is not None:
        item_data["price"] = new_price
        updated_fields.append(f"价格为 {new_price} {ECONOMY_CURRENCY_NAME}")
    if new_description is not None:
        item_data["description"] = new_description
        updated_fields.append("描述")
    if new_stock is not None:
        item_data["stock"] = new_stock
        updated_fields.append(f"库存为 {'无限' if new_stock == -1 else new_stock}")
    if new_purchase_message is not None: # 允许设置为空字符串以移除消息
        item_data["purchase_message"] = new_purchase_message if new_purchase_message.strip() else None
        updated_fields.append("购买后消息")
    
    shop_items[guild_id][item_slug_to_edit] = item_data # 更新物品
    save_economy_data()

    await interaction.followup.send(f"✅ 物品 **{item_data['name']}** (`{item_slug_to_edit}`) 已更新以下属性：{', '.join(updated_fields)}。", ephemeral=True)
    print(f"[经济系统管理员] 服务器 {guild_id} 物品 '{item_data['name']}' 已由 {interaction.user.id} 编辑。字段: {', '.join(updated_fields)}")

# --- (经济系统管理员指令结束) ---

# 将新的指令组添加到机器人树
# 这应该与其他 bot.tree.add_command 调用一起完成
# bot.tree.add_command(eco_group) # 将在末尾添加
# manage_group 已添加，eco_admin_group 作为其子级会自动随 manage_group 添加。

# --- Add the command groups to the bot tree ---
bot.tree.add_command(manage_group)
bot.tree.add_command(voice_group)
bot.tree.add_command(ai_group)
bot.tree.add_command(faq_group)
bot.tree.add_command(relay_msg_group)
bot.tree.add_command(eco_group) # 添加新的面向用户的经济系统指令组

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
            if ECONOMY_ENABLED: # 添加此行
                save_economy_data()
                print("[经济系统] 数据已在关闭时保存。")
            # 关闭机器人时清理会话
            if hasattr(bot, 'http_session') and bot.http_session and not bot.http_session.closed: # 检查会话是否已关闭
                await bot.http_session.close()
                print("已关闭 aiohttp 会话。")
            # await bot.close() # bot.start() 退出或出错时通常会调用此方法，确保不要重复调用。
            # 如果你的框架在 bot.start() 结束或出错后没有自动处理 bot.close()，则取消注释此行。
            print("机器人已关闭。") # 通用关闭消息

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n收到退出信号，正在关闭机器人...")
    except Exception as main_err:
        print(f"\n运行主程序时发生未捕获错误: {main_err}")

# --- End of Complete Code ---
