from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g
from flask_socketio import SocketIO, emit, join_room
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
from utils import setup_logging, get_key, encrypt_message, decrypt_message, get_utc_timestamp
from db_management import ChatDatabase, db
from werkzeug.security import check_password_hash
from pathlib import Path


app = Flask(__name__)
app.config['SECRET_KEY'] = get_key('secret.key')  # Replace with a secure key 

# Configure SQLAlchemy
db_name = 'chat_database.db'
db_path = Path(app.instance_path) / db_name
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_name}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db.init_app(app)
socketio = SocketIO(app)
limiter = Limiter(get_remote_address, app=app)  # Rate limiting for robustness
login_manager = LoginManager(app)
setup_logging()  # Standardized logging from utils.py
active_users = {}  # Track active users by username

# Check if the database file exists; if not, initialize the database.
with app.app_context():
    if not db_path.exists():
        logging.info(f"Database '{db_name}' not found. Creating and initializing database...")
        chat_db = ChatDatabase(db_name)
        chat_db.createTables()
        chat_db.createIndexes()
        chat_db.generateSampleData()
        logging.info("Database initialized successfully.")

# Create a per-request ChatDatabase instance.
def get_chatdb():
    if 'chat_db' not in g:
        g.chat_db = ChatDatabase(db_name)
    return g.chat_db

@app.teardown_appcontext
def close_chatdb(exception):
    chat_db = g.pop('chat_db', None)
    if chat_db is not None:
        try:
            # No need to close connection with SQLAlchemy
            pass
        except Exception as e:
            logging.error("Error closing database connection: " + str(e))

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")  # Prevent brute-force for robustness
def login():
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        try:
            user_data = get_chatdb().getUser(username)
            if user_data and check_password_hash(user_data['password'], password):
                user = User(username)
                login_user(user)
                session['username'] = username
                session['user_id'] = user_data['id']
                logging.info(f"User {username} logged in successfully.")
                return jsonify({'status': 'OK', 'message': 'Login successful'})
            else:
                logging.warning(f"Failed login attempt for {username}.")
                return jsonify({'status': 'BAD', 'message': 'Invalid credentials'}), 401
        except Exception as e:
            logging.error(f"Error during login: {e}")
            return jsonify({'status': 'ERROR', 'message': 'Server error'}), 500
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def register():
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        # Basic validation
        if not username or not password:
            return jsonify({'status': 'BAD', 'message': 'Username and password are required'}), 400
        
        if len(username) < 3:
            return jsonify({'status': 'BAD', 'message': 'Username must be at least 3 characters long'}), 400
            
        if len(password) < 6:
            return jsonify({'status': 'BAD', 'message': 'Password must be at least 6 characters long'}), 400
        
        try:
            if get_chatdb().addUser(username, password):
                logging.info(f"User {username} registered successfully.")
                return jsonify({'status': 'OK', 'message': 'Registration successful'})
            else:
                return jsonify({'status': 'BAD', 'message': 'Username already exists'}), 400
        except Exception as e:
            logging.error(f"Error during registration: {e}")
            return jsonify({'status': 'ERROR', 'message': 'Server error'}), 500
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('login'))

# API Routes

@app.route('/api/chats', methods=['GET'])
@login_required
def get_user_chats():
    """Get all chats for the current user."""
    try:
        chat_ids = get_chatdb().getUserChats(session['username'])
        if chat_ids is None:
            return jsonify({'status': 'ERROR', 'message': 'Error fetching chats'}), 500
        
        chats = []
        for chat_id in chat_ids:
            chat_data = get_chatdb().getChat(chat_id)
            if chat_data:
                # Decrypt the last message for preview
                if chat_data['messages']:
                    last_msg = chat_data['messages'][-1].copy()
                    last_msg['message'] = decrypt_message(last_msg['message'], app.config['SECRET_KEY'])
                    chat_data['last_message'] = last_msg
                else:
                    chat_data['last_message'] = None
                
                # Remove full message list from response (save bandwidth)
                del chat_data['messages']
                chats.append(chat_data)
        
        return jsonify({'status': 'OK', 'chats': chats})
    except Exception as e:
        logging.error(f"Error getting user chats: {e}")
        return jsonify({'status': 'ERROR', 'message': 'Server error'}), 500

