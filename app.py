import sys
import discord as dc
import GitIgnorables.Authcode as Authcode
from discord import app_commands
from discord.ext import commands
import log, DACommands

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

#Command
@bot.tree.command(name="quit", description="Makes the Bot exit for debugging purposes")
async def terminate(interaction: dc.Interaction):
        await interaction.response.send_message("Shutting down the bot.")
        await bot.close()
        sys.exit(0)


#Run Command
bot.run(Authcode.token)