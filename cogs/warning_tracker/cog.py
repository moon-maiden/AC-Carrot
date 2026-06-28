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
    HelpPaginationView
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
        if interaction.user.id != 255174440005009408 and not is_admin and not any(role.id in staff_role_ids for role in interaction.user.roles):
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
        resolved_content = original_content
        if not resolved_content and hasattr(message, "message_snapshots") and message.message_snapshots:
            snapshot_contents = []
            for snapshot in message.message_snapshots:
                snap_txt = snapshot.content or "*No text content*"
                snapshot_contents.append(f"(Forwarded Message) {snap_txt}")
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
            
            content_snippet = resolved_content

            if len(content_snippet) > 800:
                content_snippet = content_snippet[:800] + "..."
            
            dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:3000")
            log_link = f"[log](https://{dashboard_url}/guilds/{message.guild.id if message.guild else 0}/logs/warnings/{warn_id})"

            if all_attachments:
                # Add Original Post Content (without link)
                log_embed.add_field(
                    name="Original Post Content",
                    value=f"```\n{content_snippet}\n```",
                    inline=False
                )
                # Add Attachments (with link)
                attachments_list = "\n".join([a.url for a in all_attachments])
                if len(attachments_list) > 950:
                    attachments_list = attachments_list[:950] + "..."
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
                count = await database.get_warnings_count_last_3_months(message.author.id)
                previous_warnings = await database.get_warnings_last_3_months(message.author.id)
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
        count = await database.get_warnings_count_last_3_months(message.author.id)
        if count >= 3:
            guild_config = await database.get_guild_config(message.guild.id if message.guild else 0)
            commands_channel_id = guild_config.get("staff_commands_channel_id") or 0
            commands_channel = self.bot.get_channel(commands_channel_id)
            if not commands_channel and commands_channel_id:
                try:
                    commands_channel = await asyncio.wait_for(self.bot.fetch_channel(commands_channel_id), timeout=5.0)
                except Exception:
                    pass
            if commands_channel:
                last_warnings = await database.get_warnings_last_3_months(message.author.id)
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
                
                # Fetch last staff member who warned this user
                last_staff_id = await database.get_last_warning_staff_id_last_3_months(message.author.id)
                staff_mention = f"<@{last_staff_id}>" if last_staff_id else interaction.user.mention
                
                embed = discord.Embed(
                    title="⚠️ Warning Threshold Reached",
                    description=f"User {message.author.mention} ({message.author.id}) has accumulated **{count}** verbal notice(s) within 3 months. Please take immediate action.\n\n**Recent Warning History:**\n{warnings_str}",
                    color=discord.Color.red()
                )
                
                allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
                await commands_channel.send(
                    content=f"{staff_mention}",
                    embed=embed,
                    allowed_mentions=allowed_mentions
                )

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
                
                dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:3000")
                log_link = f"[log](https://{dashboard_url}/guilds/{message.guild.id if message.guild else 0}/logs/warnings/{warn_id})"
                
                reason_desc = original_content
                if len(reason_desc) > 1000:
                    reason_desc = reason_desc[:997] + "..."
                log_embed.add_field(
                    name="Original Post Content",
                    value=f"```\n{reason_desc}\n```\n{log_link}",
                    inline=False
                )
                
                if all_attachments:
                    attachments_list = "\n".join([a.url for a in all_attachments])
                    if len(attachments_list) > 1024:
                        attachments_list = attachments_list[:1020] + "..."
                    log_embed.add_field(name="Notice Attachments", value=attachments_list, inline=False)

                try:
                    await log_channel.send(embed=log_embed)
                except Exception as e:
                    print(f"Error sending manual warn log embed: {e}")
            
            # Check warning count
            count = await database.get_warnings_count_last_3_months(user.id)
            
            # DM the user
            try:
                previous_warnings = await database.get_warnings_last_3_months(user.id)
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
                last_warnings = await database.get_warnings_last_3_months(user.id)
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
                last_staff_id = await database.get_last_warning_staff_id_last_3_months(user.id)
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
        
        total_count = await database.get_warnings_count(target_user.id)
        
        # Build paginated view
        view = WarningsPaginationView(target_user, total_count, database.get_warnings_paginated, ctx.guild.id if ctx.guild else "@me", notice_channel_id)
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
        total_count = await database.get_warnings_by_staff_count(target_staff.id)
        
        # Build paginated view
        view = StaffWarningsPaginationView(target_staff, total_count, database.get_warnings_by_staff_paginated, ctx.guild.id if ctx.guild else "@me", notice_channel_id)
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

    @commands.command(name="carrothelp")
    async def help_command(self, ctx):
        view = HelpPaginationView()
        embed = view.get_page_embed()
        view.message = await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(WarningTracker(bot))
