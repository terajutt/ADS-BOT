import logging
from telebot import types
from sqlalchemy.exc import SQLAlchemyError

from database import get_session
from models import User, Bot, Group, AdMessage, SubscriptionLevel, MessageInterval
from config import SUBSCRIPTION_LEVELS, MAX_PHOTOS
from utils import check_subscription, count_user_bots, count_user_groups, format_error
from bot_manager import BotManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class UserHandler:
    """
    Handles user-specific operations
    """
    @staticmethod
    def register_user(chat_id, username, first_name, last_name, is_admin=False):
        """
        Register a new user or update existing user
        """
        try:
            session = get_session()
            
            # Check if user exists
            user = session.query(User).filter_by(chat_id=str(chat_id)).first()
            
            if user:
                # Update user info
                if username:
                    user.username = username
                if first_name:
                    user.first_name = first_name
                if last_name:
                    user.last_name = last_name
                # Don't override admin status if already set
                if is_admin and not user.is_admin:
                    user.is_admin = is_admin
            else:
                # Create new user
                user = User(
                    chat_id=str(chat_id),
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    is_admin=is_admin
                )
                session.add(user)
            
            session.commit()
            
            return True, user
        except SQLAlchemyError as e:
            logger.error(f"Database error in register_user: {e}")
            session.rollback()
            return False, f"Database error: {str(e)}"
        except Exception as e:
            logger.error(f"General error in register_user: {e}")
            return False, f"Error: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()
    
    @staticmethod
    def get_user_subscription(chat_id):
        """
        Get subscription info for a user
        """
        try:
            session = get_session()
            
            user = session.query(User).filter_by(chat_id=str(chat_id)).first()
            if not user:
                return False, "User not found"
            
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
                from datetime import datetime
                expiry_text = user.subscription_expiry.strftime("%Y-%m-%d %H:%M:%S")
                days_remaining = (user.subscription_expiry - datetime.utcnow()).days
                
                if days_remaining < 0:
                    days_remaining = 0
            
            subscription_info = {
                "active": subscription_active,
                "level": level_text,
                "expiry": expiry_text,
                "days_remaining": days_remaining,
                "bot_count": bot_count,
                "group_count": group_count,
                "max_bots": max_bots,
                "max_groups": max_groups
            }
            
            return True, subscription_info
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_user_subscription: {e}")
            return False, f"Database error: {str(e)}"
        except Exception as e:
            logger.error(f"General error in get_user_subscription: {e}")
            return False, f"Error: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()
    
    @staticmethod
    def connect_bot(chat_id, bot_token):
        """
        Connect a new bot to the user's account
        """
        try:
            session = get_session()
            
            # Get user
            user = session.query(User).filter_by(chat_id=str(chat_id)).first()
            if not user:
                return False, "User not found"
            
            # Check subscription
            if not check_subscription(user):
                return False, "Subscription expired"
            
            # Check if user has reached bot limit
            bot_count = count_user_bots(session, user.id)
            max_bots = 0
            if user.subscription_level:
                level_name = user.subscription_level.value
                max_bots = SUBSCRIPTION_LEVELS.get(level_name, {}).get("bots", 0)
            
            if bot_count >= max_bots:
                return False, f"Bot limit reached ({bot_count}/{max_bots})"
            
            # Validate token
            bot_info = BotManager.check_bot_token(bot_token)
            if not bot_info:
                return False, "Invalid bot token"
            
            # Check if bot already exists
            existing_bot = session.query(Bot).filter_by(token=bot_token).first()
            if existing_bot:
                return False, "Bot already connected"
            
            # Create new bot
            new_bot = Bot(
                user_id=user.id,
                token=bot_token,
                bot_username=bot_info.get('username')
            )
            session.add(new_bot)
            session.commit()
            
            return True, {
                "bot_id": new_bot.id,
                "username": bot_info.get('username'),
                "first_name": bot_info.get('first_name')
            }
        except SQLAlchemyError as e:
            logger.error(f"Database error in connect_bot: {e}")
            session.rollback()
            return False, f"Database error: {str(e)}"
        except Exception as e:
            logger.error(f"General error in connect_bot: {e}")
            return False, f"Error: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()
    
    @staticmethod
    def get_user_bots(chat_id):
        """
        Get list of bots for a user
        """
        try:
            session = get_session()
            
            # Get user
            user = session.query(User).filter_by(chat_id=str(chat_id)).first()
            if not user:
                return False, "User not found"
            
            # Get bots
            bots_list = []
            for bot_record in user.bots:
                # Count groups
                groups_count = session.query(Group).filter_by(bot_id=bot_record.id).count()
                
                # Check if bot has an ad message
                ad_message = session.query(AdMessage).filter_by(bot_id=bot_record.id).first()
                ad_status = True if ad_message else False
                
                bots_list.append({
                    "id": bot_record.id,
                    "username": bot_record.bot_username,
                    "groups_count": groups_count,
                    "ad_message_set": ad_status,
                    "created_at": bot_record.created_at.strftime("%Y-%m-%d %H:%M:%S")
                })
            
            return True, bots_list
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_user_bots: {e}")
            return False, f"Database error: {str(e)}"
        except Exception as e:
            logger.error(f"General error in get_user_bots: {e}")
            return False, f"Error: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()
    
    @staticmethod
    def disconnect_bot(chat_id, bot_id):
        """
        Disconnect a bot from user's account
        """
        try:
            session = get_session()
            
            # Get user
            user = session.query(User).filter_by(chat_id=str(chat_id)).first()
            if not user:
                return False, "User not found"
            
            # Get bot
            bot_record = session.query(Bot).filter_by(id=bot_id, user_id=user.id).first()
            if not bot_record:
                return False, "Bot not found or you don't have permission"
            
            # Save username for confirmation
            bot_username = bot_record.bot_username
            
            # Delete bot (cascade will delete groups and ad messages)
            session.delete(bot_record)
            session.commit()
            
            return True, {"username": bot_username}
        except SQLAlchemyError as e:
            logger.error(f"Database error in disconnect_bot: {e}")
            session.rollback()
            return False, f"Database error: {str(e)}"
        except Exception as e:
            logger.error(f"General error in disconnect_bot: {e}")
            return False, f"Error: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()
    
    @staticmethod
    def get_bot_groups(chat_id, bot_id):
        """
        Get list of groups for a bot
        """
        try:
            session = get_session()
            
            # Get user
            user = session.query(User).filter_by(chat_id=str(chat_id)).first()
            if not user:
                return False, "User not found"
            
            # Get bot
            bot_record = session.query(Bot).filter_by(id=bot_id, user_id=user.id).first()
            if not bot_record:
                return False, "Bot not found or you don't have permission"
            
            # Get groups
            groups_list = []
            for group in session.query(Group).filter_by(bot_id=bot_id).all():
                groups_list.append({
                    "id": group.id,
                    "group_id": group.group_id,
                    "group_title": group.group_title,
                    "interval": group.interval.value,
                    "active": group.active,
                    "media_allowed": group.media_allowed,
                    "last_ad_sent": group.last_ad_sent.strftime("%Y-%m-%d %H:%M:%S") if group.last_ad_sent else None
                })
            
            return True, {
                "bot_username": bot_record.bot_username,
                "groups": groups_list
            }
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_bot_groups: {e}")
            return False, f"Database error: {str(e)}"
        except Exception as e:
            logger.error(f"General error in get_bot_groups: {e}")
            return False, f"Error: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()
    
    @staticmethod
    def set_group_interval(chat_id, group_id, interval):
        """
        Set interval for a group
        """
        try:
            session = get_session()
            
            # Get user
            user = session.query(User).filter_by(chat_id=str(chat_id)).first()
            if not user:
                return False, "User not found"
            
            # Get group
            group = session.query(Group).filter_by(id=group_id).first()
            if not group:
                return False, "Group not found"
            
            # Verify bot belongs to user
            bot_record = session.query(Bot).filter_by(id=group.bot_id, user_id=user.id).first()
            if not bot_record:
                return False, "Bot not found or you don't have permission"
            
            # Update interval
            try:
                group.interval = MessageInterval(interval)
                session.commit()
            except ValueError:
                return False, "Invalid interval"
            
            return True, {
                "group_title": group.group_title or group.group_id,
                "interval": interval
            }
        except SQLAlchemyError as e:
            logger.error(f"Database error in set_group_interval: {e}")
            session.rollback()
            return False, f"Database error: {str(e)}"
        except Exception as e:
            logger.error(f"General error in set_group_interval: {e}")
            return False, f"Error: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()
    
    @staticmethod
    def remove_group(chat_id, group_id):
        """
        Remove a group from a bot
        """
        try:
            session = get_session()
            
            # Get user
            user = session.query(User).filter_by(chat_id=str(chat_id)).first()
            if not user:
                return False, "User not found"
            
            # Get group
            group = session.query(Group).filter_by(id=group_id).first()
            if not group:
                return False, "Group not found"
            
            # Verify bot belongs to user
            bot_record = session.query(Bot).filter_by(id=group.bot_id, user_id=user.id).first()
            if not bot_record:
                return False, "Bot not found or you don't have permission"
            
            # Save group info for confirmation
            group_title = group.group_title or group.group_id
            bot_id = group.bot_id
            
            # Delete group
            session.delete(group)
            session.commit()
            
            return True, {
                "group_title": group_title,
                "bot_id": bot_id
            }
        except SQLAlchemyError as e:
            logger.error(f"Database error in remove_group: {e}")
            session.rollback()
            return False, f"Database error: {str(e)}"
        except Exception as e:
            logger.error(f"General error in remove_group: {e}")
            return False, f"Error: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()
    
    @staticmethod
    def set_text_ad(chat_id, bot_id, text):
        """
        Set text ad message for a bot
        """
        try:
            session = get_session()
            
            # Get user
            user = session.query(User).filter_by(chat_id=str(chat_id)).first()
            if not user:
                return False, "User not found"
            
            # Get bot
            bot_record = session.query(Bot).filter_by(id=bot_id, user_id=user.id).first()
            if not bot_record:
                return False, "Bot not found or you don't have permission"
            
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
            
            return True, {
                "bot_username": bot_record.bot_username,
                "text_preview": text[:100] + "..." if len(text) > 100 else text
            }
        except SQLAlchemyError as e:
            logger.error(f"Database error in set_text_ad: {e}")
            session.rollback()
            return False, f"Database error: {str(e)}"
        except Exception as e:
            logger.error(f"General error in set_text_ad: {e}")
            return False, f"Error: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()
    
    @staticmethod
    def set_photo_ad(chat_id, bot_id, photo_ids, caption=None):
        """
        Set photo ad message for a bot
        """
        try:
            session = get_session()
            
            # Get user
            user = session.query(User).filter_by(chat_id=str(chat_id)).first()
            if not user:
                return False, "User not found"
            
            # Get bot
            bot_record = session.query(Bot).filter_by(id=bot_id, user_id=user.id).first()
            if not bot_record:
                return False, "Bot not found or you don't have permission"
            
            # Validate photo_ids
            if not photo_ids or not isinstance(photo_ids, list):
                return False, "No photos provided"
            
            if len(photo_ids) > MAX_PHOTOS:
                return False, f"Maximum {MAX_PHOTOS} photos allowed"
            
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
            
            return True, {
                "bot_username": bot_record.bot_username,
                "photo_count": len(photo_ids),
                "caption": caption
            }
        except SQLAlchemyError as e:
            logger.error(f"Database error in set_photo_ad: {e}")
            session.rollback()
            return False, f"Database error: {str(e)}"
        except Exception as e:
            logger.error(f"General error in set_photo_ad: {e}")
            return False, f"Error: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()
    
    @staticmethod
    def get_ad_message(chat_id, bot_id):
        """
        Get current ad message for a bot
        """
        try:
            session = get_session()
            
            # Get user
            user = session.query(User).filter_by(chat_id=str(chat_id)).first()
            if not user:
                return False, "User not found"
            
            # Get bot
            bot_record = session.query(Bot).filter_by(id=bot_id, user_id=user.id).first()
            if not bot_record:
                return False, "Bot not found or you don't have permission"
            
            # Get ad message
            ad_message = session.query(AdMessage).filter_by(bot_id=bot_id).first()
            if not ad_message:
                return False, "No ad message set"
            
            if ad_message.text:
                return True, {
                    "type": "text",
                    "text": ad_message.text,
                    "photo_ids": None,
                    "caption": None
                }
            else:
                return True, {
                    "type": "photo",
                    "text": None,
                    "photo_ids": ad_message.photo_ids,
                    "caption": ad_message.caption
                }
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_ad_message: {e}")
            return False, f"Database error: {str(e)}"
        except Exception as e:
            logger.error(f"General error in get_ad_message: {e}")
            return False, f"Error: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()
