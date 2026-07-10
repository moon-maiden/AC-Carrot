import discord
from discord import app_commands
from discord.ext import tasks, commands
import os
import database
from datetime import datetime, timezone
from .helpers import parse_duration_to_days
from .ui import PaidRequestModal, RejectReasonModal

class PaidRequest(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    @tasks.loop(hours=1)
    async def reminder_loop(self):
        await self.bot.wait_until_ready()
        await self.send_reminders(age_days=14.0)

    async def send_reminders(self, age_days: float):
        requests_to_remind = await database.get_paid_requests_for_reminders(age_days)
        for req in requests_to_remind:
            user_id = req['user_id']
            req_id = req['request_id']
            
            guild_id = req['guild_id'] if 'guild_id' in req.keys() else None
            guild = self.bot.get_guild(guild_id) if guild_id else None
            member = guild.get_member(user_id) if guild else None
            if guild and not member:
                try:
                    member = await guild.fetch_member(user_id)
                except discord.HTTPException:
                    member = None
                    
            if guild and not member:
                # User left the server, mark the request as invalid
                await database.update_paid_request_status(req_id, 'invalid', actioned_by=self.bot.user.id)
                
                # Delete the public approved message in the channel
                config = await database.get_guild_config(guild_id)
                approved_channel_id = config.get("approved_channel_id") or 0
                approved_channel = self.bot.get_channel(approved_channel_id)
                if not approved_channel and approved_channel_id:
                    try:
                        approved_channel = await self.bot.fetch_channel(approved_channel_id)
                    except discord.HTTPException:
                        pass
                if approved_channel and ('approved_msg_id' in req.keys() and req['approved_msg_id']):
                    try:
                        msg = await approved_channel.fetch_message(req['approved_msg_id'])
                        await msg.delete()
                    except (discord.NotFound, discord.HTTPException):
                        pass
                continue
                
            user = member
            if not user:
                try:
                    user = await self.bot.fetch_user(user_id)
                except discord.HTTPException:
                    continue
            
            # Parse created_at for dynamic timestamp
            # SQLite CURRENT_TIMESTAMP is 'YYYY-MM-DD HH:MM:SS' in UTC
            created_at_str = req['created_at']
            try:
                dt = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                timestamp = int(dt.timestamp())
                time_str = f"since <t:{timestamp}:R> (<t:{timestamp}:f>)"
            except Exception:
                time_str = "for more than 2 weeks"

            embed = discord.Embed(
                title=f"Paid Request #{req_id} Status Reminder",
                description=(
                    f"Your paid request has been open for {time_str}.\n"
                    "If the request has been fulfilled or is no longer needed, please close or mark it as fulfilled using the buttons below.\n\n"
                    f"**Details:**\n{req['content']}"
                ),
                color=discord.Color.orange()
            )
            embed.add_field(name="Budget", value=req['budget'], inline=True)
            embed.add_field(name="Payment", value=req['payment_method'], inline=True)
            embed.add_field(name="Use Case", value=req['use_case'], inline=True)
            embed.add_field(name="Type", value=req['sfw_nsfw'], inline=True)
            
            view = discord.ui.View(timeout=None)
            close_btn = discord.ui.Button(label="Close", style=discord.ButtonStyle.secondary, custom_id=f"dmclose_{req_id}")
            fulfill_btn = discord.ui.Button(label="Fulfilled", style=discord.ButtonStyle.success, custom_id=f"dmfulfill_{req_id}")
            view.add_item(close_btn)
            view.add_item(fulfill_btn)
            
            ref = None
            if req['dm_msg_id']:
                try:
                    dm_channel = user.dm_channel or await user.create_dm()
                    ref = discord.MessageReference(
                        message_id=req['dm_msg_id'],
                        channel_id=dm_channel.id
                    )
                except Exception:
                    ref = None
            
            try:
                reminder_msg = await user.send(
                    content="Hello! This is a reminder about your active paid request.",
                    embed=embed,
                    view=view,
                    reference=ref
                )
                await database.update_paid_request_reminder_msg(req_id, reminder_msg.id)
            except discord.Forbidden:
                pass
                
            await database.update_paid_request_reminded_time(req_id)

    @commands.command()
    async def trigger_paid_reminders(self, ctx, duration: str = "14d"):
        if ctx.author.id != 255174440005009408:
            if not ctx.guild or not ctx.author.guild_permissions.administrator:
                await ctx.send("You do not have the required administrator permissions to use this command.")
                return
        try:
            age_days = parse_duration_to_days(duration)
        except ValueError as e:
            await ctx.send(str(e))
            return
            
        await ctx.send(f"Checking and sending paid request reminders for age threshold of `{duration}`...")
        await self.send_reminders(age_days)
        await ctx.send("Finished processing reminders.")

    @commands.command()
    async def resend_pendings(self, ctx):
        if ctx.author.id != 255174440005009408:
            if not ctx.guild or not ctx.author.guild_permissions.administrator:
                await ctx.send("You do not have the required administrator permissions to use this command.")
                return

        pending_reqs = await database.get_pending_paid_requests()
        if not pending_reqs:
            await ctx.send("No pending requests found in the database.")
            return

        config = await database.get_guild_config(ctx.guild.id if ctx.guild else 0)
        review_channel_id = config.get("review_channel_id") or 0

        if not review_channel_id:
            async with database.aiosqlite.connect(database.DB_NAME) as db:
                db.row_factory = database.aiosqlite.Row
                cursor = await db.execute("SELECT review_channel_id FROM guild_configs WHERE review_channel_id IS NOT NULL LIMIT 1")
                row = await cursor.fetchone()
                if row:
                    review_channel_id = row['review_channel_id']

        if not review_channel_id:
            await ctx.send("Error: Paid Request Review Channel is not configured properly in the Dashboard.")
            return

        review_channel = self.bot.get_channel(review_channel_id)
        if not review_channel:
            try:
                review_channel = await self.bot.fetch_channel(review_channel_id)
            except Exception:
                pass

        if not review_channel:
            await ctx.send(f"Error: Could not find or access the Review Channel (ID: {review_channel_id}). Make sure the bot is in the server and has View Channel permissions.")
            return

        guild = review_channel.guild
        sent_count = 0

        for req in pending_reqs:
            request_id = req['request_id']
            
            if req['staff_review_msg_id']:
                try:
                    await review_channel.fetch_message(req['staff_review_msg_id'])
                    continue
                except (discord.NotFound, discord.HTTPException):
                    pass

            member = None
            try:
                member = guild.get_member(req['user_id']) or await guild.fetch_member(req['user_id'])
            except discord.HTTPException:
                pass

            joined_str = "Unknown"
            display_name = f"User ID {req['user_id']}"
            avatar_url = None
            username = "Unknown"

            if member:
                display_name = member.display_name
                username = member.name
                if member.display_avatar:
                    avatar_url = member.display_avatar.url
                if member.joined_at:
                    joined_str = f"<t:{int(member.joined_at.timestamp())}:f> ( <t:{int(member.joined_at.timestamp())}:R> )"

            embed = discord.Embed(
                title=f"Request By {display_name}",
                description=req['content'],
                color=discord.Color.blue()
            )
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)

            embed.add_field(name="Budget", value=req['budget'], inline=False)
            embed.add_field(name="Type", value=req['sfw_nsfw'], inline=False)
            embed.add_field(name="Payment", value=req['payment_method'], inline=False)
            embed.add_field(name="Use", value=req['use_case'], inline=False)
            embed.add_field(name="Member", value=f"<@{req['user_id']}> | {username} [{req['user_id']}]", inline=False)
            embed.add_field(name="Joined", value=joined_str, inline=False)
            embed.add_field(name="ID", value=str(request_id), inline=False)

            view = discord.ui.View(timeout=None)
            approve_btn = discord.ui.Button(label="Approve", style=discord.ButtonStyle.success, custom_id=f"approve_{request_id}")
            reject_btn = discord.ui.Button(label="Reject", style=discord.ButtonStyle.danger, custom_id=f"reject_{request_id}")
            view.add_item(approve_btn)
            view.add_item(reject_btn)

            try:
                msg = await review_channel.send(embed=embed, view=view)
                await database.update_paid_request_review_msg(request_id, msg.id)
                sent_count += 1
            except discord.HTTPException as e:
                await ctx.send(f"Failed to resend request #{request_id}: {str(e)}")

        await ctx.send(f"Successfully resent {sent_count} pending review cards to {review_channel.mention}!")

    @app_commands.command(name="purge", description="Purge specific database tables (Developer Only)")
    @app_commands.describe(target="What to purge")
    @app_commands.choices(target=[
        app_commands.Choice(name="Paid Requests", value="paid_requests"),
        app_commands.Choice(name="Verbals", value="verbals")
    ])
    async def purge_slash(self, interaction: discord.Interaction, target: str):
        if interaction.user.id != 255174440005009408:
            await interaction.response.send_message("❌ Only the developer can use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        if target == "paid_requests":
            await database.purge_all_paid_requests()
            await interaction.followup.send("✅ All paid requests have been successfully purged from the database.", ephemeral=True)
        elif target == "verbals":
            await database.purge_all_warnings()
            await interaction.followup.send("✅ All verbals have been successfully purged from the database.", ephemeral=True)

    @commands.command(name="purge")
    async def purge_prefix(self, ctx, *, target: str = None):
        if ctx.author.id != 255174440005009408:
            await ctx.send("❌ Only the developer can use this command.")
            return

        if not target or target.lower() not in ["verbals", "paid requests"]:
            await ctx.send("❌ Please specify what to purge: `!purge verbals` or `!purge paid requests`")
            return

        if target.lower() == "paid requests":
            await database.purge_all_paid_requests()
            await ctx.send("✅ All paid requests have been successfully purged from the database.")
        elif target.lower() == "verbals":
            await database.purge_all_warnings()
            await ctx.send("✅ All verbals have been successfully purged from the database.")


    @commands.Cog.listener()
    async def on_ready(self):
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
        
        config = await database.get_guild_config(ctx.guild.id if ctx.guild else 0)
        submit_channel_id = config.get("submit_channel_id") or 0
        submit_channel = self.bot.get_channel(submit_channel_id)
        
        if submit_channel:
            await submit_channel.send(embed=embed, view=view)
            await ctx.send(f"Setup complete! The create button was sent to {submit_channel.mention}", ephemeral=True)
        else:
            await ctx.send("Error: Paid Request Submit Channel is not configured properly in the Dashboard.", ephemeral=True)
            
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
            count = await database.get_active_paid_requests_count(interaction.user.id)
            if count >= 2:
                await interaction.response.send_message(
                    "You cannot have more than 2 active paid requests (pending or approved) at the same time. "
                    "Please close or fulfill one of your current requests before creating a new one.",
                    ephemeral=True
                )
                return
            await interaction.response.send_modal(PaidRequestModal())
            return
            
        elif custom_id.startswith("dmresubmit_"):
            req_id = int(custom_id.split("_")[1])
            req = await database.get_paid_request(req_id)
            if not req:
                await interaction.response.send_message("Request not found.", ephemeral=True)
                return
                
            count = await database.get_active_paid_requests_count(interaction.user.id)
            if count >= 2:
                await interaction.response.send_message(
                    "You cannot have more than 2 active paid requests (pending or approved) at the same time. "
                    "Please close or fulfill one of your current requests before resubmitting.",
                    ephemeral=True
                )
                return
                
            await interaction.response.send_modal(PaidRequestModal(
                budget_val=req['budget'],
                sfw_nsfw_val=req['sfw_nsfw'],
                payment_method_val=req['payment_method'],
                use_case_val=req['use_case'],
                content_val=req['content'],
                guild_id=req['guild_id']
            ))
            return
            
        if custom_id.startswith("approve_"):
            req_id = int(custom_id.split("_")[1])
            await self.handle_approve(interaction, req_id)
            
        elif custom_id.startswith("reject_"):
            req_id = int(custom_id.split("_")[1])
            req = await database.get_paid_request(req_id)
            if not req:
                await interaction.response.send_message("Request not found.", ephemeral=True)
                return
                
            if req['status'] != 'pending':
                await interaction.response.send_message(f"This request has already been actioned (Status: {req['status']}).", ephemeral=True)
                try:
                    await interaction.message.delete()
                except discord.HTTPException:
                    pass
                return
                
            guild = interaction.guild
            member = guild.get_member(req['user_id'])
            if not member and guild:
                try:
                    member = await guild.fetch_member(req['user_id'])
                except discord.HTTPException:
                    member = None
            
            if not member:
                await interaction.response.defer(ephemeral=True)
                await database.update_paid_request_status(req_id, 'invalid', actioned_by=interaction.user.id)
                config = await database.get_guild_config(interaction.guild_id or 0)
                log_channel_id = config.get("approval_log_channel_id") or 0
                log_channel = self.bot.get_channel(log_channel_id)
                if log_channel:
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
                        title="Log: Request Invalidated (User Left)",
                        description=log_desc,
                        color=discord.Color.dark_grey()
                    )
                    log_embed.add_field(name="Request From", value=f"Unknown [{req['user_id']}]", inline=False)
                    log_embed.add_field(name="Actioned By", value=f"{interaction.user.name} [{interaction.user.id}]", inline=False)
                    now_str = datetime.now().strftime('%d %B %Y %H:%M')
                    log_embed.add_field(name="Timestamp", value=f"`{now_str}`", inline=False)
                    log_embed.add_field(name="ID", value=str(req_id), inline=False)
                    await log_channel.send(embed=log_embed)
                try:
                    await interaction.message.delete()
                except discord.HTTPException:
                    pass
                await interaction.followup.send("User is no longer in the server. Request marked as Invalid.", ephemeral=True)
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
                dm_msg=interaction.message,
                guild_id=req['guild_id']
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
            
        if req['status'] != 'pending':
            await interaction.followup.send(f"This request has already been actioned (Status: {req['status']}).", ephemeral=True)
            try:
                await interaction.message.delete()
            except discord.HTTPException:
                pass
            return

        config = await database.get_guild_config(interaction.guild_id or 0)
        approved_channel_id = config.get("approved_channel_id") or 0
        approved_channel = self.bot.get_channel(approved_channel_id)
        
        guild = interaction.guild
        member = guild.get_member(req['user_id'])
        if not member and guild:
            try:
                member = await guild.fetch_member(req['user_id'])
            except discord.HTTPException:
                member = None

        if not member:
            await database.update_paid_request_status(req_id, 'invalid', actioned_by=interaction.user.id)
            log_channel_id = config.get("approval_log_channel_id") or 0
            log_channel = self.bot.get_channel(log_channel_id)
            if log_channel:
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
                    title="Log: Request Invalidated (User Left)",
                    description=log_desc,
                    color=discord.Color.dark_grey()
                )
                log_embed.add_field(name="Request From", value=f"Unknown [{req['user_id']}]", inline=False)
                log_embed.add_field(name="Actioned By", value=f"{interaction.user.name} [{interaction.user.id}]", inline=False)
                now_str = datetime.now().strftime('%d %B %Y %H:%M')
                log_embed.add_field(name="Timestamp", value=f"`{now_str}`", inline=False)
                log_embed.add_field(name="ID", value=str(req_id), inline=False)
                await log_channel.send(embed=log_embed)
            try:
                await interaction.message.delete()
            except discord.HTTPException:
                pass
            await interaction.followup.send("User is no longer in the server. Request marked as Invalid.", ephemeral=True)
            return

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

        approved_msg = None
        if approved_channel:
            approved_msg = await approved_channel.send(content=f"__**DIRECT MESSAGE the user here:**__ <@{req['user_id']}>", embed=embed)
            
        await database.update_paid_request_status(req_id, 'approved', approved_msg.id if approved_msg else None, actioned_by=interaction.user.id)

        log_channel_id = config.get("approval_log_channel_id") or 0
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

        await interaction.followup.send("Request approved and moved.", ephemeral=True)
        await interaction.message.delete()

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
                dm_msg = await user.send(f"Your paid request #{req_id} has been approved!", embed=embed, view=view)
                await database.update_paid_request_dm_msg(req_id, dm_msg.id)
            except discord.Forbidden:
                pass

    async def handle_dm_action(self, interaction: discord.Interaction, req_id: int, action: str):
        req = await database.get_paid_request(req_id)
        if not req:
            await interaction.response.send_message("Request not found.", ephemeral=True)
            return

        guild_id = req['guild_id'] if req else None
        config = await database.get_guild_config(guild_id or interaction.guild_id or 0)
        approved_channel_id = config.get("approved_channel_id") or 0
        approved_channel = self.bot.get_channel(approved_channel_id)
        if not approved_channel:
            try:
                approved_channel = await self.bot.fetch_channel(approved_channel_id)
            except discord.HTTPException:
                pass
        
        if approved_channel and req['approved_msg_id']:
            try:
                msg = await approved_channel.fetch_message(req['approved_msg_id'])
                if action == 'closed':
                    await msg.delete()
                else:  # fulfilled
                    embed = msg.embeds[0]
                    embed.title = f"~~{embed.title}~~ [{action.upper()}]"
                    embed.color = discord.Color.dark_grey()
                    
                    for i, field in enumerate(embed.fields):
                        val = field.value
                        if not val.startswith("~~"):
                            embed.set_field_at(i, name=field.name, value=f"~~{val}~~", inline=field.inline)
                            
                    await msg.edit(embed=embed)
            except (discord.NotFound, discord.HTTPException):
                pass

        await database.update_paid_request_status(req_id, action, actioned_by=interaction.user.id)
        
        view = discord.ui.View(timeout=None)
        close_btn = discord.ui.Button(label="Close", style=discord.ButtonStyle.secondary, disabled=True)
        fulfill_btn = discord.ui.Button(label="Fulfilled", style=discord.ButtonStyle.success, disabled=True)
        view.add_item(close_btn)
        view.add_item(fulfill_btn)
        
        await interaction.message.edit(view=view)
        await interaction.response.send_message(f"Marked as {action}.", ephemeral=True)

        dm_channel = interaction.channel or await interaction.user.create_dm()
        other_msg_id = None
        if req['dm_msg_id'] and interaction.message.id != req['dm_msg_id']:
            other_msg_id = req['dm_msg_id']
        elif req['reminder_msg_id'] and interaction.message.id != req['reminder_msg_id']:
            other_msg_id = req['reminder_msg_id']
            
        if other_msg_id:
            try:
                other_msg = await dm_channel.fetch_message(other_msg_id)
                await other_msg.edit(view=view)
            except Exception:
                pass

    async def handle_cancel(self, interaction: discord.Interaction, req_id: int):
        await interaction.response.defer(ephemeral=True)
        req = await database.get_paid_request(req_id)
        if not req:
            await interaction.followup.send("Request not found.", ephemeral=True)
            return

        guild_id = req['guild_id'] if req else None
        config = await database.get_guild_config(guild_id or interaction.guild_id or 0)
        review_channel_id = config.get("review_channel_id") or 0
        review_channel = self.bot.get_channel(review_channel_id)
        if review_channel and req['staff_review_msg_id']:
            try:
                msg = review_channel.get_partial_message(req['staff_review_msg_id'])
                await msg.delete()
            except discord.HTTPException:
                pass

        await database.update_paid_request_status(req_id, 'cancelled', actioned_by=interaction.user.id)

        view = discord.ui.View(timeout=None)
        edit_btn = discord.ui.Button(label="Edit", style=discord.ButtonStyle.secondary, disabled=True)
        cancel_btn = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger, disabled=True)
        view.add_item(edit_btn)
        view.add_item(cancel_btn)

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            embed.title = f"~~{embed.title}~~ [CANCELLED]"
            embed.color = discord.Color.dark_grey()
            for i, field in enumerate(embed.fields):
                val = field.value
                if not val.startswith("~~"):
                    embed.set_field_at(i, name=field.name, value=f"~~{val}~~", inline=field.inline)

        try:
            await interaction.message.edit(content="Your paid request has been cancelled.", embed=embed, view=view)
        except discord.HTTPException:
            pass

        log_channel_id = config.get("approval_log_channel_id") or 0
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
