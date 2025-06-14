#!/usr/bin/python3
import sqlite3
import logging
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Union
import json

class ChatDatabase:
    """Database class for managing chat operations using SQLite."""

    def __init__(self, database_name):
        """
        Initialize the database connection and create necessary indexes.

        :param database_name: Name of the SQLite database file.
        """
        try:
            # Use check_same_thread=False to allow multithreaded access if needed.
            self.db_conn = sqlite3.connect(database_name, check_same_thread=False)
            # Enable dictionary-like access to retrieved rows
            self.db_conn.row_factory = sqlite3.Row
        except Exception as e:
            logging.error(f"Error initializing database: {e}")
            exit(1)

    def createTables(self):
        """Create all necessary database tables."""
        cursor = self.db_conn.cursor()
        
        try:
            # Create user table with ID as primary key
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_table (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(256) UNIQUE NOT NULL,
                    password VARCHAR(256) NOT NULL,
                    timezone VARCHAR(64) DEFAULT 'UTC' NOT NULL,
                    created_at INTEGER DEFAULT (strftime('%s','now'))
                )
            ''')
            
            # Create conversations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    is_group_chat BOOLEAN DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    last_message_at INTEGER
                )
            ''')
            
            # Create conversation participants table with user ID
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversation_participants (
                    conversation_id INTEGER,
                    user_id INTEGER,
                    joined_at INTEGER DEFAULT (strftime('%s','now')),
                    PRIMARY KEY (conversation_id, user_id),
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
                    FOREIGN KEY (user_id) REFERENCES user_table(id)
                )
            ''')
            
            # Create messages table with user ID
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL,
                    sender_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    timestamp INTEGER DEFAULT (strftime('%s','now')),
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
                    FOREIGN KEY (sender_id) REFERENCES user_table(id)
                )
            ''')
            
            # Create indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_lastmsg ON conversations(last_message_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_msg_convid_time ON messages(conversation_id, timestamp DESC)")
            
            self.db_conn.commit()
            logging.info("Database tables created successfully.")
        except Exception as e:
            logging.error(f"Error creating tables: {e}")
            self.db_conn.rollback()
            
    def createIndexes(self):
        """Create database indexes for performance optimization."""
        try:
            cursor = self.db_conn.cursor()
            
            # Create indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON user_table(id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_username ON user_table(username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversation_id ON messages(conversation_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_message_timestamp ON messages(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_participant_userid ON conversation_participants(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_participant_convid ON conversation_participants(conversation_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_lastmsg ON conversations(last_message_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_msg_convid_time ON messages(conversation_id, timestamp DESC)")
            
            self.db_conn.commit()
            logging.info("Database indexes created successfully.")
        except Exception as e:
            logging.error(f"Error creating indexes: {e}")
            self.db_conn.rollback()

    def generateSampleData(self):
        """Generate sample data for testing."""
        from utils import encrypt_message, get_key, get_utc_timestamp
        
        try:
            cursor = self.db_conn.cursor()
            secret_key = get_key('secret.key')
            
            # Default users with plain text passwords.
            users = [
                ('Alice', 'alice'),
                ('Boby', 'boby'),
                ('Ryan', 'ryan'),
                ('Samy', 'samy'),
                ('Ted', 'ted'),
                ('Admin', 'admin')
            ]
            
            # Add users
            user_ids = {}
            for username, password in users:
                hashed_pw = generate_password_hash(password)
                cursor.execute("INSERT OR IGNORE INTO user_table (username, password) VALUES (?, ?)", 
                             (username, hashed_pw))
                cursor.execute("SELECT id FROM user_table WHERE username = ?", (username,))
                user_ids[username] = cursor.fetchone()[0]
            
            # Create sample direct conversation between Alice and Boby
            alice_id = user_ids['Alice']
            boby_id = user_ids['Boby']
            
            now = datetime.now()
            timestamp = int(now.timestamp())
            
            # Create conversation
            cursor.execute("INSERT INTO conversations (is_group_chat, created_at) VALUES (?, ?)",
                         (0, timestamp))
            conv_id = cursor.lastrowid
            
            # Add participants
            cursor.execute("INSERT INTO conversation_participants (conversation_id, user_id, joined_at) VALUES (?, ?, ?)",
                         (conv_id, alice_id, timestamp))
            cursor.execute("INSERT INTO conversation_participants (conversation_id, user_id, joined_at) VALUES (?, ?, ?)",
                         (conv_id, boby_id, timestamp))
            
            # Create message samples
            message_samples = [
                # Today
                {"date": now, "sender_id": alice_id, "message": "Hi Boby, how are you today?"},
                {"date": now - timedelta(minutes=5), "sender_id": boby_id, "message": "I'm great! Just finishing up some work."},
                {"date": now - timedelta(minutes=3), "sender_id": alice_id, "message": "Can we meet later?"},
                {"date": now - timedelta(minutes=2), "sender_id": boby_id, "message": "Sure, how about 6pm?"},
                
                # Yesterday
                {"date": now - timedelta(days=1, hours=2), "sender_id": alice_id, "message": "Did you finish the report?"},
                {"date": now - timedelta(days=1, hours=1, minutes=55), "sender_id": boby_id, "message": "Yes, sent it to you by email."},
                
                # Previous week
                {"date": now - timedelta(days=3, hours=8), "sender_id": alice_id, "message": "Don't forget the meeting at 3pm."},
                {"date": now - timedelta(days=3, hours=7), "sender_id": boby_id, "message": "I'll be there!"},
            ]
            
            # Insert messages
            last_timestamp = 0
            for item in message_samples:
                timestamp = int(item["date"].timestamp())
                encrypted_message = encrypt_message(item["message"], secret_key)
                cursor.execute("INSERT INTO messages (conversation_id, sender_id, message, timestamp) VALUES (?, ?, ?, ?)",
                             (conv_id, item["sender_id"], encrypted_message, timestamp))
                last_timestamp = max(last_timestamp, timestamp)
            
            # Update last message timestamp
            cursor.execute("UPDATE conversations SET last_message_at = ? WHERE id = ?", 
                         (last_timestamp, conv_id))
            
            # Create a group chat with Alice, Ryan, and Ted
            ryan_id = user_ids['Ryan']
            ted_id = user_ids['Ted']
            
            group_timestamp = int((now - timedelta(days=2)).timestamp())
            cursor.execute("INSERT INTO conversations (name, is_group_chat, created_at) VALUES (?, ?, ?)",
                         ("Project Team", 1, group_timestamp))
            group_conv_id = cursor.lastrowid
            
            # Add participants
            for user_id in [alice_id, ryan_id, ted_id]:
                cursor.execute("INSERT INTO conversation_participants (conversation_id, user_id, joined_at) VALUES (?, ?, ?)",
                             (group_conv_id, user_id, group_timestamp))
            
            # Add some group messages
            group_messages = [
                {"date": now - timedelta(days=2), "sender_id": alice_id, "message": "Welcome to the project team chat!"},
                {"date": now - timedelta(days=1, hours=20), "sender_id": ryan_id, "message": "Thanks for adding me!"},
                {"date": now - timedelta(days=1, hours=19), "sender_id": ted_id, "message": "Great to be here."},
                {"date": now - timedelta(hours=3), "sender_id": alice_id, "message": "Meeting tomorrow at 10am"},
                {"date": now - timedelta(hours=2), "sender_id": ryan_id, "message": "I'll be there"},
            ]
            
            last_group_timestamp = 0
            for item in group_messages:
                timestamp = int(item["date"].timestamp())
                encrypted_message = encrypt_message(item["message"], secret_key)
                cursor.execute("INSERT INTO messages (conversation_id, sender_id, message, timestamp) VALUES (?, ?, ?, ?)",
                             (group_conv_id, item["sender_id"], encrypted_message, timestamp))
                last_group_timestamp = max(last_group_timestamp, timestamp)
            
            cursor.execute("UPDATE conversations SET last_message_at = ? WHERE id = ?", 
                         (last_group_timestamp, group_conv_id))
            
            self.db_conn.commit()
            logging.info("Sample data generated successfully.")
        except Exception as e:
            logging.error(f"Error generating sample data: {e}")
            self.db_conn.rollback()

    # Helper functions (unexposed)
    def _getUserIdFromUsername(self, username: str) -> Optional[int]:
        """Get user ID from username."""
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("SELECT id FROM user_table WHERE username = ?", (username,))
            result = cursor.fetchone()
            return result['id'] if result else None
        except Exception as e:
            logging.error(f"Error getting user ID for {username}: {e}")
            return None

    def _getUsernameFromId(self, user_id: int) -> Optional[str]:
        """Get username from user ID."""
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("SELECT username FROM user_table WHERE id = ?", (user_id,))
            result = cursor.fetchone()
            return result['username'] if result else None
        except Exception as e:
            logging.error(f"Error getting username for ID {user_id}: {e}")
            return None

    def _getDirectChat(self, chat_id: int) -> Optional[Dict]:
        """Get direct chat data."""
        try:
            cursor = self.db_conn.cursor()
            
            # Get conversation info
            cursor.execute("""
                SELECT id, created_at, last_message_at, is_group_chat 
                FROM conversations 
                WHERE id = ? AND is_group_chat = 0
            """, (chat_id,))
            conv_row = cursor.fetchone()
            
            if not conv_row:
                return None
            
            # Get participants
            cursor.execute("""
                SELECT u.id, u.username 
                FROM conversation_participants cp
                JOIN user_table u ON cp.user_id = u.id
                WHERE cp.conversation_id = ?
            """, (chat_id,))
            participants = cursor.fetchall()
            
            # Get messages
            cursor.execute("""
                SELECT m.id, m.sender_id, u.username as sender, m.message, m.timestamp
                FROM messages m
                JOIN user_table u ON m.sender_id = u.id
                WHERE m.conversation_id = ?
                ORDER BY m.timestamp ASC
            """, (chat_id,))
            messages = cursor.fetchall()
            
            return {
                'id': conv_row['id'],
                'type': 'direct',
                'created_at': conv_row['created_at'],
                'last_message_at': conv_row['last_message_at'],
                'participants': [dict(p) for p in participants],
                'messages': [dict(m) for m in messages]
            }
        except Exception as e:
            logging.error(f"Error getting direct chat {chat_id}: {e}")
            return None

    def _getGroupChat(self, chat_id: int) -> Optional[Dict]:
        """Get group chat data."""
        try:
            cursor = self.db_conn.cursor()
            
            # Get conversation info
            cursor.execute("""
                SELECT id, name, created_at, last_message_at, is_group_chat 
                FROM conversations 
                WHERE id = ? AND is_group_chat = 1
            """, (chat_id,))
            conv_row = cursor.fetchone()
            
            if not conv_row:
                return None
            
            # Get participants
            cursor.execute("""
                SELECT u.id, u.username, cp.joined_at
                FROM conversation_participants cp
                JOIN user_table u ON cp.user_id = u.id
                WHERE cp.conversation_id = ?
            """, (chat_id,))
            participants = cursor.fetchall()
            
            # Get messages
            cursor.execute("""
                SELECT m.id, m.sender_id, u.username as sender, m.message, m.timestamp
                FROM messages m
                JOIN user_table u ON m.sender_id = u.id
                WHERE m.conversation_id = ?
                ORDER BY m.timestamp ASC
            """, (chat_id,))
            messages = cursor.fetchall()
            
            return {
                'id': conv_row['id'],
                'type': 'group',
                'name': conv_row['name'],
                'created_at': conv_row['created_at'],
                'last_message_at': conv_row['last_message_at'],
                'participants': [dict(p) for p in participants],
                'messages': [dict(m) for m in messages]
            }
        except Exception as e:
            logging.error(f"Error getting group chat {chat_id}: {e}")
            return None

    # Public API methods
    def addUser(self, username: str, password: str) -> bool:
        """
        Add a new user to the user_table.

        :param username: The username to add.
        :param password: The plaintext password (will be hashed).
        :return: True if the user was added successfully, False if the user already exists or an error occurs.
        """
        try:
            hashed_pw = generate_password_hash(password)
            cursor = self.db_conn.cursor()
            cursor.execute("SELECT id FROM user_table WHERE username=?", (username,))
            if cursor.fetchone():
                logging.warning(f"Attempt to register existing user: {username}")
                return False
            cursor.execute("INSERT INTO user_table (username, password) VALUES (?, ?)", (username, hashed_pw))
            self.db_conn.commit()
            logging.debug(f"User {username} registered successfully.")
            return True
        except Exception as e:
            logging.error(f"Error adding user {username}: {e}")
            return False

    def getUser(self, username: str) -> Optional[Dict]:
        """
        Fetch a user record from the user_table.

        :param username: The username to fetch.
        :return: The user record as a dictionary if found, otherwise None.
        """
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("SELECT * FROM user_table WHERE username=?", (username,))
            result = cursor.fetchone()
            if result:
                return dict(result)
            return None
        except Exception as e:
            logging.error(f"Error fetching user {username}: {e}")
            return None

    def getAllUsers(self) -> Optional[List[Dict]]:
        """
        Retrieve all users from the user_table.

        :return: A list of user records as dictionaries, or None if an error occurs.
        """
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("SELECT id, username, timezone, created_at FROM user_table")
            result = cursor.fetchall()
            return [dict(row) for row in result]
        except Exception as e:
            logging.error(f"Error fetching all users: {e}")
            return None

    def getChat(self, chat_id: int) -> Optional[Dict]:
        """
        Get a complete chat by its ID.
        
        :param chat_id: The ID of the chat to retrieve.
        :return: A dictionary containing the entire chat data or None if not found.
        """
        try:
            cursor = self.db_conn.cursor()
            
            # Check if it's a group chat
            cursor.execute("SELECT is_group_chat FROM conversations WHERE id = ?", (chat_id,))
            result = cursor.fetchone()
            
            if not result:
                logging.error(f"Chat {chat_id} not found")
                return None
            
            if result['is_group_chat']:
                return self._getGroupChat(chat_id)
            else:
                return self._getDirectChat(chat_id)
        except Exception as e:
            logging.error(f"Error getting chat {chat_id}: {e}")
            return None

    def getUserChats(self, username: str) -> Optional[List[int]]:
        """
        Get all chat IDs for a user.
        
        :param username: The username to get chats for.
        :return: A list of chat IDs or None if error.
        """
        try:
            user_id = self._getUserIdFromUsername(username)
            if not user_id:
                return []
            
            cursor = self.db_conn.cursor()
            cursor.execute("""
                SELECT c.id 
                FROM conversations c
                JOIN conversation_participants cp ON c.id = cp.conversation_id
                WHERE cp.user_id = ?
                ORDER BY c.last_message_at DESC NULLS LAST
            """, (user_id,))
            
            return [row['id'] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error getting chats for {username}: {e}")
            return None

    def createConversation(self, *usernames: str) -> Optional[int]:
        """
        Create a new conversation between users.
        
        :param usernames: Variable number of usernames to include in the conversation.
        :return: The conversation ID if created successfully, None otherwise.
        """
        if len(usernames) < 2:
            logging.error("At least two users are required to create a conversation.")
            return None
        
        if len(usernames) > 16:  # Max group size
            logging.error("Cannot create conversation with more than 16 users.")
            return None
            
        try:
            cursor = self.db_conn.cursor()
            
            # Get user IDs and check if all users exist
            user_ids = []
            for username in usernames:
                user_id = self._getUserIdFromUsername(username)
                if not user_id:
                    logging.error(f"User {username} is not registered!")
                    return None
                user_ids.append(user_id)
            
            # Remove duplicates
            user_ids = list(set(user_ids))
            
            # For two users, check if they already have a direct conversation
            if len(user_ids) == 2:
                cursor.execute("""
                    SELECT c.id 
                    FROM conversations c
                    WHERE c.is_group_chat = 0 AND c.id IN (
                        SELECT conversation_id 
                        FROM conversation_participants 
                        WHERE user_id IN (?, ?)
                        GROUP BY conversation_id 
                        HAVING COUNT(DISTINCT user_id) = 2
                    ) AND (
                        SELECT COUNT(*) 
                        FROM conversation_participants 
                        WHERE conversation_id = c.id
                    ) = 2
                """, tuple(user_ids))
                
                existing = cursor.fetchone()
                if existing:
                    logging.warning("Direct conversation already exists!")
                    return existing['id']
            
            # Create new conversation
            is_group = len(user_ids) > 2
            from utils import get_utc_timestamp
            timestamp = get_utc_timestamp()
            
            cursor.execute(
                "INSERT INTO conversations (is_group_chat, created_at) VALUES (?, ?)",
                (1 if is_group else 0, timestamp)
            )
            conversation_id = cursor.lastrowid
            
            # Add all users to the conversation
            for user_id in user_ids:
                cursor.execute(
                    "INSERT INTO conversation_participants (conversation_id, user_id, joined_at) VALUES (?, ?, ?)",
                    (conversation_id, user_id, timestamp)
                )
            
            self.db_conn.commit()
            logging.debug(f"Conversation created successfully with ID: {conversation_id}")
            return conversation_id
        except Exception as e:
            logging.error(f"Error creating conversation: {e}")
            try:
                self.db_conn.rollback()
            except Exception as e:
                logging.error(f"Rollback failed: {e}")
            return None

    def addUserToConversation(self, conversation_id: int, username: str) -> bool:
        """
        Add a user to an existing conversation. If it's a direct chat, convert it to a group chat.
        
        :param conversation_id: The ID of the conversation.
        :param username: The username to add.
        :return: True if successful, False otherwise.
        """
        try:
            cursor = self.db_conn.cursor()
            
            # Check if user exists and get ID
            user_id = self._getUserIdFromUsername(username)
            if not user_id:
                logging.error(f"User {username} is not registered!")
                return False
            
            # Check if conversation exists
            cursor.execute("SELECT id, is_group_chat FROM conversations WHERE id = ?", (conversation_id,))
            conv = cursor.fetchone()
            if not conv:
                logging.error(f"Conversation {conversation_id} does not exist!")
                return False
            
            # Check if user is already in the conversation
            cursor.execute("""
                SELECT user_id FROM conversation_participants 
                WHERE conversation_id = ? AND user_id = ?
            """, (conversation_id, user_id))
            if cursor.fetchone():
                logging.warning(f"User {username} is already in conversation {conversation_id}!")
                return True
            
            # Check current participant count
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM conversation_participants 
                WHERE conversation_id = ?
            """, (conversation_id,))
            participant_count = cursor.fetchone()['count']
            
            if participant_count >= 16:
                logging.error(f"Cannot add user: conversation {conversation_id} already has maximum participants (16)")
                return False
            
            # If it's a direct chat, convert to group chat
            if not conv['is_group_chat'] and participant_count == 2:
                cursor.execute("""
                    UPDATE conversations 
                    SET is_group_chat = 1 
                    WHERE id = ?
                """, (conversation_id,))
                logging.info(f"Converting conversation {conversation_id} from direct to group chat")
            
            # Add user to conversation
            from utils import get_utc_timestamp
            timestamp = get_utc_timestamp()
            
            cursor.execute(
                "INSERT INTO conversation_participants (conversation_id, user_id, joined_at) VALUES (?, ?, ?)",
                (conversation_id, user_id, timestamp)
            )
            
            self.db_conn.commit()
            logging.debug(f"Added {username} to conversation {conversation_id} successfully.")
            return True
        except Exception as e:
            logging.error(f"Error adding {username} to conversation {conversation_id}: {e}")
            return False

    def appendMessage(self, conversation_id: int, sender_username: str, message: str) -> bool:
        """
        Append a new message to a conversation.
        
        :param conversation_id: The ID of the conversation.
        :param sender_username: The username of the sender.
        :param message: The message to append (should be encrypted).
        :return: True on success, False on failure.
        """
        if not message:
            logging.error("Empty message provided.")
            return False
        
        try:
            cursor = self.db_conn.cursor()
            
            # Get sender ID
            sender_id = self._getUserIdFromUsername(sender_username)
            if not sender_id:
                logging.error(f"Sender {sender_username} not found!")
                return False
            
            # Verify conversation exists and user is a participant
            cursor.execute("""
                SELECT conversation_id 
                FROM conversation_participants 
                WHERE conversation_id = ? AND user_id = ?
            """, (conversation_id, sender_id))
            
            if not cursor.fetchone():
                logging.error(f"User {sender_username} is not a participant in conversation {conversation_id}")
                return False
            
            from utils import get_utc_timestamp
            timestamp = get_utc_timestamp()
            
            cursor.execute(
                "INSERT INTO messages (conversation_id, sender_id, message, timestamp) VALUES (?, ?, ?, ?)",
                (conversation_id, sender_id, message, timestamp)
            )
            
            # Update last_message_at for the conversation
            cursor.execute(
                "UPDATE conversations SET last_message_at = ? WHERE id = ?",
                (timestamp, conversation_id)
            )
            
            self.db_conn.commit()
            logging.debug(f"Message appended to conversation {conversation_id} successfully.")
            return True
        except Exception as e:
            logging.error(f"Error appending message to conversation {conversation_id}: {e}")
            return False

    def updateUserTimezone(self, username: str, timezone: str) -> bool:
        """Update user's timezone."""
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("UPDATE user_table SET timezone = ? WHERE username = ?", 
                        (timezone, username))
            self.db_conn.commit()
            return True
        except Exception as e:
            logging.error(f"Error updating timezone for {username}: {e}")
            return False

    def getChatParticipants(self, conversation_id: int) -> Optional[List[Dict]]:
        """
        Get all participants in a conversation.
        
        :param conversation_id: The ID of the conversation.
        :return: List of participant dictionaries with user info.
        """
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("""
                SELECT u.id, u.username, cp.joined_at
                FROM conversation_participants cp
                JOIN user_table u ON cp.user_id = u.id
                WHERE cp.conversation_id = ?
            """, (conversation_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error getting participants for conversation {conversation_id}: {e}")
            return None

    def updateChatName(self, conversation_id: int, name: str) -> bool:
        """
        Update the name of a group chat.
        
        :param conversation_id: The ID of the conversation.
        :param name: The new name for the chat.
        :return: True if successful, False otherwise.
        """
        try:
            cursor = self.db_conn.cursor()
            
            # Check if it's a group chat
            cursor.execute("SELECT is_group_chat FROM conversations WHERE id = ?", (conversation_id,))
            result = cursor.fetchone()
            
            if not result:
                logging.error(f"Conversation {conversation_id} not found")
                return False
            
            if not result['is_group_chat']:
                logging.error(f"Cannot rename direct chat {conversation_id}")
                return False
            
            # Update the name
            cursor.execute("UPDATE conversations SET name = ? WHERE id = ?", (name, conversation_id))
            self.db_conn.commit()
            
            logging.debug(f"Updated name for conversation {conversation_id} to '{name}'")
            return True
        except Exception as e:
            logging.error(f"Error updating chat name: {e}")
            return False

    def getDirectChatId(self, username1: str, username2: str) -> Optional[int]:
        """
        Get the ID of a direct chat between two users.
        
        :param username1: First username.
        :param username2: Second username.
        :return: The conversation ID if found, None otherwise.
        """
        try:
            user_id1 = self._getUserIdFromUsername(username1)
            user_id2 = self._getUserIdFromUsername(username2)
            
            if not user_id1 or not user_id2:
                return None
            
            cursor = self.db_conn.cursor()
            cursor.execute("""
                SELECT c.id 
                FROM conversations c
                WHERE c.is_group_chat = 0 AND c.id IN (
                    SELECT conversation_id 
                    FROM conversation_participants 
                    WHERE user_id IN (?, ?)
                    GROUP BY conversation_id 
                    HAVING COUNT(DISTINCT user_id) = 2
                ) AND (
                    SELECT COUNT(*) 
                    FROM conversation_participants 
                    WHERE conversation_id = c.id
                ) = 2
            """, (user_id1, user_id2))
            
            result = cursor.fetchone()
            return result['id'] if result else None
        except Exception as e:
            logging.error(f"Error getting direct chat ID between {username1} and {username2}: {e}")
            return None
