import logging
import os
from database import init_db
from handlers import bot
from scheduler import start_scheduler
from fix_bot_handlers import register_all_bots

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        # Initialize database
        logger.info("Initializing database...")
        init_db()
        
        # Start scheduler - this will also register bots in scheduler.py
        logger.info("Starting scheduler...")
        start_scheduler()
        
        # Register bots for dedicated command handling
        # But we will skip the polling here since scheduler is already handling that
        # This conflict was causing the "terminated by other getUpdates request" error
        # num_bots = register_all_bots()
        # logger.info(f"Registered {num_bots} bots for command handling")
        
        # Start the main bot (our main admin panel bot)
        logger.info("Starting Butter Ads Bot...")
        bot.infinity_polling(skip_pending=True)
    except Exception as e:
        logger.error(f"Error starting bot: {str(e)}")
