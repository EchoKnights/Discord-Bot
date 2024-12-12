import sys
import discord as dc
from discord.ext import commands

class textcommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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

    @dc.app_commands.command(name="purge", description="Purges the last specified amount of messages from the channel")
    async def purgeMessage(self, interaction: dc.Interaction, amount: int):
        try:
            if(amount <= 0):
                await interaction.response.send_message("Please enter a valid amount of messages")
                return
            elif (amount > 50):
                await interaction.response.send_message("Please enter a smaller amount of messages")
                return
            
            await interaction.response.defer(ephemeral=True)

            deleted = await interaction.channel.purge(limit=amount)

        except Exception as e:
            print(f"Couldn't purge {amount} messages in {interaction.channel} due to {e}")

        log_channel = dc.utils.get(interaction.guild.text_channels, name="da-logs")
        if log_channel:
            await log_channel.send(f"{interaction.user} requested the deletion of {len(deleted)} messages in #{interaction.channel.name}")
        await interaction.response.send_message(f"Successfully deleted {len(deleted) - 1} messages.")

async def setup(bot):
    await bot.add_cog(textcommands(bot))