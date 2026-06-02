import discord
from discord.ext import commands
import os
import database
import asyncio
from datetime import datetime, timezone, timedelta

def sanitize_reason(text: str) -> str:
    if not text:
        return ""
    text = text.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
    if len(text) > 500:
        text = text[:500] + "..."
    return text

class ConfirmRemovalView(discord.ui.View):
    def __init__(self, target_message: discord.Message, reason: str, cog, staff_interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.target_message = target_message
        self.reason = reason
        self.cog = cog
        self.staff_interaction = staff_interaction
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    @discord.ui.button(label="Confirm Removal", style=discord.ButtonStyle.success)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Executing removal...", embed=None, view=self)
        await self.cog.execute_removal(interaction, self.target_message, self.reason, self.target_message.content)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Removal cancelled.", embed=None, view=self)

class RemovalDropdownView(discord.ui.View):
    def __init__(self, select_item, timeout=180):
        super().__init__(timeout=timeout)
        self.add_item(select_item)
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

class RemovalReasonSelect(discord.ui.Select):
    def __init__(self, target_message: discord.Message, cog):
        self.target_message = target_message
        self.cog = cog
        options = [
            discord.SelectOption(label="Pricing below server minimum", value="pricing_below_min"),
            discord.SelectOption(label="Lack of visible pricing", value="no_visible_pricing"),
            discord.SelectOption(label="Lack of/No mentions of ToS", value="no_tos_mention"),
            discord.SelectOption(label="Incomplete ToS", value="incomplete_tos"),
            discord.SelectOption(label="Advertising in wrong channel", value="wrong_channel"),
            discord.SelectOption(label="Advertising in wrong channel + no art seller", value="wrong_channel_no_seller"),
            discord.SelectOption(label="Others...", value="others")
        ]
        super().__init__(placeholder="Select reason(s) for removal...", options=options, min_values=1, max_values=len(options))

    async def callback(self, interaction: discord.Interaction):
        if not any(role.id in self.cog.staff_role_ids for role in interaction.user.roles):
            await interaction.response.send_message("You do not have the required staff role to perform this action.", ephemeral=True)
            return

        reasons_map = {
            "pricing_below_min": "pricing below our [server minimum of 15USD](https://discord.com/channels/369798142289510401/492328409175687179/1481767967103389727)",
            "no_visible_pricing": "lack of [visible pricing](https://discord.com/channels/369798142289510401/492328409175687179/1481767967103389727) on your post",
            "no_tos_mention": "a lack of visible [Terms of Services(ToS)](https://discord.com/channels/369798142289510401/1191922480961552424) nor does your post indicate anywhere where it can be found",
            "incomplete_tos": "an incomplete Terms of Services(ToS) (please read [this guide](https://discord.com/channels/369798142289510401/1191922480961552424) to know what should be included in your ToS)",
            "wrong_channel": "advertising outside of the designated [commissions channel](https://discord.com/channels/369798142289510401/1393271200729268294/1476738957826850868)",
            "wrong_channel_no_seller": "advertising outside of the designated commissions channel and without Art Seller role (read https://discord.com/channels/369798142289510401/635030026911481856 on how to obtain it)"
        }

        if "others" in self.values:
            predefined = [reasons_map[v] for v in self.values if v != "others" and v in reasons_map]
            modal = CustomRemovalReasonModal(self.target_message, self.cog, predefined_reasons=predefined)
            await interaction.response.send_modal(modal)
        else:
            if len(self.values) == 1:
                reason = f"Your post has been removed from {self.target_message.channel.mention} due to {reasons_map[self.values[0]]}."
            else:
                formatted_list = "\n".join([f"- {reasons_map[v]}" for v in self.values if v in reasons_map])
                reason = f"Your post has been removed from {self.target_message.channel.mention} due to:\n{formatted_list}"

            confirm_embed = discord.Embed(
                title="Confirm Post Removal",
                description=f"Are you sure you want to remove the post by {self.target_message.author.mention}?\n\n**Reason:**\n{reason}",
                color=discord.Color.yellow()
            )
            confirm_view = ConfirmRemovalView(self.target_message, reason, self.cog, interaction)
            await interaction.response.edit_message(content=None, embed=confirm_embed, view=confirm_view)
            try:
                confirm_view.message = await interaction.original_response()
            except Exception:
                pass

class CustomRemovalReasonModal(discord.ui.Modal, title="Reason for removal"):
    def __init__(self, target_message: discord.Message, cog, predefined_reasons: list = None):
        super().__init__()
        self.target_message = target_message
        self.cog = cog
        self.predefined_reasons = predefined_reasons or []

    reason_input = discord.ui.TextInput(
        label="Reason",
        placeholder="Enter the reason for post removal...",
        style=discord.TextStyle.long,
        required=True,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        custom_reason = self.reason_input.value
        custom_reason_sanitized = sanitize_reason(custom_reason)

        if self.predefined_reasons:
            formatted_list = "\n".join([f"- {r}" for r in self.predefined_reasons] + [f"- {custom_reason_sanitized}"])
            reason = f"Your post has been removed from {self.target_message.channel.mention} due to:\n{formatted_list}"
        else:
            reason = f"Your post has been removed from {self.target_message.channel.mention} due to {custom_reason_sanitized}."

        confirm_embed = discord.Embed(
            title="Confirm Post Removal",
            description=f"Are you sure you want to remove the post by {self.target_message.author.mention}?\n\n**Reason:**\n{reason}",
            color=discord.Color.yellow()
        )
        confirm_view = ConfirmRemovalView(self.target_message, reason, self.cog, interaction)
        await interaction.response.send_message(embed=confirm_embed, view=confirm_view, ephemeral=True)
        try:
            confirm_view.message = await interaction.original_response()
        except Exception:
            pass

class WarningsPaginationView(discord.ui.View):
    def __init__(self, user, total_count, get_page_callback, guild_id, notice_channel_id, timeout=900):
        super().__init__(timeout=timeout)
        self.user = user
        self.total_count = total_count
        self.get_page_callback = get_page_callback
        self.guild_id = guild_id
        self.notice_channel_id = notice_channel_id
        self.current_page = 0
        self.page_size = 5
        self.max_pages = (total_count - 1) // self.page_size + 1 if total_count > 0 else 1
        self.message = None
        self.update_buttons()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    def update_buttons(self):
        self.prev_btn.disabled = self.current_page == 0
        self.next_btn.disabled = self.current_page >= self.max_pages - 1

    async def get_page_embed(self) -> discord.Embed:
        offset = self.current_page * self.page_size
        page_warnings = await self.get_page_callback(self.user.id, self.page_size, offset)
        
        embed = discord.Embed(
            title=f"Verbals - User: {self.user.name}({self.user.id})",
            color=discord.Color.orange()
        )
        embed.description = f"**Total : {self.total_count}**\n\n"
        
        if not page_warnings:
            embed.description += "No Verbals"
        else:
            for w in page_warnings:
                try:
                    dt = datetime.strptime(w['warned_at'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                    ts = int(dt.timestamp())
                    time_str = f"<t:{ts}:f>"
                except Exception:
                    time_str = w['warned_at']
                
                staff_str = f"<@{w['staff_id']}>({w['staff_id']})" if w['staff_id'] else "System/Unknown"
                embed.description += (
                    f"**#ID : {w['id']}** : ({time_str}) by:{staff_str}\n"
                    f"Reason: {w['reason'] or w['message_content']}\n"
                    f"> [Source](https://discord.com/channels/{self.guild_id}/{w['channel_id']}/{w['message_id']})\n\n"
                )
        
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.max_pages} • Today at {datetime.now(timezone.utc).strftime('%H:%M')}")
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, custom_id="prev_page")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            embed = await self.get_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary, custom_id="next_page")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            self.update_buttons()
            embed = await self.get_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="close_page")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

