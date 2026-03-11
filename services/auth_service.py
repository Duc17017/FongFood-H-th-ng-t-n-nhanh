import re
import logging
from typing import Any, Dict

from werkzeug.security import generate_password_hash, check_password_hash

from utils import db_get


logger = logging.getLogger(__name__)


def normalize_users(data: Any) -> Dict[str, Dict[str, Any]]:
    """Chuẩn hóa dữ liệu users (hỗ trợ cả dict và list)."""
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {
            u.get("username"): u
            for u in data
            if isinstance(u, dict) and "username" in u
        }
    return {}


def find_user(username: str) -> Dict[str, Any] | None:
    """Tìm user an toàn trong DB (kể cả khi dữ liệu đang lưu là List).
    Tìm theo: username, phone, hoặc email.
    """
    data = db_get("users") or {}
    if isinstance(data, dict):
        # Tìm theo key (username/phone)
        if username in data:
            return data[username]
        # Tìm theo email
        for key, u in data.items():
            if isinstance(u, dict) and str(u.get("email")).lower() == username.lower():
                return u
    if isinstance(data, list):
        for u in data:
            if isinstance(u, dict):
                if u.get("username") == username or str(u.get("email")).lower() == username.lower():
                    return u
    return None


def validate_register_data(phone: str, email: str, password: str) -> str | None:
    if not re.match(r"^\d{10}$", phone or ""):
        return "Số điện thoại phải có đúng 10 chữ số."
    if not re.match(r"^[a-zA-Z0-9._%+-]+@gmail\.com$", email or ""):
        return "Email phải có đuôi @gmail.com."
    if not password or len(password) < 8:
        return "Mật khẩu phải có ít nhất 8 ký tự."
    return None


def hash_password(password: str) -> str:
    """Sinh password hash an toàn để lưu DB."""
    return generate_password_hash(password)


def verify_password(stored_password: str, provided_password: str) -> bool:
    if not stored_password:
        return False
    
    # Nếu là hash (werkzeug) thì dùng check_password_hash
    if stored_password.startswith("pbkdf2:") or stored_password.startswith("scrypt:"):
        try:
            return check_password_hash(stored_password, provided_password)
        except Exception as exc:
            logger.warning("Lỗi verify password hash: %s", exc)
            return False
    
    # Fallback: dữ liệu cũ lưu plain text
    return stored_password == provided_password

