from fastapi import FastAPI, HTTPException, Request, Header, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import database
import os
import time
import aiohttp
import discord

app = FastAPI()

from fastapi.responses import JSONResponse
from collections import defaultdict

# Simple sliding window rate limiter (100 requests per minute per IP)
ip_rate_limits = defaultdict(list)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    
    # Clean up old timestamps (older than 60 seconds)
    ip_rate_limits[client_ip] = [ts for ts in ip_rate_limits[client_ip] if now - ts < 60]
    
    if len(ip_rate_limits[client_ip]) > 150:
        return JSONResponse(status_code=429, content={"detail": "Too many requests. Please try again later."})
        
    ip_rate_limits[client_ip].append(now)
    response = await call_next(request)
    return response


# Mount static files for attachments
app.mount("/api/attachments", StaticFiles(directory=database.ATTACHMENTS_DIR), name="attachments")

# Enable CORS for Next.js frontend
dashboard_origins = os.getenv("DASHBOARD_CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=dashboard_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# Reference to the Discord bot client for dynamic username resolution
bot_client = None

# Simple in-memory cache to prevent Discord API rate limiting
user_cache = {}
token_cache = {}
permission_cache = {}


async def log_dashboard_action(guild_id: int, user_id: str, action: str):
    if not bot_client:
        return
    config = await database.get_guild_config(guild_id)
    if not config or not config.get("staff_log_channel_id"):
        return
    channel = bot_client.get_channel(config["staff_log_channel_id"])
    if channel:
        try:
            await channel.send(f"🛡️ **Dashboard Action:** <@{user_id}> {action}")
        except Exception:
            pass

async def get_discord_user_id(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        print(f"[AUTH DEBUG] Missing or invalid Authorization header: {auth_header}")
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token = auth_header.split(" ")[1]
    
    now = time.time()
    if token in token_cache and token_cache[token][1] > now:
        return token_cache[token][0]
    
    async with aiohttp.ClientSession() as session:
        async with session.get("https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {token}"}) as resp:
            if resp.status != 200:
                print(f"[AUTH DEBUG] Discord API rejected token with status {resp.status}")
                text = await resp.text()
                print(f"[AUTH DEBUG] Discord API response: {text}")
                raise HTTPException(status_code=401, detail="Invalid token")
            data = await resp.json()
            user_id = data.get("id")
            token_cache[token] = (user_id, now + 600) # 10 minutes cache
            return user_id

async def get_user_access_level(guild_id: int, user_id: str = Depends(get_discord_user_id)) -> str:
    cache_key = f"{guild_id}_{user_id}"
    now = time.time()
    if cache_key in permission_cache and permission_cache[cache_key][1] > now:
        return permission_cache[cache_key][0]
        
    if not bot_client:
        return "none"
        
    guild = bot_client.get_guild(guild_id)
    if not guild:
        return "none"
        
    member = guild.get_member(int(user_id))
    if not member:
        try:
            member = await guild.fetch_member(int(user_id))
        except discord.NotFound:
            permission_cache[cache_key] = ("none", now + 120)
            return "none"
        except Exception:
            return "none"
            
    is_owner = False
    try:
        is_owner = member.id == guild.owner_id or await bot_client.is_owner(member)
    except Exception as e:
        print(f"[DEBUG] Error checking ownership: {e}")

    if member.guild_permissions.administrator or member.guild_permissions.manage_guild or is_owner:
        permission_cache[cache_key] = ("admin", now + 120)
        return "admin"
        
    # Now check bot roles vs config
    config = await database.get_guild_config(guild_id)
    if config:
        role_ids = [str(r.id) for r in member.roles]
        
        print(f"[DEBUG] User {user_id} roles in {guild_id}: {role_ids}")
        print(f"[DEBUG] Configured Team Leader: {config.get('team_leader_role_id')} | Mod: {config.get('moderator_role_id')} | Trial: {config.get('trial_moderator_role_id')}")
        
        team_leader_id = str(config.get("team_leader_role_id"))
        mod_role_id = str(config.get("moderator_role_id"))
        trial_mod_id = str(config.get("trial_moderator_role_id"))
        
        # Check team leader
        if team_leader_id in role_ids:
            print(f"[DEBUG] User granted admin via team_leader_role_id")
            permission_cache[cache_key] = ("admin", now + 120)
            return "admin"
            
        # Check moderator/trial
        if mod_role_id in role_ids or trial_mod_id in role_ids:
            print(f"[DEBUG] User granted view via mod/trial role")
            permission_cache[cache_key] = ("view", now + 120)
            return "view"
            
    print(f"[DEBUG] User {user_id} denied access to {guild_id}. Returned none.")
    permission_cache[cache_key] = ("none", now + 120)
    return "none"

async def requires_view_access(guild_id: int, access_level: str = Depends(get_user_access_level)):
    if access_level not in ["admin", "view"]:
        raise HTTPException(status_code=403, detail="Forbidden: You do not have access to this server's dashboard.")
    return access_level

async def requires_admin_access(guild_id: int, access_level: str = Depends(get_user_access_level)):
    if access_level != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Requires Server Administrator or Team Leader access.")
    return access_level

def set_bot_client(client):
    global bot_client
    bot_client = client

async def get_cached_user(user_id):
    if not user_id or not bot_client:
        return None
    
    # Return from cache if we have it
    if user_id in user_cache:
        return user_cache[user_id]
        
    # Try getting from bot's internal cache
    user = bot_client.get_user(user_id)
    
    # Fetch from API if not cached internally
    if not user:
        try:
            user = await bot_client.fetch_user(user_id)
        except Exception:
            return None
            
    if user:
        user_data = {
            "name": str(user),
            "avatar": user.display_avatar.url
        }
        user_cache[user_id] = user_data
        return user_data
        
    return None

async def get_guild_staff_names(guild_id: int) -> list[str]:
    staff_names = []
    
    # 1. Try using guild members (only works if members intent is enabled in Developer Portal)
    if bot_client and guild_id != 0:
        guild = bot_client.get_guild(guild_id)
        if not guild:
            try:
                guild = await bot_client.fetch_guild(guild_id)
            except Exception:
                guild = None
                
        if guild:
            config = await database.get_guild_config(guild_id)
            staff_role_ids = []
            for k in ["team_leader_role_id", "moderator_role_id", "trial_moderator_role_id"]:
                role_val = config.get(k)
                if role_val:
                    try:
                        staff_role_ids.append(int(role_val))
                    except (ValueError, TypeError):
                        pass
                        
            if staff_role_ids:
                members = guild.members
                if not members or len(members) <= 1:
                    try:
                        members = [m async for m in guild.fetch_members(limit=None)]
                    except Exception:
                        members = []
                        
                for m in members:
                    if any(role.id in staff_role_ids for role in m.roles):
                        staff_names.append(m.name)
                        user_cache[m.id] = {"name": m.name, "avatar": m.display_avatar.url if m.display_avatar else None}

    # 2. Fallback: query database for distinct staff IDs who have actioned warnings or requests
    async with database.aiosqlite.connect(database.DB_NAME) as db:
        db.row_factory = database.aiosqlite.Row
        
        # From warnings
        try:
            cursor = await db.execute("SELECT DISTINCT staff_id FROM warnings WHERE guild_id = ? AND staff_id IS NOT NULL", (guild_id,))
            rows = await cursor.fetchall()
            for r in rows:
                user_data = await get_cached_user(r["staff_id"])
                if user_data:
                    staff_names.append(user_data["name"])
        except Exception:
            pass
            
        # From paid_requests
        try:
            cursor = await db.execute("SELECT DISTINCT actioned_by FROM paid_requests WHERE guild_id = ? AND actioned_by IS NOT NULL", (guild_id,))
            rows = await cursor.fetchall()
            for r in rows:
                user_data = await get_cached_user(r["actioned_by"])
                if user_data:
                    staff_names.append(user_data["name"])
        except Exception:
            pass

    return sorted(list(set(staff_names)))

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

@app.get("/api/guilds/{guild_id}/warnings")
async def get_warnings(
    request: Request, 
    guild_id: int, 
    page: int = 1, 
    limit: int = 10, 
    sort_key: str = "id", 
    sort_dir: str = "desc", 
    search: str = "", 
    staff: str = "",
    access_level: str = Depends(requires_view_access)
):
    async with database.aiosqlite.connect(database.DB_NAME) as db:
        db.row_factory = database.aiosqlite.Row
        
        if guild_id == 0:
            cursor = await db.execute('''
                SELECT id, user_id, warned_at, channel_id, message_id, message_content, staff_id, reason, post_created_at, attachments, guild_id 
                FROM warnings
            ''')
        else:
            cursor = await db.execute('''
                SELECT id, user_id, warned_at, channel_id, message_id, message_content, staff_id, reason, post_created_at, attachments, guild_id 
                FROM warnings
                WHERE guild_id = ?
            ''', (guild_id,))
        rows = await cursor.fetchall()
        warnings = [dict(row) for row in rows]

    # Resolve all unique staff members' usernames (small list, safe to fetch/resolve fully)
    unique_staff_ids = list(set(w['staff_id'] for w in warnings if w['staff_id']))
    staff_name_map = {}
    for sid in unique_staff_ids:
        s_data = await get_cached_user(sid)
        if s_data:
            staff_name_map[sid] = s_data['name']
        else:
            staff_name_map[sid] = f"Unknown ({sid})"
    staff_name_map[None] = "System"
    staff_name_map[0] = "System"

    # Quick local resolution for target users, and map staff names
    resolved_warnings = []
    for w in warnings:
        # Fast local resolve for user name
        uid = w['user_id']
        u_cached = user_cache.get(uid)
        if u_cached:
            w['user_name'] = u_cached['name']
        else:
            u_obj = bot_client.get_user(uid) if bot_client else None
            if u_obj:
                w['user_name'] = str(u_obj)
                user_cache[uid] = {"name": str(u_obj), "avatar": u_obj.display_avatar.url}
            else:
                w['user_name'] = f"Unknown ({uid})"

        # Assign fully resolved staff name
        w['staff_name'] = staff_name_map.get(w['staff_id'], "System")
            
        resolved_warnings.append(w)

    # Extract unique staff list from guild staff roles and warnings logs
    guild_staff = await get_guild_staff_names(guild_id)
    log_staff = sorted(list(set(w['staff_name'] for w in resolved_warnings if w['staff_name'] != "System")))
    all_staff_names = sorted(list(set(guild_staff + log_staff)))

    # Apply Filters
    filtered_warnings = resolved_warnings
    
    if staff and staff != "All":
        filtered_warnings = [w for w in filtered_warnings if w['staff_name'].lower() == staff.lower()]
        
    if search:
        search_lower = search.lower().strip()
        filtered_warnings = [
            w for w in filtered_warnings 
            if (w['reason'] and search_lower in w['reason'].lower())
            or (search_lower in w['user_name'].lower())
            or (search_lower in str(w['user_id']))
            or (search_lower in f"#{w['id']}")
            or (search_lower in str(w['id']))
        ]
        
    filtered_total = len(filtered_warnings)

    # Apply Sorting
    if sort_key:
        reverse = (sort_dir == "desc")
        def get_sort_val(item):
            val = item.get(sort_key)
            if val is None:
                return "" if isinstance(sort_key, str) else 0
            return val
        try:
            filtered_warnings.sort(key=get_sort_val, reverse=reverse)
        except Exception:
            filtered_warnings.sort(key=lambda item: str(item.get(sort_key) or ""), reverse=reverse)

    # Apply Pagination
    start = (page - 1) * limit
    end = start + limit
    page_warnings = filtered_warnings[start:end]

    # Full API fetch/resolution for only the paginated slice
    base_url = str(request.base_url).rstrip('/')
    import json
    for w in page_warnings:
        # Convert IDs to string to avoid JavaScript float precision loss
        for k in ['user_id', 'channel_id', 'message_id', 'staff_id', 'guild_id']:
            if w.get(k) is not None:
                w[k] = str(w[k])
                
        # Resolve attachments URL
        if w.get('attachments'):
            try:
                atts = json.loads(w['attachments'])
                parsed = []
                for att in atts:
                    if "stored_filename" in att:
                        url = f"{base_url}/api/attachments/{att['stored_filename']}"
                    else:
                        url = att.get("url")
                    parsed.append({
                        "filename": att.get("filename"),
                        "url": url
                    })
                w['attachments'] = parsed
            except Exception:
                w['attachments'] = []
        else:
            w['attachments'] = []

        # Full resolve user (can make fetch_user request if not in memory)
        user_data = await get_cached_user(w['user_id'])
        if user_data:
            w['user_name'] = user_data['name']
            w['user_avatar'] = user_data['avatar']
        else:
            w['user_name'] = f"Unknown ({w['user_id']})"
            w['user_avatar'] = None
        
        # Full resolve staff
        if w['staff_id']:
            staff_data = await get_cached_user(w['staff_id'])
            if staff_data:
                w['staff_name'] = staff_data['name']
                w['staff_avatar'] = staff_data['avatar']
            else:
                w['staff_name'] = f"Unknown ({w['staff_id']})"
                w['staff_avatar'] = None
        else:
            w['staff_name'] = "System"
            w['staff_avatar'] = None

    return {"warnings": page_warnings, "total": filtered_total, "staff_list": all_staff_names}

@app.get("/api/guilds/{guild_id}/warnings/{warning_id}")
async def get_single_warning(request: Request, guild_id: int, warning_id: int, access_level: str = Depends(requires_view_access)):
    warn = await database.get_warning_by_id(warning_id)
    if not warn:
        raise HTTPException(status_code=404, detail="Warning not found")
        
    warn = dict(warn)
    # Convert IDs to string to avoid JavaScript float precision loss
    for k in ['user_id', 'channel_id', 'message_id', 'staff_id', 'guild_id']:
        if warn.get(k) is not None:
            warn[k] = str(warn[k])
            
    # Resolve usernames if bot is connected
    if bot_client:
        user_id = warn.get('user_id')
        user_data = await get_cached_user(user_id)
        if user_data:
            warn['user_name'] = user_data['name']
            warn['user_avatar'] = user_data['avatar']
        else:
            warn['user_name'] = f"Unknown ({user_id})" if user_id else "Unknown"
            warn['user_avatar'] = None

        staff_id = warn.get('staff_id')
        staff_data = await get_cached_user(staff_id)
        if staff_data:
            warn['staff_name'] = staff_data['name']
            warn['staff_avatar'] = staff_data['avatar']
        else:
            warn['staff_name'] = f"Unknown ({staff_id})" if staff_id else "Unknown"
            warn['staff_avatar'] = None
    else:
        warn['user_name'] = f"User {warn.get('user_id')}"
        warn['user_avatar'] = None
        warn['staff_name'] = f"Staff {warn.get('staff_id')}" if warn.get('staff_id') else "System"
        warn['staff_avatar'] = None

    base_url = str(request.base_url).rstrip('/')
    if warn.get('attachments'):
        import json
        try:
            atts = json.loads(warn['attachments'])
            parsed = []
            for att in atts:
                if "stored_filename" in att:
                    url = f"{base_url}/api/attachments/{att['stored_filename']}"
                else:
                    url = att.get("url")
                parsed.append({
                    "filename": att.get("filename"),
                    "url": url
                })
            warn['attachments'] = parsed
        except Exception:
            warn['attachments'] = []
    else:
        warn['attachments'] = []
        
    return warn


@app.get("/api/guilds/{guild_id}/warning-reasons")
async def get_warning_reasons(guild_id: int, access_level: str = Depends(requires_view_access)):
    async with database.aiosqlite.connect(database.DB_NAME) as db:
        db.row_factory = database.aiosqlite.Row
        cursor = await db.execute('''
            SELECT id, label, text FROM verbal_reasons WHERE guild_id = ?
        ''', (guild_id,))
        rows = await cursor.fetchall()
        reasons_list = [dict(row) for row in rows]
        
        # Fallback to default reasons if the guild doesn't have custom ones configured yet
        if not reasons_list and guild_id != 0:
            cursor = await db.execute('''
                SELECT id, label, text FROM verbal_reasons WHERE guild_id = 0 OR guild_id IS NULL
            ''')
            rows = await cursor.fetchall()
            reasons_list = [dict(row) for row in rows]
            
        return reasons_list

@app.get("/api/guilds/{guild_id}/paid-requests")
async def get_paid_requests(
    request: Request,
    guild_id: int,
    page: int = 1,
    limit: int = 10,
    sort_key: str = "request_id",
    sort_dir: str = "desc",
    search: str = "",
    status: str = "",
    staff: str = "",
    access_level: str = Depends(requires_view_access)
):
    async with database.aiosqlite.connect(database.DB_NAME) as db:
        db.row_factory = database.aiosqlite.Row
        
        if guild_id == 0:
            cursor = await db.execute('''
                SELECT request_id, user_id, budget, sfw_nsfw, payment_method, use_case, content, status, created_at, actioned_by 
                FROM paid_requests
            ''')
        else:
            cursor = await db.execute('''
                SELECT request_id, user_id, budget, sfw_nsfw, payment_method, use_case, content, status, created_at, actioned_by 
                FROM paid_requests
                WHERE guild_id = ?
            ''', (guild_id,))
        rows = await cursor.fetchall()
        requests = [dict(row) for row in rows]

    # Resolve all unique staff members' usernames
    unique_staff_ids = list(set(r['actioned_by'] for r in requests if r.get('actioned_by')))
    staff_name_map = {}
    for sid in unique_staff_ids:
        s_data = await get_cached_user(sid)
        if s_data:
            staff_name_map[sid] = s_data['name']
        else:
            staff_name_map[sid] = f"Unknown ({sid})"
    staff_name_map[None] = "System"
    staff_name_map[0] = "System"

    # Quick local resolution for target users, and map staff names
    resolved_requests = []
    for r in requests:
        # Fast local resolve for user name
        uid = r['user_id']
        u_cached = user_cache.get(uid)
        if u_cached:
            r['user_name'] = u_cached['name']
            r['user_avatar'] = u_cached['avatar']
        else:
            u_obj = bot_client.get_user(uid) if bot_client else None
            if u_obj:
                r['user_name'] = str(u_obj)
                r['user_avatar'] = u_obj.display_avatar.url
                user_cache[uid] = {"name": str(u_obj), "avatar": u_obj.display_avatar.url}
            else:
                r['user_name'] = f"Unknown ({uid})"
                r['user_avatar'] = None

        # Assign fully resolved staff name
        r['staff_name'] = staff_name_map.get(r.get('actioned_by'), "System")
            
        resolved_requests.append(r)

    # Extract unique staff list from guild staff roles and paid requests logs
    guild_staff = await get_guild_staff_names(guild_id)
    log_staff = sorted(list(set(r['staff_name'] for r in resolved_requests if r['staff_name'] != "System")))
    all_staff_names = sorted(list(set(guild_staff + log_staff)))

    # Apply Filters
    filtered_requests = resolved_requests
    
    if status and status != "All":
        filtered_requests = [r for r in filtered_requests if r['status'].lower() == status.lower()]
        
    if staff and staff != "All":
        filtered_requests = [r for r in filtered_requests if r['staff_name'].lower() == staff.lower()]
        
    if search:
        search_lower = search.lower().strip()
        filtered_requests = [
            r for r in filtered_requests 
            if search_lower in r['user_name'].lower()
            or search_lower in str(r['user_id'])
            or search_lower in r['payment_method'].lower()
            or search_lower in r['budget'].lower()
            or search_lower in r['content'].lower()
            or search_lower in f"#{r['request_id']}"
            or search_lower in str(r['request_id'])
        ]
        
    filtered_total = len(filtered_requests)

    # Apply Sorting
    if sort_key:
        reverse = (sort_dir == "desc")
        def get_sort_val(item):
            val = item.get(sort_key)
            if val is None:
                return "" if isinstance(sort_key, str) else 0
            return val
        try:
            filtered_requests.sort(key=get_sort_val, reverse=reverse)
        except Exception:
            filtered_requests.sort(key=lambda item: str(item.get(sort_key) or ""), reverse=reverse)

    # Apply Pagination
    start = (page - 1) * limit
    end = start + limit
    page_requests = filtered_requests[start:end]

    # Full API fetch/resolution for only the paginated slice
    for r in page_requests:
        # Convert IDs to string to avoid JavaScript float precision loss
        for k in ['user_id', 'actioned_by', 'guild_id']:
            if r.get(k) is not None:
                r[k] = str(r[k])
        
        # Full resolve user (can make fetch_user request if not in memory)
        user_data = await get_cached_user(r['user_id'])
        if user_data:
            r['user_name'] = user_data['name']
            r['user_avatar'] = user_data['avatar']
        else:
            r['user_name'] = f"Unknown ({r['user_id']})"
            r['user_avatar'] = None
        
        # Full resolve staff
        aid = r.get('actioned_by')
        if aid:
            staff_data = await get_cached_user(aid)
            if staff_data:
                r['staff_name'] = staff_data['name']
                r['staff_avatar'] = staff_data['avatar']
            else:
                r['staff_name'] = f"Unknown ({aid})"
                r['staff_avatar'] = None
        else:
            r['staff_name'] = "System"
            r['staff_avatar'] = None

    return {"requests": page_requests, "total": filtered_total, "staff_list": all_staff_names}

@app.get("/api/guilds/{guild_id}/stats")
async def get_stats(guild_id: int, access_level: str = Depends(requires_view_access)):
    async with database.aiosqlite.connect(database.DB_NAME) as db:
        # Pending requests
        cursor = await db.execute("SELECT COUNT(*) FROM paid_requests WHERE status = 'pending'")
        pending_requests = (await cursor.fetchone())[0]

        if guild_id == 0:
            # Verbals this week
            cursor = await db.execute("SELECT COUNT(*) FROM warnings WHERE warned_at >= datetime('now', '-7 days')")
            verbals_this_week = (await cursor.fetchone())[0]
            
            # Verbals last week for trend
            cursor = await db.execute("SELECT COUNT(*) FROM warnings WHERE warned_at >= datetime('now', '-14 days') AND warned_at < datetime('now', '-7 days')")
            verbals_last_week = (await cursor.fetchone())[0]
        else:
            # Verbals this week
            cursor = await db.execute("SELECT COUNT(*) FROM warnings WHERE warned_at >= datetime('now', '-7 days') AND (guild_id = ? OR guild_id IS NULL)", (guild_id,))
            verbals_this_week = (await cursor.fetchone())[0]
            
            # Verbals last week for trend
            cursor = await db.execute("SELECT COUNT(*) FROM warnings WHERE warned_at >= datetime('now', '-14 days') AND warned_at < datetime('now', '-7 days') AND (guild_id = ? OR guild_id IS NULL)", (guild_id,))
            verbals_last_week = (await cursor.fetchone())[0]

        # Active reminders
        cursor = await db.execute("SELECT COUNT(*) FROM reminders")
        active_reminders = (await cursor.fetchone())[0]

    # Calculate trend
    if verbals_last_week == 0:
        trend = "+100%" if verbals_this_week > 0 else "0%"
    else:
        diff = ((verbals_this_week - verbals_last_week) / verbals_last_week) * 100
        trend = f"{'+' if diff > 0 else ''}{diff:.1f}%"

    ping = f"{round(bot_client.latency * 1000)}ms" if bot_client else "N/A"
    status = "Online" if bot_client and bot_client.is_ready() else "Offline"

    return {
        "bot_status": status,
        "ping": ping,
        "pending_requests": pending_requests,
        "verbals_this_week": verbals_this_week,
        "verbals_trend": f"{trend} vs last week",
        "active_reminders": active_reminders
    }

class GuildConfig(BaseModel):
    staff_notice_channel_id: Optional[str] = None
    staff_commands_channel_id: Optional[str] = None
    staff_log_channel_id: Optional[str] = None
    team_leader_role_id: Optional[str] = None
    moderator_role_id: Optional[str] = None
    trial_moderator_role_id: Optional[str] = None
    submit_channel_id: Optional[str] = None
    review_channel_id: Optional[str] = None
    approved_channel_id: Optional[str] = None
    approval_log_channel_id: Optional[str] = None
    active_limit: int = 2
    reminder_threshold: int = 14
    accepted_currencies: str = "USD, EUR, GBP, CAD, AUD, \\$|£|€"
    accepted_payments: str = "PayPal, Stripe, CashApp, Venmo, Ko-Fi"
    banned_terms_regex: str = "robux|robuck|robucks|crypto|btc|eth|sol|ltc|usdt|usdc"
    dm_on_warning: bool = True
    vacation_role_id: Optional[str] = None
    vacation_role_id_2: Optional[str] = None
    vacation_secondary_guild_id: Optional[str] = None
    vacation_strip_roles_1: Optional[str] = None
    vacation_strip_roles_2: Optional[str] = None


@app.get("/api/guilds/{guild_id}/analytics")
async def get_analytics(guild_id: int, period: str = "month", access_level: str = Depends(requires_view_access)):
    # period can be "week", "month", "year"
    # Determine grouping and time range
    if period == "year":
        # Group by month for the last 12 months
        group_func = "strftime('%Y-%m', {col})"
        time_filter = "date({col}) >= date('now', '-1 year')"
    else:
        # Group by day
        days = 7 if period == "week" else 30
        group_func = "date({col})"
        time_filter = f"date({{col}}) >= date('now', '-{days} days')"
        
    async with database.aiosqlite.connect(database.DB_NAME) as db:
        db.row_factory = database.aiosqlite.Row
        
        warn_col = "warned_at"
        req_col = "created_at"
        
        # Get warnings
        if guild_id == 0:
            w_cursor = await db.execute(f"""
                SELECT {group_func.format(col=warn_col)} as period_key, COUNT(*) as count 
                FROM warnings 
                WHERE {time_filter.format(col=warn_col)}
                GROUP BY period_key
                ORDER BY period_key ASC
            """)
        else:
            w_cursor = await db.execute(f"""
                SELECT {group_func.format(col=warn_col)} as period_key, COUNT(*) as count 
                FROM warnings 
                WHERE guild_id = ? AND {time_filter.format(col=warn_col)}
                GROUP BY period_key
                ORDER BY period_key ASC
            """, (guild_id,))
        warn_rows = await w_cursor.fetchall()
        
        # Get paid requests
        if guild_id == 0:
            p_cursor = await db.execute(f"""
                SELECT {group_func.format(col=req_col)} as period_key, COUNT(*) as count 
                FROM paid_requests 
                WHERE {time_filter.format(col=req_col)}
                GROUP BY period_key
                ORDER BY period_key ASC
            """)
        else:
            p_cursor = await db.execute(f"""
                SELECT {group_func.format(col=req_col)} as period_key, COUNT(*) as count 
                FROM paid_requests 
                WHERE guild_id = ? AND {time_filter.format(col=req_col)}
                GROUP BY period_key
                ORDER BY period_key ASC
            """, (guild_id,))
        paid_rows = await p_cursor.fetchall()
        
        # Merge them into a single timeline array
        timeline = {}
        from datetime import datetime, timedelta
        from dateutil.relativedelta import relativedelta
        
        # Prefill timeline to ensure no gaps
        today = datetime.utcnow()
        if period == "year":
            # 12 months
            for i in range(12):
                d = (today - relativedelta(months=11 - i)).strftime('%Y-%m')
                timeline[d] = {"date": d, "warnings": 0, "requests": 0}
        else:
            # days
            for i in range(days):
                d = (today - timedelta(days=days - 1 - i)).date().isoformat()
                timeline[d] = {"date": d, "warnings": 0, "requests": 0}
            
        for r in warn_rows:
            key = r["period_key"]
            if key in timeline:
                timeline[key]["warnings"] = r["count"]
                
        for r in paid_rows:
            key = r["period_key"]
            if key in timeline:
                timeline[key]["requests"] = r["count"]
                
        return {"data": list(timeline.values())}

@app.get("/api/guilds")
async def get_guilds(user_id: str = Depends(get_discord_user_id)):
    if not bot_client:
        return {"guilds": []}
        
    user_guilds = []
    for g in bot_client.guilds:
        access_level = await get_user_access_level(g.id, user_id)
        if access_level in ["admin", "view"]:
            user_guilds.append({
                "id": str(g.id), 
                "name": g.name, 
                "icon": g.icon.url if g.icon else None,
                "access_level": access_level
            })
            
    return {"guilds": user_guilds}


@app.get("/api/guilds/{guild_id}/config")
async def get_config(guild_id: int, access_level: str = Depends(requires_view_access)):
    async with database.aiosqlite.connect(database.DB_NAME) as db:
        db.row_factory = database.aiosqlite.Row
        
        if guild_id == 0:
            cursor = await db.execute("SELECT * FROM guild_configs LIMIT 1")
        else:
            cursor = await db.execute("SELECT * FROM guild_configs WHERE guild_id = ?", (guild_id,))
        row = await cursor.fetchone()
        
        if row:
            config_dict = dict(row)
            for k, v in config_dict.items():
                if (k.endswith('_id') or k == 'vacation_role_id_2') and v is not None:
                    config_dict[k] = str(v)
            return config_dict
        
        # Return defaults if no config exists
        return GuildConfig().model_dump()

@app.post("/api/guilds/{guild_id}/config")
async def save_config(guild_id: int, config: GuildConfig, access_level: str = Depends(requires_admin_access), user_id: str = Depends(get_discord_user_id)):
    async with database.aiosqlite.connect(database.DB_NAME) as db:
        # Resolve guild_id 0 to actual guild_id if it exists
        if guild_id == 0:
            cursor = await db.execute("SELECT guild_id FROM guild_configs LIMIT 1")
            row = await cursor.fetchone()
            actual_guild_id = row[0] if row else 0
        else:
            actual_guild_id = guild_id

        # Get only explicitly provided fields
        provided_data = config.model_dump(exclude_unset=True)
        
        # Convert dm_on_warning bool to int if provided
        if "dm_on_warning" in provided_data and provided_data["dm_on_warning"] is not None:
            provided_data["dm_on_warning"] = int(provided_data["dm_on_warning"])

        # Check if exists
        cursor = await db.execute("SELECT 1 FROM guild_configs WHERE guild_id = ?", (actual_guild_id,))
        exists = await cursor.fetchone()
        
        if exists:
            if provided_data:
                # Dynamically build UPDATE query for sent fields only
                set_clause = ", ".join([f"{k} = ?" for k in provided_data.keys()])
                values = list(provided_data.values()) + [actual_guild_id]
                await db.execute(f"UPDATE guild_configs SET {set_clause} WHERE guild_id = ?", values)
        else:
            # Insert with whatever fields are provided
            all_fields = {"guild_id": actual_guild_id}
            all_fields.update(provided_data)
            
            columns = ", ".join(all_fields.keys())
            placeholders = ", ".join(["?" for _ in all_fields])
            await db.execute(f"INSERT INTO guild_configs ({columns}) VALUES ({placeholders})", list(all_fields.values()))
            
        await db.commit()
    return {"status": "success"}

class VerbalReason(BaseModel):
    id: str
    label: str
    text: str

class VerbalReasonsUpdate(BaseModel):
    reasons: List[VerbalReason]

@app.post("/api/guilds/{guild_id}/warning-reasons")
async def save_warning_reasons(guild_id: int, data: VerbalReasonsUpdate, access_level: str = Depends(requires_admin_access), user_id: str = Depends(get_discord_user_id)):
    async with database.aiosqlite.connect(database.DB_NAME) as db:
        # Delete existing reasons for this guild only
        await db.execute("DELETE FROM verbal_reasons WHERE guild_id = ?", (guild_id,))
        
        # Insert new reasons for this guild
        for r in data.reasons:
            await db.execute('''
                INSERT INTO verbal_reasons (id, label, text, guild_id) VALUES (?, ?, ?, ?)
            ''', (r.id, r.label, r.text, guild_id))
            
        await db.commit()
    return {"status": "success"}

@app.post("/api/guilds/{guild_id}/paid-requests/purge")
async def purge_paid_requests(guild_id: int, access_level: str = Depends(requires_admin_access), user_id: str = Depends(get_discord_user_id)):
    async with database.aiosqlite.connect(database.DB_NAME) as db:
        if guild_id == 0:
            await db.execute("DELETE FROM paid_requests")
            try:
                await db.execute("DELETE FROM sqlite_sequence WHERE name='paid_requests'")
            except database.aiosqlite.OperationalError:
                pass
        else:
            await db.execute("DELETE FROM paid_requests WHERE guild_id = ?", (guild_id,))
            
        await log_dashboard_action(guild_id, user_id, "PURGED all paid requests from the database.")
        
        # Reset ID counter if no requests are left in the database at all
        cursor = await db.execute("SELECT COUNT(*) FROM paid_requests")
        count = (await cursor.fetchone())[0]
        if count == 0:
            try:
                await db.execute("DELETE FROM sqlite_sequence WHERE name='paid_requests'")
            except database.aiosqlite.OperationalError:
                pass
                
        await db.commit()
    return {"status": "success"}

@app.post("/api/guilds/{guild_id}/warnings/purge")
async def purge_warnings(guild_id: int, access_level: str = Depends(requires_admin_access), user_id: str = Depends(get_discord_user_id)):
    async with database.aiosqlite.connect(database.DB_NAME) as db:
        if guild_id == 0:
            await db.execute("DELETE FROM warnings")
        else:
            await db.execute("DELETE FROM warnings WHERE guild_id = ?", (guild_id,))
        await log_dashboard_action(guild_id, user_id, "PURGED all verbal warnings from the database.")
        await db.commit()
    return {"status": "success"}

@app.delete("/api/guilds/{guild_id}/warnings/{warning_id}")
async def delete_warning(guild_id: int, warning_id: int, access_level: str = Depends(requires_admin_access), user_id: str = Depends(get_discord_user_id)):
    # Fetch the warning first
    warn = await database.get_warning_by_id(warning_id)
    if not warn:
        raise HTTPException(status_code=404, detail="Warning not found")
        
    if warn.get('guild_id') != guild_id and guild_id != 0:
        raise HTTPException(status_code=403, detail="Forbidden: This warning does not belong to your server.")

    # Delete from database
    await database.delete_warning_by_id(warning_id)

    # If the bot is connected, clean up in Discord as well
    if bot_client:
        try:
            # 1. Delete the notice message in #staff-notice
            channel_id = warn.get('channel_id')
            message_id = warn.get('message_id')
            if channel_id and message_id:
                try:
                    channel = bot_client.get_channel(channel_id)
                    if not channel:
                        channel = await bot_client.fetch_channel(channel_id)
                    if channel:
                        msg = await channel.fetch_message(message_id)
                        await msg.delete()
                except Exception as e:
                    print(f"Failed to delete warning notice message: {e}")

            # 2. Send log to staff log channel
            config = await database.get_guild_config(guild_id)
            log_channel_id = config.get("staff_log_channel_id") or 0
            if log_channel_id:
                try:
                    import discord
                    log_channel = bot_client.get_channel(log_channel_id)
                    if not log_channel:
                        log_channel = await bot_client.fetch_channel(log_channel_id)
                    if log_channel:
                        # Resolve the staff member who performed the action on the dashboard
                        staff_user = None
                        try:
                            sid = int(user_id)
                            staff_user = bot_client.get_user(sid)
                            if not staff_user:
                                staff_user = await bot_client.fetch_user(sid)
                        except Exception:
                            pass

                        if staff_user:
                            staff_str = f"{staff_user.mention} ({staff_user.id})"
                        else:
                            staff_str = f"<@{user_id}> ({user_id})"

                        log_embed = discord.Embed(
                            title="Log: Verbal Notice Deleted/Revoked (via Dashboard)",
                            color=discord.Color.red()
                        )
                        log_embed.add_field(name="Staff Member", value=staff_str, inline=True)
                        log_embed.add_field(name="Target User", value=f"<@{warn['user_id']}> ({warn['user_id']})", inline=True)
                        log_embed.add_field(name="Warning ID", value=f"#{warning_id}", inline=True)
                        log_embed.add_field(name="Original Reason", value=warn['reason'][:1000] if warn['reason'] else "None", inline=False)
                        await log_channel.send(embed=log_embed)
                except Exception as e:
                    print(f"Failed to send log embed: {e}")

            # 3. DM the warned user to let them know it was revoked
            try:
                import discord
                target_user = bot_client.get_user(warn['user_id'])
                if not target_user:
                    target_user = await bot_client.fetch_user(warn['user_id'])
                if target_user and not target_user.bot:
                    guild_name = "server"
                    guild = bot_client.get_guild(guild_id)
                    if guild:
                        guild_name = guild.name
                    dm_embed = discord.Embed(
                        title="Verbal Notice Revoked",
                        description=f"One of your verbal warns (ID #{warning_id}) in the **{guild_name}** has been revoked.",
                        color=discord.Color.green()
                    )
                    await target_user.send(embed=dm_embed)
            except Exception as e:
                print(f"Failed to DM user about revoked warning: {e}")

        except Exception as outer_e:
            print(f"Error handling discord warning removal: {outer_e}")

    return {"status": "success"}


@app.get("/api/guilds/{guild_id}/reminders")
async def get_reminders(guild_id: int, access_level: str = Depends(requires_view_access)):
    async with database.aiosqlite.connect(database.DB_NAME) as db:
        db.row_factory = database.aiosqlite.Row
        
        cursor = await db.execute('''
            SELECT id, user_id, about, remind_at, channel_id, created_at 
            FROM reminders
            ORDER BY remind_at ASC
        ''')
        rows = await cursor.fetchall()
        reminders = [dict(row) for row in rows]
        
    if bot_client:
        for r in reminders:
            user_id = r.get('user_id')
            user_data = await get_cached_user(user_id)
            if user_data:
                r['user_name'] = user_data['name']
                r['user_avatar'] = user_data['avatar']
            else:
                r['user_name'] = f"Unknown ({user_id})" if user_id else "Unknown"
                r['user_avatar'] = None

    return {"reminders": reminders}

@app.delete("/api/guilds/{guild_id}/reminders/{reminder_id}")
async def delete_reminder(guild_id: int, reminder_id: int, access_level: str = Depends(requires_admin_access), user_id: str = Depends(get_discord_user_id)):
    async with database.aiosqlite.connect(database.DB_NAME) as db:
        db.row_factory = database.aiosqlite.Row
        cursor = await db.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
        reminder = await cursor.fetchone()
        if not reminder:
            raise HTTPException(status_code=404, detail="Reminder not found")
            
        if bot_client:
            channel = bot_client.get_channel(reminder['channel_id'])
            if channel and channel.guild.id != guild_id and guild_id != 0:
                raise HTTPException(status_code=403, detail="Forbidden: Reminder belongs to another server.")

        await db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        await log_dashboard_action(guild_id, user_id, f"deleted reminder ID #{reminder_id}.")
        await db.commit()
    return {"status": "success"}


# --- Chatbot Config Schemas & Routes ---

class ChatbotButtonData(BaseModel):
    label: str
    emoji: Optional[str] = None
    action: str  # "message" or "menu"
    target: Optional[str] = None
    text: Optional[str] = None

class ChatbotMenuData(BaseModel):
    text: str
    buttons: List[ChatbotButtonData]

class ChatbotConfigUpdate(BaseModel):
    main_menu: ChatbotMenuData
    menus: Optional[dict] = None
    dm_prompt_button: Optional[bool] = False

@app.get("/api/guilds/{guild_id}/chatbot")
async def get_chatbot(guild_id: int, access_level: str = Depends(requires_view_access)):
    config = await database.get_chatbot_config(guild_id)
    return config

@app.post("/api/guilds/{guild_id}/chatbot")
async def update_chatbot(guild_id: int, data: ChatbotConfigUpdate, access_level: str = Depends(requires_admin_access), user_id: str = Depends(get_discord_user_id)):
    config_dict = data.model_dump()
    await database.save_chatbot_config(guild_id, config_dict)
    
    if bot_client:
        chatbot_cog = bot_client.get_cog("Chatbot")
        if chatbot_cog:
            await chatbot_cog.refresh_cache(guild_id)
            
    return {"status": "success"}


# --- Message Builder Schemas & Routes ---

class EmbedFieldData(BaseModel):
    name: str
    value: str
    inline: bool = True

class EmbedData(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    image: Optional[str] = None
    footer: Optional[str] = None
    fields: Optional[List[EmbedFieldData]] = None

class ReactionRoleData(BaseModel):
    emoji: str
    role_id: str

class MessageBuilderSend(BaseModel):
    channel_id: str
    message_id: Optional[str] = None
    message_text: Optional[str] = None
    embeds: Optional[List[EmbedData]] = None
    thread_name: Optional[str] = None
    reaction_roles: Optional[List[ReactionRoleData]] = None
    suppress_notifications: Optional[bool] = False
    single_choice: Optional[bool] = False

@app.get("/api/guilds/{guild_id}/channels")
async def get_guild_channels(guild_id: int, access_level: str = Depends(requires_admin_access)):
    if not bot_client:
        return {"channels": []}
    guild = bot_client.get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found or bot not in guild.")
    
    channels = []
    # Add text channels
    for c in guild.text_channels:
        channels.append({"id": str(c.id), "name": f"#{c.name}"})
    # Add forum channels
    if hasattr(guild, "forums"):
        for f in guild.forums:
            channels.append({"id": str(f.id), "name": f"📢 {f.name} (Forum)"})
        
    return {"channels": channels}

@app.get("/api/guilds/{guild_id}/roles")
async def get_guild_roles(guild_id: int, access_level: str = Depends(requires_admin_access)):
    if not bot_client:
        return {"roles": []}
    guild = bot_client.get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found or bot not in guild.")
    
    roles = []
    for r in guild.roles:
        if r.is_default():
            continue
        if r.managed:
            continue
        roles.append({"id": str(r.id), "name": r.name})
    return {"roles": roles}

@app.post("/api/guilds/{guild_id}/builder/send")
async def send_builder_message(guild_id: int, data: MessageBuilderSend, access_level: str = Depends(requires_admin_access), user_id: str = Depends(get_discord_user_id)):
    if not bot_client:
        raise HTTPException(status_code=503, detail="Discord bot is not running.")
        
    guild = bot_client.get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
        
    channel = guild.get_channel(int(data.channel_id)) or guild.get_thread(int(data.channel_id))
    if not channel:
        try:
            channel = await guild.fetch_channel(int(data.channel_id))
        except discord.HTTPException:
            try:
                channel = await guild.fetch_thread(int(data.channel_id))
            except discord.HTTPException:
                raise HTTPException(status_code=404, detail="Channel or Thread not found in this server.")
            
    embeds = []
    if data.embeds:
        for eb in data.embeds[:10]: # Max 10 embeds allowed by Discord
            has_title = bool(eb.title)
            has_desc = bool(eb.description)
            has_color = bool(eb.color)
            has_image = bool(eb.image)
            has_footer = bool(eb.footer)
            has_fields = bool(eb.fields)
            
            if has_title or has_desc or has_color or has_image or has_footer or has_fields:
                color_val = None
                if eb.color:
                    try:
                        color_val = int(eb.color.strip("#"), 16)
                    except ValueError:
                        raise HTTPException(status_code=400, detail="Invalid color format. Use hex format like #FF5555.")
                        
                embed = discord.Embed(
                    title=eb.title or None,
                    description=eb.description or None,
                    color=color_val
                )
                if eb.image:
                    embed.set_image(url=eb.image)
                if eb.footer:
                    embed.set_footer(text=eb.footer)
                if eb.fields:
                    for f in eb.fields:
                        embed.add_field(name=f.name, value=f.value, inline=f.inline)
                embeds.append(embed)

    if not data.message_text and not embeds:
        raise HTTPException(status_code=400, detail="Cannot send or edit an empty message. Provide text content or at least one embed.")

    try:
        # Edit Mode
        if data.message_id and data.message_id.strip():
            try:
                msg = await channel.fetch_message(int(data.message_id.strip()))
                if msg.author.id != bot_client.user.id:
                    raise HTTPException(status_code=400, detail="Cannot edit a message sent by another user or bot.")
                
                await msg.edit(content=data.message_text or None, embeds=embeds or None)
                
                await database.delete_reaction_roles_for_message(msg.id)
                if data.reaction_roles:
                    for rr in data.reaction_roles:
                        resolved_emoji = rr.emoji
                        if rr.emoji.startswith(":") and rr.emoji.endswith(":"):
                            clean_name = rr.emoji.strip(":")
                            custom_emoji = discord.utils.get(guild.emojis, name=clean_name)
                            if custom_emoji:
                                prefix = "a" if custom_emoji.animated else ""
                                resolved_emoji = f"<{prefix}:{custom_emoji.name}:{custom_emoji.id}>"
                        try:
                            await msg.add_reaction(resolved_emoji)
                            await database.add_reaction_role(msg.id, guild_id, resolved_emoji, int(rr.role_id))
                        except Exception as re:
                            print(f"Failed to add reaction role: {re}")
                            
                await database.set_message_reaction_role_settings(msg.id, data.single_choice or False)
                return {"status": "success", "message_id": str(msg.id)}
            except discord.NotFound:
                raise HTTPException(status_code=404, detail="Message not found in the selected channel.")
            except discord.Forbidden:
                raise HTTPException(status_code=403, detail="Bot is missing permission to edit or fetch this message.")
        
        # Send Mode (New Message)
        flags = discord.MessageFlags()
        if data.suppress_notifications:
            flags.suppress_notifications = True
        
        send_kwargs = {"content": data.message_text or None, "embeds": embeds or None}
        if flags.value != 0:
            send_kwargs["flags"] = flags
            
        msg = await channel.send(**send_kwargs)
        
        if data.thread_name:
            try:
                await msg.create_thread(name=data.thread_name)
            except Exception as te:
                print(f"Failed to create thread for builder message: {te}")
                
        await database.delete_reaction_roles_for_message(msg.id)
        if data.reaction_roles:
            for rr in data.reaction_roles:
                resolved_emoji = rr.emoji
                if rr.emoji.startswith(":") and rr.emoji.endswith(":"):
                    clean_name = rr.emoji.strip(":")
                    custom_emoji = discord.utils.get(guild.emojis, name=clean_name)
                    if custom_emoji:
                        prefix = "a" if custom_emoji.animated else ""
                        resolved_emoji = f"<{prefix}:{custom_emoji.name}:{custom_emoji.id}>"
                try:
                    await msg.add_reaction(resolved_emoji)
                    await database.add_reaction_role(msg.id, guild_id, resolved_emoji, int(rr.role_id))
                except Exception as re:
                    print(f"Failed to add reaction role: {re}")
                    
        await database.set_message_reaction_role_settings(msg.id, data.single_choice or False)
        return {"status": "success", "message_id": str(msg.id)}
    except discord.Forbidden:
        raise HTTPException(status_code=403, detail="Bot is missing Send Messages permission in the selected channel.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send/edit message: {e}")

@app.get("/api/guilds/{guild_id}/messages/{message_id}")
async def get_builder_message(
    guild_id: int, 
    message_id: int, 
    channel_id: Optional[str] = None,
    access_level: str = Depends(requires_admin_access)
):
    if not bot_client:
        raise HTTPException(status_code=503, detail="Discord bot is not running.")
    guild = bot_client.get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
        
    msg = None
    target_channel = None
    
    # 1. Check cache first
    cached_msg = discord.utils.get(bot_client.cached_messages, id=message_id)
    if cached_msg and cached_msg.guild and cached_msg.guild.id == guild_id:
        msg = cached_msg
        target_channel = cached_msg.channel
        
    # 2. Check channel_id hint if provided
    if not msg and channel_id:
        try:
            cid = int(channel_id)
            c = guild.get_channel(cid) or guild.get_thread(cid)
            if not c:
                c = await guild.fetch_channel(cid)
            if c:
                msg = await c.fetch_message(message_id)
                target_channel = c
        except Exception:
            pass
            
    # 3. Check guild config channels (highest likelihood of bot messages)
    if not msg:
        config = await database.get_guild_config(guild_id)
        config_cids = []
        if config:
            for k in ["staff_notice_channel_id", "staff_commands_channel_id", "staff_log_channel_id", "submit_channel_id", "review_channel_id", "approved_channel_id", "approval_log_channel_id"]:
                val = config.get(k)
                if val:
                    config_cids.append(int(val))
                    
        for cid in config_cids:
            try:
                c = guild.get_channel(cid) or guild.get_thread(cid)
                if not c:
                    c = await guild.fetch_channel(cid)
                if c:
                    msg = await c.fetch_message(message_id)
                    target_channel = c
                    break
            except Exception:
                continue
                
    # 4. Fallback search (concurrently check all channels)
    if not msg:
        import asyncio
        candidates = list(guild.text_channels) + list(guild.threads)
        checked_ids = set()
        if channel_id: 
            try:
                checked_ids.add(int(channel_id))
            except Exception:
                pass
        if config_cids: 
            checked_ids.update(config_cids)
        candidates = [c for c in candidates if c.id not in checked_ids]
        
        async def check_c(chan):
            try:
                m = await chan.fetch_message(message_id)
                return (chan, m)
            except Exception:
                return None
                
        results = await asyncio.gather(*(check_c(c) for c in candidates), return_exceptions=True)
        for res in results:
            if res and isinstance(res, tuple):
                target_channel, msg = res
                break
                
    if not msg or not target_channel:
        raise HTTPException(status_code=404, detail="Message not found anywhere in this server.")
        
    embeds_data = []
    for emb in msg.embeds:
        color_hex = f"#{emb.color.value:06x}" if emb.color else "#5865F2"
        fields = []
        for f in emb.fields:
            fields.append({
                "name": f.name,
                "value": f.value,
                "inline": f.inline
            })
        embeds_data.append({
            "title": emb.title or "",
            "description": emb.description or "",
            "color": color_hex,
            "image": emb.image.url if emb.image else "",
            "footer": emb.footer.text if emb.footer else "",
            "fields": fields
        })
        
    db_rrs = await database.get_reaction_roles_for_message(message_id)
    reaction_roles = []
    if db_rrs:
        for rr in db_rrs:
            reaction_roles.append({
                "emoji": rr["emoji"],
                "role_id": str(rr["role_id"])
            })
            
    settings = await database.get_message_reaction_role_settings(message_id)
    return {
        "channel_id": str(target_channel.id),
        "message_text": msg.content or "",
        "embeds": embeds_data,
        "reaction_roles": reaction_roles,
        "thread_name": msg.thread.name if msg.thread else "",
        "single_choice": settings.get("single_choice", 0) == 1
    }

class VacationRequest(BaseModel):
    user_id: str
    reason: Optional[str] = None

@app.get("/api/guilds/{guild_id}/vacations")
async def get_vacations(guild_id: int, access_level: str = Depends(requires_view_access)):
    if guild_id == 0:
        async with database.aiosqlite.connect(database.DB_NAME) as db:
            cursor = await db.execute("SELECT guild_id FROM guild_configs LIMIT 1")
            row = await cursor.fetchone()
            actual_guild_id = row[0] if row else 0
    else:
        actual_guild_id = guild_id

    records = await database.get_all_active_vacations(actual_guild_id)
    results = []
    
    guild = None
    if bot_client:
        try:
            guild = bot_client.get_guild(actual_guild_id)
            if not guild:
                guild = await bot_client.fetch_guild(actual_guild_id)
        except Exception:
            pass

    for r in records:
        user_id = r["user_id"]
        username = f"User {user_id}"
        avatar_url = ""
        
        if guild:
            try:
                member = guild.get_member(user_id)
                if not member:
                    member = await guild.fetch_member(user_id)
                if member:
                    username = member.display_name
                    avatar_url = member.display_avatar.url
            except Exception:
                try:
                    user = await bot_client.fetch_user(user_id)
                    if user:
                        username = user.display_name
                        avatar_url = user.display_avatar.url
                except Exception:
                    pass

        duration_str = "Just now"
        try:
            start_dt = None
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S'):
                try:
                    start_dt = datetime.strptime(r["vacation_start"], fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            if start_dt:
                diff = datetime.now(timezone.utc) - start_dt
                if diff.days > 365:
                    duration_str = f"{diff.days // 365} year(s) ago"
                elif diff.days > 30:
                    duration_str = f"{diff.days // 30} month(s) ago"
                elif diff.days > 0:
                    duration_str = f"{diff.days} day(s) ago"
                elif diff.seconds > 3600:
                    duration_str = f"{diff.seconds // 3600} hour(s) ago"
                elif diff.seconds > 60:
                    duration_str = f"{diff.seconds // 60} minute(s) ago"
                else:
                    duration_str = "Just now"
        except Exception:
            pass

        results.append({
            "user_id": str(user_id),
            "username": username,
            "avatar_url": avatar_url,
            "reason": r["reason"] or "No reason provided",
            "vacation_start": r["vacation_start"],
            "duration": duration_str
        })
    return results

@app.post("/api/guilds/{guild_id}/vacations")
async def create_vacation(guild_id: int, body: VacationRequest, access_level: str = Depends(requires_admin_access)):
    if not bot_client:
        raise HTTPException(status_code=503, detail="Discord bot is not currently running.")
        
    if guild_id == 0:
        async with database.aiosqlite.connect(database.DB_NAME) as db:
            cursor = await db.execute("SELECT guild_id FROM guild_configs LIMIT 1")
            row = await cursor.fetchone()
            actual_guild_id = row[0] if row else 0
    else:
        actual_guild_id = guild_id

    guild = bot_client.get_guild(actual_guild_id)
    if not guild:
        try:
            guild = await bot_client.fetch_guild(actual_guild_id)
        except Exception:
            raise HTTPException(status_code=404, detail="Guild not found or inaccessible by bot.")

    try:
        uid = int(body.user_id)
        member = guild.get_member(uid)
        if not member:
            member = await guild.fetch_member(uid)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Member with ID {body.user_id} not found in this server.")

    cog = bot_client.get_cog("VacationManager")
    if not cog:
        raise HTTPException(status_code=500, detail="VacationManager cog is not loaded in the bot.")

    try:
        msg = await cog.start_vacation(guild, member, body.reason)
        return {"status": "success", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/guilds/{guild_id}/vacations/{user_id}")
async def revoke_vacation(guild_id: int, user_id: str, access_level: str = Depends(requires_admin_access)):
    if not bot_client:
        raise HTTPException(status_code=503, detail="Discord bot is not currently running.")
        
    if guild_id == 0:
        async with database.aiosqlite.connect(database.DB_NAME) as db:
            cursor = await db.execute("SELECT guild_id FROM guild_configs LIMIT 1")
            row = await cursor.fetchone()
            actual_guild_id = row[0] if row else 0
    else:
        actual_guild_id = guild_id

    guild = bot_client.get_guild(actual_guild_id)
    if not guild:
        try:
            guild = await bot_client.fetch_guild(actual_guild_id)
        except Exception:
            raise HTTPException(status_code=404, detail="Guild not found or inaccessible by bot.")

    try:
        uid = int(user_id)
        member = guild.get_member(uid)
        if not member:
            member = await guild.fetch_member(uid)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Member with ID {user_id} not found in this server.")

    cog = bot_client.get_cog("VacationManager")
    if not cog:
        raise HTTPException(status_code=500, detail="VacationManager cog is not loaded in the bot.")

    try:
        msg = await cog.end_vacation(guild, member)
        return {"status": "success", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/guilds/{guild_id}/vacations/history")
async def get_vacations_history(guild_id: int, access_level: str = Depends(requires_view_access)):
    if guild_id == 0:
        async with database.aiosqlite.connect(database.DB_NAME) as db:
            cursor = await db.execute("SELECT guild_id FROM guild_configs LIMIT 1")
            row = await cursor.fetchone()
            actual_guild_id = row[0] if row else 0
    else:
        actual_guild_id = guild_id
        
    try:
        history = await database.get_vacation_history(actual_guild_id)
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/guilds/{guild_id}/vacation-roles")
async def get_vacation_roles(guild_id: int, secondary_guild_id: Optional[str] = None, access_level: str = Depends(requires_view_access)):
    if not bot_client:
        raise HTTPException(status_code=503, detail="Discord bot is not currently running.")

    if guild_id == 0:
        async with database.aiosqlite.connect(database.DB_NAME) as db:
            cursor = await db.execute("SELECT guild_id FROM guild_configs LIMIT 1")
            row = await cursor.fetchone()
            actual_guild_id = row[0] if row else 0
    else:
        actual_guild_id = guild_id

    guild1 = bot_client.get_guild(actual_guild_id)
    if not guild1:
        try:
            guild1 = await bot_client.fetch_guild(actual_guild_id)
        except Exception:
            raise HTTPException(status_code=404, detail="Primary Guild not found or inaccessible by bot.")

    server1_roles = [{"id": str(r.id), "name": r.name} for r in guild1.roles if not r.is_default()]
    server1_name = guild1.name

    if not secondary_guild_id:
        config = await database.get_guild_config(actual_guild_id)
        secondary_guild_id = config.get("vacation_secondary_guild_id")
    
    server2_name = "Secondary Server"
    server2_roles = []
    
    if secondary_guild_id and secondary_guild_id != "0":
        try:
            sec_id = int(secondary_guild_id)
            guild2 = bot_client.get_guild(sec_id)
            if not guild2:
                guild2 = await bot_client.fetch_guild(sec_id)
            if guild2:
                server2_name = guild2.name
                server2_roles = [{"id": str(r.id), "name": r.name} for r in guild2.roles if not r.is_default()]
        except Exception as e:
            server2_name = f"Secondary Server (Error fetching: {e})"
            
    return {
        "server1_name": server1_name,
        "server1_roles": server1_roles,
        "server2_name": server2_name,
        "server2_roles": server2_roles
    }
