# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

# Create synchronous engine (works better with Supabase pgbouncer)
engine = create_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    connect_args={"sslmode": "require"},
    execution_options={"compiled_cache": None} 
)


# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()