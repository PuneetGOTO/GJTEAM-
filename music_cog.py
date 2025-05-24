# --- START OF FILE music_cog.py ---
import discord
from discord.ext import commands
from discord import app_commands, ui
import asyncio
import yt_dlp
from collections import deque
import re
from typing import Optional, List, Dict, Any, Union # Added more specific types
import os # For checking cookie file existence

# Suppress noise about console usage from errors
# Updated lambda to accept arbitrary arguments
yt_dlp.utils.bug_reports_message = lambda *args, **kwargs: ''

# --- IMPORTANT: YouTube Cookies ---
# To potentially bypass YouTube's "Sign in to confirm you’re not a bot" errors,
# you need to provide a cookies file.
# 1. Install a browser extension like "Get cookies.txt" or "cookies.txt".
# 2. Log in to YouTube in your browser.
# 3. Use the extension to export your YouTube cookies as "youtube-cookies.txt".
# 4. Place this "youtube-cookies.txt" file in the SAME DIRECTORY as this script (music_cog.py)
#    OR in the root directory where your main bot script (role_manager_bot.py) is run.
#    If the file is not found, yt-dlp will proceed without cookies.
#
# It's recommended to use a dedicated YouTube account for this if possible,
# as your personal account's cookies will be used.
# Keep the cookie file secure and do not share it.
# Cookies can expire, so you might need to re-export them periodically.
# ---

COOKIE_FILE_PATH = "youtube-cookies.txt" # Or an absolute path if preferred

YTDL_FORMAT_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    # Add cookiefile option
    'cookiefile': COOKIE_FILE_PATH if os.path.exists(COOKIE_FILE_PATH) else None,
}

# Check if cookie file exists and print a message
if YTDL_FORMAT_OPTIONS['cookiefile']:
    print(f"ℹ️ [MusicCog] Using cookies from: {COOKIE_FILE_PATH}")
else:
    print(f"⚠️ [MusicCog] Cookie file '{COOKIE_FILE_PATH}' not found. YouTube downloads may be restricted.")
    print(f"   Please see instructions in music_cog.py for setting up YouTube cookies.")


FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source: discord.AudioSource, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)
        self.data: dict = data
        self.title: Optional[str] = data.get('title')
        self.uploader: Optional[str] = data.get('uploader')
        self.url: Optional[str] = data.get('webpage_url')
        self.duration: Optional[int] = data.get('duration')
        self.thumbnail: Optional[str] = data.get('thumbnail')

    @classmethod
    async def from_url(cls, url: str, *, loop: Optional[asyncio.AbstractEventLoop] = None, stream: bool = True, 
                       playlist: bool = False) -> Union['YTDLSource', List[Dict[str, Any]], None]: # 移除了 search 参数
        loop = loop or asyncio.get_event_loop()
        
        current_ytdl_opts = YTDL_FORMAT_OPTIONS.copy()
        # 确保cookiefile选项在每个YTDL实例中都得到应用
        current_ytdl_opts['cookiefile'] = COOKIE_FILE_PATH if os.path.exists(COOKIE_FILE_PATH) else None

        if playlist:
            current_ytdl_opts['noplaylist'] = False
            current_ytdl_opts['extract_flat'] = 'discard_in_playlist' # 获取播放列表中的所有条目信息
            current_ytdl_opts['playlistend'] = 25 # 限制一次处理的播放列表条目数量
        else:
            current_ytdl_opts['noplaylist'] = True


        custom_ytdl = yt_dlp.YoutubeDL(current_ytdl_opts)
        
        # 为避免lambda中变量捕获问题，可以这样写：
        def ytdl_extract_sync(): # 重命名以避免与外部函数重名 (如果存在)
            return custom_ytdl.extract_info(url, download=not stream)
        data = await loop.run_in_executor(None, ytdl_extract_sync)

        if not data:
            # 根据 url 前缀判断是搜索还是直接链接
            if url.startswith("scsearch:") or url.startswith("ytsearch:"): # 包括各种数量的搜索，如 scsearch1:
                search_term = url.split(":", 1)[1] if ":" in url else url # 安全地获取搜索词
                raise yt_dlp.utils.DownloadError(f"未找到与 '{search_term}' 相关的搜索结果。")
            else:
                raise yt_dlp.utils.DownloadError(f"无法从URL '{url}' 获取信息。")

        if 'entries' in data: # 这是播放列表或搜索结果的标志
            if not data['entries']: # 空的播放列表或没有搜索结果
                if playlist: 
                    raise yt_dlp.utils.DownloadError(f"播放列表 '{data.get('title', url)}' 为空或无法访问。")
                else: # 搜索没有结果
                    search_term = url.split(":", 1)[1] if ":" in url else url
                    raise yt_dlp.utils.DownloadError(f"未找到与 '{search_term}' 相关的搜索结果。")

            if playlist: # 如果明确要求处理为播放列表 (例如 SoundCloud set/album, YouTube playlist)
                return [
                    {'title': entry.get('title', '未知标题'), 
                     'webpage_url': entry.get('webpage_url', entry.get('url')), # 'url' 是备用
                     'duration': entry.get('duration'),
                     'thumbnail': entry.get('thumbnail'),
                     'uploader': entry.get('uploader')} 
                    for entry in data['entries'] if entry and (entry.get('webpage_url') or entry.get('url')) # 确保每个条目有效且有URL
                ]
            else: 
                # 如果不是显式播放列表请求，但 'entries' 存在 (例如来自 scsearch1: 或 ytsearch1:)
                # 我们只取第一个结果作为单曲
                data = data['entries'][0]
        
        # 到这里，data 应该是一个单独的歌曲条目信息
        if not stream: # 如果需要下载文件 (通常不用于音乐机器人)
            filename = custom_ytdl.prepare_filename(data) # yt-dlp 会处理文件名
            return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)
        else: # 流式播放
            # 确保 'url' 字段存在于 data 中，这是 FFmpeg 需要的流地址
            if 'url' not in data: # 有时，主 'url' 不在顶层，而在 'formats' 中
                best_audio_format = None
                for f_format in data.get('formats', []): # 遍历所有可用的格式
                    #寻找最佳的纯音频流
                    if f_format.get('vcodec') == 'none' and f_format.get('acodec') != 'none' and 'url' in f_format:
                        if best_audio_format is None or f_format.get('abr', 0) > best_audio_format.get('abr', 0): # abr = average bitrate
                            best_audio_format = f_format
                if best_audio_format and 'url' in best_audio_format:
                    data['url'] = best_audio_format['url'] # 将找到的最佳音频流URL赋给顶层'url'
                elif data.get('url'): # 如果顶层已经有一个url (可能是视频+音频)
                    pass # 允许它，FFmpeg的-vn会尝试去除视频
                else:
                    # 如果在所有格式中都找不到合适的音频流URL
                    raise yt_dlp.utils.DownloadError(f"无法从 '{data.get('title', '未知视频')}' 提取有效的音频流URL。")
            return cls(discord.FFmpegPCMAudio(data['url'], **FFMPEG_OPTIONS), data=data)

    @classmethod
    async def from_spotify(cls, url: str, *, loop: Optional[asyncio.AbstractEventLoop] = None) -> Union['YTDLSource', List[Dict[str, Any]], str, None]:
        loop = loop or asyncio.get_event_loop()
        
        spotify_track_match = re.match(r"https?://open\.spotify\.com/(?:intl-\w+/)?track/(\w+)", url)
        spotify_playlist_match = re.match(r"https?://open\.spotify\.com/(?:intl-\w+/)?playlist/(\w+)", url)
        spotify_album_match = re.match(r"https?://open\.spotify\.com/(?:intl-\w+/)?album/(\w+)", url)
        search_query = None

        # Ensure ytdl instance used for Spotify also respects cookie settings
        # Create a temporary ytdl instance with current cookie settings for Spotify processing
        spotify_ytdl_opts = YTDL_FORMAT_OPTIONS.copy()
        spotify_ytdl_opts['cookiefile'] = COOKIE_FILE_PATH if os.path.exists(COOKIE_FILE_PATH) else None
        current_ytdl_for_spotify = yt_dlp.YoutubeDL(spotify_ytdl_opts)


        try:
            if spotify_track_match:
                data = await loop.run_in_executor(None, lambda: current_ytdl_for_spotify.extract_info(url, download=False))
                if 'entries' in data: data = data['entries'][0]
                if data.get('title') and data.get('url'): return cls(discord.FFmpegPCMAudio(data['url'], **FFMPEG_OPTIONS), data=data)
                title = data.get('track') or data.get('title'); artist = data.get('artist') or data.get('uploader')
                if title and artist: search_query = f"ytsearch:{title} {artist}"
                elif title: search_query = f"ytsearch:{title}"
                else: return None
            
            elif spotify_playlist_match or spotify_album_match:
                playlist_ytdl_opts = {**YTDL_FORMAT_OPTIONS, 'noplaylist': False, 'extract_flat': 'discard_in_playlist', 'playlistend': 20}
                playlist_ytdl_opts['cookiefile'] = COOKIE_FILE_PATH if os.path.exists(COOKIE_FILE_PATH) else None
                custom_ytdl = yt_dlp.YoutubeDL(playlist_ytdl_opts)
                data = await loop.run_in_executor(None, lambda: custom_ytdl.extract_info(url, download=False))
                if 'entries' in data:
                    processed_entries = []
                    for entry in data['entries']:
                        if not entry: continue
                        entry_title = entry.get('track') or entry.get('title'); entry_artist = entry.get('artist') or entry.get('uploader')
                        query_for_entry = f"{entry_title} {entry_artist}" if entry_title and entry_artist else entry_title
                        if not query_for_entry: continue
                        processed_entries.append({
                            'title': query_for_entry, 'webpage_url': entry.get('url') or entry.get('webpage_url'), 
                            'duration': entry.get('duration'), 'thumbnail': entry.get('thumbnail'), 'uploader': entry_artist or "Spotify"
                        })
                    return processed_entries
                elif data.get('title') and data.get('url'): return cls(discord.FFmpegPCMAudio(data['url'], **FFMPEG_OPTIONS), data=data)
                return None
            else: return None
        except yt_dlp.utils.DownloadError as e:
            print(f"处理Spotify链接 '{url}' 时 yt-dlp 发生错误: {e}")
            if "This playlist is private or unavailable" in str(e): return "private_playlist"
            print(f"Spotify解析失败 '{url}', 且未启用备用抓取。")
            return None
        except Exception as e:
            print(f"处理Spotify链接 '{url}' 时发生未知错误: {e}")
            return None
        
        if search_query: return await cls.from_url(search_query, loop=loop, stream=True, search=True)
        return None

