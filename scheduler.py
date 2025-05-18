import logging
import time
import threading
from datetime import datetime
import telebot

from config import MAIN_BOT_TOKEN
from database import get_session
from models import User, Bot
from bot_manager import BotManager
from utils import check_subscription

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Scheduler runs every minute, each bot's groups are checked based on their interval
def scheduler_task():
    """
    Main scheduler task that sends ads at appropriate intervals
    """
    logger.info("Starting scheduler task")
    while True:
        try:
            process_all_bots()
        except Exception as e:
            logger.error(f"Error in scheduler task: {e}")

        # Run every minute
        time.sleep(60)

def process_all_bots():
    """
    Process all active bots and send ads if needed
    """
    try:
        session = get_session()

        # Get all users
        users = session.query(User).all()

        active_bots = 0
        expired_users = 0

        for user in users:
            # Check subscription
            if not check_subscription(user):
                expired_users += 1
                continue

            # Process each bot for the user
            for bot_record in user.bots:
                try:
                    # Send ad message if needed
                    BotManager.send_ad_message(bot_record.id)
                    active_bots += 1
                except Exception as e:
                    logger.error(f"Error processing bot {bot_record.id}: {e}")

        logger.info(f"Processed {active_bots} active bots. {expired_users} users with expired subscriptions.")
    except Exception as e:
        logger.error(f"Error in process_all_bots: {e}")
    finally:
        if 'session' in locals():
            session.close()

def start_scheduler():
    """
    Start the scheduler task
    """
    logger.info("Starting scheduler task")

    # Set up message handlers for all bots
    session = get_session()
    try:
        bots = session.query(Bot).all()
        
        # Global dictionary to store bot instances
        global _bot_instances
        _bot_instances = {}

        # Set up command handlers for each bot
        for bot_record in bots:
            try:
                # Create bot instance 
                temp_bot = telebot.TeleBot(bot_record.token)

                # Create specific handler for this bot
                def create_handler(bot_token):
                    def handler(message):
                        try:
                            if message.chat.type in ['group', 'supergroup']:
                                temp_bot.reply_to(message, "🔄 Processing registration...")
                                handle_group_registration(bot_token, message)
                            else:
                                temp_bot.reply_to(message, "⚠️ This command only works in groups!")
                        except Exception as e:
                            logger.error(f"Error in start handler: {e}")
                    return handler

                # Register handlers
                temp_bot.message_handler(commands=['start'])(create_handler(bot_record.token))
                temp_bot.message_handler(commands=['start@' + temp_bot.get_me().username])(create_handler(bot_record.token))
                
                # Store bot instance
                _bot_instances[bot_record.token] = temp_bot
                
                # Start polling in a separate thread
                polling_thread = threading.Thread(
                    target=temp_bot.infinity_polling,
                    kwargs={'timeout': 20, 'long_polling_timeout': 10, 'skip_pending': True}
                )
                polling_thread.daemon = True
                polling_thread.start()
                
                logger.info(f"Bot {bot_record.id} set up successfully")

            except Exception as e:
                logger.error(f"Error setting up bot {bot_record.id}: {e}")

        logger.info(f"{len(bots)} bots set up for message handling")
    except Exception as e:
        logger.error(f"Error in start_scheduler: {e}")
    finally:
        session.close()

    # Start scheduler task in a separate thread
    scheduler_thread = threading.Thread(target=scheduler_task)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    logger.info("Scheduler started")

# Start group registration handler for all connected bots
def handle_group_registration(bot_token, message):
    """
    Handle /start command in a group to register the group
    """
    try:
        group_id = message.chat.id
        group_title = message.chat.title

        # Only process group messages
        if message.chat.type not in ['group', 'supergroup']:
            return

        # Create a temporary bot instance
        temp_bot = telebot.TeleBot(bot_token)

        # Initial acknowledgment
        try:
            temp_bot.reply_to(
                message,
                f"🔄 Registering this group for advertising...\n"
                f"Group: {group_title}"
            )
        except Exception as e:
            logger.error(f"Could not send initial message: {e}")

        # Register group
        success = BotManager.register_group(bot_token, group_id, group_title)

        try:
            if success:
                temp_bot.reply_to(
                    message,
                    f"✅ Group successfully registered!\n\n"
                    f"Group: {group_title}\n"
                    f"ID: {group_id}\n\n"
                    f"The bot owner can now manage ads in the main bot."
                )
            else:
                temp_bot.reply_to(
                    message,
                    f"❌ Registration failed. Possible reasons:\n"
                    f"• Group limit reached\n"
                    f"• Connection issue\n\n"
                    f"Please contact the bot owner."
                )
        except Exception as e:
            logger.error(f"Could not send confirmation: {e}")

    except Exception as e:
        logger.error(f"Error in handle_group_registration: {e}")

def setup_connected_bots():
    """
    Set up message handlers for all connected bots
    """
    try:
        import telebot
        session = get_session()
        bots = session.query(Bot).all()

        # Store bot instances globally to prevent garbage collection
        global _bot_instances
        if '_bot_instances' not in globals():
            _bot_instances = {}

        for bot_record in bots:
            try:
                # Convert token to string to avoid type issues
                token = str(bot_record.token)

                # Skip if already setup
                if token in _bot_instances:
                    logger.info(f"Bot {bot_record.id} already set up")
                    continue

                # Create the bot instance
                client_bot = telebot.TeleBot(token)

                # Create a dedicated start handler for this specific bot
                def make_start_handler(token_str):
                    @client_bot.message_handler(commands=['start'])
                    def start_command_handler(message):
                        try:
                            if message.chat.type in ['group', 'supergroup']:
                                # Let user know we're processing their request
                                client_bot.send_message(
                                    message.chat.id,
                                    "🔄 Processing... registering this group for advertising"
                                )
                                # Handle the registration
                                handle_group_registration(token_str, message)
                        except Exception as e:
                            logger.error(f"Error in start handler: {e}")
                    return start_command_handler

                # Set up the handler
                start_handler = make_start_handler(token)

                # Start polling in a separate thread with reliable parameters
                thread = threading.Thread(
                    target=client_bot.infinity_polling,
                    kwargs={
                        'timeout': 20, 
                        'skip_pending': True,
                        'interval': 0.5,
                        'long_polling_timeout': 15
                    }
                )
                thread.daemon = True  # Thread will close when main program exits
                thread.start()

                # Store reference to prevent garbage collection
                _bot_instances[token] = {
                    'bot': client_bot,
                    'thread': thread,
                    'record': bot_record
                }

                logger.info(f"Successfully started polling for bot {bot_record.id} (@{bot_record.bot_username or 'Unknown'})")
            except Exception as e:
                logger.error(f"Error setting up bot {bot_record.id}: {e}")
    except Exception as e:
        logger.error(f"Error in setup_connected_bots: {e}")
    finally:
        if 'session' in locals():
            session.close()

    # Return status for debugging
    return len(_bot_instances) if '_bot_instances' in globals() else 0