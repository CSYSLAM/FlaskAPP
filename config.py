from pathlib import Path

class Config:
    SECRET_KEY = 'your_secret_key_here'
    SAVE_DIR = Path("player_data")
    DATA_DIR = Path("data")
    
    # Ensure directories exist
    SAVE_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)