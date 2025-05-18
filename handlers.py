import telebot
import logging
from telebot import types
from telebot.apihelper import ApiException
from sqlalchemy.exc import SQLAlchemyError
import time
from datetime import datetime, timedelta
import re

from config import MAIN_BOT_TOKEN, MAIN_ADMIN_CHAT_ID, AD_FOOTER, BANNER_PATH, MAX_PHOTOS, SUBSCRIPTION_LEVELS, SUBSCRIPTION_DURATIONS, MESSAGE_INTERVALS
from database import get_session
from models import User, Bot, Group, AdMessage, SubscriptionLevel, MessageInterval
from keyboards import (
    main_menu_keyboard, admin_menu_keyboard, back_button, 
    confirm_cancel_keyboard, bots_list_keyboard, bot_actions_keyboard,
    groups_list_keyboard, group_actions_keyboard, ad_message_type_keyboard,
    intervals_keyboard, subscription_levels_keyboard, subscription_durations_keyboard,
    help_menu_keyboard
)
from utils import check_subscription, validate_bot_token, count_user_bots, count_user_groups, format_error
from fix_message_handler import safe_edit_message

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize bot
bot = telebot.TeleBot(MAIN_BOT_TOKEN)

# User state storage (for conversation handling)
user_states = {}

class State:
    """
    States for conversation handling
    """
    IDLE = "idle"
    WAITING_FOR_BOT_TOKEN = "waiting_for_bot_token"
    WAITING_FOR_TEXT_AD = "waiting_for_text_ad"
    WAITING_FOR_PHOTO_AD = "waiting_for_photo_ad"
    WAITING_FOR_PHOTO_CAPTION = "waiting_for_photo_caption"
    WAITING_FOR_BROADCAST = "waiting_for_broadcast"
    WAITING_FOR_ADMIN_ID = "waiting_for_admin_id"

