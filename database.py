import aiosqlite
import os
import json

# Use persistent /data directory if on Railway, otherwise fallback to local file
if os.path.exists("/data") and os.access("/data", os.W_OK):
    DB_NAME = "/data/database.sqlite"
    ATTACHMENTS_DIR = "/data/attachments"
else:
    DB_NAME = "database.sqlite"
    ATTACHMENTS_DIR = "attachments"

os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

def _delete_files_for_attachments(attachments_str):
    if not attachments_str:
        return
    try:
        attachments_list = json.loads(attachments_str)
        if isinstance(attachments_list, list):
            for att in attachments_list:
                stored_name = att.get("stored_filename")
                if stored_name:
                    file_path = os.path.join(ATTACHMENTS_DIR, stored_name)
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            print(f"Deleted attachment file: {file_path}")
                        except Exception as e:
                            print(f"Error deleting attachment file {file_path}: {e}")
    except Exception as e:
        print(f"Error parsing attachments JSON: {e}")

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                warned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                message_content TEXT,
                staff_id INTEGER,
                reason TEXT,
                attachments TEXT
            )
        ''')
        
        # Safe migration if database already exists without message_content
        try:
            await db.execute('ALTER TABLE warnings ADD COLUMN message_content TEXT')
            await db.commit()
        except aiosqlite.OperationalError:
            pass # Column already exists

        # Safe migration if database already exists without staff_id
        try:
            await db.execute('ALTER TABLE warnings ADD COLUMN staff_id INTEGER')
            await db.commit()
        except aiosqlite.OperationalError:
            pass # Column already exists

        # Safe migration if database already exists without reason
        try:
            await db.execute('ALTER TABLE warnings ADD COLUMN reason TEXT')
            await db.commit()
        except aiosqlite.OperationalError:
            pass # Column already exists

        # Safe migration if database already exists without guild_id
        try:
            await db.execute('ALTER TABLE warnings ADD COLUMN guild_id INTEGER')
            await db.commit()
        except aiosqlite.OperationalError:
            pass # Column already exists

        try:
            await db.execute('ALTER TABLE warnings ADD COLUMN post_created_at TIMESTAMP')
            await db.commit()
        except aiosqlite.OperationalError:
            pass # Column already exists

        # Safe migration if database already exists without attachments
        try:
            await db.execute('ALTER TABLE warnings ADD COLUMN attachments TEXT')
            await db.commit()
        except aiosqlite.OperationalError:
            pass # Column already exists

            
        await db.execute('''
            CREATE TABLE IF NOT EXISTS paid_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                user_id INTEGER NOT NULL,
                budget TEXT NOT NULL,
                sfw_nsfw TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                use_case TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                staff_review_msg_id INTEGER,
                approved_msg_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_reminded_at TIMESTAMP,
                dm_msg_id INTEGER,
                reminder_msg_id INTEGER
            )
        ''')
        
        try:
            await db.execute('ALTER TABLE paid_requests ADD COLUMN last_reminded_at TIMESTAMP')
            await db.commit()
        except aiosqlite.OperationalError:
            pass # Column already exists

        try:
            await db.execute('ALTER TABLE paid_requests ADD COLUMN dm_msg_id INTEGER')
            await db.commit()
        except aiosqlite.OperationalError:
            pass # Column already exists

        try:
            await db.execute('ALTER TABLE paid_requests ADD COLUMN reminder_msg_id INTEGER')
            await db.commit()
        except aiosqlite.OperationalError:
            pass # Column already exists

        try:
            await db.execute('ALTER TABLE paid_requests ADD COLUMN guild_id INTEGER')
            await db.commit()
        except aiosqlite.OperationalError:
            pass # Column already exists

        try:
            await db.execute('ALTER TABLE guild_configs ADD COLUMN dm_on_warning INTEGER DEFAULT 1')
            await db.commit()
        except aiosqlite.OperationalError:
            pass # Column already exists

        try:
            await db.execute('ALTER TABLE paid_requests ADD COLUMN actioned_by INTEGER')
            await db.commit()
        except aiosqlite.OperationalError:
            pass # Column already exists

        # Vacation configurations in guild_configs
        try:
            await db.execute('ALTER TABLE guild_configs ADD COLUMN vacation_role_id INTEGER')
            await db.commit()
        except aiosqlite.OperationalError:
            pass
        try:
            await db.execute('ALTER TABLE guild_configs ADD COLUMN vacation_role_id_2 INTEGER')
            await db.commit()
        except aiosqlite.OperationalError:
            pass
        try:
            await db.execute('ALTER TABLE guild_configs ADD COLUMN vacation_secondary_guild_id INTEGER')
            await db.commit()
        except aiosqlite.OperationalError:
            pass
        try:
            await db.execute('ALTER TABLE guild_configs ADD COLUMN vacation_strip_roles_1 TEXT')
            await db.commit()
        except aiosqlite.OperationalError:
            pass
        try:
            await db.execute('ALTER TABLE guild_configs ADD COLUMN vacation_strip_roles_2 TEXT')
            await db.commit()
        except aiosqlite.OperationalError:
            pass

        # Create vacations table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS vacations (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                roles_server_1 TEXT NOT NULL,
                roles_server_2 TEXT,
                reason TEXT,
                vacation_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id)
            )
        ''')
        await db.commit()

        # Create vacation history table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS vacation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                username TEXT,
                avatar_url TEXT,
                vacation_start TEXT,
                vacation_end TEXT,
                reason TEXT,
                roles_server_1 TEXT,
                roles_server_2 TEXT
            )
        ''')
        await db.commit()

        await db.execute('''
            CREATE TABLE IF NOT EXISTS reaction_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                emoji TEXT NOT NULL,
                role_id INTEGER NOT NULL
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS reaction_role_settings (
                message_id INTEGER PRIMARY KEY,
                single_choice INTEGER DEFAULT 0
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS dropdown_menus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                placeholder TEXT NOT NULL,
                row_index INTEGER NOT NULL
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS dropdown_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                menu_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                emoji TEXT,
                role_id INTEGER NOT NULL
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                about TEXT NOT NULL,
                remind_at TIMESTAMP NOT NULL,
                channel_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Safe migration if database already exists with only 'id' as primary key
        table_exists = False
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='verbal_reasons'") as cursor:
            if await cursor.fetchone():
                table_exists = True

        if table_exists:
            async with db.execute("PRAGMA table_info(verbal_reasons)") as cursor:
                columns = await cursor.fetchall()
                pks = [col[1] for col in columns if col[5] > 0]
                
            if len(pks) == 1 and pks[0] == 'id':
                # Recreate table to support composite primary key (guild_id, id)
                await db.execute("CREATE TABLE IF NOT EXISTS verbal_reasons_backup (id TEXT, label TEXT, text TEXT, guild_id INTEGER)")
                await db.execute("INSERT INTO verbal_reasons_backup SELECT id, label, text, CASE WHEN guild_id IS NULL THEN 0 ELSE guild_id END FROM verbal_reasons")
                await db.execute("DROP TABLE verbal_reasons")
                await db.execute('''
                    CREATE TABLE verbal_reasons (
                        id TEXT NOT NULL,
                        label TEXT NOT NULL,
                        text TEXT NOT NULL,
                        guild_id INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (guild_id, id)
                    )
                ''')
                await db.execute("INSERT OR REPLACE INTO verbal_reasons (id, label, text, guild_id) SELECT id, label, text, guild_id FROM verbal_reasons_backup")
                await db.execute("DROP TABLE verbal_reasons_backup")
                await db.commit()

        await db.execute('''
            CREATE TABLE IF NOT EXISTS verbal_reasons (
                id TEXT NOT NULL,
                label TEXT NOT NULL,
                text TEXT NOT NULL,
                guild_id INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, id)
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS guild_configs (
                guild_id INTEGER PRIMARY KEY,
                staff_notice_channel_id INTEGER,
                staff_commands_channel_id INTEGER,
                staff_log_channel_id INTEGER,
                team_leader_role_id INTEGER,
                moderator_role_id INTEGER,
                trial_moderator_role_id INTEGER,
                submit_channel_id INTEGER,
                review_channel_id INTEGER,
                approved_channel_id INTEGER,
                approval_log_channel_id INTEGER,
                active_limit INTEGER DEFAULT 2,
                reminder_threshold INTEGER DEFAULT 7,
                accepted_currencies TEXT DEFAULT 'USD,EUR,GBP',
                accepted_payments TEXT DEFAULT 'PayPal,Ko-Fi,Stripe',
                banned_terms_regex TEXT DEFAULT 'robux|nitro|gift card|giftcard|crypto|btc|eth|ltc',
                vacation_role_id INTEGER,
                vacation_role_id_2 INTEGER,
                vacation_secondary_guild_id INTEGER,
                vacation_strip_roles_1 TEXT,
                vacation_strip_roles_2 TEXT
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS chatbot_menus (
                guild_id INTEGER,
                menu_id TEXT,
                response_text TEXT NOT NULL,
                PRIMARY KEY (guild_id, menu_id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS chatbot_settings (
                guild_id INTEGER PRIMARY KEY,
                dm_prompt_button INTEGER DEFAULT 0
            )
        ''')

        try:
            await db.execute('ALTER TABLE chatbot_settings ADD COLUMN dm_prompt_message TEXT')
            await db.commit()
        except aiosqlite.OperationalError:
            pass

        try:
            await db.execute('ALTER TABLE chatbot_settings ADD COLUMN dm_redirect_message TEXT')
            await db.commit()
        except aiosqlite.OperationalError:
            pass

        await db.execute('''
            CREATE TABLE IF NOT EXISTS chatbot_buttons (
                guild_id INTEGER,
                menu_id TEXT,
                button_index INTEGER,
                label TEXT NOT NULL,
                emoji TEXT,
                action TEXT NOT NULL,
                target_content TEXT NOT NULL,
                PRIMARY KEY (guild_id, menu_id, button_index)
            )
        ''')
        
        cursor = await db.execute("SELECT COUNT(*) FROM verbal_reasons")
        count = (await cursor.fetchone())[0]
        if count == 0:
            default_reasons = [
                ("underpricing", "Underpricing", "pricing below our server minimum of 15USD __per__ character, *or* below the server minimum of 5USD per 100 words for writing. Please refer to [Rule 2.4](https://discord.com/channels/369798142289510401/492328409175687179/1481767967103389727), and visit our [Commission Guide](https://discord.com/channels/369798142289510401/1393288825987665990/1476704977958469663) for more information.\n-# Note: Extra characters must also meet the server minimum of 15USD. Additionally, your post will be taken down if it has no specified currency, or uses one that is under the server minimum when converted.", 0),
                ("no_visible_pricing", "Lack of visible pricing and examples", "a lack of visible pricing and/or offer examples in your post. Be it through written text or images; offer examples, TOS, and pricing per service offered __must__ be visible in your post according to [Rule 2.1](https://discord.com/channels/369798142289510401/492328409175687179/1481767967103389727).\n-# Note: Refer to our [Local Rules](https://discord.com/channels/369798142289510401/1393271200729268294/1476738956396597290) per channel for more information.", 0),
                ("no_tos_mention", "Lack of/No mentions of ToS", "not having your Terms of Service linked or displayed properly, or indicated as to where they can be found. Refer to [Rule 2.1](https://discord.com/channels/369798142289510401/492328409175687179/1481767967103389727), read through the <#492328409175687179> before posting, and visit our [TOS Guide](https://discord.com/channels/369798142289510401/1191922480961552424/1191922480961552424) for examples on how your terms should be written.\n-# Note: If not directly displayed in your post; you __must__ state where your terms can be found, such as in a specific link or website. Buyers should not have to message you for additional information.", 0),
                ("incomplete_tos", "Incomplete ToS", "insufficient information in your Terms of Service. Please keep in mind that __ALL__ of the following sections must be included __and__ elaborated on, based on [Rule 2.1](https://discord.com/channels/369798142289510401/492328409175687179/1324496338985029662): \n> Offers, Specified commission rights for seller and buyer, Payment method, Refund policy, and Contact.\nPlease read through the <#492328409175687179> before posting, and visit our [TOS Guide](https://discord.com/channels/369798142289510401/1191922480961552424/1191922480961552424) for examples on how to elaborate.\n-# Note: Please explicitly mention \"Terms of Service\" in your post rather than just generally listing your terms.", 0),
                ("wrong_channel", "Advertising in wrong channel", "advertising services outside of its designated [server category](https://discord.com/channels/369798142289510401/1393271200729268294/1476738956396597290). Please ensure your post does not contain any form of advertising if it isn't allowed by its local channel ruling. Refer to this [list](https://discord.com/channels/369798142289510401/1393288825987665990/1476704979598442662) to find what designated channel your services would fall under.", 0),
                ("wrong_channel_no_role", "Advertising in wrong channel + no role", "advertising services outside of its designated [server category](https://discord.com/channels/369798142289510401/1393271200729268294/1476738956396597290), and without the Art Seller role. Please refer [here](https://discord.com/channels/369798142289510401/635030026911481856/1490007480955179180) for information on how to the obtain the Art Seller role.", 0),
                ("chatting_daily_wins", "Chatting in daily w", "as the <#873116269640036362> channel is meant only for __posting__ positive achievements, and cannot be used for chatting. To respond to someone's daily win, please only use reaction emotes.", 0),
                ("critique_format", "Critique format", "not following the format found in the channel's pins. Please follow the rules per channel. If unsure on how to formulate your critique request, or if you have any questions, please message staff at <@501746915218554881>.", 0),
                ("art_in_chats", "Art in chats", "posting art/writing work unrelated to current conversation topic. Please refer to channel pins for local ruling, as all art and writing should be shared to <#369833248240566282> or <#616268995246424097> instead.", 0)
            ]
            await db.executemany("INSERT INTO verbal_reasons (id, label, text, guild_id) VALUES (?, ?, ?, ?)", default_reasons)

        # Import chatbot config from JSON if database is empty
        cursor = await db.execute("SELECT COUNT(*) FROM chatbot_menus")
        chatbot_count = (await cursor.fetchone())[0]
        if chatbot_count == 0:
            try:
                import json
                import os
                config_path = "chatbot_config.json"
                if os.path.exists(config_path):
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_data = json.load(f)
                    await save_chatbot_config(0, config_data)
                    print("Imported chatbot_config.json into database as global default (guild_id=0).")
            except Exception as e:
                print(f"Error importing default chatbot config: {e}")

        await db.commit()

# --- Verbal Reasons Methods ---

async def get_all_verbal_reasons(guild_id: int = 0) -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM verbal_reasons WHERE guild_id = ? OR (guild_id IS NULL AND ? = 0)", (guild_id, guild_id))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_verbal_reason(guild_id: int, reason_id: str) -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM verbal_reasons WHERE id = ? AND (guild_id = ? OR (guild_id IS NULL AND ? = 0))", (reason_id, guild_id, guild_id))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def add_verbal_reason(guild_id: int, reason_id: str, label: str, text: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO verbal_reasons (id, label, text, guild_id) VALUES (?, ?, ?, ?)", (reason_id, label, text, guild_id))
        await db.commit()

async def delete_verbal_reason(guild_id: int, reason_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM verbal_reasons WHERE id = ? AND (guild_id = ? OR (guild_id IS NULL AND ? = 0))", (reason_id, guild_id, guild_id))
        await db.commit()

async def get_guild_config(guild_id: int):
    """Fetch configuration for a guild, or fallback to defaults."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        
        if guild_id == 0:
            cursor = await db.execute("SELECT * FROM guild_configs WHERE guild_id = 0")
        else:
            cursor = await db.execute("SELECT * FROM guild_configs WHERE guild_id = ?", (guild_id,))
            
        row = await cursor.fetchone()
        if row:
            d = dict(row)
            # Safe conversion of Discord IDs and booleans to integers
            keys_to_cast = [
                "guild_id", "staff_notice_channel_id", "staff_commands_channel_id", "staff_log_channel_id",
                "team_leader_role_id", "moderator_role_id", "trial_moderator_role_id",
                "submit_channel_id", "review_channel_id", "approved_channel_id", "approval_log_channel_id",
                "dm_on_warning", "vacation_role_id", "vacation_role_id_2", "vacation_secondary_guild_id"
            ]
            for k in keys_to_cast:
                if k in d and d[k] is not None:
                    try:
                        d[k] = int(d[k])
                    except (ValueError, TypeError):
                        d[k] = 0
            return d

            
        # Return sensible defaults if no config is set
        return {
            "staff_notice_channel_id": 0,
            "staff_commands_channel_id": 0,
            "staff_log_channel_id": 0,
            "team_leader_role_id": 0,
            "moderator_role_id": 0,
            "trial_moderator_role_id": 0,
            "submit_channel_id": 0,
            "review_channel_id": 0,
            "approved_channel_id": 0,
            "approval_log_channel_id": 0,
            "active_limit": 2,
            "reminder_threshold": 14,
            "accepted_currencies": "USD, EUR, GBP, CAD, AUD, \\$|£|€",
            "accepted_payments": "PayPal, Stripe, CashApp, Venmo, Ko-Fi",
            "banned_terms_regex": "robux|robuck|robucks|crypto|btc|eth|sol|ltc|usdt|usdc",
            "dm_on_warning": 1,
            "vacation_role_id": 0,
            "vacation_role_id_2": 0,
            "vacation_secondary_guild_id": 0,
            "vacation_strip_roles_1": "",
            "vacation_strip_roles_2": ""
        }

async def migrate_env_to_db(guild_id: int):
    """One-time migration to copy .env variables into the database for the given guild if empty."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM guild_configs WHERE guild_id = ?", (guild_id,))
        count = (await cursor.fetchone())[0]
        if count == 0:
            import os
            # Read from os.environ since load_dotenv() was called in bot.py
            await db.execute('''
                INSERT INTO guild_configs (
                    guild_id, 
                    staff_notice_channel_id, staff_commands_channel_id, staff_log_channel_id,
                    team_leader_role_id, moderator_role_id, trial_moderator_role_id,
                    submit_channel_id, review_channel_id, approved_channel_id, approval_log_channel_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                guild_id,
                int(os.getenv("STAFF_NOTICE_CHANNEL_ID") or 0),
                int(os.getenv("STAFF_COMMANDS_CHANNEL_ID") or 0),
                int(os.getenv("STAFF_LOG_CHANNEL_ID") or 0),
                int(os.getenv("TEAM_LEADER_ROLE_ID") or 0),
                int(os.getenv("MODERATOR_ROLE_ID") or 0),
                int(os.getenv("TRIAL_MODERATOR_ROLE_ID") or 0),
                int(os.getenv("SUBMIT_PAID_REQUEST_CHANNEL_ID") or 0),
                int(os.getenv("PAID_REQUEST_REVIEW_CHANNEL_ID") or 0),
                int(os.getenv("PAID_REQUEST_APPROVED_CHANNEL_ID") or 0),
                int(os.getenv("APPROVAL_LOG_CHANNEL_ID") or 0)
            ))
            await db.commit()
            print(f"Migrated .env config to database for guild {guild_id}")

# --- Warning Tracker Methods ---

async def add_warning(user_id: int, channel_id: int, message_id: int, message_content: str, staff_id: int = None, reason: str = None, warned_at: str = None, post_created_at: str = None, guild_id: int = None, attachments: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        if warned_at:
            cursor = await db.execute('''
                INSERT INTO warnings (user_id, channel_id, message_id, message_content, staff_id, reason, warned_at, post_created_at, guild_id, attachments)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, channel_id, message_id, message_content, staff_id, reason, warned_at, post_created_at, guild_id, attachments))
        else:
            cursor = await db.execute('''
                INSERT INTO warnings (user_id, channel_id, message_id, message_content, staff_id, reason, post_created_at, guild_id, attachments)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, channel_id, message_id, message_content, staff_id, reason, post_created_at, guild_id, attachments))
        await db.commit()
        return cursor.lastrowid

async def revoke_warning(warning_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT attachments FROM warnings WHERE id = ?', (warning_id,))
        row = await cursor.fetchone()
        if row and row['attachments']:
            _delete_files_for_attachments(row['attachments'])
        await db.execute('DELETE FROM warnings WHERE id = ?', (warning_id,))
        await db.commit()

async def warning_exists(message_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('''
            SELECT 1 FROM warnings WHERE message_id = ? AND user_id = ?
        ''', (message_id, user_id))
        row = await cursor.fetchone()
        return row is not None

async def get_warnings_count_last_3_months(user_id: int, guild_id: int = None) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        if guild_id:
            cursor = await db.execute('''
                SELECT COUNT(*) FROM warnings 
                WHERE user_id = ? AND (guild_id = ? OR guild_id IS NULL) AND warned_at >= datetime('now', '-3 months')
            ''', (user_id, guild_id))
        else:
            cursor = await db.execute('''
                SELECT COUNT(*) FROM warnings 
                WHERE user_id = ? AND warned_at >= datetime('now', '-3 months')
            ''', (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0

async def get_warnings_count_last_30_days(user_id: int) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('''
            SELECT COUNT(*) FROM warnings 
            WHERE user_id = ? AND warned_at >= datetime('now', '-30 days')
        ''', (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0

async def get_last_warning_staff_id_last_30_days(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('''
            SELECT staff_id FROM warnings
            WHERE user_id = ? AND staff_id IS NOT NULL AND warned_at >= datetime('now', '-30 days')
            ORDER BY warned_at DESC
            LIMIT 1
        ''', (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def get_last_warning_staff_id_last_3_months(user_id: int, guild_id: int = None):
    async with aiosqlite.connect(DB_NAME) as db:
        if guild_id:
            cursor = await db.execute('''
                SELECT staff_id FROM warnings
                WHERE user_id = ? AND (guild_id = ? OR guild_id IS NULL) AND staff_id IS NOT NULL AND warned_at >= datetime('now', '-3 months')
                ORDER BY warned_at DESC
                LIMIT 1
            ''', (user_id, guild_id))
        else:
            cursor = await db.execute('''
                SELECT staff_id FROM warnings
                WHERE user_id = ? AND staff_id IS NOT NULL AND warned_at >= datetime('now', '-3 months')
                ORDER BY warned_at DESC
                LIMIT 1
            ''', (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def get_warnings_last_3_months(user_id: int, guild_id: int = None):
    async with aiosqlite.connect(DB_NAME) as db:
        if guild_id:
            cursor = await db.execute('''
                SELECT id, reason, warned_at FROM warnings
                WHERE user_id = ? AND (guild_id = ? OR guild_id IS NULL) AND warned_at >= datetime('now', '-3 months')
                ORDER BY warned_at DESC
            ''', (user_id, guild_id))
        else:
            cursor = await db.execute('''
                SELECT id, reason, warned_at FROM warnings
                WHERE user_id = ? AND warned_at >= datetime('now', '-3 months')
                ORDER BY warned_at DESC
            ''', (user_id,))
        return await cursor.fetchall()

async def get_warnings_paginated(user_id: int, limit: int, offset: int, guild_id: int = None):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        if guild_id:
            cursor = await db.execute('''
                SELECT id, warned_at, channel_id, message_id, message_content, staff_id, reason FROM warnings
                WHERE user_id = ? AND (guild_id = ? OR guild_id IS NULL)
                ORDER BY warned_at DESC
                LIMIT ? OFFSET ?
            ''', (user_id, guild_id, limit, offset))
        else:
            cursor = await db.execute('''
                SELECT id, warned_at, channel_id, message_id, message_content, staff_id, reason FROM warnings
                WHERE user_id = ?
                ORDER BY warned_at DESC
                LIMIT ? OFFSET ?
            ''', (user_id, limit, offset))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_warnings_count(user_id: int, guild_id: int = None) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        if guild_id:
            cursor = await db.execute('SELECT COUNT(*) FROM warnings WHERE user_id = ? AND (guild_id = ? OR guild_id IS NULL)', (user_id, guild_id))
        else:
            cursor = await db.execute('SELECT COUNT(*) FROM warnings WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0

async def get_warning_by_id(warning_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM warnings WHERE id = ?', (warning_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def delete_warning_by_id(warning_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT attachments FROM warnings WHERE id = ?', (warning_id,))
        row = await cursor.fetchone()
        if not row:
            return False
        if row['attachments']:
            _delete_files_for_attachments(row['attachments'])
        await db.execute('DELETE FROM warnings WHERE id = ?', (warning_id,))
        await db.commit()
        return True

async def get_warnings_by_staff_paginated(staff_id: int, limit: int, offset: int, guild_id: int = None):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        if guild_id:
            cursor = await db.execute('''
                SELECT id, user_id, warned_at, channel_id, message_id, message_content, reason FROM warnings
                WHERE staff_id = ? AND (guild_id = ? OR guild_id IS NULL)
                ORDER BY warned_at DESC
                LIMIT ? OFFSET ?
            ''', (staff_id, guild_id, limit, offset))
        else:
            cursor = await db.execute('''
                SELECT id, user_id, warned_at, channel_id, message_id, message_content, reason FROM warnings
                WHERE staff_id = ?
                ORDER BY warned_at DESC
                LIMIT ? OFFSET ?
            ''', (staff_id, limit, offset))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_warnings_by_staff_count(staff_id: int, guild_id: int = None) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        if guild_id:
            cursor = await db.execute('SELECT COUNT(*) FROM warnings WHERE staff_id = ? AND (guild_id = ? OR guild_id IS NULL)', (staff_id, guild_id))
        else:
            cursor = await db.execute('SELECT COUNT(*) FROM warnings WHERE staff_id = ?', (staff_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0

# --- Paid Request Methods ---

async def create_paid_request(guild_id: int, user_id: int, budget: str, sfw_nsfw: str, payment_method: str, use_case: str, content: str) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('''
            INSERT INTO paid_requests (guild_id, user_id, budget, sfw_nsfw, payment_method, use_case, content)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (guild_id, user_id, budget, sfw_nsfw, payment_method, use_case, content))
        await db.commit()
        return cursor.lastrowid

