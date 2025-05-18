"""
This module fixes the issues with bot registration and handling in the Telegram bot system.
"""
import logging
import threading
import telebot
from models import Bot
from database import get_session
from scheduler import handle_group_registration

logger = logging.getLogger(__name__)

# Global registry to store bot instances
bot_instances = {}

def register_bot_handlers(token):
    """
    Register message handlers for a bot and start polling
    
    Args:
        token: The bot token as a string
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create bot instance with our token
        client_bot = telebot.TeleBot(token)
        
        # Register /start handler explicitly
        @client_bot.message_handler(commands=['start', 'start@' + client_bot.get_me().username])
        def start_handler(message):
            try:
                # Only process group messages
                if message.chat.type in ['group', 'supergroup']:
                    client_bot.send_message(
                        message.chat.id,
                        "🔄 Processing... Registering this group for advertising"
                    )
                    handle_group_registration(token, message)
            except Exception as e:
                logger.error(f"Error in start handler: {e}")
        
        # Start polling in a separate thread
        polling_thread = threading.Thread(
            target=client_bot.infinity_polling,
            kwargs={
                'timeout': 20,
                'long_polling_timeout': 15,
                'interval': 1,
                'skip_pending': True
            }
        )
        polling_thread.daemon = True
        polling_thread.start()
        
        # Store the bot in our registry
        bot_instances[token] = {
            'bot': client_bot,
            'thread': polling_thread
        }
        
        return True
    except Exception as e:
        logger.error(f"Error setting up bot handlers for token {token}: {e}")
        return False

def register_all_bots():
    """
    Register handlers for all bots in the database
    
    Returns:
        int: Number of successfully registered bots
    """
    session = None
    try:
        session = get_session()
        bots = session.query(Bot).all()
        
        count = 0
        for bot_record in bots:
            try:
                token = str(bot_record.token)
                if register_bot_handlers(token):
                    count += 1
                    logger.info(f"Registered handlers for bot {bot_record.id} (@{bot_record.bot_username or 'Unknown'})")
            except Exception as e:
                logger.error(f"Error registering bot {bot_record.id}: {e}")
        
        return count
    except Exception as e:
        logger.error(f"Error registering bots: {e}")
        return 0
    finally:
        if session:
            session.close()