# ==================== Start Command Handler ====================
@bot.message_handler(commands=['start'])
def start_command(message):
    """
    Handle /start command to initialize the bot interaction
    """
    try:
        chat_id = message.chat.id
        session = get_session()
        
        # Reset user state
        user_states[chat_id] = State.IDLE
        
        # Check if user exists, create if not
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            user = User(
                chat_id=str(chat_id),
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name
            )
            # Add main admin
            if str(chat_id) == str(MAIN_ADMIN_CHAT_ID):
                user.is_admin = True
                
            session.add(user)
            session.commit()
            logger.info(f"New user registered: {chat_id}")
        
        # Send welcome message with banner
        with open(BANNER_PATH, 'rb') as photo:
            bot.send_photo(
                chat_id,
                photo=photo,
                caption=f"Welcome to *Butter Ads Bot Service*\n\n"
                       f"User: {message.from_user.first_name} {message.from_user.last_name or ''}\n"
                       f"ID: `{chat_id}`\n\n"
                       f"Please select an option below:",
                parse_mode="Markdown",
                reply_markup=admin_menu_keyboard() if user.is_admin else main_menu_keyboard()
            )
    except Exception as e:
        logger.error(f"Error in start command: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

# ==================== Main Menu Callback Handlers ====================
@bot.callback_query_handler(func=lambda call: call.data == "main_menu")
def main_menu_callback(call):
    """
    Handle main menu callback
    """
    try:
        chat_id = call.message.chat.id
        user_states[chat_id] = State.IDLE
        
        session = get_session()
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        
        if user and user.is_admin:
            # Admin menu
            edit_message_with_banner(call.message, 
                "Welcome to *Butter Ads Bot Service*\n\n"
                f"Admin Panel for: {call.from_user.first_name} {call.from_user.last_name or ''}\n"
                f"ID: `{chat_id}`\n\n"
                f"Select an admin option:",
                admin_menu_keyboard()
            )
        else:
            # Regular user menu
            edit_message_with_banner(call.message,
                "Welcome to *Butter Ads Bot Service*\n\n"
                f"User: {call.from_user.first_name} {call.from_user.last_name or ''}\n"
                f"ID: `{chat_id}`\n\n"
                f"Please select an option below:",
                main_menu_keyboard()
            )
    except Exception as e:
        logger.error(f"Error in main menu callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

# ==================== Connect Bot Handlers ====================
@bot.callback_query_handler(func=lambda call: call.data == "connect_bot")
def connect_bot_callback(call):
    """
    Handle connect bot callback
    """
    try:
        chat_id = call.message.chat.id
        session = get_session()
        
        # Check subscription
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found! Please restart the bot.")
            return
            
        if not check_subscription(user):
            bot.answer_callback_query(call.id, "Your subscription has expired. Contact @pyth0nsyntax to renew.")
            bot.send_message(
                chat_id,
                "❌ Your subscription has expired. Contact @pyth0nsyntax to renew.",
                reply_markup=back_button()
            )
            return
        
        # Check if user has reached bot limit
        bot_count = count_user_bots(session, user.id)
        max_bots = 0
        if user.subscription_level:
            level_name = user.subscription_level.value
            max_bots = SUBSCRIPTION_LEVELS.get(level_name, {}).get("bots", 0)
        
        if bot_count >= max_bots:
            bot.answer_callback_query(call.id, f"You've reached your limit of {max_bots} bots. Upgrade subscription to add more.")
            bot.send_message(
                chat_id,
                f"❌ You've reached your limit of {max_bots} bots with your {user.subscription_level.value} subscription.\n\n"
                "Please contact @pyth0nsyntax to upgrade your subscription.",
                reply_markup=back_button()
            )
            return
        
        # Set state and ask for bot token
        user_states[chat_id] = State.WAITING_FOR_BOT_TOKEN
        
        bot.send_message(
            chat_id,
            "🤖 Please provide your bot token from BotFather.\n\n"
            "If you don't have a token yet, please create a new bot with @BotFather first.\n"
            "See our Help section for instructions.",
            reply_markup=back_button()
        )
    except Exception as e:
        logger.error(f"Error in connect bot callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == State.WAITING_FOR_BOT_TOKEN)
def process_bot_token(message):
    """
    Process bot token provided by user
    """
    try:
        chat_id = message.chat.id
        token = message.text.strip()
        
        # Reset state
        user_states[chat_id] = State.IDLE
        
        # Delete message with token for security
        bot.delete_message(chat_id, message.message_id)
        
        session = get_session()
        
        # Validate token
        bot_info = validate_bot_token(token)
        if not bot_info:
            bot.send_message(
                chat_id,
                "❌ Invalid bot token. Please check your token and try again.",
                reply_markup=back_button()
            )
            return
        
        # Check if bot already exists
        existing_bot = session.query(Bot).filter_by(token=token).first()
        if existing_bot:
            bot.send_message(
                chat_id,
                "❌ This bot is already connected to our system.",
                reply_markup=back_button()
            )
            return
        
        # Get user and add the bot
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.send_message(
                chat_id,
                "❌ User not found! Please restart the bot.",
                reply_markup=back_button()
            )
            return
        
        # Create new bot
        new_bot = Bot(
            user_id=user.id,
            token=token,
            bot_username=bot_info.get('username')
        )
        session.add(new_bot)
        session.commit()
        
        # Inform user
        bot.send_message(
            chat_id,
            f"✅ Bot @{bot_info.get('username')} connected successfully!\n\n"
            "Now you can add this bot to groups and set up your ad message.",
            reply_markup=main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Error processing bot token: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred while connecting your bot.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

# ==================== My Bots Handlers ====================
@bot.callback_query_handler(func=lambda call: call.data == "my_bots")
def my_bots_callback(call):
    """
    Show list of user's bots
    """
    try:
        chat_id = call.message.chat.id
        session = get_session()
        
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found! Please restart the bot.")
            return
        
        bots = session.query(Bot).filter_by(user_id=user.id).all()
        
        if not bots:
            bot.edit_message_text(
                "You don't have any bots connected yet. Use 'Connect New Bot' to add one.",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=main_menu_keyboard()
            )
            return
        
        # Try to edit message safely based on content type
        try:
            if hasattr(call.message, 'content_type') and call.message.content_type == 'photo':
                bot.edit_message_caption(
                    caption=f"🤖 Your connected bots ({len(bots)}):\n\nSelect a bot to manage:",
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    reply_markup=bots_list_keyboard(bots)
                )
            else:
                bot.edit_message_text(
                    f"🤖 Your connected bots ({len(bots)}):\n\nSelect a bot to manage:",
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    reply_markup=bots_list_keyboard(bots)
                )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            # If editing fails, send a new message
            bot.send_message(
                chat_id,
                f"🤖 Your connected bots ({len(bots)}):\n\nSelect a bot to manage:",
                reply_markup=bots_list_keyboard(bots)
            )
    except Exception as e:
        logger.error(f"Error in my bots callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith("bot_"))
def bot_actions_callback(call):
    """
    Show actions for a specific bot
    """
    try:
        chat_id = call.message.chat.id
        bot_id = int(call.data.split("_")[1])
        
        session = get_session()
        
        # Verify bot belongs to user
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found! Please restart the bot.")
            return
            
        bot_record = session.query(Bot).filter_by(id=bot_id, user_id=user.id).first()
        if not bot_record:
            bot.answer_callback_query(call.id, "Bot not found or you don't have permission to manage it.")
            return
        
        # Show bot info and actions
        groups_count = session.query(Group).filter_by(bot_id=bot_id).count()
        
        # Check if bot has an ad message
        ad_message = session.query(AdMessage).filter_by(bot_id=bot_id).first()
        ad_status = "✅ Set" if ad_message else "❌ Not set"
        
        bot.edit_message_text(
            f"🤖 Bot: @{bot_record.bot_username}\n\n"
            f"📊 Status:\n"
            f"- Connected Groups: {groups_count}\n"
            f"- Ad Message: {ad_status}\n\n"
            "Select an action:",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=bot_actions_keyboard(bot_id)
        )
    except Exception as e:
        logger.error(f"Error in bot actions callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

# ==================== Disconnect Bot Handlers ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("disconnect_"))
def disconnect_bot_callback(call):
    """
    Confirm disconnecting a bot
    """
    try:
        chat_id = call.message.chat.id
        bot_id = int(call.data.split("_")[1])
        
        session = get_session()
        
        # Verify bot belongs to user
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found! Please restart the bot.")
            return
            
        bot_record = session.query(Bot).filter_by(id=bot_id, user_id=user.id).first()
        if not bot_record:
            bot.answer_callback_query(call.id, "Bot not found or you don't have permission to manage it.")
            return
        
        # Ask for confirmation
        bot.edit_message_text(
            f"⚠️ Are you sure you want to disconnect @{bot_record.bot_username}?\n\n"
            "This will remove the bot from our system and stop all ads. "
            "All group connections and ad messages will be deleted.\n\n"
            "This action cannot be undone.",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=confirm_cancel_keyboard(f"confirm_disconnect_{bot_id}", f"bot_{bot_id}")
        )
    except Exception as e:
        logger.error(f"Error in disconnect bot callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_disconnect_"))
def confirm_disconnect_bot_callback(call):
    """
    Disconnect bot after confirmation
    """
    try:
        chat_id = call.message.chat.id
        bot_id = int(call.data.split("_")[2])
        
        session = get_session()
        
        # Verify bot belongs to user
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found! Please restart the bot.")
            return
            
        bot_record = session.query(Bot).filter_by(id=bot_id, user_id=user.id).first()
        if not bot_record:
            bot.answer_callback_query(call.id, "Bot not found or you don't have permission to manage it.")
            return
        
        # Save bot username for the message
        bot_username = bot_record.bot_username
        
        # Delete bot (cascade will delete groups and ad messages)
        session.delete(bot_record)
        session.commit()
        
        # Inform user
        bot.edit_message_text(
            f"✅ Bot @{bot_username} disconnected successfully.",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=back_button("my_bots")
        )
    except Exception as e:
        logger.error(f"Error in confirm disconnect bot callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

# ==================== Groups Handlers ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("groups_"))
def groups_list_callback(call):
    """
    Show list of groups for a specific bot
    """
    try:
        chat_id = call.message.chat.id
        bot_id = int(call.data.split("_")[1])
        
        session = get_session()
        
        # Verify bot belongs to user
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found! Please restart the bot.")
            return
            
        bot_record = session.query(Bot).filter_by(id=bot_id, user_id=user.id).first()
        if not bot_record:
            bot.answer_callback_query(call.id, "Bot not found or you don't have permission to manage it.")
            return
        
        # Get groups
        groups = session.query(Group).filter_by(bot_id=bot_id).all()
        
        if not groups:
            bot.edit_message_text(
                f"No groups connected to @{bot_record.bot_username} yet.\n\n"
                "To add this bot to a group:\n"
                "1. Add @{bot_record.bot_username} to your group as admin\n"
                "2. Give it permission to send messages\n"
                "3. Send /start in the group with the bot\n"
                "4. The bot will automatically register the group",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=back_button(f"bot_{bot_id}")
            )
            return
        
        bot.edit_message_text(
            f"📋 Groups connected to @{bot_record.bot_username} ({len(groups)}):\n\n"
            "Select a group to manage:",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=groups_list_keyboard(groups, bot_id)
        )
    except Exception as e:
        logger.error(f"Error in groups list callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith("group_"))
def group_actions_callback(call):
    """
    Show actions for a specific group
    """
    try:
        chat_id = call.message.chat.id
        group_id = int(call.data.split("_")[1])
        
        session = get_session()
        
        # Get group
        group = session.query(Group).filter_by(id=group_id).first()
        if not group:
            bot.answer_callback_query(call.id, "Group not found.")
            return
        
        # Verify bot belongs to user
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found! Please restart the bot.")
            return
            
        bot_record = session.query(Bot).filter_by(id=group.bot_id, user_id=user.id).first()
        if not bot_record:
            bot.answer_callback_query(call.id, "Bot not found or you don't have permission to manage it.")
            return
        
        # Show group info and actions
        status = "✅ Active" if group.active else "❌ Inactive"
        media_status = "✅ Allowed" if group.media_allowed else "❌ Not allowed"
        interval_text = group.interval.value if group.interval else "1hr (default)"
        
        last_ad = "Never" if not group.last_ad_sent else group.last_ad_sent.strftime("%Y-%m-%d %H:%M:%S")
        
        bot.edit_message_text(
            f"📋 Group: {group.group_title or group.group_id}\n\n"
            f"📊 Status:\n"
            f"- Status: {status}\n"
            f"- Media: {media_status}\n"
            f"- Interval: {interval_text}\n"
            f"- Last Ad Sent: {last_ad}\n\n"
            "Select an action:",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=group_actions_keyboard(group_id, group.bot_id)
        )
    except Exception as e:
        logger.error(f"Error in group actions callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith("interval_"))
def interval_selection_callback(call):
    """
    Show interval selection for a group
    """
    try:
        chat_id = call.message.chat.id
        group_id = int(call.data.split("_")[1])
        
        session = get_session()
        
        # Get group
        group = session.query(Group).filter_by(id=group_id).first()
        if not group:
            bot.answer_callback_query(call.id, "Group not found.")
            return
        
        # Verify bot belongs to user
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found! Please restart the bot.")
            return
            
        bot_record = session.query(Bot).filter_by(id=group.bot_id, user_id=user.id).first()
        if not bot_record:
            bot.answer_callback_query(call.id, "Bot not found or you don't have permission to manage it.")
            return
        
        # Show interval selection
        current_interval = group.interval.value if group.interval else "1hr (default)"
        
        bot.edit_message_text(
            f"⏱️ Set message interval for group: {group.group_title or group.group_id}\n\n"
            f"Current interval: {current_interval}\n\n"
            "Select a new interval:",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=intervals_keyboard(group_id)
        )
    except Exception as e:
        logger.error(f"Error in interval selection callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_interval_"))
def set_interval_callback(call):
    """
    Set interval for a group
    """
    try:
        chat_id = call.message.chat.id
        parts = call.data.split("_")
        
        # Make sure we have enough parts and can safely convert the group_id to int
        if len(parts) < 4:
            bot.answer_callback_query(call.id, "Invalid data format")
            bot.send_message(chat_id, "❌ Invalid data format. Please try again.", reply_markup=back_button())
            return
        
        try:
            group_id = int(parts[2])
        except ValueError as e:
            logger.error(f"Invalid group id in set_interval_callback: {e}")
            bot.answer_callback_query(call.id, "Invalid group ID")
            bot.send_message(chat_id, "❌ Invalid group selection. Please try again.", reply_markup=back_button())
            return
            
        interval_name = parts[3]
        
        # Validate interval_name is one of the expected values
        valid_intervals = ["10min", "30min", "1hr", "6hrs"]
        if interval_name not in valid_intervals:
            bot.answer_callback_query(call.id, "Invalid interval")
            bot.send_message(chat_id, "❌ Invalid interval selection. Please choose from the available options.", 
                            reply_markup=back_button())
            return
        
        session = get_session()
        
        # Get group
        group = session.query(Group).filter_by(id=group_id).first()
        if not group:
            bot.answer_callback_query(call.id, "Group not found.")
            return
        
        # Verify bot belongs to user
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found! Please restart the bot.")
            return
            
        bot_record = session.query(Bot).filter_by(id=group.bot_id, user_id=user.id).first()
        if not bot_record:
            bot.answer_callback_query(call.id, "Bot not found or you don't have permission to manage it.")
            return
        
        # Update interval
        group.interval = MessageInterval(interval_name)
        session.commit()
        
        # Confirm
        bot.answer_callback_query(call.id, f"Interval set to {interval_name}")
        
        # Back to group actions
        safe_edit_message(
            call.message, 
            f"✅ Interval updated successfully to {interval_name}.",
            back_button(f"group_{group_id}")
        )
    except Exception as e:
        logger.error(f"Error in set interval callback: {str(e)}")
        try:
            bot.send_message(
                chat_id,
                f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
                reply_markup=back_button()
            )
        except:
            # Fallback in case chat_id isn't available
            logger.error("Failed to send error message")
    finally:
        if 'session' in locals():
            session.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_group_"))
def remove_group_callback(call):
    """
    Confirm removing a group
    """
    try:
        chat_id = call.message.chat.id
        group_id = int(call.data.split("_")[2])
        
        session = get_session()
        
        # Get group
        group = session.query(Group).filter_by(id=group_id).first()
        if not group:
            bot.answer_callback_query(call.id, "Group not found.")
            return
        
        # Verify bot belongs to user
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found! Please restart the bot.")
            return
            
        bot_record = session.query(Bot).filter_by(id=group.bot_id, user_id=user.id).first()
        if not bot_record:
            bot.answer_callback_query(call.id, "Bot not found or you don't have permission to manage it.")
            return
        
        # Ask for confirmation
        bot.edit_message_text(
            f"⚠️ Are you sure you want to remove the group {group.group_title or group.group_id}?\n\n"
            f"The bot will no longer send ads to this group.\n\n"
            f"This action cannot be undone.",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=confirm_cancel_keyboard(f"confirm_remove_group_{group_id}", f"group_{group_id}")
        )
    except Exception as e:
        logger.error(f"Error in remove group callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_remove_group_"))
def confirm_remove_group_callback(call):
    """
    Remove group after confirmation
    """
    try:
        chat_id = call.message.chat.id
        group_id = int(call.data.split("_")[3])
        
        session = get_session()
        
        # Get group
        group = session.query(Group).filter_by(id=group_id).first()
        if not group:
            bot.answer_callback_query(call.id, "Group not found.")
            return
        
        # Verify bot belongs to user
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found! Please restart the bot.")
            return
            
        bot_record = session.query(Bot).filter_by(id=group.bot_id, user_id=user.id).first()
        if not bot_record:
            bot.answer_callback_query(call.id, "Bot not found or you don't have permission to manage it.")
            return
        
        # Save bot_id for return
        bot_id = group.bot_id
        group_title = group.group_title or group.group_id
        
        # Delete group
        session.delete(group)
        session.commit()
        
        # Confirm
        bot.edit_message_text(
            f"✅ Group {group_title} removed successfully.",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=back_button(f"groups_{bot_id}")
        )
    except Exception as e:
        logger.error(f"Error in confirm remove group callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

# ==================== Ad Message Handlers ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("ad_message_"))
def ad_message_callback(call):
    """
    Show ad message options
    """
    try:
        chat_id = call.message.chat.id
        bot_id = int(call.data.split("_")[2])
        
        session = get_session()
        
        # Verify bot belongs to user
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found! Please restart the bot.")
            return
            
        bot_record = session.query(Bot).filter_by(id=bot_id, user_id=user.id).first()
        if not bot_record:
            bot.answer_callback_query(call.id, "Bot not found or you don't have permission to manage it.")
            return
        
        # Get current ad message
        ad_message = session.query(AdMessage).filter_by(bot_id=bot_id).first()
        
        # Show current message if exists
        if ad_message:
            message_type = "Text" if ad_message.text else "Photos"
            message_preview = ad_message.text if ad_message.text else f"{len(ad_message.photo_ids or [])} photo(s)"
            
            bot.edit_message_text(
                f"📝 Current Ad Message for @{bot_record.bot_username}:\n\n"
                f"Type: {message_type}\n"
                f"Content: {message_preview[:100] + '...' if len(message_preview) > 100 else message_preview}\n\n"
                f"Do you want to update your ad message?",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=ad_message_type_keyboard(bot_id)
            )
        else:
            bot.edit_message_text(
                f"📝 Set Ad Message for @{bot_record.bot_username}:\n\n"
                f"Please choose the type of ad message:",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=ad_message_type_keyboard(bot_id)
            )
    except Exception as e:
        logger.error(f"Error in ad message callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith("text_ad_"))
def text_ad_callback(call):
    """
    Handle text ad creation
    """
    try:
        chat_id = call.message.chat.id
        bot_id = int(call.data.split("_")[2])
        
        session = get_session()
        
        # Verify bot belongs to user
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found! Please restart the bot.")
            return
            
        bot_record = session.query(Bot).filter_by(id=bot_id, user_id=user.id).first()
        if not bot_record:
            bot.answer_callback_query(call.id, "Bot not found or you don't have permission to manage it.")
            return
        
        # Set state and ask for text
        user_states[chat_id] = State.WAITING_FOR_TEXT_AD
        
        # Store bot_id in state
        if "data" not in user_states:
            user_states["data"] = {}
        user_states["data"][chat_id] = {"bot_id": bot_id}
        
        bot.edit_message_text(
            f"📝 Enter the text for your ad message:\n\n"
            f"The following footer will be automatically added to your message:\n"
            f"```\n{AD_FOOTER}\n```",
            chat_id=chat_id,
            message_id=call.message.message_id,
            parse_mode="Markdown",
            reply_markup=back_button(f"ad_message_{bot_id}")
        )
    except Exception as e:
        logger.error(f"Error in text ad callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == State.WAITING_FOR_TEXT_AD)
def process_text_ad(message):
    """
    Process text ad message
    """
    try:
        chat_id = message.chat.id
        text = message.text.strip()
        
        # Reset state
        user_states[chat_id] = State.IDLE
        
        # Get bot_id from state
        bot_id = user_states.get("data", {}).get(chat_id, {}).get("bot_id")
        if not bot_id:
            bot.send_message(
                chat_id,
                "❌ Session expired. Please try again.",
                reply_markup=main_menu_keyboard()
            )
            return
        
        session = get_session()
        
        # Verify bot belongs to user
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.send_message(
                chat_id,
                "❌ User not found! Please restart the bot.",
                reply_markup=main_menu_keyboard()
            )
            return
            
        bot_record = session.query(Bot).filter_by(id=bot_id, user_id=user.id).first()
        if not bot_record:
            bot.send_message(
                chat_id,
                "❌ Bot not found or you don't have permission to manage it.",
                reply_markup=main_menu_keyboard()
            )
            return
        
        # Check if ad message exists, update or create
        ad_message = session.query(AdMessage).filter_by(bot_id=bot_id).first()
        if ad_message:
            ad_message.text = text
            ad_message.photo_ids = None
            ad_message.caption = None
        else:
            ad_message = AdMessage(bot_id=bot_id, text=text)
            session.add(ad_message)
        
        session.commit()
        
        # Show preview
        full_text = text + "\n\n" + AD_FOOTER
        bot.send_message(
            chat_id,
            f"✅ Text ad message saved successfully!\n\n"
            f"Preview:\n"
            f"```\n{full_text}\n```",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Error processing text ad: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith("photo_ad_"))
def photo_ad_callback(call):
    """
    Handle photo ad creation
    """
    try:
        chat_id = call.message.chat.id
        bot_id = int(call.data.split("_")[2])
        
        session = get_session()
        
        # Verify bot belongs to user
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found! Please restart the bot.")
            return
            
        bot_record = session.query(Bot).filter_by(id=bot_id, user_id=user.id).first()
        if not bot_record:
            bot.answer_callback_query(call.id, "Bot not found or you don't have permission to manage it.")
            return
        
        # Set state and ask for photos
        user_states[chat_id] = State.WAITING_FOR_PHOTO_AD
        
        # Store bot_id in state
        if "data" not in user_states:
            user_states["data"] = {}
        user_states["data"][chat_id] = {"bot_id": bot_id, "photo_ids": []}
        
        bot.edit_message_text(
            f"🖼️ Send up to {MAX_PHOTOS} photos for your ad message:\n\n"
            f"• Send each photo separately\n"
            f"• After sending all photos (max {MAX_PHOTOS}), click 'Done'\n"
            f"• You'll be able to add a caption after uploading photos\n\n"
            f"The ad footer will be automatically added to your caption.",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("✅ Done", callback_data=f"photos_done_{bot_id}"),
                types.InlineKeyboardButton("❌ Cancel", callback_data=f"ad_message_{bot_id}")
            )
        )
    except Exception as e:
        logger.error(f"Error in photo ad callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.message_handler(content_types=['photo'], func=lambda message: user_states.get(message.chat.id) == State.WAITING_FOR_PHOTO_AD)
def process_photo_ad(message):
    """
    Process photo for ad message
    """
    try:
        chat_id = message.chat.id
        
        # Get state data
        if "data" not in user_states:
            user_states["data"] = {}
        if chat_id not in user_states["data"]:
            user_states["data"][chat_id] = {"photo_ids": []}
            
        state_data = user_states["data"][chat_id]
        bot_id = state_data.get("bot_id")
        photo_ids = state_data.get("photo_ids", [])
        
        if not bot_id:
            bot.send_message(
                chat_id,
                "❌ Session expired. Please try again.",
                reply_markup=main_menu_keyboard()
            )
            user_states[chat_id] = State.IDLE
            return
        
        # Check if max photos reached
        if len(photo_ids) >= MAX_PHOTOS:
            bot.send_message(
                chat_id,
                f"❌ Maximum {MAX_PHOTOS} photos allowed. Click 'Done' to continue.",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("✅ Done", callback_data=f"photos_done_{bot_id}"),
                    types.InlineKeyboardButton("❌ Cancel", callback_data=f"ad_message_{bot_id}")
                )
            )
            return
        
        # Get file id of the largest photo
        file_id = message.photo[-1].file_id
        photo_ids.append(file_id)
        
        # Update state
        user_states["data"][chat_id]["photo_ids"] = photo_ids
        
        # Show the user what their photo looks like
        bot.send_photo(
            chat_id,
            file_id,
            caption=f"✅ Photo {len(photo_ids)}/{MAX_PHOTOS} successfully received"
        )
        
        # Inform user with clear instructions
        bot.send_message(
            chat_id,
            f"📸 Photo {len(photo_ids)}/{MAX_PHOTOS} received!\n\n"
            f"• {'Send more photos or click Done when finished.' if len(photo_ids) < MAX_PHOTOS else 'Maximum photos reached. Click Done to continue.'}\n"
            f"• After clicking Done, you'll be able to add a caption\n"
            f"• The ad footer will be automatically added to your caption",
            reply_markup=types.InlineKeyboardMarkup().row(
                types.InlineKeyboardButton("✅ Done", callback_data=f"photos_done_{bot_id}"),
                types.InlineKeyboardButton("❌ Cancel", callback_data=f"ad_message_{bot_id}")
            )
        )
    except Exception as e:
        logger.error(f"Error processing photo ad: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith("photos_done_"))
def photos_done_callback(call):
    """
    Handle completion of photos upload
    """
    try:
        chat_id = call.message.chat.id
        bot_id = int(call.data.split("_")[2])
        
        # Get state data
        if "data" not in user_states:
            user_states["data"] = {}
        if chat_id not in user_states["data"]:
            user_states["data"][chat_id] = {"photo_ids": []}
            
        state_data = user_states["data"][chat_id]
        photo_ids = state_data.get("photo_ids", [])
        
        if not photo_ids:
            bot.answer_callback_query(call.id, "No photos uploaded. Please send at least one photo.")
            return
        
        # Change state to waiting for caption
        user_states[chat_id] = State.WAITING_FOR_PHOTO_CAPTION
        
        # Ask for caption
        bot.edit_message_text(
            f"📝 {len(photo_ids)} photo(s) received. Now enter a caption for your photos (optional):\n\n"
            f"The following footer will be automatically added to your caption:\n"
            f"```\n{AD_FOOTER}\n```\n\n"
            f"Send your caption or click 'Skip' for no caption.",
            chat_id=chat_id,
            message_id=call.message.message_id,
            parse_mode="Markdown",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("⏩ Skip", callback_data=f"skip_caption_{bot_id}"),
                types.InlineKeyboardButton("❌ Cancel", callback_data=f"ad_message_{bot_id}")
            )
        )
    except Exception as e:
        logger.error(f"Error in photos done callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith("skip_caption_"))
def skip_caption_callback(call):
    """
    Skip caption for photo ad
    """
    try:
        chat_id = call.message.chat.id
        bot_id = int(call.data.split("_")[2])
        
        # Reset state
        user_states[chat_id] = State.IDLE
        
        # Get state data
        if "data" not in user_states:
            user_states["data"] = {}
        if chat_id not in user_states["data"]:
            user_states["data"][chat_id] = {"photo_ids": []}
            
        state_data = user_states["data"][chat_id]
        photo_ids = state_data.get("photo_ids", [])
        
        if not photo_ids:
            bot.answer_callback_query(call.id, "No photos uploaded. Please try again.")
            return
        
        session = get_session()
        
        # Verify bot belongs to user
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found! Please restart the bot.")
            return
            
        bot_record = session.query(Bot).filter_by(id=bot_id, user_id=user.id).first()
        if not bot_record:
            bot.answer_callback_query(call.id, "Bot not found or you don't have permission to manage it.")
            return
        
        # Check if ad message exists, update or create
        ad_message = session.query(AdMessage).filter_by(bot_id=bot_id).first()
        if ad_message:
            ad_message.text = None
            ad_message.photo_ids = photo_ids
            ad_message.caption = None
        else:
            ad_message = AdMessage(bot_id=bot_id, photo_ids=photo_ids)
            session.add(ad_message)
        
        session.commit()
        
        # Show preview of first photo
        bot.answer_callback_query(call.id, "Photos saved without caption")
        
        # Try to send a preview of the first photo
        try:
            bot.send_photo(
                chat_id,
                photo=photo_ids[0],
                caption=f"✅ Photo ad saved successfully!\n\n"
                       f"• {len(photo_ids)} photo(s) saved\n"
                       f"• No caption\n"
                       f"• Footer will be added automatically\n\n"
                       f"Preview (first photo):",
                reply_markup=main_menu_keyboard()
            )
        except Exception as e:
            # If can't send photo, just send text confirmation
            bot.send_message(
                chat_id,
                f"✅ Photo ad saved successfully!\n\n"
                f"• {len(photo_ids)} photo(s) saved\n"
                f"• No caption\n"
                f"• Footer will be added automatically",
                reply_markup=main_menu_keyboard()
            )
    except Exception as e:
        logger.error(f"Error in skip caption callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == State.WAITING_FOR_PHOTO_CAPTION)
def process_photo_caption(message):
    """
    Process caption for photo ad
    """
    try:
        chat_id = message.chat.id
        caption = message.text.strip()
        
        # Reset state
        user_states[chat_id] = State.IDLE
        
        # Get state data
        if "data" not in user_states:
            user_states["data"] = {}
        if chat_id not in user_states["data"]:
            user_states["data"][chat_id] = {"photo_ids": []}
            
        state_data = user_states["data"][chat_id]
        bot_id = state_data.get("bot_id")
        photo_ids = state_data.get("photo_ids", [])
        
        if not bot_id or not photo_ids:
            bot.send_message(
                chat_id,
                "❌ Session expired or no photos uploaded. Please try again.",
                reply_markup=main_menu_keyboard()
            )
            return
        
        session = get_session()
        
        # Verify bot belongs to user
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.send_message(
                chat_id,
                "❌ User not found! Please restart the bot.",
                reply_markup=main_menu_keyboard()
            )
            return
            
        bot_record = session.query(Bot).filter_by(id=bot_id, user_id=user.id).first()
        if not bot_record:
            bot.send_message(
                chat_id,
                "❌ Bot not found or you don't have permission to manage it.",
                reply_markup=main_menu_keyboard()
            )
            return
        
        # Check if ad message exists, update or create
        ad_message = session.query(AdMessage).filter_by(bot_id=bot_id).first()
        if ad_message:
            ad_message.text = None
            ad_message.photo_ids = photo_ids
            ad_message.caption = caption
        else:
            ad_message = AdMessage(bot_id=bot_id, photo_ids=photo_ids, caption=caption)
            session.add(ad_message)
        
        session.commit()
        
        # Show preview of first photo with caption
        full_caption = caption + "\n\n" + AD_FOOTER
        
        # Try to send a preview of the first photo
        try:
            bot.send_photo(
                chat_id,
                photo=photo_ids[0],
                caption=f"✅ Photo ad saved successfully!\n\n"
                       f"• {len(photo_ids)} photo(s) saved\n"
                       f"• Caption added\n"
                       f"• Footer will be added automatically\n\n"
                       f"Preview (first photo with caption):\n\n"
                       f"{full_caption}",
                reply_markup=main_menu_keyboard()
            )
        except Exception as e:
            # If can't send photo, just send text confirmation
            bot.send_message(
                chat_id,
                f"✅ Photo ad saved successfully!\n\n"
                f"• {len(photo_ids)} photo(s) saved\n"
                f"• Caption: {caption}\n"
                f"• Footer will be added automatically",
                reply_markup=main_menu_keyboard()
            )
    except Exception as e:
        logger.error(f"Error processing photo caption: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

# ==================== Subscription Info Handlers ====================
@bot.callback_query_handler(func=lambda call: call.data == "subscription_info")
def subscription_info_callback(call):
    """
    Show subscription info
    """
    try:
        chat_id = call.message.chat.id
        session = get_session()
        
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found! Please restart the bot.")
            return
        
        # Check subscription
        subscription_active = check_subscription(user)
        
        # Get stats
        bot_count = count_user_bots(session, user.id)
        group_count = count_user_groups(session, user.id)
        
        # Format level and limits
        level_text = "None"
        max_bots = 0
        max_groups = 0
        
        if user.subscription_level:
            level_name = user.subscription_level.value
            level_text = level_name
            max_bots = SUBSCRIPTION_LEVELS.get(level_name, {}).get("bots", 0)
            max_groups = SUBSCRIPTION_LEVELS.get(level_name, {}).get("groups", 0)
        
        # Format expiry
        expiry_text = "Not set"
        days_remaining = 0
        
        if user.subscription_expiry:
            expiry_text = user.subscription_expiry.strftime("%Y-%m-%d %H:%M:%S")
            days_remaining = (user.subscription_expiry - datetime.utcnow()).days
            
            if days_remaining < 0:
                days_remaining = 0
        
        # Create message
        status = "✅ Active" if subscription_active else "❌ Expired"
        message = (
            f"📊 Your Subscription Info:\n\n"
            f"Status: {status}\n"
            f"Level: {level_text}\n"
            f"Expires: {expiry_text}\n"
            f"Days Remaining: {days_remaining}\n\n"
            f"Limits:\n"
            f"- Bots: {bot_count}/{max_bots}\n"
            f"- Groups: {group_count}/{max_groups}\n\n"
            f"To extend or upgrade your subscription, please contact @pyth0nsyntax."
        )
        
        bot.edit_message_text(
            message,
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=back_button()
        )
    except Exception as e:
        logger.error(f"Error in subscription info callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

# ==================== Help Section Handlers ====================
@bot.callback_query_handler(func=lambda call: call.data == "help")
def help_menu_callback(call):
    """
    Show help menu
    """
    try:
        chat_id = call.message.chat.id
        
        bot.edit_message_text(
            "❓ Help Center\n\n"
            "Welcome to the Butter Ads Bot Service help center!\n\n"
            "Select a topic to learn more:",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=help_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Error in help menu callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )

@bot.callback_query_handler(func=lambda call: call.data == "help_create_bot")
def help_create_bot_callback(call):
    """
    Show help for creating a bot
    """
    try:
        chat_id = call.message.chat.id
        
        bot.edit_message_text(
            "🤖 How to Create a Bot\n\n"
            "1. Open Telegram and search for @BotFather\n"
            "2. Start a chat with BotFather\n"
            "3. Send /newbot command\n"
            "4. Follow BotFather's instructions:\n"
            "   - Provide a name for your bot\n"
            "   - Provide a username (must end with 'bot')\n"
            "5. BotFather will give you a token (keep it secure)\n"
            "6. Use this token to connect your bot to our service",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=back_button("help")
        )
    except Exception as e:
        logger.error(f"Error in help create bot callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )

@bot.callback_query_handler(func=lambda call: call.data == "help_get_token")
def help_get_token_callback(call):
    """
    Show help for getting a bot token
    """
    try:
        chat_id = call.message.chat.id
        
        bot.edit_message_text(
            "🔑 How to Get Your Bot Token\n\n"
            "If you already created a bot but need to get the token again:\n\n"
            "1. Open Telegram and go to @BotFather\n"
            "2. Send /mybots command\n"
            "3. Select your bot from the list\n"
            "4. Click 'API Token'\n"
            "5. BotFather will send you the token\n\n"
            "Keep your token secure and never share it with others!",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=back_button("help")
        )
    except Exception as e:
        logger.error(f"Error in help get token callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )

@bot.callback_query_handler(func=lambda call: call.data == "help_connect")
def help_connect_callback(call):
    """
    Show help for connecting a bot
    """
    try:
        chat_id = call.message.chat.id
        
        bot.edit_message_text(
            "🔄 How to Connect Your Bot\n\n"
            "1. From the main menu, click '✨ Connect New Bot'\n"
            "2. Paste your bot token when prompted\n"
            "3. Wait for confirmation\n\n"
            "After connecting, your bot will appear in 'My Bots' section.\n\n"
            "Important: Make sure your bot has these settings:\n"
            "- Privacy mode: Disabled (use /setprivacy with BotFather)\n"
            "- Inline mode: Not required\n"
            "- Group admin rights: Required for posting in groups",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=back_button("help")
        )
    except Exception as e:
        logger.error(f"Error in help connect callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )

@bot.callback_query_handler(func=lambda call: call.data == "help_add_group")
def help_add_group_callback(call):
    """
    Show help for adding bot to group
    """
    try:
        chat_id = call.message.chat.id
        
        bot.edit_message_text(
            "➕ How to Add Bot to a Group\n\n"
            "1. Open the group where you want to add your bot\n"
            "2. Tap the group name at the top\n"
            "3. Select 'Add members' or 'Add administrators'\n"
            "4. Search for your bot by username\n"
            "5. Add the bot to the group\n"
            "6. Give your bot admin rights with at least:\n"
            "   - 'Send messages' permission\n"
            "   - 'Delete messages' (if you want auto-cleanup)\n\n"
            "After adding, the bot will automatically detect and register the group.\n"
            "You can then set the ad interval in the 'My Bots' → 'Connected Groups' section.",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=back_button("help")
        )
    except Exception as e:
        logger.error(f"Error in help add group callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )

@bot.callback_query_handler(func=lambda call: call.data == "help_set_ad")
def help_set_ad_callback(call):
    """
    Show help for setting ad message
    """
    try:
        chat_id = call.message.chat.id
        
        bot.edit_message_text(
            "📝 How to Set Your Ad Message\n\n"
            "1. Go to 'My Bots' and select your bot\n"
            "2. Click 'Set Ad Message'\n"
            "3. Choose message type:\n"
            "   - Text: Just text message\n"
            "   - Photos: Up to 3 photos with optional caption\n\n"
            "For Text Ads:\n"
            "- Type your message text\n"
            "- Our system automatically adds the required footer\n\n"
            "For Photo Ads:\n"
            "- Send up to 3 photos one by one\n"
            "- Click 'Done' when finished\n"
            "- Optionally add a caption or skip\n\n"
            "Note: If a group doesn't allow media, the bot will automatically fall back to sending text only.",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=back_button("help")
        )
    except Exception as e:
        logger.error(f"Error in help set ad callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )

# ==================== Admin Menu Handlers ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_actions_callback(call):
    """
    Handle admin actions
    """
    try:
        chat_id = call.message.chat.id
        action = call.data.split("_")[1]
        
        session = get_session()
        
        # Check if user is admin
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user or not user.is_admin:
            bot.answer_callback_query(call.id, "You don't have permission to access this.")
            return
        
        # Handle different admin actions
        if action == "users":
            # Show all users
            users = session.query(User).all()
            
            if not users:
                try:
                    if hasattr(call.message, 'content_type') and call.message.content_type == 'photo':
                        bot.edit_message_caption(
                            caption="No users found in the system.",
                            chat_id=chat_id,
                            message_id=call.message.message_id,
                            reply_markup=back_button("main_menu")
                        )
                    else:
                        bot.edit_message_text(
                            "No users found in the system.",
                            chat_id=chat_id,
                            message_id=call.message.message_id,
                            reply_markup=back_button("main_menu")
                        )
                except Exception as e:
                    logger.error(f"Error editing message: {e}")
                    bot.send_message(
                        chat_id,
                        "No users found in the system.",
                        reply_markup=back_button("main_menu")
                    )
                return
            
            # Create user list with inline buttons
            keyboard = types.InlineKeyboardMarkup(row_width=1)
            
            for user in users:
                name = user.username or f"{user.first_name} {user.last_name or ''}"
                status = "👑" if user.is_admin else "👤"
                sub_status = "✅" if check_subscription(user) else "❌"
                
                keyboard.add(types.InlineKeyboardButton(
                    f"{status} {sub_status} {name} (ID: {user.chat_id})",
                    callback_data=f"user_{user.id}"
                ))
            
            keyboard.add(types.InlineKeyboardButton("⬅️ Back", callback_data="main_menu"))
            
            # Safely edit message based on content type
            try:
                if hasattr(call.message, 'content_type') and call.message.content_type == 'photo':
                    bot.edit_message_caption(
                        caption=f"👥 All Users ({len(users)}):\n\n"
                        f"Legend: 👑 Admin | 👤 User | ✅ Active | ❌ Expired\n\n"
                        f"Select a user to manage:",
                        chat_id=chat_id,
                        message_id=call.message.message_id,
                        reply_markup=keyboard
                    )
                else:
                    bot.edit_message_text(
                        f"👥 All Users ({len(users)}):\n\n"
                        f"Legend: 👑 Admin | 👤 User | ✅ Active | ❌ Expired\n\n"
                        f"Select a user to manage:",
                        chat_id=chat_id,
                        message_id=call.message.message_id,
                        reply_markup=keyboard
                    )
            except Exception as e:
                logger.error(f"Error editing admin message: {e}")
                # If editing fails, send a new message
                bot.send_message(
                    chat_id,
                    f"👥 All Users ({len(users)}):\n\n"
                    f"Legend: 👑 Admin | 👤 User | ✅ Active | ❌ Expired\n\n"
                    f"Select a user to manage:",
                    reply_markup=keyboard
                )
            
        elif action == "subscriptions":
            # Show users for subscription management
            users = session.query(User).all()
            
            if not users:
                bot.edit_message_text(
                    "No users found in the system.",
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    reply_markup=back_button("main_menu")
                )
                return
            
            # Create user list with inline buttons
            keyboard = types.InlineKeyboardMarkup(row_width=1)
            
            for user in users:
                name = user.username or f"{user.first_name} {user.last_name or ''}"
                level = user.subscription_level.value if user.subscription_level else "None"
                expiry = "Never" if not user.subscription_expiry else user.subscription_expiry.strftime("%Y-%m-%d")
                
                keyboard.add(types.InlineKeyboardButton(
                    f"{name} - {level} (Expires: {expiry})",
                    callback_data=f"subscription_{user.id}"
                ))
            
            keyboard.add(types.InlineKeyboardButton("⬅️ Back", callback_data="main_menu"))
            
            bot.edit_message_text(
                f"🔄 Manage Subscriptions\n\n"
                f"Select a user to update subscription:",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=keyboard
            )
            
        elif action == "broadcast":
            # Set state and ask for broadcast message
            user_states[chat_id] = State.WAITING_FOR_BROADCAST
            
            bot.edit_message_text(
                "🔊 Broadcast Message\n\n"
                "Enter the message you want to broadcast to all users:",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=back_button("main_menu")
            )
            
        elif action == "stats":
            # Show system stats
            total_users = session.query(User).count()
            total_admins = session.query(User).filter_by(is_admin=True).count()
            total_bots = session.query(Bot).count()
            total_groups = session.query(Group).count()
            
            # Count subscriptions by level
            bronze = session.query(User).filter_by(subscription_level=SubscriptionLevel.BRONZE).count()
            silver = session.query(User).filter_by(subscription_level=SubscriptionLevel.SILVER).count()
            gold = session.query(User).filter_by(subscription_level=SubscriptionLevel.GOLD).count()
            
            # Count active subscriptions
            active_subs = 0
            for user in session.query(User).all():
                if check_subscription(user):
                    active_subs += 1
            
            bot.edit_message_text(
                "📊 System Statistics\n\n"
                f"Users: {total_users}\n"
                f"Admins: {total_admins}\n"
                f"Bots: {total_bots}\n"
                f"Groups: {total_groups}\n\n"
                f"Subscriptions:\n"
                f"- Active: {active_subs}\n"
                f"- Bronze: {bronze}\n"
                f"- Silver: {silver}\n"
                f"- Gold: {gold}",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=back_button("main_menu")
            )
            
        elif action == "add":
            # Set state and ask for new admin's chat ID
            user_states[chat_id] = State.WAITING_FOR_ADMIN_ID
            
            bot.edit_message_text(
                "👨‍💼 Add Admin\n\n"
                "Enter the Chat ID of the user you want to make an admin:",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=back_button("main_menu")
            )
    except Exception as e:
        logger.error(f"Error in admin actions callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == State.WAITING_FOR_BROADCAST)
def process_broadcast(message):
    """
    Process broadcast message
    """
    try:
        chat_id = message.chat.id
        broadcast_text = message.text.strip()
        
        # Reset state
        user_states[chat_id] = State.IDLE
        
        session = get_session()
        
        # Check if user is admin
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user or not user.is_admin:
            bot.send_message(
                chat_id,
                "❌ You don't have permission to broadcast messages.",
                reply_markup=main_menu_keyboard()
            )
            return
        
        # Get all users
        users = session.query(User).all()
        
        if not users:
            bot.send_message(
                chat_id,
                "No users found in the system.",
                reply_markup=main_menu_keyboard()
            )
            return
        
        # Send confirmation
        bot.send_message(
            chat_id,
            f"🔊 Broadcasting message to {len(users)} users...\n\n"
            f"Message: {broadcast_text}",
            reply_markup=main_menu_keyboard()
        )
        
        # Broadcast message
        success = 0
        failed = 0
        
        for user in users:
            try:
                bot.send_message(
                    user.chat_id,
                    f"📢 Announcement from Admin:\n\n{broadcast_text}"
                )
                success += 1
                # Sleep to avoid flood limits
                time.sleep(0.1)
            except Exception:
                failed += 1
        
        # Send broadcast report
        bot.send_message(
            chat_id,
            f"📊 Broadcast Report:\n\n"
            f"Total Users: {len(users)}\n"
            f"Successfully Sent: {success}\n"
            f"Failed: {failed}",
            reply_markup=main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Error in process broadcast: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == State.WAITING_FOR_ADMIN_ID)
def process_admin_id(message):
    """
    Process new admin ID
    """
    try:
        chat_id = message.chat.id
        new_admin_id = message.text.strip()
        
        # Reset state
        user_states[chat_id] = State.IDLE
        
        session = get_session()
        
        # Check if user is admin
        user = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not user or not user.is_admin:
            bot.send_message(
                chat_id,
                "❌ You don't have permission to add admins.",
                reply_markup=main_menu_keyboard()
            )
            return
        
        # Validate chat ID
        if not re.match(r'^\d+$', new_admin_id):
            bot.send_message(
                chat_id,
                "❌ Invalid chat ID. Please enter a valid numeric ID.",
                reply_markup=main_menu_keyboard()
            )
            return
        
        # Find user by chat ID
        target_user = session.query(User).filter_by(chat_id=new_admin_id).first()
        
        if not target_user:
            # Create user if not exists
            target_user = User(chat_id=new_admin_id)
            session.add(target_user)
        
        # Set as admin
        target_user.is_admin = True
        session.commit()
        
        # Send confirmation
        bot.send_message(
            chat_id,
            f"✅ User with chat ID {new_admin_id} has been set as admin successfully.",
            reply_markup=main_menu_keyboard()
        )
        
        # Notify the new admin if possible
        try:
            bot.send_message(
                new_admin_id,
                f"🎉 Congratulations! You have been promoted to admin by {user.username or user.first_name}.\n\n"
                f"You now have access to the admin panel with additional privileges."
            )
        except:
            # Ignore if can't send message to the new admin
            pass
    except Exception as e:
        logger.error(f"Error in process admin id: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith("user_"))
def user_manage_callback(call):
    """
    Show user management options
    """
    try:
        chat_id = call.message.chat.id
        user_id = int(call.data.split("_")[1])
        
        session = get_session()
        
        # Check if current user is admin
        admin = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not admin or not admin.is_admin:
            bot.answer_callback_query(call.id, "You don't have permission to manage users.")
            return
        
        # Get target user
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found.")
            return
        
        # Get user stats
        bot_count = count_user_bots(session, user.id)
        group_count = count_user_groups(session, user.id)
        
        # Format level and expiry
        level = user.subscription_level.value if user.subscription_level else "None"
        expiry = "Never" if not user.subscription_expiry else user.subscription_expiry.strftime("%Y-%m-%d %H:%M:%S")
        
        # Create actions keyboard
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        
        buttons = [
            types.InlineKeyboardButton("🔄 Change Subscription", callback_data=f"subscription_{user.id}"),
            types.InlineKeyboardButton("👑 Toggle Admin", callback_data=f"toggle_admin_{user.id}")
        ]
        
        keyboard.add(*buttons)
        keyboard.add(types.InlineKeyboardButton("⬅️ Back", callback_data="admin_users"))
        
        # Show user info and actions
        bot.edit_message_text(
            f"👤 User Profile\n\n"
            f"ID: {user.chat_id}\n"
            f"Username: {user.username or 'Not set'}\n"
            f"Name: {user.first_name} {user.last_name or ''}\n"
            f"Admin: {'Yes' if user.is_admin else 'No'}\n\n"
            f"Subscription:\n"
            f"- Level: {level}\n"
            f"- Expires: {expiry}\n"
            f"- Status: {'✅ Active' if check_subscription(user) else '❌ Expired'}\n\n"
            f"Usage:\n"
            f"- Bots: {bot_count}\n"
            f"- Groups: {group_count}",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error in user manage callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_admin_"))
def toggle_admin_callback(call):
    """
    Toggle admin status
    """
    try:
        chat_id = call.message.chat.id
        user_id = int(call.data.split("_")[2])
        
        session = get_session()
        
        # Check if current user is admin
        admin = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not admin or not admin.is_admin:
            bot.answer_callback_query(call.id, "You don't have permission to manage admins.")
            return
        
        # Get target user
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found.")
            return
        
        # Don't allow removing main admin
        if str(user.chat_id) == str(MAIN_ADMIN_CHAT_ID) and user.is_admin:
            bot.answer_callback_query(call.id, "Cannot remove main admin status.")
            return
        
        # Toggle admin status
        user.is_admin = not user.is_admin
        session.commit()
        
        # Show result
        bot.answer_callback_query(call.id, f"User admin status set to: {user.is_admin}")
        
        # Refresh user management view
        user_manage_callback(call)
        
        # Notify the user
        try:
            if user.is_admin:
                bot.send_message(
                    user.chat_id,
                    f"🎉 Congratulations! You have been promoted to admin by {admin.username or admin.first_name}.\n\n"
                    f"You now have access to the admin panel with additional privileges."
                )
            else:
                bot.send_message(
                    user.chat_id,
                    f"Your admin privileges have been revoked by {admin.username or admin.first_name}."
                )
        except:
            # Ignore if can't send message to the user
            pass
    except Exception as e:
        logger.error(f"Error in toggle admin callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith("subscription_"))
def subscription_manage_callback(call):
    """
    Show subscription management options
    """
    try:
        chat_id = call.message.chat.id
        user_id = int(call.data.split("_")[1])
        
        session = get_session()
        
        # Check if current user is admin
        admin = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not admin or not admin.is_admin:
            bot.answer_callback_query(call.id, "You don't have permission to manage subscriptions.")
            return
        
        # Get target user
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found.")
            return
        
        # Show subscription level selection
        bot.edit_message_text(
            f"🔄 Update Subscription for User:\n"
            f"ID: {user.chat_id}\n"
            f"Name: {user.username or user.first_name}\n\n"
            f"Select subscription level:",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=subscription_levels_keyboard(user_id)
        )
    except Exception as e:
        logger.error(f"Error in subscription manage callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_level_"))
def set_level_callback(call):
    """
    Set subscription level
    """
    try:
        chat_id = call.message.chat.id
        parts = call.data.split("_")
        user_id = int(parts[2])
        level = parts[3]
        
        session = get_session()
        
        # Check if current user is admin
        admin = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not admin or not admin.is_admin:
            bot.answer_callback_query(call.id, "You don't have permission to manage subscriptions.")
            return
        
        # Get target user
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found.")
            return
        
        # Show duration selection
        bot.edit_message_text(
            f"🔄 Set Duration for {level} Subscription\n\n"
            f"User: {user.username or user.first_name}\n"
            f"ID: {user.chat_id}\n\n"
            f"Select subscription duration:",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=subscription_durations_keyboard(user_id, level)
        )
    except Exception as e:
        logger.error(f"Error in set level callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_duration_"))
def set_duration_callback(call):
    """
    Set subscription duration
    """
    try:
        chat_id = call.message.chat.id
        parts = call.data.split("_")
        user_id = int(parts[2])
        level = parts[3]
        duration = " ".join(parts[4:])
        
        session = get_session()
        
        # Check if current user is admin
        admin = session.query(User).filter_by(chat_id=str(chat_id)).first()
        if not admin or not admin.is_admin:
            bot.answer_callback_query(call.id, "You don't have permission to manage subscriptions.")
            return
        
        # Get target user
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            bot.answer_callback_query(call.id, "User not found.")
            return
        
        # Calculate expiry date
        days = SUBSCRIPTION_DURATIONS.get(duration, 30)  # Default to 30 days if duration not found
        expiry_date = datetime.utcnow() + timedelta(days=days)
        
        # Update subscription
        user.subscription_level = SubscriptionLevel(level)
        user.subscription_expiry = expiry_date
        session.commit()
        
        # Show confirmation
        bot.edit_message_text(
            f"✅ Subscription updated successfully!\n\n"
            f"User: {user.username or user.first_name}\n"
            f"ID: {user.chat_id}\n\n"
            f"New Subscription:\n"
            f"- Level: {level}\n"
            f"- Duration: {duration}\n"
            f"- Expires: {expiry_date.strftime('%Y-%m-%d %H:%M:%S')}",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=back_button("admin_subscriptions")
        )
        
        # Notify the user
        try:
            bot.send_message(
                user.chat_id,
                f"🎉 Your subscription has been updated!\n\n"
                f"New Subscription:\n"
                f"- Level: {level}\n"
                f"- Duration: {duration}\n"
                f"- Expires: {expiry_date.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Thank you for using Butter Ads Bot Service!"
            )
        except:
            # Ignore if can't send message to the user
            pass
    except Exception as e:
        logger.error(f"Error in set duration callback: {str(e)}")
        bot.send_message(
            chat_id,
            f"😞 An error occurred. Please try again later.\nError: {format_error(e)}",
            reply_markup=back_button()
        )
    finally:
        if 'session' in locals():
            session.close()

# ==================== Helper Functions ====================
def edit_message_with_banner(message, text, reply_markup=None):
    """
    Edit message with banner (if it was sent with a photo)
    """
    try:
        # Send new message if edit fails
        try:
            if hasattr(message, 'content_type') and message.content_type == 'photo':
                bot.edit_message_caption(
                    caption=text,
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
            else:
                bot.edit_message_text(
                    text=text,
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.warning(f"Failed to edit message: {e}")
            bot.send_message(
                message.chat.id,
                text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Error editing message with banner: {str(e)}")
        # Try without parse_mode if there's a formatting issue
        try:
            if message.content_type == 'photo':
                bot.edit_message_caption(
                    caption=text,
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    reply_markup=reply_markup
                )
            else:
                bot.edit_message_text(
                    text=text,
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    reply_markup=reply_markup
                )
        except Exception:
            # If all else fails, send a new message
            bot.send_message(
                message.chat.id,
                text,
                reply_markup=reply_markup
            )

# Register group handler (for connected bots in scheduler.py)

# ==================== Default Message Handler ====================
@bot.message_handler(func=lambda message: True)
def default_handler(message):
    """
    Handle any message that doesn't match other handlers
    """
    chat_id = message.chat.id
    
    # Reset state
    user_states[chat_id] = State.IDLE
    
    # If in a private chat, show the menu
    if message.chat.type == 'private':
        bot.send_message(
            chat_id,
            "Welcome to Butter Ads Bot! Please use the menu below:",
            reply_markup=main_menu_keyboard()
        )
