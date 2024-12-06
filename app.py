import sys
import discord as dc
import GitIgnorables.Authcode as Authcode
import commands.textcommands
import asyncio
from discord import app_commands
from discord.ext import commands

intents = dc.Intents.default()
intents.message_content = True
intents.guilds = True
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

@bot.event
async def on_guild_join(guild: dc.Guild):
    overwrites = {
    guild.default_role: dc.PermissionOverwrite(read_messages=False),
    guild.me: dc.PermissionOverwrite(read_messages=True),
    }
    
    try:
        debugRole = await guild.create_role(
            name = "DA Debug",
            color = dc.Color.dark_gray(),
            permissions = dc.Permissions(permissions=5),
            reason="Auto-created by bot for debugging purposes"
        )
        
    except Exception as e:
        print(f'Failed to create debug role due to {e}')

    if debugRole:
        overwrites[debugRole] = dc.PermissionOverwrite(read_messages=True)

    try:
        djRole = await guild.create_role(
            name = "Devil's DJ",
            color = dc.Color.red(),
            permissions = dc.Permissions(permissions=5),
            reason="Auto-created to allow music operation."
        )
        
    except Exception as e:
        print(f'Failed to create DJ role due to {e}')

    try:
        debugChannel = await guild.create_text_channel(
            name='Devils Advocate Debug Channel',
            overwrites=overwrites,
        )
    except Exception as e:
        print(f'Couldnt create debug channel due to {e}')

#Run Function
async def run():
    async with bot:
        await bot.load_extension("commands")
        await bot.start(Authcode.token)

asyncio.run(run())