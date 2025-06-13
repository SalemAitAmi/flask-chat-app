#!/usr/bin/python3
import sqlite3
import logging
from werkzeug.security import generate_password_hash

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
            self.db_conn.execute("CREATE INDEX IF NOT EXISTS idx_username ON user_table(username)")
            self.db_conn.execute("CREATE INDEX IF NOT EXISTS idx_conversation_id ON messages(conversation_id)")
            self.db_conn.execute("CREATE INDEX IF NOT EXISTS idx_participant_username ON conversation_participants(username)")
        except Exception as e:
            logging.error(f"Error initializing database: {e}")
            exit(1)

    def addUser(self, username, password):
        """
        Add a new user to the user_table.

        :param username: The username to add.
        :param password: The plaintext password (will be hashed).
        :return: True if the user was added successfully, False if the user already exists or an error occurs.
        """
        try:
            hashed_pw = generate_password_hash(password)
            cursor = self.db_conn.cursor()
            cursor.execute("SELECT * FROM user_table WHERE username=?", (username,))
            if cursor.fetchall():
                logging.warning(f"Attempt to register existing user: {username}")
                return False
            cursor.execute("INSERT INTO user_table (username, password) VALUES (?, ?)", (username, hashed_pw))
            self.db_conn.commit()
            logging.debug(f"User {username} registered successfully.")
            return True
        except Exception as e:
            logging.error(f"Error adding user {username}: {e}")
            return False

    def getUser(self, username):
        """
        Fetch a user record from the user_table.

        :param username: The username to fetch.
        :return: The user record if found, otherwise None.
        """
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("SELECT * FROM user_table WHERE username=?", (username,))
            result = cursor.fetchone()
            logging.debug(f"User {username} fetched successfully.")
            return result
        except Exception as e:
            logging.error(f"Error fetching user {username}: {e}")
            return None

    def getAllUsers(self):
        """
        Retrieve all users from the user_table.

        :return: A list of user records, or None if an error occurs.
        """
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("SELECT * FROM user_table")
            result = cursor.fetchall()
            logging.debug("All users fetched successfully.")
            return result
        except Exception as e:
            logging.error(f"Error fetching all users: {e}")
            return None

    def getAllTables(self):
        """
        Retrieve the names of all tables in the database. 
        Creates table names for direct chats to maintain legacy conversation existence checks.

        :return: A list of table names, or None if an error occurs.
        """
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            table_list = cursor.fetchall()
            logging.debug("All table names fetched successfully.")
            
            users = sorted(row[0] for row in self.getAllUsers()) # Alphabetical
            
            while users:
                user1 = users.pop(0)
                for user2 in users:
                    convID = self.getConversationId(user1, user2)
                    if convID:
                        table_list.append((f"conversation_{user1}_{user2}", ))
            return table_list
        except Exception as e:
            logging.error(f"Error fetching table names: {e}")
            return None

    def getRecipientList(self, username):
        """
        Retrieve a list of recipients that have an ongoing conversation with the given username.

        :param username: The username whose conversation partners are to be found.
        :return: A list of recipient usernames, or None if an error occurs.
        """
        try:
            cursor = self.db_conn.cursor()
            # Get all conversations this user is part of
            cursor.execute("""
                SELECT conversation_id FROM conversation_participants 
                WHERE username = ?
            """, (username,))
            conversation_ids = [row[0] for row in cursor.fetchall()]
            
            if not conversation_ids:
                return []
            
            # For each conversation, get the other participants
            recipients = set()
            for conv_id in conversation_ids:
                cursor.execute("""
                    SELECT username FROM conversation_participants 
                    WHERE conversation_id = ? AND username != ?
                """, (conv_id, username))
                for row in cursor.fetchall():
                    recipients.add(row[0])
            
            logging.debug(f"Recipient list for {username} fetched successfully.")
            return list(recipients)
        except Exception as e:
            logging.error(f"Error fetching recipient list for {username}: {e}")
            return None

    def getConversationId(self, user1, user2):
        """
        Get the conversation ID between two users.
        
        :param user1: The first username.
        :param user2: The second username.
        :return: The conversation ID if found, otherwise None.
        """
        try:
            cursor = self.db_conn.cursor()
            # Find conversations where both users are participants
            cursor.execute("""
                SELECT cp1.conversation_id 
                FROM conversation_participants cp1
                JOIN conversation_participants cp2 ON cp1.conversation_id = cp2.conversation_id
                JOIN conversations c ON c.id = cp1.conversation_id
                WHERE cp1.username = ? AND cp2.username = ? AND c.is_group_chat = 0
            """, (user1, user2))
            result = cursor.fetchone()
            
            if result:
                return result[0]
            return None
        except Exception as e:
            logging.error(f"Error getting conversation ID between {user1} and {user2}: {e}")
            return None

    def getConversation(self, user1, user2):
        """
        Retrieve the conversation rows between two users.

        :param user1: The first username.
        :param user2: The second username.
        :return: List of rows from the messages table, or None if the conversation does not exist or an error occurs.
        """
        try:
            conversation_id = self.getConversationId(user1, user2)
            if conversation_id is None:
                logging.error("Conversation does not exist!")
                return None
                
            cursor = self.db_conn.cursor()
            cursor.execute("""
                SELECT sender, message, timestamp 
                FROM messages 
                WHERE conversation_id = ?
                ORDER BY timestamp
            """, (conversation_id,))
            result = cursor.fetchall()
            
            logging.debug(f"Conversation between {user1} and {user2} fetched successfully.")
            return result
        except Exception as e:
            logging.error(f"Error fetching conversation between {user1} and {user2}: {e}")
            return None

    def getFullConversation(self, user1, user2):
        """
        Retrieve the entire conversation between two users.

        :param user1: The first username.
        :param user2: The second username.
        :return: A list of dictionaries with keys 'sender', 'message', and 'timestamp', or None if no conversation exists.
        """
        conversation_history = self.getConversation(user1, user2)
        if conversation_history is None:
            return None
        history = [
            {'sender': row[0], 'message': row[1], 'timestamp': row[2]}
            for row in conversation_history
        ]
        # Sort by timestamp (ascending - oldest first)
        history.sort(key=lambda x: x['timestamp'])
        logging.debug(f"Full conversation between {user1} and {user2} assembled successfully.")
        return history

    def createConversation(self, *usernames):
        """
        Create a new conversation between users.
        
        :param usernames: Variable number of usernames to include in the conversation.
        :return: The conversation ID if created successfully, None otherwise.
        """
        if len(usernames) < 2:
            logging.error("At least two users are required to create a conversation.")
            return None
            
        try:
            cursor = self.db_conn.cursor()
            
            # Check if all users exist
            for username in usernames:
                cursor.execute("SELECT username FROM user_table WHERE username = ?", (username,))
                if not cursor.fetchone():
                    logging.error(f"User {username} is not registered!")
                    return None
            
            # For two users, check if they already have a direct conversation
            if len(usernames) == 2:
                existing_conv_id = self.getConversationId(usernames[0], usernames[1])
                if existing_conv_id:
                    logging.warning("Conversation already exists!")
                    return False
                
            if len(usernames) > 20:
                logging.warning("Attempt to create conversation with more than 20 users!")
                return False
            
            # Create new conversation
            is_group = len(usernames) > 2
            from utils import get_utc_timestamp
            timestamp = get_utc_timestamp()
            
            cursor.execute(
                "INSERT INTO conversations (is_group_chat, created_at) VALUES (?, ?)",
                (1 if is_group else 0, timestamp)
            )
            conversation_id = cursor.lastrowid
            
            # Add all users to the conversation
            for username in usernames:
                cursor.execute(
                    "INSERT INTO conversation_participants (conversation_id, username, joined_at) VALUES (?, ?, ?)",
                    (conversation_id, username, timestamp)
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

    def appendConversation(self, sender: str, receiver: str, message: str):
        """
        Append a new message to the conversation between sender and receiver.
        The timestamp is automatically recorded using UTC.

        :param sender: The username of the sender.
        :param receiver: The username of the receiver.
        :param message: The message to append.
        :return: True on success, False on failure.
        """
        if not message:
            logging.error("Empty message provided.")
            return False
        try:
            # Get conversation
            conversation_id = self.getConversationId(sender, receiver)
            if conversation_id is None:
                return False
            
            from utils import get_utc_timestamp
            utc_timestamp = get_utc_timestamp()
            
            cursor = self.db_conn.cursor()
            cursor.execute(
                "INSERT INTO messages (conversation_id, sender, message, timestamp) VALUES (?, ?, ?, ?)",
                (conversation_id, sender, message, utc_timestamp)
            )
            
            self.db_conn.commit()
            logging.debug(f"Appended message from {sender} to conversation with {receiver} successfully.")
            return True
        except Exception as e:
            logging.error(f"Error appending message to conversation between {sender} and {receiver}: {e}")
            return False

    def updateUserTimezone(self, username, timezone):
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
    
    def getGroupConversations(self, username):
        """
        Get all group conversations a user is part of.
        
        :param username: The username to check.
        :return: List of group conversation IDs and names.
        """
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("""
                SELECT c.id, c.name 
                FROM conversations c
                JOIN conversation_participants cp ON c.id = cp.conversation_id
                WHERE cp.username = ? AND c.is_group_chat = 1
            """, (username,))
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"Error getting group conversations for {username}: {e}")
            return None
            
    def getConversationParticipants(self, conversation_id):
        """
        Get all participants in a conversation.
        
        :param conversation_id: The ID of the conversation.
        :return: List of usernames.
        """
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("""
                SELECT username 
                FROM conversation_participants 
                WHERE conversation_id = ?
            """, (conversation_id,))
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error getting participants for conversation {conversation_id}: {e}")
            return None
            
    def addUserToConversation(self, conversation_id, username):
        """
        Add a user to an existing conversation.
        
        :param conversation_id: The ID of the conversation.
        :param username: The username to add.
        :return: True if successful, False otherwise.
        """
        try:
            cursor = self.db_conn.cursor()
            
            # Check if user exists
            cursor.execute("SELECT username FROM user_table WHERE username = ?", (username,))
            if not cursor.fetchone():
                logging.error(f"User {username} is not registered!")
                return False
                
            # Check if conversation exists
            cursor.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,))
            if not cursor.fetchone():
                logging.error(f"Conversation {conversation_id} does not exist!")
                return False
                
            # Check if user is already in the conversation
            cursor.execute("""
                SELECT username FROM conversation_participants 
                WHERE conversation_id = ? AND username = ?
            """, (conversation_id, username))
            if cursor.fetchone():
                logging.warning(f"User {username} is already in conversation {conversation_id}!")
                return True
                
            # Add user to conversation
            from utils import get_utc_timestamp
            timestamp = get_utc_timestamp()
            
            cursor.execute(
                "INSERT INTO conversation_participants (conversation_id, username, joined_at) VALUES (?, ?, ?)",
                (conversation_id, username, timestamp)
            )
            
            self.db_conn.commit()
            logging.debug(f"Added {username} to conversation {conversation_id} successfully.")
            return True
        except Exception as e:
            logging.error(f"Error adding {username} to conversation {conversation_id}: {e}")
            return False