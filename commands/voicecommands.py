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

    @dc.app_commands.command(name="join_vc", description="Joins the voice channel you are currently connected to")
    async def joinVC(self, interaction: dc.Interaction):
        voice_channel = interaction.user.voice.channel
        await interaction.response.send_message("Joining")
        try:
            if(voice_channel):
                voice_client = await voice_channel.connect()

                async def inactivityAutoLeave():
                    await asyncio.sleep((2 * 60))
                    if voice_client.is_connected(): 
                        await voice_client.disconnect()

                await inactivityAutoLeave()
            else:
                interaction.response.send_message("Connect to the voice channel you want me to connect to")
        except Exception as e:
            print(f'Couldnt join vc due to {e}')

    @dc.app_commands.command(name="leave_vc", description="Leaves the voice channel the bot is currently connected to")
    async def leaveVC(self, interaction: dc.Interaction):
        await interaction.response.send_message("Leaving")
        voice_channel = dc.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if(voice_channel):
            await voice_channel.disconnect()
        else:
            interaction.response.send_message("I am not connected to voice channel")

async def setup(bot):
    await bot.add_cog(voicecommands(bot))