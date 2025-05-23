# --- START OF FILE music_cog.py ---
import discord
from discord.ext import commands
from discord import app_commands, ui
import asyncio
import yt_dlp # 用于从YouTube等网站提取信息
from collections import deque # 用于实现队列
import re # 用于解析Spotify链接
from typing import Optional # 确保 Optional 被导入

# 抑制yt_dlp关于控制台错误的噪音
yt_dlp.utils.bug_reports_message = lambda: ''

# yt-dlp 的格式选项
YTDL_FORMAT_OPTIONS = {
    'format': 'bestaudio/best', # 选择最佳音质
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s', # 输出文件名模板
    'restrictfilenames': True, # 限制文件名中的特殊字符
    'noplaylist': True, # 默认不处理播放列表（除非明确指定）
    'nocheckcertificate': True, # 不检查SSL证书
    'ignoreerrors': False, # 出现错误时不忽略
    'logtostderr': False, # 不将日志输出到stderr
    'quiet': True, # 安静模式，减少输出
    'no_warnings': True, # 不显示警告
    'default_search': 'auto', # 默认搜索平台
    'source_address': '0.0.0.0',  # 绑定到IPv4，避免IPv6可能导致的问题
}

# FFmpeg 的选项
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', # 连接中断时尝试重连
    'options': '-vn', # 不处理视频部分
}

# 初始化一个全局的yt_dlp实例，使用默认选项
ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)

