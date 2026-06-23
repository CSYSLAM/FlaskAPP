import os
import sys
from pathlib import Path


def get_base_path():
    """获取基础路径，支持PyInstaller打包"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent


def get_instance_path():
    """获取instance路径"""
    base = get_base_path()
    instance_path = base / "instance"
    # 确保instance目录存在
    if not instance_path.exists():
        instance_path.mkdir(parents=True, exist_ok=True)
    return instance_path


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(32).hex())
    DATA_DIR = get_base_path() / "data"
    # 数据库放在instance目录下
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{get_instance_path() / "game1.db"}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TEMPLATES_AUTO_RELOAD = True