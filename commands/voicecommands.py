import re
import os
import asyncio
import logging

from datetime import datetime, timedelta
from collections import defaultdict
import discord as dc
from discord.ext import commands
import yt_dlp as ytdl
import html
import json

#Finding and Loading Opus (this took me 100 years to figure out because im not the smartest)
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

#config stuff
config_path = os.path.join(parent_directory, "config.json")
with open(config_path, 'r') as config_file:
    config = json.load(config_file)
INACTIVITY_TIMEOUT = config['inactivity_timeout']

#Logging (i barely understand how this works bro)
logging.basicConfig(
    level=logging.INFO,  # (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s',
    handlers=[
        logging.FileHandler("voicecommands.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('voicecommands')

class voicecommands(commands.Cog): 
    def __init__(self, bot):
        self.bot = bot
        self.guild_voice_clients = {}
        self.guild_last_activity = defaultdict(lambda: datetime.utcnow())
        self.inactivity_timeout = INACTIVITY_TIMEOUT
        self.inactivity_task = self.bot.loop.create_task(self.inactivity_monitor())
        self.logger = logger
        self.logger.info("voicecommands Cog initialized.")

    async def inactivity_monitor(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = datetime.utcnow()
            for guild_id, last_activity in list(self.guild_last_activity.items()):
                voice_client = self.guild_voice_clients.get(guild_id)
                
                if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
                    self.logger.debug(f"Guild {guild_id} is actively playing or paused. Skipping inactivity check")
                    continue 
                
                elapsed = (now - last_activity).total_seconds()
                self.logger.debug(f"Checking guild {guild_id}: elapsed time {elapsed} seconds.")
                
                if elapsed > self.inactivity_timeout:
                    if voice_client:
                        await voice_client.disconnect()
                        self.logger.info(f"Disconnected from guild {guild_id} due to {elapsed} seconds of inactivity.")
                        del self.guild_voice_clients[guild_id]
                    del self.guild_last_activity[guild_id]
            await asyncio.sleep(30)


    #For useage with other cogs(playercommands)
    async def update_last_activity(self, guild_id: int):
        self.guild_last_activity[guild_id] = datetime.utcnow()
        self.logger.debug(f"Updated last activity for guild {guild_id} to {self.guild_last_activity[guild_id]}")

    async def get_voice_client(self, guild_id: int):
        return self.guild_voice_clients.get(guild_id, None)

    async def ensure_voice_connection(self, guild_id: int, voice_channel: dc.VoiceChannel, interaction: dc.Interaction):
        if guild_id in self.guild_voice_clients:
            voice_client = self.guild_voice_clients[guild_id]
            if voice_client.channel.id != voice_channel.id:
                await voice_client.move_to(voice_channel)
                self.text_channel = interaction.channel
                self.logger.info(f"Moved to {voice_channel.name} in guild {guild_id}")
        else:
            voice_client = await voice_channel.connect()
            self.guild_voice_clients[guild_id] = voice_client
            self.logger.info(f"Connected to {voice_channel.name} in guild {guild_id}")
            self.text_channel = interaction.channel
        self.guild_last_activity[guild_id] = datetime.utcnow()
        self.text_channel = interaction.channel
        return self.guild_voice_clients[guild_id]

    @dc.app_commands.command(name="join_vc", description="Makes the bot join the voice channel you're connected to")
    async def join(self, interaction: dc.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("You are not connected to a voice channel", ephemeral=True)
            return
        
        voice_channel = interaction.user.voice.channel
        guild_id = interaction.guild.id     

        if guild_id in self.guild_voice_clients:
            voice_client = self.guild_voice_clients[guild_id]
            if voice_client.channel.id != voice_channel.id:
                await interaction.response.send_message(f"Joined {voice_channel.name}.")
            else:
                await interaction.response.send_message("I am already in that voice channel")
        else:
            await interaction.response.send_message(f"Joined {voice_channel.name}.")

        await self.ensure_voice_connection(guild_id, voice_channel, interaction)

    @dc.app_commands.command(name="leave_vc", description="Bot leaves the current voice channel")
    async def leave(self, interaction: dc.Interaction):
        guild_id = interaction.guild.id

        if guild_id not in self.guild_voice_clients:
            await interaction.response.send_message("I'm not connected to any voice channel", ephemeral=True)
            return

        voice_client = self.guild_voice_clients[guild_id]
        await voice_client.disconnect()
        del self.guild_voice_clients[guild_id]
        del self.guild_last_activity[guild_id]
        await interaction.response.send_message("Left the voice channel")
        self.logger.info(f"Left the voice channel in guild {guild_id}")
    
async def setup(bot):
    await bot.add_cog(voicecommands(bot))