# YTDLSource类，用于处理从yt-dlp获取的音频源
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data # 存储原始数据
        self.title = data.get('title') # 歌曲标题
        self.uploader = data.get('uploader') # 上传者
        self.url = data.get('webpage_url') # 原始网页链接
        self.duration = data.get('duration') # 时长 (秒)
        self.thumbnail = data.get('thumbnail') # 缩略图URL

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True, search=False, playlist=False):
        loop = loop or asyncio.get_event_loop()
        
        current_ytdl_opts = YTDL_FORMAT_OPTIONS.copy()
        if playlist: # 如果是播放列表
            current_ytdl_opts['noplaylist'] = False # 允许处理播放列表
            current_ytdl_opts['extract_flat'] = 'discard_in_playlist' # 快速提取播放列表信息
            current_ytdl_opts['playlistend'] = 25 # 一次最多添加25首来自播放列表的歌曲
        else:
            current_ytdl_opts['noplaylist'] = True # 只处理单个视频

        custom_ytdl = yt_dlp.YoutubeDL(current_ytdl_opts)

        # 如果是搜索词而不是URL
        if search and not url.startswith(('http://', 'https://')):
            url = f"ytsearch:{url}" # 使用yt-dlp的搜索功能

        # 使用run_in_executor在单独线程中运行阻塞的yt-dlp操作
        data = await loop.run_in_executor(None, lambda: custom_ytdl.extract_info(url, download=not stream))

        if 'entries' in data: # 如果结果是播放列表或有多个条目的搜索结果
            if playlist: # 如果明确请求了播放列表
                return [
                    {'title': entry.get('title', '未知标题'), 
                     'webpage_url': entry.get('webpage_url', entry.get('url')), 
                     'duration': entry.get('duration'),
                     'thumbnail': entry.get('thumbnail'),
                     'uploader': entry.get('uploader')} 
                    for entry in data['entries'] if entry # 过滤掉空的条目
                ]
            else: # 搜索结果，取第一个
                if not data['entries']: # 如果搜索结果为空列表
                    raise yt_dlp.utils.DownloadError(f"未找到与 '{url}' 相关的搜索结果。")
                data = data['entries'][0]
        
        if not stream: # 如果是下载模式 (目前未使用)
            filename = custom_ytdl.prepare_filename(data)
            return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)
        else: # 流媒体模式
            if 'url' not in data:
                best_audio_format = None
                for f_format in data.get('formats', []): # Renamed f to f_format
                    if f_format.get('vcodec') == 'none' and f_format.get('acodec') != 'none' and 'url' in f_format:
                        if best_audio_format is None or f_format.get('abr', 0) > best_audio_format.get('abr', 0):
                            best_audio_format = f_format
                if best_audio_format and 'url' in best_audio_format:
                    data['url'] = best_audio_format['url']
                else:
                    if 'requested_downloads' in data and data['requested_downloads'] and data['requested_downloads'][0].get('url'):
                        data['url'] = data['requested_downloads'][0]['url']
                    elif data.get('url'): # Sometimes the main data object might have a URL if not in formats
                        pass # URL is already in data
                    else:
                        raise yt_dlp.utils.DownloadError("无法从视频信息中提取有效的音频流URL。")
            return cls(discord.FFmpegPCMAudio(data['url'], **FFMPEG_OPTIONS), data=data)

    @classmethod
    async def from_spotify(cls, url, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        
        spotify_track_match = re.match(r"https?://open\.spotify\.com/(?:intl-\w+/)?track/(\w+)", url)
        spotify_playlist_match = re.match(r"https?://open\.spotify\.com/(?:intl-\w+/)?playlist/(\w+)", url)
        spotify_album_match = re.match(r"https?://open\.spotify\.com/(?:intl-\w+/)?album/(\w+)", url)

        search_query = None

        try:
            if spotify_track_match:
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
                if 'entries' in data: data = data['entries'][0]
                
                if data.get('title') and data.get('url'): # yt-dlp resolved it directly
                    return cls(discord.FFmpegPCMAudio(data['url'], **FFMPEG_OPTIONS), data=data)
                else: 
                    title = data.get('track') or data.get('title')
                    artist = data.get('artist') or data.get('uploader')
                    if title and artist: search_query = f"ytsearch:{title} {artist}"
                    elif title: search_query = f"ytsearch:{title}"
                    else: return None 
            
            elif spotify_playlist_match or spotify_album_match:
                playlist_ytdl_opts = YTDL_FORMAT_OPTIONS.copy()
                playlist_ytdl_opts['noplaylist'] = False 
                playlist_ytdl_opts['extract_flat'] = 'discard_in_playlist'
                playlist_ytdl_opts['playlistend'] = 20

                custom_ytdl = yt_dlp.YoutubeDL(playlist_ytdl_opts)
                data = await loop.run_in_executor(None, lambda: custom_ytdl.extract_info(url, download=False))

                if 'entries' in data:
                    processed_entries = []
                    for entry in data['entries']:
                        if not entry: continue
                        entry_title = entry.get('track') or entry.get('title')
                        entry_artist = entry.get('artist') or entry.get('uploader')
                        
                        query_for_entry = ""
                        if entry_title and entry_artist: query_for_entry = f"{entry_title} {entry_artist}"
                        elif entry_title: query_for_entry = entry_title
                        else: continue

                        processed_entries.append({
                            'title': query_for_entry, 
                            'webpage_url': entry.get('url') or entry.get('webpage_url'), 
                            'duration': entry.get('duration'),
                            'thumbnail': entry.get('thumbnail'),
                            'uploader': entry_artist or "Spotify"
                        })
                    return processed_entries
                else: 
                    if data.get('title') and data.get('url'):
                         return cls(discord.FFmpegPCMAudio(data['url'], **FFMPEG_OPTIONS), data=data)
                    return None
            else: 
                return None

        except yt_dlp.utils.DownloadError as e:
            print(f"处理Spotify链接 '{url}' 时 yt-dlp 发生错误: {e}")
            if "This playlist is private or unavailable" in str(e): return "private_playlist"
            try: # Fallback to very basic scraping (highly unreliable)
                # Ensure requests and BeautifulSoup are imported if you uncomment this
                # import requests 
                # from bs4 import BeautifulSoup
                # headers = {'User-Agent': 'Mozilla/5.0'}
                # page = requests.get(url, headers=headers, timeout=5)
                # soup = BeautifulSoup(page.content, 'html.parser')
                # title_tag = soup.find('meta', property='og:title')
                # if title_tag and title_tag.get('content'):
                #     search_query = f"ytsearch:{title_tag['content']}"
                # else: return None
                print("Spotify解析失败，且未启用备用抓取。") # Placeholder if scraping is commented out
                return None
            except Exception: return None
        except Exception as e:
            print(f"处理Spotify链接 '{url}' 时发生未知错误: {e}")
            return None
        
        if search_query: 
            return await cls.from_url(search_query, loop=loop, stream=True, search=True)
        
        return None

# 每个服务器（Guild）的音乐播放状态
class GuildMusicState:
    def __init__(self, bot_loop):
        self.queue = deque()
        self.voice_client = None
        self.current_song = None
        self.loop_mode = "none" 
        self.bot_loop = bot_loop
        self.now_playing_message = None
        self.volume = 0.3 
        self.leave_task = None

    def _schedule_leave(self, delay=180):
        if self.leave_task: self.leave_task.cancel()
        if self.voice_client and self.voice_client.is_connected():
            self.leave_task = self.bot_loop.create_task(self._auto_leave(delay))
            guild_name_debug = self.voice_client.guild.name if self.voice_client and self.voice_client.guild else "未知服务器"
            print(f"[{guild_name_debug}] 无人且队列为空，{delay}秒后自动离开。")

    async def _auto_leave(self, delay):
        await asyncio.sleep(delay)
        if self.voice_client and self.voice_client.is_connected() and \
           not self.voice_client.is_playing() and not self.queue:
            guild_name = self.voice_client.guild.name if self.voice_client.guild else "未知服务器"
            last_text_channel = getattr(self.voice_client, 'last_text_channel', None)
            await self.voice_client.disconnect()
            self.voice_client = None
            if self.now_playing_message:
                try: await self.now_playing_message.delete()
                except: pass
                self.now_playing_message = None
            print(f"[{guild_name}] 自动离开语音频道。")
            if last_text_channel:
                try: await last_text_channel.send("🎵 播放结束且频道内无人，我先走啦！下次见~", delete_after=30)
                except: pass

    def play_next_song_sync(self, error=None):
        guild_name_debug = self.voice_client.guild.name if self.voice_client and self.voice_client.guild else "UnknownGuild"
        if error: print(f'[{guild_name_debug}] 播放器错误: {error}')
        if self.leave_task: self.leave_task.cancel(); self.leave_task = None
        fut = asyncio.run_coroutine_threadsafe(self.play_next_song_async(), self.bot_loop)
        try: fut.result(timeout=10)
        except asyncio.TimeoutError: print(f"[{guild_name_debug}] play_next_song_sync: fut.result timed out.")
        except Exception as e: print(f'[{guild_name_debug}] 安排下一首歌时出错: {e}')

    async def play_next_song_async(self, interaction_for_reply: Optional[discord.Interaction] = None):
        guild_name_debug = self.voice_client.guild.name if self.voice_client and self.voice_client.guild else "UnknownGuild"
        if self.voice_client is None or not self.voice_client.is_connected():
            self.current_song = None; self.queue.clear(); return

        next_song_data_to_play = None
        if self.loop_mode == "song" and self.current_song: next_song_data_to_play = self.current_song.data
        elif self.loop_mode == "queue" and self.current_song: self.queue.append(self.current_song.data); self.current_song = None
        else: self.current_song = None

        if self.current_song is None:
            if not self.queue:
                self.current_song = None
                if self.now_playing_message:
                    try: await self.now_playing_message.edit(content="✅ 队列已播放完毕。", embed=None, view=None)
                    except discord.NotFound: pass
                    except Exception as e: print(f"[{guild_name_debug}] 编辑NP消息(队列结束)时出错: {e}")
                    self.now_playing_message = None
                if self.voice_client and not any(m for m in self.voice_client.channel.members if not m.bot): self._schedule_leave()
                else: print(f"[{guild_name_debug}] 队列播放完毕，但频道内尚有其他成员。")
                return
            else: next_song_data_to_play = self.queue.popleft()
        
        if next_song_data_to_play is None:
            print(f"[{guild_name_debug}] 错误：next_song_data_to_play 为空，无法播放。")
            if self.queue: await self.play_next_song_async(interaction_for_reply)
            return

        try:
            if isinstance(next_song_data_to_play, YTDLSource): self.current_song = next_song_data_to_play
            elif isinstance(next_song_data_to_play, dict) and 'webpage_url' in next_song_data_to_play:
                title_for_search = next_song_data_to_play['title'] # Default to using the title directly
                if next_song_data_to_play.get('uploader') == "Spotify" and not str(next_song_data_to_play.get('webpage_url','')).startswith(('http://', 'https://')):
                    print(f"[{guild_name_debug}] Spotify条目 '{title_for_search}' 需要二次搜索YouTube。")
                    self.current_song = await YTDLSource.from_url(f"ytsearch:{title_for_search}", loop=self.bot_loop, stream=True, search=True)
                else: 
                    self.current_song = await YTDLSource.from_url(next_song_data_to_play['webpage_url'], loop=self.bot_loop, stream=True)
            else:
                print(f"[{guild_name_debug}] 错误：队列中的歌曲数据格式无效: {next_song_data_to_play}")
                if self.queue: await self.play_next_song_async(interaction_for_reply)
                return
            
            if not self.current_song or not hasattr(self.current_song, 'title'):
                raise ValueError("未能成功创建YTDLSource对象或对象缺少标题。")

            self.current_song.volume = self.volume
            self.voice_client.play(self.current_song, after=lambda e: self.play_next_song_sync(e))
            print(f"[{guild_name_debug}] 正在播放: {self.current_song.title}")

            target_interaction_channel = interaction_for_reply.channel if interaction_for_reply else getattr(self.voice_client, 'last_text_channel', None)
            if target_interaction_channel:
                embed = self.create_now_playing_embed()
                view = self.create_music_controls_view()
                if self.now_playing_message:
                    try: await self.now_playing_message.edit(embed=embed, view=view)
                    except discord.NotFound: self.now_playing_message = await target_interaction_channel.send(embed=embed, view=view)
                    except Exception as e_edit: print(f"[{guild_name_debug}] 编辑旧NP消息时出错: {e_edit}, 将发送新消息。"); self.now_playing_message = await target_interaction_channel.send(embed=embed, view=view)
                else:
                    if interaction_for_reply and not interaction_for_reply.response.is_done():
                        await interaction_for_reply.response.send_message(embed=embed, view=view); self.now_playing_message = await interaction_for_reply.original_response()
                    elif interaction_for_reply: self.now_playing_message = await interaction_for_reply.followup.send(embed=embed, view=view, wait=True)
                    else: self.now_playing_message = await target_interaction_channel.send(embed=embed, view=view)
        
        except yt_dlp.utils.DownloadError as e_dl:
            song_title_debug = self.current_song.title if self.current_song else (next_song_data_to_play.get('title', '未知歌曲') if isinstance(next_song_data_to_play, dict) else "未知歌曲")
            error_message = f"❌ 播放时发生下载错误 ({song_title_debug}): {str(e_dl)[:300]}"
            print(f"[{guild_name_debug}] {error_message}")
            channel_to_reply = interaction_for_reply.channel if interaction_for_reply else getattr(self.voice_client, 'last_text_channel', None)
                        if channel_to_reply:
                try: 
                    await channel_to_reply.send(error_message, delete_after=20)
                except: # 最好捕获更具体的异常，但至少需要一个 except 子句
                    pass 
            except: pass
            if self.queue: await self.play_next_song_async(interaction_for_reply)
            else: self._schedule_leave()

        except ValueError as e_val:
            song_title_debug = self.current_song.title if self.current_song else (next_song_data_to_play.get('title', '未知歌曲') if isinstance(next_song_data_to_play, dict) else "未知歌曲")
            error_message = f"❌ 播放时发生值错误 ({song_title_debug}): {str(e_val)[:300]}"
            print(f"[{guild_name_debug}] {error_message}")
            channel_to_reply = interaction_for_reply.channel if interaction_for_reply else getattr(self.voice_client, 'last_text_channel', None)
            if channel_to_reply: try: await channel_to_reply.send(error_message, delete_after=20)
            except: pass
            if self.queue: await self.play_next_song_async(interaction_for_reply)
            else: self._schedule_leave()

        except Exception as e_generic:
            song_title_debug = self.current_song.title if self.current_song else (next_song_data_to_play.get('title', '未知歌曲') if isinstance(next_song_data_to_play, dict) else "未知歌曲")
            error_message = f"❌ 播放时发生未知错误 ({song_title_debug}): {type(e_generic).__name__} - {str(e_generic)[:200]}"
            print(f"[{guild_name_debug}] {error_message}")
            import traceback; traceback.print_exc()
            channel_to_reply = interaction_for_reply.channel if interaction_for_reply else getattr(self.voice_client, 'last_text_channel', None)
            if channel_to_reply: try: await channel_to_reply.send(error_message, delete_after=20)
            except: pass
            if self.queue: await self.play_next_song_async(interaction_for_reply)
            else: self._schedule_leave()

    def create_now_playing_embed(self):
        if not self.current_song: return discord.Embed(title="当前没有播放歌曲", color=discord.Color.greyple())
        embed = discord.Embed(title="🎶 正在播放", description=f"[{self.current_song.title}]({self.current_song.url})", color=discord.Color.random())
        if self.current_song.uploader: embed.set_author(name=self.current_song.uploader)
        if self.current_song.thumbnail: embed.set_thumbnail(url=self.current_song.thumbnail)
        duration_str = "直播或未知"
        if self.current_song.duration: mins, secs = divmod(int(self.current_song.duration), 60); duration_str = f"{mins:02d}:{secs:02d}"
        embed.add_field(name="时长", value=duration_str, inline=True)
        embed.add_field(name="循环模式", value=self.loop_mode.capitalize(), inline=True)
        embed.add_field(name="音量", value=f"{int(self.volume * 100)}%", inline=True)
        if self.queue:
            next_up_data = self.queue[0]
            next_up_title = next_up_data.get('title', '未知标题') if isinstance(next_up_data, dict) else getattr(next_up_data, 'title', '未知标题')
            if len(next_up_title) > 70: next_up_title = next_up_title[:67] + "..."
            embed.add_field(name="下一首", value=next_up_title, inline=False)
        else: embed.add_field(name="下一首", value="队列已空", inline=False)
        return embed

    def create_music_controls_view(self):
        view = ui.View(timeout=None)
        guild_id_for_custom_id = self.voice_client.guild.id if self.voice_client and self.voice_client.guild else 'global_music_controls'

        skip_button = ui.Button(label="跳过", style=discord.ButtonStyle.secondary, emoji="⏭️", custom_id=f"music_skip_{guild_id_for_custom_id}")
        async def skip_callback(interaction: discord.Interaction):
            state = MusicCog._guild_states_ref.get(interaction.guild_id)
            if not state or not interaction.user.voice or not state.voice_client or interaction.user.voice.channel != state.voice_client.channel:
                await interaction.response.send_message("🚫 你需要和机器人在同一个语音频道才能控制播放。", ephemeral=True, delete_after=10); return
            if state.voice_client and state.voice_client.is_playing():
                state.voice_client.stop()
                await interaction.response.send_message("⏭️ 已跳过当前歌曲。", ephemeral=True, delete_after=5)
            else: await interaction.response.send_message("当前没有歌曲可以跳过。", ephemeral=True, delete_after=5)
        skip_button.callback = skip_callback
        view.add_item(skip_button)

        stop_button = ui.Button(label="停止并离开", style=discord.ButtonStyle.danger, emoji="⏹️", custom_id=f"music_stop_{guild_id_for_custom_id}")
        async def stop_callback(interaction: discord.Interaction):
            state = MusicCog._guild_states_ref.get(interaction.guild_id)
            if not state or not interaction.user.voice or not state.voice_client or interaction.user.voice.channel != state.voice_client.channel:
                await interaction.response.send_message("🚫 你需要和机器人在同一个语音频道才能控制播放。", ephemeral=True, delete_after=10); return
            state.queue.clear(); state.current_song = None; state.loop_mode = "none"
            if state.voice_client: state.voice_client.stop(); await state.voice_client.disconnect(); state.voice_client = None
            if state.now_playing_message: try: await state.now_playing_message.delete()
            except: pass; state.now_playing_message = None
            await interaction.response.send_message("⏹️ 音乐已停止，机器人已离开频道。", ephemeral=True, delete_after=10)
            if interaction.guild_id in MusicCog._guild_states_ref: del MusicCog._guild_states_ref[interaction.guild_id]
        stop_button.callback = stop_callback
        view.add_item(stop_button)

        loop_button = ui.Button(label=f"循环: {self.loop_mode.capitalize()}", style=discord.ButtonStyle.primary, emoji="🔁", custom_id=f"music_loop_{guild_id_for_custom_id}")
        async def loop_callback(interaction: discord.Interaction):
            state = MusicCog._guild_states_ref.get(interaction.guild_id)
            if not state or not interaction.user.voice or not state.voice_client or interaction.user.voice.channel != state.voice_client.channel:
                await interaction.response.send_message("🚫 你需要和机器人在同一个语音频道才能控制播放。", ephemeral=True, delete_after=10); return
            if state.loop_mode == "none": state.loop_mode = "song"
            elif state.loop_mode == "song": state.loop_mode = "queue"
            elif state.loop_mode == "queue": state.loop_mode = "none"
            loop_button.label = f"循环: {state.loop_mode.capitalize()}"
            await interaction.response.edit_message(view=view)
            await interaction.followup.send(f"🔁 循环模式已设为: **{state.loop_mode.capitalize()}**", ephemeral=True, delete_after=7)
            if state.now_playing_message and state.current_song: try: await state.now_playing_message.edit(embed=state.create_now_playing_embed(), view=view)
            except: pass
        loop_button.callback = loop_callback
        view.add_item(loop_button)
        return view

class MusicCog(commands.Cog, name="音乐播放"):
    _guild_states_ref = {} 

    def __init__(self, bot: commands.Bot):
        self.bot = bot
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
            try: state.voice_client = await user_vc.connect(timeout=10.0, self_deaf=True); state.voice_client.last_text_channel = interaction.channel
            except discord.ClientException: await interaction.followup.send(" 机器人似乎已在其他语音频道，或无法连接。", ephemeral=True); return False
            except asyncio.TimeoutError: await interaction.followup.send(" 连接到语音频道超时。", ephemeral=True); return False
        elif state.voice_client.channel != user_vc:
            try: await state.voice_client.move_to(user_vc); state.voice_client.last_text_channel = interaction.channel
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
        if state.voice_client and state.voice_client.is_connected():
            guild_name = state.voice_client.guild.name if state.voice_client.guild else "未知服务器"
            state.queue.clear(); state.current_song = None; state.loop_mode = "none"
            if state.voice_client.is_playing(): state.voice_client.stop()
            await state.voice_client.disconnect(); state.voice_client = None
            if state.now_playing_message: try: await state.now_playing_message.delete()
            except: pass; state.now_playing_message = None
            await interaction.followup.send("👋 已离开语音频道并清空队列。", ephemeral=True)
            print(f"[{guild_name}] 用户 {interaction.user.name} 执行 /leave。")
        else: await interaction.followup.send(" 我当前不在任何语音频道。", ephemeral=True)
        if interaction.guild_id in MusicCog._guild_states_ref: del MusicCog._guild_states_ref[interaction.guild_id]

    @music_group.command(name="play", description="播放歌曲或添加到队列 (支持YouTube链接/搜索词, Spotify链接)。")
    @app_commands.describe(query="输入YouTube链接、Spotify链接或歌曲名称进行搜索。")
    async def play_cmd(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=False); state = self.get_guild_state(interaction.guild_id)
        if not await self.ensure_voice(interaction, state): return
        if state.voice_client: state.voice_client.last_text_channel = interaction.channel
        is_spotify_url = "open.spotify.com" in query.lower()
        is_youtube_playlist = ("youtube.com/playlist?" in query) or ("youtu.be/playlist?" in query)
        is_soundcloud_url = "soundcloud.com/" in query.lower()
        songs_to_add_data = []; source_or_list_of_data = None; initial_feedback_sent = False
        try:
            if is_spotify_url:
                source_or_list_of_data = await YTDLSource.from_spotify(query, loop=self.bot.loop)
                if source_or_list_of_data == "private_playlist": await interaction.followup.send(f"❌ 无法处理Spotify链接: `{query}`。该播放列表可能是私有的或不可用。", ephemeral=True); initial_feedback_sent = True; return
                if source_or_list_of_data is None: await interaction.followup.send(f"❌ 未能从Spotify链接解析到任何歌曲: `{query}`。", ephemeral=True); initial_feedback_sent = True; return
            elif is_youtube_playlist or is_soundcloud_url: source_or_list_of_data = await YTDLSource.from_url(query, loop=self.bot.loop, stream=True, playlist=True)
            else: source_or_list_of_data = await YTDLSource.from_url(query, loop=self.bot.loop, stream=True, search=True)
            if isinstance(source_or_list_of_data, list):
                songs_to_add_data.extend(source_or_list_of_data)
                if songs_to_add_data: await interaction.followup.send(f"✅ 已将来自播放列表/专辑的 **{len(songs_to_add_data)}** 首歌添加到队列。", ephemeral=True); initial_feedback_sent = True
                else: await interaction.followup.send(f"播放列表 `{query}` 中未找到可播放的歌曲。", ephemeral=True); initial_feedback_sent = True; return
            elif isinstance(source_or_list_of_data, YTDLSource):
                songs_to_add_data.append(source_or_list_of_data.data)
                await interaction.followup.send(f"✅ 已将 **{source_or_list_of_data.title}** 添加到队列。", ephemeral=True); initial_feedback_sent = True
            else: 
                if not initial_feedback_sent: await interaction.followup.send(f"❓ 未能找到与查询 `{query}` 相关的内容。", ephemeral=True)
                return
        except yt_dlp.utils.DownloadError as e_dl_play: 
            if not initial_feedback_sent: await interaction.followup.send(f"❌ 处理查询时发生下载错误: `{str(e_dl_play)[:300]}`。\n内容可能不可用或受地区限制。", ephemeral=True)
            return
        except Exception as e_play_generic:
            guild_name_debug_play = interaction.guild.name if interaction.guild else "UnknownGuild"
            print(f"[{guild_name_debug_play}] /play 命令执行出错: {type(e_play_generic).__name__} - {e_play_generic}")
            import traceback; traceback.print_exc()
            if not initial_feedback_sent: await interaction.followup.send(f"❌ 发生未知错误: {type(e_play_generic).__name__}。请检查日志。", ephemeral=True)
            return
        if not songs_to_add_data:
            if not initial_feedback_sent: await interaction.followup.send(f"❓ 未能找到与查询 `{query}` 相关的内容或列表为空。", ephemeral=True)
            return
        for song_data_dict in songs_to_add_data: state.queue.append(song_data_dict)
        if not state.voice_client.is_playing() and not state.current_song: await state.play_next_song_async(interaction)

    @music_group.command(name="skip", description="跳过当前播放的歌曲。")
    async def skip_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); state = self.get_guild_state(interaction.guild_id)
        if not interaction.user.voice or not state.voice_client or interaction.user.voice.channel != state.voice_client.channel: await interaction.followup.send("🚫 你需要和机器人在同一个语音频道才能跳歌。", ephemeral=True); return
        if state.voice_client and state.voice_client.is_playing() and state.current_song: state.voice_client.stop(); await interaction.followup.send("⏭️ 已跳过当前歌曲。", ephemeral=True)
        else: await interaction.followup.send(" 当前没有歌曲可以跳过。", ephemeral=True)

    @music_group.command(name="stop", description="停止播放，清空队列，并让机器人离开频道。")
    async def stop_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); state = self.get_guild_state(interaction.guild_id)
        if not interaction.user.voice or not state.voice_client or interaction.user.voice.channel != state.voice_client.channel: await interaction.followup.send("🚫 你需要和机器人在同一个语音频道才能停止播放。", ephemeral=True); return
        if state.voice_client and state.voice_client.is_connected():
            guild_name = state.voice_client.guild.name if state.voice_client.guild else "未知服务器"
            state.queue.clear(); state.current_song = None; state.loop_mode = "none"
            if state.voice_client.is_playing(): state.voice_client.stop()
            await state.voice_client.disconnect(); state.voice_client = None
            if state.now_playing_message: try: await state.now_playing_message.delete()
            except: pass; state.now_playing_message = None
            await interaction.followup.send("⏹️ 播放已停止，队列已清空，机器人已离开频道。", ephemeral=True)
            print(f"[{guild_name}] 用户 {interaction.user.name} 执行 /stop。")
        else: await interaction.followup.send(" 我当前不在语音频道或没有在播放。", ephemeral=True)
        if interaction.guild_id in MusicCog._guild_states_ref: del MusicCog._guild_states_ref[interaction.guild_id]

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
            for i, song_data_dict_q in enumerate(list(state.queue)[:queue_display_limit]): # Renamed song_data_dict
                title_q = song_data_dict_q.get('title', '未知标题') # Renamed title
                if len(title_q) > 60: title_q = title_q[:57] + "..."
                description_lines.append(f"{i+1}. {title_q}")
            if len(state.queue) > queue_display_limit: description_lines.append(f"\n...还有 **{len(state.queue) - queue_display_limit}** 首歌在队列中。")
        embed.description = "\n".join(description_lines); await interaction.followup.send(embed=embed, ephemeral=True)

    @music_group.command(name="nowplaying", description="显示当前正在播放的歌曲信息。")
    async def nowplaying_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False); state = self.get_guild_state(interaction.guild_id)
        if state.current_song and state.voice_client and state.voice_client.is_playing():
            if state.now_playing_message: 
                try: 
                    if state.now_playing_message.channel.id == interaction.channel.id: await state.now_playing_message.delete()
                    else: pass
                except discord.NotFound: pass 
                except Exception as e_del_np: print(f"删除旧NP消息时出错: {e_del_np}"); state.now_playing_message = None
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
        if state.now_playing_message and state.current_song: try: view_vol = state.create_music_controls_view(); await state.now_playing_message.edit(embed=state.create_now_playing_embed(), view=view_vol) # Renamed view
        except: pass

    @music_group.command(name="loop", description="设置播放循环模式。")
    @app_commands.choices(mode=[ app_commands.Choice(name="关闭循环", value="none"), app_commands.Choice(name="单曲循环", value="song"), app_commands.Choice(name="队列循环", value="queue"), ])
    async def loop_cmd(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True); state = self.get_guild_state(interaction.guild_id)
        if not interaction.user.voice or not state.voice_client or interaction.user.voice.channel != state.voice_client.channel: await interaction.followup.send("🚫 你需要和机器人在同一个语音频道才能设置循环模式。", ephemeral=True); return
        state.loop_mode = mode.value; await interaction.followup.send(f"🔁 循环模式已设置为 **{mode.name}**。", ephemeral=True)
        if state.now_playing_message and state.current_song: try: view_loop = state.create_music_controls_view(); await state.now_playing_message.edit(embed=state.create_now_playing_embed(), view=view_loop) # Renamed view
        except: pass
            
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.id == self.bot.user.id:
            if before.channel and not after.channel: 
                state = MusicCog._guild_states_ref.pop(member.guild.id, None)
                if state:
                    if state.now_playing_message: try: await state.now_playing_message.delete()
                    except: pass
                    if state.leave_task: state.leave_task.cancel()
                    print(f"机器人已从 {member.guild.name if member.guild else '未知服务器'} 的语音频道断开，音乐状态已清理。")
            return
        state = MusicCog._guild_states_ref.get(member.guild.id)
        if not state or not state.voice_client or not state.voice_client.is_connected(): return
        bot_vc = state.voice_client.channel
        if state.voice_client.channel != before.channel and state.voice_client.channel != after.channel: return # User activity not in bot's channel
        if before.channel == bot_vc and after.channel != bot_vc: # User left bot's channel
            human_members_in_bot_vc = [m for m in bot_vc.members if not m.bot]
            if not human_members_in_bot_vc: print(f"[{member.guild.name if member.guild else ''}] 用户 {member.name} 离开后，机器人独自在频道 {bot_vc.name}。"); state._schedule_leave()
            elif state.leave_task: state.leave_task.cancel(); state.leave_task = None; print(f"[{member.guild.name if member.guild else ''}] 用户 {member.name} 离开，但频道内仍有其他用户，取消自动离开任务。")
        elif after.channel == bot_vc and before.channel != bot_vc: # User joined bot's channel
            if state.leave_task: state.leave_task.cancel(); state.leave_task = None; print(f"[{member.guild.name if member.guild else ''}] 用户 {member.name} 加入，取消机器人自动离开任务。")

async def setup(bot: commands.Bot):
    music_cog_instance = MusicCog(bot)
    await bot.add_cog(music_cog_instance)
    bot.tree.add_command(music_cog_instance.music_group)
    print("MusicCog 已加载，并且 music 指令组已添加到tree。")

# --- END OF FILE music_cog.py ---
