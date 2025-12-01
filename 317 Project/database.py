# # database.py

# import os
# from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionmaker, declarative_base

# # Load env vars (with safe local defaults)
# DB_USER = os.getenv("DB_USER", "root")
# DB_PASS = os.getenv("DB_PASS", "password")
# DB_HOST = os.getenv("DB_HOST", "localhost")
# DB_PORT = os.getenv("DB_PORT", "3333")
# DB_NAME = os.getenv("DB_NAME", "movies_db")

# # Build SQLAlchemy URL
# SQLALCHEMY_DATABASE_URL = (
#     f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
# )

# engine = create_engine(
#     SQLALCHEMY_DATABASE_URL,
#     pool_pre_ping=True
# )

# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base = declarative_base()


# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()

# import os
# from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionmaker, declarative_base

# # Prefer DATABASE_URL or MYSQL_URL provided by Railway
# DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("MYSQL_URL")

# if not DATABASE_URL:
#     raise RuntimeError("DATABASE_URL or MYSQL_URL is not set.")

# # SQLAlchemy needs mysql+pymysql instead of mysql://
# if DATABASE_URL.startswith("mysql://"):
#     DATABASE_URL = DATABASE_URL.replace("mysql://", "mysql+pymysql://", 1)

# engine = create_engine(
#     DATABASE_URL,
#     pool_pre_ping=True
# )

# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base = declarative_base()


# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()
# database.py

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 1. Try Railway-style full URL first
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("MYSQL_URL")

if DATABASE_URL:
    # SQLAlchemy requires mysql+pymysql://
    if DATABASE_URL.startswith("mysql://"):
        DATABASE_URL = DATABASE_URL.replace("mysql://", "mysql+pymysql://", 1)
else:
    # 2. Local development fallback
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASS = os.getenv("DB_PASS", "password")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "3333")
    DB_NAME = os.getenv("DB_NAME", "movies_db")

    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
