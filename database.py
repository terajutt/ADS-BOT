
from sqlalchemy import inspect, text


import logging
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from config import DATABASE_URL

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create SQLAlchemy engine and session
try:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
    SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
    Base = declarative_base()
    
    logger.info("Database connection established successfully")
except Exception as e:
    logger.error(f"Database connection error: {str(e)}")
    raise

def get_session():
    """
    Get database session
    """
    session = SessionLocal()
    try:
        return session
    finally:
        session.close()

def init_db():
    """
    Initialize database tables if they don't exist
    """
    try:
        # Only create tables if they don't exist
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {str(e)}")
        raise
