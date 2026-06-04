import discord
from discord.ext import commands
from discord import app_commands
import database
import asyncio
import re

class MessageContentModal(discord.ui.Modal, title="Edit Message Content"):
    content_input = discord.ui.TextInput(
        label="Message Text", style=discord.TextStyle.long, required=False, max_length=4000,
        placeholder="Hello everyone! Welcome to the server..."
    )
    def __init__(self, view):
        super().__init__()
        self.view_context = view
        self.content_input.default = view.msg_content
    async def on_submit(self, interaction: discord.Interaction):
        self.view_context.msg_content = self.content_input.value
        await self.view_context.update_preview(interaction)

class EmbedContentModal(discord.ui.Modal, title="Edit Embed"):
    embed_title = discord.ui.TextInput(label="Title", style=discord.TextStyle.short, required=False, max_length=256, placeholder="Embed Title Here")
    embed_description = discord.ui.TextInput(label="Description", style=discord.TextStyle.long, required=False, max_length=4000, placeholder="Main embed text...")
    embed_color = discord.ui.TextInput(label="Color (Hex, e.g. #FF5555)", style=discord.TextStyle.short, required=False, max_length=7, placeholder="#5865F2")
    embed_image = discord.ui.TextInput(label="Image URL", style=discord.TextStyle.short, required=False, placeholder="https://example.com/image.png")
    embed_footer = discord.ui.TextInput(label="Footer Text", style=discord.TextStyle.short, required=False, max_length=2048, placeholder="This text appears below the divider line")
    
    def __init__(self, view):
        super().__init__()
        self.view_context = view
        self.embed_title.default = view.embed_data.get('title', '')
        self.embed_description.default = view.embed_data.get('description', '')
        self.embed_color.default = view.embed_data.get('color', '')
        self.embed_image.default = view.embed_data.get('image', '')
        self.embed_footer.default = view.embed_data.get('footer', '')
        
    async def on_submit(self, interaction: discord.Interaction):
        color_val = self.embed_color.value.strip()
        if color_val:
            try:
                # Validate hex format
                int(color_val.strip('#'), 16)
            except ValueError:
                await interaction.response.send_message(
                    "❌ **Invalid Color Format:** Please use a valid Hex code for the embed color (e.g., `#FF5555`, `#5865F2`, or `FFFFFF`).",
                    ephemeral=True
                )
                return

        self.view_context.embed_data = {
            'title': self.embed_title.value, 'description': self.embed_description.value,
            'color': color_val, 'image': self.embed_image.value, 'footer': self.embed_footer.value
        }
        await self.view_context.update_preview(interaction)

class ThreadModal(discord.ui.Modal, title="Thread Settings"):
    thread_name = discord.ui.TextInput(label="Thread Name", style=discord.TextStyle.short, required=False, max_length=100, placeholder="Name of the public thread to spawn")
    def __init__(self, view):
        super().__init__()
        self.view_context = view
        self.thread_name.default = view.thread_name
    async def on_submit(self, interaction: discord.Interaction):
        self.view_context.thread_name = self.thread_name.value
        await self.view_context.update_preview(interaction)

# --- Embed Fields Flow ---

class EmbedFieldModal(discord.ui.Modal):
    name_input = discord.ui.TextInput(label="Field Title", style=discord.TextStyle.short, required=True, max_length=256, placeholder="e.g. Option A or just -")
    value_input = discord.ui.TextInput(label="Field Value", style=discord.TextStyle.long, required=True, max_length=1024, placeholder="e.g. • Role 1\n• Role 2")
    inline_input = discord.ui.TextInput(label="Inline (yes/no)", style=discord.TextStyle.short, required=True, max_length=3, placeholder="yes")
    
    def __init__(self, view_context, edit_idx=None):
        super().__init__(title="Edit Embed Field" if edit_idx is not None else "Add Embed Field")
        self.view_context = view_context
        self.edit_idx = edit_idx
        
        if edit_idx is not None:
            field = self.view_context.embed_fields[edit_idx]
            self.name_input.default = field['name']
            self.value_input.default = field['value']
            self.inline_input.default = "yes" if field['inline'] else "no"
            
    async def on_submit(self, interaction: discord.Interaction):
        inline_val = self.inline_input.value.strip().lower() in ['y', 'yes', 'true', '1']
        field_data = {
            'name': self.name_input.value,
            'value': self.value_input.value,
            'inline': inline_val
        }
        
        if self.edit_idx is not None:
            self.view_context.embed_fields[self.edit_idx] = field_data
        else:
            self.view_context.embed_fields.append(field_data)
            
        await self.view_context.update_preview(interaction)

