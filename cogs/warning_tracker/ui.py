import discord
import database
from datetime import datetime, timezone
from .helpers import sanitize_reason, get_channel_mention

def is_higher_up(member: discord.Member, config: dict) -> bool:
    if member.id == 255174440005009408:
        return True
    if member.guild_permissions.administrator:
        return True
    tl_id = config.get("team_leader_role_id") or 0
    mod_id = config.get("moderator_role_id") or 0
    user_role_ids = {r.id for r in member.roles} if hasattr(member, 'roles') else set()
    if (tl_id and tl_id in user_role_ids) or (mod_id and mod_id in user_role_ids):
        return True
    return False

class ConfirmRemovalView(discord.ui.View):
    def __init__(self, target_message: discord.Message, reason: str, cog, staff_interaction: discord.Interaction, on_training_wheels: bool = False):
        super().__init__(timeout=180)
        self.target_message = target_message
        self.reason = reason
        self.cog = cog
        self.staff_interaction = staff_interaction
        self.on_training_wheels = on_training_wheels
        self.message = None
        if on_training_wheels:
            self.confirm_btn.label = "Submit for Review"
            self.confirm_btn.style = discord.ButtonStyle.primary
        else:
            self.confirm_btn.label = "Confirm Removal"
            self.confirm_btn.style = discord.ButtonStyle.danger

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    @discord.ui.button(label="Confirm Removal", style=discord.ButtonStyle.danger)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
            
        guild_id = interaction.guild_id or (self.target_message.guild.id if self.target_message.guild else 0)
        config = await database.get_guild_config(guild_id)
        user_role_ids = [r.id for r in interaction.user.roles] if hasattr(interaction.user, 'roles') else []
        target_channel_id = getattr(self.target_message.channel, "parent_id", None) or self.target_message.channel.id
        on_wheels = await database.is_user_on_training_wheels(guild_id, interaction.user.id, user_role_ids, config, channel_id=target_channel_id)

        if on_wheels:
            await interaction.response.edit_message(content="Submitting post for deletion review...", embed=None, view=self)
            await self.cog.queue_removal(interaction, self.target_message, self.reason, self.target_message.content)
        else:
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
        user_role_ids = [r.id for r in interaction.user.roles] if hasattr(interaction.user, 'roles') else []
        on_wheels = await database.is_user_on_training_wheels(interaction.guild_id or 0, interaction.user.id, user_role_ids, config)
        if interaction.user.id != 255174440005009408 and not is_admin and not on_wheels and not any(role.id in staff_role_ids for role in interaction.user.roles):
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

            guild_id = interaction.guild_id or (self.target_message.guild.id if self.target_message.guild else 0)
            user_role_ids = [r.id for r in interaction.user.roles] if hasattr(interaction.user, 'roles') else []
            target_channel_id = getattr(self.target_message.channel, "parent_id", None) or self.target_message.channel.id
            on_wheels = await database.is_user_on_training_wheels(guild_id, interaction.user.id, user_role_ids, config, channel_id=target_channel_id)

            if on_wheels:
                preview_title = "[Training Wheel] Queue Post for Deletion"
                preview_desc = (
                    f"You are on Training Wheels. This removal will be sent to the review channel for moderator approval before deletion.\n\n"
                    f"**Preview of notice message to be sent upon approval:**\n"
                    f"{self.target_message.author.mention} {reason}"
                )
            else:
                preview_title = "Confirm Post Removal"
                preview_desc = (
                    f"Are you sure you want to remove the post by {self.target_message.author.mention}?\n\n"
                    f"**Preview of notice message to be sent:**\n"
                    f"{self.target_message.author.mention} {reason}"
                )
            confirm_embed = discord.Embed(
                title=preview_title,
                description=preview_desc,
                color=discord.Color.yellow()
            )
            confirm_view = ConfirmRemovalView(self.target_message, reason, self.cog, interaction, on_training_wheels=on_wheels)
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
            reason = f"Your post has been removed from {chan_mention} due to {custom_reason_sanitized}"

        guild_id = interaction.guild_id or (self.target_message.guild.id if self.target_message.guild else 0)
        config = await database.get_guild_config(guild_id)
        user_role_ids = [r.id for r in interaction.user.roles] if hasattr(interaction.user, 'roles') else []
        target_channel_id = getattr(self.target_message.channel, "parent_id", None) or self.target_message.channel.id
        on_wheels = await database.is_user_on_training_wheels(guild_id, interaction.user.id, user_role_ids, config, channel_id=target_channel_id)

        if on_wheels:
            preview_title = "[Training Wheel] Queue Post for Deletion"
            preview_desc = (
                f"You are on Training Wheels. This removal will be sent to the review channel for moderator approval before deletion.\n\n"
                f"**Preview of notice message to be sent upon approval:**\n"
                f"{self.target_message.author.mention} {reason}"
            )
        else:
            preview_title = "Confirm Post Removal"
            preview_desc = (
                f"Are you sure you want to remove the post by {self.target_message.author.mention}?\n\n"
                f"**Preview of notice message to be sent:**\n"
                f"{self.target_message.author.mention} {reason}"
            )
        confirm_embed = discord.Embed(
            title=preview_title,
            description=preview_desc,
            color=discord.Color.yellow()
        )
        confirm_view = ConfirmRemovalView(self.target_message, reason, self.cog, interaction, on_training_wheels=on_wheels)
        await interaction.response.send_message(embed=confirm_embed, view=confirm_view, ephemeral=True)
        try:
            confirm_view.message = await interaction.original_response()
        except Exception:
            pass

