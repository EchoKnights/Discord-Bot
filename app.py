import discord as dc
import commands.textcommands
import asyncio
import os
import logging
import json
from discord.ext import commands

intents = dc.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

logging.basicConfig(
    level=logging.INFO, #(DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s',
    handlers=[
        logging.FileHandler("app.log"),  
        logging.StreamHandler()
    ]
)
#global version
logger = logging.getLogger('bot')


#config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
with open(CONFIG_PATH, 'r') as config_file:
    config = json.load(config_file)
bot.config = config
TOKEN = config['token']

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
    print(f"Bot joined a new guild: {guild.name} ({guild.id})")
    overwrites = {
        guild.default_role: dc.PermissionOverwrite(read_messages=False),
        guild.me: dc.PermissionOverwrite(read_messages=True),
    }
    
    try:
        print("Attempting to create debug role...")
        debug_role = await guild.create_role(
            name="DA Debug",
            color=dc.Color.dark_gray(),
            permissions=dc.Permissions(permissions=5),
            reason="Auto-created by bot for debugging purposes"
        )
        print(f"Debug role created: {debug_role.name}")
    except Exception as e:
        debug_role = None
        print(f'Failed to create debug role due to: {e}')

    if debug_role:
        overwrites[debug_role] = dc.PermissionOverwrite(read_messages=True)

    try:
        dj_role = await guild.create_role(
            name="Devil's DJ",
            color=dc.Color.red(),
            permissions=dc.Permissions(permissions=5),
            reason="Auto-created to allow music operation."
        )
        print(f"DJ role created: {dj_role.name}")
    except Exception as e:
        print(f'Failed to create DJ role due to: {e}')

    try:
        print("Attempting to create debug channel...")
        debug_channel = await guild.create_text_channel(
            name='devils-advocate-debug-channel',
            overwrites=overwrites,
            reason="Auto-created by bot for debugging purposes"
        )
        print(f"Debug channel created: {debug_channel.name}")
    except Exception as e:
        print(f"Couldn't create debug channel due to: {e}")

    try:
        print("Attempting to create log channel...")
        log_channel = await guild.create_text_channel(
            name='da-logs',
            overwrites=overwrites,
            reason="Auto-created by bot for logging purposes"
        )
        print(f"Log channel created: {log_channel.name}")
    except Exception as e:
        print(f"Couldn't create log channel due to: {e}")

    try:
        QUOTE_DIR = "server_quotes"
        def get_server_file(guild_id):
            return os.path.join(QUOTE_DIR, f"{guild_id}.json")
        
        file_path = get_server_file(guild.id)
        if not os.path.exists(file_path):
            with open(file_path, "w") as f:
                json.dump([], f, indent=4)
            print(f"Created a new quotes file for guild: {guild.name} ({guild.id})")
        else:
            print(f"Quotes file for guild {guild.name} ({guild.id}) already exists.")
    except Exception as e:
        print(f'Couldnt create the server quote file due to: {e}')

#Run Function
async def run():
    async with bot:
        await bot.load_extension("commands")
        await bot.start(TOKEN)

asyncio.run(run())