import re
import os
import asyncio
import logging
import traceback
from datetime import datetime, timedelta
from collections import defaultdict
import discord as dc
from discord import opus
from discord import app_commands
from discord.ext import commands
import yt_dlp as ytdl
import html

current_directory = os.path.dirname(os.path.abspath(__file__))
parent_directory = os.path.abspath(os.path.join(current_directory, ".."))
dll_path = os.path.join(parent_directory, "libopus-0.dll")

if not os.path.exists(dll_path):
    raise FileNotFoundError(f"Opus library not found at {dll_path}")

if not dc.opus.is_loaded():
    dc.opus.load_opus(dll_path)

if dc.opus.is_loaded():
    print("Opus library loaded successfully")
else:
    print("Failed to load Opus library")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('voicecommands')

YDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'default_search': 'ytsearch',
}

MAX_QUEUE_SIZE = 50

YOUTUBE_VIDEO_URL_REGEX = re.compile(
    r'^(https?://)?(www\.)?'
    r'(youtube\.com/watch\?v=|youtu\.be/)[\w-]{11}'
    r'(?:&\S*)?$'
)

def is_valid_youtube_video_url(url: str) -> bool:
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'ignoreerrors': True,
    }
    with ytdl.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            if info is None:
                logger.debug(f"URL validation failed: No info extracted for {url}")
                return False
            if 'entries' in info:
                logger.debug(f"URL validation failed: URL points to a playlist or multiple entries: {url}")
                return False
            if info.get('is_live'):
                logger.debug(f"URL validation failed: URL points to a live stream: {url}")
                return False
            logger.debug(f"URL validation succeeded for {url}")
            return True
        except Exception as e:
            logger.error(f"URL validation exception for {url}: {e}")
            return False

def sanitize_input(user_input: str) -> str:
    return html.escape(user_input)

class voicecommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild_data = defaultdict(lambda: {
            'last_activity_time': None,
            'voice_channel': None,
            'voice_client': None,
            'inactivity_task': None,
            'queue': [],
            'current_track': None,
            'is_moving': False,
        })

    async def inactivity_auto_leave(self, guild_id: int):
        await self.bot.wait_until_ready()
        while True:
            await asyncio.sleep(30)
            data = self.guild_data[guild_id]
            if data['last_activity_time']:
                elapsed = datetime.utcnow() - data['last_activity_time']
                if elapsed > timedelta(minutes=2):
                    if data['voice_client'] and data['voice_client'].is_connected():
                        await data['voice_client'].disconnect()
                        logger.info(f"Disconnected due to inactivity in guild {guild_id}")
                    data['voice_client'] = None
                    data['voice_channel'] = None
                    data['current_track'] = None
                    data['queue'].clear()
                    data['last_activity_time'] = None

    def after_play(self, error, guild_id: int):
        if error:
            logger.error(f"Player error in guild {guild_id}: {error}")
        data = self.guild_data[guild_id]
        if not data['is_moving']:
            coro = self.play_next(guild_id)
            asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

    async def play_next(self, guild_id: int):
        data = self.guild_data[guild_id]
        if not data['queue']:
            data['current_track'] = None
            logger.info(f"No more tracks in the queue for guild {guild_id}")
            return
        track = data['queue'].pop(0)
        data['current_track'] = track
        data['last_activity_time'] = datetime.utcnow()
        audio_source = dc.FFmpegPCMAudio(
            track['source_url'],
            before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
        )
        data['voice_client'].play(audio_source, after=lambda e: self.after_play(e, guild_id))
        logger.info(f"Now playing in guild {guild_id}: {track['title']}")

    @dc.app_commands.command(name="join_vc", description="Joins the voice channel you are in")
    async def join_vc(self, interaction: dc.Interaction):
        guild_id = interaction.guild.id
        user_voice = interaction.user.voice
        await interaction.response.send_message("Joining your voice channel.", ephemeral=True)
        if not user_voice or not user_voice.channel:
            await interaction.followup.send("You need to be in a voice channel first.", ephemeral=True)
            return
        user_channel = user_voice.channel
        data = self.guild_data[guild_id]
        if data['voice_client']:
            if data['voice_client'].channel.id == user_channel.id:
                await interaction.followup.send("I'm already in your voice channel.", ephemeral=True)
                return
            else:
                data['is_moving'] = True
                if data['voice_client'].is_playing():
                    data['voice_client'].pause()
                    logger.info(f"Paused playback before moving in guild {guild_id}")
                await data['voice_client'].disconnect()
                data['voice_client'] = None
                logger.info(f"Disconnected from previous voice channel in guild {guild_id}")
        data['voice_channel'] = user_channel
        data['voice_client'] = await user_channel.connect()
        data['last_activity_time'] = datetime.utcnow()
        if not data['inactivity_task'] or data['inactivity_task'].done():
            data['inactivity_task'] = asyncio.create_task(self.inactivity_auto_leave(guild_id))
        if data['current_track'] and not data['voice_client'].is_playing():
            audio_source = dc.FFmpegPCMAudio(
                data['current_track']['source_url'],
                before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
            )
            data['voice_client'].play(audio_source, after=lambda e: self.after_play(e, guild_id))
            logger.info(f"Resumed playing in guild {guild_id}: {data['current_track']['title']}")
        data['is_moving'] = False
        await interaction.followup.send(f"Joined {user_channel.name}.", ephemeral=True)

    @dc.app_commands.command(name="leave_vc", description="Leaves the current voice channel")
    async def leave_vc(self, interaction: dc.Interaction):
        guild_id = interaction.guild.id
        data = self.guild_data[guild_id]
        await interaction.response.send_message("Leaving the voice channel.", ephemeral=True)
        if data['voice_client'] and data['voice_client'].is_connected():
            await data['voice_client'].disconnect()
            logger.info(f"Left the voice channel in guild {guild_id}")
            data['voice_client'] = None
            data['voice_channel'] = None
            data['current_track'] = None
            data['queue'].clear()
            data['last_activity_time'] = None
            await interaction.followup.send("Left the voice channel and cleared the queue.", ephemeral=True)
        else:
            await interaction.followup.send("I'm not connected to any voice channel.", ephemeral=True)

    @dc.app_commands.command(name="play", description="Plays audio from a YouTube video link or search query")
    async def play(self, interaction: dc.Interaction, input: str):
        guild_id = interaction.guild.id
        data = self.guild_data[guild_id]
        input = sanitize_input(input)
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("You need to be in a voice channel first.", ephemeral=True)
            return
        user_channel = interaction.user.voice.channel
        if not data['voice_client'] or not data['voice_client'].is_connected():
            data['voice_channel'] = user_channel
            data['voice_client'] = await user_channel.connect()
            logger.info(f"Connected to {user_channel.name} in guild {guild_id}")
            data['last_activity_time'] = datetime.utcnow()
            if not data['inactivity_task'] or data['inactivity_task'].done():
                data['inactivity_task'] = asyncio.create_task(self.inactivity_auto_leave(guild_id))
        else:
            if data['voice_client'].channel.id != user_channel.id:
                await interaction.followup.send("I'm already connected to another voice channel. Use `/join_vc` to move me.", ephemeral=True)
                return
        is_url = bool(YOUTUBE_VIDEO_URL_REGEX.match(input))
        if is_url:
            if not is_valid_youtube_video_url(input):
                await interaction.followup.send("The provided link is not a valid YouTube video.", ephemeral=True)
                return
            video_url = input
            try:
                info = await asyncio.to_thread(lambda: ytdl.YoutubeDL(YDL_OPTS).extract_info(video_url, download=False))
                if not info:
                    await interaction.followup.send("Could not extract information from that link.", ephemeral=True)
                    return
                formats = info.get('formats', [])
                audio_format = next((f for f in formats if f.get('acodec') != 'none'), None)
                if not audio_format:
                    await interaction.followup.send("No suitable audio format found for this video.", ephemeral=True)
                    return
                audio_url = audio_format.get('url')
            except Exception as e:
                logger.error(f"Error extracting info for URL {video_url}: {e}")
                await interaction.followup.send("An error occurred while processing the video.", ephemeral=True)
                return
            track = {
                "title": info.get("title", "Unknown Title"),
                "url": video_url,
                "requester": interaction.user.display_name,
                "source_url": audio_url
            }
            if len(data['queue']) >= MAX_QUEUE_SIZE:
                await interaction.followup.send("The queue is full. Please wait for some tracks to finish.", ephemeral=True)
                return
            data['queue'].append(track)
            logger.info(f"Added to queue in guild {guild_id}: {track['title']}")
            if not data['current_track'] and not data['voice_client'].is_playing():
                await self.play_next(guild_id)
            await interaction.followup.send(f"Added **{track['title']}** to the queue.", ephemeral=True)
        else:
            search_query = f"ytsearch:{input}"
            try:
                info = await asyncio.to_thread(lambda: ytdl.YoutubeDL(YDL_OPTS).extract_info(search_query, download=False))
                if not info or 'entries' not in info or len(info['entries']) == 0:
                    await interaction.followup.send("No results found for that query.", ephemeral=True)
                    return
                first_entry = info['entries'][0]
                video_url = first_entry.get('webpage_url')
                if not video_url:
                    await interaction.followup.send("Could not retrieve video information.", ephemeral=True)
                    return
                if not is_valid_youtube_video_url(video_url):
                    await interaction.followup.send("The top search result is not a valid YouTube video.", ephemeral=True)
                    return
                info_inner = await asyncio.to_thread(lambda: ytdl.YoutubeDL(YDL_OPTS).extract_info(video_url, download=False))
                if not info_inner:
                    await interaction.followup.send("Could not extract information from the top search result.", ephemeral=True)
                    return
                formats = info_inner.get('formats', [])
                audio_format = next((f for f in formats if f.get('acodec') != 'none'), None)
                if not audio_format:
                    await interaction.followup.send("No suitable audio format found for the top search result.", ephemeral=True)
                    return
                audio_url = audio_format.get('url')
            except Exception as e:
                logger.error(f"Error processing search query '{input}': {e}")
                await interaction.followup.send("An error occurred while processing the search query.", ephemeral=True)
                return
            track = {
                "title": info_inner.get("title", "Unknown Title"),
                "url": video_url,
                "requester": interaction.user.display_name,
                "source_url": audio_url
            }
            if len(data['queue']) >= MAX_QUEUE_SIZE:
                await interaction.followup.send("The queue is full. Please wait for some tracks to finish.", ephemeral=True)
                return
            data['queue'].append(track)
            logger.info(f"Added to queue in guild {guild_id}: {track['title']}")
            if not data['current_track'] and not data['voice_client'].is_playing():
                await self.play_next(guild_id)
            await interaction.followup.send(f"Added **{track['title']}** to the queue.", ephemeral=True)

    @dc.app_commands.command(name="skip", description="Skips the current track")
    async def skip(self, interaction: dc.Interaction):
        guild_id = interaction.guild.id
        data = self.guild_data[guild_id]
        if data['voice_client'] and data['voice_client'].is_playing():
            data['voice_client'].stop()
            await interaction.response.send_message("Skipped the current track.")
            logger.info(f"Skipped track in guild {guild_id}")
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    @dc.app_commands.command(name="pause", description="Pauses the current track")
    async def pause(self, interaction: dc.Interaction):
        guild_id = interaction.guild.id
        data = self.guild_data[guild_id]
        if data['voice_client'] and data['voice_client'].is_playing():
            data['voice_client'].pause()
            await interaction.response.send_message("Paused the current track.")
            logger.info(f"Paused track in guild {guild_id}")
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    @dc.app_commands.command(name="resume", description="Resumes the current track")
    async def resume(self, interaction: dc.Interaction):
        guild_id = interaction.guild.id
        data = self.guild_data[guild_id]
        if data['voice_client'] and data['voice_client'].is_paused():
            data['voice_client'].resume()
            await interaction.response.send_message("Resumed the current track.")
            logger.info(f"Resumed track in guild {guild_id}")
        else:
            await interaction.response.send_message("There is nothing to resume.", ephemeral=True)

    @dc.app_commands.command(name="clear", description="Stops playback and clears the queue")
    async def clear(self, interaction: dc.Interaction):
        guild_id = interaction.guild.id
        data = self.guild_data[guild_id]
        data['queue'].clear()
        if data['voice_client'] and data['voice_client'].is_playing():
            data['voice_client'].stop()
        data['current_track'] = None
        await interaction.response.send_message("Stopped playback and cleared the queue.")
        logger.info(f"Cleared queue and stopped playback in guild {guild_id}")

    @dc.app_commands.command(name="queue", description="Displays the current queue")
    async def queue_cmd(self, interaction: dc.Interaction):
        guild_id = interaction.guild.id
        data = self.guild_data[guild_id]
        if not data['current_track'] and not data['queue']:
            await interaction.response.send_message("The queue is empty.", ephemeral=True)
            return
        embed = dc.Embed(title="Music Queue", color=dc.Color.blue())
        if data['current_track']:
            embed.add_field(
                name="Now Playing",
                value=f"**{data['current_track']['title']}**\nRequested by: {data['current_track']['requester']}",
                inline=False
            )
        else:
            embed.add_field(name="Now Playing", value="Nothing currently playing.", inline=False)
        if data['queue']:
            queue_description = "\n".join(
                f"{i}. **{t['title']}** (Requested by: {t['requester']})"
                for i, t in enumerate(data['queue'], start=1)
            )
            embed.add_field(name="Up Next", value=queue_description, inline=False)
        else:
            embed.add_field(name="Queue", value="The queue is empty.", inline=False)
        await interaction.response.send_message(embed=embed)

    @dc.app_commands.command(name="remove", description="Removes a track from the queue by its index")
    async def remove(self, interaction: dc.Interaction, index: int):
        guild_id = interaction.guild.id
        data = self.guild_data[guild_id]
        index = index - 1
        if 0 <= index < len(data['queue']):
            removed = data['queue'].pop(index)
            await interaction.response.send_message(f"Removed **{removed['title']}** from the queue.")
            logger.info(f"Removed track from queue in guild {guild_id}: {removed['title']}")
        else:
            await interaction.response.send_message("Invalid track index.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(voicecommands(bot))
