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

async def get_discord_user_id(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    token = authorization.split("Bearer ")[1]
    
    now = time.time()
    if token in token_cache and token_cache[token][1] > now:
        return token_cache[token][0]
        
    async with aiohttp.ClientSession() as session:
        async with session.get("https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {token}"}) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=401, detail="Invalid Discord token")
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
            
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        permission_cache[cache_key] = ("admin", now + 120)
        return "admin"
        
    config = await database.get_guild_config(guild_id)
    if config:
        role_ids = [str(r.id) for r in member.roles]
        if config.get("team_leader_role_id") in role_ids:
            permission_cache[cache_key] = ("admin", now + 120)
            return "admin"
        if config.get("moderator_role_id") in role_ids or config.get("trial_moderator_role_id") in role_ids:
            permission_cache[cache_key] = ("view", now + 120)
            return "view"
            
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
    staff: str = ""
):
    async with database.aiosqlite.connect(database.DB_NAME) as db:
        db.row_factory = database.aiosqlite.Row
        
        if guild_id == 0:
            cursor = await db.execute('''
                SELECT id, user_id, warned_at, channel_id, message_id, message_content, staff_id, reason, post_created_at, attachments 
                FROM warnings
            ''')
        else:
            cursor = await db.execute('''
                SELECT id, user_id, warned_at, channel_id, message_id, message_content, staff_id, reason, post_created_at, attachments 
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
    staff: str = ""
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


@app.get("/api/guilds/{guild_id}/analytics")
async def get_analytics(guild_id: int, period: str = "month", access_level: str = Depends(requires_view_access)):
    # period can be "week", "month", "year"
    days = 30
    if period == "week":
        days = 7
    elif period == "year":
        days = 365
        
    async with database.aiosqlite.connect(database.DB_NAME) as db:
        db.row_factory = database.aiosqlite.Row
        
        # Get warnings grouped by date
        if guild_id == 0:
            w_cursor = await db.execute(f"""
                SELECT date(warned_at) as day, COUNT(*) as count 
                FROM warnings 
                WHERE date(warned_at) >= date('now', '-{days} days')
                GROUP BY date(warned_at)
                ORDER BY day ASC
            """)
        else:
            w_cursor = await db.execute(f"""
                SELECT date(warned_at) as day, COUNT(*) as count 
                FROM warnings 
                WHERE guild_id = ? AND date(warned_at) >= date('now', '-{days} days')
                GROUP BY date(warned_at)
                ORDER BY day ASC
            """, (guild_id,))
        warn_rows = await w_cursor.fetchall()
        
        # Get paid requests grouped by date, scoped to guild
        if guild_id == 0:
            p_cursor = await db.execute(f"""
                SELECT date(created_at) as day, COUNT(*) as count 
                FROM paid_requests 
                WHERE date(created_at) >= date('now', '-{days} days')
                GROUP BY date(created_at)
                ORDER BY day ASC
            """)
        else:
            p_cursor = await db.execute(f"""
                SELECT date(created_at) as day, COUNT(*) as count 
                FROM paid_requests 
                WHERE guild_id = ? AND date(created_at) >= date('now', '-{days} days')
                GROUP BY date(created_at)
                ORDER BY day ASC
            """, (guild_id,))
        paid_rows = await p_cursor.fetchall()
        
        # Merge them into a single timeline array for Recharts
        timeline = {}
        from datetime import datetime, timedelta
        
        # Prefill timeline with 0s to ensure the chart doesn't skip days
        today = datetime.utcnow().date()
        for i in range(days):
            d = (today - timedelta(days=days - 1 - i)).isoformat()
            timeline[d] = {"date": d, "warnings": 0, "requests": 0}
            
        for r in warn_rows:
            if r["day"] in timeline:
                timeline[r["day"]]["warnings"] = r["count"]
                
        for r in paid_rows:
            if r["day"] in timeline:
                timeline[r["day"]]["requests"] = r["count"]
                
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
                if k.endswith('_id') and v is not None:
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

        # Check if exists
        cursor = await db.execute("SELECT 1 FROM guild_configs WHERE guild_id = ?", (actual_guild_id,))
        exists = await cursor.fetchone()
        
        if exists:
            await db.execute('''
                UPDATE guild_configs SET 
                    staff_notice_channel_id = ?, staff_commands_channel_id = ?, staff_log_channel_id = ?,
                    team_leader_role_id = ?, moderator_role_id = ?, trial_moderator_role_id = ?,
                    submit_channel_id = ?, review_channel_id = ?, approved_channel_id = ?, approval_log_channel_id = ?,
                    active_limit = ?, reminder_threshold = ?, accepted_currencies = ?, accepted_payments = ?, banned_terms_regex = ?,
                    dm_on_warning = ?
                WHERE guild_id = ?
            ''', (
                config.staff_notice_channel_id, config.staff_commands_channel_id, config.staff_log_channel_id,
                config.team_leader_role_id, config.moderator_role_id, config.trial_moderator_role_id,
                config.submit_channel_id, config.review_channel_id, config.approved_channel_id, config.approval_log_channel_id,
                config.active_limit, config.reminder_threshold, config.accepted_currencies, config.accepted_payments, config.banned_terms_regex,
                int(config.dm_on_warning),
                actual_guild_id
            ))
        else:
            await db.execute('''
                INSERT INTO guild_configs (
                    guild_id, staff_notice_channel_id, staff_commands_channel_id, staff_log_channel_id,
                    team_leader_role_id, moderator_role_id, trial_moderator_role_id,
                    submit_channel_id, review_channel_id, approved_channel_id, approval_log_channel_id,
                    active_limit, reminder_threshold, accepted_currencies, accepted_payments, banned_terms_regex,
                    dm_on_warning
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                actual_guild_id, config.staff_notice_channel_id, config.staff_commands_channel_id, config.staff_log_channel_id,
                config.team_leader_role_id, config.moderator_role_id, config.trial_moderator_role_id,
                config.submit_channel_id, config.review_channel_id, config.approved_channel_id, config.approval_log_channel_id,
                config.active_limit, config.reminder_threshold, config.accepted_currencies, config.accepted_payments, config.banned_terms_regex,
                int(config.dm_on_warning)
            ))
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
                        log_embed = discord.Embed(
                            title="Log: Verbal Notice Deleted/Revoked (via Dashboard)",
                            color=discord.Color.red()
                        )
                        log_embed.add_field(name="Staff Member", value="Dashboard / Web Admin", inline=True)
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
        await db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        await log_dashboard_action(guild_id, user_id, f"deleted reminder ID #{reminder_id}.")
        await db.commit()
    return {"status": "success"}
