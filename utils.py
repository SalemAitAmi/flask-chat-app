import logging
import os
from cryptography.fernet import Fernet
from datetime import datetime, timedelta

def setup_logging():
    logging.basicConfig(level=logging.DEBUG, filename='app.log', filemode='w',
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logging.info("Logging configured.")

def generate_key():
    return Fernet.generate_key()

def encrypt_message(message, key):
    f = Fernet(key)
    return f.encrypt(message.encode()).decode()

def decrypt_message(encrypted_message, key):
    f = Fernet(key)
    return f.decrypt(encrypted_message.encode()).decode()

def get_key(filepath):
    if os.path.exists(filepath):
        with open(filepath, 'rb') as f:
            key = f.read()
            return key
    else:
        raise f"ERROR: key not found at file path\'{filepath}\'"
    
def get_date_header(msg_date, today):
    """Get the appropriate date header for a message date."""
    if msg_date == today:
        return "Today"
    elif msg_date == today - timedelta(days=1):
        return "Yesterday"
    elif msg_date > today - timedelta(days=7):
        # Within the last week, show weekday
        return msg_date.strftime('%A')
    else:
        # Older than a week, show Month-Day
        return msg_date.strftime('%B %d')
    
def group_messages_by_date(conversation):
    """Group messages by date and insert date headers."""
    if not conversation:
        return []
    
    today = datetime.now().date()
    grouped_messages = []
    current_date_header = None
    
    for msg in conversation:
        # Get the date from the dateTime object
        msg_date_str = msg['dateTime']['date']
        msg_date = datetime.strptime(msg_date_str, '%Y-%m-%d').date()
        
        # Determine the appropriate date header
        date_header = get_date_header(msg_date, today)
        
        # If this is a new date section, add a date header
        if date_header != current_date_header:
            grouped_messages.append({
                'type': 'date_header',
                'header': date_header
            })
            current_date_header = date_header
        
        # Add the message with a type indicator
        msg['type'] = 'message'
        grouped_messages.append(msg)
    
    return grouped_messages

def get_utc_timestamp():
    """Get current UTC timestamp in seconds since epoch."""
    from datetime import datetime, timezone
    return int(datetime.now(timezone.utc).timestamp())

if __name__ == '__main__':
    print(generate_key().decode()) # Generate once and store manually (avoid accidental override)