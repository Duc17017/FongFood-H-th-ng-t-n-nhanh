import time
import logging

import requests
import json

from config import FIREBASE_URL

logger = logging.getLogger(__name__)
# 1. TẠO SESSION (Giữ kết nối sống để không phải bắt tay SSL lại)
session = requests.Session()

# 2. TẠO CACHE ĐƠN GIẢN (Lưu dữ liệu vào RAM trong 60 giây)
_cache: dict[str, dict] = {}


def db_get(path: str, use_cache: bool = False):
    """
    Lấy dữ liệu từ Firebase.
    use_cache=True: Nếu dữ liệu mới tải trong vòng 60s thì lấy từ RAM luôn, không hỏi Firebase.
    """
    global _cache
    current_time = time.time()

    if use_cache and path in _cache:
        if current_time - _cache[path]["time"] < 60:
            return _cache[path]["data"]

    try:
        r = session.get(f"{FIREBASE_URL}{path}.json")
        data = r.json() if r.status_code == 200 and r.text != "null" else {}

        if use_cache:
            _cache[path] = {"data": data, "time": current_time}

        return data
    except Exception:
        return {}


def db_put(path: str, data):
    try:
        r = session.put(f"{FIREBASE_URL}{path}.json", json=data)
        if r.status_code >= 400:
            logger.warning("Firebase db_put %s status %s", path, r.status_code)
            raise RuntimeError(f"Firebase put failed: {r.status_code}")
    except Exception as e:
        logger.exception("Firebase db_put %s: %s", path, e)
        raise


def db_patch(path: str, data):
    try:
        r = session.patch(f"{FIREBASE_URL}{path}.json", json=data)
        if r.status_code >= 400:
            logger.warning("Firebase db_patch %s status %s", path, r.status_code)
            raise RuntimeError(f"Firebase patch failed: {r.status_code}")
    except Exception as e:
        logger.exception("Firebase db_patch %s: %s", path, e)
        raise

def get_db_connection():
    return pymysql.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 3306)),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'fongfood'),
        cursorclass=pymysql.cursors.DictCursor
    )