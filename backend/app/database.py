import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Load environment variables from .env file
load_dotenv()

# Read the database URL from the environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

# Create SQLAlchemy engine and session factory. The pool is per API process (SQLAlchemy's 5 + 10 by default);
# DB_POOL_SIZE and DB_MAX_OVERFLOW tune it from load-test results. SQLite in tests has no pool to size.
pool = {}
if not DATABASE_URL.startswith("sqlite"):
    pool = {"pool_size": int(os.getenv("DB_POOL_SIZE", "5")), "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10"))}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, **pool)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for declarative models
Base = declarative_base()


# FastAPI dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
