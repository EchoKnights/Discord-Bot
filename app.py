import sys
import discord as dc
import GitIgnorables.Authcode as Authcode
from discord import app_commands
from discord.ext import commands

intents = dc.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_connect():
    print(f"Succesfully connected to Discord's servers.")
    return

@bot.event
async def on_ready():
    print(f"Successfuly logged on as {bot.user}")

    #Trying to sync slash commands globally
    try:
        syncLen = await bot.tree.sync()
        print(f'Synced {len(syncLen)} slash-based commands')
    except Exception as e:
        print(f'Failed to sync commands due to: {e}')

#Commands
@bot.tree.command(name="quit", description="Makes the Bot exit for debugging purposes")
async def terminate(interaction: dc.Interaction):
        await interaction.response.send_message("Shutting down the bot.")
        await bot.close()
        sys.exit(0)


@bot.tree.command(name="message_channel", description="Sends a message to the requested channel")
async def channelMessage(interaction: dc.Interaction, channel: dc.TextChannel, msg: str):
    try:
        #add an anti-spam feature and check if it sees hidden messages the user cant see.
        await channel.send(content=f"{msg}")
        await interaction.response.send_message("Sent.")
    except Exception as e:
        #Next time make it so that it sends the message to a debug channel automatically created when joining a guild
        print(f'Couldnt send the message due to {e}')

@bot.tree.command(name="ping", description="See how much latency the bot is suffering from")
async def ping(interaction: dc.Interaction):
     time = bot.latency * 1000
     await interaction.response.send_message(f'My ping returned after: {time: .2f}ms')

#Run Command
bot.run(Authcode.token)