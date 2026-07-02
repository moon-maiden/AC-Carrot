import discord
import os
import re
from datetime import datetime
import database
from .helpers import sanitize_input

class PaidRequestModal(discord.ui.Modal):
    def __init__(self, request_id: int = None, budget_val: str = None, sfw_nsfw_val: str = None,
                 payment_method_val: str = None, use_case_val: str = None, content_val: str = None,
                 review_msg_id: int = None, dm_msg: discord.Message = None, budget_error: str = None,
                 guild_id: int = None):
        title = "Edit Request" if request_id else "Create Request"
        super().__init__(title=title)
        
        self.request_id = request_id
        self.review_msg_id = review_msg_id
        self.dm_msg = dm_msg
        self.guild_id = guild_id
        
        budget_label = "Budget (AUD/USD/CAD/etc.)"
        if budget_error:
            budget_label = f"Budget ({budget_error})"
            
        self.budget = discord.ui.TextInput(
            label=budget_label,
            placeholder="Crypto/Robux is NOT ALLOWED",
            default=budget_val,
            required=True,
            max_length=100
        )
        self.sfw_nsfw = discord.ui.TextInput(
            label="SFW/NSFW",
            placeholder="Must include SFW or NSFW",
            default=sfw_nsfw_val,
            required=True,
            max_length=50
        )
        self.payment_method = discord.ui.TextInput(
            label="Payment Method",
            placeholder="Crypto/Robux is NOT ALLOWED",
            default=payment_method_val,
            required=True,
            max_length=100
        )
        self.use_case = discord.ui.TextInput(
            label="Personal/Commercial Use",
            placeholder="Must include Personal or Commercial",
            default=use_case_val,
            required=True,
            max_length=50
        )
        self.content = discord.ui.TextInput(
            label="Content",
            style=discord.TextStyle.long,
            placeholder="Your request will be rejected if it is too explicit/NSFW or unclear/vague",
            default=content_val,
            required=True,
            max_length=1000
        )
        
        self.add_item(self.budget)
        self.add_item(self.sfw_nsfw)
        self.add_item(self.payment_method)
        self.add_item(self.use_case)
        self.add_item(self.content)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        is_edit = self.request_id is not None
        guild_id = self.guild_id or interaction.guild_id
        if is_edit and not guild_id:
            req = await database.get_paid_request(self.request_id)
            if req and req.get('guild_id'):
                guild_id = req['guild_id']
                
        config = await database.get_guild_config(guild_id or 0)
        
        budget_val = sanitize_input(self.budget.value, 100)
        sfw_nsfw_val = sanitize_input(self.sfw_nsfw.value, 50)
        payment_method_val = sanitize_input(self.payment_method.value, 100)
        use_case_val = sanitize_input(self.use_case.value, 50)
        content_val = sanitize_input(self.content.value, 1000)
        
        banned_regex_str = config.get("banned_terms_regex") or r'\b(robux|crypto)\b'
        disallowed_pattern = re.compile(banned_regex_str, re.IGNORECASE)
        
        budget_upper = budget_val.upper()
        
        # 1. Check for disallowed currency
        has_disallowed_budget = disallowed_pattern.search(budget_val)
        has_disallowed_payment = disallowed_pattern.search(payment_method_val)
        
        if has_disallowed_budget or has_disallowed_payment:
            view = discord.ui.View(timeout=180)
            fix_btn = discord.ui.Button(label="Fix Form", style=discord.ButtonStyle.primary)
            
            error_label = "NO ROBUX/CRYPTO ALLOWED" if has_disallowed_budget else None
            
            async def fix_callback(btn_interaction: discord.Interaction):
                await btn_interaction.response.send_modal(PaidRequestModal(
                    request_id=self.request_id,
                    budget_val=self.budget.value,
                    sfw_nsfw_val=self.sfw_nsfw.value,
                    payment_method_val=self.payment_method.value,
                    use_case_val=self.use_case.value,
                    content_val=self.content.value,
                    review_msg_id=self.review_msg_id,
                    dm_msg=self.dm_msg,
                    budget_error=error_label,
                    guild_id=guild_id
                ))
            
            fix_btn.callback = fix_callback
            view.add_item(fix_btn)
            
            await interaction.followup.send(
                "⚠️ **Disallowed Currency / Payment Method**\nRobux, Robucks, crypto, or other equivalent currencies are not allowed in either the Budget or Payment Method fields.\n\nClick the button below to correct your input without losing what you typed.",
                view=view,
                ephemeral=True
            )
            return

        # Check SFW/NSFW and Use Case field validation
        sfw_nsfw_upper = sfw_nsfw_val.upper()
        has_sfw = "SFW" in sfw_nsfw_upper
        has_nsfw = "NSFW" in sfw_nsfw_upper
        has_sfw_nsfw = has_sfw or has_nsfw # Satisfies SFW, NSFW, SFW/NSFW, NSFW/SFW
        
        use_case_upper = use_case_val.upper()
        has_use_case = "COMMERCIAL" in use_case_upper or "PERSONAL" in use_case_upper
        
        if not has_sfw_nsfw or not has_use_case:
            view = discord.ui.View(timeout=180)
            fix_btn = discord.ui.Button(label="Fix Form", style=discord.ButtonStyle.primary)
            
            async def fix_callback(btn_interaction: discord.Interaction):
                await btn_interaction.response.send_modal(PaidRequestModal(
                    request_id=self.request_id,
                    budget_val=self.budget.value,
                    sfw_nsfw_val=self.sfw_nsfw.value,
                    payment_method_val=self.payment_method.value,
                    use_case_val=self.use_case.value,
                    content_val=self.content.value,
                    review_msg_id=self.review_msg_id,
                    dm_msg=self.dm_msg,
                    guild_id=guild_id
                ))
            
            fix_btn.callback = fix_callback
            view.add_item(fix_btn)
            
            errors = []
            if not has_sfw_nsfw:
                errors.append("• **SFW/NSFW** field must contain **SFW** or **NSFW**.")
            if not has_use_case:
                errors.append("• **Personal/Commercial Use** field must contain **Personal** or **Commercial**.")
                
            err_msg = "⚠️ **Form Validation Errors:**\n" + "\n".join(errors) + "\n\nClick the button below to correct your input without losing what you typed."
            await interaction.followup.send(
                err_msg,
                view=view,
                ephemeral=True
            )
            return
            
        # 2. Check if detects a number/digit
        has_digit = any(c.isdigit() for c in budget_val)
        
        if has_digit:
            accepted_curr = config.get("accepted_currencies") or "USD"
            # allow checking symbols or codes
            is_valid_currency = any(code.strip().upper() in budget_upper for code in accepted_curr.split(","))
            if not is_valid_currency:
                # also check for common symbols dynamically via the accepted string if we want, or just enforce strict
                is_valid_currency = any(symbol in budget_val for symbol in ["$", "£", "€", "¥", "₱", "Rp"])
            
            if not is_valid_currency:
                if "$" in budget_val:
                    error_label = "SPECIFY USD/AUD/CAD/etc."
                    error_msg = "⚠️ **Specify Dollar Currency**\nYou used the '$' symbol with a number, but did not specify which dollar currency it is (e.g. **USD, AUD, CAD, NZD**).\n\nClick the button below to specify the currency."
                else:
                    error_label = "SPECIFY CURRENCY (USD/AUD/etc)"
                    error_msg = "⚠️ **Specify Currency**\nYou only wrote a number. Please specify which currency it is (e.g. **USD, AUD, CAD, NZD, EUR, GBP, JPY**).\n\nClick the button below to specify the currency."

                view = discord.ui.View(timeout=180)
                fix_btn = discord.ui.Button(label="Specify Currency", style=discord.ButtonStyle.primary)
                
                async def fix_callback(btn_interaction: discord.Interaction):
                    await btn_interaction.response.send_modal(PaidRequestModal(
                        request_id=self.request_id,
                        budget_val=self.budget.value,
                        sfw_nsfw_val=self.sfw_nsfw.value,
                        payment_method_val=self.payment_method.value,
                        use_case_val=self.use_case.value,
                        content_val=self.content.value,
                        review_msg_id=self.review_msg_id,
                        dm_msg=self.dm_msg,
                        budget_error=error_label,
                        guild_id=guild_id
                    ))
                
                fix_btn.callback = fix_callback
                view.add_item(fix_btn)
                
                await interaction.followup.send(
                    error_msg,
                    view=view,
                    ephemeral=True
                )
                return
            
        if is_edit:
            req_id = self.request_id
            await database.update_paid_request_details(
                req_id,
                budget_val,
                sfw_nsfw_val,
                payment_method_val,
                use_case_val,
                content_val
            )
        else:
            count = await database.get_active_paid_requests_count(interaction.user.id)
            active_limit = config.get("active_limit") or 2
            if count >= active_limit:
                await interaction.followup.send(
                    f"You cannot have more than {active_limit} active paid requests (pending or approved) at the same time. Please close or fulfill an existing request first.",
                    ephemeral=True
                )
                return
            req_id = await database.create_paid_request(
                guild_id,
                interaction.user.id,
                budget_val,
                sfw_nsfw_val,
                payment_method_val,
                use_case_val,
                content_val
            )

        # Fetch member from the review channel guild to support DMs
        review_channel_id = config.get("review_channel_id") or 0
        review_channel = interaction.client.get_channel(review_channel_id)
        guild = review_channel.guild if review_channel else None
        
        member = None
        if guild:
            member = guild.get_member(interaction.user.id)
            if not member:
                try:
                    member = await guild.fetch_member(interaction.user.id)
                except discord.HTTPException:
                    member = None
                    
        joined_str = "Unknown"
        display_name = interaction.user.display_name
        avatar_url = interaction.user.display_avatar.url if interaction.user.display_avatar else None
        
        if member:
            display_name = member.display_name
            if member.display_avatar:
                avatar_url = member.display_avatar.url
            if member.joined_at:
                joined_str = f"<t:{int(member.joined_at.timestamp())}:f> ( <t:{int(member.joined_at.timestamp())}:R> )"

        embed = discord.Embed(
            title=f"Request By {display_name}",
            description=self.content.value,
            color=discord.Color.blue()
        )
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
            
        embed.add_field(name="Budget", value=self.budget.value, inline=False)
        embed.add_field(name="Type", value=self.sfw_nsfw.value, inline=False)
        embed.add_field(name="Payment", value=self.payment_method.value, inline=False)
        embed.add_field(name="Use", value=self.use_case.value, inline=False)
        embed.add_field(name="Member", value=f"{interaction.user.mention} | {interaction.user.name}\n[{interaction.user.id}]", inline=False)
        embed.add_field(name="Joined", value=joined_str, inline=False)
        embed.add_field(name="ID", value=str(req_id), inline=False)

        # Create DM view (Edit and Cancel)
        dm_view = discord.ui.View(timeout=None)
        edit_btn = discord.ui.Button(label="Edit", style=discord.ButtonStyle.secondary, custom_id=f"dmedit_{req_id}")
        cancel_btn = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger, custom_id=f"dmcancel_{req_id}")
        dm_view.add_item(edit_btn)
        dm_view.add_item(cancel_btn)

        # Send/Edit DM
        if is_edit and self.dm_msg:
            try:
                await self.dm_msg.edit(embed=embed, view=dm_view)
            except discord.HTTPException:
                pass
        else:
            try:
                await interaction.user.send("Your paid request has been submitted for review! Here is a copy:", embed=embed, view=dm_view)
            except discord.Forbidden:
                pass

        # Send to Review Channel
        if review_channel:
            view = discord.ui.View(timeout=None)
            approve_btn = discord.ui.Button(label="Approve", style=discord.ButtonStyle.success, custom_id=f"approve_{req_id}")
            reject_btn = discord.ui.Button(label="Reject", style=discord.ButtonStyle.danger, custom_id=f"reject_{req_id}")
            view.add_item(approve_btn)
            view.add_item(reject_btn)
            
            if is_edit:
                if self.review_msg_id:
                    try:
                        msg = review_channel.get_partial_message(self.review_msg_id)
                        await msg.edit(embed=embed, view=view)
                    except discord.HTTPException:
                        msg = await review_channel.send(embed=embed, view=view)
                        await database.update_paid_request_review_msg(req_id, msg.id)
            else:
                msg = await review_channel.send(embed=embed, view=view)
                await database.update_paid_request_review_msg(req_id, msg.id)

        msg_text = "Your request has been updated successfully!" if is_edit else "Request submitted successfully!"
        await interaction.followup.send(msg_text, ephemeral=True)

