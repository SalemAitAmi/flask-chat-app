from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g
from flask_socketio import SocketIO, emit, join_room
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
from utils import setup_logging, get_key, encrypt_message, decrypt_message, get_date_header, group_messages_by_date
from db_management import ChatDatabase
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone as dt_timezone
import pytz
import os
import sys
import subprocess

app = Flask(__name__)
app.config['SECRET_KEY'] = get_key('secret.key')  # Replace with a secure key 
socketio = SocketIO(app)
limiter = Limiter(get_remote_address, app=app)  # Rate limiting for robustness
login_manager = LoginManager(app)
setup_logging()  # Standardized logging from utils.py
active_users = {}  # Track active users by username

# Check if the database file exists; if not, initialize the database.
db_path = 'chat_database'
if not os.path.exists(db_path):
    logging.info(f"Database '{db_path}' not found. Initializing database...")
    result = subprocess.run([sys.executable, "init_database.py"],
                            capture_output=True,
                            text=True)
    if result.returncode != 0:
        logging.error("Failed to initialize database. Error: " + result.stderr)
        sys.exit(1)
    logging.info("Database initialized successfully.")

# Create a per-request ChatDatabase instance.
def get_chatdb():
    if 'chat_db' not in g:
        g.chat_db = ChatDatabase(db_path)
    return g.chat_db

def get_user_timezone(username):
    """Get user's timezone from database."""
    user_data = get_chatdb().getUser(username)
    if user_data and len(user_data) > 2:  # Assuming timezone is the 3rd column
        return user_data[2] if user_data[2] else 'UTC'
    return 'UTC'

def convert_timestamp_to_user_timezone(timestamp, user_timezone):
    """Convert UTC timestamp to user's local timezone."""
    utc_dt = datetime.fromtimestamp(timestamp, tz=dt_timezone.utc)
    user_tz = pytz.timezone(user_timezone)
    local_dt = utc_dt.astimezone(user_tz)
    return local_dt

@app.teardown_appcontext
def close_chatdb(exception):
    chat_db = g.pop('chat_db', None)
    if chat_db is not None:
        try:
            chat_db.db_conn.close()
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
            user_row = get_chatdb().getUser(username)
            if user_row and check_password_hash(user_row[1], password):
                user = User(username)
                login_user(user)
                session['username'] = username
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

# The route to display the conversation selection interface.
@app.route('/chat')
@login_required
def chat_select():
    recipients = get_chatdb().getRecipientList(session['username'])
    return render_template('chat_select.html', recipients=recipients)

# A route to start a new conversation.
@app.route('/new_chat', methods=['GET', 'POST'])
@login_required
def new_chat():
    if request.method == 'POST':
        recipient = request.form.get('recipient')
        
        # Check if recipient exists
        user_row = get_chatdb().getUser(recipient)
        if not user_row:
            return render_template('error.html', 
                                  message=f"User '{recipient}' does not exist",
                                  return_url=url_for('chat_select'))
        
        # Check if trying to chat with self
        if recipient == session['username']:
            return render_template('error.html', 
                                  message="You cannot start a conversation with yourself",
                                  return_url=url_for('chat_select'))
        
        if get_chatdb().createConversation(session['username'], recipient):
            logging.info(f"Conversation created between {session['username']} and {recipient}.")
            return redirect(url_for('chat', recipient=recipient))
        else:
            logging.error(f"Failed to create conversation between {session['username']} and {recipient}.")
            return render_template('error.html', 
                                  message="Error creating conversation. The conversation may already exist.",
                                  return_url=url_for('chat_select'))
    return render_template('new_chat.html')

@app.route('/chat/<recipient>', methods=['GET'])
@login_required
def chat(recipient):
    try:
        conversation = get_chatdb().getFullConversation(session['username'], recipient)
        if conversation is None:
            conversation = []
        else:
            secret_key = app.config['SECRET_KEY']
            for row in conversation:
                # Only decrypt the message, leave timestamp as-is
                row['message'] = decrypt_message(row['message'], secret_key)
                # Keep timestamp as Unix timestamp for client-side processing
                row['timestamp'] = int(row['timestamp'])
        
        is_online = recipient in active_users
        
        return render_template('chat.html', 
                               recipient=recipient, 
                               conversation=conversation,
                               username=session['username'],
                               is_online=is_online)
    except Exception as e:
        logging.error(f"Error loading chat: {e}")
        return render_template('error.html', message="Error loading chat"), 500

