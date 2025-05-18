from telebot import types
from config import SUBSCRIPTION_LEVELS, SUBSCRIPTION_DURATIONS, MESSAGE_INTERVALS

def main_menu_keyboard():
    """
    Main menu keyboard with all options for users
    """
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("🤖 My Bots", callback_data="my_bots"),
        types.InlineKeyboardButton("✨ Connect New Bot", callback_data="connect_bot"),
        types.InlineKeyboardButton("❓ Help", callback_data="help"),
        types.InlineKeyboardButton("📊 Subscription", callback_data="subscription_info")
    ]
    keyboard.add(*buttons)
    return keyboard

def admin_menu_keyboard():
    """
    Admin menu keyboard with administrative options
    """
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("👑 Manage Users", callback_data="admin_users"),
        types.InlineKeyboardButton("🔄 Manage Subscriptions", callback_data="admin_subscriptions"),
        types.InlineKeyboardButton("🔊 Broadcast Message", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("📊 System Stats", callback_data="admin_stats"),
        types.InlineKeyboardButton("👨‍💼 Add Admin", callback_data="admin_add"),
        types.InlineKeyboardButton("⬅️ Back", callback_data="main_menu")
    ]
    keyboard.add(*buttons)
    return keyboard

def back_button(callback_data="main_menu"):
    """
    Simple back button
    """
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("⬅️ Back", callback_data=callback_data))
    return keyboard

def confirm_cancel_keyboard(confirm_data, cancel_data="main_menu"):
    """
    Confirm/Cancel buttons for operations that need confirmation
    """
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("✅ Confirm", callback_data=confirm_data),
        types.InlineKeyboardButton("❌ Cancel", callback_data=cancel_data)
    )
    return keyboard

def bots_list_keyboard(bots):
    """
    Create keyboard with list of user's bots
    """
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    
    for bot in bots:
        bot_name = bot.bot_username or f"Bot {bot.id}"
        keyboard.add(types.InlineKeyboardButton(f"🤖 {bot_name}", callback_data=f"bot_{bot.id}"))
    
    keyboard.add(types.InlineKeyboardButton("⬅️ Back", callback_data="main_menu"))
    return keyboard

def bot_actions_keyboard(bot_id):
    """
    Actions for a specific bot
    """
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("📋 Connected Groups", callback_data=f"groups_{bot_id}"),
        types.InlineKeyboardButton("📝 Set Ad Message", callback_data=f"ad_message_{bot_id}"),
        types.InlineKeyboardButton("❌ Disconnect Bot", callback_data=f"disconnect_{bot_id}"),
        types.InlineKeyboardButton("⬅️ Back", callback_data="my_bots")
    ]
    keyboard.add(*buttons)
    return keyboard

def groups_list_keyboard(groups, bot_id):
    """
    List of groups connected to a specific bot
    """
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    
    for group in groups:
        group_name = group.group_title or f"Group {group.group_id}"
        status = "✅" if group.active else "❌"
        keyboard.add(types.InlineKeyboardButton(
            f"{status} {group_name}", 
            callback_data=f"group_{group.id}"
        ))
    
    keyboard.add(types.InlineKeyboardButton("⬅️ Back", callback_data=f"bot_{bot_id}"))
    return keyboard

def group_actions_keyboard(group_id, bot_id):
    """
    Actions for a specific group
    """
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("⏱️ Set Interval", callback_data=f"interval_{group_id}"),
        types.InlineKeyboardButton("❌ Remove Group", callback_data=f"remove_group_{group_id}"),
        types.InlineKeyboardButton("⬅️ Back", callback_data=f"groups_{bot_id}")
    ]
    keyboard.add(*buttons)
    return keyboard

def ad_message_type_keyboard(bot_id):
    """
    Choose type of ad message (text or media)
    """
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("📝 Text", callback_data=f"text_ad_{bot_id}"),
        types.InlineKeyboardButton("🖼️ Photos", callback_data=f"photo_ad_{bot_id}"),
        types.InlineKeyboardButton("⬅️ Back", callback_data=f"bot_{bot_id}")
    ]
    keyboard.add(*buttons)
    return keyboard

def intervals_keyboard(group_id):
    """
    Create keyboard with available message intervals
    """
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    
    # Make sure group_id is an integer to avoid issues
    try:
        group_id = int(group_id)
    except (ValueError, TypeError):
        # If we can't convert to int, just use as is (fallback)
        pass
        
    # Create buttons for each interval
    for interval_name in MESSAGE_INTERVALS:
        keyboard.add(types.InlineKeyboardButton(
            interval_name, 
            callback_data=f"set_interval_{group_id}_{interval_name}"
        ))
    
    keyboard.add(types.InlineKeyboardButton("⬅️ Back", callback_data=f"group_{group_id}"))
    return keyboard

def subscription_levels_keyboard(user_id):
    """
    Create keyboard with available subscription levels
    """
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    for level in SUBSCRIPTION_LEVELS:
        bots = SUBSCRIPTION_LEVELS[level]["bots"]
        groups = SUBSCRIPTION_LEVELS[level]["groups"]
        keyboard.add(types.InlineKeyboardButton(
            f"{level} ({bots} bots, {groups} groups)",
            callback_data=f"set_level_{user_id}_{level}"
        ))
    
    keyboard.add(types.InlineKeyboardButton("⬅️ Back", callback_data="admin_subscriptions"))
    return keyboard

def subscription_durations_keyboard(user_id, level):
    """
    Create keyboard with available subscription durations
    """
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    for duration in SUBSCRIPTION_DURATIONS:
        keyboard.add(types.InlineKeyboardButton(
            duration,
            callback_data=f"set_duration_{user_id}_{level}_{duration}"
        ))
    
    keyboard.add(types.InlineKeyboardButton("⬅️ Back", callback_data=f"admin_subscriptions"))
    return keyboard

def help_menu_keyboard():
    """
    Help menu with different sections
    """
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("🤖 Create a Bot", callback_data="help_create_bot"),
        types.InlineKeyboardButton("🔑 Get Bot Token", callback_data="help_get_token"),
        types.InlineKeyboardButton("🔄 Connect Bot", callback_data="help_connect"),
        types.InlineKeyboardButton("➕ Add to Group", callback_data="help_add_group"),
        types.InlineKeyboardButton("📝 Set Ad Message", callback_data="help_set_ad"),
        types.InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")
    ]
    keyboard.add(*buttons)
    return keyboard