class PendingDeletionReviewView(discord.ui.View):
    def __init__(self, pending_id: int, cog=None):
        super().__init__(timeout=None)
        self.pending_id = pending_id
        self.cog = cog
        
        self.approve_btn.custom_id = f"pending_del_approve:{pending_id}"
        self.edit_btn.custom_id = f"pending_del_edit:{pending_id}"
        self.reject_btn.custom_id = f"pending_del_reject:{pending_id}"

    # Actions are handled centrally in WarningTracker.on_interaction to prevent race conditions
    @discord.ui.button(label="Approve Deletion", style=discord.ButtonStyle.success)
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Edit Reason", style=discord.ButtonStyle.primary)
    async def edit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.secondary)
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

class RejectDeletionModal(discord.ui.Modal, title="Reject Post Deletion"):
    def __init__(self, pending_id: int, cog):
        super().__init__()
        self.pending_id = pending_id
        self.cog = cog

    reason_input = discord.ui.TextInput(
        label="Reason for Rejection",
        placeholder="Why is this post deletion being rejected?",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        reject_reason = self.reason_input.value.strip() if self.reason_input.value else "No reason provided."
        if self.cog:
            await self.cog.reject_pending_deletion(interaction, self.pending_id, reject_reason=reject_reason)

class EditPendingReasonSelect(discord.ui.Select):
    def __init__(self, pending_id: int, cog, reasons_db: list, current_channel_mention: str):
        self.pending_id = pending_id
        self.cog = cog
        self.reasons_db = reasons_db
        self.current_channel_mention = current_channel_mention
        options = [discord.SelectOption(label=r['label'][:100], value=r['id'][:100]) for r in reasons_db]
        options.append(discord.SelectOption(label="Others...", value="others"))
        super().__init__(placeholder="Choose a new removal reason...", options=options[:25], min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        reasons_map = {r['id']: r['text'] for r in self.reasons_db}
        if self.values[0] == "others":
            modal = EditPendingCustomReasonModal(self.pending_id, self.cog, self.current_channel_mention)
            await interaction.response.send_modal(modal)
        else:
            selected_text = reasons_map[self.values[0]]
            if selected_text.startswith("as "):
                new_reason = f"Your post has been removed from {self.current_channel_mention} {selected_text}"
            else:
                new_reason = f"Your post has been removed from {self.current_channel_mention} due to {selected_text}"
            await self.cog.apply_edited_reason(interaction, self.pending_id, new_reason)

class EditPendingReasonView(discord.ui.View):
    def __init__(self, select_item):
        super().__init__(timeout=120)
        self.add_item(select_item)

class EditPendingCustomReasonModal(discord.ui.Modal, title="Edit Removal Reason"):
    def __init__(self, pending_id: int, cog, channel_mention: str):
        super().__init__()
        self.pending_id = pending_id
        self.cog = cog
        self.channel_mention = channel_mention

    custom_reason = discord.ui.TextInput(
        label="New Reason",
        placeholder="Enter the updated reason for removal...",
        style=discord.TextStyle.long,
        required=True,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        sanitized = sanitize_reason(self.custom_reason.value)
        new_reason = f"Your post has been removed from {self.channel_mention} due to {sanitized}"
        await self.cog.apply_edited_reason(interaction, self.pending_id, new_reason)

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
        g_id = self.guild_id if isinstance(self.guild_id, int) else None
        page_warnings = await self.get_page_callback(self.user.id, self.page_size, offset, g_id)
        
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
        g_id = self.guild_id if isinstance(self.guild_id, int) else None
        page_warnings = await self.get_page_callback(self.staff_user.id, self.page_size, offset, g_id)
        
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
                "title": "🥕 Prefix Commands (!)",
                "color": discord.Color.orange(),
                "fields": [
                    ("!verbals <userid>", "Retrieve a list of verbal warnings for the specified user ID.", False),
                    ("!delverbal <id>", "Deletes a verbal warning using its unique Verbal ID.", False),
                    ("!editverbal <id> <new_reason>", "Edits the reason of a verbal warning using its unique Verbal ID.", False),
                    ("!verbalby <userid>", "List all warnings issued by the specified staff member ID.", False),
                    ("!sync_warnings", "Syncs the last 3 months of warnings in #staff-notice into the database.", False),
                    ("!givevac @member [reason]", "Puts a staff member on vacation (removes staff roles).", False),
                    ("!removevac @member", "Restores staff roles and returns a user from vacation.", False),
                    ("!setup_paid_requests", "Sends the persistent 'Create Request' panel to the configured channel.", False),
                    ("!chatbot_setup_channel", "Sends the persistent 'Start Chat' card to the configured channel.", False),
                    ("!carrothelp", "Show this help menu.", False)
                ]
            },
            {
                "title": "🥕 Slash Commands (/)",
                "color": discord.Color.blurple(),
                "fields": [
                    ("/trainingwheel <add|remove|list>", "Manage Training Wheels for post deletions (Mods+).", False),
                    ("/verbal <action> [reason]", "Manage dynamic verbal warning reasons (Admins/TLs only).", False),
                    ("/addvac <target> [reason]", "Puts a staff member on vacation (Admins/TLs only).", False),
                    ("/removevac <target>", "Restores staff roles and returns a user from vacation (Admins/TLs only).", False),
                    ("/send_as <message>", "Sends a raw message directly as Carrot Bot.", False),
                    ("/message_builder", "Opens the web link to the interactive message builder panel.", False),
                    ("/purge <target>", "Purge specific database tables (Developer Only).", False)
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

class EditVerbalReasonSelect(discord.ui.Select):
    def __init__(self, warning_id: int, cog, reasons_db: list, guild_id: int):
        self.warning_id = warning_id
        self.cog = cog
        self.reasons_db = reasons_db
        self.guild_id = guild_id
        options = [discord.SelectOption(label=r['label'][:100], value=r['id'][:100]) for r in reasons_db]
        options.append(discord.SelectOption(label="Others...", value="others"))
        super().__init__(placeholder="Select new reason(s) for verbal...", options=options[:25], min_values=1, max_values=len(options[:25]))

    async def callback(self, interaction: discord.Interaction):
        is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False
        if interaction.user.id != 255174440005009408 and not is_admin:
            await interaction.response.send_message("You do not have the required administrator permissions to perform this action.", ephemeral=True)
            return

        reasons_map = {r['id']: r['text'] for r in self.reasons_db}

        if "others" in self.values:
            predefined = [reasons_map[v] for v in self.values if v != "others" and v in reasons_map]
            modal = CustomEditVerbalReasonModal(self.warning_id, self.cog, self.guild_id, predefined_reasons=predefined)
            await interaction.response.send_modal(modal)
        else:
            warn = await database.get_warning_by_id(self.warning_id)
            if not warn:
                await interaction.response.send_message("Warning not found in database.", ephemeral=True)
                return
                
            guild = interaction.guild
            original_channel = guild.get_channel(warn['channel_id']) if guild else None
            chan_mention = get_channel_mention(original_channel)
            
            if len(self.values) == 1:
                selected_reason = reasons_map[self.values[0]]
                if selected_reason.startswith("as "):
                    reason = f"Your post has been removed from {chan_mention} {selected_reason}"
                else:
                    reason = f"Your post has been removed from {chan_mention} due to {selected_reason}"
            else:
                formatted_list = "\n".join([f"- {reasons_map[v]}" for v in self.values if v in reasons_map])
                reason = f"Your post has been removed from {chan_mention} due to:\n{formatted_list}"

            await interaction.response.edit_message(content="Updating verbal warning...", view=None)
            await self.cog.execute_verbal_edit(interaction, self.warning_id, reason)

class CustomEditVerbalReasonModal(discord.ui.Modal, title="New reason for verbal"):
    def __init__(self, warning_id: int, cog, guild_id: int, predefined_reasons: list = None):
        super().__init__()
        self.warning_id = warning_id
        self.cog = cog
        self.guild_id = guild_id
        self.predefined_reasons = predefined_reasons or []

    reason_input = discord.ui.TextInput(
        label="Reason",
        placeholder="Enter the new reason for post removal...",
        style=discord.TextStyle.long,
        required=True,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False
        if interaction.user.id != 255174440005009408 and not is_admin:
            await interaction.response.send_message("You do not have the required administrator permissions to perform this action.", ephemeral=True)
            return

        custom_reason = self.reason_input.value
        custom_reason_sanitized = sanitize_reason(custom_reason)

        warn = await database.get_warning_by_id(self.warning_id)
        if not warn:
            await interaction.response.send_message("Warning not found in database.", ephemeral=True)
            return

        guild = interaction.guild
        original_channel = guild.get_channel(warn['channel_id']) if guild else None
        chan_mention = get_channel_mention(original_channel)

        if self.predefined_reasons:
            formatted_list = "\n".join([f"- {r}" for r in self.predefined_reasons] + [f"- {custom_reason_sanitized}"])
            reason = f"Your post has been removed from {chan_mention} due to:\n{formatted_list}"
        else:
            reason = f"Your post has been removed from {chan_mention} due to {custom_reason_sanitized}"

        await interaction.response.edit_message(content="Updating verbal warning...", view=None)
        await self.cog.execute_verbal_edit(interaction, self.warning_id, reason)
