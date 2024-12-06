import sys
import discord as dc
import GitIgnorables.Authcode as Authcode
from discord import app_commands
from discord.ext import commands
import asyncio  

class timercommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.timers = {}

    @dc.app_commands.command(name="start_timer", description="Start a timer.")
    async def timerStart(self, interaction: dc.Interaction, h: int = 0, m: int = 0, s: int = 0):
        duration = (h * 60 * 60) + (m * 60) + s

        if (duration <= 0):
            await interaction.response.send_message("Please input an actual amount of time.")
            return
            
        user_id = interaction.user.id

        await interaction.response.send_message(f'Started a timer for {h}h:{m}m:{s}s')

        if user_id not in self.timers:
            self.timers[user_id] = []

        timer_task = self.bot.loop.create_task(self.run_timer(interaction, duration))
        self.timers[user_id].append(timer_task)
    
    async def run_timer(self, interaction: dc.Interaction, duration: int):
        user_id = interaction.user.id

        try:
            await asyncio.sleep(duration)
            await interaction.followup.send(content=f"Time's up, {interaction.user.mention}.")
        except asyncio.CancelledError:
            await interaction.followup.send(content="The timer was canceled.")
        finally:
            if user_id in self.timers:
                self.timers[user_id] = [t for t in self.timers[user_id] if not t.done()]
                if not self.timers[user_id]:
                    del self.timers[user_id]

    @dc.app_commands.command(name="cancel_timers", description="Cancels all your active timers.")
    async def cancelTimers(self, interaction: dc.Interaction):
        user_id = interaction.user.id

        if user_id not in self.timers or not self.timers[user_id]:
            await interaction.response.send_message("You don't have any active timers.")
            return

        for timer in self.timers[user_id]:
            timer.cancel()

        del self.timers[user_id]
        await interaction.response.send_message("Stopped your active timers.")

    @dc.app_commands.command(name="list_timers", description="Lists all your active timers.")
    async def listTimers(self, interaction: dc.Interaction):
        user_id = interaction.user.id

        if user_id not in self.timers or not self.timers[user_id]:
            await interaction.response.send_message("You don't have any active timers.")
            return

        timer_count = len(self.timers[user_id])
        await interaction.response.send_message(f"You have {timer_count} active timer(s).")


async def setup(bot):
    await bot.add_cog(timercommands(bot))