class StaffWarningsPaginationView(discord.ui.View):
    def __init__(self, staff_user, total_count, get_page_callback, guild_id, notice_channel_id, timeout=900):
        super().__init__(timeout=timeout)
        self.staff_user = staff_user
        self.total_count = total_count
        self.get_page_callback = get_page_callback
        self.guild_id = guild_id
        self.notice_channel_id = notice_channel_id
        self.current_page = 0
        self.page_size = 5
        self.max_pages = (total_count - 1) // self.page_size + 1 if total_count > 0 else 1
        self.message = None
        self.update_buttons()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    def update_buttons(self):
        self.prev_btn.disabled = self.current_page == 0
        self.next_btn.disabled = self.current_page >= self.max_pages - 1

    async def get_page_embed(self) -> discord.Embed:
        offset = self.current_page * self.page_size
        page_warnings = await self.get_page_callback(self.staff_user.id, self.page_size, offset)
        
        embed = discord.Embed(
            title=f"Verbals by {self.staff_user.name}({self.staff_user.id})",
            color=discord.Color.blue()
        )
        embed.description = f"**Total Verbals Issued: {self.total_count}**\n\n"
        
        if not page_warnings:
            embed.description += "No Verbals Issued"
        else:
            for w in page_warnings:
                try:
                    dt = datetime.strptime(w['warned_at'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                    ts = int(dt.timestamp())
                    time_str = f"<t:{ts}:f>"
                except Exception:
                    time_str = w['warned_at']
                
                embed.description += (
                    f"**#ID : {w['id']}** : ({time_str}) for user: <@{w['user_id']}>({w['user_id']})\n"
                    f"Reason: {w['reason'] or w['message_content']}\n"
                    f"> [Source](https://discord.com/channels/{self.guild_id}/{w['channel_id']}/{w['message_id']})\n\n"
                )
        
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.max_pages} • Today at {datetime.now(timezone.utc).strftime('%H:%M')}")
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, custom_id="prev_page_staff")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            embed = await self.get_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary, custom_id="next_page_staff")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            self.update_buttons()
            embed = await self.get_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="close_page_staff")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

