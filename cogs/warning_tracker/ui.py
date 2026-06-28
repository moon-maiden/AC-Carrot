import discord
import database
from datetime import datetime, timezone
from .helpers import sanitize_reason, get_channel_mention

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
    def __init__(self, target_message: discord.Message, cog, reasons_db: list):
        self.target_message = target_message
        self.cog = cog
        self.reasons_db = reasons_db
        options = [discord.SelectOption(label=r['label'][:100], value=r['id'][:100]) for r in reasons_db]
        options.append(discord.SelectOption(label="Others...", value="others"))
        super().__init__(placeholder="Select reason(s) for removal...", options=options[:25], min_values=1, max_values=len(options[:25]))

    async def callback(self, interaction: discord.Interaction):
        config = await database.get_guild_config(interaction.guild_id or 0)
        staff_role_ids = [config.get("team_leader_role_id"), config.get("moderator_role_id"), config.get("trial_moderator_role_id")]
        
        is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False
        if interaction.user.id != 255174440005009408 and not is_admin and not any(role.id in staff_role_ids for role in interaction.user.roles):
            await interaction.response.send_message("You do not have the required staff role to perform this action.", ephemeral=True)
            return

        reasons_map = {r['id']: r['text'] for r in self.reasons_db}

        if "others" in self.values:
            predefined = [reasons_map[v] for v in self.values if v != "others" and v in reasons_map]
            modal = CustomRemovalReasonModal(self.target_message, self.cog, predefined_reasons=predefined)
            await interaction.response.send_modal(modal)
        else:
            chan_mention = get_channel_mention(self.target_message.channel)
            if len(self.values) == 1:
                selected_reason = reasons_map[self.values[0]]
                if selected_reason.startswith("as "):
                    reason = f"Your post has been removed from {chan_mention} {selected_reason}"
                else:
                    reason = f"Your post has been removed from {chan_mention} due to {selected_reason}"
            else:
                formatted_list = "\n".join([f"- {reasons_map[v]}" for v in self.values if v in reasons_map])
                reason = f"Your post has been removed from {chan_mention} due to:\n{formatted_list}"

            preview_desc = (
                f"Are you sure you want to remove the post by {self.target_message.author.mention}?\n\n"
                f"**Preview of notice message to be sent:**\n"
                f"{self.target_message.author.mention} {reason}"
            )
            confirm_embed = discord.Embed(
                title="Confirm Post Removal",
                description=preview_desc,
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

        chan_mention = get_channel_mention(self.target_message.channel)
        if self.predefined_reasons:
            formatted_list = "\n".join([f"- {r}" for r in self.predefined_reasons] + [f"- {custom_reason_sanitized}"])
            reason = f"Your post has been removed from {chan_mention} due to:\n{formatted_list}"
        else:
            reason = f"Your post has been removed from {chan_mention} due to {custom_reason_sanitized}."

        preview_desc = (
            f"Are you sure you want to remove the post by {self.target_message.author.mention}?\n\n"
            f"**Preview of notice message to be sent:**\n"
            f"{self.target_message.author.mention} {reason}"
        )
        confirm_embed = discord.Embed(
            title="Confirm Post Removal",
            description=preview_desc,
            color=discord.Color.yellow()
        )
        confirm_view = ConfirmRemovalView(self.target_message, reason, self.cog, interaction)
        await interaction.response.send_message(embed=confirm_embed, view=confirm_view, ephemeral=True)
        try:
            confirm_view.message = await interaction.original_response()
        except Exception:
            pass

class VerbalPreviewView(discord.ui.View):
    def __init__(self, action: str, reason_id: str, label: str, text: str, interaction: discord.Interaction):
        super().__init__(timeout=120)
        self.action = action
        self.reason_id = reason_id
        self.label_str = label
        self.text_str = text
        self.original_interaction = interaction

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        guild_id = interaction.guild_id or 0
        if self.action == "remove":
            await database.delete_verbal_reason(guild_id, self.reason_id)
            await interaction.followup.send(f"✅ Verbal reason `{self.reason_id}` has been removed.", ephemeral=True)
        else:
            await database.add_verbal_reason(guild_id, self.reason_id, self.label_str, self.text_str)
            await interaction.followup.send(f"✅ Verbal reason `{self.reason_id}` has been saved.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Action cancelled.", embed=None, view=self)

class VerbalReasonModal(discord.ui.Modal):
    def __init__(self, action: str, reason_id: str = None, default_label: str = "", default_text: str = ""):
        super().__init__(title=f"{action.capitalize()} Verbal Reason")
        self.action = action
        
        self.id_input = discord.ui.TextInput(
            label="Reason ID (Internal Identifier)",
            placeholder="e.g. underpricing",
            default=reason_id or "",
            style=discord.TextStyle.short,
            required=True,
            max_length=50
        )
        if action == "edit":
            self.id_input.disabled = True

        self.label_input = discord.ui.TextInput(
            label="Dropdown Label",
            placeholder="e.g. Underpricing",
            default=default_label,
            style=discord.TextStyle.short,
            required=True,
            max_length=100
        )
        
        self.text_input = discord.ui.TextInput(
            label="Warning Text",
            placeholder="Enter the detailed warning message here...",
            default=default_text,
            style=discord.TextStyle.long,
            required=True,
            max_length=4000
        )

        self.add_item(self.id_input)
        self.add_item(self.label_input)
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        rid = self.id_input.value.strip().replace(" ", "_").lower()
        lbl = self.label_input.value.strip()
        txt = self.text_input.value.strip()

        embed = discord.Embed(title=f"Preview: {self.action.capitalize()} Reason", color=discord.Color.yellow())
        embed.add_field(name="ID", value=rid, inline=True)
        embed.add_field(name="Label", value=lbl, inline=True)
        embed.add_field(name="Text", value=txt[:1024], inline=False)
        embed.set_footer(text="Please confirm to save changes.")

        view = VerbalPreviewView(self.action, rid, lbl, txt, interaction)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

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
                    ("!verbals <userid>", "Retrieve a list of verbal notices for the specified user ID.", False),
                    ("!delverbal <id>", "Deletes a verbal notice from the database using its unique Verbal ID.", False),
                    ("!verbalby <userid>", "Retrieve a paginated list of all verbal notices issued by the specified staff member ID.", False),
                    ("!sync_warnings", "Syncs the last 3 months of verbals in #staff-notice into the database.", False)
                ]
            },
            {
                "title": "🥕 Setup & General Commands",
                "color": discord.Color.green(),
                "fields": [
                    ("!setup_paid_requests", "Sends the persistent 'Create Request' embed/button to the configured paid requests channel.", False),
                    ("!chatbot_setup_channel", "Sends the persistent 'Start Chat' chatbot embed/button to the configured channel.", False),
                    ("!carrothelp", "Show a help menu.", False)
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
