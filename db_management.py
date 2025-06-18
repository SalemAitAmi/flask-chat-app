#!/usr/bin/python3
import logging
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Union
import json
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_, or_, func, desc
from sqlalchemy.exc import IntegrityError

# Initialize SQLAlchemy
db = SQLAlchemy()

# Define Models
class User(db.Model):
    __tablename__ = 'user_table'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(256), unique=True, nullable=False, index=True)
    password = db.Column(db.String(256), nullable=False)
    timezone = db.Column(db.String(64), nullable=False, default='UTC')
    created_at = db.Column(db.Integer, default=lambda: int(datetime.now().timestamp()))
    
    # Relationships
    sent_messages = db.relationship('Message', backref='sender', lazy='dynamic', foreign_keys='Message.sender_id')
    conversations = db.relationship('ConversationParticipant', backref='user', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'password': self.password,
            'timezone': self.timezone,
            'created_at': self.created_at
        }


class Conversation(db.Model):
    __tablename__ = 'conversations'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text)
    is_group_chat = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.Integer, nullable=False)
    last_message_at = db.Column(db.Integer, index=True)
    
    # Relationships
    messages = db.relationship('Message', backref='conversation', lazy='dynamic', cascade='all, delete-orphan')
    participants = db.relationship('ConversationParticipant', backref='conversation', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'is_group_chat': self.is_group_chat,
            'created_at': self.created_at,
            'last_message_at': self.last_message_at
        }


class ConversationParticipant(db.Model):
    __tablename__ = 'conversation_participants'
    
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user_table.id'), primary_key=True)
    joined_at = db.Column(db.Integer, default=lambda: int(datetime.now().timestamp()))
    
    # Add indexes
    __table_args__ = (
        db.Index('idx_participant_userid', 'user_id'),
        db.Index('idx_participant_convid', 'conversation_id'),
    )


