import sys
import discord as dc
import GitIgnorables.Authcode as Authcode
from discord import app_commands
from discord.ext import commands
import asyncio

class textcommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.timers = {}

    @commands.Cog.listener()
    async def on_ready():
        print('Text Commands Cog Succesfully Loaded.')
            
    @dc.app_commands.command(name="quit", description="Makes the Bot exit for debugging purposes")
    async def terminate(self, interaction: dc.Interaction):
        await interaction.response.send_message("Shutting down the bot.")
        await self.bot.close()
        sys.exit(0)


    @dc.app_commands.command(name="message_channel", description="Sends a message to the requested channel")
    async def channelMessage(self, interaction: dc.Interaction, channel: dc.TextChannel, msg: str):
        try:
            #add an anti-spam feature and check if it sees hidden messages the user cant see.
            await channel.send(content=f"{msg}")
            await interaction.response.send_message("Sent.")
        except Exception as e:
            #Next time make it so that it sends the message to a debug channel automatically created when joining a guild
            print(f'Couldnt send the message due to {e}')

    @dc.app_commands.command(name="ping", description="See how much latency the bot is suffering from")
    async def ping(self, interaction: dc.Interaction):
        time = self.bot.latency * 1000
        await interaction.response.send_message(f'My ping returned after: {time: .2f}ms')

        
async def setup(bot):
    await bot.add_cog(textcommands(bot))