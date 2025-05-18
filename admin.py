import logging
from datetime import datetime, timedelta
from telebot import types
from sqlalchemy.exc import SQLAlchemyError

from database import get_session
from models import User, Bot, Group, SubscriptionLevel
from config import SUBSCRIPTION_LEVELS, SUBSCRIPTION_DURATIONS, MAIN_ADMIN_CHAT_ID
from utils import check_subscription, count_user_bots, count_user_groups, format_error

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AdminHandler:
    """
    Handles admin-specific operations
    """
    @staticmethod
    def get_system_stats():
        """
        Get system statistics for admin dashboard
        """
        try:
            session = get_session()
            
            # Count various entities
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
            
            stats = {
                "total_users": total_users,
                "total_admins": total_admins,
                "total_bots": total_bots,
                "total_groups": total_groups,
                "active_subscriptions": active_subs,
                "bronze_subscriptions": bronze,
                "silver_subscriptions": silver,
                "gold_subscriptions": gold
            }
            
            return stats
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_system_stats: {e}")
            return None
        except Exception as e:
            logger.error(f"General error in get_system_stats: {e}")
            return None
        finally:
            if 'session' in locals():
                session.close()
    
    @staticmethod
    def update_user_subscription(user_id, level, duration):
        """
        Update a user's subscription level and duration
        """
        try:
            session = get_session()
            
            # Get user
            user = session.query(User).filter_by(id=user_id).first()
            if not user:
                return False, "User not found"
            
            # Check if level is valid
            if level not in [e.value for e in SubscriptionLevel]:
                return False, "Invalid subscription level"
            
            # Calculate expiry date
            days = SUBSCRIPTION_DURATIONS.get(duration, 30)  # Default to 30 days if duration not found
            expiry_date = datetime.utcnow() + timedelta(days=days)
            
            # Update subscription
            user.subscription_level = SubscriptionLevel(level)
            user.subscription_expiry = expiry_date
            session.commit()
            
            return True, {
                "user": user.username or user.first_name,
                "level": level,
                "duration": duration,
                "expiry": expiry_date.strftime('%Y-%m-%d %H:%M:%S')
            }
        except SQLAlchemyError as e:
            logger.error(f"Database error in update_user_subscription: {e}")
            return False, f"Database error: {str(e)}"
        except Exception as e:
            logger.error(f"General error in update_user_subscription: {e}")
            return False, f"Error: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()
    
    @staticmethod
    def toggle_admin_status(user_id, admin_chat_id):
        """
        Toggle admin status for a user
        """
        try:
            session = get_session()
            
            # Get admin making the request
            admin = session.query(User).filter_by(chat_id=str(admin_chat_id)).first()
            if not admin or not admin.is_admin:
                return False, "You don't have permission to manage admins"
            
            # Get target user
            user = session.query(User).filter_by(id=user_id).first()
            if not user:
                return False, "User not found"
            
            # Don't allow removing main admin
            if str(user.chat_id) == str(MAIN_ADMIN_CHAT_ID) and user.is_admin:
                return False, "Cannot remove main admin status"
            
            # Toggle admin status
            user.is_admin = not user.is_admin
            session.commit()
            
            return True, {
                "user": user.username or user.first_name,
                "is_admin": user.is_admin,
                "chat_id": user.chat_id
            }
        except SQLAlchemyError as e:
            logger.error(f"Database error in toggle_admin_status: {e}")
            return False, f"Database error: {str(e)}"
        except Exception as e:
            logger.error(f"General error in toggle_admin_status: {e}")
            return False, f"Error: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()
    
    @staticmethod
    def add_admin_by_chat_id(new_admin_chat_id, admin_chat_id):
        """
        Add a new admin by chat ID
        """
        try:
            session = get_session()
            
            # Get admin making the request
            admin = session.query(User).filter_by(chat_id=str(admin_chat_id)).first()
            if not admin or not admin.is_admin:
                return False, "You don't have permission to add admins"
            
            # Find user by chat ID
            target_user = session.query(User).filter_by(chat_id=new_admin_chat_id).first()
            
            if not target_user:
                # Create user if not exists
                target_user = User(chat_id=new_admin_chat_id)
                session.add(target_user)
            
            # Set as admin
            target_user.is_admin = True
            session.commit()
            
            return True, {
                "user": target_user.username or target_user.first_name or "New user",
                "chat_id": new_admin_chat_id
            }
        except SQLAlchemyError as e:
            logger.error(f"Database error in add_admin_by_chat_id: {e}")
            return False, f"Database error: {str(e)}"
        except Exception as e:
            logger.error(f"General error in add_admin_by_chat_id: {e}")
            return False, f"Error: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()
    
    @staticmethod
    def get_user_details(user_id):
        """
        Get detailed information about a user
        """
        try:
            session = get_session()
            
            # Get user
            user = session.query(User).filter_by(id=user_id).first()
            if not user:
                return False, "User not found"
            
            # Get user stats
            bot_count = count_user_bots(session, user.id)
            group_count = count_user_groups(session, user.id)
            
            # Format level and expiry
            level = user.subscription_level.value if user.subscription_level else "None"
            expiry = "Never" if not user.subscription_expiry else user.subscription_expiry.strftime("%Y-%m-%d %H:%M:%S")
            subscription_active = check_subscription(user)
            
            user_details = {
                "id": user.id,
                "chat_id": user.chat_id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_admin": user.is_admin,
                "subscription_level": level,
                "subscription_expiry": expiry,
                "subscription_active": subscription_active,
                "bot_count": bot_count,
                "group_count": group_count,
                "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            return True, user_details
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_user_details: {e}")
            return False, f"Database error: {str(e)}"
        except Exception as e:
            logger.error(f"General error in get_user_details: {e}")
            return False, f"Error: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()
    
    @staticmethod
    def get_all_users():
        """
        Get a list of all users
        """
        try:
            session = get_session()
            
            users_list = []
            users = session.query(User).all()
            
            for user in users:
                subscription_active = check_subscription(user)
                level = user.subscription_level.value if user.subscription_level else "None"
                
                users_list.append({
                    "id": user.id,
                    "chat_id": user.chat_id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "is_admin": user.is_admin,
                    "subscription_level": level,
                    "subscription_active": subscription_active
                })
            
            return True, users_list
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_all_users: {e}")
            return False, f"Database error: {str(e)}"
        except Exception as e:
            logger.error(f"General error in get_all_users: {e}")
            return False, f"Error: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()
