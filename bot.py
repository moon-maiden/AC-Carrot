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
import uvicorn
import api

load_dotenv()

# We need message content intent to read #staff-notice mentions
intents = discord.Intents.default()
intents.message_content = True
intents.members = False

class ACCarrotBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.remove_command('help')
        
    async def setup_hook(self):
        # Initialize SQLite database
        await database.init_db()
        print("Database initialized.")
        
        # Cleanup orphaned and old attachments
        await database.cleanup_attachments()
        print("Attachments cleaned up.")
        
        # Load extensions/cogs
        await self.load_extension("cogs.warning_tracker")
        await self.load_extension("cogs.paid_request")
        await self.load_extension("cogs.chatbot")
        await self.load_extension("cogs.message_builder")
        await self.load_extension("cogs.reminders")
        await self.load_extension("cogs.vacation_manager")
        print("Cogs loaded.")
        
        # Start FastAPI server alongside Discord bot
        api.set_bot_client(self)
        port = int(os.environ.get("PORT", 8000))
        config = uvicorn.Config(api.app, host="0.0.0.0", port=port, log_level="info")
        server = uvicorn.Server(config)
        self.loop.create_task(server.serve())
        print("FastAPI server started on port 8000.")
        
    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        try:
            # Clear guild-specific commands to remove previous duplicates
            for guild in self.guilds:
                await database.migrate_env_to_db(guild.id)
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
