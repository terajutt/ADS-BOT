import telebot
import logging
from telebot.apihelper import ApiException
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import time

from config import MAIN_BOT_TOKEN, MAX_PHOTOS, AD_FOOTER
from database import get_session
from models import Bot, Group, AdMessage, MessageInterval

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BotManager:
    """
    Manages operations for connected bots
    """
    @staticmethod
    def check_bot_token(token):
        """
        Check if a bot token is valid by creating a temporary bot instance
        and requesting the bot's info
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
            logger.error(f"Error checking bot token: {e}")
            return None

    @staticmethod
    def send_ad_message(bot_id):
        """
        Send ad message to all groups for a specific bot
        """
        try:
            session = get_session()
            bot_record = session.query(Bot).filter_by(id=bot_id).first()
            
            if not bot_record:
                logger.error(f"Bot not found: {bot_id}")
                return False
            
            # Get ad message
            ad_message = session.query(AdMessage).filter_by(bot_id=bot_id).first()
            if not ad_message:
                logger.warning(f"No ad message set for bot: {bot_id}")
                return False
            
            # Get active groups
            groups = session.query(Group).filter_by(bot_id=bot_id, active=True).all()
            if not groups:
                logger.info(f"No active groups for bot: {bot_id}")
                return False
            
            # Create bot instance
            client_bot = telebot.TeleBot(bot_record.token)
            
            success_count = 0
            
            # Send message to each group
            for group in groups:
                try:
                    # Check if it's time to send the ad based on interval
                    if group.last_ad_sent:
                        interval_minutes = 60  # Default 1 hour
                        
                        if group.interval == MessageInterval.TEN_MIN:
                            interval_minutes = 10
                        elif group.interval == MessageInterval.THIRTY_MIN:
                            interval_minutes = 30
                        elif group.interval == MessageInterval.ONE_HOUR:
                            interval_minutes = 60
                        elif group.interval == MessageInterval.SIX_HOURS:
                            interval_minutes = 360
                        
                        time_diff = datetime.utcnow() - group.last_ad_sent
                        if time_diff.total_seconds() < interval_minutes * 60:
                            # Not time to send yet
                            continue
                    
                    # Send ad based on type
                    if ad_message.text:  # Text message
                        full_text = ad_message.text + "\n\n" + AD_FOOTER
                        client_bot.send_message(group.group_id, full_text)
                        success_count += 1
                    elif ad_message.photo_ids and isinstance(ad_message.photo_ids, list):  # Photo message with valid list
                        if not group.media_allowed:
                            # Send text only if media not allowed
                            text = ad_message.caption or "Check out our ad!"
                            full_text = text + "\n\n" + AD_FOOTER
                            client_bot.send_message(group.group_id, full_text)
                            success_count += 1
                        else:
                            # Always use a fallback text message in case photos fail
                            try:
                                caption_text = ad_message.caption or "Check out our latest update!"
                                full_text = caption_text + "\n\n" + AD_FOOTER
                                
                                # Try to send a simple text message first to ensure we can post to this group
                                client_bot.send_message(group.group_id, full_text)
                                success_count += 1
                                
                                # For now, we'll skip sending photos due to file ID expiration issues
                                logger.info(f"Successfully sent text message to group {group.group_id}")
                                
                            except Exception as text_error:
                                logger.error(f"Error sending message to group {group.group_id}: {text_error}")
                    else:
                        # No ad content set or invalid photo_ids
                        logger.warning(f"No valid content in ad for bot {bot_id}")
                        # Send default message
                        try:
                            default_text = "📢 Stay tuned for updates!" + "\n\n" + AD_FOOTER
                            client_bot.send_message(group.group_id, default_text)
                            success_count += 1
                        except Exception as default_error:
                            logger.error(f"Error sending default message: {default_error}")
                    
                    # Update last_ad_sent timestamp
                    group.last_ad_sent = datetime.utcnow()
                    session.commit()
                    
                    # Sleep to avoid flood limits
                    time.sleep(1)
                except ApiException as e:
                    if "chat not found" in str(e).lower() or "bot was kicked" in str(e).lower():
                        # Bot was removed from the group
                        logger.warning(f"Bot was removed from group {group.group_id}, marking as inactive")
                        group.active = False
                        session.commit()
                    elif "not enough rights" in str(e).lower():
                        # Bot doesn't have permission to post
                        logger.warning(f"Bot doesn't have permission to post in group {group.group_id}, marking as inactive")
                        group.active = False
                        session.commit()
                    elif "MEDIA_CAPTION_TOO_LONG" in str(e).upper():
                        # Caption too long, try without footer
                        try:
                            if ad_message.text:
                                client_bot.send_message(group.group_id, ad_message.text)
                            elif ad_message.photo_ids and group.media_allowed:
                                client_bot.send_photo(group.group_id, ad_message.photo_ids[0], caption=ad_message.caption or "")
                            success_count += 1
                            group.last_ad_sent = datetime.utcnow()
                            session.commit()
                        except:
                            logger.error(f"Failed to send ad to group {group.group_id} even without footer")
                    elif "MEDIA_GROUP_INVALID" in str(e).upper():
                        # Try sending photos individually
                        try:
                            for photo_id in ad_message.photo_ids:
                                client_bot.send_photo(group.group_id, photo_id)
                                time.sleep(0.5)
                            success_count += 1
                            group.last_ad_sent = datetime.utcnow()
                            session.commit()
                        except:
                            logger.error(f"Failed to send individual photos to group {group.group_id}")
                    else:
                        logger.error(f"Error sending ad to group {group.group_id}: {e}")
                except Exception as e:
                    logger.error(f"General error sending ad to group {group.group_id}: {e}")
            
            logger.info(f"Sent ads to {success_count}/{len(groups)} groups for bot {bot_id}")
            return success_count > 0
        except SQLAlchemyError as e:
            logger.error(f"Database error in send_ad_message: {e}")
            return False
        except Exception as e:
            logger.error(f"General error in send_ad_message: {e}")
            return False
        finally:
            if 'session' in locals():
                session.close()

    @staticmethod
    def register_group(bot_token, group_id, group_title):
        """
        Register a group for a bot
        """
        try:
            session = get_session()
            
            # Find bot by token
            bot_record = session.query(Bot).filter_by(token=bot_token).first()
            if not bot_record:
                logger.warning(f"Bot not found for token when registering group")
                return False
            
            # Check if group already exists for this bot
            existing_group = session.query(Group).filter_by(bot_id=bot_record.id, group_id=str(group_id)).first()
            if existing_group:
                # Update group title and set as active
                existing_group.group_title = group_title
                existing_group.active = True
                session.commit()
                logger.info(f"Updated existing group {group_id} for bot {bot_record.id}")
                return True
            
            # Check if user has reached group limit
            user = bot_record.user
            if not user:
                logger.warning(f"User not found for bot {bot_record.id}")
                return False
            
            # Count user's groups
            groups_count = sum(len(b.groups) for b in user.bots)
            
            # Get max groups based on subscription level
            from utils import get_max_groups
            max_groups = get_max_groups(user)
            
            if groups_count >= max_groups:
                logger.warning(f"User {user.id} has reached group limit of {max_groups}")
                return False
            
            # Check if media is allowed in the group
            media_allowed = True
            try:
                import telebot
                temp_bot = telebot.TeleBot(bot_token)
                
                # Send a simple text message first
                temp_bot.send_message(group_id, "🔄 Checking group permissions...")
                
                # Try to send a photo with caption to check media permissions
                try:
                    # No need to use a file_id, use a local file or URL
                    msg = temp_bot.send_photo(group_id, 'https://via.placeholder.com/50', caption="✅ Media allowed in this group")
                    # Try to delete the test messages
                    try:
                        temp_bot.delete_message(group_id, msg.message_id)
                    except:
                        pass
                except Exception as e:
                    if "not enough rights" in str(e).lower():
                        media_allowed = False
                        logger.info(f"Media not allowed in group {group_id}")
                        # Notify the group
                        temp_bot.send_message(group_id, "⚠️ This bot doesn't have permission to send media. Only text ads will be sent.")
            except Exception as e:
                # Continue with registration even if media check fails
                logger.warning(f"Could not check media permissions for group {group_id}: {e}")
            
            # Create new group
            new_group = Group(
                bot_id=bot_record.id,
                group_id=str(group_id),
                group_title=group_title,
                interval=MessageInterval.ONE_HOUR,
                active=True,
                media_allowed=media_allowed
            )
            session.add(new_group)
            session.commit()
            
            logger.info(f"Registered new group {group_id} for bot {bot_record.id}")
            
            # Send a final confirmation message to the group
            try:
                import telebot
                temp_bot = telebot.TeleBot(bot_token)
                temp_bot.send_message(
                    group_id,
                    f"✅ Group successfully registered for ad messages!\n\n"
                    f"Group: {group_title}\n"
                    f"Media allowed: {'Yes' if media_allowed else 'No'}\n"
                    f"Default interval: 1 hour\n\n"
                    f"The owner can manage this group's settings in the main bot."
                )
            except Exception as e:
                logger.error(f"Error sending confirmation message to group {group_id}: {e}")
            
            return True
        except SQLAlchemyError as e:
            logger.error(f"Database error in register_group: {e}")
            return False
        except Exception as e:
            logger.error(f"General error in register_group: {e}")
            return False
        finally:
            if 'session' in locals():
                session.close()

    @staticmethod
    def check_group_media_permission(bot_token, group_id):
        """
        Check if a bot can send media to a group
        """
        try:
            temp_bot = telebot.TeleBot(bot_token)
            
            # Try to send a test photo to check if media is allowed
            photo_id = "AgACAgQAAxkBAAIDXmWQU_zM_tn7KoGrAAGNblkPkQR-uQACsLoxG6qF0VKgVl0U00-3nAEAAwIAA3kAAzME"
            msg = temp_bot.send_photo(group_id, photo_id, caption="Testing media permissions")
            
            # Delete the test message
            temp_bot.delete_message(group_id, msg.message_id)
            
            return True
        except ApiException as e:
            if "not enough rights" in str(e).lower() or "MEDIA_EMPTY" in str(e).upper():
                return False
            else:
                logger.error(f"API error checking media permissions: {e}")
                return False
        except Exception as e:
            logger.error(f"General error checking media permissions: {e}")
            return False
