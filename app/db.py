import time
from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy.exc import OperationalError
from .config import settings

# REMOVE: engine = create_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
# Define it here for use in get_session later, but creation is moved to the function
engine = None 

def create_db_and_tables(max_tries: int = 15, delay: int = 1):
    global engine
    print("Attempting to connect to database and create tables...")
    
    for attempt in range(max_tries):
        try:
            # 1. CREATE ENGINE INSIDE THE LOOP
            # Force the creation of a new engine on each attempt
            engine = create_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
            
            # 2. Try to create tables
            SQLModel.metadata.create_all(engine)
            print("Database connection successful and tables created!")
            return  # Success, exit the function

        except OperationalError as e:
            error_message = str(e)
            # The retry logic remains the same
            if "password authentication failed" in error_message or "connection refused" in error_message or "could not translate host name" in error_message:
                print(f"Database not ready (Attempt {attempt + 1}/{max_tries}). Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print(f"Non-retryable operational error encountered: {e}")
                raise

        except Exception as e:
            print(f"An unexpected error occurred during database setup: {e}")
            raise

    print(f"FATAL: Failed to connect to database after {max_tries} attempts.")
    raise ConnectionError("Could not connect to the database. Check credentials and container health.")

def get_session():
    """依賴注入函式，用於獲取資料庫會話 (Session)。"""
    # Use the global engine, which is guaranteed to be set if create_db_and_tables succeeds
    with Session(engine) as session:
        yield session