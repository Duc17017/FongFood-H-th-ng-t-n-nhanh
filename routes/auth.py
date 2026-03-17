import logging
import random
import uuid

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from config import FLASK_DEBUG

from services.auth_service import (
    normalize_users,
    find_user,
    validate_register_data,
    hash_password,
    verify_password,
)
from utils import db_get, db_put, db_patch


auth_bp = Blueprint("auth", __name__)
otp_storage = {}
logger = logging.getLogger(__name__)



# --- 0. MÀN HÌNH MỞ ĐẦU (SPLASH SCREEN) ---
@auth_bp.route("/fongfood")  # <-- Đổi cái này thành /fongfood
def splash():
    return render_template("splash.html")

# --- 1. ĐĂNG NHẬP ---
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password") 
        # 1. Check Admin mặc định (tài khoản kỹ thuật)
        if u == "admin" and p == "admin123":
            session["user"] = u
            session["role"] = "admin"
            session["name"] = "Admin"
            logger.info("Admin %s logged in (hard-coded)", u)
            return redirect("/admin/dashboard")

        # 2. Check User từ DB (dùng phone / username)
        user_data = find_user(u)

        if user_data and verify_password(user_data.get("password"), p):
            new_token = str(uuid.uuid4())
            try:
                db_patch(f"users/{u}", {"login_token": new_token})
            except Exception as exc:
                logger.warning("Không thể lưu login_token cho user %s: %s", u, exc)

            # Lấy role từ DB, mặc định là customer
            role = user_data.get("role", "customer")

            session["user"] = u
            session["name"] = user_data.get("name") or u
            session["role"] = role
            session["login_token"] = new_token
            logger.info("User %s logged in with role %s", u, role)

            # Điều hướng theo role
            if role == "admin":
                return redirect("/admin/dashboard")
            return redirect("/home")

        logger.warning("Đăng nhập thất bại cho user %s", u)
        flash("Sai tài khoản hoặc mật khẩu!", "danger")
    return render_template("auth/login.html")

# --- 2. ĐĂNG KÝ ---
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        phone = request.form.get("phone")
        email = request.form.get("email")
        name = request.form.get("name")
        password = request.form.get("password")
        otp_input = request.form.get("otp_phone")

        error = validate_register_data(phone, email, password)
        if error:
            flash(error, "error")
            return render_template("auth/register.html")

        if otp_storage.get(phone) != otp_input:
            flash("Mã OTP không đúng!", "error")
            return render_template("auth/register.html")

        raw_users = db_get("users") or {}
        users = normalize_users(raw_users)

        if phone in users:
            flash("Số điện thoại đã tồn tại!", "error")
            return render_template("auth/register.html")

        new_user = {
            "username": phone,
            "password": hash_password(password),
            "name": name,
            "email": email,
            "role": "customer",
            "avatar": "",
            "login_token": "",
        }

        try:
            if isinstance(raw_users, list):
                raw_users.append(new_user)
                db_put("users", raw_users)
            else:
                db_put(f"users/{phone}", new_user)
        except Exception as exc:
            logger.exception("Lỗi lưu user khi đăng ký: %s", exc)
            flash("Lỗi kết nối. Vui lòng kiểm tra mạng hoặc thử lại sau.", "error")
            return render_template("auth/register.html")

        logger.info("User %s registered successfully", phone)
        flash("Đăng ký thành công! Mời bạn đăng nhập.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")

# --- 3. API OTP ---
@auth_bp.route("/api/send-otp", methods=["POST"])
def send_otp():
    try:
        data = request.get_json(silent=True) or {}
        target = (data.get("target") or "").strip()
        if not target:
            return jsonify({"success": False, "message": "Thieu so dien thoai hoac email"}), 400
        
        otp_code = str(random.randint(100000, 999999))
        otp_storage[target] = otp_code
        
        # Log OTP
        logger.info(f"=== OTP CODE === Phone: {target} | Code: {otp_code} ====================")
        
        # Luôn trả về OTP để hiển thị trực tiếp cho user
        # Chỉ trả về trong message khi là debug mode
        debug_msg = ""
        if FLASK_DEBUG:
            debug_msg = f" [DEBUG: OTP is {otp_code}]"
        
        return jsonify({
            "success": True, 
            "message": f"Da gui ma OTP!{debug_msg}",
            "otp_code": otp_code  # Luôn trả về OTP để hiển thị
        })
    except Exception as e:
        logger.exception("Loi gui OTP: %s", e)
        return jsonify({"success": False, "message": "Loi server"}), 500

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))

# --- 5. QUÊN MẬT KHẨU ---
@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        try:
            target = request.form.get("target")
            otp_input = request.form.get("otp")
            new_password = request.form.get("password")
            confirm_password = request.form.get("confirm_password")

            if otp_storage.get(target) != otp_input:
                flash("Mã OTP không chính xác!", "error")
                return render_template("auth/forgot.html")

            if new_password != confirm_password:
                flash("Mật khẩu xác nhận không khớp!", "error")
                return render_template("auth/forgot.html")

            raw_users = db_get("users") or {}
            users = normalize_users(raw_users)

            found_key = None
            for key, u in users.items():
                if str(u.get("username")) == target or str(u.get("email")) == target:
                    found_key = key
                    break

            if found_key:
                db_patch(
                    f"users/{found_key}",
                    {"password": hash_password(new_password)},
                )
                if target in otp_storage: del otp_storage[target]
                logger.info("User %s reset password successfully", found_key)
                flash("Đổi mật khẩu thành công! Vui lòng đăng nhập.", "success")
                return redirect(url_for("auth.login"))
            else:
                flash("Tài khoản không tồn tại!", "error")
        except Exception as e:
            logger.exception("Lỗi Forgot: %s", e)
            flash("Có lỗi xảy ra, vui lòng thử lại.", "error")
            
    return render_template("auth/forgot.html")

# --- 6. AUTO KICK ---
@auth_bp.route("/check-session-status")
def check_session_status():
    if "user" not in session or "login_token" not in session:
        return jsonify({"status": "ok"})

    username = session["user"]
    current_token = session["login_token"]

    raw_users = db_get("users") or {}
    users = normalize_users(raw_users)
    user_in_db = users.get(username)

    if user_in_db:
        db_token = user_in_db.get("login_token")
        if db_token != current_token:
            session.clear()
            return jsonify({"status": "kick"})

    return jsonify({"status": "ok"})
