import sqlite3
import random
from datetime import datetime, timedelta

def insert_mock_data():
    conn = sqlite3.connect('database.sqlite')
    cursor = conn.cursor()
    
    statuses = ['pending', 'approved', 'rejected', 'fulfilled', 'closed', 'invalid']
    guild_ids = [312644233930473472, 1437362160211726452]
    
    # First, delete the previous incorrect mock data
    cursor.execute('DELETE FROM paid_requests WHERE guild_id = 1510670954097807570')
    
    for guild_id in guild_ids:
        for idx, status in enumerate(statuses):
            user_id = 111222333444 + idx
            budget = f"{random.randint(10, 100)} USD"
            sfw_nsfw = "SFW" if idx % 2 == 0 else "NSFW"
            payment_method = "PayPal"
            use_case = "Personal"
            content = f"Mock Paid Request - {status.capitalize()} (Guild {guild_id})"
            
            staff_review_msg_id = random.randint(100000000000000000, 999999999999999999)
            approved_msg_id = random.randint(100000000000000000, 999999999999999999) if status in ['approved', 'fulfilled', 'closed'] else None
            actioned_by = random.randint(100000000000000000, 999999999999999999) if status != 'pending' else None
            
            # Insert
            cursor.execute('''
                INSERT INTO paid_requests 
                (guild_id, user_id, budget, sfw_nsfw, payment_method, use_case, content, status, staff_review_msg_id, approved_msg_id, actioned_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (guild_id, user_id, budget, sfw_nsfw, payment_method, use_case, content, status, staff_review_msg_id, approved_msg_id, actioned_by))
        
    conn.commit()
    conn.close()
    print(f"Inserted {len(statuses) * len(guild_ids)} mock records into paid_requests table.")

if __name__ == '__main__':
    insert_mock_data()