@app.route('/chat_history/<recipient>', methods=['GET'])
@login_required
def chat_history(recipient):
    conversation = get_chatdb().getFullConversation(session['username'], recipient)
    if conversation is None:
        conversation = []
    else:
        secret_key = app.config['SECRET_KEY']
        for msg in conversation:
            # Only decrypt the message, leave timestamp as-is
            msg['message'] = decrypt_message(msg['message'], secret_key)
            # Keep timestamp as Unix timestamp for client-side processing
            msg['timestamp'] = int(msg['timestamp'])
    
    logging.info(f'Fetching history for [{session["username"]}] - [{recipient}]')
    logging.debug(f'Conversation: {conversation}')
    return jsonify({'conversation': conversation})

def get_conversation_room(user1, user2):
    """Return a unique room string based on the two usernames in sorted order."""
    return '_'.join(sorted([user1, user2]))

@app.route('/send_message', methods=['POST'])
@login_required
@limiter.limit("10 per minute")  # Prevent spam
def send_message():
    data = request.json
    recipient = data.get('recipient')
    message = data.get('message')
    if not message.strip():
        return jsonify({'status': 'BAD', 'message': 'Empty message'}), 400
    try:
        # Encrypt the message.
        encrypted_msg = encrypt_message(message, app.config['SECRET_KEY'])
        # Append the message to the conversation; check for success.
        if not get_chatdb().appendConversation(session['username'], recipient, encrypted_msg):
            logging.error(f"Failed to append conversation between {session['username']} and {recipient}.")
            return jsonify({'status': 'ERROR', 'message': 'Failed to save message'}), 500

        # Send current UTC timestamp for client-side processing
        current_timestamp = int(datetime.now().timestamp())
        
        logging.info(f"Message sent from {session['username']} to {recipient}")
        room = get_conversation_room(session['username'], recipient)
        socketio.emit(
            'new_message',
            {'sender': session['username'], 'message': message, 'timestamp': current_timestamp},
            room=room
        )
        return jsonify({'status': 'OK', 'message': 'Message sent'})
    except Exception as e:
        logging.error(f"Error sending message: {e}")
        return jsonify({'status': 'ERROR', 'message': 'Server error'}), 500
    
@app.route('/update_timezone', methods=['POST'])
@login_required
def update_timezone():
    data = request.json
    timezone = data.get('timezone', 'UTC')
    try:
        get_chatdb().updateUserTimezone(session['username'], timezone)
        return jsonify({'status': 'OK'})
    except Exception as e:
        logging.error(f"Error updating timezone: {e}")
        return jsonify({'status': 'ERROR'}), 500


@socketio.on('join')
def on_join(data):
    username = session.get('username')
    room = data['room']  # Expecting a room like "Alice_Boby"
    join_room(room)
    logging.info(f"{username} joined room {room}")
    emit('status', {'msg': f'{username} has entered the chat.'}, room=room)
    
@socketio.on('connect')
def on_connect():
    if 'username' in session:
        username = session['username']
        active_users[username] = request.sid  # Store socket ID
        # Broadcast to everyone
        socketio.emit('user_status_change', {'username': username, 'status': 'online'})

@socketio.on('disconnect')
def on_disconnect():
    if 'username' in session:
        username = session['username']
        if username in active_users:
            del active_users[username]
            socketio.emit('user_status_change', {'username': username, 'status': 'offline'})

@app.errorhandler(404)
def not_found(error):
    logging.error(f"404 error: {error}")
    return render_template('error.html', message="Page not found"), 404

if __name__ == '__main__':
    # For development; use Gunicorn for production with HTTPS
    socketio.run(app, debug=True, host='127.0.0.1', port=9090)
