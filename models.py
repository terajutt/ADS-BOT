import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from database import Base

class SubscriptionLevel(enum.Enum):
    BRONZE = "Bronze"
    SILVER = "Silver"
    GOLD = "Gold"

class MessageInterval(enum.Enum):
    TEN_MIN = "10min"
    THIRTY_MIN = "30min"
    ONE_HOUR = "1hr"
    SIX_HOURS = "6hrs"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    chat_id = Column(String, unique=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)
    subscription_level = Column(Enum(SubscriptionLevel), nullable=True)
    subscription_expiry = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bots = relationship("Bot", back_populates="user", cascade="all, delete-orphan")

class Bot(Base):
    __tablename__ = "bots"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String, unique=True, nullable=False)
    bot_username = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="bots")
    groups = relationship("Group", back_populates="bot", cascade="all, delete-orphan")
    ad_message = relationship("AdMessage", uselist=False, back_populates="bot", cascade="all, delete-orphan")

class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(String, nullable=False)
    group_title = Column(String, nullable=True)
    interval = Column(Enum(MessageInterval), default=MessageInterval.ONE_HOUR)
    active = Column(Boolean, default=True)
    media_allowed = Column(Boolean, default=True)
    last_ad_sent = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bot = relationship("Bot", back_populates="groups")

    __table_args__ = (
        UniqueConstraint('bot_id', 'group_id', name='uix_bot_group'),
    )

class AdMessage(Base):
    __tablename__ = "ad_messages"

    id = Column(Integer, primary_key=True)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, unique=True)
    text = Column(Text, nullable=True)
    photo_ids = Column(ARRAY(String), nullable=True)
    caption = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bot = relationship("Bot", back_populates="ad_message")