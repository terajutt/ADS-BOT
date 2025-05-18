import logging
import telebot
from datetime import datetime
from telebot.apihelper import ApiException

from config import SUBSCRIPTION_LEVELS

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_subscription(user):
    """
    Check if a user's subscription is active
    """
    if not user:
        return False
    
    # Check if user has a subscription level
    if not user.subscription_level:
        return False
    
    # Check if user has an expiry date
    if not user.subscription_expiry:
        return False
    
    # Check if subscription has expired
    if user.subscription_expiry < datetime.utcnow():
        return False
    
    return True

def validate_bot_token(token):
    """
    Validate bot token by requesting bot info
    """
    try:
        temp_bot = telebot.TeleBot(token)
        bot_info = temp_bot.get_me()
        return {
            'id': bot_info.id,
            'username': bot_info.username,
            'first_name': bot_info.first_name,
            'can_join_groups': bot_info.can_join_groups,
            'can_read_all_group_messages': bot_info.can_read_all_group_messages
        }
    except ApiException as e:
        logger.error(f"Invalid bot token: {e}")
        return None
    except Exception as e:
        logger.error(f"Error validating bot token: {e}")
        return None

def count_user_bots(session, user_id):
    """
    Count the number of bots a user has
    """
    from models import Bot
    return session.query(Bot).filter_by(user_id=user_id).count()

def count_user_groups(session, user_id):
    """
    Count the number of groups across all bots for a user
    """
    from models import Bot, Group
    
    # Get all bots for user
    bots = session.query(Bot).filter_by(user_id=user_id).all()
    
    # Count groups for each bot
    group_count = 0
    for bot in bots:
        group_count += session.query(Group).filter_by(bot_id=bot.id).count()
    
    return group_count

def get_max_bots(user):
    """
    Get maximum allowed bots based on subscription level
    """
    if not user or not user.subscription_level:
        return 0
    
    level_name = user.subscription_level.value
    return SUBSCRIPTION_LEVELS.get(level_name, {}).get("bots", 0)

def get_max_groups(user):
    """
    Get maximum allowed groups based on subscription level
    """
    if not user or not user.subscription_level:
        return 0
    
    level_name = user.subscription_level.value
    return SUBSCRIPTION_LEVELS.get(level_name, {}).get("groups", 0)

def format_error(error):
    """
    Format error message for user display
    """
    error_str = str(error)
    
    # Shorten and clean up common error messages
    if "incorrect padding" in error_str.lower():
        return "Invalid token format"
    elif "not enough rights" in error_str.lower():
        return "Bot needs admin rights in the group"
    elif "chat not found" in error_str.lower():
        return "Chat/Group not found"
    elif "bot was kicked" in error_str.lower():
        return "Bot was removed from the group"
    elif "too many requests" in error_str.lower():
        return "Rate limit exceeded. Try again later."
    elif "unauthorized" in error_str.lower():
        return "Unauthorized. Check your bot token."
    elif "request timed out" in error_str.lower():
        return "Request timed out. Try again later."
    
    # For database errors, provide a generic message
    if "sqlalchemy" in error_str.lower() or "postgresql" in error_str.lower():
        return "Database error. Please try again later."
    
    # Limit length for other errors
    if len(error_str) > 100:
        return error_str[:97] + "..."
    
    return error_str

def user_friendly_time(timestamp):
    """
    Format timestamp to user-friendly string
    """
    if not timestamp:
        return "Never"
    
    now = datetime.utcnow()
    diff = now - timestamp
    
    if diff.days > 30:
        return timestamp.strftime("%Y-%m-%d")
    elif diff.days > 0:
        return f"{diff.days} days ago"
    elif diff.seconds > 3600:
        return f"{diff.seconds // 3600} hours ago"
    elif diff.seconds > 60:
        return f"{diff.seconds // 60} minutes ago"
    else:
        return "Just now"