class RemoveEmbedFieldModal(discord.ui.Modal, title="Remove Embed Field"):
    idx_input = discord.ui.TextInput(label="Field Index (e.g. 1, 2, 3)", style=discord.TextStyle.short, required=True)
    def __init__(self, view_context):
        super().__init__()
        self.view_context = view_context
    async def on_submit(self, interaction: discord.Interaction):
        try:
            idx = int(self.idx_input.value.strip()) - 1
            if idx < 0 or idx >= len(self.view_context.embed_fields):
                raise ValueError
            del self.view_context.embed_fields[idx]
            await self.view_context.update_preview(interaction)
        except ValueError:
            await interaction.response.send_message(f"❌ **Invalid Index:** Please enter a number between 1 and {len(self.view_context.embed_fields)}.", ephemeral=True)

class EditEmbedFieldSelectView(discord.ui.View):
    def __init__(self, view_context):
        super().__init__(timeout=300)
        self.view_context = view_context
        
        options = []
        for i, field in enumerate(self.view_context.embed_fields):
            label = field['name'][:90] + "..." if len(field['name']) > 90 else field['name']
            options.append(discord.SelectOption(label=f"Field {i+1}: {label}", value=str(i)))
            
        self.select = discord.ui.Select(placeholder="Choose a field to edit...", options=options)
        self.select.callback = self.on_select
        self.add_item(self.select)
        
    async def on_select(self, interaction: discord.Interaction):
        idx = int(self.select.values[0])
        await interaction.response.send_modal(EmbedFieldModal(self.view_context, edit_idx=idx))