class HelpPaginationView(discord.ui.View):
    def __init__(self, timeout=900):
        super().__init__(timeout=timeout)
        self.current_page = 0
        self.message = None
        self.pages = [
            {
                "title": "🥕 Verbal Tracker Commands",
                "color": discord.Color.orange(),
                "fields": [
                    ("!verbals <userid>", "Retrieve a paginated list of verbal notices for the specified user ID.", False),
                    ("!delverbal <id>", "Deletes a verbal notice from the database using its unique Verbal ID.", False),
                    ("!verbalby <userid>", "Retrieve a paginated list of all verbal notices issued by the specified staff member ID.", False),
                    ("!sync_warnings", "Syncs the last 3 months of verbals in #staff-notice into the SQLite database.", False)
                ]
            },
            {
                "title": "🥕 Setup & General Commands",
                "color": discord.Color.green(),
                "fields": [
                    ("!setup_paid_requests", "Sends the persistent 'Create Request' embed/button to the configured paid requests channel.", False),
                    ("!chatbot_setup_channel", "Sends the persistent 'Start Chat' chatbot embed/button to the configured channel.", False),
                    ("!carrothelp", "Show this paginated help menu.", False)
                ]
            }
        ]
        self.update_buttons()

    def update_buttons(self):
        self.prev_btn.disabled = self.current_page == 0
        self.next_btn.disabled = self.current_page == len(self.pages) - 1

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    def get_page_embed(self) -> discord.Embed:
        page_data = self.pages[self.current_page]
        embed = discord.Embed(
            title=page_data["title"],
            color=page_data["color"],
            description="Here are the commands available in Carrot Bot:"
        )
        for name, value, inline in page_data["fields"]:
            embed.add_field(name=name, value=value, inline=inline)
        embed.set_footer(text=f"Page {self.current_page + 1} of {len(self.pages)}")
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, custom_id="help_prev")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary, custom_id="help_next")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="help_close")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

class WarningTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.notice_channel_id = int(os.getenv("STAFF_NOTICE_CHANNEL_ID") or 748949267397476392)
        self.commands_channel_id = int(os.getenv("STAFF_COMMANDS_CHANNEL_ID") or 0)
        self.log_channel_id = int(os.getenv("STAFF_LOG_CHANNEL_ID") or 0)
        
        # Support multiple staff roles via comma-separated list
        role_ids_str = os.getenv("STAFF_ROLE_IDS") or ""
        if role_ids_str:
            self.staff_role_ids = [int(r.strip()) for r in role_ids_str.split(",") if r.strip().isdigit()]
        else:
            single_id = os.getenv("STAFF_ROLE_ID") or "0"
            self.staff_role_ids = [int(single_id)] if single_id.isdigit() else []

        # Add Context Menu
        self.ctx_menu = discord.app_commands.ContextMenu(
            name="Remove Post",
            callback=self.remove_post_callback
        )
        self.bot.tree.add_command(self.ctx_menu)

    def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    async def cog_check(self, ctx):
        """Restricts all commands in this cog to only work in the staff command channel by authorized staff."""
        # Developer bypass for user 255174440005009408 (allows running anywhere including DMs)
        if ctx.author.id == 255174440005009408:
            return True

        # Explicitly block commands in DMs for everyone else
        if ctx.guild is None:
            return False

        # 1. Restrict to staff commands channel
        if self.commands_channel_id != 0 and ctx.channel.id != self.commands_channel_id:
            try:
                await ctx.send(f"Error: This command can only be used in the staff commands channel (<#{self.commands_channel_id}>).", delete_after=5)
                if ctx.guild:
                    await ctx.message.delete()
            except Exception:
                pass
            return False

        # 2. Restrict to staff role holders or server admins
        if ctx.guild:
            has_role = any(role.id in self.staff_role_ids for role in ctx.author.roles)
            is_admin = ctx.author.guild_permissions.administrator
            if not (has_role or is_admin):
                try:
                    await ctx.send("Error: You do not have the required staff role to use this command.", delete_after=5)
                    await ctx.message.delete()
                except Exception:
                    pass
                return False

        return True

    async def remove_post_callback(self, interaction: discord.Interaction, message: discord.Message):
        await interaction.response.defer(ephemeral=True)
        # Check role
        if not any(role.id in self.staff_role_ids for role in interaction.user.roles):
            await interaction.followup.send("You do not have the required staff role to use this command.", ephemeral=True)
            return

        # Send ephemeral dropdown select menu
        view = RemovalDropdownView(RemovalReasonSelect(message, self), timeout=180)
        msg = await interaction.followup.send("Select a reason to remove this post:", view=view, ephemeral=True)
        view.message = msg

    async def execute_removal(self, interaction: discord.Interaction, message: discord.Message, reason: str, original_content: str):
        # Delete message
        try:
            await message.delete()
        except discord.HTTPException as e:
            await interaction.followup.send(f"Failed to delete the message: {e}", ephemeral=True)
            return

        # Post warning in #staff-notice (748949267397476392)
        notice_channel = self.bot.get_channel(self.notice_channel_id)
        if not notice_channel:
            try:
                notice_channel = await asyncio.wait_for(self.bot.fetch_channel(self.notice_channel_id), timeout=5.0)
            except Exception:
                pass

        notice_msg = None
        if notice_channel:
            try:
                allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
                notice_msg = await notice_channel.send(content=f"{message.author.mention} {reason}", allowed_mentions=allowed_mentions)
            except Exception as e:
                print(f"Error sending notice message: {e}")

        # Log it in staff log channel
        log_channel = self.bot.get_channel(self.log_channel_id)
        if not log_channel:
            try:
                log_channel = await asyncio.wait_for(self.bot.fetch_channel(self.log_channel_id), timeout=5.0)
            except Exception:
                pass

        log_msg = None
        if log_channel:
            log_embed = discord.Embed(
                title="Log: Post Removed",
                color=discord.Color.orange()
            )
            log_embed.add_field(name="Staff Member", value=f"{interaction.user.mention} ({interaction.user.id})", inline=True)
            log_embed.add_field(name="Original Author", value=f"{message.author.mention} ({message.author.id})", inline=True)
            log_embed.add_field(name="Channel", value=message.channel.mention, inline=True)
            log_embed.add_field(name="Rejection Reason", value=reason, inline=False)
            
            content_snippet = original_content if original_content else "*No text content*"
            if len(content_snippet) > 800:
                content_snippet = content_snippet[:800] + "..."
            
            log_embed.add_field(
                name="Original Post Content",
                value=f"```\n{content_snippet}\n```",
                inline=False
            )
            
            if message.attachments:
                attachments_list = "\n".join([a.url for a in message.attachments])
                log_embed.add_field(name="Attachments", value=attachments_list, inline=False)
                
            try:
                log_msg = await log_channel.send(embed=log_embed)
            except Exception as e:
                print(f"Error sending log embed: {e}")

        # Add warning to database (prioritize log channel/msg, then staff notice)
        warn_channel_id = self.log_channel_id if log_msg else (self.notice_channel_id if notice_msg else message.channel.id)
        warn_message_id = log_msg.id if log_msg else (notice_msg.id if notice_msg else 0)
        
        # Format attachments as plain links (wrapped in <> to prevent previews) and append to reason
        db_reason = reason
        if message.attachments:
            attachments_str = "\n**Attachments:**\n" + "\n".join([f"- <{a.url}>" for a in message.attachments])
            db_reason += attachments_str
        
        await database.add_warning(
            user_id=message.author.id,
            channel_id=warn_channel_id,
            message_id=warn_message_id,
            message_content=db_reason,
            staff_id=interaction.user.id,
            reason=db_reason
        )

        await interaction.followup.send("Post successfully removed, logged, and verbal notice recorded.", ephemeral=True)

        # Warning threshold check (3 warnings in 3 months)
        count = await database.get_warnings_count_last_3_months(message.author.id)
        if count >= 3:
            commands_channel = self.bot.get_channel(self.commands_channel_id)
            if not commands_channel:
                try:
                    commands_channel = await asyncio.wait_for(self.bot.fetch_channel(self.commands_channel_id), timeout=5.0)
                except Exception:
                    pass
            if commands_channel:
                last_warnings = await database.get_last_3_warnings(message.author.id)
                last_warnings.reverse()
                
                formatted_warnings = []
                for idx, (content, warned_at) in enumerate(last_warnings, 1):
                    try:
                        dt = datetime.strptime(warned_at, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                        ts = int(dt.timestamp())
                        time_str = f"<t:{ts}:f>"
                    except Exception:
                        time_str = "Unknown Date"
                    
                    lines = content.split('\n')
                    formatted_lines = []
                    sub_bullet_idx = 0
                    for line in lines:
                        if line.startswith("- "):
                            prefix = "-> " if sub_bullet_idx == 0 else "-> "
                            formatted_lines.append(prefix + line[2:])
                            sub_bullet_idx += 1
                        else:
                            formatted_lines.append(line)
                    
                    quoted_content = "\n> ".join(formatted_lines)
                    formatted_warnings.append(f"> {idx}. ({time_str}) {quoted_content}")
                
                warnings_str = "\n".join(formatted_warnings)
                
                # Fetch last staff member who warned this user
                last_staff_id = await database.get_last_warning_staff_id_last_3_months(message.author.id)
                staff_mention = f"<@{last_staff_id}>" if last_staff_id else interaction.user.mention
                
                allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
                await commands_channel.send(
                    f"{staff_mention}, user {message.author.mention} has accumulated {count} verbal notice(s) within 3 months. Please take immediate action.\n{warnings_str}",
                    allowed_mentions=allowed_mentions
                )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bot messages
        if message.author.bot:
            return
            
        # Check if the message is in the staff-notice channel
        if message.channel.id != self.notice_channel_id:
            return
            
        # Check for user mentions
        if not message.mentions:
            return
            
        commands_channel = self.bot.get_channel(self.commands_channel_id)
        if not commands_channel:
            try:
                commands_channel = await asyncio.wait_for(self.bot.fetch_channel(self.commands_channel_id), timeout=5.0)
            except Exception:
                pass
        
        for user in message.mentions:
            if user.bot:
                continue
                
            # Add warning to database (saving message content)
            await database.add_warning(
                user_id=user.id,
                channel_id=message.channel.id,
                message_id=message.id,
                message_content=message.content,
                staff_id=message.author.id,
                reason=message.content
            )
            
            # Check warning count for the last 3 months
            count = await database.get_warnings_count_last_3_months(user.id)
            
            if count >= 3 and commands_channel:
                last_warnings = await database.get_last_3_warnings(user.id)
                last_warnings.reverse()
                
                formatted_warnings = []
                for idx, (content, warned_at) in enumerate(last_warnings, 1):
                    try:
                        dt = datetime.strptime(warned_at, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                        ts = int(dt.timestamp())
                        time_str = f"<t:{ts}:f>"
                    except Exception:
                        time_str = "Unknown Date"
                    
                    lines = content.split('\n')
                    formatted_lines = []
                    sub_bullet_idx = 0
                    for line in lines:
                        if line.startswith("- "):
                            prefix = "-> " if sub_bullet_idx == 0 else "  -> "
                            formatted_lines.append(prefix + line[2:])
                            sub_bullet_idx += 1
                        else:
                            formatted_lines.append(line)
                    
                    quoted_content = "\n> ".join(formatted_lines)
                    formatted_warnings.append(f"> {idx}. ({time_str}) {quoted_content}")
                
                warnings_str = "\n".join(formatted_warnings)
                
                # Ping the last staff member who warned them instead of Carrot
                last_staff_id = await database.get_last_warning_staff_id_last_3_months(user.id)
                staff_mention = f"<@{last_staff_id}>" if last_staff_id else message.author.mention
                
                await commands_channel.send(
                    f"{staff_mention}, user {user.mention} has accumulated {count} verbal notice(s) within 3 months. Please take immediate action.\n{warnings_str}"
                )

    @commands.command(name="verbals")
    async def verbals(self, ctx, user: discord.User = None):
        # Allow checking either self or specific user
        target_user = user or ctx.author
        
        total_count = await database.get_warnings_count(target_user.id)
        
        # Build paginated view
        view = WarningsPaginationView(target_user, total_count, database.get_warnings_paginated, ctx.guild.id if ctx.guild else "@me", self.notice_channel_id)
        embed = await view.get_page_embed()
        view.message = await ctx.send(embed=embed, view=view)

    @commands.command(name="delverbal")
    async def delverbal(self, ctx, warning_id: int):
        # Restrict command to users with the specific staff roles (bypassed for developer)
        if ctx.author.id != 255174440005009408:
            if not ctx.guild or not any(role.id in self.staff_role_ids for role in ctx.author.roles):
                await ctx.send("You do not have the required staff role to use this command.")
                return

        # Fetch the warning first
        warn = await database.get_warning_by_id(warning_id)
        if not warn:
            await ctx.send(f"Verbal ID #{warning_id} was not found in the database.")
            return

        # Delete the message in #staff-notice
        notice_channel = self.bot.get_channel(self.notice_channel_id)
        if not notice_channel:
            try:
                notice_channel = await asyncio.wait_for(self.bot.fetch_channel(self.notice_channel_id), timeout=5.0)
            except Exception:
                pass
        
        if notice_channel and warn['message_id']:
            try:
                msg = await notice_channel.fetch_message(warn['message_id'])
                await msg.delete()
            except Exception:
                pass # Message might have been manually deleted already

        # Delete from database
        await database.delete_warning_by_id(warning_id)

        # Log it in staff log channel
        log_channel = self.bot.get_channel(self.log_channel_id)
        if not log_channel:
            try:
                log_channel = await asyncio.wait_for(self.bot.fetch_channel(self.log_channel_id), timeout=5.0)
            except Exception:
                pass
        
        if log_channel:
            log_embed = discord.Embed(
                title="Log: Verbal Notice Deleted",
                color=discord.Color.red()
            )
            log_embed.add_field(name="Staff Member", value=f"{ctx.author.mention} ({ctx.author.id})", inline=True)
            log_embed.add_field(name="Target User", value=f"<@{warn['user_id']}> ({warn['user_id']})", inline=True)
            log_embed.add_field(name="Verbal ID", value=f"#{warning_id}", inline=True)
            log_embed.add_field(name="Original Reason", value=warn['reason'] or warn['message_content'] or "*None*", inline=False)
            
            await log_channel.send(embed=log_embed)

        await ctx.send(f"Successfully deleted verbal notice with ID #{warning_id} from `#staff-notice` and database.")

    @commands.command(name="verbalby")
    async def verbalby(self, ctx, staff: discord.User = None):
        # Restrict command to users with the specific staff roles (bypassed for developer)
        if ctx.author.id != 255174440005009408:
            if not ctx.guild or not any(role.id in self.staff_role_ids for role in ctx.author.roles):
                await ctx.send("You do not have the required staff role to use this command.")
                return

        target_staff = staff or ctx.author
        total_count = await database.get_warnings_by_staff_count(target_staff.id)
        
        # Build paginated view
        view = StaffWarningsPaginationView(target_staff, total_count, database.get_warnings_by_staff_paginated, ctx.guild.id if ctx.guild else "@me", self.notice_channel_id)
        embed = await view.get_page_embed()
        view.message = await ctx.send(embed=embed, view=view)

    @commands.command(name="sync_warnings")
    async def sync_warnings(self, ctx):
        # Restrict command to administrators (bypassed for developer)
        if ctx.author.id != 255174440005009408:
            if not ctx.guild or not ctx.author.guild_permissions.administrator:
                await ctx.send("You do not have the required administrator permissions to use this command.")
                return
        notice_channel = self.bot.get_channel(self.notice_channel_id)
        if not notice_channel:
            await ctx.send("Error: Could not access the staff notice channel. Please verify the ID.")
            return

        status_msg = await ctx.send("Starting verbal notices history sync (last 3 months)... This may take a moment.")
        
        imported_count = 0
        
        # Fetch message history of the staff-notice channel from the last 3 months (90 days)
        three_months_ago = datetime.now(timezone.utc) - timedelta(days=90)
        async for message in notice_channel.history(limit=None, after=three_months_ago, oldest_first=True):
            # Ignore other bots (allow Carrot since Carrot will be posting warnings now)
            if message.author.bot and message.author.id != self.bot.user.id:
                continue
            if not message.mentions:
                continue
                
            warned_at_str = message.created_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            
            for user in message.mentions:
                if user.bot:
                    continue
                    
                # Check if already imported
                exists = await database.warning_exists(message.id, user.id)
                if not exists:
                    # Sync staff ID: message.author is the staff unless the message was sent by the bot
                    staff_id = None if message.author.bot else message.author.id
                    await database.add_warning(
                        user_id=user.id, 
                        channel_id=message.channel.id, 
                        message_id=message.id, 
                        message_content=message.content,
                        staff_id=staff_id,
                        reason=message.content,
                        warned_at=warned_at_str
                    )
                    imported_count += 1

        await status_msg.edit(content=f"Sync complete! Imported {imported_count} historical verbal notices into the database.")

    @commands.command(name="carrothelp")
    async def help_command(self, ctx):
        view = HelpPaginationView()
        embed = view.get_page_embed()
        view.message = await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(WarningTracker(bot))