class GuildMusicState:
    def __init__(self, bot_loop: asyncio.AbstractEventLoop):
        self.queue: deque[Dict[str, Any]] = deque()
        self.voice_client: Optional[discord.VoiceClient] = None
        self.current_song: Optional[YTDLSource] = None
        self.loop_mode: str = "none"
        self.bot_loop: asyncio.AbstractEventLoop = bot_loop
        self.now_playing_message: Optional[discord.Message] = None
        self.volume: float = 0.3
        self.leave_task: Optional[asyncio.Task] = None
        self.last_interaction_channel_id: Optional[int] = None # Store channel ID for NP messages

    def _get_guild_name_for_debug(self) -> str:
        return self.voice_client.guild.name if self.voice_client and self.voice_client.guild else "未知服务器"

    def _schedule_leave(self, delay: int = 180):
        if self.leave_task: self.leave_task.cancel()
        if self.voice_client and self.voice_client.is_connected():
            self.leave_task = self.bot_loop.create_task(self._auto_leave(delay))
            print(f"[{self._get_guild_name_for_debug()}] 无人且队列为空，{delay}秒后自动离开。")

    async def _auto_leave(self, delay: int):
        await asyncio.sleep(delay)
        if self.voice_client and self.voice_client.is_connected() and \
           not self.voice_client.is_playing() and not self.queue:
            guild_name = self._get_guild_name_for_debug()
            last_text_channel_id = self.last_interaction_channel_id
            
            await self.voice_client.disconnect()
            self.voice_client = None # Critical to set this to None
            if self.now_playing_message:
                try: await self.now_playing_message.delete()
                except: pass # Ignore errors if message already gone
                self.now_playing_message = None
            print(f"[{guild_name}] 自动离开语音频道。")

            if last_text_channel_id and self.bot_loop: # Check if bot_loop is available (it's part of self)
                bot_instance = getattr(self.bot_loop, '_bot_instance_for_music_cog', None) # Needs to be set
                if bot_instance:
                    last_text_channel = bot_instance.get_channel(last_text_channel_id)
                    if last_text_channel and isinstance(last_text_channel, discord.TextChannel):
                        try: await last_text_channel.send("🎵 播放结束且频道内无人，我先走啦！下次见~", delete_after=30)
                        except: pass # Ignore send errors

    def play_next_song_sync(self, error: Optional[Exception] = None):
        guild_name = self._get_guild_name_for_debug()
        if error: print(f'[{guild_name}] 播放器错误: {error}')
        if self.leave_task: self.leave_task.cancel(); self.leave_task = None
        fut = asyncio.run_coroutine_threadsafe(self.play_next_song_async(), self.bot_loop)
        try: fut.result(timeout=10)
        except asyncio.TimeoutError: print(f"[{guild_name}] play_next_song_sync: fut.result timed out.")
        except Exception as e: print(f'[{guild_name}] 安排下一首歌时出错: {e}')

    async def play_next_song_async(self, interaction_for_reply: Optional[discord.Interaction] = None):
        guild_name = self._get_guild_name_for_debug()
        if self.voice_client is None or not self.voice_client.is_connected():
            self.current_song = None; self.queue.clear(); return

        if interaction_for_reply and interaction_for_reply.channel: # Update last channel from interaction
             self.last_interaction_channel_id = interaction_for_reply.channel.id

        next_song_data_to_play: Optional[Dict[str, Any]] = None
        if self.loop_mode == "song" and self.current_song: next_song_data_to_play = self.current_song.data
        elif self.loop_mode == "queue" and self.current_song: self.queue.append(self.current_song.data); self.current_song = None
        else: self.current_song = None

        if self.current_song is None:
            if not self.queue:
                self.current_song = None
                if self.now_playing_message:
                    try: await self.now_playing_message.edit(content="✅ 队列已播放完毕。", embed=None, view=None)
                    except: pass # Ignore errors
                    self.now_playing_message = None
                if self.voice_client and not any(m for m in self.voice_client.channel.members if not m.bot): self._schedule_leave()
                else: print(f"[{guild_name}] 队列播放完毕，但频道内尚有其他成员。")
                return
            else: next_song_data_to_play = self.queue.popleft()
        
        if next_song_data_to_play is None:
            print(f"[{guild_name}] 错误：next_song_data_to_play 为空，无法播放。")
            if self.queue: await self.play_next_song_async(interaction_for_reply); return
        
        original_interaction_channel_id = self.last_interaction_channel_id # Use the stored channel ID

        try:
            if isinstance(next_song_data_to_play, YTDLSource): self.current_song = next_song_data_to_play # Should not happen often
            elif isinstance(next_song_data_to_play, dict) and ('webpage_url' in next_song_data_to_play or 'title' in next_song_data_to_play):
                url_to_play = next_song_data_to_play.get('webpage_url')
                title_for_search = next_song_data_to_play.get('title')
                
                if next_song_data_to_play.get('uploader') == "Spotify" and (not url_to_play or not url_to_play.startswith(('http://', 'https://'))):
                    if not title_for_search: raise ValueError("Spotify条目缺少标题无法搜索YouTube。")
                    print(f"[{guild_name}] Spotify条目 '{title_for_search}' 需要二次搜索YouTube。")
                    self.current_song = await YTDLSource.from_url(f"ytsearch:{title_for_search}", loop=self.bot_loop, stream=True, search=True)
                elif url_to_play: 
                    self.current_song = await YTDLSource.from_url(url_to_play, loop=self.bot_loop, stream=True)
                elif title_for_search: # Fallback to search if no proper URL but title exists (e.g. from a malformed Spotify entry)
                    print(f"[{guild_name}] 条目缺少URL但有标题'{title_for_search}', 尝试YouTube搜索。")
                    self.current_song = await YTDLSource.from_url(f"ytsearch:{title_for_search}", loop=self.bot_loop, stream=True, search=True)
                else:
                    raise ValueError(f"队列中的歌曲数据格式无效: {next_song_data_to_play}")
            else:
                raise ValueError(f"队列中的歌曲数据格式无效: {next_song_data_to_play}")
            
            if not self.current_song or not self.current_song.title: raise ValueError("未能成功创建YTDLSource对象或对象缺少标题。")

            self.current_song.volume = self.volume
            self.voice_client.play(self.current_song, after=lambda e: self.play_next_song_sync(e))
            print(f"[{guild_name}] 正在播放: {self.current_song.title}")

            target_text_channel: Optional[discord.TextChannel] = None
            if interaction_for_reply and interaction_for_reply.channel: target_text_channel = interaction_for_reply.channel
            elif original_interaction_channel_id and self.bot_loop:
                 bot_instance = getattr(self.bot_loop, '_bot_instance_for_music_cog', None)
                 if bot_instance: target_text_channel = bot_instance.get_channel(original_interaction_channel_id)
            
            if target_text_channel and isinstance(target_text_channel, discord.TextChannel):
                embed = self.create_now_playing_embed(); view = self.create_music_controls_view()
                if self.now_playing_message:
                    try: await self.now_playing_message.edit(embed=embed, view=view)
                    except: self.now_playing_message = await target_text_channel.send(embed=embed, view=view) # Fallback to send new
                else:
                    if interaction_for_reply and not interaction_for_reply.response.is_done(): # Should be rare
                        await interaction_for_reply.response.send_message(embed=embed, view=view); self.now_playing_message = await interaction_for_reply.original_response()
                    elif interaction_for_reply: self.now_playing_message = await interaction_for_reply.followup.send(embed=embed, view=view, wait=True)
                    else: self.now_playing_message = await target_text_channel.send(embed=embed, view=view)
        
        except (yt_dlp.utils.DownloadError, ValueError) as e_play:
            song_title_debug = getattr(self.current_song, 'title', None) or (next_song_data_to_play.get('title', '未知歌曲') if isinstance(next_song_data_to_play, dict) else "未知歌曲")
            error_type = "下载" if isinstance(e_play, yt_dlp.utils.DownloadError) else "值"
            error_message = f"❌ 播放时发生{error_type}错误 ({song_title_debug}): {str(e_play)[:300]}"
            print(f"[{guild_name}] {error_message}")
            
            channel_to_reply_id = (interaction_for_reply.channel.id if interaction_for_reply and interaction_for_reply.channel 
                                   else original_interaction_channel_id)
            if channel_to_reply_id and self.bot_loop:
                bot_instance = getattr(self.bot_loop, '_bot_instance_for_music_cog', None)
                if bot_instance:
                    channel_to_reply_obj = bot_instance.get_channel(channel_to_reply_id)
                    if channel_to_reply_obj and isinstance(channel_to_reply_obj, discord.TextChannel):
                        try: await channel_to_reply_obj.send(error_message, delete_after=20)
                        except Exception as send_err: print(f"[{guild_name}] 发送播放错误消息时出错: {send_err}")
            
            if self.queue: await self.play_next_song_async(None) # Try next song, pass None for interaction
            else: self._schedule_leave()
        except Exception as e_generic: # Catch-all for other unexpected errors
            song_title_debug = getattr(self.current_song, 'title', None) or (next_song_data_to_play.get('title', '未知歌曲') if isinstance(next_song_data_to_play, dict) else "未知歌曲")
            error_message = f"❌ 播放时发生未知错误 ({song_title_debug}): {type(e_generic).__name__} - {str(e_generic)[:200]}"
            print(f"[{guild_name}] {error_message}")
            import traceback; traceback.print_exc()
            channel_to_reply_id = (interaction_for_reply.channel.id if interaction_for_reply and interaction_for_reply.channel 
                                   else original_interaction_channel_id)
            if channel_to_reply_id and self.bot_loop:
                bot_instance = getattr(self.bot_loop, '_bot_instance_for_music_cog', None)
                if bot_instance:
                    channel_to_reply_obj = bot_instance.get_channel(channel_to_reply_id)
                    if channel_to_reply_obj and isinstance(channel_to_reply_obj, discord.TextChannel):
                        try: await channel_to_reply_obj.send(error_message, delete_after=20)
                        except Exception as send_err: print(f"[{guild_name}] 发送通用播放错误消息时出错: {send_err}")

            if self.queue: await self.play_next_song_async(None)
            else: self._schedule_leave()

    def create_now_playing_embed(self) -> discord.Embed:
        if not self.current_song: return discord.Embed(title="当前没有播放歌曲", color=discord.Color.greyple())
        embed = discord.Embed(title="🎶 正在播放", description=f"[{self.current_song.title}]({self.current_song.url})", color=discord.Color.random())
        if self.current_song.uploader: embed.set_author(name=self.current_song.uploader)
        if self.current_song.thumbnail: embed.set_thumbnail(url=self.current_song.thumbnail)
        duration_str = "直播或未知"; secs_val = 0
        if self.current_song.duration: secs_val = int(self.current_song.duration); mins, secs = divmod(secs_val, 60); duration_str = f"{mins:02d}:{secs:02d}"
        embed.add_field(name="时长", value=duration_str, inline=True)
        embed.add_field(name="循环模式", value=self.loop_mode.capitalize(), inline=True)
        embed.add_field(name="音量", value=f"{int(self.volume * 100)}%", inline=True)
        if self.queue:
            next_up_data = self.queue[0]; next_up_title = next_up_data.get('title', '未知标题') if isinstance(next_up_data, dict) else getattr(next_up_data, 'title', '未知标题')
            if len(next_up_title) > 70: next_up_title = next_up_title[:67] + "..."
            embed.add_field(name="下一首", value=next_up_title, inline=False)
        else: embed.add_field(name="下一首", value="队列已空", inline=False)
        return embed


    def create_music_controls_view(self) -> ui.View:
        view = ui.View(timeout=None)
        guild_id_for_custom_id = self.voice_client.guild.id if self.voice_client and self.voice_client.guild else 'global_music_controls' # Fallback for custom_id

        skip_button = ui.Button(label="跳过", style=discord.ButtonStyle.secondary, emoji="⏭️", custom_id=f"music_skip_{guild_id_for_custom_id}")
        async def skip_callback(interaction: discord.Interaction):
            state = MusicCog._guild_states_ref.get(interaction.guild_id) # Get state using static ref
            if not state or not interaction.user.voice or not state.voice_client or interaction.user.voice.channel != state.voice_client.channel:
                await interaction.response.send_message("🚫 你需要和机器人在同一个语音频道才能控制播放。", ephemeral=True, delete_after=10); return
            if state.voice_client and state.voice_client.is_playing(): state.voice_client.stop(); await interaction.response.send_message("⏭️ 已跳过当前歌曲。", ephemeral=True, delete_after=5)
            else: await interaction.response.send_message("当前没有歌曲可以跳过。", ephemeral=True, delete_after=5)
        skip_button.callback = skip_callback; view.add_item(skip_button)

        stop_button = ui.Button(label="停止并离开", style=discord.ButtonStyle.danger, emoji="⏹️", custom_id=f"music_stop_{guild_id_for_custom_id}")
        async def stop_callback(interaction: discord.Interaction):
            state = MusicCog._guild_states_ref.get(interaction.guild_id)
            if not state or not interaction.user.voice or not state.voice_client or interaction.user.voice.channel != state.voice_client.channel:
                await interaction.response.send_message("🚫 你需要和机器人在同一个语音频道才能控制播放。", ephemeral=True, delete_after=10); return
            state.queue.clear(); state.current_song = None; state.loop_mode = "none"
            if state.voice_client: state.voice_client.stop(); await state.voice_client.disconnect(); state.voice_client = None
            if state.now_playing_message: 
                try: await state.now_playing_message.delete()
                except: pass # Ignore if already deleted
            state.now_playing_message = None # Always clear reference
            await interaction.response.send_message("⏹️ 音乐已停止，机器人已离开频道。", ephemeral=True, delete_after=10)
            if interaction.guild_id in MusicCog._guild_states_ref: del MusicCog._guild_states_ref[interaction.guild_id]
        stop_button.callback = stop_callback; view.add_item(stop_button)

        loop_button = ui.Button(label=f"循环: {self.loop_mode.capitalize()}", style=discord.ButtonStyle.primary, emoji="🔁", custom_id=f"music_loop_{guild_id_for_custom_id}") # Initial label based on current state
        async def loop_callback(interaction: discord.Interaction):
            state = MusicCog._guild_states_ref.get(interaction.guild_id)
            if not state or not interaction.user.voice or not state.voice_client or interaction.user.voice.channel != state.voice_client.channel:
                await interaction.response.send_message("🚫 你需要和机器人在同一个语音频道才能控制播放。", ephemeral=True, delete_after=10); return
            if state.loop_mode == "none": state.loop_mode = "song"
            elif state.loop_mode == "song": state.loop_mode = "queue"
            else: state.loop_mode = "none" # Cycle back to "none"
            
            for item in view.children:
                if isinstance(item, ui.Button) and item.custom_id == f"music_loop_{guild_id_for_custom_id}": 
                    item.label = f"循环: {state.loop_mode.capitalize()}"
                    break
            await interaction.response.edit_message(view=view) 
            await interaction.followup.send(f"🔁 循环模式已设为: **{state.loop_mode.capitalize()}**", ephemeral=True, delete_after=7)
            if state.now_playing_message and state.current_song: 
                try: await state.now_playing_message.edit(embed=state.create_now_playing_embed(), view=view)
                except: pass 
        loop_button.callback = loop_callback; view.add_item(loop_button)
        return view

