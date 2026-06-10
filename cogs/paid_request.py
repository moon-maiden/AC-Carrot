import discord
from discord.ext import commands
import os
import database
from datetime import datetime

def sanitize_input(text: str, max_len: int = 1000) -> str:
    if not text:
        return ""
    text = text.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text

class PaidRequestModal(discord.ui.Modal):
    def __init__(self, request_id: int = None, budget_val: str = None, sfw_nsfw_val: str = None,
                 payment_method_val: str = None, use_case_val: str = None, content_val: str = None,
                 review_msg_id: int = None, dm_msg: discord.Message = None):
        title = "Edit Request" if request_id else "Create Request"
        super().__init__(title=title)
        
        self.request_id = request_id
        self.review_msg_id = review_msg_id
        self.dm_msg = dm_msg
        
        self.budget = discord.ui.TextInput(
            label="Budget (AUD/USD/CAD/etc.)",
            placeholder="Crypto/Robux is NOT ALLOWED",
            default=budget_val,
            required=True,
            max_length=100
        )
        self.sfw_nsfw = discord.ui.TextInput(
            label="SFW/NSFW",
            placeholder="Choose one only",
            default=sfw_nsfw_val,
            required=True,
            max_length=50
        )
        self.payment_method = discord.ui.TextInput(
            label="Payment Method",
            placeholder="Cryto/Robux/Royalty is NOT ALLOWED",
            default=payment_method_val,
            required=True,
            max_length=100
        )
        self.use_case = discord.ui.TextInput(
            label="Personal/Commercial Use",
            placeholder="Choose one only",
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
        budget_val = sanitize_input(self.budget.value, 100)
        sfw_nsfw_val = sanitize_input(self.sfw_nsfw.value, 50)
        payment_method_val = sanitize_input(self.payment_method.value, 100)
        use_case_val = sanitize_input(self.use_case.value, 50)
        content_val = sanitize_input(self.content.value, 1000)
        
        # Validate budget currency
        import re
        disallowed_pattern = re.compile(
            r'\b(robux|robuck|robucks|crypto|cryptocurrency|cryptocurrencies|btc|eth|sol|ltc|usdt|usdc|bitcoin|ethereum|solana|litecoin|doge|dogecoin)\b',
            re.IGNORECASE
        )
        
        budget_upper = budget_val.upper()
        
        # 1. Check for disallowed currency
        if disallowed_pattern.search(budget_val):
            view = discord.ui.View(timeout=180)
            fix_btn = discord.ui.Button(label="Fix Currency", style=discord.ButtonStyle.primary)
            
            async def fix_callback(btn_interaction: discord.Interaction):
                await btn_interaction.response.send_modal(PaidRequestModal(
                    request_id=self.request_id,
                    budget_val=self.budget.value,
                    sfw_nsfw_val=self.sfw_nsfw.value,
                    payment_method_val=self.payment_method.value,
                    use_case_val=self.use_case.value,
                    content_val=self.content.value,
                    review_msg_id=self.review_msg_id,
                    dm_msg=self.dm_msg
                ))
            
            fix_btn.callback = fix_callback
            view.add_item(fix_btn)
            
            await interaction.followup.send(
                "⚠️ **Disallowed Currency**\nRobux, Robucks, crypto, or other equivalent currencies are not allowed.\n\nClick the button below to correct your input without losing what you typed.",
                view=view,
                ephemeral=True
            )
            return
            
        # 2. Check if detects $ and a number/digit
        has_dollar = "$" in budget_val
        has_digit = any(c.isdigit() for c in budget_val)
        
        if has_dollar and has_digit:
            currencies = {"USD", "AUD", "CAD", "NZD", "EUR", "GBP", "SGD", "MYR", "PHP", "IDR", "JPY", "HKD", "TWD", "KRW", "INR"}
            if not any(code in budget_upper for code in currencies):
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
                        dm_msg=self.dm_msg
                    ))
                
                fix_btn.callback = fix_callback
                view.add_item(fix_btn)
                
                await interaction.followup.send(
                    "⚠️ **Specify Dollar Currency**\nYou used the '$' symbol with a number, but did not specify which dollar currency it is (e.g. **USD, AUD, CAD, NZD**).\n\nClick the button below to specify the currency.",
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
            req_id = await database.create_paid_request(
                interaction.user.id,
                budget_val,
                sfw_nsfw_val,
                payment_method_val,
                use_case_val,
                content_val
            )

        # Fetch member from the review channel guild to support DMs
        review_channel_id = int(os.getenv("PAID_REQUEST_REVIEW_CHANNEL_ID") or 0)
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
        review_channel_id = int(os.getenv("PAID_REQUEST_REVIEW_CHANNEL_ID") or 0)
        review_channel = interaction.client.get_channel(review_channel_id)
        if review_channel:
            view = discord.ui.View(timeout=None)
            approve_btn = discord.ui.Button(label="Approve", style=discord.ButtonStyle.success, custom_id=f"approve_{req_id}")
            reject_btn = discord.ui.Button(label="Reject", style=discord.ButtonStyle.danger, custom_id=f"reject_{req_id}")
            view.add_item(approve_btn)
            view.add_item(reject_btn)
            
            if is_edit:
                if self.review_msg_id:
                    try:
                        msg = await review_channel.fetch_message(self.review_msg_id)
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
        await database.update_paid_request_status(self.request_id, 'rejected')
        
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
        log_channel_id = int(os.getenv("APPROVAL_LOG_CHANNEL_ID") or 0)
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

        # Send confirmation first before deleting the card (deleting the card invalidates the interaction token)
        await interaction.followup.send("Request rejected and user notified.", ephemeral=True)

        # Delete review card
        await self.review_msg.delete()

        # DM user
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
            
            try:
                await user.send(embed=embed1)
                await user.send(embed=embed2)
            except discord.Forbidden:
                pass


class PaidRequest(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    @commands.Cog.listener()
    async def on_ready(self):
        # Register the persistent create button view
        view = discord.ui.View(timeout=None)
        btn = discord.ui.Button(label="Create", style=discord.ButtonStyle.primary, custom_id="create_paid_request_btn")
        view.add_item(btn)
        self.bot.add_view(view)

    @commands.command()
    async def setup_paid_requests(self, ctx):
        if ctx.author.id != 255174440005009408:
            if not ctx.guild or not ctx.author.guild_permissions.administrator:
                await ctx.send("You do not have the required administrator permissions to use this command.")
                return
        embed = discord.Embed(
            title="Submit a Paid Request",
            description="NOTE: PLEASE read <#492328409175687179> before you submit your request.\n\nOnce you click on Create button, you will be presented with forms to fill in.\nREMEMBER that you can only link images in Content field. After you finished adding information and hit submit button, your message will be in pending review for staff to verify.\n\n- You will be notified by our bot <@1506161699441610794> via DIRECT MESSAGE whether your commission request got approved or rejected. Note that your message will appear on a channel that only artists can view.\n- You will receive a DM from our bot that contains a copy of your paid request message with 2 buttons, Close and Fulfilled. Close will delete your pre-approved request, while Fulfilled will cross your request messages in the channel that artists can access.\nRemember to click close or fulfilled buttons as buyers can only submit a maximum of 2 requests simultaneously.",
            color=discord.Color.blurple()
        )
        view = discord.ui.View(timeout=None)
        btn = discord.ui.Button(label="Create", style=discord.ButtonStyle.primary, custom_id="create_paid_request_btn")
        view.add_item(btn)
        
        submit_channel_id = int(os.getenv("SUBMIT_PAID_REQUEST_CHANNEL_ID") or 0)
        submit_channel = self.bot.get_channel(submit_channel_id)
        
        if submit_channel:
            await submit_channel.send(embed=embed, view=view)
            await ctx.send(f"Setup complete! The create button was sent to {submit_channel.mention}", ephemeral=True)
        else:
            await ctx.send("Error: SUBMIT_PAID_REQUEST_CHANNEL_ID is not configured properly in .env.", ephemeral=True)
            
        # Try to delete the trigger message if we can
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "")
        
        if custom_id == "create_paid_request_btn":
            await interaction.response.send_modal(PaidRequestModal())
            return
            
        # Parse dynamic buttons
        if custom_id.startswith("approve_"):
            req_id = int(custom_id.split("_")[1])
            await self.handle_approve(interaction, req_id)
            
        elif custom_id.startswith("reject_"):
            req_id = int(custom_id.split("_")[1])
            req = await database.get_paid_request(req_id)
            if not req:
                await interaction.response.send_message("Request not found.", ephemeral=True)
                return
            await interaction.response.send_modal(RejectReasonModal(req_id, req['user_id'], interaction.message))
            
        elif custom_id.startswith("dmclose_") or custom_id.startswith("dmfulfill_"):
            req_id = int(custom_id.split("_")[1])
            action = "closed" if custom_id.startswith("dmclose_") else "fulfilled"
            await self.handle_dm_action(interaction, req_id, action)
            
        elif custom_id.startswith("dmedit_"):
            req_id = int(custom_id.split("_")[1])
            req = await database.get_paid_request(req_id)
            if not req:
                await interaction.response.send_message("Request not found.", ephemeral=True)
                return
            
            # If the request is not pending, we shouldn't allow editing
            if req['status'] != 'pending':
                await interaction.response.send_message("This request is no longer under review and cannot be edited.", ephemeral=True)
                return
                
            await interaction.response.send_modal(PaidRequestModal(
                request_id=req_id,
                budget_val=req['budget'],
                sfw_nsfw_val=req['sfw_nsfw'],
                payment_method_val=req['payment_method'],
                use_case_val=req['use_case'],
                content_val=req['content'],
                review_msg_id=req['staff_review_msg_id'],
                dm_msg=interaction.message
            ))
            
        elif custom_id.startswith("dmcancel_"):
            req_id = int(custom_id.split("_")[1])
            req = await database.get_paid_request(req_id)
            if not req:
                await interaction.response.send_message("Request not found.", ephemeral=True)
                return
                
            if req['status'] != 'pending':
                await interaction.response.send_message("This request is no longer under review and cannot be cancelled.", ephemeral=True)
                return
                
            await self.handle_cancel(interaction, req_id)

    async def handle_approve(self, interaction: discord.Interaction, req_id: int):
        await interaction.response.defer(ephemeral=True)
        req = await database.get_paid_request(req_id)
        if not req:
            await interaction.followup.send("Request not found.", ephemeral=True)
            return

        approved_channel_id = int(os.getenv("PAID_REQUEST_APPROVED_CHANNEL_ID") or 0)
        approved_channel = self.bot.get_channel(approved_channel_id)
        
        # Get the member from guild to fetch their avatar and join date
        guild = interaction.guild
        member = guild.get_member(req['user_id'])
        if not member:
            try:
                member = await guild.fetch_member(req['user_id'])
            except discord.HTTPException:
                member = None

        joined_str = "Unknown"
        display_name = f"User ID {req['user_id']}"
        avatar_url = None
        
        if member:
            display_name = member.display_name
            if member.display_avatar:
                avatar_url = member.display_avatar.url
            if member.joined_at:
                joined_str = f"<t:{int(member.joined_at.timestamp())}:f> ( <t:{int(member.joined_at.timestamp())}:R> )"

        embed = discord.Embed(
            title=f"Request By {display_name}",
            description=req['content'],
            color=discord.Color.green()
        )
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
            
        embed.add_field(name="Budget", value=req['budget'], inline=False)
        embed.add_field(name="Type", value=req['sfw_nsfw'], inline=False)
        embed.add_field(name="Payment", value=req['payment_method'], inline=False)
        embed.add_field(name="Use", value=req['use_case'], inline=False)
        embed.add_field(name="Member", value=f"<@{req['user_id']}> | {member.name if member else 'Unknown'}\n[{req['user_id']}]", inline=False)
        embed.add_field(name="Joined", value=joined_str, inline=False)
        embed.add_field(name="ID", value=str(req_id), inline=False)

        # Send to approved channel
        approved_msg = None
        if approved_channel:
            approved_msg = await approved_channel.send(content=f"DM the user here <@{req['user_id']}>", embed=embed)
            
        await database.update_paid_request_status(req_id, 'approved', approved_msg.id if approved_msg else None)

        # Log it
        log_channel_id = int(os.getenv("APPROVAL_LOG_CHANNEL_ID") or 0)
        log_channel = self.bot.get_channel(log_channel_id)
        if log_channel:
            submitter_name = member.name if member else "Unknown"
            submitter_str = f"{submitter_name} [{req['user_id']}]"
            
            log_desc = (
                f"```\n"
                f"ID: {req_id}\n"
                f"Budget: {req['budget']}\n"
                f"Type: {req['sfw_nsfw']}\n"
                f"Payment: {req['payment_method']}\n"
                f"Use: {req['use_case']}\n"
                f"Content: {req['content']}\n"
                f"```"
            )
            
            log_embed = discord.Embed(
                title="Log: Request Approved",
                description=log_desc,
                color=discord.Color.green()
            )
            log_embed.add_field(name="Request From", value=submitter_str, inline=False)
            log_embed.add_field(name="Approved By", value=f"{interaction.user.name} [{interaction.user.id}]", inline=False)
            
            now_str = datetime.now().strftime('%d %B %Y %H:%M')
            log_embed.add_field(name="Timestamp", value=f"`{now_str}`", inline=False)
            log_embed.add_field(name="ID", value=str(req_id), inline=False)
            
            await log_channel.send(embed=log_embed)

        # Send confirmation first before deleting the card (deleting the card invalidates the interaction token)
        await interaction.followup.send("Request approved and moved.", ephemeral=True)

        # Delete review card
        await interaction.message.delete()

        # DM User with Close & Fulfilled
        user = self.bot.get_user(req['user_id'])
        if not user:
            try:
                user = await self.bot.fetch_user(req['user_id'])
            except discord.HTTPException:
                user = None

        if user:
            view = discord.ui.View(timeout=None)
            close_btn = discord.ui.Button(label="Close", style=discord.ButtonStyle.secondary, custom_id=f"dmclose_{req_id}")
            fulfill_btn = discord.ui.Button(label="Fulfilled", style=discord.ButtonStyle.success, custom_id=f"dmfulfill_{req_id}")
            view.add_item(close_btn)
            view.add_item(fulfill_btn)
            
            try:
                await user.send(f"Your paid request #{req_id} has been approved!", embed=embed, view=view)
            except discord.Forbidden:
                pass

    async def handle_dm_action(self, interaction: discord.Interaction, req_id: int, action: str):
        req = await database.get_paid_request(req_id)
        if not req:
            await interaction.response.send_message("Request not found.", ephemeral=True)
            return

        approved_channel_id = int(os.getenv("PAID_REQUEST_APPROVED_CHANNEL_ID") or 0)
        approved_channel = self.bot.get_channel(approved_channel_id)
        
        if approved_channel and req['approved_msg_id']:
            try:
                msg = await approved_channel.fetch_message(req['approved_msg_id'])
                if action == 'closed':
                    await msg.delete()
                else:  # fulfilled
                    # Strikethrough the embed content
                    embed = msg.embeds[0]
                    embed.title = f"~~{embed.title}~~ [{action.upper()}]"
                    embed.color = discord.Color.dark_grey()
                    
                    # Apply strikethrough to all text fields
                    for i, field in enumerate(embed.fields):
                        val = field.value
                        if not val.startswith("~~"):
                            embed.set_field_at(i, name=field.name, value=f"~~{val}~~", inline=field.inline)
                            
                    await msg.edit(embed=embed)
            except (discord.NotFound, discord.HTTPException):
                pass

        await database.update_paid_request_status(req_id, action)
        
        # Disable buttons in DM
        view = discord.ui.View(timeout=None)
        close_btn = discord.ui.Button(label="Close", style=discord.ButtonStyle.secondary, disabled=True)
        fulfill_btn = discord.ui.Button(label="Fulfilled", style=discord.ButtonStyle.success, disabled=True)
        view.add_item(close_btn)
        view.add_item(fulfill_btn)
        
        await interaction.message.edit(view=view)
        await interaction.response.send_message(f"Marked as {action}.", ephemeral=True)

    async def handle_cancel(self, interaction: discord.Interaction, req_id: int):
        await interaction.response.defer(ephemeral=True)
        req = await database.get_paid_request(req_id)
        if not req:
            await interaction.followup.send("Request not found.", ephemeral=True)
            return

        # Fetch and delete review card
        review_channel_id = int(os.getenv("PAID_REQUEST_REVIEW_CHANNEL_ID") or 0)
        review_channel = self.bot.get_channel(review_channel_id)
        if review_channel and req['staff_review_msg_id']:
            try:
                msg = await review_channel.fetch_message(req['staff_review_msg_id'])
                await msg.delete()
            except discord.HTTPException:
                pass

        await database.update_paid_request_status(req_id, 'cancelled')

        # Edit DM message: disable/remove buttons and update content
        view = discord.ui.View(timeout=None)
        edit_btn = discord.ui.Button(label="Edit", style=discord.ButtonStyle.secondary, disabled=True)
        cancel_btn = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger, disabled=True)
        view.add_item(edit_btn)
        view.add_item(cancel_btn)

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            embed.title = f"~~{embed.title}~~ [CANCELLED]"
            embed.color = discord.Color.dark_grey()
            # Strikethrough fields
            for i, field in enumerate(embed.fields):
                val = field.value
                if not val.startswith("~~"):
                    embed.set_field_at(i, name=field.name, value=f"~~{val}~~", inline=field.inline)

        try:
            await interaction.message.edit(content="Your paid request has been cancelled.", embed=embed, view=view)
        except discord.HTTPException:
            pass

        # Log it to approval log
        log_channel_id = int(os.getenv("APPROVAL_LOG_CHANNEL_ID") or 0)
        log_channel = self.bot.get_channel(log_channel_id)
        if log_channel:
            submitter_str = f"{interaction.user.name} [{interaction.user.id}]"
            
            log_desc = (
                f"```\n"
                f"ID: {req_id}\n"
                f"Budget: {req['budget']}\n"
                f"Type: {req['sfw_nsfw']}\n"
                f"Payment: {req['payment_method']}\n"
                f"Use: {req['use_case']}\n"
                f"Content: {req['content']}\n"
                f"```"
            )
            
            log_embed = discord.Embed(
                title="Log: Request Cancelled",
                description=log_desc,
                color=discord.Color.dark_grey()
            )
            log_embed.add_field(name="Request From", value=submitter_str, inline=False)
            log_embed.add_field(name="Cancelled By", value=submitter_str, inline=False)
            
            now_str = datetime.now().strftime('%d %B %Y %H:%M')
            log_embed.add_field(name="Timestamp", value=f"`{now_str}`", inline=False)
            log_embed.add_field(name="ID", value=str(req_id), inline=False)
            
            await log_channel.send(embed=log_embed)

        await interaction.followup.send("Your request has been cancelled.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(PaidRequest(bot))