async def get_paid_request(request_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM paid_requests WHERE request_id = ?', (request_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def update_paid_request_review_msg(request_id: int, msg_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('UPDATE paid_requests SET staff_review_msg_id = ? WHERE request_id = ?', (msg_id, request_id))
        await db.commit()

async def update_paid_request_status(request_id: int, status: str, approved_msg_id: int = None, actioned_by: int = None):
    async with aiosqlite.connect(DB_NAME) as db:
        if approved_msg_id and actioned_by:
            await db.execute('UPDATE paid_requests SET status = ?, approved_msg_id = ?, actioned_by = ? WHERE request_id = ?', (status, approved_msg_id, actioned_by, request_id))
        elif approved_msg_id:
            await db.execute('UPDATE paid_requests SET status = ?, approved_msg_id = ? WHERE request_id = ?', (status, approved_msg_id, request_id))
        elif actioned_by:
            await db.execute('UPDATE paid_requests SET status = ?, actioned_by = ? WHERE request_id = ?', (status, actioned_by, request_id))
        else:
            await db.execute('UPDATE paid_requests SET status = ? WHERE request_id = ?', (status, request_id))
        await db.commit()

async def update_paid_request_details(request_id: int, budget: str, sfw_nsfw: str, payment_method: str, use_case: str, content: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            UPDATE paid_requests 
            SET budget = ?, sfw_nsfw = ?, payment_method = ?, use_case = ?, content = ? 
            WHERE request_id = ?
        ''', (budget, sfw_nsfw, payment_method, use_case, content, request_id))
        await db.commit()

async def get_last_submitted_request(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            SELECT * FROM paid_requests
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        ''', (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def get_paid_requests_for_reminders(age_days: float = 30.0) -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        # Calculate time threshold in seconds
        seconds = int(age_days * 86400.0)
        cursor = await db.execute('''
            SELECT * FROM paid_requests
            WHERE status = 'approved'
              AND datetime(created_at) < datetime('now', ?)
              AND (last_reminded_at IS NULL OR datetime(last_reminded_at) < datetime('now', ?))
        ''', (f'-{seconds} seconds', f'-{seconds} seconds'))
        return await cursor.fetchall()

async def update_paid_request_reminded_time(request_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            UPDATE paid_requests
            SET last_reminded_at = CURRENT_TIMESTAMP
            WHERE request_id = ?
        ''', (request_id,))
        await db.commit()

async def update_paid_request_dm_msg(request_id: int, dm_msg_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            UPDATE paid_requests
            SET dm_msg_id = ?
            WHERE request_id = ?
        ''', (dm_msg_id, request_id))
        await db.commit()

async def update_paid_request_reminder_msg(request_id: int, reminder_msg_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            UPDATE paid_requests
            SET reminder_msg_id = ?
            WHERE request_id = ?
        ''', (reminder_msg_id, request_id))
        await db.commit()


async def get_active_paid_requests_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('''
            SELECT COUNT(*) FROM paid_requests
            WHERE user_id = ? AND status IN ('pending', 'approved')
        ''', (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0

async def get_pending_paid_requests() -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM paid_requests WHERE status = 'pending'")
        return await cursor.fetchall()

async def purge_all_paid_requests():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM paid_requests")
        await db.execute("DELETE FROM sqlite_sequence WHERE name = 'paid_requests'")
        await db.commit()

async def purge_all_warnings():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM warnings")
        await db.execute("DELETE FROM sqlite_sequence WHERE name = 'warnings'")
        await db.commit()

    if os.path.exists(ATTACHMENTS_DIR):
        for filename in os.listdir(ATTACHMENTS_DIR):
            file_path = os.path.join(ATTACHMENTS_DIR, filename)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Failed to delete {file_path}: {e}")



# --- Reaction Roles Methods ---

async def add_reaction_role(message_id: int, guild_id: int, emoji: str, role_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO reaction_roles (message_id, guild_id, emoji, role_id)
            VALUES (?, ?, ?, ?)
        ''', (message_id, guild_id, emoji, role_id))
        await db.commit()

async def get_reaction_roles_for_message(message_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM reaction_roles WHERE message_id = ?', (message_id,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def delete_reaction_roles_for_message(message_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('DELETE FROM reaction_roles WHERE message_id = ?', (message_id,))
        await db.commit()

async def remove_reaction_role(message_id: int, emoji: str, role_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            DELETE FROM reaction_roles 
            WHERE message_id = ? AND emoji = ? AND role_id = ?
        ''', (message_id, emoji, role_id))
        await db.commit()

async def set_message_reaction_role_settings(message_id: int, single_choice: bool):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO reaction_role_settings (message_id, single_choice)
            VALUES (?, ?)
            ON CONFLICT(message_id) DO UPDATE SET single_choice = excluded.single_choice
        ''', (message_id, 1 if single_choice else 0))
        await db.commit()

async def get_message_reaction_role_settings(message_id: int) -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM reaction_role_settings WHERE message_id = ?', (message_id,))
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return {"message_id": message_id, "single_choice": 0}

# --- Dropdown Roles Methods ---

async def add_dropdown_menu(message_id: int, placeholder: str, row_index: int) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('''
            INSERT INTO dropdown_menus (message_id, placeholder, row_index)
            VALUES (?, ?, ?)
        ''', (message_id, placeholder, row_index))
        await db.commit()
        return cursor.lastrowid

async def add_dropdown_option(menu_id: int, label: str, emoji: str, role_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO dropdown_options (menu_id, label, emoji, role_id)
            VALUES (?, ?, ?, ?)
        ''', (menu_id, label, emoji, role_id))
        await db.commit()

async def get_dropdowns_for_message(message_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        
        # Get menus
        cursor = await db.execute('SELECT * FROM dropdown_menus WHERE message_id = ? ORDER BY row_index ASC', (message_id,))
        menus = [dict(row) for row in await cursor.fetchall()]
        
        # Get options for each menu
        for menu in menus:
            cursor = await db.execute('SELECT * FROM dropdown_options WHERE menu_id = ?', (menu['id'],))
            menu['options'] = [dict(row) for row in await cursor.fetchall()]
            
        return menus

async def delete_dropdowns_for_message(message_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        # First find menus
        cursor = await db.execute('SELECT id FROM dropdown_menus WHERE message_id = ?', (message_id,))
        menus = await cursor.fetchall()
        
        for (menu_id,) in menus:
            await db.execute('DELETE FROM dropdown_options WHERE menu_id = ?', (menu_id,))
            
        await db.execute('DELETE FROM dropdown_menus WHERE message_id = ?', (message_id,))
        await db.commit()

# --- Reminders Methods ---

async def add_reminder(user_id: int, about: str, remind_at: str, channel_id: int = None) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('''
            INSERT INTO reminders (user_id, about, remind_at, channel_id)
            VALUES (?, ?, ?, ?)
        ''', (user_id, about, remind_at, channel_id))
        await db.commit()
        return cursor.lastrowid

async def get_due_reminders() -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            SELECT * FROM reminders WHERE remind_at <= datetime('now')
        ''')
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def delete_reminder(reminder_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('DELETE FROM reminders WHERE id = ?', (reminder_id,))
        await db.commit()


# --- Chatbot Config Methods ---

async def get_chatbot_config(guild_id: int) -> dict:
    """Fetch the chatbot configuration for a guild from the database.
    If none exists, returns default template structure.
    """
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        
        # 1. Fetch all menus for this guild
        cursor = await db.execute("SELECT menu_id, response_text FROM chatbot_menus WHERE guild_id = ?", (guild_id,))
        menu_rows = await cursor.fetchall()
        
        # 2. Fetch all buttons for this guild
        cursor = await db.execute(
            "SELECT menu_id, button_index, label, emoji, action, target_content FROM chatbot_buttons WHERE guild_id = ? ORDER BY menu_id, button_index", 
            (guild_id,)
        )
        button_rows = await cursor.fetchall()
        
        # 3. Fetch chatbot settings
        cursor = await db.execute("SELECT dm_prompt_button, dm_prompt_message, dm_redirect_message FROM chatbot_settings WHERE guild_id = ?", (guild_id,))
        settings_row = await cursor.fetchone()
        dm_prompt = settings_row["dm_prompt_button"] == 1 if settings_row else False
        dm_prompt_message = settings_row["dm_prompt_message"] if settings_row else None
        dm_redirect_message = settings_row["dm_redirect_message"] if settings_row else None
        
    # Build buttons map by menu_id
    buttons_by_menu = {}
    for r in button_rows:
        menu_id = r["menu_id"]
        if menu_id not in buttons_by_menu:
            buttons_by_menu[menu_id] = []
            
        # Reconstruct JSON format
        btn_dict = {
            "label": r["label"],
            "emoji": r["emoji"],
            "action": r["action"]
        }
        if r["action"] == "menu":
            btn_dict["target"] = r["target_content"]
        else:
            btn_dict["text"] = r["target_content"]
            
        buttons_by_menu[menu_id].append(btn_dict)

    # Reconstruct JSON format configuration
    config = {
        "main_menu": {
            "text": "Hello! I'm Carrot and I can help you with answering with questions you might have! \n\nTo get started, please select from provided options:",
            "buttons": []
        },
        "menus": {},
        "dm_prompt_button": dm_prompt,
        "dm_prompt_message": dm_prompt_message,
        "dm_redirect_message": dm_redirect_message
    }
    
    for r in menu_rows:
        menu_id = r["menu_id"]
        menu_text = r["response_text"]
        menu_buttons = buttons_by_menu.get(menu_id, [])
        
        if menu_id == "main_menu":
            config["main_menu"] = {
                "text": menu_text,
                "buttons": menu_buttons
            }
        else:
            config["menus"][menu_id] = {
                "text": menu_text,
                "buttons": menu_buttons
            }
            
    # If no custom configuration exists in the database for this guild, return defaults
    if not menu_rows and guild_id != 0:
        return await get_chatbot_config(0)
        
    return config

async def save_chatbot_config(guild_id: int, config: dict):
    """Save the chatbot configuration for a guild to the database."""
    async with aiosqlite.connect(DB_NAME) as db:
        # Delete existing menus and buttons for this guild
        await db.execute("DELETE FROM chatbot_menus WHERE guild_id = ?", (guild_id,))
        await db.execute("DELETE FROM chatbot_buttons WHERE guild_id = ?", (guild_id,))
        
        # Save chatbot settings
        dm_prompt = 1 if config.get("dm_prompt_button", False) else 0
        dm_prompt_message = config.get("dm_prompt_message", None)
        dm_redirect_message = config.get("dm_redirect_message", None)
        await db.execute(
            "INSERT OR REPLACE INTO chatbot_settings (guild_id, dm_prompt_button, dm_prompt_message, dm_redirect_message) VALUES (?, ?, ?, ?)",
            (guild_id, dm_prompt, dm_prompt_message, dm_redirect_message)
        )
        
        # Save main menu
        main_menu = config.get("main_menu", {})
        main_text = main_menu.get("text", "Hello!")
        await db.execute(
            "INSERT INTO chatbot_menus (guild_id, menu_id, response_text) VALUES (?, ?, ?)",
            (guild_id, "main_menu", main_text)
        )
        
        # Save main menu buttons
        for idx, btn in enumerate(main_menu.get("buttons", [])):
            target_content = btn.get("target") if btn.get("action") == "menu" else btn.get("text", "")
            await db.execute(
                "INSERT INTO chatbot_buttons (guild_id, menu_id, button_index, label, emoji, action, target_content) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (guild_id, "main_menu", idx, btn.get("label"), btn.get("emoji"), btn.get("action"), target_content)
            )
            
        # Save sub menus
        menus = config.get("menus", {})
        for menu_id, menu_data in menus.items():
            menu_text = menu_data.get("text", "...")
            await db.execute(
                "INSERT INTO chatbot_menus (guild_id, menu_id, response_text) VALUES (?, ?, ?)",
                (guild_id, menu_id, menu_text)
            )
            
            for idx, btn in enumerate(menu_data.get("buttons", [])):
                target_content = btn.get("target") if btn.get("action") == "menu" else btn.get("text", "")
                await db.execute(
                    "INSERT INTO chatbot_buttons (guild_id, menu_id, button_index, label, emoji, action, target_content) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (guild_id, menu_id, idx, btn.get("label"), btn.get("emoji"), btn.get("action"), target_content)
                )
                
        await db.commit()

async def add_vacation_record(user_id: int, guild_id: int, roles_server_1: str, roles_server_2: str, reason: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO vacations (user_id, guild_id, roles_server_1, roles_server_2, reason) VALUES (?, ?, ?, ?, ?)",
            (user_id, guild_id, roles_server_1, roles_server_2, reason)
        )
        await db.commit()

async def get_vacation_record(user_id: int, guild_id: int) -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM vacations WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def remove_vacation_record(user_id: int, guild_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM vacations WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        await db.commit()

async def get_all_active_vacations(guild_id: int) -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM vacations WHERE guild_id = ? ORDER BY vacation_start DESC", (guild_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def add_vacation_history_record(user_id: int, guild_id: int, username: str, avatar_url: str, vacation_start: str, vacation_end: str, reason: str, roles_server_1: str, roles_server_2: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """INSERT INTO vacation_history 
               (user_id, guild_id, username, avatar_url, vacation_start, vacation_end, reason, roles_server_1, roles_server_2) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, guild_id, username, avatar_url, vacation_start, vacation_end, reason, roles_server_1, roles_server_2)
        )
        await db.commit()

async def get_vacation_history(guild_id: int) -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM vacation_history WHERE guild_id = ? ORDER BY vacation_end DESC", (guild_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def cleanup_attachments():
    """
    1. 30-Day Retention Policy: Delete attachments for warnings older than 30 days.
    2. Orphan Cleanup: Delete files not referenced in the database.
    """
    if not os.path.exists(ATTACHMENTS_DIR):
        return

    print("Starting attachments cleanup and retention policy execution...")
    
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        
        # 1. Retention Policy
        cursor = await db.execute('''
            SELECT id, attachments FROM warnings 
            WHERE (warned_at < datetime('now', '-30 days') OR post_created_at < datetime('now', '-30 days'))
              AND attachments IS NOT NULL
        ''')
        old_warnings = await cursor.fetchall()
        
        deleted_count = 0
        for warning in old_warnings:
            attachments_str = warning['attachments']
            _delete_files_for_attachments(attachments_str)
            await db.execute('UPDATE warnings SET attachments = NULL WHERE id = ?', (warning['id'],))
            deleted_count += 1
            
        if deleted_count > 0:
            await db.commit()
            print(f"Removed attachments from {deleted_count} warnings older than 30 days.")
            
        # 2. Orphan Cleanup
        cursor = await db.execute('SELECT attachments FROM warnings WHERE attachments IS NOT NULL')
        rows = await cursor.fetchall()
        
        active_filenames = set()
        for row in rows:
            attachments_str = row['attachments']
            try:
                attachments_list = json.loads(attachments_str)
                if isinstance(attachments_list, list):
                    for att in attachments_list:
                        stored_name = att.get("stored_filename")
                        if stored_name:
                            active_filenames.add(stored_name)
            except Exception:
                pass
                
        files_in_dir = os.listdir(ATTACHMENTS_DIR)
        orphaned_count = 0
        for filename in files_in_dir:
            if filename not in active_filenames:
                file_path = os.path.join(ATTACHMENTS_DIR, filename)
                if os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                        orphaned_count += 1
                    except Exception as e:
                        print(f"Error removing orphaned file {filename}: {e}")
                        
        print(f"Orphan cleanup finished. Deleted {orphaned_count} orphaned attachment files.")
