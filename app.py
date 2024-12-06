import sys
import discord as dc
import GitIgnorables.Authcode as Authcode
import commands.textcommands
import asyncio
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

#Run Function
async def run():
    async with bot:
        await bot.load_extension("commands")
        await bot.start(Authcode.token)

asyncio.run(run())