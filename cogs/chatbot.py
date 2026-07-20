import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timezone
import database

class ChatbotButton(discord.ui.Button):
    def __init__(self, label, emoji, action, target, text, style=discord.ButtonStyle.primary, row=None, custom_id=None):
        btn_emoji = emoji if emoji else None
        super().__init__(label=label, emoji=btn_emoji, style=style, row=row, custom_id=custom_id)
        self.action = action
        self.target = target
        self.text = text

    async def callback(self, interaction: discord.Interaction):
        cog = self.view.cog
        user_id = interaction.user.id
        guild_id = 0

        # Validate DM session expiration (3 hours)
        if interaction.guild is None: # Interaction is in DMs
            session = cog.sessions.get(user_id)
            if not session:
                await interaction.response.send_message("This session has expired or is inactive. Please initiate a new chat from the server channel.", ephemeral=True)
                return
                
            last_active = session.get("last_active")
            time_diff = (datetime.now(timezone.utc) - last_active).total_seconds()
            if time_diff > 3600: # 1 hour
                cog.sessions.pop(user_id, None)
                try:
                    await interaction.message.delete()
                except Exception:
                    pass
                await interaction.response.send_message("This session has expired due to inactivity. Please initiate a new chat from the server channel.", ephemeral=True)
                return
            
            # Session is valid, refresh active time and message reference
            session["last_active"] = datetime.now(timezone.utc)
            session["message"] = interaction.message
            guild_id = session.get("guild_id", 0)
        else:
            guild_id = interaction.guild_id or 0

        # If this is the active preview message (for admin builder), update tracked preview menu state
        if cog.active_preview_message and interaction.message.id == cog.active_preview_message.id:
            if self.action == "menu":
                cog.preview_menu_name = self.target

        if self.action == "message":
            await interaction.response.send_message(self.text or "No response configured.", ephemeral=True)
        elif self.action == "menu":
            embed, view = cog.get_menu_embed_and_view(self.target, user_id=user_id, guild_id=guild_id)
            await interaction.response.edit_message(content=None, embed=embed, view=view)

