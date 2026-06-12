from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class ConcurrentModificationError(Exception):
    pass