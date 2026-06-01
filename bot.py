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
        
    async def setup_hook(self):
        # Initialize SQLite database
        await database.init_db()
        print("Database initialized.")
        
        # Load extensions/cogs
        await self.load_extension("cogs.warning_tracker")
        await self.load_extension("cogs.paid_request")
        await self.load_extension("cogs.chatbot")
        print("Cogs loaded.")
        
    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")

bot = ACCarrotBot()

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN or TOKEN == "your_bot_token_here":
        print("Please configure your DISCORD_TOKEN in the .env file.")
    else:
        bot.run(TOKEN)