@app.route('/api/chat/<int:chat_id>', methods=['GET'])
@login_required
def get_chat(chat_id):
    """Get a specific chat by ID."""
    try:
        # Verify user has access to this chat
        user_chats = get_chatdb().getUserChats(session['username'])
        if chat_id not in user_chats:
            return jsonify({'status': 'ERROR', 'message': 'Access denied'}), 403
        
        chat_data = get_chatdb().getChat(chat_id)
        if not chat_data:
            return jsonify({'status': 'ERROR', 'message': 'Chat not found'}), 404
        
        # Decrypt messages
        for msg in chat_data['messages']:
            msg['message'] = decrypt_message(msg['message'], app.config['SECRET_KEY'])
        
        return jsonify({'status': 'OK', 'chat': chat_data})
    except Exception as e:
        logging.error(f"Error getting chat {chat_id}: {e}")
        return jsonify({'status': 'ERROR', 'message': 'Server error'}), 500

@app.route('/api/send_message', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def send_message():
    """Send a message to a chat."""
    try:
        data = request.json
        chat_id = data.get('chat_id')
        message = data.get('message')
        
        if not message or not message.strip():
            return jsonify({'status': 'BAD', 'message': 'Empty message'}), 400
        
        if not chat_id:
            return jsonify({'status': 'BAD', 'message': 'Chat ID required'}), 400
        
        # Verify user has access to this chat
        user_chats = get_chatdb().getUserChats(session['username'])
        if chat_id not in user_chats:
            return jsonify({'status': 'ERROR', 'message': 'Access denied'}), 403
        
        # Encrypt and save message
        encrypted_msg = encrypt_message(message, app.config['SECRET_KEY'])
        if not get_chatdb().appendMessage(chat_id, session['username'], encrypted_msg):
            return jsonify({'status': 'ERROR', 'message': 'Failed to save message'}), 500
        
        # Get chat participants for WebSocket notification
        participants = get_chatdb().getChatParticipants(chat_id)
        
        # Send current timestamp
        current_timestamp = get_utc_timestamp()
        
        # Emit to all participants via WebSocket
        socketio.emit(
            'new_message',
            {
                'chat_id': chat_id,
                'sender': session['username'],
                'sender_id': session['user_id'],
                'message': message,
                'timestamp': current_timestamp
            },
            room=f'chat_{chat_id}'
        )
        
        logging.info(f"Message sent by {session['username']} to chat {chat_id}")
        return jsonify({'status': 'OK', 'message': 'Message sent', 'timestamp': current_timestamp})
    except Exception as e:
        logging.error(f"Error sending message: {e}")
        return jsonify({'status': 'ERROR', 'message': 'Server error'}), 500

@app.route('/api/create_chat', methods=['POST'])
@login_required
def create_chat():
    """Create a new chat."""
    try:
        data = request.json
        participants = data.get('participants', [])
        
        if not participants:
            return jsonify({'status': 'BAD', 'message': 'No participants specified'}), 400
        
        # Add current user to participants
        if session['username'] not in participants:
            participants.append(session['username'])
        
        # Create the conversation
        chat_id = get_chatdb().createConversation(*participants)
        if chat_id:
            return jsonify({'status': 'OK', 'chat_id': chat_id})
        else:
            return jsonify({'status': 'ERROR', 'message': 'Failed to create chat'}), 500
    except Exception as e:
        logging.error(f"Error creating chat: {e}")
        return jsonify({'status': 'ERROR', 'message': 'Server error'}), 500

@app.route('/api/add_user_to_chat', methods=['POST'])
@login_required
def add_user_to_chat():
    """Add a user to an existing chat."""
    try:
        data = request.json
        chat_id = data.get('chat_id')
        username = data.get('username')
        
        if not chat_id or not username:
            return jsonify({'status': 'BAD', 'message': 'Chat ID and username required'}), 400
        
        # Verify current user has access to this chat
        user_chats = get_chatdb().getUserChats(session['username'])
        if chat_id not in user_chats:
            return jsonify({'status': 'ERROR', 'message': 'Access denied'}), 403
        
        # Add user to chat
        if get_chatdb().addUserToConversation(chat_id, username):
            # Notify via WebSocket
            socketio.emit(
                'user_added',
                {
                    'chat_id': chat_id,
                    'username': username,
                    'added_by': session['username']
                },
                room=f'chat_{chat_id}'
            )
            return jsonify({'status': 'OK', 'message': 'User added successfully'})
        else:
            return jsonify({'status': 'ERROR', 'message': 'Failed to add user'}), 500
    except Exception as e:
        logging.error(f"Error adding user to chat: {e}")
        return jsonify({'status': 'ERROR', 'message': 'Server error'}), 500

@app.route('/api/update_chat_name', methods=['POST'])
@login_required
def update_chat_name():
    """Update the name of a group chat."""
    try:
        data = request.json
        chat_id = data.get('chat_id')
        name = data.get('name', '').strip()
        
        if not chat_id:
            return jsonify({'status': 'BAD', 'message': 'Chat ID required'}), 400
        
        # Verify current user has access to this chat
        user_chats = get_chatdb().getUserChats(session['username'])
        if chat_id not in user_chats:
            return jsonify({'status': 'ERROR', 'message': 'Access denied'}), 403
        
        # Update chat name
        if get_chatdb().updateChatName(chat_id, name):
            # Notify via WebSocket
            socketio.emit(
                'chat_renamed',
                {
                    'chat_id': chat_id,
                    'new_name': name,
                    'renamed_by': session['username']
                },
                room=f'chat_{chat_id}'
            )
            return jsonify({'status': 'OK', 'message': 'Chat renamed successfully'})
        else:
            return jsonify({'status': 'ERROR', 'message': 'Failed to rename chat'}), 500
    except Exception as e:
        logging.error(f"Error renaming chat: {e}")
        return jsonify({'status': 'ERROR', 'message': 'Server error'}), 500

@app.route('/api/users', methods=['GET'])
@login_required
def get_all_users():
    """Get all users for autocomplete."""
    try:
        users = get_chatdb().getAllUsers()
        if users:
            # Remove passwords and current user
            usernames = [u['username'] for u in users if u['username'] != session['username']]
            return jsonify({'status': 'OK', 'users': usernames})
        else:
            return jsonify({'status': 'ERROR', 'message': 'Error fetching users'}), 500
    except Exception as e:
        logging.error(f"Error getting users: {e}")
        return jsonify({'status': 'ERROR', 'message': 'Server error'}), 500

# Page Routes

@app.route('/chat')
@login_required
def chat_select():
    """Chat selection page."""
    return render_template('chat_select.html', username=session['username'])

@app.route('/chat/<int:chat_id>')
@login_required
def chat_view(chat_id):
    """Individual chat view."""
    try:
        # Verify user has access
        user_chats = get_chatdb().getUserChats(session['username'])
        if chat_id not in user_chats:
            return render_template('error.html', 
                                 message="You don't have access to this chat",
                                 return_url=url_for('chat_select'))
        
        chat_data = get_chatdb().getChat(chat_id)
        if not chat_data:
            return render_template('error.html', 
                                 message="Chat not found",
                                 return_url=url_for('chat_select'))
        
        # Decrypt messages
        for msg in chat_data['messages']:
            msg['message'] = decrypt_message(msg['message'], app.config['SECRET_KEY'])
        
        return render_template('chat.html', 
                             chat_data=chat_data,
                             username=session['username'],
                             user_id=session['user_id'])
    except Exception as e:
        logging.error(f"Error loading chat {chat_id}: {e}")
        return render_template('error.html', message="Error loading chat"), 500

@app.route('/new_chat')
@login_required
def new_chat():
    """New chat creation page."""
    return render_template('new_chat.html', username=session['username'])

# WebSocket handlers

@socketio.on('join_chat')
def on_join_chat(data):
    """Join a chat room."""
    if 'username' not in session:
        return
    
    chat_id = data.get('chat_id')
    if not chat_id:
        return
    
    # Verify user has access
    user_chats = get_chatdb().getUserChats(session['username'])
    if chat_id not in user_chats:
        emit('error', {'message': 'Access denied'})
        return
    
    room = f'chat_{chat_id}'
    join_room(room)
    logging.info(f"{session['username']} joined chat room {chat_id}")

@socketio.on('connect')
def on_connect():
    if 'username' in session:
        username = session['username']
        active_users[username] = request.sid  # Store socket ID
        # Broadcast to everyone
        socketio.emit('user_status_change', {'username': username, 'status': 'online'})
        logging.info(f"{username} connected")

@socketio.on('disconnect')
def on_disconnect():
    if 'username' in session:
        username = session['username']
        if username in active_users:
            del active_users[username]
            socketio.emit('user_status_change', {'username': username, 'status': 'offline'})
            logging.info(f"{username} disconnected")

@app.route('/update_timezone', methods=['POST'])
@login_required
def update_timezone():
    """Update user's timezone."""
    data = request.json
    timezone = data.get('timezone', 'UTC')
    try:
        get_chatdb().updateUserTimezone(session['username'], timezone)
        return jsonify({'status': 'OK'})
    except Exception as e:
        logging.error(f"Error updating timezone: {e}")
        return jsonify({'status': 'ERROR'}), 500

@app.errorhandler(404)
def not_found(error):
    logging.error(f"404 error: {error}")
    return render_template('error.html', message="Page not found"), 404

if __name__ == '__main__':
    # For development; use Gunicorn for production with HTTPS
    socketio.run(app, debug=True, host='127.0.0.1', port=9090)