import os
import asyncio
import logging
import json
from datetime import datetime, timedelta
from collections import defaultdict, deque
import discord as dc
from discord import app_commands
from discord.ext import commands
import yt_dlp as ytdl

current_directory = os.path.dirname(os.path.abspath(__file__))
parent_directory = os.path.abspath(os.path.join(current_directory, ".."))
config_path = os.path.join(parent_directory, "config.json")
with open(config_path, 'r') as config_file:
    config = json.load(config_file)

FFMPEG_PATH = config['ffmpeg_path']
YTDLP_OPTS = config['yt_dlp_options']
MAX_QUEUE_SIZE = config['max_queue_size']
INACTIVITY_TIMEOUT = config['inactivity_timeout']

def format_duration(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02}:{secs:02}"
    else:
        return f"{minutes}:{secs:02}"

class playercommands(commands.Cog):
    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.logger = logging.getLogger('playercommands')
        self.music_queue = defaultdict(deque)
        self.current_track = defaultdict(lambda: None)
        self.ytdl = ytdl.YoutubeDL(YTDLP_OPTS)
        self.paused = defaultdict(bool)
        
        self.skipped = defaultdict(bool)

    async def update_inactivity_queue(self, interaction: dc.Interaction):
        guild_id = interaction.guild.id
        voice_commands_cog = self.bot.get_cog('voicecommands')
        if voice_commands_cog:
            await voice_commands_cog.update_last_activity(guild_id)
            self.logger.debug(f"Updated last activity for guild {guild_id}")
        else:
            self.logger.warning("voicecommands Cog not found")

    async def play_next_track(self, guild_id: int):
        if not self.music_queue[guild_id]:
            self.logger.info(f"No more tracks in the queue for guild {guild_id}.")
            self.current_track[guild_id] = None
            return

        track = self.music_queue[guild_id].popleft()
        title = track['title']
        url = track['url']
        duration = track.get('duration', 0)
        self.logger.info(f"Now playing: {title} in guild {guild_id}.")
        self.current_track[guild_id] = track

        voice_commands_cog = self.bot.get_cog('voicecommands')
        if voice_commands_cog:
            await voice_commands_cog.update_last_activity(guild_id)
        else:
            self.logger.warning("voicecommands Cog not found when updating last activity.")

        voice_client = await voice_commands_cog.get_voice_client(guild_id) if voice_commands_cog else None
        if not voice_client:
            self.logger.error(f"VoiceClient not found for guild {guild_id}.")
            self.current_track[guild_id] = None
            return

        ffmpeg_options = {
            'options': '-vn'
        }

        before_options = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
        source = dc.FFmpegPCMAudio(url, before_options=before_options, **ffmpeg_options)

        def after_playing(error):
            if error:
                self.logger.error(f"Error playing {title} in guild {guild_id}: {error}")

            if self.skipped[guild_id]:
                self.skipped[guild_id] = False
                self.logger.info(f"Track '{title}' was skipped in guild {guild_id}, not looping.")
                if not self.paused[guild_id]:
                    self.bot.loop.create_task(self.play_next_track(guild_id))
                return

            current = self.current_track[guild_id]
            if current and current.get('loop', False) and not self.paused[guild_id]:
                self.music_queue[guild_id].appendleft(current)
                self.logger.info(f"Looping the track '{current['title']}' in guild {guild_id}.")
                self.bot.loop.create_task(self.play_next_track(guild_id))
            else:
                if not self.paused[guild_id]:
                    self.bot.loop.create_task(self.play_next_track(guild_id))
                else:
                    self.logger.info(f"Playback is paused in guild {guild_id}. Not proceeding to next track.")

        voice_client.play(source, after=after_playing)

        async def playback_activity_updater():
            while voice_client.is_playing() and not self.paused[guild_id]:
                await voice_commands_cog.update_last_activity(guild_id)
                self.logger.debug(f"Playback activity updater: Updated last activity for guild {guild_id}.")
                await asyncio.sleep(30)

        self.bot.loop.create_task(playback_activity_updater())

    async def add_tracks_to_queue(self, guild_id: int, info: dict, playlist_origin: str = None):
        """Add one or multiple tracks from a single track or a playlist to the queue."""
        entries = info['entries'] if 'entries' in info else [info]
        for entry in entries:
            url = entry['url']
            title = entry.get('title', 'Unknown Title')
            duration = entry.get('duration', 0)
            track = {
                'title': title,
                'url': url,
                'duration': duration,
                'playlist_origin': playlist_origin,
                'loop': False
            }
            if len(self.music_queue[guild_id]) >= MAX_QUEUE_SIZE:
                self.logger.info(f"Queue is full for guild {guild_id}, skipping remaining tracks.")
                break
            self.music_queue[guild_id].append(track)
            self.logger.info(f"Added '{title}' to the queue in guild {guild_id}")

    def is_playlist(self, info: dict) -> bool:
        return 'entries' in info and len(info['entries']) > 1

    @app_commands.command(name="play", description="Plays a song or playlist from a YouTube URL or search query")
    async def play(self, interaction: dc.Interaction, query: str):
        guild_id = interaction.guild.id
        self.logger.info(f"Received play command in guild {guild_id} with query: {query}")

        await interaction.response.defer(ephemeral=True)
        await self.update_inactivity_queue(interaction)

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("You are not connected to a voice channel", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        voice_commands_cog = self.bot.get_cog('voicecommands')
        voice_client = await voice_commands_cog.ensure_voice_connection(guild_id, voice_channel, interaction)

        if not voice_client:
            return

        try:
            info = await asyncio.to_thread(lambda: self.ytdl.extract_info(query, download=False))
        except Exception as e:
            self.logger.error(f"Error extracting info for query '{query}': {e}")
            await interaction.followup.send("An error occurred while processing your request", ephemeral=True)
            return

        if self.is_playlist(info):
            playlist_title = info.get('title', 'Unknown Playlist')
            await self.add_tracks_to_queue(guild_id, info, playlist_origin=playlist_title)
            message = f"Added playlist **{playlist_title}** with {len(info['entries'])} tracks to the queue."
        else:
            entries = info['entries'] if 'entries' in info else [info]
            await self.add_tracks_to_queue(guild_id, {'entries': entries})
            message = f"Added **{entries[0].get('title', 'Unknown Title')}** to the queue."

        if not voice_client.is_playing() and not self.paused[guild_id]:
            await self.play_next_track(guild_id)

        await interaction.followup.send(message, ephemeral=True)

    @app_commands.command(name="pause", description="Pauses the current song")
    async def pause(self, interaction: dc.Interaction):
        guild_id = interaction.guild.id
        self.logger.info(f"Received pause command in guild {guild_id}")
        await interaction.response.defer(ephemeral=True)

        voice_commands_cog = self.bot.get_cog('voicecommands')
        voice_client = await voice_commands_cog.get_voice_client(guild_id) if voice_commands_cog else None

        if not voice_client or not voice_client.is_connected():
            await interaction.followup.send("I'm not connected to any voice channel", ephemeral=True)
            return

        if not voice_client.is_playing():
            await interaction.followup.send("I'm not playing anything right now", ephemeral=True)
            return

        if voice_client.is_paused():
            await interaction.followup.send("The playback is already paused", ephemeral=True)
            return

        voice_client.pause()
        self.paused[guild_id] = True
        await interaction.followup.send("Paused the current song", ephemeral=True)
        self.logger.info(f"Paused playback in guild {guild_id}.")

    @app_commands.command(name="resume", description="Resumes the current song")
    async def resume(self, interaction: dc.Interaction):
        guild_id = interaction.guild.id
        self.logger.info(f"Received resume command in guild {guild_id}")
        await interaction.response.defer(ephemeral=True)

        voice_commands_cog = self.bot.get_cog('voicecommands')
        voice_client = await voice_commands_cog.get_voice_client(guild_id) if voice_commands_cog else None

        if not voice_client or not voice_client.is_connected():
            await interaction.followup.send("I'm not connected to any voice channel", ephemeral=True)
            return

        if not voice_client.is_paused():
            await interaction.followup.send("The playback is not paused.", ephemeral=True)
            return

        voice_client.resume()
        self.paused[guild_id] = False
        await interaction.followup.send("Resumed the current song", ephemeral=True)
        self.logger.info(f"Resumed playback in guild {guild_id}")

    @app_commands.command(name="skip", description="Skips the current song in queue")
    async def skip(self, interaction: dc.Interaction):
        guild_id = interaction.guild.id
        self.logger.info(f"Received skip command in guild {guild_id}")
        await self.update_inactivity_queue(interaction)

        voice_commands_cog = self.bot.get_cog('voicecommands')
        voice_client = await voice_commands_cog.get_voice_client(guild_id) if voice_commands_cog else None
        if not voice_client or not voice_client.is_connected():
            await interaction.response.send_message("I'm not connected to any voice channel")
            return

        if not voice_client.is_playing():
            await interaction.response.send_message("I'm not playing anything right now")
            return

        self.skipped[guild_id] = True
        voice_client.stop()
        self.logger.info(f"Skipped current track in guild {guild_id}.")
        await interaction.response.send_message("Skipped the current song")

    @app_commands.command(name="remove", description="Removes a specific song from the queue by its position number")
    async def remove(self, interaction: dc.Interaction, position: int):
        guild_id = interaction.guild.id
        self.logger.info(f"Received remove command in guild {guild_id} for position: {position}")

        await interaction.response.defer(ephemeral=True)
        await self.update_inactivity_queue(interaction)
        
        if guild_id not in self.music_queue or not self.music_queue[guild_id]:
            await interaction.followup.send("The queue is currently empty", ephemeral=True)
            return

        if position < 1 or position > len(self.music_queue[guild_id]):
            await interaction.followup.send(f"Invalid position. Please enter a number between 1 and {len(self.music_queue[guild_id])}", ephemeral=True)
            return

        queue_list = list(self.music_queue[guild_id])
        removed_track = queue_list.pop(position - 1)
        self.music_queue[guild_id] = deque(queue_list)

        await interaction.followup.send(f"Removed **{removed_track['title']}** from the queue.", ephemeral=True)
        self.logger.info(f"Removed '{removed_track['title']}' from guild {guild_id}'s queue at position {position}")

    @app_commands.command(name="clear", description="Stops playback and clears the queue")
    async def clear(self, interaction: dc.Interaction):
        guild_id = interaction.guild.id
        self.logger.info(f"Received stop command in guild {guild_id}")

        await self.update_inactivity_queue(interaction)
        voice_commands_cog = self.bot.get_cog('voicecommands')
        voice_client = await voice_commands_cog.get_voice_client(guild_id) if voice_commands_cog else None
        if not voice_client or not voice_client.is_connected():
            await interaction.response.send_message("I'm not connected to any voice channel", ephemeral=True)
            return

        if voice_client.is_playing():
            self.skipped[guild_id] = True
            voice_client.stop()
            self.logger.info(f"Stopped playback in guild {guild_id}")

        self.music_queue[guild_id].clear()
        self.current_track[guild_id] = None
        self.logger.info(f"Cleared the queue in guild {guild_id}")

        await interaction.response.send_message("Stopped playback and cleared the queue", ephemeral=True)

    @app_commands.command(name="queue", description="Displays the current music queue")
    async def queue_cmd(self, interaction: dc.Interaction):
        guild_id = interaction.guild.id
        self.logger.info(f"Received queue command in guild {guild_id}")

        await self.update_inactivity_queue(interaction)

        current_track = self.current_track[guild_id]
        if current_track:
            looping_indicator = " (Looping)" if current_track.get('loop', False) else ""
            duration_str = format_duration(current_track.get('duration', 0))
            playlist_info = f" (from {current_track['playlist_origin']})" if current_track.get('playlist_origin') else ""
            currently_playing = f"**Now Playing:** {current_track['title']}{looping_indicator} [{duration_str}]{playlist_info}\n\n"
        else:
            currently_playing = "No song is currently playing\n\n"

        if not self.music_queue[guild_id]:
            await interaction.response.send_message(currently_playing + "The queue is currently empty")
            return

        queue_list = "\n".join([
            f"{idx + 1}. {track['title']} [{format_duration(track.get('duration', 0))}]" +
            (f" (from {track['playlist_origin']})" if track.get('playlist_origin') else "")
            for idx, track in enumerate(self.music_queue[guild_id])
        ])
        embed = dc.Embed(title="Music Queue", description=currently_playing + queue_list, color=dc.Color.blue())

        await interaction.response.send_message(embed=embed)
        self.logger.info(f"Displayed queue for guild {guild_id}")

    @app_commands.command(name="loop", description="Toggles looping of the current song")
    async def loop_command(self, interaction: dc.Interaction):
        guild_id = interaction.guild.id
        self.logger.info(f"Received loop command in guild {guild_id}")

        await interaction.response.defer(ephemeral=True)
        await self.update_inactivity_queue(interaction)

        current = self.current_track[guild_id]
        if current is None:
            await interaction.followup.send("No track is currently playing.")
            return

        current['loop'] = not current.get('loop', False)
        state = "enabled" if current['loop'] else "disabled"
        await interaction.followup.send(f"Loop {state} for the current song: {current['title']}")
        self.logger.info(f"Loop {state} for '{current['title']}' in guild {guild_id}.")

async def setup(bot):
    await bot.add_cog(playercommands(bot, config))