class ChatbotView(discord.ui.View):
    def __init__(self, cog, menu_name="main_menu", user_id=None, guild_id=0):
        super().__init__(timeout=None)
        self.cog = cog
        self.menu_name = menu_name
        self.user_id = user_id
        self.guild_id = guild_id
        self.build_buttons()

    def build_buttons(self):
        self.clear_items()
        config = self.cog.get_guild_chatbot_config_sync(self.guild_id)
        
        if self.menu_name == "main_menu":
            menu_data = config.get("main_menu", {})
        else:
            menu_data = config.get("menus", {}).get(self.menu_name, {})
            
        buttons = menu_data.get("buttons", [])
        
        for idx, btn_info in enumerate(buttons[:24]):
            label = btn_info.get("label", f"Button {idx+1}")
            emoji = btn_info.get("emoji")
            action = btn_info.get("action")
            target = btn_info.get("target")
            text = btn_info.get("text")
            
            row_num = min(idx // 2, 4)
            
            button = ChatbotButton(
                label=label,
                emoji=emoji,
                action=action,
                target=target,
                text=text,
                row=row_num,
                custom_id=f"chatbot_{self.menu_name}_{idx}"
            )
            self.add_item(button)
            
        # Add "Back" button if it is a sub-menu
        if self.menu_name != "main_menu":
            back_row = min(((len(buttons) - 1) // 2) + 1, 4)
            back_button = ChatbotButton(
                label="Back",
                emoji="◀️",
                action="menu",
                target="main_menu",
                text=None,
                style=discord.ButtonStyle.secondary,
                row=back_row,
                custom_id=f"chatbot_{self.menu_name}_back"
            )
            self.add_item(back_button)

class InitiateChatView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Start Chat", emoji="💬", style=discord.ButtonStyle.success, custom_id="initiate_carrot_chat")
    async def start_chat(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        await interaction.response.defer(ephemeral=True)
        
        # If there's an existing session, delete its previous message to avoid clutter
        old_session = self.cog.sessions.get(user.id)
        if old_session:
            old_msg = old_session.get("message")
            if old_msg:
                try:
                    await old_msg.delete()
                except Exception:
                    pass
        
        guild_id = interaction.guild_id or 0
        if guild_id == 0 and self.cog.bot.guilds:
            guild_id = self.cog.bot.guilds[0].id
            
        try:
            embed, view = self.cog.get_menu_embed_and_view("main_menu", user_id=user.id, guild_id=guild_id)
            msg = await user.send(embed=embed, view=view)
            
            # Record DM session with message reference for background expiration edits
            self.cog.sessions[user.id] = {
                "last_active": datetime.now(timezone.utc),
                "message": msg,
                "guild_id": guild_id
            }
            await interaction.followup.send("I've sent you a DM! Please check your Direct Messages to start our conversation.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I couldn't send you a DM. Please enable Direct Messages (DMs) for this server in your Privacy Settings and try again.", 
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"An error occurred while trying to send DM: {e}", ephemeral=True)

class Chatbot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_preview_message = None
        self.preview_menu_name = "main_menu"
        # Track active DM sessions: { user_id: { "last_active": datetime, "message": Message, "guild_id": int } }
        self.sessions = {}
        self.configs_cache = {}
        
        # Start the background task to sweep expired sessions
        self.timeout_check.start()
        self.bot.loop.create_task(self.register_persistent_views())

    def cog_unload(self):
        self.timeout_check.cancel()

    async def register_persistent_views(self):
        await self.bot.wait_until_ready()
        self.bot.add_view(InitiateChatView(self))
        await self.load_all_configs()

    @tasks.loop(minutes=2)
    async def timeout_check(self):
        """Periodically sweeps expired sessions (inactive for 3h) and edits DM messages to alert the user."""
        now = datetime.now(timezone.utc)
        expired_users = []
        
        for user_id, session in list(self.sessions.items()):
            last_active = session.get("last_active")
            # 3600 seconds = 1 hour
            if (now - last_active).total_seconds() > 3600:
                expired_users.append(user_id)
                msg = session.get("message")
                if msg:
                    try:
                        await msg.delete()
                    except Exception:
                        pass # Ignore if DM was deleted or bot blocked
                        
        for user_id in expired_users:
            self.sessions.pop(user_id, None)

    async def load_all_configs(self):
        """Pre-loads all chatbot configurations from the database into memory."""
        try:
            print(f"[CHATBOT DEBUG] load_all_configs started. Bot guilds: {[g.id for g in self.bot.guilds]}")
            self.configs_cache[0] = await database.get_chatbot_config(0)
            print(f"[CHATBOT DEBUG] Loaded default config (0) with {len(self.configs_cache[0].get('main_menu', {}).get('buttons', []))} buttons.")
            for guild in self.bot.guilds:
                self.configs_cache[guild.id] = await database.get_chatbot_config(guild.id)
                print(f"[CHATBOT DEBUG] Loaded config for guild {guild.id} with {len(self.configs_cache[guild.id].get('main_menu', {}).get('buttons', []))} buttons.")
            print(f"Chatbot configurations loaded for {len(self.configs_cache)} guilds. Cache keys: {list(self.configs_cache.keys())}")
        except Exception as e:
            print(f"[CHATBOT DEBUG] Error loading chatbot configs from database: {e}")

    async def refresh_cache(self, guild_id: int):
        """Refreshes the cached chatbot config for a specific guild."""
        try:
            self.configs_cache[guild_id] = await database.get_chatbot_config(guild_id)
            print(f"[CHATBOT DEBUG] Refreshed config cache for guild {guild_id}. Cache keys: {list(self.configs_cache.keys())}")
        except Exception as e:
            print(f"Error refreshing chatbot config cache for guild {guild_id}: {e}")

    def get_guild_chatbot_config_sync(self, guild_id: int) -> dict:
        """Helper to synchronously fetch a guild's chatbot configuration from cache."""
        # Convert to int just in case
        try:
            g_id = int(guild_id)
        except (ValueError, TypeError):
            g_id = 0
            
        print(f"[CHATBOT DEBUG] get_guild_chatbot_config_sync called for guild_id={g_id} (original: {guild_id}, type: {type(guild_id)}). Cached keys: {list(self.configs_cache.keys())}")
        
        if g_id in self.configs_cache:
            cfg = self.configs_cache[g_id]
            print(f"[CHATBOT DEBUG] Found config in cache. main_menu buttons: {len(cfg.get('main_menu', {}).get('buttons', []))}")
            return cfg
            
        fallback = self.configs_cache.get(0, {
            "main_menu": {
                "text": "Hello! I'm Carrot and I can help you with answering with questions you might have! \n\nTo get started, please select from provided options:", 
                "buttons": []
            }, 
            "menus": {}
        })
        print(f"[CHATBOT DEBUG] Config not found in cache. Using fallback. main_menu buttons: {len(fallback.get('main_menu', {}).get('buttons', []))}")
        return fallback

    def get_menu_embed_and_view(self, menu_name, user_id=None, guild_id=0):
        """Constructs and returns the embed and view for the given menu name."""
        config = self.get_guild_chatbot_config_sync(guild_id)
        if menu_name == "main_menu":
            text = config.get("main_menu", {}).get("text", "Hello!")
        else:
            text = config.get("menus", {}).get(menu_name, {}).get("text", "...")
            
        embed = discord.Embed(
            title="🥕 Carrot Assistant",
            description=text,
            color=discord.Color.orange()
        )
        embed.set_footer(text="Made by @moriluna")
        
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            
        view = ChatbotView(self, menu_name=menu_name, user_id=user_id, guild_id=guild_id)
        return embed, view

    async def update_active_preview(self):
        """Edits the active preview message to reflect config changes in real-time."""
        if not self.active_preview_message:
            return
            
        try:
            # Fallback preview uses guild_id=0 (global template)
            embed, view = self.get_menu_embed_and_view(self.preview_menu_name, guild_id=0)
            await self.active_preview_message.edit(content=None, embed=embed, view=view)
        except Exception as e:
            print(f"Failed to update active preview message: {e}")
            self.active_preview_message = None

    @commands.command(name="chatbot_setup_channel")
    async def chatbot_setup_channel(self, ctx):
        if ctx.author.id != 255174440005009408:
            if not ctx.guild or not ctx.author.guild_permissions.administrator:
                await ctx.send("You do not have the required administrator permissions to use this command.")
                return
        """Spawns the persistent message in the channel for users to initiate chatbot DMs."""
        embed = discord.Embed(
            title="🥕 Contact Carrot Support",
            description="Need help or have questions? Click the button below to start an interactive chat with Carrot in your Direct Messages.",
            color=discord.Color.orange()
        )
        embed.set_footer(text="Made by @moriluna")
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            
        view = InitiateChatView(self)
        await ctx.send(embed=embed, view=view)
        try:
            await ctx.message.delete()
        except Exception as e:
            print(f"[CHATBOT DEBUG] Failed to delete setup command trigger message: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Intercepts direct text messages in DMs and redirects users to ModMail."""
        # Ignore bots
        if message.author.bot:
            return
            
        # Check if the message is a DM (guild is None)
        if message.guild is None:
            # Ignore bot command messages starting with '!'
            if message.content.startswith("!"):
                return
                
            guild_id = 0
            if self.bot.guilds:
                guild_id = self.bot.guilds[0].id
                
            config = self.get_guild_chatbot_config_sync(guild_id)
            dm_prompt = config.get("dm_prompt_button", False)
            trigger_on_dm = config.get("trigger_on_dm", False)
            custom_message = config.get("dm_custom_message")
            
            try:
                if trigger_on_dm:
                    # Clean up old session
                    old_session = self.sessions.get(message.author.id)
                    if old_session:
                        old_msg = old_session.get("message")
                        if old_msg:
                            try:
                                await old_msg.delete()
                            except Exception:
                                pass
                                
                    embed, view = self.get_menu_embed_and_view("main_menu", user_id=message.author.id, guild_id=guild_id)
                    
                    content = custom_message if custom_message else None
                    msg = await message.channel.send(content=content, embed=embed, view=view)
                    
                    self.sessions[message.author.id] = {
                        "last_active": datetime.now(timezone.utc),
                        "message": msg,
                        "guild_id": guild_id
                    }
                elif dm_prompt:
                    desc = custom_message if custom_message else "I noticed you're trying to send a message to Carrot. If you'd like to use the interactive assistant helper, click the button below to start our chat! Otherwise, please direct all applications/reports to <@501746915218554881>."
                    embed = discord.Embed(
                        title="🥕 Carrot Assistant Support",
                        description=desc,
                        color=discord.Color.orange()
                    )
                    view = InitiateChatView(self)
                    await message.channel.send(embed=embed, view=view)
                else:
                    msg_text = custom_message if custom_message else "I noticed you're trying to send a message to Carrot. Please direct all your applications/questions/reports to <@501746915218554881>!"
                    await message.channel.send(msg_text)
            except Exception as e:
                print(f"Failed to respond to user DM message: {e}")

async def setup(bot):
    await bot.add_cog(Chatbot(bot))
