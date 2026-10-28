from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from content_radar.config.settings import settings

engine = create_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
