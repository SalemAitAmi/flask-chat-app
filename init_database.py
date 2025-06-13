#!/usr/bin/python3
import sqlite3
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
from utils import encrypt_message, get_key

"""
New Database Structure:
    user_table: Contains the usernames and hashed passwords for all registered users
    conversations: Contains conversation IDs and metadata (creation time, name if group chat)
    conversation_participants: Maps users to conversations they're part of
    messages: Contains all messages with sender, conversation ID, content, and timestamp
"""

def create_sample_conversation(conn):
    """Create a sample conversation between Alice and Boby with messages from various dates"""
    c = conn.cursor()
    
    try:
        # Get encryption key for message encryption
        secret_key = get_key('secret.key')
        
        # Create a conversation
        c.execute("INSERT INTO conversations (created_at) VALUES (?)", (int(datetime.now().timestamp()),))
        conversation_id = c.lastrowid
        
        # Add participants
        c.execute("INSERT INTO conversation_participants (conversation_id, username) VALUES (?, ?)", 
                 (conversation_id, "Alice"))
        c.execute("INSERT INTO conversation_participants (conversation_id, username) VALUES (?, ?)", 
                 (conversation_id, "Boby"))
        
        # Create message samples for different time periods
        now = datetime.now()
        
        message_samples = [
            # Today
            {"date": now, "sender": "Alice", "message": "Hi Boby, how are you today?"},
            {"date": now - timedelta(minutes=5), "sender": "Boby", "message": "I'm great! Just finishing up some work."},
            {"date": now - timedelta(minutes=3), "sender": "Alice", "message": "Can we meet later?"},
            {"date": now - timedelta(minutes=2), "sender": "Boby", "message": "Sure, how about 6pm?"},
            
            # Yesterday
            {"date": now - timedelta(days=1, hours=2), "sender": "Alice", "message": "Did you finish the report?"},
            {"date": now - timedelta(days=1, hours=1, minutes=55), "sender": "Boby", "message": "Yes, sent it to you by email."},
            {"date": now - timedelta(days=1, hours=1), "sender": "Alice", "message": "Got it, thanks!"},
            
            # Previous week (7 days back to 2 days back)
            {"date": now - timedelta(days=2, hours=5), "sender": "Boby", "message": "Are we still on for lunch tomorrow?"},
            {"date": now - timedelta(days=2, hours=4), "sender": "Alice", "message": "Yes, let's meet at noon."},
            
            {"date": now - timedelta(days=3, hours=8), "sender": "Alice", "message": "Don't forget the meeting at 3pm."},
            {"date": now - timedelta(days=3, hours=7), "sender": "Boby", "message": "I'll be there!"},
            
            {"date": now - timedelta(days=4, hours=12), "sender": "Boby", "message": "Have you seen the new project specs?"},
            {"date": now - timedelta(days=4, hours=11), "sender": "Alice", "message": "Yes, looks challenging but fun."},
            
            {"date": now - timedelta(days=5, hours=3), "sender": "Alice", "message": "Weekend plans?"},
            {"date": now - timedelta(days=5, hours=2), "sender": "Boby", "message": "Hiking on Saturday, want to join?"},
            
            {"date": now - timedelta(days=6, hours=18), "sender": "Boby", "message": "Just finished the book you recommended."},
            {"date": now - timedelta(days=6, hours=17), "sender": "Alice", "message": "What did you think?"},
            
            {"date": now - timedelta(days=7, hours=9), "sender": "Alice", "message": "Morning, do you have the notes from last week?"},
            {"date": now - timedelta(days=7, hours=8, minutes=30), "sender": "Boby", "message": "Yes, I'll share the Google Doc."},
            
            # 10 days back
            {"date": now - timedelta(days=10, hours=11), "sender": "Boby", "message": "Happy Monday! Ready for the big project?"},
            {"date": now - timedelta(days=10, hours=10), "sender": "Alice", "message": "All set and excited!"},
            
            # 1 month back
            {"date": now - timedelta(days=30, hours=14), "sender": "Alice", "message": "Remember we need to renew the subscription next month."},
            {"date": now - timedelta(days=30, hours=13), "sender": "Boby", "message": "Noted, I'll set a reminder."}
        ]
        
        # Insert messages with appropriate timestamps
        for item in message_samples:
            timestamp = int(item["date"].timestamp())
            encrypted_message = encrypt_message(item["message"], secret_key)
            c.execute("INSERT INTO messages (conversation_id, sender, message, timestamp) VALUES (?, ?, ?, ?)",
                     (conversation_id, item["sender"], encrypted_message, timestamp))
        
    except Exception as e:
        print(f"Error creating sample conversation: {e}")
    
    conn.commit()

if __name__ == '__main__':
    conn = sqlite3.connect('chat_database')
    c = conn.cursor()

    try:
        # Create user table
        c.execute('''
            CREATE TABLE IF NOT EXISTS user_table (
                username VARCHAR(256) NOT NULL,
                password VARCHAR(256) NOT NULL,
                timezone VARCHAR(64) DEFAULT "UTC" NOT NULL,
                PRIMARY KEY (username)
            )
        ''')
        
        # Create conversations table
        c.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                is_group_chat BOOLEAN DEFAULT 0,
                created_at INTEGER NOT NULL
            )
        ''')
        
        # Create conversation participants table
        c.execute('''
            CREATE TABLE IF NOT EXISTS conversation_participants (
                conversation_id INTEGER,
                username VARCHAR(256),
                joined_at INTEGER DEFAULT (strftime('%s','now')),
                PRIMARY KEY (conversation_id, username),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id),
                FOREIGN KEY (username) REFERENCES user_table(username)
            )
        ''')
        
        # Create messages table
        c.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                sender VARCHAR(256) NOT NULL,
                message TEXT NOT NULL,
                timestamp INTEGER DEFAULT (strftime('%s','now')),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id),
                FOREIGN KEY (sender) REFERENCES user_table(username)
            )
        ''')
        
        # Create indexes for performance
        c.execute("CREATE INDEX IF NOT EXISTS idx_username ON user_table(username)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_conversation_id ON messages(conversation_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sender ON messages(sender)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON messages(timestamp)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_participant_username ON conversation_participants(username)")

        # Default users with plain text passwords.
        users = [
            ('Alice', 'alice'),
            ('Boby', 'boby'),
            ('Ryan', 'ryan'),
            ('Samy', 'Samy'),
            ('Ted', 'ted'),
            ('Admin', 'admin')
        ]

        # Hash each password
        hashed_users = []
        for username, password in users:
            hashed_pw = generate_password_hash(password)
            hashed_users.append((username, hashed_pw))

        c.executemany("INSERT OR IGNORE INTO user_table (username, password) VALUES (?, ?)", hashed_users)
        
        # Create sample conversation between Alice and Boby
        create_sample_conversation(conn)
    except Exception as e:
        print(f"Error initializing database: {e}")
    
    conn.commit()
    conn.close()