class MusicCog(commands.Cog, name="音乐播放"):
    _guild_states_ref: Dict[int, GuildMusicState] = {} 

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.loop._bot_instance_for_music_cog = bot 
        MusicCog._guild_states_ref = {}

    def get_guild_state(self, guild_id: int) -> GuildMusicState:
        if guild_id not in MusicCog._guild_states_ref:
            MusicCog._guild_states_ref[guild_id] = GuildMusicState(self.bot.loop)
        return MusicCog._guild_states_ref[guild_id]

    async def ensure_voice(self, interaction: discord.Interaction, state: GuildMusicState) -> bool:
        if not interaction.user.voice: await interaction.followup.send(" 你需要先连接到一个语音频道。", ephemeral=True); return False
        user_vc = interaction.user.voice.channel
        bot_perms = user_vc.permissions_for(interaction.guild.me)
        if not bot_perms.connect or not bot_perms.speak: await interaction.followup.send(f" 我缺少连接或在频道 **{user_vc.name}** 说话的权限。", ephemeral=True); return False
        if state.voice_client is None or not state.voice_client.is_connected():
            try: state.voice_client = await user_vc.connect(timeout=10.0, self_deaf=True); state.last_interaction_channel_id = interaction.channel.id
            except discord.ClientException: await interaction.followup.send(" 机器人似乎已在其他语音频道，或无法连接。", ephemeral=True); return False
            except asyncio.TimeoutError: await interaction.followup.send(" 连接到语音频道超时。", ephemeral=True); return False
        elif state.voice_client.channel != user_vc:
            try: await state.voice_client.move_to(user_vc); state.last_interaction_channel_id = interaction.channel.id
            except asyncio.TimeoutError: await interaction.followup.send(" 移动到你的语音频道超时。", ephemeral=True); return False
            except discord.ClientException: await interaction.followup.send(" 无法移动到你的语音频道。", ephemeral=True); return False
        return True


    music_group = app_commands.Group(name="music", description="音乐播放相关指令")

    @music_group.command(name="join", description="让机器人加入你所在的语音频道。")
    async def join_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); state = self.get_guild_state(interaction.guild_id)
        if await self.ensure_voice(interaction, state): await interaction.followup.send(f"✅ 已加入语音频道 **{state.voice_client.channel.name}**。", ephemeral=True)

    @music_group.command(name="leave", description="让机器人离开语音频道并清空队列。")
    async def leave_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); state = self.get_guild_state(interaction.guild_id)
        guild_name_debug_leave = interaction.guild.name if interaction.guild else "未知服务器"
        if state.voice_client and state.voice_client.is_connected():
            state.queue.clear(); state.current_song = None; state.loop_mode = "none"
            if state.voice_client.is_playing(): state.voice_client.stop()
            await state.voice_client.disconnect(); state.voice_client = None 
            if state.now_playing_message:
                try:
                    await state.now_playing_message.delete()
                except discord.NotFound:
                    pass
                except Exception as e_del_np_leave:
                    guild_name_debug = interaction.guild.name if interaction.guild else "未知服务器"
                    print(f"[{guild_name_debug}] Leave命令删除NP消息时出错: {e_del_np_leave}")
                state.now_playing_message = None
            await interaction.followup.send("👋 已离开语音频道并清空队列。", ephemeral=True)
            print(f"[{guild_name_debug_leave}] 用户 {interaction.user.name} 执行 /leave。")
        else: await interaction.followup.send(" 我当前不在任何语音频道。", ephemeral=True)
        if interaction.guild_id in MusicCog._guild_states_ref: del MusicCog._guild_states_ref[interaction.guild_id]


    @music_group.command(name="play", description="播放歌曲。默认搜SoundCloud，也支持YouTube/SoundCloud链接。")
    @app_commands.describe(query="输入歌曲名/艺术家 (优先搜SoundCloud)，或YouTube/SoundCloud等平台链接。")
    async def play_cmd(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=True) # 公开的“正在播放”消息
        state = self.get_guild_state(interaction.guild_id)
        guild_name_debug_play = interaction.guild.name if interaction.guild else "UnknownGuild"
        
        # 确保用户在语音频道，并且机器人可以加入/移动
        if not await self.ensure_voice(interaction, state): 
            # ensure_voice 内部已经发送了ephemeral的错误消息，所以这里直接返回
            return

        state.last_interaction_channel_id = interaction.channel.id # 记录交互频道ID

        # 判断链接类型
        is_spotify_url = "open.spotify.com/" in query.lower()
        is_youtube_url = ("youtube.com/" in query.lower()) or ("youtu.be/" in query.lower())
        is_soundcloud_url = "soundcloud.com/" in query.lower()
        # 粗略判断是否是其他直接链接 (不是上述平台)
        is_direct_link = query.startswith(('http://', 'https://')) and not (is_youtube_url or is_soundcloud_url or is_spotify_url)

        songs_to_add_data: List[Dict[str, Any]] = []
        source_or_list_of_data: Union[YTDLSource, List[Dict[str, Any]], str, None] = None
        initial_feedback_sent = False # 标记是否已发送过临时反馈
        pre_message: Optional[discord.WebhookMessage] = None # 用于编辑的初始反馈消息

        url_to_process = query # 将要传递给 YTDLSource.from_url 的最终查询字符串
        is_playlist_request = False # 标记是否正在请求一个播放列表

        try:
            # 准备初始处理消息
            processing_message_content = f"⚙️ 正在处理查询: `{query[:70]}...`"

            if is_youtube_url:
                processing_message_content = f"🔗 正在处理 YouTube 链接: `{query[:70]}...`"
                # 判断是否是YouTube播放列表
                if ("youtube.com/playlist?" in query.lower()) or ("youtu.be/playlist?" in query.lower()):
                    is_playlist_request = True
            elif is_soundcloud_url:
                processing_message_content = f"🎧 正在处理 SoundCloud 链接: `{query[:70]}...`"
                # 判断是否是SoundCloud播放列表/专辑 (sets 或 albums)
                if "/sets/" in query.lower() or "/albums/" in query.lower():
                    is_playlist_request = True
            elif is_spotify_url:
                # Spotify 的逻辑是获取元数据后通常去YouTube搜索
                processing_message_content = f"🔗 正在处理 Spotify 链接 (通常会在YouTube上搜索匹配项): `{query[:70]}...`"
                # from_spotify 内部会判断是单曲还是列表，并返回相应结构
            elif is_direct_link:
                processing_message_content = f"🔗 正在处理直接链接: `{query[:70]}...`"
            else: # 如果不是任何已知平台的 URL，则认为是搜索词，强制搜索 SoundCloud
                url_to_process = f"scsearch1:{query}" # "scsearch1:" 表示搜索SoundCloud并获取第一个结果
                processing_message_content = f"☁️ 正在 SoundCloud 上搜索: `{query[:70]}...`"
                # 对于 scsearch1，我们期望的是单个结果，所以 is_playlist_request 保持 False
            
            # 发送初始的“处理中”消息 (ephemeral)
            pre_message = await interaction.followup.send(processing_message_content, ephemeral=True, wait=True)
            
            # 调用核心处理逻辑
            if is_spotify_url:
                source_or_list_of_data = await YTDLSource.from_spotify(query, loop=self.bot.loop)
            else:
                # from_url 不再需要 search=True 参数，因为它现在只处理直接的 URL 或已构造好的搜索查询
                source_or_list_of_data = await YTDLSource.from_url(
                    url_to_process, 
                    loop=self.bot.loop, 
                    stream=True, 
                    playlist=is_playlist_request # 传递是否按播放列表处理
                )

            # 处理返回结果
            if source_or_list_of_data == "private_playlist": # Spotify 私有播放列表的特殊返回值
                await pre_message.edit(content=f"❌ 无法处理链接: `{query}`。该播放列表可能是私有的或不可用。")
                return
            if source_or_list_of_data is None: # 没有找到任何内容
                await pre_message.edit(content=f"❌ 未能从链接/查询解析到任何歌曲: `{query}`。")
                return
            
            # 将获取到的数据统一到 songs_to_add_data 列表中
            if isinstance(source_or_list_of_data, list): # 如果返回的是播放列表
                songs_to_add_data.extend(source_or_list_of_data)
            elif isinstance(source_or_list_of_data, YTDLSource): # 如果返回的是单个YTDLSource对象
                songs_to_add_data.append(source_or_list_of_data.data) # 我们需要的是原始数据字典
            else: # 理论上不应该到这里，因为上面已经检查了 None
                await pre_message.edit(content=f"❓ 未能找到与查询 `{query}` 相关的内容或格式无法识别。")
                return

            if not songs_to_add_data: # 如果处理后列表仍然为空
                await pre_message.edit(content=f"列表/查询 `{query}` 中未找到可播放的歌曲。")
                return

            # 将所有找到的歌曲数据添加到服务器的播放队列
            for song_data_dict in songs_to_add_data:
                state.queue.append(song_data_dict)
            
            # 构建成功反馈消息
            source_name = "SoundCloud" if url_to_process.startswith("scsearch") or is_soundcloud_url else \
                          "YouTube" if is_youtube_url else \
                          "Spotify (匹配项)" if is_spotify_url else \
                          "直接链接" if is_direct_link else "搜索结果"

            num_songs_added = len(songs_to_add_data)
            first_song_title_added = songs_to_add_data[0].get('title', '歌曲') if num_songs_added > 0 else "歌曲"
            
            if num_songs_added == 1:
                final_feedback_msg = f"✅ 已将来自 {source_name} 的歌曲 **{first_song_title_added}** 添加到队列。"
            else:
                final_feedback_msg = f"✅ 已将来自 {source_name} 的 **{num_songs_added} 首歌** 添加到队列 (第一首: {first_song_title_added[:50]}{'...' if len(first_song_title_added)>50 else ''})。"
            
            await pre_message.edit(content=final_feedback_msg)
            initial_feedback_sent = True # 标记已发送临时反馈

        except yt_dlp.utils.DownloadError as e_dl_play: 
            error_content = f"❌ 处理查询时发生下载错误: `{str(e_dl_play)[:300]}`。"
            if "Sign in to confirm you're not a bot" in str(e_dl_play) and is_youtube_url:
                error_content += "\nYouTube 需要登录验证，请确保 Cookie 文件有效或尝试 SoundCloud 链接。"
            elif is_soundcloud_url or url_to_process.startswith("scsearch"):
                 error_content += "\n请检查 SoundCloud 链接是否有效或歌曲/播放列表是否公开。"
            
            if pre_message: await pre_message.edit(content=error_content)
            # 如果 pre_message 未发送（不太可能到这里），则用 followup.send
            elif not initial_feedback_sent: await interaction.followup.send(error_content, ephemeral=True) 
            return # 出错后不再继续
        except Exception as e_play_generic:
            print(f"[{guild_name_debug_play}] /play 命令执行时发生严重错误: {type(e_play_generic).__name__} - {e_play_generic}")
            import traceback
            traceback.print_exc()
            error_content_generic = f"❌ 处理您的请求时发生未知内部错误: {type(e_play_generic).__name__}。管理员请检查日志。"
            if pre_message: await pre_message.edit(content=error_content_generic)
            elif not initial_feedback_sent: await interaction.followup.send(error_content_generic, ephemeral=True)
            return # 出错后不再继续

        # 如果当前没有歌曲在播放，并且队列不为空，则开始播放
        # 注意：如果 initial_feedback_sent 为 True，表示已经通过 pre_message.edit 给了用户反馈，
        # play_next_song_async 内部发送的“正在播放”消息应该是公开的。
        # 如果 initial_feedback_sent 为 False (例如 pre_message 发送失败了)，
        # 并且 play_next_song_async 是第一次播放，它应该使用 interaction.followup.send 来发送公开的“正在播放”消息。
        if not state.voice_client.is_playing() and not state.current_song: 
            # 如果已经发送了临时的 "已添加" 反馈，play_next_song_async 不需要原始的 interaction 来回复
            # 它会自己创建新的 "正在播放" 消息。
            # 如果上面的 pre_message.edit 失败了，这里传递 interaction 确保至少有一次回应。
            await state.play_next_song_async(interaction if not initial_feedback_sent and not interaction.response.is_done() else None) 

    @music_group.command(name="skip", description="跳过当前播放的歌曲。")
    async def skip_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); state = self.get_guild_state(interaction.guild_id)
        if not interaction.user.voice or not state.voice_client or interaction.user.voice.channel != state.voice_client.channel: await interaction.followup.send("🚫 你需要和机器人在同一个语音频道才能跳歌。", ephemeral=True); return
        if state.voice_client and state.voice_client.is_playing() and state.current_song: state.voice_client.stop(); await interaction.followup.send("⏭️ 已跳过当前歌曲。", ephemeral=True)
        else: await interaction.followup.send(" 当前没有歌曲可以跳过。", ephemeral=True)


    @music_group.command(name="stop", description="停止播放，清空队列，并让机器人离开频道。")
    async def stop_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        state = self.get_guild_state(interaction.guild_id)
        guild_name_debug_stop = interaction.guild.name if interaction.guild else "未知服务器"

        if not interaction.user.voice or not state.voice_client or interaction.user.voice.channel != state.voice_client.channel:
            await interaction.followup.send("🚫 你需要和机器人在同一个语音频道才能停止播放。", ephemeral=True)
            return
        
        if state.voice_client and state.voice_client.is_connected():
            state.queue.clear()
            state.current_song = None
            state.loop_mode = "none"
            if state.voice_client.is_playing():
                state.voice_client.stop()
            
            if state.now_playing_message:
                try:
                    await state.now_playing_message.delete()
                except discord.NotFound:
                    pass 
                except Exception as e_del_np_stop:
                    print(f"[{guild_name_debug_stop}] stop_cmd 删除NP消息时出错: {e_del_np_stop}")
                finally: 
                    state.now_playing_message = None
            
            await state.voice_client.disconnect()
            state.voice_client = None 

            await interaction.followup.send("⏹️ 播放已停止，队列已清空，机器人已离开频道。", ephemeral=True)
            print(f"[{guild_name_debug_stop}] 用户 {interaction.user.name} 执行 /stop。")
        else:
            await interaction.followup.send(" 我当前不在语音频道或没有在播放。", ephemeral=True)
        
        if interaction.guild_id in MusicCog._guild_states_ref:
            del MusicCog._guild_states_ref[interaction.guild_id]


    @music_group.command(name="queue", description="显示当前的歌曲队列。")
    async def queue_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); state = self.get_guild_state(interaction.guild_id)
        if not state.queue and not state.current_song: await interaction.followup.send(" 队列是空的，当前也没有歌曲在播放。", ephemeral=True); return
        embed = discord.Embed(title="🎵 歌曲队列", color=discord.Color.purple()); queue_display_limit = 10; description_lines = []
        if state.current_song: description_lines.append(f"**正在播放:** [{state.current_song.title}]({state.current_song.url})")
        if not state.queue:
            if state.current_song: description_lines.append("\n队列中暂无其他歌曲。")
            else: description_lines.append("队列是空的。")
        else:
            description_lines.append("\n**等待播放:**")
            for i, song_data_item in enumerate(list(state.queue)[:queue_display_limit]): 
                title_item = song_data_item.get('title', '未知标题') 
                if len(title_item) > 60: title_item = title_item[:57] + "..."
                description_lines.append(f"{i+1}. {title_item}")
            if len(state.queue) > queue_display_limit: description_lines.append(f"\n...还有 **{len(state.queue) - queue_display_limit}** 首歌在队列中。")
        embed.description = "\n".join(description_lines); await interaction.followup.send(embed=embed, ephemeral=True)


    @music_group.command(name="nowplaying", description="显示当前正在播放的歌曲信息。")
    async def nowplaying_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False); state = self.get_guild_state(interaction.guild_id)
        if state.voice_client: state.last_interaction_channel_id = interaction.channel.id 

        if state.current_song and state.voice_client and state.voice_client.is_playing():
            if state.now_playing_message: 
                try: 
                    if state.now_playing_message.channel.id == interaction.channel.id: await state.now_playing_message.delete()
                except: pass 
                state.now_playing_message = None 
            embed = state.create_now_playing_embed(); view = state.create_music_controls_view()
            state.now_playing_message = await interaction.followup.send(embed=embed, view=view, wait=True)
        else: await interaction.followup.send(" 当前没有歌曲在播放。", ephemeral=True)
    
    @music_group.command(name="volume", description="设置音乐播放音量 (0-150)。")
    @app_commands.describe(level="音量大小 (0-150，默认为30)。")
    async def volume_cmd(self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 150]):
        await interaction.response.defer(ephemeral=True); state = self.get_guild_state(interaction.guild_id)
        if not state.voice_client or not state.voice_client.is_connected(): await interaction.followup.send(" 我需要先连接到语音频道才能调节音量。", ephemeral=True); return
        if not interaction.user.voice or state.voice_client.channel != interaction.user.voice.channel: await interaction.followup.send(" 你需要和我在同一个语音频道才能调节音量。", ephemeral=True); return
        new_volume_float = level / 100.0; state.volume = new_volume_float
        if state.voice_client.source and isinstance(state.voice_client.source, discord.PCMVolumeTransformer): state.voice_client.source.volume = new_volume_float
        await interaction.followup.send(f"🔊 音量已设置为 **{level}%**。", ephemeral=True)
        if state.now_playing_message and state.current_song: 
            try: view_for_vol_update = state.create_music_controls_view(); await state.now_playing_message.edit(embed=state.create_now_playing_embed(), view=view_for_vol_update)
            except: pass


    @music_group.command(name="loop", description="设置播放循环模式。")
    @app_commands.choices(mode=[ app_commands.Choice(name="关闭循环", value="none"), app_commands.Choice(name="单曲循环", value="song"), app_commands.Choice(name="队列循环", value="queue"), ])
    async def loop_cmd(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True); state = self.get_guild_state(interaction.guild_id)
        if not interaction.user.voice or not state.voice_client or interaction.user.voice.channel != state.voice_client.channel: await interaction.followup.send("🚫 你需要和机器人在同一个语音频道才能设置循环模式。", ephemeral=True); return
        state.loop_mode = mode.value; await interaction.followup.send(f"🔁 循环模式已设置为 **{mode.name}**。", ephemeral=True)
        if state.now_playing_message and state.current_song: 
            try: view_for_loop_update = state.create_music_controls_view(); await state.now_playing_message.edit(embed=state.create_now_playing_embed(), view=view_for_loop_update)
            except: pass
            
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild_name_listener = member.guild.name if member.guild else "未知服务器"
        if member.id == self.bot.user.id:
            if before.channel and not after.channel: 
                state = MusicCog._guild_states_ref.pop(member.guild.id, None)
                if state:
                    if state.now_playing_message:
                        try:
                            await state.now_playing_message.delete()
                        except discord.NotFound:
                            pass 
                        except Exception as e_del_np_bot_disconnect:
                            print(f"[{guild_name_listener}] on_voice_state_update (bot disconnect) 删除NP消息时出错: {e_del_np_bot_disconnect}")
                    
                    if state.leave_task:
                        state.leave_task.cancel()
                    print(f"机器人已从 {guild_name_listener} 的语音频道断开，音乐状态已清理。")
            return 
        
        state = MusicCog._guild_states_ref.get(member.guild.id)
        if not state or not state.voice_client or not state.voice_client.is_connected(): return
        bot_vc = state.voice_client.channel
        if bot_vc != before.channel and bot_vc != after.channel: return 
        if before.channel == bot_vc and after.channel != bot_vc: 
            human_members_in_bot_vc = [m for m in bot_vc.members if not m.bot]
            if not human_members_in_bot_vc: print(f"[{guild_name_listener}] 用户 {member.name} 离开后，机器人独自在频道 {bot_vc.name}。"); state._schedule_leave()
            elif state.leave_task: state.leave_task.cancel(); state.leave_task = None; print(f"[{guild_name_listener}] 用户 {member.name} 离开，但频道内仍有其他用户，取消自动离开任务。")
        elif after.channel == bot_vc and before.channel != bot_vc: 
            if state.leave_task: state.leave_task.cancel(); state.leave_task = None; print(f"[{guild_name_listener}] 用户 {member.name} 加入，取消机器人自动离开任务。")

async def setup(bot: commands.Bot):
    music_cog_instance = MusicCog(bot)
    await bot.add_cog(music_cog_instance)
    if not any(cmd.name == music_cog_instance.music_group.name for cmd in bot.tree.get_commands()):
         bot.tree.add_command(music_cog_instance.music_group)
         print("Music 指令组已显式添加到tree。")
    else:
        print("Music 指令组似乎已在tree中 (可能由Cog加载自动处理)。")
    print("MusicCog 已加载。")

# --- END OF FILE music_cog.py ---