class EmbedFieldsMenuView(discord.ui.View):
    def __init__(self, view_context):
        super().__init__(timeout=300)
        self.view_context = view_context
    @discord.ui.button(label="Add Field", emoji="➕", style=discord.ButtonStyle.primary)
    async def add_field(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if len(self.view_context.embed_fields) >= 25:
            await interaction.response.send_message("❌ You have reached the maximum of 25 fields.", ephemeral=True)
            return
        await interaction.response.send_modal(EmbedFieldModal(self.view_context))
    @discord.ui.button(label="Edit Field", emoji="✏️", style=discord.ButtonStyle.success)
    async def edit_field(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if not self.view_context.embed_fields:
            await interaction.response.send_message("❌ No fields to edit.", ephemeral=True)
            return
        await interaction.response.send_message("Select a field to edit:", view=EditEmbedFieldSelectView(self.view_context), ephemeral=True)
    @discord.ui.button(label="Remove Field", emoji="➖", style=discord.ButtonStyle.secondary)
    async def remove_field(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if not self.view_context.embed_fields:
            await interaction.response.send_message("❌ No fields to remove.", ephemeral=True)
            return
        await interaction.response.send_modal(RemoveEmbedFieldModal(self.view_context))
    @discord.ui.button(label="Clear All Fields", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def clear_fields(self, interaction: discord.Interaction, btn: discord.ui.Button):
        self.view_context.embed_fields = []
        await self.view_context.update_preview(interaction)
    @discord.ui.button(label="Back", emoji="🔙", style=discord.ButtonStyle.secondary)
    async def back_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await self.view_context.update_preview(interaction)

# --- Reaction Roles Flow ---

class ReactionRoleSelectView(discord.ui.View):
    def __init__(self, view_context, emoji: str):
        super().__init__(timeout=300)
        self.view_context = view_context
        self.emoji = emoji

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select a role...")
    async def select_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        role = select.values[0]
        self.view_context.reaction_roles = [rr for rr in self.view_context.reaction_roles if rr['emoji'] != self.emoji]
        self.view_context.reaction_roles.append({'emoji': self.emoji, 'role_id': role.id})
        await self.view_context.update_preview(interaction)

class AddReactionRoleModal(discord.ui.Modal):
    emoji_input = discord.ui.TextInput(label="Emoji (Unicode/Custom)", style=discord.TextStyle.short, required=True, placeholder="i.e :carrot_cry: / carrot_cry / 🥕 ")
    def __init__(self, view_context, edit_idx=None):
        super().__init__(title="Edit Reaction Emoji" if edit_idx is not None else "Add Reaction Emoji")
        self.view_context = view_context
        self.edit_idx = edit_idx
        
        if edit_idx is not None:
            self.emoji_input.default = self.view_context.reaction_roles[edit_idx]['emoji']
            
    async def on_submit(self, interaction: discord.Interaction):
        emoji_str = self.emoji_input.value.strip()
        
        # Basic validation for custom emojis
        if emoji_str.startswith(":") and emoji_str.endswith(":"):
            clean_name = emoji_str.strip(":")
            custom_emoji = discord.utils.get(interaction.guild.emojis, name=clean_name)
            if custom_emoji:
                prefix = "a" if custom_emoji.animated else ""
                emoji_str = f"<{prefix}:{custom_emoji.name}:{custom_emoji.id}>"
            else:
                if clean_name.isascii() and clean_name.replace('_', '').isalnum():
                    await interaction.response.send_message(
                        f"❌ **Emoji Not Found:** Could not find a custom server emoji named `{clean_name}`. If you meant a standard emoji, please paste the emoji itself (e.g. 🔥) using your device's emoji picker.",
                        ephemeral=True
                    )
                    return
        elif ':' in emoji_str:
            if not re.search(r'[a-zA-Z0-9_]+:[0-9]+', emoji_str):
                await interaction.response.send_message(
                    "❌ **Invalid Emoji Format:** Custom emojis should be formatted as `<:emoji_name:123456789>`. If using a standard emoji, just paste the unicode character.",
                    ephemeral=True
                )
                return
                
        if self.edit_idx is not None:
            # We are editing an existing mapping. We update the emoji, but they also need to re-select the role.
            # We will pop the role select. 
            # First, we can just remove the old one.
            del self.view_context.reaction_roles[self.edit_idx]
            
        await interaction.response.send_message("Select a role for " + emoji_str, view=ReactionRoleSelectView(self.view_context, emoji_str), ephemeral=True)

class RemoveReactionRoleModal(discord.ui.Modal, title="Remove Reaction Mapping"):
    emoji_input = discord.ui.TextInput(label="Emoji to Remove", style=discord.TextStyle.short, required=True, placeholder="i.e :carrot_cry: / carrot_cry / 🥕")
    def __init__(self, view_context):
        super().__init__()
        self.view_context = view_context
    async def on_submit(self, interaction: discord.Interaction):
        emoji_str = self.emoji_input.value.strip()
        self.view_context.reaction_roles = [rr for rr in self.view_context.reaction_roles if rr['emoji'] != emoji_str]
        await self.view_context.update_preview(interaction)

class EditReactionSelectView(discord.ui.View):
    def __init__(self, view_context):
        super().__init__(timeout=300)
        self.view_context = view_context
        
        options = []
        for i, rr in enumerate(self.view_context.reaction_roles):
            # Try to grab the role name if possible, otherwise use ID
            label = f"Emoji: {rr['emoji']} (Role ID: {rr['role_id']})"
            options.append(discord.SelectOption(label=label[:100], value=str(i)))
            
        self.select = discord.ui.Select(placeholder="Choose a mapping to edit...", options=options)
        self.select.callback = self.on_select
        self.add_item(self.select)
        
    async def on_select(self, interaction: discord.Interaction):
        idx = int(self.select.values[0])
        await interaction.response.send_modal(AddReactionRoleModal(self.view_context, edit_idx=idx))

class ReactionRolesMenuView(discord.ui.View):
    def __init__(self, view_context):
        super().__init__(timeout=300)
        self.view_context = view_context
    @discord.ui.button(label="Add Mapping", emoji="➕", style=discord.ButtonStyle.primary)
    async def add_mapping(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(AddReactionRoleModal(self.view_context))
    @discord.ui.button(label="Edit Mapping", emoji="✏️", style=discord.ButtonStyle.success)
    async def edit_mapping(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if not self.view_context.reaction_roles:
            await interaction.response.send_message("❌ No mappings to edit.", ephemeral=True)
            return
        await interaction.response.send_message("Select a mapping to edit:", view=EditReactionSelectView(self.view_context), ephemeral=True)
    @discord.ui.button(label="Remove Mapping", emoji="➖", style=discord.ButtonStyle.secondary)
    async def remove_mapping(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(RemoveReactionRoleModal(self.view_context))
    @discord.ui.button(label="Clear All Mappings", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def clear_mappings(self, interaction: discord.Interaction, btn: discord.ui.Button):
        self.view_context.reaction_roles = []
        await self.view_context.update_preview(interaction)
    @discord.ui.button(label="Back", emoji="🔙", style=discord.ButtonStyle.secondary)
    async def back_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await self.view_context.update_preview(interaction)

# --- Main Builder View ---

class BuilderControlView(discord.ui.View):
    def __init__(self, cog, target_message=None):
        super().__init__(timeout=900)
        self.cog = cog
        self.target_message = target_message
        self.msg_content = ""
        self.embed_data = {}
        self.embed_fields = []
        self.reaction_roles = []
        self.thread_name = ""
        self.flag_silent = False
        self.flag_suppress_embeds = False
        self.preview_message = None

        if target_message:
            self.msg_content = target_message.content
            if target_message.embeds:
                emb = target_message.embeds[0]
                color_hex = f"#{emb.color.value:06x}" if emb.color else ""
                self.embed_data = {
                    'title': emb.title or "", 'description': emb.description or "",
                    'color': color_hex, 'image': emb.image.url if emb.image else "",
                    'footer': emb.footer.text if emb.footer else ""
                }
            self.delete_btn.disabled = False
        else:
            self.remove_item(self.delete_btn)

    def get_preview_kwargs(self):
        kwargs = {"content": self.msg_content if self.msg_content else None}
        has_embed = any(self.embed_data.get(k) for k in ['title', 'description', 'image', 'footer']) or self.embed_fields
        if has_embed:
            color = discord.Color.default()
            if self.embed_data.get('color'):
                try:
                    color = discord.Color(int(self.embed_data['color'].strip('#'), 16))
                except ValueError:
                    pass
            embed = discord.Embed(title=self.embed_data.get('title'), description=self.embed_data.get('description'), color=color)
            if self.embed_data.get('image'): embed.set_image(url=self.embed_data['image'])
            if self.embed_data.get('footer'): embed.set_footer(text=self.embed_data['footer'])
            
            for field in self.embed_fields:
                embed.add_field(name=field['name'], value=field['value'], inline=field['inline'])
                
            kwargs["embed"] = embed
        else:
            kwargs["embed"] = None

        info = f"**Thread**: {self.thread_name or 'None'} | **Silent**: {self.flag_silent} | **Suppress Embeds**: {self.flag_suppress_embeds}\n"
        
        rr_display = "\n".join([f"{rr['emoji']} -> <@&{rr['role_id']}>" for rr in self.reaction_roles])
        if rr_display: info += f"\n**Reactions:**\n{rr_display}\n"

        kwargs["view"] = self
        return kwargs, info

    async def update_preview(self, interaction: discord.Interaction):
        kwargs, info = self.get_preview_kwargs()
        content = kwargs.get("content", "")
        preview_text = "**[PREVIEW INFO]**\n" + info + "\n**[MESSAGE PREVIEW]**\n" + (content or "")
        edit_kwargs = {"content": preview_text, "embed": kwargs.get("embed"), "view": self}
        
        if interaction.response.is_done():
            if self.preview_message:
                await self.preview_message.edit(**edit_kwargs)
        else:
            await interaction.response.edit_message(**edit_kwargs)

    @discord.ui.button(label="Text/Embed", style=discord.ButtonStyle.primary, row=0)
    async def edit_text_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MessageContentModal(self))

    @discord.ui.button(label="Embed Detail", style=discord.ButtonStyle.primary, row=0)
    async def edit_embed_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedContentModal(self))

    @discord.ui.button(label="Embed Fields", style=discord.ButtonStyle.primary, row=0)
    async def fields_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="**Embed Fields Config**", embed=None, view=EmbedFieldsMenuView(self))

    @discord.ui.button(label="Thread Name", style=discord.ButtonStyle.secondary, row=1)
    async def thread_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ThreadModal(self))

    @discord.ui.button(label="Toggle Flags", style=discord.ButtonStyle.secondary, row=1)
    async def flags_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.flag_silent = not self.flag_silent
        self.flag_suppress_embeds = not self.flag_suppress_embeds
        await self.update_preview(interaction)

    @discord.ui.button(label="Reactions", style=discord.ButtonStyle.secondary, row=1)
    async def reactions_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="**Reactions Roles Config**", embed=None, view=ReactionRolesMenuView(self))

    @discord.ui.button(label="Publish", emoji="✅", style=discord.ButtonStyle.success, row=2)
    async def publish_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        kwargs, _ = self.get_preview_kwargs()
        
        send_kwargs = {}
        if kwargs.get("content"):
            send_kwargs["content"] = kwargs["content"]
        if kwargs.get("embed"):
            send_kwargs["embed"] = kwargs["embed"]
            
        try:
            if self.target_message:
                final_msg = await self.target_message.edit(**send_kwargs)
                await database.delete_reaction_roles_for_message(final_msg.id)
            else:
                flags = discord.MessageFlags()
                if self.flag_silent: flags.suppress_notifications = True
                if self.flag_suppress_embeds: flags.suppress_embeds = True
                if flags.value != 0:
                    send_kwargs["flags"] = flags
                
                final_msg = await interaction.channel.send(**send_kwargs)
                
                # In TextChannels, we create the thread after the message is sent.
                if self.thread_name and isinstance(interaction.channel, discord.TextChannel):
                    try:
                        await final_msg.create_thread(name=self.thread_name)
                    except discord.HTTPException:
                        pass
        except discord.HTTPException as e:
            err_msg = "❌ **Failed to publish:**\n"
            if "content" in str(e).lower() and "cannot be empty" in str(e).lower():
                err_msg += "Your message must contain either Text Content or an Embed."
            else:
                err_msg += str(e)
            await interaction.followup.send(err_msg, ephemeral=True)
            return

        for rr in self.reaction_roles:
            await database.add_reaction_role(final_msg.id, interaction.guild_id, rr['emoji'], rr['role_id'])
            try:
                await final_msg.add_reaction(rr['emoji'])
            except discord.HTTPException as e:
                await interaction.followup.send(f"⚠️ Could not add reaction `{rr['emoji']}`: {e}", ephemeral=True)

        for item in self.children: item.disabled = True
        await self.preview_message.edit(content="**[PUBLISHED SUCCESSFULLY]**", view=self, embed=None)
        await interaction.followup.send("Message published and configured successfully!", ephemeral=True)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, row=2, disabled=True)
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if self.target_message:
            try:
                await self.target_message.delete()
                await database.delete_reaction_roles_for_message(self.target_message.id)
                for item in self.children: item.disabled = True
                await self.preview_message.edit(content="**[DELETED]**", view=self, embed=None)
                await interaction.followup.send("Message deleted successfully.", ephemeral=True)
            except discord.HTTPException as e:
                await interaction.followup.send(f"Failed to delete message: {e}", ephemeral=True)


class MessageBuilder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ctx_menu = app_commands.ContextMenu(name="Edit Bot Message", callback=self.edit_bot_message_ctx)
        self.bot.tree.add_command(self.ctx_menu)

    def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    @app_commands.command(name="send_as", description="Send a message as Carrot")
    @app_commands.describe(message="The message to send")
    async def send_as(self, interaction: discord.Interaction, message: str):
        # Allow administrators OR the specific superuser
        is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False
        if not (is_admin or interaction.user.id == 255174440005009408):
            await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.channel.send(message)
            await interaction.followup.send("Message sent successfully.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Failed to send message: {e}", ephemeral=True)

    @app_commands.command(name="message_builder", description="Open interactive Webhook message builder")
    async def message_builder(self, interaction: discord.Interaction):
        # Allow administrators OR the specific superuser
        is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False
        if not (is_admin or interaction.user.id == 255174440005009408):
            await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
            return

        view = BuilderControlView(self)
        kwargs, info = view.get_preview_kwargs()
        await interaction.response.send_message(
            content="**[PREVIEW INFO]**\n" + info + "\n**[MESSAGE PREVIEW]**\n" + (kwargs.get("content") or ""),
            embed=kwargs.get("embed"), view=view, ephemeral=True
        )
        view.preview_message = await interaction.original_response()

    async def edit_bot_message_ctx(self, interaction: discord.Interaction, message: discord.Message):
        # Allow administrators OR the specific superuser
        is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False
        if not (is_admin or interaction.user.id == 255174440005009408):
            await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
            return

        if message.author.id != self.bot.user.id:
            await interaction.response.send_message("You can only edit messages sent by this bot.", ephemeral=True)
            return

        view = BuilderControlView(self, target_message=message)

        # Load existing reaction roles
        existing_rrs = await database.get_reaction_roles_for_message(message.id)
        view.reaction_roles = existing_rrs
        
        # Load existing embed fields
        if message.embeds:
            for field in message.embeds[0].fields:
                view.embed_fields.append({
                    'name': field.name,
                    'value': field.value,
                    'inline': field.inline
                })

        kwargs, info = view.get_preview_kwargs()
        await interaction.response.send_message(
            content="**[PREVIEW INFO]**\n" + info + "\n**[MESSAGE PREVIEW]**\n" + (kwargs.get("content") or ""),
            embed=kwargs.get("embed"), view=view, ephemeral=True
        )
        view.preview_message = await interaction.original_response()

    # --- Listeners ---
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id: return
        rrs = await database.get_reaction_roles_for_message(payload.message_id)
        if not rrs: return
        
        channel = self.bot.get_channel(payload.channel_id)
        matched = False
        for rr in rrs:
            db_emoji = rr['emoji'].replace('\ufe0f', '')
            payload_emoji = str(payload.emoji).replace('\ufe0f', '')
            
            # Extract just the ID if it's a custom emoji to be absolutely safe
            db_id = re.search(r':([0-9]+)>?$', db_emoji)
            pl_id = re.search(r':([0-9]+)>?$', payload_emoji)
            
            is_match = False
            if db_emoji == payload_emoji or payload_emoji == f"<:{db_emoji}>" or payload_emoji == f"<a:{db_emoji}>":
                is_match = True
            elif db_id and pl_id and db_id.group(1) == pl_id.group(1):
                is_match = True
                
            if is_match:
                matched = True
                guild = self.bot.get_guild(payload.guild_id)
                if guild:
                    member = payload.member
                    if not member:
                        try: member = await guild.fetch_member(payload.user_id)
                        except discord.HTTPException: pass
                            
                    role = guild.get_role(rr['role_id'])
                    if member and role:
                        try: 
                            await member.add_roles(role)
                        except discord.errors.Forbidden: 
                            if channel: await channel.send(f"❌ **Permission Error:** I cannot assign the `{role.name}` role. Please ensure I have the **Manage Roles** permission and my role is placed *above* `{role.name}` in the server settings.", delete_after=10)
                        except Exception as e: 
                            if channel: await channel.send(f"❌ **Error adding role:** {e}", delete_after=10)
                    else:
                        if channel: await channel.send(f"❌ **Error:** Could not find the role or member! (Role exists: {role is not None})", delete_after=10)

        # Uncomment for deep debugging if needed
        # if not matched and channel:
        #    await channel.send(f"DEBUG: No emoji match found. Payload: {payload_emoji}. DB: {[r['emoji'] for r in rrs]}", delete_after=15)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id: return
        rrs = await database.get_reaction_roles_for_message(payload.message_id)
        if not rrs: return
        for rr in rrs:
            db_emoji = rr['emoji'].replace('\ufe0f', '')
            payload_emoji = str(payload.emoji).replace('\ufe0f', '')
            
            db_id = re.search(r':([0-9]+)>?$', db_emoji)
            pl_id = re.search(r':([0-9]+)>?$', payload_emoji)
            
            is_match = False
            if db_emoji == payload_emoji or payload_emoji == f"<:{db_emoji}>" or payload_emoji == f"<a:{db_emoji}>":
                is_match = True
            elif db_id and pl_id and db_id.group(1) == pl_id.group(1):
                is_match = True
                
            if is_match:
                guild = self.bot.get_guild(payload.guild_id)
                if guild:
                    member = guild.get_member(payload.user_id)
                    if not member:
                        try: member = await guild.fetch_member(payload.user_id)
                        except discord.HTTPException: pass
                            
                    role = guild.get_role(rr['role_id'])
                    if member and role:
                        try: await member.remove_roles(role)
                        except discord.HTTPException: pass

    # --- Listeners (End) ---


async def setup(bot):
    await bot.add_cog(MessageBuilder(bot))
