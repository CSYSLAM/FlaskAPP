import os
from pathlib import Path


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(32).hex())
    DATA_DIR = Path("data")
    SQLALCHEMY_DATABASE_URI = 'sqlite:///game1.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False