class Message(db.Model):
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user_table.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.Integer, default=lambda: int(datetime.now().timestamp()), index=True)
    
    # Add composite index for performance
    __table_args__ = (
        db.Index('idx_msg_convid_time', 'conversation_id', 'timestamp'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'sender_id': self.sender_id,
            'sender': self.sender.username,
            'message': self.message,
            'timestamp': self.timestamp
        }


class ChatDatabase:
    """Database class for managing chat operations using SQLAlchemy."""

    def __init__(self, database_name):
        """
        Initialize the database connection.
        This class now serves as a wrapper around SQLAlchemy models.
        
        :param database_name: Name of the SQLite database file (kept for compatibility).
        """
        self.database_name = database_name
        # SQLAlchemy is initialized in the Flask app, so we don't need to do anything here
        # This maintains backward compatibility with the existing interface
        
        # Create a dummy connection object for backward compatibility
        class DummyConnection:
            def close(self):
                pass
            
            def commit(self):
                db.session.commit()
                
            def rollback(self):
                db.session.rollback()
        
        self.db_conn = DummyConnection()

    def createTables(self):
        """Create all necessary database tables."""
        try:
            db.create_all()
            logging.info("Database tables created successfully.")
        except Exception as e:
            logging.error(f"Error creating tables: {e}")
            
    def createIndexes(self):
        """Create database indexes for performance optimization."""
        # Indexes are now defined in the model classes
        # This method is kept for backward compatibility
        logging.info("Database indexes created successfully.")

    def generateSampleData(self):
        """Generate sample data for testing."""
        from utils import encrypt_message, get_key, get_utc_timestamp
        
        try:
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
            user_objects = {}
            for username, password in users:
                existing_user = User.query.filter_by(username=username).first()
                if not existing_user:
                    hashed_pw = generate_password_hash(password)
                    user = User(username=username, password=hashed_pw)
                    db.session.add(user)
                    db.session.flush()  # Get the ID
                    user_objects[username] = user
                else:
                    user_objects[username] = existing_user
            
            # Create sample direct conversation between Alice and Boby
            alice = user_objects['Alice']
            boby = user_objects['Boby']
            
            now = datetime.now()
            timestamp = int(now.timestamp())
            
            # Create conversation
            conv = Conversation(is_group_chat=False, created_at=timestamp)
            db.session.add(conv)
            db.session.flush()
            
            # Add participants
            participant1 = ConversationParticipant(
                conversation_id=conv.id, 
                user_id=alice.id, 
                joined_at=timestamp
            )
            participant2 = ConversationParticipant(
                conversation_id=conv.id, 
                user_id=boby.id, 
                joined_at=timestamp
            )
            db.session.add(participant1)
            db.session.add(participant2)
            
            # Create message samples
            message_samples = [
                # Today
                {"date": now, "sender": alice, "message": "Hi Boby, how are you today?"},
                {"date": now - timedelta(minutes=5), "sender": boby, "message": "I'm great! Just finishing up some work."},
                {"date": now - timedelta(minutes=3), "sender": alice, "message": "Can we meet later?"},
                {"date": now - timedelta(minutes=2), "sender": boby, "message": "Sure, how about 6pm?"},
                
                # Yesterday
                {"date": now - timedelta(days=1, hours=2), "sender": alice, "message": "Did you finish the report?"},
                {"date": now - timedelta(days=1, hours=1, minutes=55), "sender": boby, "message": "Yes, sent it to you by email."},
                
                # Previous week
                {"date": now - timedelta(days=3, hours=8), "sender": alice, "message": "Don't forget the meeting at 3pm."},
                {"date": now - timedelta(days=3, hours=7), "sender": boby, "message": "I'll be there!"},
            ]
            
            # Insert messages
            last_timestamp = 0
            for item in message_samples:
                timestamp = int(item["date"].timestamp())
                encrypted_message = encrypt_message(item["message"], secret_key)
                msg = Message(
                    conversation_id=conv.id,
                    sender_id=item["sender"].id,
                    message=encrypted_message,
                    timestamp=timestamp
                )
                db.session.add(msg)
                last_timestamp = max(last_timestamp, timestamp)
            
            # Update last message timestamp
            conv.last_message_at = last_timestamp
            
            # Create a group chat with Alice, Ryan, and Ted
            ryan = user_objects['Ryan']
            ted = user_objects['Ted']
            
            group_timestamp = int((now - timedelta(days=2)).timestamp())
            group_conv = Conversation(
                name="Project Team",
                is_group_chat=True,
                created_at=group_timestamp
            )
            db.session.add(group_conv)
            db.session.flush()
            
            # Add participants
            for user in [alice, ryan, ted]:
                participant = ConversationParticipant(
                    conversation_id=group_conv.id,
                    user_id=user.id,
                    joined_at=group_timestamp
                )
                db.session.add(participant)
            
            # Add some group messages
            group_messages = [
                {"date": now - timedelta(days=2), "sender": alice, "message": "Welcome to the project team chat!"},
                {"date": now - timedelta(days=1, hours=20), "sender": ryan, "message": "Thanks for adding me!"},
                {"date": now - timedelta(days=1, hours=19), "sender": ted, "message": "Great to be here."},
                {"date": now - timedelta(hours=3), "sender": alice, "message": "Meeting tomorrow at 10am"},
                {"date": now - timedelta(hours=2), "sender": ryan, "message": "I'll be there"},
            ]
            
            last_group_timestamp = 0
            for item in group_messages:
                timestamp = int(item["date"].timestamp())
                encrypted_message = encrypt_message(item["message"], secret_key)
                msg = Message(
                    conversation_id=group_conv.id,
                    sender_id=item["sender"].id,
                    message=encrypted_message,
                    timestamp=timestamp
                )
                db.session.add(msg)
                last_group_timestamp = max(last_group_timestamp, timestamp)
            
            group_conv.last_message_at = last_group_timestamp
            
            db.session.commit()
            logging.info("Sample data generated successfully.")
        except Exception as e:
            logging.error(f"Error generating sample data: {e}")
            db.session.rollback()

    # Helper functions (unexposed)
    def _getUserIdFromUsername(self, username: str) -> Optional[int]:
        """Get user ID from username."""
        try:
            user = User.query.filter_by(username=username).first()
            return user.id if user else None
        except Exception as e:
            logging.error(f"Error getting user ID for {username}: {e}")
            return None

    def _getUsernameFromId(self, user_id: int) -> Optional[str]:
        """Get username from user ID."""
        try:
            user = User.query.get(user_id)
            return user.username if user else None
        except Exception as e:
            logging.error(f"Error getting username for ID {user_id}: {e}")
            return None

    def _getDirectChat(self, chat_id: int) -> Optional[Dict]:
        """Get direct chat data."""
        try:
            conv = Conversation.query.filter_by(id=chat_id, is_group_chat=False).first()
            
            if not conv:
                return None
            
            # Get participants
            participants = []
            for cp in conv.participants:
                participants.append({
                    'id': cp.user.id,
                    'username': cp.user.username
                })
            
            # Get messages
            messages = []
            for msg in conv.messages.order_by(Message.timestamp):
                messages.append({
                    'id': msg.id,
                    'sender_id': msg.sender_id,
                    'sender': msg.sender.username,
                    'message': msg.message,
                    'timestamp': msg.timestamp
                })
            
            return {
                'id': conv.id,
                'type': 'direct',
                'created_at': conv.created_at,
                'last_message_at': conv.last_message_at,
                'participants': participants,
                'messages': messages
            }
        except Exception as e:
            logging.error(f"Error getting direct chat {chat_id}: {e}")
            return None

    def _getGroupChat(self, chat_id: int) -> Optional[Dict]:
        """Get group chat data."""
        try:
            conv = Conversation.query.filter_by(id=chat_id, is_group_chat=True).first()
            
            if not conv:
                return None
            
            # Get participants
            participants = []
            for cp in conv.participants:
                participants.append({
                    'id': cp.user.id,
                    'username': cp.user.username,
                    'joined_at': cp.joined_at
                })
            
            # Get messages
            messages = []
            for msg in conv.messages.order_by(Message.timestamp):
                messages.append({
                    'id': msg.id,
                    'sender_id': msg.sender_id,
                    'sender': msg.sender.username,
                    'message': msg.message,
                    'timestamp': msg.timestamp
                })
            
            return {
                'id': conv.id,
                'type': 'group',
                'name': conv.name,
                'created_at': conv.created_at,
                'last_message_at': conv.last_message_at,
                'participants': participants,
                'messages': messages
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
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                logging.warning(f"Attempt to register existing user: {username}")
                return False
                
            hashed_pw = generate_password_hash(password)
            user = User(username=username, password=hashed_pw)
            db.session.add(user)
            db.session.commit()
            logging.debug(f"User {username} registered successfully.")
            return True
        except Exception as e:
            logging.error(f"Error adding user {username}: {e}")
            db.session.rollback()
            return False

    def getUser(self, username: str) -> Optional[Dict]:
        """
        Fetch a user record from the user_table.

        :param username: The username to fetch.
        :return: The user record as a dictionary if found, otherwise None.
        """
        try:
            user = User.query.filter_by(username=username).first()
            if user:
                return user.to_dict()
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
            users = User.query.all()
            return [{'id': u.id, 'username': u.username, 'timezone': u.timezone, 'created_at': u.created_at} 
                   for u in users]
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
            conv = Conversation.query.get(chat_id)
            
            if not conv:
                logging.error(f"Chat {chat_id} not found")
                return None
            
            if conv.is_group_chat:
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
            user = User.query.filter_by(username=username).first()
            if not user:
                return []
            
            # Get all conversations where user is a participant
            conversations = db.session.query(Conversation.id).join(
                ConversationParticipant, 
                Conversation.id == ConversationParticipant.conversation_id
            ).filter(
                ConversationParticipant.user_id == user.id
            ).order_by(
                desc(func.coalesce(Conversation.last_message_at, 0))
            ).all()
            
            return [conv[0] for conv in conversations]
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
            # Get user IDs and check if all users exist
            users = []
            for username in usernames:
                user = User.query.filter_by(username=username).first()
                if not user:
                    logging.error(f"User {username} is not registered!")
                    return None
                users.append(user)
            
            # Remove duplicates
            users = list(set(users))
            user_ids = [u.id for u in users]
            
            # For two users, check if they already have a direct conversation
            if len(users) == 2:
                # Check for existing direct conversation
                existing_conv = db.session.query(Conversation).join(
                    ConversationParticipant,
                    Conversation.id == ConversationParticipant.conversation_id
                ).filter(
                    Conversation.is_group_chat == False,
                    ConversationParticipant.user_id.in_(user_ids)
                ).group_by(Conversation.id).having(
                    func.count(ConversationParticipant.user_id) == 2
                ).first()
                
                if existing_conv:
                    # Verify it only has these two users
                    participant_count = ConversationParticipant.query.filter_by(
                        conversation_id=existing_conv.id
                    ).count()
                    
                    if participant_count == 2:
                        logging.warning("Direct conversation already exists!")
                        return existing_conv.id
            
            # Create new conversation
            is_group = len(users) > 2
            from utils import get_utc_timestamp
            timestamp = get_utc_timestamp()
            
            conv = Conversation(
                is_group_chat=is_group,
                created_at=timestamp
            )
            db.session.add(conv)
            db.session.flush()  # Get the ID
            
            # Add all users to the conversation
            for user in users:
                participant = ConversationParticipant(
                    conversation_id=conv.id,
                    user_id=user.id,
                    joined_at=timestamp
                )
                db.session.add(participant)
            
            db.session.commit()
            logging.debug(f"Conversation created successfully with ID: {conv.id}")
            return conv.id
        except Exception as e:
            logging.error(f"Error creating conversation: {e}")
            try:
                db.session.rollback()
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
            # Check if user exists
            user = User.query.filter_by(username=username).first()
            if not user:
                logging.error(f"User {username} is not registered!")
                return False
            
            # Check if conversation exists
            conv = Conversation.query.get(conversation_id)
            if not conv:
                logging.error(f"Conversation {conversation_id} does not exist!")
                return False
            
            # Check if user is already in the conversation
            existing = ConversationParticipant.query.filter_by(
                conversation_id=conversation_id,
                user_id=user.id
            ).first()
            if existing:
                logging.warning(f"User {username} is already in conversation {conversation_id}!")
                return True
            
            # Check current participant count
            participant_count = ConversationParticipant.query.filter_by(
                conversation_id=conversation_id
            ).count()
            
            if participant_count >= 16:
                logging.error(f"Cannot add user: conversation {conversation_id} already has maximum participants (16)")
                return False
            
            # If it's a direct chat, convert to group chat
            if not conv.is_group_chat and participant_count == 2:
                conv.is_group_chat = True
                logging.info(f"Converting conversation {conversation_id} from direct to group chat")
            
            # Add user to conversation
            from utils import get_utc_timestamp
            timestamp = get_utc_timestamp()
            
            participant = ConversationParticipant(
                conversation_id=conversation_id,
                user_id=user.id,
                joined_at=timestamp
            )
            db.session.add(participant)
            db.session.commit()
            
            logging.debug(f"Added {username} to conversation {conversation_id} successfully.")
            return True
        except Exception as e:
            logging.error(f"Error adding {username} to conversation {conversation_id}: {e}")
            db.session.rollback()
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
            # Get sender
            sender = User.query.filter_by(username=sender_username).first()
            if not sender:
                logging.error(f"Sender {sender_username} not found!")
                return False
            
            # Verify conversation exists and user is a participant
            participant = ConversationParticipant.query.filter_by(
                conversation_id=conversation_id,
                user_id=sender.id
            ).first()
            
            if not participant:
                logging.error(f"User {sender_username} is not a participant in conversation {conversation_id}")
                return False
            
            from utils import get_utc_timestamp
            timestamp = get_utc_timestamp()
            
            msg = Message(
                conversation_id=conversation_id,
                sender_id=sender.id,
                message=message,
                timestamp=timestamp
            )
            db.session.add(msg)
            
            # Update last_message_at for the conversation
            conv = Conversation.query.get(conversation_id)
            conv.last_message_at = timestamp
            
            db.session.commit()
            logging.debug(f"Message appended to conversation {conversation_id} successfully.")
            return True
        except Exception as e:
            logging.error(f"Error appending message to conversation {conversation_id}: {e}")
            db.session.rollback()
            return False

    def updateUserTimezone(self, username: str, timezone: str) -> bool:
        """Update user's timezone."""
        try:
            user = User.query.filter_by(username=username).first()
            if user:
                user.timezone = timezone
                db.session.commit()
                return True
            return False
        except Exception as e:
            logging.error(f"Error updating timezone for {username}: {e}")
            db.session.rollback()
            return False

    def getChatParticipants(self, conversation_id: int) -> Optional[List[Dict]]:
        """
        Get all participants in a conversation.
        
        :param conversation_id: The ID of the conversation.
        :return: List of participant dictionaries with user info.
        """
        try:
            participants = []
            conv_participants = ConversationParticipant.query.filter_by(
                conversation_id=conversation_id
            ).all()
            
            for cp in conv_participants:
                participants.append({
                    'id': cp.user.id,
                    'username': cp.user.username,
                    'joined_at': cp.joined_at
                })
            
            return participants
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
            conv = Conversation.query.get(conversation_id)
            
            if not conv:
                logging.error(f"Conversation {conversation_id} not found")
                return False
            
            if not conv.is_group_chat:
                logging.error(f"Cannot rename direct chat {conversation_id}")
                return False
            
            # Update the name
            conv.name = name
            db.session.commit()
            
            logging.debug(f"Updated name for conversation {conversation_id} to '{name}'")
            return True
        except Exception as e:
            logging.error(f"Error updating chat name: {e}")
            db.session.rollback()
            return False

    def getDirectChatId(self, username1: str, username2: str) -> Optional[int]:
        """
        Get the ID of a direct chat between two users.
        
        :param username1: First username.
        :param username2: Second username.
        :return: The conversation ID if found, None otherwise.
        """
        try:
            user1 = User.query.filter_by(username=username1).first()
            user2 = User.query.filter_by(username=username2).first()
            
            if not user1 or not user2:
                return None
            
            user_ids = [user1.id, user2.id]
            
            # Find direct conversation between these two users
            conv = db.session.query(Conversation).join(
                ConversationParticipant,
                Conversation.id == ConversationParticipant.conversation_id
            ).filter(
                Conversation.is_group_chat == False,
                ConversationParticipant.user_id.in_(user_ids)
            ).group_by(Conversation.id).having(
                func.count(ConversationParticipant.user_id) == 2
            ).first()
            
            if conv:
                # Verify it only has these two users
                participant_count = ConversationParticipant.query.filter_by(
                    conversation_id=conv.id
                ).count()
                
                if participant_count == 2:
                    return conv.id
                    
            return None
        except Exception as e:
            logging.error(f"Error getting direct chat ID between {username1} and {username2}: {e}")
            return None
