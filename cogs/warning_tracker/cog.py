import discord
from discord.ext import commands
from discord import app_commands
import os
import database
import asyncio
from datetime import datetime, timezone, timedelta

from .helpers import get_ordinal, is_repeated_offense, get_channel_mention
from .ui import (
    RemovalDropdownView,
    RemovalReasonSelect,
    VerbalReasonModal,
    VerbalPreviewView,
    WarningsPaginationView,
    StaffWarningsPaginationView,
    HelpPaginationView,
    EditVerbalReasonSelect,
    PendingDeletionReviewView,
    RejectDeletionModal,
    EditPendingReasonSelect,
    EditPendingReasonView,
    is_higher_up
)

class WarningTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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

        config = await database.get_guild_config(ctx.guild.id)
        commands_channel_id = config.get("staff_commands_channel_id") or 0
        staff_role_ids = [
            config.get("team_leader_role_id") or 0,
            config.get("moderator_role_id") or 0,
            config.get("trial_moderator_role_id") or 0
        ]

        # 1. Restrict to staff commands channel
        if commands_channel_id != 0 and ctx.channel.id != commands_channel_id:
            try:
                await ctx.send(f"Error: This command can only be used in the staff commands channel (<#{commands_channel_id}>).", delete_after=5)
                if ctx.guild:
                    await ctx.message.delete()
            except Exception:
                pass
            return False

        # 2. Restrict to staff role holders or server admins
        if ctx.guild:
            if ctx.author.id != 255174440005009408:
                has_role = any(role.id in staff_role_ids for role in ctx.author.roles)
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
        config = await database.get_guild_config(interaction.guild_id or 0)
        staff_role_ids = [config.get("team_leader_role_id"), config.get("moderator_role_id"), config.get("trial_moderator_role_id")]
        
        # Check role
        is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False
        user_role_ids = [r.id for r in interaction.user.roles] if hasattr(interaction.user, 'roles') else []
        on_wheels = await database.is_user_on_training_wheels(interaction.guild_id or 0, interaction.user.id, user_role_ids, config)
        if interaction.user.id != 255174440005009408 and not is_admin and not on_wheels and not any(role.id in staff_role_ids for role in interaction.user.roles):
            await interaction.followup.send("You do not have the required staff role to use this command.", ephemeral=True)
            return

        reasons_db = await database.get_all_verbal_reasons(interaction.guild_id or 0)
        if not reasons_db:
            await interaction.followup.send("No verbal reasons configured in the database.", ephemeral=True)
            return

        # Send ephemeral dropdown select menu
        view = RemovalDropdownView(RemovalReasonSelect(message, self, reasons_db), timeout=180)
        msg = await interaction.followup.send("Select a reason to remove this post:", view=view, ephemeral=True)
        view.message = msg

    async def execute_removal(self, interaction: discord.Interaction, message: discord.Message, reason: str, original_content: str):
        config = await database.get_guild_config(interaction.guild_id or 0)
        notice_channel_id = config.get("staff_notice_channel_id") or 0
        log_channel_id = config.get("staff_log_channel_id") or 0
        
        # 1. Save attachments as JSON in the database BEFORE deleting the message (so Discord CDN links are valid)
        all_attachments = list(message.attachments)
        if hasattr(message, "message_snapshots") and message.message_snapshots:
            for snapshot in message.message_snapshots:
                if hasattr(snapshot, "attachments") and snapshot.attachments:
                    all_attachments.extend(snapshot.attachments)

        import json
        import uuid
        import os
        saved_attachments = []
        for a in all_attachments:
            try:
                ext = os.path.splitext(a.filename)[1]
                unique_filename = f"{uuid.uuid4()}{ext}"
                file_path = os.path.join(database.ATTACHMENTS_DIR, unique_filename)
                await a.save(file_path)
                saved_attachments.append({
                    "filename": a.filename,
                    "stored_filename": unique_filename
                })
            except Exception as e:
                print(f"Failed to download/save attachment {a.filename}: {e}")
                
        attachments_data = json.dumps(saved_attachments) if saved_attachments else None

        # 2. Delete message
        try:
            await message.delete()
        except discord.HTTPException as e:
            err_msg = f"Failed to delete the message: {e}"
            if e.code == 50013:
                err_msg += "\n\n**Note:** This means the *bot itself* is missing the `Manage Messages` permission in this channel. Even as a superuser, the bot still needs Discord permissions to delete other users' messages!"
            await interaction.followup.send(err_msg, ephemeral=True)
            return

        # 3. Post warning in staff-notice
        notice_channel = self.bot.get_channel(notice_channel_id)
        if not notice_channel:
            try:
                notice_channel = await asyncio.wait_for(self.bot.fetch_channel(notice_channel_id), timeout=5.0)
            except Exception:
                pass

        notice_msg = None
        if notice_channel:
            try:
                allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
                notice_content = f"{message.author.mention} {reason}"
                if len(notice_content) > 2000:
                    notice_content = notice_content[:1997] + "..."
                notice_msg = await notice_channel.send(content=notice_content, allowed_mentions=allowed_mentions)
            except Exception as e:
                print(f"Error sending notice message: {e}")

        # Log it in staff log channel
        # Add warning to database (reference the staff notice message so delverbal works)
        warn_channel_id = notice_channel_id if notice_msg else message.channel.id
        warn_message_id = notice_msg.id if notice_msg else 0

        
        # Extract text content (checking snapshots for forwarded messages)
        resolved_content = original_content or ""
        if hasattr(message, "message_snapshots") and message.message_snapshots:
            snapshot_contents = []
            for snapshot in message.message_snapshots:
                snap_txt = snapshot.content or "*No text content*"
                snapshot_contents.append(f"(Forwarded Message) {snap_txt}")
            if snapshot_contents:
                if resolved_content:
                    resolved_content = resolved_content + "\n" + "\n".join(snapshot_contents)
                else:
                    resolved_content = "\n".join(snapshot_contents)

        if not resolved_content:
            resolved_content = "*No text content*"

        warn_id = await database.add_warning(
            user_id=message.author.id,
            channel_id=warn_channel_id,
            message_id=warn_message_id,
            message_content=resolved_content,
            staff_id=interaction.user.id,
            reason=reason,
            post_created_at=message.created_at.isoformat(),
            guild_id=message.guild.id if message.guild else None,
            attachments=attachments_data
        )

        # Log it in staff log channel
        log_channel = self.bot.get_channel(log_channel_id)
        if not log_channel:
            try:
                log_channel = await asyncio.wait_for(self.bot.fetch_channel(log_channel_id), timeout=5.0)
            except Exception:
                pass
        
        if not log_channel:
            await interaction.followup.send(f"Warning: Could not fetch the log channel ({log_channel_id}). Please check bot permissions and channel ID.", ephemeral=True)
        else:
            orig_ts = int(message.created_at.timestamp())
            del_ts = int(datetime.now(timezone.utc).timestamp())
            log_embed = discord.Embed(
                title="Log: Post Removed",
                color=discord.Color.orange()
            )
            log_embed.add_field(name="Warning ID", value=f"#{warn_id}", inline=False)
            log_embed.add_field(name="Staff Member", value=f"{interaction.user.mention} ({interaction.user.id})", inline=True)
            log_embed.add_field(name="Original Author", value=f"{message.author.mention} ({message.author.id})", inline=True)
            log_embed.add_field(name="Channel", value=get_channel_mention(message.channel), inline=True)
            log_embed.add_field(name="Original Post Created At", value=f"<t:{orig_ts}:f> (<t:{orig_ts}:R>)", inline=True)
            log_embed.add_field(name="Post Deleted At", value=f"<t:{del_ts}:f> (<t:{del_ts}:R>)", inline=True)
            
            reason_text = reason
            if len(reason_text) > 1024:
                reason_text = reason_text[:1021] + "..."
            log_embed.add_field(name="Rejection Reason", value=reason_text, inline=False)
            
            dashboard_url = os.getenv("DASHBOARD_URL", "localhost:3000")
            if dashboard_url.startswith("http://") or dashboard_url.startswith("https://"):
                base_url = dashboard_url
            else:
                clean_host = dashboard_url.split(":")[0]
                is_ip = clean_host.replace(".", "").isdigit() or clean_host == "localhost"
                protocol = "http" if is_ip else "https"
                base_url = f"{protocol}://{dashboard_url}"
            
            log_link = f"[log]({base_url}/guilds/{message.guild.id if message.guild else 0}/logs/warnings/{warn_id})"

            # Original Post Content (without link is 10 chars for formatting: ```\n\n```\n, with link is 10 + len(log_link) + 1 for newline)
            content_snippet = resolved_content
            if all_attachments:
                allowed_content_len = 1024 - 10
            else:
                allowed_content_len = 1024 - 11 - len(log_link)
            
            # Cap at 800 for readability, but restrict by allowed length too
            max_content_len = min(800, allowed_content_len - 3)
            if len(content_snippet) > max_content_len:
                content_snippet = content_snippet[:max_content_len] + "..."

            if all_attachments:
                # Add Original Post Content (without link)
                log_embed.add_field(
                    name="Original Post Content",
                    value=f"```\n{content_snippet}\n```",
                    inline=False
                )
                # Add Attachments (with link)
                attachments_list = "\n".join([a.url for a in all_attachments])
                allowed_attachments_len = 1024 - 2 - len(log_link) - 3 # 2 for \n\n, 3 for "..."
                if len(attachments_list) > allowed_attachments_len:
                    attachments_list = attachments_list[:allowed_attachments_len] + "..."
                attachments_list += f"\n\n{log_link}"
                log_embed.add_field(name="Attachments", value=attachments_list, inline=False)
            else:
                # Add Original Post Content (with link)
                log_embed.add_field(
                    name="Original Post Content",
                    value=f"```\n{content_snippet}\n```\n{log_link}",
                    inline=False
                )

                
            try:
                await log_channel.send(embed=log_embed)
            except Exception as e:
                await interaction.followup.send(f"Warning: Failed to send log embed: {e}", ephemeral=True)
                print(f"Error sending log embed: {e}")

        await interaction.followup.send("Verbal warning successfully logged.", ephemeral=True)

        # DM the user if not a bot
        if not message.author.bot:
            try:
                count = await database.get_warnings_count_last_3_months(message.author.id, guild_id=message.guild.id if message.guild else None)
                previous_warnings = await database.get_warnings_last_3_months(message.author.id, guild_id=message.guild.id if message.guild else None)
                history = previous_warnings[1:] if len(previous_warnings) > 1 else []
                is_repeat = is_repeated_offense(reason, history)
                timestamp_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")
                embed = discord.Embed(color=discord.Color.red())
                guild = message.guild
                guild_name = guild.name if guild else "this server"
                icon_url = guild.icon.url if guild and guild.icon else self.bot.user.display_avatar.url
                embed.set_author(name=f"{guild_name} | {timestamp_str}", icon_url=icon_url)
                
                ordinal_num = get_ordinal(count)
                desc = f"### This is your {ordinal_num} verbal warning\n\n"
                suffix = "" if "server" in guild_name.lower() else " server"
                desc += f"You have received a __verbal warning__ in {guild_name}{suffix} for:\n"
                
                context_reason = reason
                if len(context_reason) > 1200:
                    context_reason = context_reason[:1197] + "..."
                
                quoted_lines = []
                unbold_rest = False
                for line in context_reason.split('\n'):
                    if "Note:" in line:
                        unbold_rest = True
                        
                    if unbold_rest:
                        quoted_lines.append(f"> {line}")
                    else:
                        quoted_lines.append(f"> {line}")
                desc += "\n".join(quoted_lines) + "\n"
                
                if is_repeat:
                    desc += "\n⚠️ **Note:** You have received a verbal notice for the same offense in the last 3 months. Repeated offenses may lead to stricter actions.\n"
                elif count == 2:
                    desc += "\n⚠️ **This is your 2nd verbal notice in the last 3 months.** Accumulating one more notice will result in further staff action.\n"
                
                jump_url = notice_msg.jump_url if notice_msg else "https://discord.com"
                desc += f"\n**[Link to verbal warn]({jump_url})**\n\n"
                desc += "-# In case of questions, or if you believe you've been warned by mistake; please contact <@501746915218554881> for appeal or concerns."
                
                embed.description = desc
                embed.set_footer(text="Verbal warnings expire every 3 months.")
                
                guild_config = await database.get_guild_config(guild.id if guild else 0)
                if guild_config.get("dm_on_warning", 1):
                    # Send warning embed first
                    await message.author.send(embed=embed)
                    
                    # Prepare files
                    files = []
                    for att in saved_attachments:
                        try:
                            file_path = os.path.join(database.ATTACHMENTS_DIR, att["stored_filename"])
                            if os.path.exists(file_path):
                                files.append(discord.File(file_path, filename=att["filename"]))
                        except Exception as fe:
                            print(f"Error preparing file for DM: {fe}")
                            
                    # Send original content and files as a separate embed (in markdown)
                    content_display = resolved_content
                    if len(content_display) > 2048:
                        content_display = content_display[:2045] + "..."
                        
                    followup_embed = discord.Embed(
                        title="Removed post",
                        description=content_display,
                        color=discord.Color.light_grey()
                    )
                    if files:
                        await message.author.send(embed=followup_embed, files=files)
                    else:
                        await message.author.send(embed=followup_embed)

            except Exception as e:
                print(f"Could not DM user {message.author.id}: {e}")

        # Warning threshold check (3 warnings in 3 months)
        await self._check_and_send_threshold_alert(message.guild.id if message.guild else 0, message.author.id, fallback_staff_id=interaction.user.id)

    async def _check_and_send_threshold_alert(self, guild_id: int, author_id: int, fallback_staff_id: int = None):
        count = await database.get_warnings_count_last_3_months(author_id, guild_id=guild_id)
        if count >= 3:
            guild_config = await database.get_guild_config(guild_id)
            commands_channel_id = guild_config.get("staff_commands_channel_id") or 0
            commands_channel = self.bot.get_channel(commands_channel_id)
            if not commands_channel and commands_channel_id:
                try:
                    commands_channel = await asyncio.wait_for(self.bot.fetch_channel(commands_channel_id), timeout=5.0)
                except Exception:
                    pass
            if commands_channel:
                last_warnings = await database.get_warnings_last_3_months(author_id, guild_id=guild_id)
                last_warnings.reverse()
                
                formatted_warnings = []
                for warn_id, content, warned_at in last_warnings:
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
                            prefix = "- " if sub_bullet_idx == 0 else "   - "
                            formatted_lines.append(prefix + line[2:])
                            sub_bullet_idx += 1
                        else:
                            formatted_lines.append(line)
                    
                    content_str = "\n".join(formatted_lines)
                    formatted_warnings.append(f"**ID: {warn_id}** ({time_str}) {content_str}")
                
                warnings_str = ""
                truncated_any = False
                for w in formatted_warnings:
                    if len(warnings_str) + len(w) + 2 > 3500:
                        truncated_any = True
                        break
                    if warnings_str:
                        warnings_str += "\n" + w
                    else:
                        warnings_str = w
                
                if truncated_any:
                    warnings_str += "\n*(Older warnings truncated to fit Discord message limits...)*"
                
                last_staff_id = await database.get_last_warning_staff_id_last_3_months(author_id, guild_id=guild_id)
                if not last_staff_id and fallback_staff_id:
                    last_staff_id = fallback_staff_id
                staff_mention = f"<@{last_staff_id}>" if last_staff_id else "@here"
                
                embed = discord.Embed(
                    title="⚠️ Warning Threshold Reached",
                    description=f"User <@{author_id}> ({author_id}) has accumulated **{count}** verbal notice(s) within 3 months. Please take immediate action.\n\n**Recent Warning History:**\n{warnings_str}",
                    color=discord.Color.red()
                )
                
                allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
                await commands_channel.send(
                    content=f"{staff_mention}",
                    embed=embed,
                    allowed_mentions=allowed_mentions
                )

    async def queue_removal(self, interaction: discord.Interaction, message: discord.Message, reason: str, original_content: str):
        config = await database.get_guild_config(interaction.guild_id or 0)
        review_channel_id = config.get("deletion_review_channel_id") or config.get("staff_commands_channel_id") or 0

        # Validate review channel before writing to database or disk
        review_channel = self.bot.get_channel(review_channel_id)
        if not review_channel and review_channel_id:
            try:
                review_channel = await asyncio.wait_for(self.bot.fetch_channel(review_channel_id), timeout=5.0)
            except Exception:
                pass

        if not review_channel:
            await interaction.followup.send(
                f"Warning: Could not access the deletion review channel (ID: {review_channel_id}). Please check bot permissions and channel ID.",
                ephemeral=True
            )
            return

        # 1. Save attachments immediately before anything changes
        all_attachments = list(message.attachments)
        if hasattr(message, "message_snapshots") and message.message_snapshots:
            for snapshot in message.message_snapshots:
                if hasattr(snapshot, "attachments") and snapshot.attachments:
                    all_attachments.extend(snapshot.attachments)

        import json
        import uuid
        import os
        saved_attachments = []
        for a in all_attachments:
            try:
                ext = os.path.splitext(a.filename)[1]
                unique_filename = f"{uuid.uuid4()}{ext}"
                file_path = os.path.join(database.ATTACHMENTS_DIR, unique_filename)
                await a.save(file_path)
                saved_attachments.append({
                    "filename": a.filename,
                    "stored_filename": unique_filename,
                    "url": getattr(a, "url", None)
                })
            except Exception as e:
                print(f"Failed to download/save attachment {a.filename}: {e}")
                
        attachments_data = json.dumps(saved_attachments) if saved_attachments else None

        # 2. Resolve content
        resolved_content = original_content or ""
        if hasattr(message, "message_snapshots") and message.message_snapshots:
            snapshot_contents = []
            for snapshot in message.message_snapshots:
                snap_txt = snapshot.content or "*No text content*"
                snapshot_contents.append(f"(Forwarded Message) {snap_txt}")
            if snapshot_contents:
                if resolved_content:
                    resolved_content = resolved_content + "\n" + "\n".join(snapshot_contents)
                else:
                    resolved_content = "\n".join(snapshot_contents)

        if not resolved_content:
            resolved_content = "*No text content*"

        marked_at = datetime.now(timezone.utc).isoformat()
        post_created_at = message.created_at.isoformat()

        # 3. Add to pending_post_deletions table
        pending_id = await database.add_pending_post_deletion(
            guild_id=message.guild.id if message.guild else (interaction.guild_id or 0),
            channel_id=message.channel.id,
            message_id=message.id,
            author_id=message.author.id,
            staff_id=interaction.user.id,
            reason=reason,
            original_content=resolved_content,
            post_created_at=post_created_at,
            marked_at=marked_at,
            attachments=attachments_data
        )

        # 4. Send exact post preview (content + attachments) to review channel
        preview_content = resolved_content if resolved_content != "*No text content*" else ""
        if len(preview_content) > 2000:
            preview_content = preview_content[:1997] + "..."

        preview_files = []
        for att in saved_attachments:
            try:
                file_path = os.path.join(database.ATTACHMENTS_DIR, att["stored_filename"])
                if os.path.exists(file_path):
                    preview_files.append(discord.File(file_path, filename=att["filename"]))
            except Exception as fe:
                print(f"Error preparing file for preview: {fe}")

        files_to_send = preview_files[:10] if preview_files else None
        if len(preview_files) > 10:
            for extra_f in preview_files[10:]:
                extra_f.close()
            overflow_note = f"\n*(Showing 10 of {len(preview_files)} attachments in preview)*"
            if len(preview_content) + len(overflow_note) <= 2000:
                preview_content += overflow_note
            else:
                preview_content = preview_content[:2000 - len(overflow_note)] + overflow_note

        send_content = preview_content or (None if files_to_send else "*No text content*")
        preview_msg = None
        try:
            preview_msg = await review_channel.send(
                content=send_content,
                files=files_to_send,
                allowed_mentions=discord.AllowedMentions.none()
            )
        except Exception as e:
            print(f"Failed to send preview message with attachments: {e}")
            try:
                fallback_content = preview_content or "*No text content*"
                if preview_files:
                    fallback_content += "\n*(Attachments could not be previewed)*"
                preview_msg = await review_channel.send(
                    content=fallback_content,
                    allowed_mentions=discord.AllowedMentions.none()
                )
            except Exception as e2:
                print(f"Failed to send fallback preview message: {e2}")

        # 5. Post review card to deletion review channel as reply to preview
        orig_ts = int(message.created_at.timestamp())
        marked_ts = int(datetime.fromisoformat(marked_at).timestamp())

        review_embed = discord.Embed(
            title="Pending Post Deletion",
            color=discord.Color.yellow(),
            description="A post has been marked for deletion and is waiting for higher-up review."
        )
        review_embed.add_field(name="Marked By", value=f"{interaction.user.mention} ({interaction.user.id})", inline=True)
        review_embed.add_field(name="Original Author", value=f"{message.author.mention} ({message.author.id})", inline=True)
        review_embed.add_field(name="Channel", value=f"{get_channel_mention(message.channel)} • [Jump to Message]({message.jump_url})", inline=True)
        review_embed.add_field(name="Original Post Created At", value=f"<t:{orig_ts}:f> (<t:{orig_ts}:R>)", inline=True)
        review_embed.add_field(name="Marked For Deletion At", value=f"<t:{marked_ts}:f> (<t:{marked_ts}:R>)", inline=True)
        
        reason_text = reason
        if len(reason_text) > 1024:
            reason_text = reason_text[:1021] + "..."
        review_embed.add_field(name="Removal Reason", value=reason_text, inline=False)

        # Only add content snippet and attachments to embed if preview message could not be sent
        if not preview_msg:
            content_snippet = resolved_content
            if len(content_snippet) > 800:
                content_snippet = content_snippet[:797] + "..."
            review_embed.add_field(name="Original Post Content", value=f"```\n{content_snippet}\n```", inline=False)

            if saved_attachments:
                att_names = ", ".join([f"`{a['filename']}`" for a in saved_attachments])
                if len(att_names) > 1024:
                    att_names = att_names[:1021] + "..."
                review_embed.add_field(name="Attachments", value=att_names, inline=False)

        review_view = PendingDeletionReviewView(pending_id, cog=self)
        if preview_msg:
            try:
                review_msg = await preview_msg.reply(embed=review_embed, view=review_view, mention_author=False)
            except Exception as e:
                print(f"Failed to reply to preview message: {e}")
                review_msg = await review_channel.send(embed=review_embed, view=review_view)
        else:
            review_msg = await review_channel.send(embed=review_embed, view=review_view)
        
        if preview_msg:
            await database.update_pending_post_deletion_preview_msg(pending_id, preview_msg.id)
        await database.update_pending_post_deletion_review_msg(pending_id, review_msg.id)

        await interaction.followup.send(
            "Post has been queued for deletion and sent to the review channel for higher-up approval.",
            ephemeral=True
        )

    async def _get_review_message(self, interaction: discord.Interaction, review_msg_id: int, config: dict):
        if interaction.message and interaction.message.id == review_msg_id:
            return interaction.message
        if interaction.channel:
            try:
                return await interaction.channel.fetch_message(review_msg_id)
            except Exception:
                pass
        review_channel_id = config.get("deletion_review_channel_id") or config.get("staff_commands_channel_id") or 0
        if review_channel_id:
            chan = self.bot.get_channel(review_channel_id)
            if not chan:
                try:
                    chan = await self.bot.fetch_channel(review_channel_id)
                except Exception:
                    chan = None
            if chan:
                try:
                    return await chan.fetch_message(review_msg_id)
                except Exception:
                    pass
        return None

    async def _cleanup_preview_message(self, interaction: discord.Interaction, pending: dict, rev_msg: discord.Message = None):
        preview_msg_id = pending.get("preview_message_id")
        if not preview_msg_id and rev_msg and getattr(rev_msg, "reference", None):
            preview_msg_id = rev_msg.reference.message_id

        if not preview_msg_id:
            return

        channel = None
        if rev_msg and hasattr(rev_msg, "channel") and rev_msg.channel:
            channel = rev_msg.channel
        elif interaction.channel:
            channel = interaction.channel
        else:
            config = await database.get_guild_config(interaction.guild_id or (rev_msg.guild.id if rev_msg and rev_msg.guild else 0))
            review_channel_id = config.get("deletion_review_channel_id") or config.get("staff_commands_channel_id") or 0
            if review_channel_id:
                channel = self.bot.get_channel(review_channel_id)
                if not channel:
                    try:
                        channel = await self.bot.fetch_channel(review_channel_id)
                    except Exception:
                        channel = None

        if not channel:
            return

        try:
            preview_msg = await channel.fetch_message(preview_msg_id)
            await preview_msg.delete()
        except discord.NotFound:
            pass
        except Exception as e:
            print(f"Failed to delete preview message {preview_msg_id}: {e}")

    async def cancel_pending_deletion(self, interaction: discord.Interaction, pending: dict, reason: str = "Original post was already deleted from chat."):
        pending_id = pending["id"]
        # Clean up temporary attachments
        if pending.get("attachments"):
            database._delete_files_for_attachments(pending["attachments"])

        # Update database status
        await database.update_pending_post_deletion_status(pending_id, "cancelled", reject_reason=reason)

        # Update review card in review channel
        config = await database.get_guild_config(interaction.guild_id or 0)
        review_msg_id = pending.get("review_message_id")
        rev_msg = None
        if review_msg_id:
            rev_msg = await self._get_review_message(interaction, review_msg_id, config)
            if rev_msg and rev_msg.embeds:
                emb = rev_msg.embeds[0]
                emb.color = discord.Color.dark_grey()
                emb.title = "Pending Post Deletion [CANCELLED]"
                now_ts = int(datetime.now(timezone.utc).timestamp())
                actioned_val = f"Cancelled on <t:{now_ts}:f>\n**Reason:** {reason}"
                emb.add_field(name="Actioned", value=actioned_val, inline=False)
                try:
                    await rev_msg.edit(embed=emb, view=None)
                except Exception as e:
                    print(f"Could not update review message: {e}")

        await self._cleanup_preview_message(interaction, pending, rev_msg)

        await interaction.followup.send(
            f"The request has been cancelled: {reason} No warning was issued.",
            ephemeral=True
        )

    async def approve_pending_deletion(self, interaction: discord.Interaction, pending_id: int):
        pending = await database.get_pending_post_deletion(pending_id)
        if not pending:
            await interaction.response.send_message("Pending deletion request not found.", ephemeral=True)
            return

        if pending.get("status") != "pending":
            st = pending.get("status", "actioned")
            config = await database.get_guild_config(interaction.guild_id or 0)
            review_msg_id = pending.get("review_message_id")
            if review_msg_id:
                rev_msg = await self._get_review_message(interaction, review_msg_id, config)
                if rev_msg and rev_msg.embeds:
                    emb = rev_msg.embeds[0]
                    is_corr = (st == "approved_with_correction") or (bool(pending.get("original_reason")) and pending.get("original_reason") != pending.get("reason"))
                    if st in ("approved", "approved_with_correction"):
                        emb.color = discord.Color.green()
                        emb.title = "Pending Post Deletion [APPROVED WITH CORRECTION]" if is_corr else "Pending Post Deletion [APPROVED]"
                    elif st == "rejected":
                        emb.color = discord.Color.red()
                        emb.title = "Pending Post Deletion [REJECTED]"
                    elif st == "cancelled":
                        emb.color = discord.Color.dark_grey()
                        emb.title = "Pending Post Deletion [CANCELLED]"
                    try:
                        await rev_msg.edit(embed=emb, view=None)
                    except Exception:
                        pass
            await interaction.response.send_message(f"This request has already been actioned ({st}).", ephemeral=True)
            return

        # Atomically claim request to prevent concurrent approval/rejection races
        if not await database.claim_pending_post_deletion(pending_id):
            await interaction.response.send_message("This request is already being processed or has been actioned.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        config = await database.get_guild_config(interaction.guild_id or 0)
        notice_channel_id = config.get("staff_notice_channel_id") or 0
        log_channel_id = config.get("staff_log_channel_id") or 0

        # 1. Fetch and delete the message in target channel
        channel_id = pending["channel_id"]
        message_id = pending["message_id"]
        channel = self.bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                channel = None

        if not channel:
            await self.cancel_pending_deletion(interaction, pending, reason="Original channel no longer exists.")
            return

        target_message = None
        target_attachments = []
        try:
            target_message = await channel.fetch_message(message_id)
            target_attachments = list(target_message.attachments)
            if hasattr(target_message, "message_snapshots") and target_message.message_snapshots:
                for snapshot in target_message.message_snapshots:
                    if hasattr(snapshot, "attachments") and snapshot.attachments:
                        target_attachments.extend(snapshot.attachments)
            await target_message.delete()
        except discord.NotFound:
            await self.cancel_pending_deletion(interaction, pending, reason="Original post was already deleted from chat.")
            return
        except discord.HTTPException as e:
            await database.update_pending_post_deletion_status(pending_id, "pending")
            err_msg = f"Failed to delete the message: {e}"
            if e.code == 50013:
                err_msg += f"\n\n**Note:** The bot is missing the `Manage Messages` permission in <#{channel_id}>. Please grant permissions and try again."
            await interaction.followup.send(err_msg, ephemeral=True)
            return
        except Exception as e:
            await database.update_pending_post_deletion_status(pending_id, "pending")
            print(f"Error deleting target message {message_id}: {e}")
            await interaction.followup.send(f"An unexpected error occurred while deleting the message: {e}", ephemeral=True)
            return

        # 2. Post warning notice in staff-notice
        notice_channel = self.bot.get_channel(notice_channel_id)
        if not notice_channel and notice_channel_id:
            try:
                notice_channel = await asyncio.wait_for(self.bot.fetch_channel(notice_channel_id), timeout=5.0)
            except Exception:
                pass

        author_id = pending["author_id"]
        reason = pending["reason"]
        notice_msg = None
        if notice_channel:
            try:
                allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
                notice_content = f"<@{author_id}> {reason}"
                if len(notice_content) > 2000:
                    notice_content = notice_content[:1997] + "..."
                notice_msg = await notice_channel.send(content=notice_content, allowed_mentions=allowed_mentions)
            except Exception as e:
                print(f"Error sending notice message: {e}")

        # 3. Add warning to database (crediting person who marked it, with marked_at timestamp)
        warn_channel_id = notice_channel_id if notice_msg else channel_id
        warn_message_id = notice_msg.id if notice_msg else 0
        
        marked_at_str = pending["marked_at"]
        marked_dt = None
        warned_at_formatted = None
        try:
            marked_dt = datetime.fromisoformat(marked_at_str.replace("Z", "+00:00"))
            warned_at_formatted = marked_dt.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass

        warn_id = await database.add_warning(
            user_id=author_id,
            channel_id=warn_channel_id,
            message_id=warn_message_id,
            message_content=pending["original_content"],
            staff_id=pending["staff_id"],
            reason=reason,
            warned_at=warned_at_formatted,
            post_created_at=pending["post_created_at"],
            guild_id=pending["guild_id"],
            attachments=pending["attachments"]
        )

        # 4. Log to staff log channel
        dashboard_url = os.getenv("DASHBOARD_URL", "localhost:3000")
        if dashboard_url.startswith("http://") or dashboard_url.startswith("https://"):
            base_url = dashboard_url
        else:
            clean_host = dashboard_url.split(":")[0]
            is_ip = clean_host.replace(".", "").isdigit() or clean_host == "localhost"
            protocol = "http" if is_ip else "https"
            base_url = f"{protocol}://{dashboard_url}"

        web_log_url = f"{base_url}/guilds/{pending['guild_id']}/logs/warnings/{warn_id}"
        log_msg = None

        log_channel = self.bot.get_channel(log_channel_id)
        if not log_channel and log_channel_id:
            try:
                log_channel = await asyncio.wait_for(self.bot.fetch_channel(log_channel_id), timeout=5.0)
            except Exception:
                pass

        if log_channel:
            try:
                post_created_dt = datetime.fromisoformat(pending["post_created_at"].replace("Z", "+00:00"))
                orig_ts = int(post_created_dt.timestamp())
            except Exception:
                orig_ts = int(datetime.now(timezone.utc).timestamp())

            try:
                marked_ts = int(marked_dt.timestamp()) if marked_dt else int(datetime.now(timezone.utc).timestamp())
            except Exception:
                marked_ts = int(datetime.now(timezone.utc).timestamp())

            is_corrected = bool(pending.get("original_reason") and pending.get("original_reason") != reason)
            log_title = "Log: Post Removed [Approved with Correction]" if is_corrected else "Log: Post Removed"
            log_embed = discord.Embed(
                title=log_title,
                color=discord.Color.orange()
            )
            log_embed.add_field(name="Warning ID", value=f"#{warn_id}", inline=False)
            log_embed.add_field(name="Staff Member", value=f"<@{pending['staff_id']}> ({pending['staff_id']})", inline=True)
            log_embed.add_field(name="Original Author", value=f"<@{author_id}> ({author_id})", inline=True)
            log_embed.add_field(name="Channel", value=f"<#{channel_id}>", inline=True)
            log_embed.add_field(name="Original Post Created At", value=f"<t:{orig_ts}:f> (<t:{orig_ts}:R>)", inline=True)
            log_embed.add_field(name="Marked For Deletion At", value=f"<t:{marked_ts}:f> (<t:{marked_ts}:R>)", inline=True)
            approved_by_val = f"{interaction.user.mention} ({interaction.user.id}) (with correction)" if is_corrected else f"{interaction.user.mention} ({interaction.user.id})"
            log_embed.add_field(name="Approved By", value=approved_by_val, inline=True)

            reason_text = reason
            if len(reason_text) > 1024:
                reason_text = reason_text[:1021] + "..."
            log_embed.add_field(name="Removal Reason", value=reason_text, inline=False)

            dashboard_url = os.getenv("DASHBOARD_URL", "localhost:3000")
            if dashboard_url.startswith("http://") or dashboard_url.startswith("https://"):
                base_url = dashboard_url
            else:
                clean_host = dashboard_url.split(":")[0]
                is_ip = clean_host.replace(".", "").isdigit() or clean_host == "localhost"
                protocol = "http" if is_ip else "https"
                base_url = f"{protocol}://{dashboard_url}"
            
            log_link = f"[log]({base_url}/guilds/{pending['guild_id']}/logs/warnings/{warn_id})"

            content_snippet = pending["original_content"]
            allowed_len = 1024 - 11 - len(log_link)
            max_len = min(800, allowed_len - 3)
            if len(content_snippet) > max_len:
                content_snippet = content_snippet[:max_len] + "..."

            import json
            saved_attachments = []
            if pending["attachments"]:
                try:
                    saved_attachments = json.loads(pending["attachments"])
                except Exception:
                    pass

            # Resolve attachment URLs
            attachment_urls = []
            if target_attachments:
                attachment_urls = [a.url for a in target_attachments if hasattr(a, "url") and a.url]
            elif saved_attachments:
                attachment_urls = [a["url"] for a in saved_attachments if a.get("url")]

            if attachment_urls:
                log_embed.add_field(
                    name="Original Post Content",
                    value=f"```\n{content_snippet}\n```",
                    inline=False
                )
                attachments_list = "\n".join(attachment_urls)
                allowed_attachments_len = 1024 - 2 - len(log_link) - 3
                if len(attachments_list) > allowed_attachments_len:
                    attachments_list = attachments_list[:allowed_attachments_len] + "..."
                attachments_list += f"\n\n{log_link}"
                log_embed.add_field(name="Attachments", value=attachments_list, inline=False)
            elif saved_attachments:
                log_embed.add_field(
                    name="Original Post Content",
                    value=f"```\n{content_snippet}\n```",
                    inline=False
                )
                att_text = "\n".join([f"`{a['filename']}`" for a in saved_attachments])
                allowed_attachments_len = 1024 - 2 - len(log_link) - 3
                if len(att_text) > allowed_attachments_len:
                    att_text = att_text[:allowed_attachments_len] + "..."
                att_text += f"\n\n{log_link}"
                log_embed.add_field(name="Attachments", value=att_text, inline=False)
            else:
                log_embed.add_field(
                    name="Original Post Content",
                    value=f"```\n{content_snippet}\n```\n{log_link}",
                    inline=False
                )

            try:
                log_msg = await log_channel.send(embed=log_embed)
            except Exception as e:
                print(f"Error sending staff log embed: {e}")

        # 5. DM the user if dm_on_warning is enabled
        author_user = self.bot.get_user(author_id)
        if not author_user:
            try:
                author_user = await self.bot.fetch_user(author_id)
            except Exception:
                pass

        if author_user and not author_user.bot:
            try:
                count = await database.get_warnings_count_last_3_months(author_id, guild_id=pending["guild_id"])
                previous_warnings = await database.get_warnings_last_3_months(author_id, guild_id=pending["guild_id"])
                history = previous_warnings[1:] if len(previous_warnings) > 1 else []
                is_repeat = is_repeated_offense(reason, history)
                
                try:
                    timestamp_str = marked_dt.strftime("%d/%m/%Y") if marked_dt else datetime.now(timezone.utc).strftime("%d/%m/%Y")
                except Exception:
                    timestamp_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")

                embed = discord.Embed(color=discord.Color.red())
                guild = self.bot.get_guild(pending["guild_id"])
                guild_name = guild.name if guild else "this server"
                icon_url = guild.icon.url if guild and guild.icon else self.bot.user.display_avatar.url
                embed.set_author(name=f"{guild_name} | {timestamp_str}", icon_url=icon_url)

                ordinal_num = get_ordinal(count)
                desc = f"### This is your {ordinal_num} verbal warning\n\n"
                suffix = "" if "server" in guild_name.lower() else " server"
                desc += f"You have received a __verbal warning__ in {guild_name}{suffix} for:\n"

                context_reason = reason
                if len(context_reason) > 1200:
                    context_reason = context_reason[:1197] + "..."

                quoted_lines = [f"> {line}" for line in context_reason.split('\n')]
                desc += "\n".join(quoted_lines) + "\n"

                if is_repeat:
                    desc += "\n⚠️ **Note:** You have received a verbal notice for the same offense in the last 3 months. Repeated offenses may lead to stricter actions.\n"
                elif count == 2:
                    desc += "\n⚠️ **This is your 2nd verbal notice in the last 3 months.** Accumulating one more notice will result in further staff action.\n"

                jump_url = notice_msg.jump_url if notice_msg else "https://discord.com"
                desc += f"\n**[Link to verbal warn]({jump_url})**\n\n"
                desc += "-# In case of questions, or if you believe you've been warned by mistake; please contact <@501746915218554881> for appeal or concerns."

                embed.description = desc
                embed.set_footer(text="Verbal warnings expire every 3 months.")

                if config.get("dm_on_warning", 1):
                    await author_user.send(embed=embed)
                    
                    files = []
                    for att in saved_attachments:
                        try:
                            file_path = os.path.join(database.ATTACHMENTS_DIR, att["stored_filename"])
                            if os.path.exists(file_path):
                                files.append(discord.File(file_path, filename=att["filename"]))
                        except Exception:
                            pass

                    content_display = pending["original_content"]
                    if len(content_display) > 2048:
                        content_display = content_display[:2045] + "..."

                    followup_embed = discord.Embed(
                        title="Removed post",
                        description=content_display,
                        color=discord.Color.light_grey()
                    )
                    if files:
                        await author_user.send(embed=followup_embed, files=files)
                    else:
                        await author_user.send(embed=followup_embed)
            except Exception as e:
                print(f"Could not DM user {author_id}: {e}")

        # 6. Update pending record status
        approval_status = "approved_with_correction" if is_corrected else "approved"
        await database.update_pending_post_deletion_status(pending_id, approval_status)

        # 7. Update review card message in staff channel
        review_msg_id = pending.get("review_message_id")
        if review_msg_id:
            rev_msg = await self._get_review_message(interaction, review_msg_id, config)
            if rev_msg and rev_msg.embeds:
                emb = rev_msg.embeds[0]
                emb.color = discord.Color.green()
                now_ts = int(datetime.now(timezone.utc).timestamp())
                if is_corrected:
                    emb.title = "Pending Post Deletion [APPROVED WITH CORRECTION]"
                    actioned_val = f"Approved with correction by {interaction.user.mention} on <t:{now_ts}:f>"
                else:
                    emb.title = "Pending Post Deletion [APPROVED]"
                    actioned_val = f"Approved by {interaction.user.mention} on <t:{now_ts}:f>"
                links = []
                if log_msg:
                    links.append(f"[Discord Log]({log_msg.jump_url})")
                if web_log_url:
                    links.append(f"[Website Log]({web_log_url})")
                if links:
                    actioned_val += f"\n{' • '.join(links)}"
                emb.add_field(name="Actioned", value=actioned_val, inline=False)
                try:
                    await rev_msg.edit(embed=emb, view=None)
                except Exception as e:
                    print(f"Could not update review message: {e}")

        await self._cleanup_preview_message(interaction, pending, rev_msg)

        # 8. Ping the staff member who submitted the deletion request
        staff_id = pending.get("staff_id")
        if staff_id:
            if is_corrected:
                app_embed = discord.Embed(
                    title="Post Deletion Approved (Reason Corrected)",
                    description=f"Your post deletion request was approved by {interaction.user.mention} with a corrected reason.",
                    color=discord.Color.gold()
                )
                app_embed.add_field(name="Submitted Reason", value=pending.get("original_reason") or "None", inline=False)
                app_embed.add_field(name="Corrected Reason", value=reason, inline=False)
            else:
                app_embed = discord.Embed(
                    title="Post Deletion Approved",
                    description=f"Your post deletion request was approved by {interaction.user.mention}.",
                    color=discord.Color.green()
                )
                if reason:
                    reason_val = reason if len(reason) <= 1024 else reason[:1021] + "..."
                    app_embed.add_field(name="Reason", value=reason_val, inline=False)

            ping_text = f"<@{staff_id}>"
            if rev_msg:
                try:
                    await rev_msg.reply(content=ping_text, embed=app_embed)
                except Exception as e:
                    print(f"Could not reply to review message: {e}")
            elif interaction.channel:
                try:
                    await interaction.channel.send(content=ping_text, embed=app_embed)
                except Exception as e:
                    print(f"Could not send approval ping: {e}")

        # 9. Check warning threshold (3 warnings in 3 months)
        await self._check_and_send_threshold_alert(pending["guild_id"], author_id, fallback_staff_id=pending["staff_id"])

        await interaction.followup.send("Post deletion approved and executed successfully.", ephemeral=True)

    async def reject_pending_deletion(self, interaction: discord.Interaction, pending_id: int, reject_reason: str = "No reason provided."):
        pending = await database.get_pending_post_deletion(pending_id)
        if not pending:
            await interaction.response.send_message("Pending deletion request not found.", ephemeral=True)
            return

        if pending.get("status") != "pending":
            st = pending.get("status", "actioned")
            config = await database.get_guild_config(interaction.guild_id or 0)
            review_msg_id = pending.get("review_message_id")
            if review_msg_id:
                rev_msg = await self._get_review_message(interaction, review_msg_id, config)
                if rev_msg and rev_msg.embeds:
                    emb = rev_msg.embeds[0]
                    if st == "rejected":
                        emb.color = discord.Color.red()
                        emb.title = "Pending Post Deletion [REJECTED]"
                    elif st in ("approved", "approved_with_correction"):
                        emb.color = discord.Color.green()
                        is_corr = (st == "approved_with_correction") or (bool(pending.get("original_reason")) and pending.get("original_reason") != pending.get("reason"))
                        emb.title = "Pending Post Deletion [APPROVED WITH CORRECTION]" if is_corr else "Pending Post Deletion [APPROVED]"
                    elif st == "cancelled":
                        emb.color = discord.Color.dark_grey()
                        emb.title = "Pending Post Deletion [CANCELLED]"
                    try:
                        await rev_msg.edit(embed=emb, view=None)
                    except Exception:
                        pass
            await interaction.response.send_message(f"This request has already been actioned ({st}).", ephemeral=True)
            return

        # Atomically claim request to prevent concurrent approval/rejection races
        if not await database.claim_pending_post_deletion(pending_id):
            await interaction.response.send_message("This request is already being processed or has been actioned by someone else.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # 1. Clean up temporary attachments from disk
        if pending.get("attachments"):
            database._delete_files_for_attachments(pending["attachments"])

        # 2. Update status
        staff_id = pending.get("staff_id")
        is_self = (staff_id == interaction.user.id)
        new_status = "cancelled" if is_self else "rejected"
        await database.update_pending_post_deletion_status(pending_id, new_status, reject_reason=reject_reason)

        # 3. Update review card message in staff channel
        config = await database.get_guild_config(interaction.guild_id or 0)
        review_msg_id = pending.get("review_message_id")
        rev_msg = None
        if review_msg_id:
            rev_msg = await self._get_review_message(interaction, review_msg_id, config)
            if rev_msg and rev_msg.embeds:
                emb = rev_msg.embeds[0]
                now_ts = int(datetime.now(timezone.utc).timestamp())
                if is_self:
                    emb.color = discord.Color.dark_grey()
                    emb.title = "Pending Post Deletion [WITHDRAWN]"
                    actioned_val = f"Withdrawn by {interaction.user.mention} on <t:{now_ts}:f>"
                else:
                    emb.color = discord.Color.red()
                    emb.title = "Pending Post Deletion [REJECTED]"
                    actioned_val = f"Rejected by {interaction.user.mention} on <t:{now_ts}:f>"
                if reject_reason and reject_reason != "No reason provided.":
                    actioned_val += f"\n**Reason:** {reject_reason}"
                emb.add_field(name="Actioned", value=actioned_val, inline=False)
                try:
                    await rev_msg.edit(embed=emb, view=None)
                except Exception as e:
                    print(f"Could not update review message: {e}")

        await self._cleanup_preview_message(interaction, pending, rev_msg)

        # 4. Ping the staff member who submitted the deletion request (if not self)
        if staff_id and not is_self:
            reject_embed = discord.Embed(
                title="Post Deletion Rejected",
                description=f"Your post deletion request was rejected by {interaction.user.mention}.",
                color=discord.Color.red()
            )
            if reject_reason:
                reason_val = reject_reason if len(reject_reason) <= 1024 else reject_reason[:1021] + "..."
                reject_embed.add_field(name="Reason", value=reason_val, inline=False)

            ping_text = f"<@{staff_id}>"
            if rev_msg:
                try:
                    await rev_msg.reply(content=ping_text, embed=reject_embed)
                except Exception as e:
                    print(f"Could not reply to review message: {e}")
            elif interaction.channel:
                try:
                    await interaction.channel.send(content=ping_text, embed=reject_embed)
                except Exception as e:
                    print(f"Could not send rejection ping: {e}")

        if is_self:
            await interaction.followup.send("You have withdrawn your post deletion request.", ephemeral=True)
        else:
            await interaction.followup.send("Post deletion request has been rejected with no post deletion or log.", ephemeral=True)

    async def edit_pending_deletion_reason(self, interaction: discord.Interaction, pending_id: int):
        pending = await database.get_pending_post_deletion(pending_id)
        if not pending:
            await interaction.response.send_message("Pending deletion request not found.", ephemeral=True)
            return

        if pending.get("status") != "pending":
            await interaction.response.send_message("This request is no longer pending.", ephemeral=True)
            return

        reasons_db = await database.get_all_verbal_reasons(interaction.guild_id or 0)
        if not reasons_db:
            await interaction.response.send_message("No verbal reasons configured in the database.", ephemeral=True)
            return

        channel_mention = f"<#{pending['channel_id']}>"
        view = EditPendingReasonView(EditPendingReasonSelect(pending_id, self, reasons_db, channel_mention))
        await interaction.response.send_message("Select a new removal reason:", view=view, ephemeral=True)

    async def apply_edited_reason(self, interaction: discord.Interaction, pending_id: int, new_reason: str):
        pending = await database.get_pending_post_deletion(pending_id)
        if not pending or pending.get("status") != "pending":
            await interaction.response.send_message("Request is no longer pending.", ephemeral=True)
            return

        await database.update_pending_post_deletion_reason(pending_id, new_reason)

        # Edit review embed
        config = await database.get_guild_config(interaction.guild_id or 0)
        review_msg_id = pending.get("review_message_id")
        if review_msg_id:
            rev_msg = await self._get_review_message(interaction, review_msg_id, config)
            if rev_msg and rev_msg.embeds:
                emb = rev_msg.embeds[0]
                reason_text = new_reason
                if len(reason_text) > 1024:
                    reason_text = reason_text[:1021] + "..."
                updated = False
                for idx, field in enumerate(emb.fields):
                    if field.name == "Removal Reason":
                        emb.set_field_at(idx, name="Removal Reason", value=reason_text, inline=False)
                        updated = True
                        break
                if not updated:
                    emb.add_field(name="Removal Reason", value=reason_text, inline=False)
                try:
                    await rev_msg.edit(embed=emb)
                except Exception as e:
                    print(f"Could not update review message reason: {e}")

        msg_text = f"Updated reason to:\n> {new_reason}"
        if interaction.response.is_done():
            await interaction.followup.send(msg_text, ephemeral=True)
        else:
            if interaction.type == discord.InteractionType.component:
                await interaction.response.edit_message(content=msg_text, view=None)
            else:
                await interaction.response.send_message(msg_text, ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component and not interaction.response.is_done():
            custom_id = interaction.data.get("custom_id", "")
            if custom_id.startswith("pending_del_"):
                parts = custom_id.split(":", 1)
                if len(parts) == 2:
                    action, pending_id_str = parts
                    try:
                        pending_id = int(pending_id_str)
                    except ValueError:
                        return
                    
                    config = await database.get_guild_config(interaction.guild_id or 0)
                    if not is_higher_up(interaction.user, config):
                        await interaction.response.send_message("Only Moderators and above can review pending deletions.", ephemeral=True)
                        return

                    if await database.is_user_on_training_wheels(interaction.guild_id or 0, interaction.user.id, config=config):
                        await interaction.response.send_message("Staff on training wheels cannot review pending deletions.", ephemeral=True)
                        return

                    if action == "pending_del_approve":
                        await self.approve_pending_deletion(interaction, pending_id)
                    elif action == "pending_del_edit":
                        await self.edit_pending_deletion_reason(interaction, pending_id)
                    elif action == "pending_del_reject":
                        modal = RejectDeletionModal(pending_id, self)
                        await interaction.response.send_modal(modal)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bot messages
        if message.author.bot:
            return
            
        config = await database.get_guild_config(message.guild.id if message.guild else 0)
        notice_channel_id = config.get("staff_notice_channel_id") or 0
        commands_channel_id = config.get("staff_commands_channel_id") or 0
        log_channel_id = config.get("staff_log_channel_id") or 0

        # Check if the message is in the staff-notice channel
        if message.channel.id != notice_channel_id:
            return
            
        # Check for user mentions
        if not message.mentions:
            return
            
        commands_channel = self.bot.get_channel(commands_channel_id)
        if not commands_channel:
            try:
                commands_channel = await asyncio.wait_for(self.bot.fetch_channel(commands_channel_id), timeout=5.0)
            except Exception:
                pass
                
        log_channel = self.bot.get_channel(log_channel_id)
        if not log_channel and log_channel_id:
            try:
                log_channel = await asyncio.wait_for(self.bot.fetch_channel(log_channel_id), timeout=5.0)
            except Exception:
                pass
        
        for user in message.mentions:
            if user.bot:
                continue
                
            all_attachments = list(message.attachments)
            if hasattr(message, "message_snapshots") and message.message_snapshots:
                for snapshot in message.message_snapshots:
                    if hasattr(snapshot, "attachments") and snapshot.attachments:
                        all_attachments.extend(snapshot.attachments)

            import json
            import uuid
            import os
            saved_attachments = []
            for a in all_attachments:
                try:
                    ext = os.path.splitext(a.filename)[1]
                    unique_filename = f"{uuid.uuid4()}{ext}"
                    file_path = os.path.join(database.ATTACHMENTS_DIR, unique_filename)
                    await a.save(file_path)
                    saved_attachments.append({
                        "filename": a.filename,
                        "stored_filename": unique_filename
                    })
                except Exception as e:
                    print(f"Failed to download/save attachment {a.filename}: {e}")
                    
            attachments_data = json.dumps(saved_attachments) if saved_attachments else None

            original_content = "(none)"
            if hasattr(message, "message_snapshots") and message.message_snapshots:
                snapshot_contents = []
                for snapshot in message.message_snapshots:
                    snap_txt = snapshot.content or "*No text content*"
                    snapshot_contents.append(f"(Forwarded Message) {snap_txt}")
                if snapshot_contents:
                    original_content = "\n\n".join(snapshot_contents)

            # Add warning to database (saving message content)
            warn_id = await database.add_warning(
                user_id=user.id,
                channel_id=message.channel.id,
                message_id=message.id,
                message_content=original_content,
                staff_id=message.author.id,
                reason=message.content,
                post_created_at=message.created_at.isoformat(),
                guild_id=message.guild.id if message.guild else None,
                attachments=attachments_data
            )
            
            # Log to staff log channel
            if log_channel:
                orig_ts = int(message.created_at.timestamp())
                log_embed = discord.Embed(
                    title="Log: Verbal Notice Issued",
                    color=discord.Color.orange()
                )
                log_embed.add_field(name="Warning ID", value=f"#{warn_id}", inline=False)
                log_embed.add_field(name="Staff Member", value=f"{message.author.mention} ({message.author.id})", inline=True)
                log_embed.add_field(name="Original Author", value=f"{user.mention} ({user.id})", inline=True)
                log_embed.add_field(name="Channel", value=get_channel_mention(message.channel), inline=True)
                log_embed.add_field(name="Warning Issued At", value=f"<t:{orig_ts}:f> (<t:{orig_ts}:R>)", inline=True)
                
                reason_text = message.content
                if len(reason_text) > 1024:
                    reason_text = reason_text[:1021] + "..."
                log_embed.add_field(name="Warning Reason", value=reason_text, inline=False)
                
                dashboard_url = os.getenv("DASHBOARD_URL", "localhost:3000")
                if dashboard_url.startswith("http://") or dashboard_url.startswith("https://"):
                    base_url = dashboard_url
                else:
                    clean_host = dashboard_url.split(":")[0]
                    is_ip = clean_host.replace(".", "").isdigit() or clean_host == "localhost"
                    protocol = "http" if is_ip else "https"
                    base_url = f"{protocol}://{dashboard_url}"
                
                log_link = f"[log]({base_url}/guilds/{message.guild.id if message.guild else 0}/logs/warnings/{warn_id})"
                
                # Format original post content to fit under 1024 (11 chars for ```\n\n```\n, and length of log_link)
                reason_desc = original_content
                allowed_desc_len = 1024 - 11 - len(log_link) - 3 # 3 for "..."
                if len(reason_desc) > allowed_desc_len:
                    reason_desc = reason_desc[:allowed_desc_len] + "..."
                log_embed.add_field(
                    name="Original Post Content",
                    value=f"```\n{reason_desc}\n```\n{log_link}",
                    inline=False
                )
                
                if all_attachments:
                    attachments_list = "\n".join([a.url for a in all_attachments])
                    allowed_attachments_len = 1024 - 3 # 3 for "..."
                    if len(attachments_list) > allowed_attachments_len:
                        attachments_list = attachments_list[:allowed_attachments_len] + "..."
                    log_embed.add_field(name="Notice Attachments", value=attachments_list, inline=False)

                try:
                    await log_channel.send(embed=log_embed)
                except Exception as e:
                    print(f"Error sending manual warn log embed: {e}")
            
            # Check warning count
            count = await database.get_warnings_count_last_3_months(user.id, guild_id=message.guild.id if message.guild else None)
            
            # DM the user
            try:
                previous_warnings = await database.get_warnings_last_3_months(user.id, guild_id=message.guild.id if message.guild else None)
                history = previous_warnings[1:] if len(previous_warnings) > 1 else []
                
                is_repeat = is_repeated_offense(message.content, history)
                timestamp_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")
                
                embed = discord.Embed(color=discord.Color.red())
                guild = message.guild
                guild_name = guild.name if guild else "this server"
                icon_url = guild.icon.url if guild and guild.icon else self.bot.user.display_avatar.url
                embed.set_author(name=f"{guild_name} | {timestamp_str}", icon_url=icon_url)
                
                ordinal_num = get_ordinal(count)
                desc = f"### This is your {ordinal_num} verbal warning\n\n"
                suffix = "" if "server" in guild_name.lower() else " server"
                desc += f"You have received a __verbal warning__ in {guild_name}{suffix} for:\n\n"
                
                context_reason = message.content
                if len(context_reason) > 1200:
                    context_reason = context_reason[:1197] + "..."
                
                quoted_lines = []
                unbold_rest = False
                for line in context_reason.split('\n'):
                    if "Note:" in line:
                        unbold_rest = True
                        
                    if unbold_rest:
                        quoted_lines.append(f"> {line}")
                    else:
                        quoted_lines.append(f"> {line}")
                desc += "\n".join(quoted_lines) + "\n"
                
                if is_repeat:
                    desc += "\n⚠️ **Note:** You have previously received a verbal notice for this same offense within the last 3 months. Repeatedly violating the same rules may lead to stricter actions.\n"
                elif count == 2:
                    desc += "\n⚠️ **This is your 2nd verbal notice in the last 3 months.** Accumulating one more notice will result in further staff action.\n"
                
                desc += f"\n-# **[View your verbal warning here.]({message.jump_url})**\n\n"
                desc += "-# In case of questions, or if you believe you've been warned by mistake; please contact  <@501746915218554881>"
                
                embed.description = desc
                embed.set_footer(text="Keep in mind that verbal warnings reset every 3 months.")
                
                guild_config = await database.get_guild_config(guild.id if guild else 0)
                if guild_config.get("dm_on_warning", 1):
                    await user.send(embed=embed)
            except Exception as e:
                print(f"Could not DM user {user.id}: {e}")
            
            if count >= 3 and commands_channel:
                last_warnings = await database.get_warnings_last_3_months(user.id, guild_id=guild.id if guild else None)
                last_warnings.reverse()
                
                formatted_warnings = []
                for warn_id, content, warned_at in last_warnings:
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
                            prefix = "- " if sub_bullet_idx == 0 else "   - "
                            formatted_lines.append(prefix + line[2:])
                            sub_bullet_idx += 1
                        else:
                            formatted_lines.append(line)
                    
                    content_str = "\n".join(formatted_lines)
                    formatted_warnings.append(f"**ID: {warn_id}** ({time_str}) {content_str}")
                
                warnings_str = ""
                truncated_any = False
                for w in formatted_warnings:
                    if len(warnings_str) + len(w) + 2 > 3500:
                        truncated_any = True
                        break
                    if warnings_str:
                        warnings_str += "\n" + w
                    else:
                        warnings_str = w
                
                if truncated_any:
                    warnings_str += "\n*(Older warnings truncated to fit Discord message limits...)*"
                
                # Ping the last staff member who warned them instead of Carrot
                last_staff_id = await database.get_last_warning_staff_id_last_3_months(user.id, guild_id=guild.id if guild else None)
                staff_mention = f"<@{last_staff_id}>" if last_staff_id else message.author.mention
                
                embed = discord.Embed(
                    title="⚠️ Warning Threshold Reached",
                    description=f"User {user.mention} ({user.id}) has accumulated **{count}** verbal notice(s) within 3 months. Please take immediate action.\n\n**Recent Warning History:**\n{warnings_str}",
                    color=discord.Color.red()
                )
                
                allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
                await commands_channel.send(
                    content=f"{staff_mention}",
                    embed=embed,
                    allowed_mentions=allowed_mentions
                )

    @commands.command(name="verbals")
    async def verbals(self, ctx, user: discord.User = None):
        # Allow checking either self or specific user
        target_user = user or ctx.author
        
        config = await database.get_guild_config(ctx.guild.id if ctx.guild else 0)
        notice_channel_id = config.get("staff_notice_channel_id") or 0
        
        guild_id = ctx.guild.id if ctx.guild else None
        total_count = await database.get_warnings_count(target_user.id, guild_id)
        
        # Build paginated view
        view = WarningsPaginationView(target_user, total_count, database.get_warnings_paginated, guild_id or "@me", notice_channel_id)
        embed = await view.get_page_embed()
        view.message = await ctx.send(embed=embed, view=view)

    @commands.command(name="delverbal")
    async def delverbal(self, ctx, warning_id: int, *, reason: str):
        config = await database.get_guild_config(ctx.guild.id if ctx.guild else 0)
        staff_role_ids = [config.get("team_leader_role_id"), config.get("moderator_role_id"), config.get("trial_moderator_role_id")]
        notice_channel_id = config.get("staff_notice_channel_id") or 0
        log_channel_id = config.get("staff_log_channel_id") or 0
        
        # Restrict command to users with the specific staff roles (bypassed for developer and admins)
        is_admin = ctx.author.guild_permissions.administrator if ctx.guild else False
        if ctx.author.id != 255174440005009408:
            if not ctx.guild or (not is_admin and not any(role.id in staff_role_ids for role in ctx.author.roles)):
                await ctx.send("You do not have the required staff role to use this command.")
                return

        # Fetch the warning first
        warn = await database.get_warning_by_id(warning_id)
        if not warn:
            await ctx.send(f"Verbal ID #{warning_id} was not found in the database.")
            return

        # Delete the message in #staff-notice
        notice_channel = self.bot.get_channel(notice_channel_id)
        if not notice_channel:
            try:
                notice_channel = await asyncio.wait_for(self.bot.fetch_channel(notice_channel_id), timeout=5.0)
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
        log_channel = self.bot.get_channel(log_channel_id)
        if not log_channel:
            try:
                log_channel = await asyncio.wait_for(self.bot.fetch_channel(log_channel_id), timeout=5.0)
            except Exception:
                pass
        
        if log_channel:
            log_embed = discord.Embed(
                title="Log: Verbal Notice Deleted/Revoked",
                color=discord.Color.red()
            )
            log_embed.add_field(name="Staff Member", value=f"{ctx.author.mention} ({ctx.author.id})", inline=True)
            log_embed.add_field(name="Target User", value=f"<@{warn['user_id']}> ({warn['user_id']})", inline=True)
            log_embed.add_field(name="Verbal ID", value=f"#{warning_id}", inline=True)
            log_embed.add_field(name="Revoke Reason", value=reason, inline=False)
            log_embed.add_field(name="Original Reason", value=warn['reason'] or warn['message_content'] or "*None*", inline=False)
            
            await log_channel.send(embed=log_embed)

        # DM the user about the revocation
        try:
            target_user = self.bot.get_user(warn['user_id'])
            if not target_user:
                target_user = await self.bot.fetch_user(warn['user_id'])
                
            if target_user and not target_user.bot:
                dm_embed = discord.Embed(
                    title="Verbal Notice Revoked",
                    description=f"One of your verbal warns (ID #{warning_id}) have been revoked for the following reason:\n\n> **{reason}**",
                    color=discord.Color.green()
                )
                await target_user.send(embed=dm_embed)
        except Exception as e:
            print(f"Failed to DM user {warn['user_id']} about revoked warning: {e}")

        await ctx.send(f"Successfully deleted verbal notice with ID #{warning_id} and notified the user.")

    @commands.command(name="editverbal")
    async def editverbal(self, ctx, warning_id: int):
        config = await database.get_guild_config(ctx.guild.id if ctx.guild else 0)
        
        # Restrict command to administrators (bypassed for developer)
        is_admin = ctx.author.guild_permissions.administrator if ctx.guild else False
        if ctx.author.id != 255174440005009408 and not is_admin:
            await ctx.send("You do not have the required administrator permissions to use this command.")
            return

        # Fetch the warning first
        warn = await database.get_warning_by_id(warning_id)
        if not warn:
            await ctx.send(f"Verbal ID #{warning_id} was not found in the database.")
            return

        # Fetch pre-configured reasons
        reasons_db = await database.get_all_verbal_reasons(ctx.guild.id if ctx.guild else 0)
        if not reasons_db:
            await ctx.send("No verbal reasons configured in the database.")
            return

        # Send dropdown select menu
        view = RemovalDropdownView(EditVerbalReasonSelect(warning_id, self, reasons_db, ctx.guild.id if ctx.guild else 0), timeout=180)
        msg = await ctx.send("Select a new reason for this verbal warning:", view=view)
        view.message = msg

    async def execute_verbal_edit(self, interaction: discord.Interaction, warning_id: int, new_reason: str):
        config = await database.get_guild_config(interaction.guild_id or 0)
        notice_channel_id = config.get("staff_notice_channel_id") or 0
        log_channel_id = config.get("staff_log_channel_id") or 0

        warn = await database.get_warning_by_id(warning_id)
        if not warn:
            await interaction.followup.send(f"Verbal ID #{warning_id} was not found in the database.", ephemeral=True)
            return

        old_reason = warn['reason']

        # Update warning in database
        async with database.aiosqlite.connect(database.DB_NAME) as db:
            await db.execute("UPDATE warnings SET reason = ? WHERE id = ?", (new_reason, warning_id))
            await db.commit()

        # Update notice in staff-notice
        notice_channel = self.bot.get_channel(notice_channel_id)
        if not notice_channel and notice_channel_id:
            try:
                notice_channel = await asyncio.wait_for(self.bot.fetch_channel(notice_channel_id), timeout=5.0)
            except Exception:
                pass

        if notice_channel and warn['message_id']:
            try:
                msg = await notice_channel.fetch_message(warn['message_id'])
                allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
                await msg.edit(content=f"<@{warn['user_id']}> {new_reason}", allowed_mentions=allowed_mentions)
            except Exception as e:
                print(f"Failed to edit staff notice message {warn['message_id']}: {e}")

        # Send updated DM to the user
        try:
            target_user = self.bot.get_user(warn['user_id'])
            if not target_user:
                target_user = await self.bot.fetch_user(warn['user_id'])
            if target_user and not target_user.bot:
                dm_embed = discord.Embed(
                    title="Verbal Warning Reason Updated",
                    description=(
                        f"Hello, the reason for your post removal (Warning ID #{warning_id}) has been updated.\n\n"
                        f"**New Reason:** {new_reason}\n\n"
                        f"**Original Content:**\n```\n{warn['message_content']}\n```"
                    ),
                    color=discord.Color.orange()
                )
                await target_user.send(embed=dm_embed)
        except Exception as e:
            print(f"Failed to DM user {warn['user_id']} about updated warning reason: {e}")

        # Log it in staff log channel
        log_channel = self.bot.get_channel(log_channel_id)
        if not log_channel and log_channel_id:
            try:
                log_channel = await asyncio.wait_for(self.bot.fetch_channel(log_channel_id), timeout=5.0)
            except Exception:
                pass

        if log_channel:
            log_embed = discord.Embed(
                title="Log: Verbal Warning Edited",
                description=f"Admin {interaction.user.mention} has edited the reason for Verbal ID #{warning_id}.",
                color=discord.Color.blue()
            )
            log_embed.add_field(name="User", value=f"<@{warn['user_id']}> ({warn['user_id']})", inline=True)
            log_embed.add_field(name="Old Reason", value=old_reason, inline=False)
            log_embed.add_field(name="New Reason", value=new_reason, inline=False)
            
            try:
                await log_channel.send(embed=log_embed)
            except Exception as e:
                print(f"Failed to send log embed: {e}")

        try:
            await interaction.message.delete()
        except Exception:
            pass

        await interaction.followup.send(f"Successfully updated verbal notice with ID #{warning_id} and notified the user.", ephemeral=True)

    @commands.command(name="verbalby")
    async def verbalby(self, ctx, staff: discord.User = None):
        config = await database.get_guild_config(ctx.guild.id if ctx.guild else 0)
        staff_role_ids = [config.get("team_leader_role_id"), config.get("moderator_role_id"), config.get("trial_moderator_role_id")]
        notice_channel_id = config.get("staff_notice_channel_id") or 0
        
        # Restrict command to users with the specific staff roles (bypassed for developer and admins)
        is_admin = ctx.author.guild_permissions.administrator if ctx.guild else False
        if ctx.author.id != 255174440005009408:
            if not ctx.guild or (not is_admin and not any(role.id in staff_role_ids for role in ctx.author.roles)):
                await ctx.send("You do not have the required staff role to use this command.")
                return

        target_staff = staff or ctx.author
        guild_id = ctx.guild.id if ctx.guild else None
        total_count = await database.get_warnings_by_staff_count(target_staff.id, guild_id)
        
        # Build paginated view
        view = StaffWarningsPaginationView(target_staff, total_count, database.get_warnings_by_staff_paginated, guild_id or "@me", notice_channel_id)
        embed = await view.get_page_embed()
        view.message = await ctx.send(embed=embed, view=view)

    @commands.command(name="sync_warnings")
    async def sync_warnings(self, ctx):
        config = await database.get_guild_config(ctx.guild.id if ctx.guild else 0)
        notice_channel_id = config.get("staff_notice_channel_id") or 0
        
        # Restrict command to administrators (bypassed for developer)
        if ctx.author.id != 255174440005009408:
            if not ctx.guild or not ctx.author.guild_permissions.administrator:
                await ctx.send("You do not have the required administrator permissions to use this command.")
                return
        notice_channel = self.bot.get_channel(notice_channel_id)
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
                    
                    all_attachments = list(message.attachments)
                    if hasattr(message, "message_snapshots") and message.message_snapshots:
                        for snapshot in message.message_snapshots:
                            if hasattr(snapshot, "attachments") and snapshot.attachments:
                                all_attachments.extend(snapshot.attachments)

                    import json
                    import uuid
                    import os
                    saved_attachments = []
                    for a in all_attachments:
                        try:
                            ext = os.path.splitext(a.filename)[1]
                            unique_filename = f"{uuid.uuid4()}{ext}"
                            file_path = os.path.join(database.ATTACHMENTS_DIR, unique_filename)
                            await a.save(file_path)
                            saved_attachments.append({
                                "filename": a.filename,
                                "stored_filename": unique_filename
                            })
                        except Exception as e:
                            print(f"Failed to download/save attachment {a.filename}: {e}")
                            
                    attachments_data = json.dumps(saved_attachments) if saved_attachments else None

                    await database.add_warning(
                        user_id=user.id, 
                        channel_id=message.channel.id, 
                        message_id=message.id, 
                        message_content="(none)",
                        staff_id=staff_id,
                        reason=message.content,
                        warned_at=warned_at_str,
                        post_created_at=message.created_at.isoformat(),
                        guild_id=message.guild.id if message.guild else None,
                        attachments=attachments_data
                    )
                    imported_count += 1

        await status_msg.edit(content=f"Sync complete! Imported {imported_count} historical verbal notices into the database.")

    @app_commands.command(name="verbal", description="Manage dynamic verbal warning reasons (Team Leaders only)")
    @app_commands.describe(action="Add, Edit, or Remove", reason="Reason to edit/remove, or name for new reason")
    @app_commands.choices(action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Edit", value="edit"),
        app_commands.Choice(name="Remove", value="remove"),
    ])
    async def manage_verbal(self, interaction: discord.Interaction, action: str, reason: str = None):
        config = await database.get_guild_config(interaction.guild_id or 0)
        team_leader_role_id = config.get("team_leader_role_id") or 0
        
        is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False
        if interaction.user.id != 255174440005009408 and not is_admin and not any(role.id == team_leader_role_id for role in interaction.user.roles):
            await interaction.response.send_message("Only Team Leaders, Server Administrators, and the superuser can manage verbal reasons.", ephemeral=True)
            return

        if action == "add":
            modal = VerbalReasonModal("add", reason_id=reason)
            await interaction.response.send_modal(modal)
            
        elif action == "edit":
            if not reason:
                return await interaction.response.send_message("Please select a reason to edit from the autocomplete list.", ephemeral=True)
            data = await database.get_verbal_reason(interaction.guild_id or 0, reason)
            if not data:
                return await interaction.response.send_message(f"Reason `{reason}` not found.", ephemeral=True)
            modal = VerbalReasonModal("edit", reason_id=reason, default_label=data['label'], default_text=data['text'])
            await interaction.response.send_modal(modal)
            
        elif action == "remove":
            if not reason:
                return await interaction.response.send_message("Please select a reason to remove from the autocomplete list.", ephemeral=True)
            data = await database.get_verbal_reason(interaction.guild_id or 0, reason)
            if not data:
                return await interaction.response.send_message(f"Reason `{reason}` not found.", ephemeral=True)
            
            embed = discord.Embed(title="Confirm Removal", description=f"Are you sure you want to remove the verbal reason `{reason}`?\n\n**Label:** {data['label']}\n**Text:** {data['text'][:1000]}", color=discord.Color.red())
            view = VerbalPreviewView("remove", reason, data['label'], data['text'], interaction)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @manage_verbal.autocomplete("reason")
    async def verbal_autocomplete(self, interaction: discord.Interaction, current: str):
        action = interaction.namespace.action
        if action in ["edit", "remove"]:
            reasons = await database.get_all_verbal_reasons(interaction.guild_id or 0)
            choices = [app_commands.Choice(name=r['label'][:100], value=r['id'][:100]) for r in reasons if current.lower() in r['label'].lower() or current.lower() in r['id'].lower()][:25]
            return choices
        return []

    trainingwheel = app_commands.Group(name="trainingwheel", description="Manage Training Wheels for post deletions (Mods+)")

    @trainingwheel.command(name="add", description="Add a staff member to training wheels")
    @app_commands.describe(user="The staff member to supervise")
    async def trainingwheel_add(self, interaction: discord.Interaction, user: discord.User):
        config = await database.get_guild_config(interaction.guild_id or 0)
        if not is_higher_up(interaction.user, config):
            await interaction.response.send_message("Only Moderators and above can manage training wheels.", ephemeral=True)
            return

        if await database.is_user_on_training_wheels(interaction.guild_id or 0, interaction.user.id, config=config):
            await interaction.response.send_message("Staff on training wheels cannot manage training wheels.", ephemeral=True)
            return

        await database.set_training_wheel_user(interaction.guild_id or 0, user.id, 1)
        await interaction.response.send_message(
            f"Added {user.mention} ({user.id}) to the Training Wheel list. Their post removals will now be queued for review.",
            ephemeral=True
        )

    @trainingwheel.command(name="remove", description="Remove a staff member from training wheels")
    @app_commands.describe(user="The user to remove from training wheels")
    async def trainingwheel_remove(self, interaction: discord.Interaction, user: discord.User):
        config = await database.get_guild_config(interaction.guild_id or 0)
        if not is_higher_up(interaction.user, config):
            await interaction.response.send_message("Only Moderators and above can manage training wheels.", ephemeral=True)
            return

        if await database.is_user_on_training_wheels(interaction.guild_id or 0, interaction.user.id, config=config):
            await interaction.response.send_message("Staff on training wheels cannot manage training wheels.", ephemeral=True)
            return

        await database.remove_training_wheel_user(interaction.guild_id or 0, user.id)
        await interaction.response.send_message(
            f"Removed {user.mention} ({user.id}) from the Training Wheel list.",
            ephemeral=True
        )

    @trainingwheel.command(name="list", description="List all users on the training wheel list")
    async def trainingwheel_list(self, interaction: discord.Interaction):
        config = await database.get_guild_config(interaction.guild_id or 0)
        if not is_higher_up(interaction.user, config):
            await interaction.response.send_message("Only Moderators and above can manage training wheels.", ephemeral=True)
            return

        if await database.is_user_on_training_wheels(interaction.guild_id or 0, interaction.user.id, config=config):
            await interaction.response.send_message("Staff on training wheels cannot view the training wheel list.", ephemeral=True)
            return

        users = await database.get_training_wheel_users(interaction.guild_id or 0)
        if not users:
            await interaction.response.send_message("No users are currently on the Training Wheel list.", ephemeral=True)
            return

        lines = []
        for u in users:
            ex_count = len(u.get("exempt_channels", []))
            ex_note = f" ({ex_count} exempt)" if ex_count > 0 else " (all supervised)"
            lines.append(f"- <@{u['user_id']}> ({u['user_id']}){ex_note}")

        embed = discord.Embed(
            title="Training Wheel Users",
            description="\n".join(lines),
            color=discord.Color.teal()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    trainingwheel_channel = app_commands.Group(name="channel", description="Manage channel exemptions for training wheels", parent=trainingwheel)

    @trainingwheel_channel.command(name="exempt", description="Allow direct post removals in a specific channel")
    @app_commands.describe(user="The staff member on training wheels", channel="The channel or forum to exempt")
    async def channel_exempt(self, interaction: discord.Interaction, user: discord.User, channel: discord.abc.GuildChannel):
        config = await database.get_guild_config(interaction.guild_id or 0)
        if not is_higher_up(interaction.user, config):
            await interaction.response.send_message("Only Moderators and above can manage training wheels.", ephemeral=True)
            return
        if await database.is_user_on_training_wheels(interaction.guild_id or 0, interaction.user.id, config=config):
            await interaction.response.send_message("Staff on training wheels cannot manage training wheels.", ephemeral=True)
            return

        target_channel_id = getattr(channel, "parent_id", None) or channel.id
        exemptions = await database.get_user_training_wheel_exemptions(interaction.guild_id or 0, user.id)
        cid_str = str(target_channel_id)
        if cid_str not in exemptions:
            exemptions.append(cid_str)
            await database.set_user_training_wheel_exemptions(interaction.guild_id or 0, user.id, exemptions)

        await interaction.response.send_message(
            f"Exempted <#{target_channel_id}> for {user.mention}. They can now remove posts there directly without review.",
            ephemeral=True
        )

    @trainingwheel_channel.command(name="supervise", description="Require review for post removals in a specific channel")
    @app_commands.describe(user="The staff member on training wheels", channel="The channel or forum to supervise")
    async def channel_supervise(self, interaction: discord.Interaction, user: discord.User, channel: discord.abc.GuildChannel):
        config = await database.get_guild_config(interaction.guild_id or 0)
        if not is_higher_up(interaction.user, config):
            await interaction.response.send_message("Only Moderators and above can manage training wheels.", ephemeral=True)
            return
        if await database.is_user_on_training_wheels(interaction.guild_id or 0, interaction.user.id, config=config):
            await interaction.response.send_message("Staff on training wheels cannot manage training wheels.", ephemeral=True)
            return

        target_channel_id = getattr(channel, "parent_id", None) or channel.id
        exemptions = await database.get_user_training_wheel_exemptions(interaction.guild_id or 0, user.id)
        cid_str = str(target_channel_id)
        if cid_str in exemptions:
            exemptions.remove(cid_str)
            await database.set_user_training_wheel_exemptions(interaction.guild_id or 0, user.id, exemptions)

        await interaction.response.send_message(
            f"Removed exemption for <#{target_channel_id}> for {user.mention}. Their removals there now require review.",
            ephemeral=True
        )

    @trainingwheel_channel.command(name="list", description="List active channel exemptions for a staff member")
    @app_commands.describe(user="The staff member to check")
    async def channel_list(self, interaction: discord.Interaction, user: discord.User):
        config = await database.get_guild_config(interaction.guild_id or 0)
        if not is_higher_up(interaction.user, config):
            await interaction.response.send_message("Only Moderators and above can manage training wheels.", ephemeral=True)
            return
        if await database.is_user_on_training_wheels(interaction.guild_id or 0, interaction.user.id, config=config):
            await interaction.response.send_message("Staff on training wheels cannot view training wheel settings.", ephemeral=True)
            return

        exemptions = await database.get_user_training_wheel_exemptions(interaction.guild_id or 0, user.id)
        if not exemptions:
            await interaction.response.send_message(
                f"{user.mention} has no channel exemptions. All channels are currently supervised.",
                ephemeral=True
            )
            return

        lines = [f"- <#{cid}> (`{cid}`)" for cid in exemptions]
        embed = discord.Embed(
            title=f"Channel Exemptions: {user.display_name}",
            description="The following channels allow direct post removals without review:\n\n" + "\n".join(lines),
            color=discord.Color.teal()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="carrothelp")
    async def help_command(self, ctx):
        view = HelpPaginationView()
        embed = view.get_page_embed()
        view.message = await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(WarningTracker(bot))