class RejectReasonModal(discord.ui.Modal, title="Reason for Rejection"):
    def __init__(self, request_id: int, user_id: int, review_msg: discord.Message):
        super().__init__()
        self.request_id = request_id
        self.user_id = user_id
        self.review_msg = review_msg

    reason = discord.ui.TextInput(
        label="Reason",
        style=discord.TextStyle.long,
        placeholder="Please provide a reason for rejecting this request...",
        required=True,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await database.update_paid_request_status(self.request_id, 'rejected', actioned_by=interaction.user.id)
        
        req = await database.get_paid_request(self.request_id)
        reason_val = sanitize_input(self.reason.value, 500)
        
        # Fetch submitter
        submitter = interaction.client.get_user(self.user_id)
        if not submitter:
            try:
                submitter = await interaction.client.fetch_user(self.user_id)
            except discord.HTTPException:
                submitter = None
        submitter_str = f"{submitter.name} [{self.user_id}]" if submitter else f"Unknown [{self.user_id}]"

        # Log it
        guild_id = (req['guild_id'] if req else None) or interaction.guild_id
        config = await database.get_guild_config(guild_id or 0)
        log_channel_id = config.get("approval_log_channel_id") or 0
        log_channel = interaction.client.get_channel(log_channel_id)
        if log_channel and req:
            log_desc = (
                f"```\n"
                f"ID: {self.request_id}\n"
                f"Budget: {req['budget']}\n"
                f"Type: {req['sfw_nsfw']}\n"
                f"Payment: {req['payment_method']}\n"
                f"Use: {req['use_case']}\n"
                f"Content: {req['content']}\n"
                f"```"
            )
            log_embed = discord.Embed(
                title="Log: Request Rejected",
                description=log_desc,
                color=discord.Color.red()
            )
            log_embed.add_field(name="Request From", value=submitter_str, inline=False)
            log_embed.add_field(name="Rejected By", value=f"{interaction.user.name} [{interaction.user.id}]", inline=False)
            log_embed.add_field(name="Reason", value=reason_val, inline=False)
            
            now_str = datetime.now().strftime('%d %B %Y %H:%M')
            log_embed.add_field(name="Timestamp", value=f"`{now_str}`", inline=False)
            log_embed.add_field(name="ID", value=str(self.request_id), inline=False)
            
            await log_channel.send(embed=log_embed)

        await interaction.followup.send("Request rejected and user notified.", ephemeral=True)
        await self.review_msg.delete()

        user = interaction.client.get_user(self.user_id)
        if not user:
            try:
                user = await interaction.client.fetch_user(self.user_id)
            except discord.HTTPException:
                user = None
                
        if user and req:
            guild = interaction.guild
            member = guild.get_member(self.user_id) if guild else None
            if not member and guild:
                try:
                    member = await guild.fetch_member(self.user_id)
                except discord.HTTPException:
                    member = None
            
            joined_str = "Unknown"
            display_name = f"User ID {self.user_id}"
            avatar_url = None
            username = "Unknown"
            
            if member:
                display_name = member.display_name
                username = member.name
                if member.display_avatar:
                    avatar_url = member.display_avatar.url
                if member.joined_at:
                    joined_str = f"<t:{int(member.joined_at.timestamp())}:f> ( <t:{int(member.joined_at.timestamp())}:R> )"
            elif submitter:
                display_name = submitter.display_name
                username = submitter.name
                if submitter.display_avatar:
                    avatar_url = submitter.display_avatar.url

            embed1 = discord.Embed(
                title=f"Request By {display_name}",
                description=req['content'],
                color=discord.Color.red()
            )
            if avatar_url:
                embed1.set_thumbnail(url=avatar_url)
                
            embed1.add_field(name="Budget", value=req['budget'], inline=False)
            embed1.add_field(name="Type", value=req['sfw_nsfw'], inline=False)
            embed1.add_field(name="Payment", value=req['payment_method'], inline=False)
            embed1.add_field(name="Use", value=req['use_case'], inline=False)
            embed1.add_field(name="Member", value=f"<@{self.user_id}> | {username} [{self.user_id}]", inline=False)
            embed1.add_field(name="Joined", value=joined_str, inline=False)
            embed1.add_field(name="ID", value=str(self.request_id), inline=False)
            
            embed2 = discord.Embed(
                description=f"One of your requests has been rejected for the following reason: **{reason_val}**",
                color=discord.Color.blue()
            )
            
            view = discord.ui.View(timeout=None)
            resubmit_btn = discord.ui.Button(label="Resubmit / Edit", style=discord.ButtonStyle.primary, custom_id=f"dmresubmit_{self.request_id}")
            view.add_item(resubmit_btn)
            
            try:
                await user.send(embed=embed1)
                await user.send(embed=embed2, view=view)
            except discord.Forbidden:
                pass
