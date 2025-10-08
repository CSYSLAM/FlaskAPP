import json
import time
from pathlib import Path
from typing import List, Dict, Any


_STORE = Path("data/public_chat.json")
_MAX_LEN = 100


def _load() -> List[Dict[str, Any]]:
    if not _STORE.exists():
        return []
    try:
        with open(_STORE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _save(messages: List[Dict[str, Any]]):
    messages = messages[-_MAX_LEN:]
    with open(_STORE, 'w', encoding='utf-8') as f:
        json.dump(messages, f, ensure_ascii=False)


def list_latest(limit: int = 10) -> List[Dict[str, Any]]:
    return _load()[-limit:]


def broadcast_system(content: str):
    msgs = _load()
    msgs.append({
        "type": "system",
        "content": content,
        "time": time.strftime('%Y-%m-%d %H:%M:%S')
    })
    _save(msgs)


def broadcast_player(username: str, player_name: str, content: str):
    msgs = _load()
    msgs.append({
        "type": "player",
        "username": username,
        "player_name": player_name,
        "content": content,
        "time": time.strftime('%Y-%m-%d %H:%M:%S')
    })
    _save(msgs)


