import os
import json
import uuid
import base64
import logging
import requests
import socket
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, session, redirect, url_for, flash, g, jsonify, make_response, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from pathlib import Path

# Load .env trước khi import config để đảm bảo biến môi trường được nạp
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

from config import SECRET_KEY, FLASK_DEBUG, FIREBASE_URL, GEMINI_API_KEY
from utils import db_get, db_put, db_patch


logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.debug = FLASK_DEBUG
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

from routes.auth import auth_bp
from routes.user import customer_bp
from routes.admin import admin_bp
from routes.api import api_bp
from routes.ai import ai_bp

app.register_blueprint(auth_bp)
app.register_blueprint(customer_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp, url_prefix="/api/v1")
app.register_blueprint(ai_bp, url_prefix="/api/v1/ai")

# PWA: Serve manifest.json from static folder

@app.route("/")
def index():
    """Trang chủ mặc định - chuyển hướng đến login"""
    return redirect(url_for("auth.login"))



def get_user_from_db(username):
    data = db_get("users") or {}
    if isinstance(data, dict):
        return data.get(username)
    if isinstance(data, list):
        for u in data:
            if isinstance(u, dict) and u.get("username") == username:
                return u
    return None


@app.before_request
def security_check():
    g.user_avatar = None
    g.user_info = None

    if request.endpoint in [
        "static",
        "auth.login",
        "auth.logout",
        "auth.register",
        "auth.send_otp",
        "auth.check_session_status",
    ] or request.path.startswith("/api/v1/auth"):
        return

    if "user" in session:
        username = session["user"]
        # Admin không lưu trong DB → dùng thông tin mặc định để template không lỗi
        if username == "admin":
            g.user_avatar = ""
            g.user_info = {"username": "admin", "name": "Admin", "avatar": "", "role": "admin"}
            return

        user_in_db = get_user_from_db(username)

        if user_in_db:
            g.user_avatar = user_in_db.get("avatar", "")
            g.user_info = user_in_db

            if session.get("role") == "customer":
                token_session = session.get("login_token")
                token_db = user_in_db.get("login_token")
                if token_db and token_db != token_session:
                    logger.warning("Session token mismatch for user %s", username)
                    session.clear()
                    flash("Tài khoản đã đăng nhập nơi khác!", "danger")
                    return redirect(url_for("auth.login"))


@app.context_processor
def inject_global_vars():
    total_cart = 0
    unread_notif = 0

    if "user" in session:
        user = session["user"]

        raw_cart = db_get(f"carts/{user}") or {}
        cart_items = raw_cart if isinstance(raw_cart, list) else raw_cart.values()

        if cart_items:
            for item in cart_items:
                if isinstance(item, dict):
                    total_cart += int(item.get("qty", 0))

        raw_notifs = db_get(f"notifications/{user}") or []
        notif_items = list(raw_notifs.values()) if isinstance(raw_notifs, dict) else raw_notifs

        if notif_items:
            for n in notif_items:
                if isinstance(n, dict) and not n.get("is_read"):
                    unread_notif += 1

    return dict(total_cart_items=total_cart, unread_notif_count=unread_notif)


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api"):
        return jsonify({"error": "API endpoint not found", "status": 404}), 404
    try:
        return render_template("404.html"), 404
    except Exception:
        return "404 - Trang không tồn tại", 404


@app.errorhandler(500)
def server_error(e):
    logger.exception("Unhandled server error: %s", e)
    if request.path.startswith("/api"):
        return jsonify({"error": "Internal server error", "status": 500}), 500
    try:
        return render_template("500.html"), 500
    except Exception:
        return "500 - Lỗi hệ thống. Vui lòng thử lại sau.", 500


if __name__ == "__main__":
    # Get local IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        local_ip = "127.0.0.1"
    
    print("\n" + "="*50)
    print("FONG FOOD APP STARTED!")
    print("="*50)
    print(f"Local:    http://127.0.0.1:5005")
    print(f"Network:  http://{local_ip}:5005")
    print(f"Admin:    http://{local_ip}:5005/admin")
    print("="*50 + "\n")
    app.run(debug=False, host="0.0.0.0", port=5005)
