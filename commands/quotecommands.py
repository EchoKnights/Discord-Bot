import json
import sys
import discord as dc
from discord import app_commands
from discord.ext import commands
import asyncio
import os
from datetime import datetime

#actual functions (for some reason they freak out if i put them inside the class.)
QUOTE_DIR = "server_quotes"
os.makedirs(QUOTE_DIR, exist_ok=True)

def get_server_file(guild_id):
    return os.path.join(QUOTE_DIR, f"{guild_id}.json")
        
def load_quotes(guild_id):
    file_path = get_server_file(guild_id)
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print(f"Invalid JSON in {file_path}. Resetting quotes.")
                return []
    else:
        return []
    
def save_quotes(guild_id, quotes):
    file_path = get_server_file(guild_id)
    with open(file_path, "w") as f:
         json.dump(quotes, f, indent=4)

#actual commands.
class quotecommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready():
        print('Quote Commands Cog Succesfully Loaded')

    @dc.app_commands.command(name="save_quote", description="Save a message as a quote")
    async def save_quote(self, interaction: dc.Interaction):
        def checkMessage(message):
            return (
                message.author == interaction.user and message.channel == interaction.channel)
            
        await interaction.response.defer(ephemeral=True, thinking=False)
        await interaction.followup.send("Please reply to the message you want to quote or type 'cancel' to abort.")

        try:
            try:
                reply = await self.bot.wait_for("message", check=checkMessage, timeout=20)
            except asyncio.TimeoutError:
                await interaction.followup.send("You took too long to reply, so the action has been canceled.")
                return
            
            if reply.content.lower() == "cancel":
                await interaction.followup.send("Quote saving action has been canceled.")
                return

            if reply.reference:
                referenced_message = await reply.channel.fetch_message(reply.reference.message_id)
            else:
                await interaction.followup.send("Please reply to a valid message.")
                return

            try:
                if referenced_message.is_system():
                    await interaction.followup.send("System messages cannot be saved as quotes.")
                    return
                else:
                    guild_id = interaction.guild.id
                    quotes = load_quotes(guild_id)
                    quotes.append({
                        "content": referenced_message.content,
                        "author": str(referenced_message.author),
                        "message_id": referenced_message.id,
                        "message_date": referenced_message.created_at.isoformat(),
                    })
                    save_quotes(guild_id, quotes)

                    await interaction.followup.send(f"Quote saved: \"{referenced_message.content}\" - {referenced_message.author.mention}")
            except Exception as e:
                print(f"Couldn't execute command due to {e}")
        except Exception as e:
            print(f'Failed to start quote process due to {e}')


    @dc.app_commands.command(name="list_quotes", description="List all saved quotes for this server")
    async def listQuotes(self, interaction: dc.Interaction):
        guild_id = interaction.guild.id
        quotes = load_quotes(guild_id)

        if quotes:
            quote_list = "\n".join(
                [f"{idx + 1}. \"{quote['content']}\" - {quote['author']}" for idx, quote in enumerate(quotes)]
            )
            await interaction.response.send_message(f"Saved quotes:\n{quote_list}")
        else:
            await interaction.response.send_message("No quotes saved yet.")

    @dc.app_commands.command(name="remove_quote", description="Remove a quote by its index")
    async def removeQuote(self, interaction: dc.Interaction, index: int):
        guild_id = interaction.guild.id
        quotes = load_quotes(guild_id)

        if 0 < index <= len(quotes):
            removed = quotes.pop(index - 1)
            save_quotes(guild_id, quotes)
            await interaction.response.send_message(
                f"Removed quote: \"{removed['content']}\" - {removed['author']}"
            )
        else:
            await interaction.response.send_message("Invalid quote index.")

async def setup(bot):
    await bot.add_cog(quotecommands(bot))