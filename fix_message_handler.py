"""
Helper function to fix the message editing issues in the Telegram bot.
This will be imported in handlers.py to ensure consistent message editing behavior.
"""
import logging
from telebot import types
from config import MAIN_BOT_TOKEN
import telebot

logger = logging.getLogger(__name__)

def safe_edit_message(message, text, reply_markup=None, parse_mode=None):
    """
    Safely edit a message considering its type (text or photo).
    Falls back to sending a new message if editing fails.
    
    Args:
        message: The telebot message object
        text: The new text to display
        reply_markup: Optional keyboard markup
        parse_mode: Optional parse mode (Markdown, HTML, etc.)
    """
    try:
        bot = telebot.TeleBot(MAIN_BOT_TOKEN)
        
        # Try to determine if this is a photo message
        has_photo = False
        if hasattr(message, 'photo') and message.photo:
            has_photo = True
        elif hasattr(message, 'content_type') and message.content_type == 'photo':
            has_photo = True
        
        # Try to edit the message based on its type
        if has_photo:
            try:
                bot.edit_message_caption(
                    caption=text,
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                return True
            except Exception as e:
                logger.warning(f"Failed to edit caption: {e}, trying alternative method")
        
        # Try to edit as text message if not photo or if photo edit failed
        try:
            bot.edit_message_text(
                text=text,
                chat_id=message.chat.id,
                message_id=message.message_id,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to edit message: {e}, sending new message")
            # If all editing fails, send a new message
            bot.send_message(
                message.chat.id,
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return False
    except Exception as e:
        logger.error(f"Error in safe_edit_message: {e}")
        # Last resort - try to send a completely new message
        try:
            bot = telebot.TeleBot(MAIN_BOT_TOKEN)
            bot.send_message(
                message.chat.id,
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return False
        except Exception as e2:
            logger.error(f"Failed to send any message: {e2}")
            return False