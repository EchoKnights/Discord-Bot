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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    print("Opus library loaded successfully")
else:
    print("Failed to load Opus library")

class voicecommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_activity_time = None
        self.voice_channel = None
        self.voice_client = None
        self.inactivity_task = None
        self.queue = []
        self.current_track = None

    async def inactivityAutoLeave(self):
        while self.voice_client and self.voice_client.is_connected():
            if self.last_activity_time and datetime.utcnow() - self.last_activity_time > timedelta(minutes=2):
                await self.voice_client.disconnect()
                self.voice_client = None
                self.last_activity_time = None
                return
            await asyncio.sleep(30)

    def after_play(self, error):
        if error:
            print(f"Player error: {error}")

        coro = self.play_next()
        future = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
        future.result()

    async def play_next(self):
        if not self.queue or not self.voice_client or not self.voice_client.is_connected():
            self.current_track = None
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
                        print(f"Extracted {len(info['entries'])} tracks from playlist")
                        return info['entries'], True
                    else:
                        print("Extracted a single track from playlist URL")
                        return [info], False
            else:
                with ytdl.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(query, download=False)
                    print(f"Extracted single track: {info.get('title', 'Unknown title')}")
                    return [info], False
        else:
            search_query = f"ytsearch:{query}"
            with ytdl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_query, download=False)
                if 'entries' in info and info['entries']:
                    print(f"Extracted search result: {info['entries'][0].get('title', 'Unknown title')}")
                    return [info['entries'][0]], False
                else:
                    print("No search results found")
                    return [], False

    @dc.app_commands.command(name="join_vc", description="Joins the voice channel you are currently connected to")
    async def joinVC(self, interaction: dc.Interaction):
        await interaction.response.send_message("Joining")
        try:
            if interaction.user.voice is None or interaction.user.voice.channel is None:
                await interaction.followup.send("Connect to the voice channel you want me to connect to")
                return

            self.voice_channel = interaction.user.voice.channel
            self.voice_client = await self.voice_channel.connect()
            self.last_activity_time = datetime.utcnow()

            if self.inactivity_task is None or self.inactivity_task.done():
                self.inactivity_task = asyncio.create_task(self.inactivityAutoLeave())

        except Exception as e:
            print(f'Couldnt join vc due to {e}')

    @dc.app_commands.command(name="leave_vc", description="Leaves the voice channel the bot is currently connected to")
    async def leaveVC(self, interaction: dc.Interaction):
        await interaction.response.send_message("Leaving")
        if self.voice_client and self.voice_client.is_connected():
            await self.voice_client.disconnect()
            self.voice_client = None
            self.last_activity_time = None
        else:
            await interaction.followup.send("I am not connected to a voice channel")


    @dc.app_commands.command(name="play", description="Plays audio in the voice channel")
    async def play(self, interaction: dc.Interaction, input: str):
        if not self.voice_client or not self.voice_client.is_connected():
            await interaction.response.send_message("I am not connected to a voice channel")
            return

        await interaction.response.defer(ephemeral=False, thinking=True)

        try:
            results, is_playlist = self.extract_info(input)
            if not results:
                await interaction.followup.send("No results found for that query")
                return

            for entry in results:
                # Use yt_dlp to get the direct audio URL
                with ytdl.YoutubeDL(YDL_OPTS) as ydl:
                    info = ydl.extract_info(entry['webpage_url'], download=False)
                    audio_url = info['url']  # This should be the direct audio stream URL

                track = {
                    "title": entry.get("title", "Unknown title"),
                    "url": entry.get("webpage_url", ""),
                    "requester": interaction.user.display_name,
                    "source_url": audio_url
                }
                self.queue.append(track)
                print(f"Added to queue: {track['title']}")

            if self.current_track is None and not self.voice_client.is_playing():
                await self.play_next()

            if is_playlist:
                await interaction.followup.send(f"Added a playlist with {len(results)} tracks to the queue")
            else:
                await interaction.followup.send(f"Added {results[0]['title']} to the queue")
        except Exception as e:
            print(f"Error while playing: {e}")
            await interaction.followup.send("Failed to play the requested track")
            traceback.print_exc()

        self.last_activity_time = datetime.utcnow()  # Update the last activity time
    
    @dc.app_commands.command(name="skip", description="Skips the current track")
    async def skip(self, interaction: dc.Interaction):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
            await interaction.response.send_message("Skipped the current track")
        else:
            await interaction.response.send_message("Nothing is playing")

    @dc.app_commands.command(name="pause", description="Pauses the current track")
    async def pause(self, interaction: dc.Interaction):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            await interaction.response.send_message("Paused the current track")
        else:
            await interaction.response.send_message("Nothing is playing.")

    @dc.app_commands.command(name="resume", description="Resumes the current track")
    async def resume(self, interaction: dc.Interaction):
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            await interaction.response.send_message("Resumed the current track")
        else:
            await interaction.response.send_message("There is nothing to resume")

    @dc.app_commands.command(name="clear", description="Stops playback and clears the queue")
    async def clear(self, interaction: dc.Interaction):
        self.queue.clear()
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
        self.current_track = None
        await interaction.response.send_message("Stopped playback and cleared the queue")

    @dc.app_commands.command(name="queue", description="Displays the current queue")
    async def queue(self, interaction: dc.Interaction):
        embed = dc.Embed(title="Music Queue", color=dc.Color.blue())

        if self.current_track:
            embed.add_field(
                name="Now Playing",
                value=f"**{self.current_track['title']}**\nRequested by: {self.current_track['requester']}",
                inline=False
            )
        else:
            embed.add_field(name="Now Playing", value="Nothing currently playing", inline=False)

        if self.queue:
            queue_description = ""
            for i, track in enumerate(self.queue, start=1):
                queue_description += f"{i}. **{track['title']}** (Requested by: {track['requester']})\n"
            embed.add_field(name="Up Next", value=queue_description, inline=False)
        else:
            embed.add_field(name="Queue", value="The queue is empty", inline=False)

        await interaction.response.send_message(embed=embed)

    @dc.app_commands.command(name="remove", description="Removes a track from the queue by its index")
    async def remove(self, interaction: dc.Interaction, index: int):
        index = index - 1
        if 0 <= index < len(self.queue):
            removed = self.queue.pop(index)
            await interaction.response.send_message(f"Removed {removed['title']} from the queue")
        else:
            await interaction.response.send_message("Invalid track index")

async def setup(bot):
    await bot.add_cog(voicecommands(bot))