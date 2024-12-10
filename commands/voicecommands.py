from datetime import datetime, timedelta
import sys
import nacl
import discord as dc
from discord import app_commands
from discord.ext import commands
import asyncio
import os

class voicecommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_activity_time = None
        self.voice_channel = None
        self.voice_client = None
        self.inactivity_task = None

    async def inactivityAutoLeave(self):
        while self.voice_client and self.voice_client.is_connected():
            if self.last_activity_time and datetime.utcnow() - self.last_activity_time > timedelta(minutes=2):
                await self.voice_client.disconnect()
                self.voice_client = None
                self.last_activity_time = None
                return
            await asyncio.sleep(30)

    @dc.app_commands.command(name="join_vc", description="Joins the voice channel you are currently connected to")
    async def joinVC(self, interaction: dc.Interaction):
        await interaction.response.send_message("Joining")
        text_channel = interaction.channel
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
    

async def setup(bot):
    await bot.add_cog(voicecommands(bot))