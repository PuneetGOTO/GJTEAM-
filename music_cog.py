# --- START OF FILE music_cog.py ---
import discord
from discord.ext import commands
from discord import app_commands, ui
import asyncio
import yt_dlp # 用于从YouTube等网站提取信息
from collections import deque # 用于实现队列
import re # 用于解析Spotify链接

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
                data = data['entries'][0]
        
        if not stream: # 如果是下载模式 (目前未使用)
            filename = custom_ytdl.prepare_filename(data)
            return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)
        else: # 流媒体模式
            # 注意：某些视频可能没有直接的 'url' 字段，而是 'formats' 列表。
            # 'bestaudio/best' 通常会选择一个有 'url' 的格式。
            # 如果遇到 "KeyError: 'url'"，可能需要更复杂的格式选择逻辑。
            if 'url' not in data:
                # 尝试从 formats 中寻找最佳音频流
                best_audio_format = None
                for f in data.get('formats', []):
                    if f.get('vcodec') == 'none' and f.get('acodec') != 'none' and 'url' in f: # 仅音频
                        if best_audio_format is None or f.get('abr', 0) > best_audio_format.get('abr', 0):
                            best_audio_format = f
                if best_audio_format and 'url' in best_audio_format:
                    data['url'] = best_audio_format['url']
                else:
                    # 最后的备选方案，如果实在找不到纯音频的url，就用请求的那个，可能会有问题
                    if 'requested_downloads' in data and data['requested_downloads']:
                        data['url'] = data['requested_downloads'][0]['url']
                    else: # 实在没办法了
                        raise yt_dlp.utils.DownloadError("无法提取有效的音频流URL。")
            return cls(discord.FFmpegPCMAudio(data['url'], **FFMPEG_OPTIONS), data=data)

    @classmethod
    async def from_spotify(cls, url, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        
        # 简单的正则匹配Spotify链接类型
        spotify_track_match = re.match(r"https?://open\.spotify\.com/(?:intl-\w+/)?track/(\w+)", url)
        spotify_playlist_match = re.match(r"https?://open\.spotify\.com/(?:intl-\w+/)?playlist/(\w+)", url)
        spotify_album_match = re.match(r"https?://open\.spotify\.com/(?:intl-\w+/)?album/(\w+)", url)

        search_query = None # 用于在YouTube上搜索的查询词

        try:
            if spotify_track_match:
                # yt-dlp 有时可以直接从Spotify链接中解析出可播放源（如通过SoundCloud元数据）
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
                if 'entries' in data: data = data['entries'][0] # 如果返回多个匹配，取第一个
                
                if data.get('title') and data.get('url'):
                    return cls(discord.FFmpegPCMAudio(data['url'], **FFMPEG_OPTIONS), data=data)
                else: # 如果yt-dlp无法直接解析，尝试提取歌曲名和歌手名在YouTube搜索
                    title = data.get('track') or data.get('title')
                    artist = data.get('artist') or data.get('uploader')
                    if title and artist:
                        search_query = f"ytsearch:{title} {artist}"
                    elif title:
                        search_query = f"ytsearch:{title}"
                    else: # 无法获取足够信息进行搜索
                        return None 
            
            elif spotify_playlist_match or spotify_album_match:
                # 对于播放列表和专辑，尝试让yt-dlp提取所有曲目信息
                playlist_ytdl_opts = YTDL_FORMAT_OPTIONS.copy()
                playlist_ytdl_opts['noplaylist'] = False 
                playlist_ytdl_opts['extract_flat'] = 'discard_in_playlist' # 快速提取
                playlist_ytdl_opts['playlistend'] = 20 # 限制一次添加的数量

                custom_ytdl = yt_dlp.YoutubeDL(playlist_ytdl_opts)
                data = await loop.run_in_executor(None, lambda: custom_ytdl.extract_info(url, download=False))

                if 'entries' in data:
                    processed_entries = []
                    for entry in data['entries']:
                        if not entry: continue
                        # 对于播放列表中的每个条目，我们需要获取其可播放的YouTube链接
                        # 这通常意味着对每个Spotify条目在YouTube上进行搜索
                        entry_title = entry.get('track') or entry.get('title')
                        entry_artist = entry.get('artist') or entry.get('uploader')
                        
                        if entry_title and entry_artist:
                            query_for_entry = f"{entry_title} {entry_artist}"
                        elif entry_title:
                            query_for_entry = entry_title
                        else:
                            continue # 信息不足

                        # 将条目信息传递给 from_url 进行YouTube搜索
                        # 注意：这里我们只是构建了包含标题、URL（原始Spotify URL）等的字典
                        # 实际播放时，play_next_song_async 会再次调用 YTDLSource.from_url 
                        # 来获取YouTube的流媒体URL。
                        # 这是一个简化的处理，理想情况下，这里应该直接返回yt-dlp能找到的YouTube链接。
                        # 为了简化，我们先返回包含原始信息的字典，播放时再解析。
                        processed_entries.append({
                            'title': query_for_entry, # 用作后续搜索的标题
                            'webpage_url': entry.get('url') or entry.get('webpage_url'), # 原始Spotify条目链接
                            'duration': entry.get('duration'),
                            'thumbnail': entry.get('thumbnail'),
                            'uploader': entry_artist or "Spotify" # 标记来源
                        })
                    return processed_entries
                else: # 单个项目
                    if data.get('title') and data.get('url'):
                         return cls(discord.FFmpegPCMAudio(data['url'], **FFMPEG_OPTIONS), data=data)
                    return None # 无法解析
            else: # 不是可识别的Spotify链接
                return None

        except yt_dlp.utils.DownloadError as e: # yt-dlp在解析时可能出错
            print(f"处理Spotify链接 '{url}' 时 yt-dlp 发生错误: {e}")
            # 尝试从错误信息中提取可能的搜索词
            if "This playlist is private or unavailable" in str(e):
                return "private_playlist" # 特殊标记，告知用户
            # 可以尝试一个非常基础的页面抓取作为最后手段（非常不可靠）
            try:
                import requests
                from bs4 import BeautifulSoup
                headers = {'User-Agent': 'Mozilla/5.0'}
                page = requests.get(url, headers=headers, timeout=5)
                soup = BeautifulSoup(page.content, 'html.parser')
                title_tag = soup.find('meta', property='og:title')
                if title_tag and title_tag.get('content'):
                    search_query = f"ytsearch:{title_tag['content']}"
                else: return None
            except Exception: return None
        except Exception as e:
            print(f"处理Spotify链接 '{url}' 时发生未知错误: {e}")
            return None
        
        if search_query: # 如果通过某种方式得到了搜索词
            return await cls.from_url(search_query, loop=loop, stream=True, search=True)
        
        return None # 如果所有尝试都失败

# 每个服务器（Guild）的音乐播放状态
class GuildMusicState:
    def __init__(self, bot_loop):
        self.queue = deque() # 歌曲队列
        self.voice_client = None # 当前的语音客户端
        self.current_song = None # 当前播放的歌曲 (YTDLSource实例)
        self.loop_mode = "none"  # "none" (不循环), "song" (单曲循环), "queue" (队列循环)
        self.bot_loop = bot_loop # 机器人的事件循环
        self.now_playing_message = None # 显示“正在播放”消息的对象
        self.volume = 0.3 # 默认音量 (0.0 到 2.0)
        self.leave_task = None # 自动离开频道的任务

    # 安排自动离开任务
    def _schedule_leave(self, delay=180): # 默认3分钟后离开
        if self.leave_task:
            self.leave_task.cancel() # 取消已有的离开任务
        if self.voice_client and self.voice_client.is_connected():
            # 创建一个新的离开任务
            self.leave_task = self.bot_loop.create_task(self._auto_leave(delay))
            print(f"[{self.voice_client.guild.name}] 无人且队列为空，{delay}秒后自动离开。")

    # 实际执行自动离开的协程
    async def _auto_leave(self, delay):
        await asyncio.sleep(delay)
        if self.voice_client and self.voice_client.is_connected() and \
           not self.voice_client.is_playing() and not self.queue:
            # 确认条件仍然满足：已连接，未播放，队列为空
            guild_name = self.voice_client.guild.name
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


    # 同步版本的播放下一首歌（主要用于 vc.play 的 after 回调）
    def play_next_song_sync(self, error=None):
        if error:
            print(f'[{self.voice_client.guild.name if self.voice_client else "UnknownGuild"}] 播放器错误: {error}')
        
        if self.leave_task: # 如果有离开任务，取消它，因为我们要尝试播放或重新排队
            self.leave_task.cancel()
            self.leave_task = None

        # 这个函数是在一个非异步上下文中被调用的（来自vc.play的'after'回调）
        # 我们需要将异步的 play_next_song_async 安排到机器人的事件循环中执行
        fut = asyncio.run_coroutine_threadsafe(self.play_next_song_async(), self.bot_loop)
        try:
            fut.result(timeout=10) # 等待一小段时间，主要用于调试和确保任务启动
        except asyncio.TimeoutError:
            print(f"[{self.voice_client.guild.name if self.voice_client else "UnknownGuild"}] play_next_song_sync: fut.result timed out.")
        except Exception as e:
            print(f'[{self.voice_client.guild.name if self.voice_client else "UnknownGuild"}] 安排下一首歌时出错: {e}')

    # 异步版本的播放下一首歌
    async def play_next_song_async(self, interaction_for_reply: Optional[discord.Interaction] = None):
        if self.voice_client is None or not self.voice_client.is_connected():
            self.current_song = None
            self.queue.clear()
            return

        next_song_data_to_play = None # 将要播放的歌曲数据

        if self.loop_mode == "song" and self.current_song:
            # 单曲循环模式，重新播放当前歌曲
            next_song_data_to_play = self.current_song.data # 使用当前歌曲的数据
        elif self.loop_mode == "queue" and self.current_song:
            # 队列循环模式，将当前歌曲添加到队列末尾
            self.queue.append(self.current_song.data)
            self.current_song = None # 清除当前歌曲，以便从队列中取下一首
        else: # "none" (不循环) 或当前歌曲已结束
            self.current_song = None

        if self.current_song is None: # 如果当前没有设定要重播的歌
            if not self.queue: # 队列也为空
                self.current_song = None # 确保当前歌曲状态正确
                if self.now_playing_message:
                    try: await self.now_playing_message.edit(content="✅ 队列已播放完毕。", embed=None, view=None)
                    except discord.NotFound: pass # 消息可能已被删除
                    except Exception as e: print(f"编辑NP消息(队列结束)时出错: {e}")
                    self.now_playing_message = None
                # 检查是否应该自动离开
                if self.voice_client and not any(m for m in self.voice_client.channel.members if not m.bot):
                    self._schedule_leave() # 频道内只有机器人，安排离开
                else: # 频道内还有其他人，不离开
                    print(f"[{self.voice_client.guild.name}] 队列播放完毕，但频道内尚有其他成员。")
                return
            else: # 队列不为空，从队列头取出一首歌
                next_song_data_to_play = self.queue.popleft()
        
        # 到这里，next_song_data_to_play 应该有值了
        if next_song_data_to_play is None:
            print(f"[{self.voice_client.guild.name}] 错误：next_song_data_to_play 为空，无法播放。")
            if self.queue: await self.play_next_song_async(interaction_for_reply) # 尝试队列中的下一首
            return

        try:
            # 如果 next_song_data_to_play 是 YTDLSource 实例 (通常是单曲循环时)
            if isinstance(next_song_data_to_play, YTDLSource): # 这种情况理论上不应该发生，因为我们存的是data
                 self.current_song = next_song_data_to_play
            # 如果是字典 (来自队列或新添加的歌曲)
            elif isinstance(next_song_data_to_play, dict) and 'webpage_url' in next_song_data_to_play:
                # 有些从Spotify列表来的条目可能只有标题，需要用标题去搜索YouTube
                if next_song_data_to_play.get('uploader') == "Spotify" and not next_song_data_to_play['webpage_url'].startswith(('http://', 'https://')):
                    # 这是一个需要用标题搜索的Spotify条目
                    print(f"[{self.voice_client.guild.name}] Spotify条目 '{next_song_data_to_play['title']}' 需要二次搜索YouTube。")
                    self.current_song = await YTDLSource.from_url(f"ytsearch:{next_song_data_to_play['title']}", loop=self.bot_loop, stream=True, search=True)
                else: # 普通的YouTube链接或已解析的Spotify链接
                    self.current_song = await YTDLSource.from_url(next_song_data_to_play['webpage_url'], loop=self.bot_loop, stream=True)
            else:
                print(f"[{self.voice_client.guild.name}] 错误：队列中的歌曲数据格式无效: {next_song_data_to_play}")
                if self.queue: await self.play_next_song_async(interaction_for_reply) # 尝试下一首
                return
            
            # 检查 self.current_song 是否成功创建
            if not self.current_song or not hasattr(self.current_song, 'title'):
                raise ValueError("未能成功创建YTDLSource对象或对象缺少标题。")

            self.current_song.volume = self.volume # 应用当前音量设置
            self.voice_client.play(self.current_song, after=lambda e: self.play_next_song_sync(e))
            print(f"[{self.voice_client.guild.name}] 正在播放: {self.current_song.title}")

            # 更新或发送“正在播放”消息
            # 如果 interaction_for_reply 存在，说明是命令触发的播放，用它来回复
            target_interaction_channel = interaction_for_reply.channel if interaction_for_reply else None
            if not target_interaction_channel and hasattr(self.voice_client, 'last_text_channel'):
                target_interaction_channel = self.voice_client.last_text_channel
            
            if target_interaction_channel:
                embed = self.create_now_playing_embed()
                view = self.create_music_controls_view() # 获取最新的视图
                if self.now_playing_message: # 如果已有NP消息，尝试编辑
                    try:
                        await self.now_playing_message.edit(embed=embed, view=view)
                    except discord.NotFound: # 消息被删了
                        self.now_playing_message = await target_interaction_channel.send(embed=embed, view=view)
                    except Exception as e_edit:
                        print(f"编辑旧NP消息时出错: {e_edit}, 将发送新消息。")
                        self.now_playing_message = await target_interaction_channel.send(embed=embed, view=view)
                else: # 没有旧的NP消息，发送新的
                    if interaction_for_reply and not interaction_for_reply.response.is_done():
                        # play 命令通常会 defer，所以 is_done() 应该是 True
                        # 但以防万一，如果还没响应，就用 response.send_message
                        await interaction_for_reply.response.send_message(embed=embed, view=view)
                        self.now_playing_message = await interaction_for_reply.original_response()
                    elif interaction_for_reply: # 已经 defer/responded
                        self.now_playing_message = await interaction_for_reply.followup.send(embed=embed, view=view, wait=True)
                    else: # 没有交互对象，直接在频道发送
                        self.now_playing_message = await target_interaction_channel.send(embed=embed, view=view)
        
        except yt_dlp.utils.DownloadError as e:
            error_message = f"❌ 播放时发生下载错误 ({self.current_song.title if self.current_song else next_song_data_to_play.get('title', '未知歌曲')}): {str(e)[:300]}"
            print(f"[{self.voice_client.guild.name}] {error_message}")
            channel_to_reply = interaction_for_reply.channel if interaction_for_reply else getattr(self.voice_client, 'last_text_channel', None)
            if channel_to_reply:
                try: await channel_to_reply.send(error_message, delete_after=20)
                except: pass
            if self.queue: await self.play_next_song_async(interaction_for_reply) # 尝试播放队列中的下一首歌
            else: self._schedule_leave() # 队列空了，且当前播放失败，检查是否离开

        except ValueError as e: # 例如 YTDLSource 创建失败
            error_message = f"❌ 播放时发生值错误 ({self.current_song.title if self.current_song else next_song_data_to_play.get('title', '未知歌曲')}): {str(e)[:300]}"
            print(f"[{self.voice_client.guild.name}] {error_message}")
            channel_to_reply = interaction_for_reply.channel if interaction_for_reply else getattr(self.voice_client, 'last_text_channel', None)
            if channel_to_reply:
                try: await channel_to_reply.send(error_message, delete_after=20)
                except: pass
            if self.queue: await self.play_next_song_async(interaction_for_reply)
            else: self._schedule_leave()

        except Exception as e:
            error_message = f"❌ 播放时发生未知错误 ({self.current_song.title if self.current_song else next_song_data_to_play.get('title', '未知歌曲')}): {type(e).__name__} - {str(e)[:200]}"
            print(f"[{self.voice_client.guild.name}] {error_message}")
            import traceback
            traceback.print_exc()
            channel_to_reply = interaction_for_reply.channel if interaction_for_reply else getattr(self.voice_client, 'last_text_channel', None)
            if channel_to_reply:
                try: await channel_to_reply.send(error_message, delete_after=20)
                except: pass
            if self.queue: await self.play_next_song_async(interaction_for_reply)
            else: self._schedule_leave()

    # 创建“正在播放”的Embed消息
    def create_now_playing_embed(self):
        if not self.current_song:
            return discord.Embed(title="当前没有播放歌曲", color=discord.Color.greyple())
        
        embed = discord.Embed(title="🎶 正在播放", description=f"[{self.current_song.title}]({self.current_song.url})", color=discord.Color.random()) # 随机颜色
        if self.current_song.uploader:
            embed.set_author(name=self.current_song.uploader)
        if self.current_song.thumbnail:
            embed.set_thumbnail(url=self.current_song.thumbnail)
        
        duration_str = "直播或未知"
        if self.current_song.duration:
            mins, secs = divmod(int(self.current_song.duration), 60)
            duration_str = f"{mins:02d}:{secs:02d}"
        embed.add_field(name="时长", value=duration_str, inline=True)
        embed.add_field(name="循环模式", value=self.loop_mode.capitalize(), inline=True)
        embed.add_field(name="音量", value=f"{int(self.volume * 100)}%", inline=True)
        
        if self.queue:
            next_up_title = self.queue[0].get('title', '未知标题') if isinstance(self.queue[0], dict) else self.queue[0].title
            if len(next_up_title) > 70: next_up_title = next_up_title[:67] + "..." # 截断过长标题
            embed.add_field(name="下一首", value=next_up_title, inline=False)
        else:
            embed.add_field(name="下一首", value="队列已空", inline=False)
        
        return embed

    # 创建音乐控制按钮的视图
    def create_music_controls_view(self):
        view = ui.View(timeout=None) # timeout=None 使按钮持久（直到消息被删除或机器人重启）

        skip_button = ui.Button(label="跳过", style=discord.ButtonStyle.secondary, emoji="⏭️", custom_id=f"music_skip_{self.voice_client.guild.id if self.voice_client else 'global'}")
        async def skip_callback(interaction: discord.Interaction):
            # 权限检查：确保用户在机器人所在的语音频道
            if not interaction.user.voice or not self.voice_client or interaction.user.voice.channel != self.voice_client.channel:
                await interaction.response.send_message("🚫 你需要和机器人在同一个语音频道才能控制播放。", ephemeral=True, delete_after=10)
                return

            if self.voice_client and self.voice_client.is_playing():
                self.voice_client.stop() # 这会触发after回调，播放下一首
                await interaction.response.send_message("⏭️ 已跳过当前歌曲。", ephemeral=True, delete_after=5)
                # play_next_song_async 会更新NP消息
            else:
                await interaction.response.send_message("当前没有歌曲可以跳过。", ephemeral=True, delete_after=5)
        skip_button.callback = skip_callback
        view.add_item(skip_button)

        stop_button = ui.Button(label="停止并离开", style=discord.ButtonStyle.danger, emoji="⏹️", custom_id=f"music_stop_{self.voice_client.guild.id if self.voice_client else 'global'}")
        async def stop_callback(interaction: discord.Interaction):
            if not interaction.user.voice or not self.voice_client or interaction.user.voice.channel != self.voice_client.channel:
                await interaction.response.send_message("🚫 你需要和机器人在同一个语音频道才能控制播放。", ephemeral=True, delete_after=10)
                return
            
            self.queue.clear()
            self.current_song = None
            self.loop_mode = "none"
            if self.voice_client:
                self.voice_client.stop()
                await self.voice_client.disconnect()
                self.voice_client = None
            if self.now_playing_message:
                try: await self.now_playing_message.delete()
                except: pass
                self.now_playing_message = None
            await interaction.response.send_message("⏹️ 音乐已停止，机器人已离开频道。", ephemeral=True, delete_after=10)
            # 从 guild_states 中移除状态，因为已经离开了
            if interaction.guild_id in MusicCog._guild_states_ref: # 使用静态引用
                 del MusicCog._guild_states_ref[interaction.guild_id]

        stop_button.callback = stop_callback
        view.add_item(stop_button)

        loop_button = ui.Button(label=f"循环: {self.loop_mode.capitalize()}", style=discord.ButtonStyle.primary, emoji="🔁", custom_id=f"music_loop_{self.voice_client.guild.id if self.voice_client else 'global'}")
        async def loop_callback(interaction: discord.Interaction):
            if not interaction.user.voice or not self.voice_client or interaction.user.voice.channel != self.voice_client.channel:
                await interaction.response.send_message("🚫 你需要和机器人在同一个语音频道才能控制播放。", ephemeral=True, delete_after=10)
                return

            if self.loop_mode == "none": self.loop_mode = "song"
            elif self.loop_mode == "song": self.loop_mode = "queue"
            elif self.loop_mode == "queue": self.loop_mode = "none"
            
            loop_button.label = f"循环: {self.loop_mode.capitalize()}" # 更新按钮上的文字
            await interaction.response.edit_message(view=view) # 编辑原始消息以更新视图
            await interaction.followup.send(f"🔁 循环模式已设为: **{self.loop_mode.capitalize()}**", ephemeral=True, delete_after=7)
            
            if self.now_playing_message and self.current_song: # 更新Embed中的循环状态
                try: await self.now_playing_message.edit(embed=self.create_now_playing_embed(), view=view)
                except: pass
        loop_button.callback = loop_callback
        view.add_item(loop_button)
        
        return view

# Music Cog 主类
class MusicCog(commands.Cog, name="音乐播放"):
    _guild_states_ref = {} # 静态引用，用于按钮回调中访问正确的GuildMusicState

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # self.guild_states = {} # guild_id: GuildMusicState # 改为静态变量
        MusicCog._guild_states_ref = {} # 初始化静态引用

    def get_guild_state(self, guild_id: int) -> GuildMusicState:
        if guild_id not in MusicCog._guild_states_ref:
            MusicCog._guild_states_ref[guild_id] = GuildMusicState(self.bot.loop)
        return MusicCog._guild_states_ref[guild_id]

    # 确保机器人已连接到语音频道
    async def ensure_voice(self, interaction: discord.Interaction, state: GuildMusicState) -> bool:
        if not interaction.user.voice:
            await interaction.followup.send(" 你需要先连接到一个语音频道。", ephemeral=True)
            return False

        user_vc = interaction.user.voice.channel
        bot_perms = user_vc.permissions_for(interaction.guild.me)
        if not bot_perms.connect or not bot_perms.speak:
            await interaction.followup.send(f" 我缺少连接或在频道 **{user_vc.name}** 说话的权限。", ephemeral=True)
            return False

        if state.voice_client is None or not state.voice_client.is_connected():
            try:
                state.voice_client = await user_vc.connect(timeout=10.0, self_deaf=True) # 尝试自动闭麦
                state.voice_client.last_text_channel = interaction.channel # 记录命令发起的文字频道
            except discord.ClientException:
                await interaction.followup.send(" 机器人似乎已在其他语音频道，或无法连接。", ephemeral=True)
                return False
            except asyncio.TimeoutError:
                await interaction.followup.send(" 连接到语音频道超时。", ephemeral=True)
                return False
        elif state.voice_client.channel != user_vc: # 如果机器人在别的频道
            try:
                await state.voice_client.move_to(user_vc)
                state.voice_client.last_text_channel = interaction.channel
            except asyncio.TimeoutError:
                await interaction.followup.send(" 移动到你的语音频道超时。", ephemeral=True)
                return False
            except discord.ClientException:
                 await interaction.followup.send(" 无法移动到你的语音频道。", ephemeral=True)
                 return False
        return True

    music_group = app_commands.Group(name="music", description="音乐播放相关指令")

    @music_group.command(name="join", description="让机器人加入你所在的语音频道。")
    async def join_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        state = self.get_guild_state(interaction.guild_id)
        if await self.ensure_voice(interaction, state):
            await interaction.followup.send(f"✅ 已加入语音频道 **{state.voice_client.channel.name}**。", ephemeral=True)
        # ensure_voice 会处理失败情况的反馈

    @music_group.command(name="leave", description="让机器人离开语音频道并清空队列。")
    async def leave_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        state = self.get_guild_state(interaction.guild_id)
        if state.voice_client and state.voice_client.is_connected():
            guild_name = state.voice_client.guild.name
            state.queue.clear()
            state.current_song = None
            state.loop_mode = "none"
            if state.voice_client.is_playing(): state.voice_client.stop()
            await state.voice_client.disconnect()
            state.voice_client = None
            if state.now_playing_message:
                try: await state.now_playing_message.delete()
                except: pass
                state.now_playing_message = None
            await interaction.followup.send("👋 已离开语音频道并清空队列。", ephemeral=True)
            print(f"[{guild_name}] 用户 {interaction.user.name} 执行 /leave。")
        else:
            await interaction.followup.send(" 我当前不在任何语音频道。", ephemeral=True)
        
        # 清理 guild_states 中的条目
        if interaction.guild_id in MusicCog._guild_states_ref:
            del MusicCog._guild_states_ref[interaction.guild_id]


    @music_group.command(name="play", description="播放歌曲或添加到队列 (支持YouTube链接/搜索词, Spotify链接)。")
    @app_commands.describe(query="输入YouTube链接、Spotify链接或歌曲名称进行搜索。")
    async def play_cmd(self, interaction: discord.Interaction, query: str):
        # defer 发送给所有人的消息，因为“正在播放”应该是公开的
        await interaction.response.defer(ephemeral=False) 
        state = self.get_guild_state(interaction.guild_id)

        if not await self.ensure_voice(interaction, state):
            # ensure_voice 会发送错误消息，所以这里直接返回
            # 如果defer是ephemeral=False，后续的followup可能也需要是ephemeral=False或修改原消息
            # 但因为ensure_voice的followup是ephemeral=True，这里可能需要调整
            # 为了简单，我们假设 play 命令的主要反馈是 Now Playing embed
            return

        if state.voice_client: # 记录命令发起的文字频道
             state.voice_client.last_text_channel = interaction.channel

        is_spotify_url = "open.spotify.com" in query.lower()
        is_youtube_playlist = ("youtube.com/playlist?" in query) or ("youtu.be/playlist?" in query)
        # 简单的 SoundCloud 链接检测
        is_soundcloud_url = "soundcloud.com/" in query.lower()


        songs_to_add_data = [] # 存储将要添加到队列的歌曲数据 (字典列表)
        source_or_list_of_data = None # YTDLSource实例或字典列表

        initial_feedback_sent = False # 标记是否已发送初始“已添加到队列”反馈

        try:
            if is_spotify_url:
                source_or_list_of_data = await YTDLSource.from_spotify(query, loop=self.bot.loop)
                if source_or_list_of_data == "private_playlist":
                    await interaction.followup.send(f"❌ 无法处理Spotify链接: `{query}`。该播放列表可能是私有的或不可用。", ephemeral=True)
                    initial_feedback_sent = True
                    return
                if source_or_list_of_data is None:
                    await interaction.followup.send(f"❌ 未能从Spotify链接解析到任何歌曲: `{query}`。", ephemeral=True)
                    initial_feedback_sent = True
                    return
            elif is_youtube_playlist or is_soundcloud_url: # SoundCloud 链接也可能返回列表
                source_or_list_of_data = await YTDLSource.from_url(query, loop=self.bot.loop, stream=True, playlist=True)
            else: # 普通YouTube链接或搜索词
                source_or_list_of_data = await YTDLSource.from_url(query, loop=self.bot.loop, stream=True, search=True)

            # 处理返回结果
            if isinstance(source_or_list_of_data, list): # 播放列表结果
                songs_to_add_data.extend(source_or_list_of_data) # source_or_list_of_data已经是字典列表
                if songs_to_add_data: # 确保列表不为空
                    await interaction.followup.send(f"✅ 已将来自播放列表/专辑的 **{len(songs_to_add_data)}** 首歌添加到队列。", ephemeral=True)
                    initial_feedback_sent = True
                else:
                    await interaction.followup.send(f"播放列表 `{query}` 中未找到可播放的歌曲。", ephemeral=True)
                    initial_feedback_sent = True
                    return
            elif isinstance(source_or_list_of_data, YTDLSource): # 单首歌曲
                songs_to_add_data.append(source_or_list_of_data.data) # 添加歌曲的data字典
                await interaction.followup.send(f"✅ 已将 **{source_or_list_of_data.title}** 添加到队列。", ephemeral=True)
                initial_feedback_sent = True
            else: # 未找到任何内容或返回了None
                if not initial_feedback_sent:
                    await interaction.followup.send(f"❓ 未能找到与查询 `{query}` 相关的内容。", ephemeral=True)
                return

        except yt_dlp.utils.DownloadError as e:
            if not initial_feedback_sent:
                await interaction.followup.send(f"❌ 处理查询时发生下载错误: `{str(e)[:300]}`。\n内容可能不可用或受地区限制。", ephemeral=True)
            return
        except Exception as e:
            print(f"[{interaction.guild.name}] /play 命令执行出错: {type(e).__name__} - {e}")
            import traceback
            traceback.print_exc()
            if not initial_feedback_sent:
                await interaction.followup.send(f"❌ 发生未知错误: {type(e).__name__}。请检查日志。", ephemeral=True)
            return

        if not songs_to_add_data:
            if not initial_feedback_sent: # 以防万一
                await interaction.followup.send(f"❓ 未能找到与查询 `{query}` 相关的内容或列表为空。", ephemeral=True)
            return
            
        for song_data_dict in songs_to_add_data:
            state.queue.append(song_data_dict) # 将字典添加到队列

        # 如果当前没有播放歌曲，则开始播放
        if not state.voice_client.is_playing() and not state.current_song:
            # play_next_song_async 会处理发送 Now Playing 消息
            # 由于 play 命令 defer(ephemeral=False)，这里的 interaction 可以传递过去
            # 确保 play_next_song_async 能正确使用 interaction.followup.send
            await state.play_next_song_async(interaction) 
        # 如果已经在播放，歌曲只是被添加到队列，NP消息会在下一首歌时或通过 /nowplaying 更新

    @music_group.command(name="skip", description="跳过当前播放的歌曲。")
    async def skip_cmd(self, interaction: discord.Interaction):
        # 此命令现在主要由“正在播放”消息上的按钮处理。
        # 这个斜杠命令版本可以作为备选。
        await interaction.response.defer(ephemeral=True)
        state = self.get_guild_state(interaction.guild_id)
        
        if not interaction.user.voice or not state.voice_client or interaction.user.voice.channel != state.voice_client.channel:
            await interaction.followup.send("🚫 你需要和机器人在同一个语音频道才能跳歌。", ephemeral=True)
            return

        if state.voice_client and state.voice_client.is_playing() and state.current_song:
            state.voice_client.stop() # 触发 'after' 回调，播放下一首
            await interaction.followup.send("⏭️ 已跳过当前歌曲。", ephemeral=True)
        else:
            await interaction.followup.send(" 当前没有歌曲可以跳过。", ephemeral=True)

    @music_group.command(name="stop", description="停止播放，清空队列，并让机器人离开频道。")
    async def stop_cmd(self, interaction: discord.Interaction):
        # 也主要由按钮处理。
        await interaction.response.defer(ephemeral=True)
        state = self.get_guild_state(interaction.guild_id)

        if not interaction.user.voice or not state.voice_client or interaction.user.voice.channel != state.voice_client.channel:
            await interaction.followup.send("🚫 你需要和机器人在同一个语音频道才能停止播放。", ephemeral=True)
            return
        
        if state.voice_client and state.voice_client.is_connected():
            state.queue.clear()
            state.current_song = None
            state.loop_mode = "none"
            if state.voice_client.is_playing(): state.voice_client.stop()
            await state.voice_client.disconnect()
            state.voice_client = None
            if state.now_playing_message:
                try: await state.now_playing_message.delete()
                except: pass
                state.now_playing_message = None
            await interaction.followup.send("⏹️ 播放已停止，队列已清空，机器人已离开频道。", ephemeral=True)
        else:
            await interaction.followup.send(" 我当前不在语音频道或没有在播放。", ephemeral=True)
        
        if interaction.guild_id in MusicCog._guild_states_ref:
            del MusicCog._guild_states_ref[interaction.guild_id]

    @music_group.command(name="queue", description="显示当前的歌曲队列。")
    async def queue_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        state = self.get_guild_state(interaction.guild_id)
        
        if not state.queue and not state.current_song:
            await interaction.followup.send(" 队列是空的，当前也没有歌曲在播放。", ephemeral=True)
            return

        embed = discord.Embed(title="🎵 歌曲队列", color=discord.Color.purple())
        
        queue_display_limit = 10 # 最多显示10首歌
        
        description_lines = []
        if state.current_song:
            description_lines.append(f"**正在播放:** [{state.current_song.title}]({state.current_song.url})")
        
        if not state.queue:
            if state.current_song: description_lines.append("\n队列中暂无其他歌曲。")
            else: description_lines.append("队列是空的。") # 理论上不会到这里如果上面检查了
        else:
            description_lines.append("\n**等待播放:**")
            for i, song_data_dict in enumerate(list(state.queue)[:queue_display_limit]):
                title = song_data_dict.get('title', '未知标题')
                # url = song_data_dict.get('webpage_url', '#') # 原始网页URL
                # 如果是从Spotify来的，webpage_url可能是Spotify的，title可能是搜索用的
                # 为了简化，只显示标题
                if len(title) > 60: title = title[:57] + "..."
                description_lines.append(f"{i+1}. {title}")
            
            if len(state.queue) > queue_display_limit:
                description_lines.append(f"\n...还有 **{len(state.queue) - queue_display_limit}** 首歌在队列中。")
        
        embed.description = "\n".join(description_lines)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @music_group.command(name="nowplaying", description="显示当前正在播放的歌曲信息。")
    async def nowplaying_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False) # “正在播放”消息应该对所有人可见
        state = self.get_guild_state(interaction.guild_id)
        if state.current_song and state.voice_client and state.voice_client.is_playing():
            if state.now_playing_message: # 如果旧的NP消息存在，先删除它
                try: 
                    # 检查消息是否还在，以及是否在同一个频道
                    if state.now_playing_message.channel.id == interaction.channel.id:
                        await state.now_playing_message.delete()
                    else: # 不在同一个频道，不删除旧的，直接发新的
                         pass
                except discord.NotFound: pass # 找不到了就算了
                except Exception as e_del: print(f"删除旧NP消息时出错: {e_del}")
                state.now_playing_message = None # 清除引用
            
            embed = state.create_now_playing_embed()
            view = state.create_music_controls_view()
            # 使用 followup.send 发送新的 NP 消息
            state.now_playing_message = await interaction.followup.send(embed=embed, view=view, wait=True)
        else:
            # 如果 defer 是 ephemeral=False，followup 也应该是
            await interaction.followup.send(" 当前没有歌曲在播放。", ephemeral=True) # 改为True，因为没有NP消息可公开显示
    
    @music_group.command(name="volume", description="设置音乐播放音量 (0-150)。")
    @app_commands.describe(level="音量大小 (0-150，默认为30)。")
    async def volume_cmd(self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 150]):
        await interaction.response.defer(ephemeral=True)
        state = self.get_guild_state(interaction.guild_id)

        if not state.voice_client or not state.voice_client.is_connected():
            await interaction.followup.send(" 我需要先连接到语音频道才能调节音量。", ephemeral=True)
            return
        
        if not interaction.user.voice or state.voice_client.channel != interaction.user.voice.channel:
            await interaction.followup.send(" 你需要和我在同一个语音频道才能调节音量。", ephemeral=True)
            return

        new_volume_float = level / 100.0 # 将整数转换为0.0-1.5的浮点数
        state.volume = new_volume_float
        
        if state.voice_client.source and isinstance(state.voice_client.source, discord.PCMVolumeTransformer):
            state.voice_client.source.volume = new_volume_float # 直接修改正在播放的源的音量
        
        await interaction.followup.send(f"🔊 音量已设置为 **{level}%**。", ephemeral=True)
        if state.now_playing_message and state.current_song: # 更新NP消息中的音量显示
            try: 
                view = state.create_music_controls_view() # 重新获取视图以防按钮状态变化
                await state.now_playing_message.edit(embed=state.create_now_playing_embed(), view=view)
            except: pass # 编辑失败就算了

    @music_group.command(name="loop", description="设置播放循环模式。")
    @app_commands.choices(mode=[
        app_commands.Choice(name="关闭循环", value="none"),
        app_commands.Choice(name="单曲循环", value="song"),
        app_commands.Choice(name="队列循环", value="queue"),
    ])
    async def loop_cmd(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        state = self.get_guild_state(interaction.guild_id)

        if not interaction.user.voice or not state.voice_client or interaction.user.voice.channel != state.voice_client.channel:
            await interaction.followup.send("🚫 你需要和机器人在同一个语音频道才能设置循环模式。", ephemeral=True)
            return
            
        state.loop_mode = mode.value
        await interaction.followup.send(f"🔁 循环模式已设置为 **{mode.name}**。", ephemeral=True)
        if state.now_playing_message and state.current_song: # 更新NP消息
            try: 
                view = state.create_music_controls_view() # 确保按钮标签也更新
                await state.now_playing_message.edit(embed=state.create_now_playing_embed(), view=view)
            except: pass
            
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # 当机器人自己状态改变（例如被踢出或断开连接）
        if member.id == self.bot.user.id:
            if before.channel and not after.channel: # 机器人从一个频道离开
                state = MusicCog._guild_states_ref.pop(member.guild.id, None) # 从静态引用中移除
                if state:
                    if state.now_playing_message:
                        try: await state.now_playing_message.delete()
                        except: pass
                    if state.leave_task: state.leave_task.cancel()
                    print(f"机器人已从 {member.guild.name} 的语音频道断开，音乐状态已清理。")
            return

        # 如果事件与机器人无关，或者机器人不在任何频道，则忽略
        state = MusicCog._guild_states_ref.get(member.guild.id)
        if not state or not state.voice_client or not state.voice_client.is_connected():
            return

        # 如果事件发生的频道不是机器人所在的频道，也忽略
        if state.voice_client.channel != before.channel and state.voice_client.channel != after.channel:
            return
            
        # 检查机器人是否独自在频道中
        # 注意：after.channel 可能是 None (如果用户离开频道)
        # 我们关心的是 before.channel (用户离开前的频道) 是否是机器人所在的频道
        # 以及 after.channel (用户加入的频道) 是否是机器人所在的频道
        
        # 机器人所在的频道
        bot_vc = state.voice_client.channel

        # Case 1: 用户离开了机器人所在的频道
        if before.channel == bot_vc and after.channel != bot_vc:
            # 检查机器人是否独自留在频道
            human_members_in_bot_vc = [m for m in bot_vc.members if not m.bot]
            if not human_members_in_bot_vc: # 机器人独自一人
                print(f"[{member.guild.name}] 用户 {member.name} 离开后，机器人独自在频道 {bot_vc.name}。")
                state._schedule_leave() # 安排自动离开
            else: # 还有其他人类用户
                if state.leave_task: # 如果之前有离开任务，取消它
                    state.leave_task.cancel()
                    state.leave_task = None
                    print(f"[{member.guild.name}] 用户 {member.name} 离开，但频道内仍有其他用户，取消自动离开任务。")


        # Case 2: 用户加入了机器人所在的频道 (之前频道中可能只有机器人)
        elif after.channel == bot_vc and before.channel != bot_vc:
            if state.leave_task: # 如果机器人因为之前独自一人而计划离开
                state.leave_task.cancel() # 用户加入了，取消离开计划
                state.leave_task = None
                print(f"[{member.guild.name}] 用户 {member.name} 加入，取消机器人自动离开任务。")


# setup 函数，用于将 Cog 加载到机器人中
async def setup(bot: commands.Bot):
    music_cog_instance = MusicCog(bot)
    await bot.add_cog(music_cog_instance)
    # 将指令组添加到 bot.tree (这一步很重要，否则斜杠命令不会注册)
    bot.tree.add_command(music_cog_instance.music_group)
    print("MusicCog 已加载，并且 music 指令组已添加到tree。")

# --- END OF FILE music_cog.py ---