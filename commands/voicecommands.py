from datetime import datetime, timedelta
import sys
import nacl
import traceback
import yt_dlp as ytdl
import re
import discord as dc
from discord import opus
from discord import app_commands
from discord.ext import commands
import asyncio
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('voicecommands')

YDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'default_search': 'ytsearch',
}

current_directory = os.path.dirname(os.path.abspath(__file__))
parent_directory = os.path.abspath(os.path.join(current_directory, ".."))
dll_path = os.path.join(parent_directory, "libopus-0.dll")

if not os.path.exists(dll_path):
    raise FileNotFoundError(f"Opus library not found at {dll_path}")
else:
    dc.opus.load_opus(dll_path)

if dc.opus.is_loaded():
    logger.info("Opus library loaded successfully")
else:
    logger.error("Failed to load Opus library")

class voicecommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_activity_time = None
        self.voice_channel = None
        self.voice_client = None
        self.inactivity_task = None
        self.queue = []
        self.current_track = None
        self.is_moving = False  # Flag to indicate if the bot is moving voice channels

    async def inactivityAutoLeave(self):
        while self.voice_client and self.voice_client.is_connected():
            if self.last_activity_time and datetime.utcnow() - self.last_activity_time > timedelta(minutes=2):
                await self.voice_client.disconnect()
                logger.info("Disconnected due to inactivity.")
                self.voice_client = None
                self.last_activity_time = None
                return
            await asyncio.sleep(30)

    def after_play(self, error):
        if error:
            logger.error(f"Player error: {error}")

        # Only proceed if not moving to another voice channel
        if not self.is_moving:
            coro = self.play_next()
            future = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
            try:
                future.result()
            except Exception as e:
                logger.error(f"Error in after_play coroutine: {e}")

    async def play_next(self):
        if not self.queue or not self.voice_client or not self.voice_client.is_connected():
            self.current_track = None
            logger.info("No more tracks in the queue or voice client disconnected.")
            return

        track = self.queue.pop(0)
        self.current_track = track

        self.last_activity_time = datetime.utcnow()

        audio_source = dc.FFmpegPCMAudio(
            track['source_url'],
            before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
        )
        self.voice_client.play(audio_source, after=self.after_play)
        logger.info(f"Now playing: {track['title']}")

    def extract_info(self, query: str):
        ydl_opts = YDL_OPTS.copy()

        youtube_pattern = re.compile(r"(youtube\.com|youtu\.be)")

        if youtube_pattern.search(query):
            if "list=" in query:
                ydl_opts['extract_flat'] = False
                with ytdl.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(query, download=False)
                    if 'entries' in info:
                        logger.info(f"Extracted {len(info['entries'])} tracks from playlist")
                        return info['entries'], True
                    else:
                        logger.info("Extracted a single track from playlist URL")
                        return [info], False
            else:
                with ytdl.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(query, download=False)
                    logger.info(f"Extracted single track: {info.get('title', 'Unknown title')}")
                    return [info], False
        else:
            search_query = f"ytsearch:{query}"
            with ytdl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_query, download=False)
                if 'entries' in info and info['entries']:
                    logger.info(f"Extracted search result: {info['entries'][0].get('title', 'Unknown title')}")
                    return [info['entries'][0]], False
                else:
                    logger.info("No search results found")
                    return [], False

    @dc.app_commands.command(name="join_vc", description="Joins the voice channel you are currently connected to")
    async def joinVC(self, interaction: dc.Interaction):
        await interaction.response.send_message("Joining voice channel...", ephemeral=True)
        try:
            if interaction.user.voice is None or interaction.user.voice.channel is None:
                await interaction.followup.send("You need to be connected to a voice channel first.", ephemeral=True)
                return

            user_voice_channel = interaction.user.voice.channel

            if self.voice_client:
                if self.voice_client.channel.id == user_voice_channel.id:
                    await interaction.followup.send("I'm already in your voice channel!", ephemeral=True)
                    return
                else:
                    self.is_moving = True  # Indicate that the bot is moving
                    # Pause current playback if any
                    if self.voice_client.is_playing():
                        self.voice_client.pause()
                        logger.info("Paused current playback before moving.")
                    await self.voice_client.disconnect()
                    self.voice_client = None
                    logger.info("Disconnected from the previous voice channel.")
                    self.is_moving = False  # Reset the moving flag

            self.voice_channel = user_voice_channel
            self.voice_client = await self.voice_channel.connect()
            logger.info(f"Connected to voice channel: {self.voice_channel.name}")
            self.last_activity_time = datetime.utcnow()

            if self.inactivity_task is None or self.inactivity_task.done():
                self.inactivity_task = asyncio.create_task(self.inactivityAutoLeave())

            # Resume playback if there was a track paused
            if self.current_track and not self.voice_client.is_playing():
                audio_source = dc.FFmpegPCMAudio(
                    self.current_track['source_url'],
                    before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
                )
                self.voice_client.play(audio_source, after=self.after_play)
                logger.info(f"Resumed playing: {self.current_track['title']}")

            await interaction.followup.send(f"Joined {self.voice_channel.name}!", ephemeral=True)

        except Exception as e:
            logger.error(f"Couldn't join VC: {e}")
            await interaction.followup.send(f"Couldn't join the voice channel: {e}", ephemeral=True)

    @dc.app_commands.command(name="leave_vc", description="Leaves the voice channel the bot is currently connected to")
    async def leaveVC(self, interaction: dc.Interaction):
        await interaction.response.send_message("Leaving voice channel...", ephemeral=True)
        if self.voice_client and self.voice_client.is_connected():
            await self.voice_client.disconnect()
            logger.info("Left the voice channel.")
            self.voice_client = None
            self.last_activity_time = None
            self.current_track = None  # Optionally, you can set current_track to None
            await interaction.followup.send("Left the voice channel.", ephemeral=True)
        else:
            await interaction.followup.send("I am not connected to any voice channel.", ephemeral=True)

    @dc.app_commands.command(name="play", description="Plays audio in the voice channel")
    async def play(self, interaction: dc.Interaction, input: str):
        await interaction.response.defer(ephemeral=False, thinking=True)

        try:
            if interaction.user.voice is None or interaction.user.voice.channel is None:
                await interaction.followup.send("You need to be connected to a voice channel to use this command.", ephemeral=True)
                return

            user_voice_channel = interaction.user.voice.channel

            if not self.voice_client or not self.voice_client.is_connected():
                self.voice_channel = user_voice_channel
                self.voice_client = await self.voice_channel.connect()
                logger.info(f"Connected to voice channel: {self.voice_channel.name}")
                self.last_activity_time = datetime.utcnow()

                if self.inactivity_task is None or self.inactivity_task.done():
                    self.inactivity_task = asyncio.create_task(self.inactivityAutoLeave())

                await interaction.followup.send(f"Joined {self.voice_channel.name} and added the track to the queue.", ephemeral=True)
            else:
                # Optionally, you can check if the bot is in the same channel as the user
                if self.voice_client.channel.id != user_voice_channel.id:
                    await interaction.followup.send("I'm already connected to another voice channel. Use `/join_vc` to move me.", ephemeral=True)
                    return

            results, is_playlist = self.extract_info(input)
            if not results:
                await interaction.followup.send("No results found for that query.")
                return

            for entry in results:
                # Use yt_dlp to get the direct audio URL
                with ytdl.YoutubeDL(YDL_OPTS) as ydl:
                    info = ydl.extract_info(entry['webpage_url'], download=False)
                    # Choose the best audio format available
                    formats = info.get('formats', [])
                    audio_format = next((f for f in formats if f.get('acodec') != 'none'), None)
                    if not audio_format:
                        await interaction.followup.send(f"Couldn't find a suitable audio format for {entry.get('title', 'Unknown Title')}.")
                        continue
                    audio_url = audio_format['url']

                track = {
                    "title": entry.get("title", "Unknown title"),
                    "url": entry.get("webpage_url", ""),
                    "requester": interaction.user.display_name,
                    "source_url": audio_url
                }
                self.queue.append(track)
                logger.info(f"Added to queue: {track['title']}")

            if self.current_track is None and not self.voice_client.is_playing():
                await self.play_next()

            if is_playlist:
                await interaction.followup.send(f"Added a playlist with {len(results)} tracks to the queue.")
            else:
                await interaction.followup.send(f"Added **{results[0]['title']}** to the queue.")

        except Exception as e:
            logger.error(f"Error while playing: {e}")
            await interaction.followup.send("Failed to play the requested track.")
            traceback.print_exc()

    @dc.app_commands.command(name="skip", description="Skips the current track")
    async def skip(self, interaction: dc.Interaction):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
            await interaction.response.send_message("Skipped the current track.")
            logger.info("Skipped the current track.")
        else:
            await interaction.response.send_message("Nothing is playing.")

    @dc.app_commands.command(name="pause", description="Pauses the current track")
    async def pause(self, interaction: dc.Interaction):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            await interaction.response.send_message("Paused the current track.")
            logger.info("Paused the current track.")
        else:
            await interaction.response.send_message("Nothing is playing.")

    @dc.app_commands.command(name="resume", description="Resumes the current track")
    async def resume(self, interaction: dc.Interaction):
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            await interaction.response.send_message("Resumed the current track.")
            logger.info("Resumed the current track.")
        else:
            await interaction.response.send_message("There is nothing to resume.")

    @dc.app_commands.command(name="clear", description="Stops playback and clears the queue")
    async def clear(self, interaction: dc.Interaction):
        self.queue.clear()
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
        self.current_track = None
        await interaction.response.send_message("Stopped playback and cleared the queue.")
        logger.info("Cleared the queue and stopped playback.")

    @dc.app_commands.command(name="queue", description="Displays the current queue")
    async def queue_cmd(self, interaction: dc.Interaction):
        if not self.current_track and not self.queue:
            await interaction.response.send_message("The queue is empty.", ephemeral=True)
            return

        embed = dc.Embed(title="Music Queue", color=dc.Color.blue())

        if self.current_track:
            embed.add_field(
                name="Now Playing",
                value=f"**{self.current_track['title']}**\nRequested by: {self.current_track['requester']}",
                inline=False
            )
        else:
            embed.add_field(name="Now Playing", value="Nothing currently playing.", inline=False)

        if self.queue:
            queue_description = ""
            for i, track in enumerate(self.queue, start=1):
                queue_description += f"{i}. **{track['title']}** (Requested by: {track['requester']})\n"
            embed.add_field(name="Up Next", value=queue_description, inline=False)
        else:
            embed.add_field(name="Queue", value="The queue is empty.", inline=False)

        await interaction.response.send_message(embed=embed)

    @dc.app_commands.command(name="remove", description="Removes a track from the queue by its index")
    async def remove(self, interaction: dc.Interaction, index: int):
        index = index - 1
        if 0 <= index < len(self.queue):
            removed = self.queue.pop(index)
            await interaction.response.send_message(f"Removed **{removed['title']}** from the queue.")
            logger.info(f"Removed track from queue: {removed['title']}")
        else:
            await interaction.response.send_message("Invalid track index.")

async def setup(bot):
    await bot.add_cog(voicecommands(bot))
