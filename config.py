import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot configuration
MAIN_BOT_TOKEN = "7507012945:AAGZTqk_OjTGh4Ut2HkJinwkL2g5hIH_raU"
MAIN_ADMIN_CHAT_ID = 6652452460

# Database configuration
DATABASE_URL = "postgresql://neondb_owner:npg_DfFY1Gs4kTdr@ep-weathered-fire-a4kn9571-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

# Subscription levels
SUBSCRIPTION_LEVELS = {
    "Bronze": {"bots": 1, "groups": 10},
    "Silver": {"bots": 3, "groups": 25},
    "Gold": {"bots": 5, "groups": 50}
}

# Subscription durations (in days)
SUBSCRIPTION_DURATIONS = {
    "1 Day": 1,
    "1 Week": 7,
    "1 Month": 30,
    "6 Months": 180,
    "1 Year": 365
}

# Message intervals (in minutes)
MESSAGE_INTERVALS = {
    "10min": 10,
    "30min": 30,
    "1hr": 60,
    "6hrs": 360
}

# Default ad footer
AD_FOOTER = """
Powered by Butter Ads Bot Service
Owner: @pyth0nsyntax
Want to advertise? Contact admin!
"""

# Maximum photos per ad
MAX_PHOTOS = 3

# Banner image path
BANNER_PATH = "attached_assets/IMG_20250517_192232_891.jpg"
