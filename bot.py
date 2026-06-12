import socket
import aiohttp

# Force IPv4 globally in aiohttp TCPConnectors to workaround Railway's IPv6 routing/gateway timeouts.
original_init = aiohttp.TCPConnector.__init__

def patched_init(self, *args, **kwargs):
    kwargs['family'] = socket.AF_INET
    original_init(self, *args, **kwargs)

aiohttp.TCPConnector.__init__ = patched_init

import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import database
import asyncio

load_dotenv()

# We need message content intent to read #staff-notice mentions
intents = discord.Intents.default()
intents.message_content = True

class ACCarrotBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.remove_command('help')
        
    async def setup_hook(self):
        # Initialize SQLite database
        await database.init_db()
        print("Database initialized.")
        
        # Load extensions/cogs
        await self.load_extension("cogs.warning_tracker")
        await self.load_extension("cogs.paid_request")
        await self.load_extension("cogs.chatbot")
        await self.load_extension("cogs.message_builder")
        print("Cogs loaded.")
        
    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        try:
            # Clear guild-specific commands to remove previous duplicates
            for guild in self.guilds:
                self.tree.clear_commands(guild=guild)
                await self.tree.sync(guild=guild)
                
            # Sync globally (so the command only exists once)
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} global application commands.")
        except Exception as e:
            print(f"Error syncing commands: {e}")
        print("------")

bot = ACCarrotBot()

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN or TOKEN == "your_bot_token_here":
        print("Please configure your DISCORD_TOKEN in the .env file.")
    else:
        bot.run(TOKEN)
