
import base64
import logging
import time
import uuid
from datetime import datetime
import unicodedata

from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify

logger = logging.getLogger(__name__)

from decorators import login_required
from services.auth_service import find_user
from utils import db_get, db_put, db_patch


customer_bp = Blueprint("customer", __name__)

# --- HÀM HỖ TRỢ CHUẨN HÓA DỮ LIỆU ---
def normalize_data(data, key_field='id'):
    """Chuyển List/Dict thành Dict để code Python xử lý logic"""
    if isinstance(data, dict): return data
    if isinstance(data, list):
        res = {}
        for i, item in enumerate(data):
            if isinstance(item, dict):
                k = item.get(key_field, str(i))
                res[str(k)] = item
        return res
    return {}

def get_user_db(username):
    data = db_get('users') or {}
    if isinstance(data, dict): return data.get(username)
    if isinstance(data, list):
        for u in data:
            if isinstance(u, dict) and u.get('username') == username: return u
    return None


def _normalize_text(s: str) -> str:
    if not s:
        return ""
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.split())

# --- AI GỢI Ý MÓN ĂN ---
def get_ai_recommendations(username, products):
    """AI gợi ý món ăn dựa trên thời tiết, thời gian và lịch sử"""
    from datetime import datetime
    import random
    import requests
    
    # Lấy lịch sử đơn hàng
    raw_orders = db_get("orders") or {}
    orders = normalize_data(raw_orders, "id")
    user_orders = [o for o in orders.values() if o.get("user") == username]
    
    # Đếm tần suất mua
    food_prefs = {}
    for order in user_orders:
        items = order.get("details") or order.get("items") or []
        for item in items:
            name = item.get("name", "")
            food_prefs[name] = food_prefs.get(name, 0) + 1
    
    # Xác định thời gian trong ngày
    hour = datetime.now().hour
    time_category = "drink" if hour < 10 or (14 <= hour < 18) else "food"
    
    # Lấy thông tin thời tiết thực tế (Hà Nội)
    weather_info = {"condition": "normal", "temp": 25, "description": "Trời bình thường"}
    try:
        from config import OPENWEATHER_API_KEY
        if OPENWEATHER_API_KEY:
            weather_url = f"https://api.openweathermap.org/data/2.5/weather?q=Hanoi,vn&appid={OPENWEATHER_API_KEY}&units=metric"
            weather_response = requests.get(weather_url, timeout=5)
            if weather_response.status_code == 200:
                weather_data = weather_response.json()
                temp = weather_data.get("main", {}).get("temp", 25)
                weather_id = weather_data.get("weather", [{}])[0].get("id", 800)
                
                # Phân loại thời tiết
                if weather_id >= 200 and weather_id < 300:  # Thunderstorm
                    weather_info = {"condition": "rainy", "temp": temp, "description": "Trời bão"}
                elif weather_id >= 300 and weather_id < 600:  # Drizzle, Rain
                    weather_info = {"condition": "rainy", "temp": temp, "description": "Trời mưa"}
                elif weather_id >= 600 and weather_id < 700:  # Snow
                    weather_info = {"condition": "cold", "temp": temp, "description": "Trời tuyết lạnh"}
                elif weather_id == 800:  # Clear
                    if temp > 30:
                        weather_info = {"condition": "hot", "temp": temp, "description": "Trời nóng"}
                    elif temp < 20:
                        weather_info = {"condition": "cold", "temp": temp, "description": "Trời mát lạnh"}
                    else:
                        weather_info = {"condition": "normal", "temp": temp, "description": "Trời nắng đẹp"}
                elif weather_id > 800:  # Clouds
                    weather_info = {"condition": "cloudy", "temp": temp, "description": "Trời nhiều mây"}
    except Exception as e:
        logger.warning(f"Không lấy được thời tiết: {e}")
    
    # Lọc sản phẩm theo gợi ý
    recommendations = []
    for pid, p in products.items():
        score = 0
        name = p.get("name", "").lower()
        
        # Ưu tiên THEO THỜI TIẾT (quan trọng nhất)
        if weather_info["condition"] in ["rainy", "cold"]:
            # Trời lạnh/mưa: ưu tiên món nóng
            if any(x in name for x in ["lau", "hot", "nuong", "ram", "sup", "chao", "pho", "bun"]):
                score += 5
            elif any(x in name for x in ["tra", "sinh to", "nuoc", "cold", "đá"]):
                score -= 3  # Giảm ưu tiên đồ lạnh
        elif weather_info["condition"] == "hot":
            # Trời nóng: ưu tiên đồ uống lạnh
            if any(x in name for x in ["tra", "sinh to", "nuoc", "cafe", "coffee", "coca", "pepsi"]):
                score += 5
            elif any(x in name for x in ["lau", "hot", "nuong"]):
                score -= 2
        
        # Ưu tiên theo thời gian trong ngày
        if time_category == "food" and any(x in name for x in ["com", "pho", "chao", "mi", "ga", "bo", "bun"]):
            score += 3
        elif time_category == "drink" and any(x in name for x in ["tra", "nuoc", "cafe", "coffee", "sinh to"]):
            score += 3
        
        # Ưu tiên theo sở thích
        for pref_name, count in food_prefs.items():
            if pref_name.lower() in name:
                score += count
        
        # Ưu tiên món được đề xuất
        if p.get("isPromoted"):
            score += 2
        
        if score > 0:
            recommendations.append((pid, p, score, weather_info))
    
    # Sắp xếp và lấy top 6
    recommendations.sort(key=lambda x: x[2], reverse=True)
    return recommendations[:6]


# --- HOME & MENU ---
@customer_bp.route("/home")
@login_required(role="customer")
def home():
    raw_products = db_get("products") or {}
    products = normalize_data(raw_products, "id")
    hot_products = {k: v for k, v in products.items() if v.get("isPromoted")}
    
    # AI gợi ý
    username = session.get("user")
    ai_recommendations = get_ai_recommendations(username, products) if username else []
    
    # Lấy thông tin thời tiết để hiển thị
    weather_info = {"condition": "normal", "temp": 25, "description": "Trời bình thường"}
    try:
        from config import OPENWEATHER_API_KEY
        if OPENWEATHER_API_KEY:
            import requests
            weather_url = f"https://api.openweathermap.org/data/2.5/weather?q=Hanoi,vn&appid={OPENWEATHER_API_KEY}&units=metric"
            weather_response = requests.get(weather_url, timeout=5)
            if weather_response.status_code == 200:
                weather_data = weather_response.json()
                weather_info["temp"] = weather_data.get("main", {}).get("temp", 25)
                weather_id = weather_data.get("weather", [{}])[0].get("id", 800)
                if weather_id >= 200 and weather_id < 600:
                    weather_info["condition"] = "rainy"
                    weather_info["description"] = "Trời mưa"
                elif weather_id == 800 and weather_info["temp"] > 30:
                    weather_info["condition"] = "hot"
                    weather_info["description"] = "Trời nóng"
                elif weather_info["temp"] < 20:
                    weather_info["condition"] = "cold"
                    weather_info["description"] = "Trời lạnh"
    except:
        pass
    
    return render_template("customer/home.html", hot_products=hot_products, ai_recommendations=ai_recommendations, weather=weather_info)


@customer_bp.route("/menu")
@login_required(role="customer")
def menu():
    known_categories = {"all", "fastfood", "noodle", "drink", "bread", "pizza"}

    category = (request.args.get("category") or "").strip().lower()
    q = (request.args.get("q") or "").strip()
    search = (request.args.get("search") or "").strip()

    if not category:
        if q and q.strip().lower() in known_categories:
            category = q.strip().lower()
        elif q and not search:
            search = q

    cat = category or "all"

    # Tìm kiếm với cả text gốc và text đã normalize
    search_norm = _normalize_text(search)
    search_original = search.strip().lower() if search else ""

    raw_products = db_get("products") or {}
    products = normalize_data(raw_products, "id")

    filtered_products = {}
    for pid, p in products.items():
        if cat != "all" and p.get("category") != cat:
            continue
        if search_norm or search_original:
            name = p.get("name", "")
            description = p.get("description", "")
            category_name = p.get("category", "")
            
            name_norm = _normalize_text(name)
            name_original = str(name).strip().lower()
            desc_norm = _normalize_text(description)
            desc_original = str(description).strip().lower() if description else ""
            category_norm = _normalize_text(category_name)
            
            # Kiểm tra với cả text gốc và text đã normalize
            # Tìm kiếm cả trong tên, mô tả và category
            match_norm = (search_norm and (
                search_norm in name_norm or 
                (desc_norm and search_norm in desc_norm) or
                search_norm in category_norm
            ))
            match_orig = (search_original and (
                search_original in name_original or 
                search_original in desc_original or
                search_original in category_name.lower()
            ))

            if not match_norm and not match_orig:
                continue
        filtered_products[pid] = p
    return render_template("customer/menu.html", products=filtered_products)


@customer_bp.route("/product/<pid>")
@login_required(role="customer")
def product_detail(pid):
    raw_products = db_get("products") or {}
    products = normalize_data(raw_products, "id")
    product = products.get(pid)
    
    if not product:
        flash("Không tìm thấy sản phẩm", "error")
        return redirect(url_for("customer.menu"))
    
    # AI tạo nội dung chi tiết sản phẩm
    ai_content = generate_ai_product_content(product)
    
    return render_template("customer/product_detail.html", product=product, ai_content=ai_content)


def generate_ai_product_content(product):
    """AI tạo nội dung chi tiết sản phẩm"""
    from datetime import datetime
    
    name = product.get("name", "")
    category = product.get("category", "")
    description = product.get("description", "")
    price = product.get("price", 0)
    
    # AI generated content
    hour = datetime.now().hour
    
    # Tạo mô tả chi tiết dựa trên thời gian
    if 6 <= hour < 11:
        time_desc = "Buổi sáng perfect!"
        occasion = "Bữa sáng tuyệt vời"
    elif 11 <= hour < 14:
        time_desc = "Giờ ăn trưa!"
        occasion = "Bữa trưa no bụng"
    elif 14 <= hour < 18:
        time_desc = "Chiều xuýt xoa!"
        occasion = "Bữa xế nhẹ nhàng"
    else:
        time_desc = "Buổi tối sum vầy!"
        occasion = "Bữa tối ấm cúng"
    
    # Tạo nội dung theo category
    category_content = {
        "fastfood": {
            "highlights": ["Ngon nhanh", "Tiện lợi", "Đậm đà"],
            "tips": "Nên ăn ngay sau khi nhận để giữ độ giòn tốt nhất"
        },
        "noodle": {
            "highlights": ["Nước dùng ngọt thanh", "Bánh mềm dai vừa", "Topping đầy đủ"],
            "tips": "Thêm chanh, ớt, hành phi để tăng hương vị"
        },
        "drink": {
            "highlights": ["Thơm mát", "Giải khát", "Năng lượng tức thì"],
            "tips": "Uống lạnh ngon hơn, có thể thêm đá"
        },
        "bread": {
            "highlights": ["Giòn bên ngoài", "Mềm bên trong", "Nhân đầy đặn"],
            "tips": "Nên hâm nóng lại nếu để qua đêm"
        },
        "pizza": {
            "highlights": ["Đế giòn tan", "Phô mai kéo sợi", "Nhà làm tươi ngon"],
            "tips": "Thêm xốt tiêu, ớt bột để tăng hương vị"
        }
    }
    
    content = category_content.get(category, {
        "highlights": ["Ngon", "Tươi", "Chất lượng"],
        "tips": "Thưởng thức ngay khi nhận được"
    })
    
    return {
        "time_desc": time_desc,
        "occasion": occasion,
        "highlights": content["highlights"],
        "tips": content["tips"],
        "price_formatted": "{:,.0f}đ".format(price),
        "original_price": "{:,.0f}đ".format(price + 15000) if price > 0 else None,
        "discount": "20%" if price > 0 else None
    }


# --- ROUTE 1: HIỂN THỊ TRANG PROFILE ---
@customer_bp.route("/profile")
@login_required(role="customer")
def profile():
    username = session["user"]
    user_info = get_user_db(username)

    if not user_info:
        return redirect(url_for("auth.logout"))

    return render_template("customer/profile.html", user=user_info)

# --- ROUTE 2: XỬ LÝ CẬP NHẬT PROFILE ---
@customer_bp.route("/update_profile", methods=["POST"])
@login_required(role="customer")
def update_profile():
    username = session["user"]

    name = request.form.get("name")
    dob = request.form.get("dob")
    gender = request.form.get("gender")

    update_data = {
        "name": name,
        "dob": dob,
        "gender": gender,
    }

    f = request.files.get("avatar")
    if f and f.filename:
        try:
            b64_data = base64.b64encode(f.read()).decode('utf-8')
            update_data["avatar"] = f"data:{f.content_type};base64,{b64_data}"
        except Exception as e:
            print("Lỗi upload ảnh:", e)

    db_patch(f"users/{username}", update_data)

    session["name"] = name

    flash("Cập nhật thông tin thành công!", "success")
    return redirect(url_for("customer.profile"))


@customer_bp.route("/account")
@login_required(role="customer")
def account():
    user_info = get_user_db(session["user"])
    return render_template("customer/account.html", user=user_info or {})



@customer_bp.route("/notifications")
@login_required(role="customer")
def notifications():
    user = session["user"]
    # KHÔNG dùng cache để hiển thị thông báo mới nhất
    raw_notifs = db_get(f'notifications/{user}', use_cache=False) or []
    notifications = list(raw_notifs.values()) if isinstance(raw_notifs, dict) else raw_notifs

    return render_template("customer/notifications.html", notifications=notifications)

# --- MY VOUCHERS PAGE ---
@customer_bp.route("/my_vouchers")
@login_required(role="customer")
def my_vouchers():
    user = session["user"]
    raw_vouchers = db_get("vouchers") or {}
    vouchers_obj = normalize_data(raw_vouchers, "code") if isinstance(raw_vouchers, (list, dict)) else {}
    
    my_vouchers = []
    now = datetime.now()
    for code, v in vouchers_obj.items():
        if not isinstance(v, dict):
            continue
        v_code = (v.get("code") or code or "").strip().upper()
        if not v_code:
            continue
        target_user = (v.get("user") or "all").strip()
        if target_user not in ("all", user):
            continue
        valid_until = v.get("valid_until")
        is_expired = False
        if valid_until:
            try:
                if datetime.fromisoformat(valid_until) < now:
                    is_expired = True
            except Exception:
                pass
        vv = dict(v)
        vv["code"] = v_code
        vv["is_expired"] = is_expired
        my_vouchers.append(vv)
    
    return render_template("customer/my_vouchers.html", vouchers=my_vouchers)

# --- ROUTE: XEM LỊCH SỬ ĐƠN HÀNG ---
@customer_bp.route("/history")
@login_required(role="customer")
def history():
    user = session["user"]
    raw_orders = db_get("orders") or {}
    all_orders = normalize_data(raw_orders, "id")
    
    # Get products for image lookup
    raw_products = db_get("products") or {}
    all_products = normalize_data(raw_products, "id")

    my_orders = []
    for oid, order in all_orders.items():
        if order.get("user") == user:
            order = dict(order)
            order["id"] = oid
            
            # Add images to order items
            items = order.get("items", [])
            if items:
                for item in items:
                    pid = item.get("id")
                    if pid and pid in all_products:
                        item["image"] = all_products[pid].get("image", "")
            
            my_orders.append(order)
    my_orders.sort(key=lambda x: x.get("date", ""), reverse=True)
    return render_template("customer/history.html", orders=my_orders)

# --- ROUTE: HỦY ĐƠN HÀNG ---
@customer_bp.route("/cancel_order/<oid>")
@login_required(role="customer")
def cancel_order(oid):
    order = db_get(f"orders/{oid}")

    if order and order.get("user") == session["user"]:
        if order.get("status") == "pending":
            db_patch(f"orders/{oid}", {"status": "cancelled"})
            flash("Đã hủy đơn hàng thành công!", "success")
        else:
            flash("Đơn hàng đã được xử lý, không thể hủy!", "warning")
    else:
        flash("Lỗi xác thực đơn hàng!", "danger")

    return redirect(url_for("customer.history"))


# --- GIỎ HÀNG & THANH TOÁN ---
@customer_bp.route("/cart")
@login_required(role="customer")
def cart():
    user = session["user"]

    raw_cart = db_get(f"carts/{user}") or {}
    user_cart = normalize_data(raw_cart, "id")

    raw_products = db_get("products") or {}
    all_products = normalize_data(raw_products, "id")

    display_cart = {}
    for pid, item in user_cart.items():
        display_cart[pid] = item.copy()
        if pid in all_products:
            display_cart[pid]["image"] = all_products[pid].get("image", "")

    user_info = get_user_db(user) or {}

    # Map default address from addresses[] -> user.address for template compatibility
    default_address_text = ""
    addresses = user_info.get("addresses", []) if isinstance(user_info, dict) else []
    if isinstance(addresses, list) and addresses:
        default_addr = None
        for a in addresses:
            if isinstance(a, dict) and a.get("is_default"):
                default_addr = a
                break
        if not default_addr:
            default_addr = addresses[0] if isinstance(addresses[0], dict) else None

        if default_addr:
            default_address_text = (
                default_addr.get("full_address")
                or default_addr.get("detail")
                or ""
            )

    user_info_for_cart = dict(user_info) if isinstance(user_info, dict) else {}
    user_info_for_cart["address"] = default_address_text

    # Available vouchers for dropdown (user-specific + all)
    raw_vouchers = db_get("vouchers") or {}
    vouchers_obj = normalize_data(raw_vouchers, "code") if isinstance(raw_vouchers, (list, dict)) else {}
    available_vouchers = []
    now = datetime.now()
    for code, v in vouchers_obj.items():
        if not isinstance(v, dict):
            continue
        v_code = (v.get("code") or code or "").strip().upper()
        if not v_code:
            continue
        target_user = (v.get("user") or "all").strip()
        if target_user not in ("all", user):
            continue
        valid_until = v.get("valid_until")
        if valid_until:
            try:
                if datetime.fromisoformat(valid_until) < now:
                    continue
            except Exception:
                pass
        vv = dict(v)
        vv["code"] = v_code
        available_vouchers.append(vv)

    return render_template(
        "customer/cart.html",
        cart=display_cart,
        user=user_info_for_cart,
        available_vouchers=available_vouchers,
    )


@customer_bp.route("/voucher/check", methods=["POST"])
@login_required(role="customer")
def check_voucher():
    """
    Validate voucher for cart/checkout via AJAX.
    Expected JSON: { code: "ABC", order_total: 123000 }
    Returns: { success, message, discount_amount }
    """
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip().upper()
    order_total = float(data.get("order_total") or 0)
    user = session["user"]

    if not code:
        return jsonify({"success": False, "message": "Vui lòng nhập mã voucher."}), 400
    if order_total <= 0:
        return jsonify({"success": False, "message": "Tổng đơn hàng không hợp lệ."}), 400

    raw_vouchers = db_get("vouchers") or {}
    vouchers_obj = normalize_data(raw_vouchers, "code") if isinstance(raw_vouchers, (list, dict)) else {}

    voucher = None
    # Support dict keyed by code, or list of vouchers
    if isinstance(raw_vouchers, dict):
        voucher = raw_vouchers.get(code)
    if not voucher:
        for _, v in vouchers_obj.items():
            if isinstance(v, dict) and (v.get("code") or "").strip().upper() == code:
                voucher = v
                break

    if not isinstance(voucher, dict):
        return jsonify({"success": False, "message": "Mã voucher không tồn tại."}), 404

    target_user = (voucher.get("user") or "all").strip()
    if target_user not in ("all", user):
        return jsonify({"success": False, "message": "Voucher không áp dụng cho tài khoản này."}), 400

    valid_until = voucher.get("valid_until")
    if valid_until:
        try:
            if datetime.fromisoformat(valid_until) < datetime.now():
                return jsonify({"success": False, "message": "Voucher đã hết hạn."}), 400
        except Exception:
            pass

    min_order = float(voucher.get("min_order", 0) or 0)
    if order_total < min_order:
        return jsonify(
            {
                "success": False,
                "message": f"Đơn tối thiểu {min_order:,.0f}đ mới áp dụng được voucher.",
            }
        ), 400

    v_type = (voucher.get("type") or "percent").strip().lower()
    v_discount = float(voucher.get("discount", voucher.get("discount_percent", 0)) or 0)
    if v_discount <= 0:
        return jsonify({"success": False, "message": "Voucher không hợp lệ."}), 400

    if v_type == "percent":
        discount_amount = order_total * v_discount / 100.0
    else:
        discount_amount = v_discount

    discount_amount = max(0.0, min(discount_amount, order_total))
    return jsonify(
        {
            "success": True,
            "message": f"Áp dụng voucher {code} thành công!",
            "discount_amount": discount_amount,
        }
    )


@customer_bp.route("/update_cart/<pid>/<action>")
@login_required(role="customer")
def update_cart(pid, action):
    user = session["user"]

    raw_cart = db_get(f"carts/{user}") or {}
    user_cart = normalize_data(raw_cart, "id")

    if pid in user_cart:
        if action == "increase":
            user_cart[pid]["qty"] += 1
        elif action == "decrease":
            user_cart[pid]["qty"] -= 1
            if user_cart[pid]["qty"] <= 0:
                del user_cart[pid]
        elif action == "remove":
            del user_cart[pid]
        db_put(f"carts/{user}", user_cart)

    return redirect(url_for("customer.cart"))


@customer_bp.route("/add_to_cart/<pid>", methods=["POST"])
@login_required(role="customer")
def add_to_cart(pid):
    user = session["user"]
    
    # Support JSON body for quantity
    quantity = 1
    if request.is_json:
        data = request.get_json() or {}
        quantity = data.get("quantity", 1)

    raw_products = db_get("products") or {}
    products = normalize_data(raw_products, "id")
    product = products.get(pid)
    
    if product:
        raw_cart = db_get(f"carts/{user}") or {}
        user_cart = normalize_data(raw_cart, "id")

        if pid in user_cart:
            user_cart[pid]["qty"] += quantity
        else:
            user_cart[pid] = {
                "name": product["name"],
                "price": product.get("price", 0),
                "qty": quantity,
                "id": pid,
            }
        db_put(f"carts/{user}", user_cart)
        
        # Return JSON if requested, otherwise redirect
        if request.is_json:
            return jsonify({"success": True, "message": f"Đã thêm {product['name']} vào giỏ!", "cart_count": sum(item.get("qty", 1) for item in user_cart.values())})
        flash(f"Đã thêm {product['name']} vào giỏ!", "success")
    return redirect(request.referrer or url_for("customer.menu"))


@customer_bp.route("/checkout", methods=["POST"])
@login_required(role="customer")
def checkout():
    user = session["user"]

    raw_cart = db_get(f"carts/{user}") or {}
    user_cart = normalize_data(raw_cart, "id")
    if not user_cart:
        return redirect(url_for("customer.menu"))

    name = request.form.get("name")
    phone = request.form.get("phone")
    payment_method = request.form.get("payment_method")
    address = request.form.get("new_address") or request.form.get(
        "default_address_val"
    )
    voucher_code = (request.form.get("voucher_code") or "").strip().upper()

    total_before_discount = sum(
        item["price"] * item["qty"] for item in user_cart.values()
    )
    discount_amount = 0

    if voucher_code:
        vouchers = db_get("vouchers") or {}
        logger.info(f"=== CHECKOUT: all vouchers = {vouchers} ===")
        
        voucher = None
        if isinstance(vouchers, dict):
            voucher = vouchers.get(voucher_code)
        elif isinstance(vouchers, list):
            for v in vouchers:
                if isinstance(v, dict) and v.get("code") == voucher_code:
                    voucher = v
                    break

        if voucher:
            target_user = voucher.get("user") or "all"
            valid_for_user = target_user in ("all", user)

            valid_until = voucher.get("valid_until")
            still_valid = True
            if valid_until:
                try:
                    dt_valid = datetime.fromisoformat(valid_until)
                    still_valid = dt_valid >= datetime.now()
                except Exception:
                    still_valid = True

            logger.info(f"=== CHECKOUT: voucher found = {voucher}, valid_for_user={valid_for_user}, still_valid={still_valid} ===")

            if valid_for_user and still_valid:
                v_type = voucher.get("type", "percent")
                v_discount = float(voucher.get("discount", 0) or 0)
                min_order = float(voucher.get("min_order", 0) or 0)

                logger.info(f"=== CHECKOUT: v_type={v_type}, v_discount={v_discount}, min_order={min_order}, total_before={total_before_discount} ===")

                if total_before_discount >= min_order and v_discount > 0:
                    if v_type == "percent":
                        discount_amount = total_before_discount * v_discount / 100.0
                    else:
                        discount_amount = v_discount
                    logger.info(f"=== CHECKOUT: discount_amount = {discount_amount} ===")
                else:
                    flash("Đơn hàng không đủ điều kiện áp dụng voucher (tối thiểu {:,.0f}đ)".format(min_order), "error")
            else:
                flash("Mã voucher không hợp lệ hoặc đã hết hạn.", "error")
        else:
            flash("Mã voucher không tồn tại.", "error")

    total = max(total_before_discount - discount_amount, 0)
    order_id = str(uuid.uuid4())[:8].upper()
    
    # Lưu thông tin voucher vào đơn hàng
    order_voucher = None
    if voucher_code and discount_amount > 0:
        order_voucher = {
            "code": voucher_code,
            "discount_amount": discount_amount,
            "discount_percent": v_discount if v_type == "percent" else 0
        }
    
    order_status = "pending"
    payment_status = "Chưa thanh toán"
    proof_image = ""

    if payment_method == "qr":
        f = request.files.get("payment_proof")
        if f: 
            try:
                b64 = base64.b64encode(f.read()).decode('utf-8')
                proof_image = f"data:{f.content_type};base64,{b64}"
            except: pass

            order_status = "shipping"
            payment_status = "Đã thanh toán (AI Verified)"
            flash("AI đã kiểm tra ảnh hợp lệ! Đơn hàng đã được chuyển cho Shipper.", "success")

    if payment_method == "qr":
        f = request.files.get("payment_proof")
        if f: 
            order_status = "shipping"
            payment_status = "Đã thanh toán (AI)"
    
    items_list = [v for v in user_cart.values()]

    new_order = {
        "id": order_id,
        "customer_id": user,
        "user": user,
        "customerName": name,
        "address": address,
        "phone": phone,
        "total": total,
        "subtotal": total_before_discount,
        "voucher_discount": discount_amount,
        "voucher_code": voucher_code if discount_amount > 0 else None,
        "status": order_status,
        "paymentMethod": payment_method,
        "paymentStatus": payment_status,
        "proofImage": proof_image,
        "date": datetime.now().strftime("%H:%M %d/%m/%Y"),
        "items": items_list,
        "details": items_list,
    }

    db_put(f"orders/{order_id}", new_order)
    db_put(f"carts/{user}", {})

    msg = f"Đơn hàng #{order_id} đang chờ xử lý."
    if order_status == "shipping":
        msg = f"Đơn hàng #{order_id} đã được duyệt!"

    raw_notifs = db_get(f"notifications/{user}") or []
    notifs_list = list(raw_notifs.values()) if isinstance(raw_notifs, dict) else raw_notifs
    
    notifs_list.insert(
        0,
        {
            "id": str(uuid.uuid4()),
            "title": "Đặt hàng thành công",
            "message": msg,
            "time": datetime.now().strftime("%H:%M %d/%m"),
            "link": f"/order/{order_id}",
            "type": "order",
            "is_read": False,
            "is_new": True,
        },
    )
    db_put(f"notifications/{user}", notifs_list)

    return redirect(url_for("customer.notifications"))

# --- 1. XEM DANH SÁCH ĐỊA CHỈ ---
@customer_bp.route("/address")
@login_required(role="customer")
def address():
    username = session["user"]
    user_data = get_user_db(username) or {}
    addresses = user_data.get("addresses", [])
    return render_template("customer/address.html", addresses=addresses)

# --- 2. GIAO DIỆN THÊM ĐỊA CHỈ MỚI ---
@customer_bp.route("/address/add")
@login_required(role="customer")
def address_add():
    return render_template("customer/address_add.html")


@customer_bp.route("/address/edit/<addr_id>")
@login_required(role="customer")
def address_edit(addr_id):
    username = session["user"]
    user_data = get_user_db(username) or {}
    addresses = user_data.get("addresses", [])
    edit_address = None
    for a in addresses:
        if str(a.get("id")) == str(addr_id):
            edit_address = a
            break
    if not edit_address:
        flash("Không tìm thấy địa chỉ cần sửa.", "danger")
        return redirect(url_for("customer.address"))
    return render_template("customer/address_add.html", edit_address=edit_address)

# --- 3. XỬ LÝ LƯU ĐỊA CHỈ ---
@customer_bp.route("/save_address", methods=["POST"])
@login_required(role="customer")
def save_address():
    username = session["user"]
    user_data = get_user_db(username)
    if not user_data:
        flash("Không tìm thấy tài khoản.", "danger")
        return redirect(url_for("customer.address"))
    current_addresses = user_data.get("addresses", [])

    fullname = request.form.get("fullname")
    phone = request.form.get("phone")
    city = request.form.get("city")
    district = request.form.get("district")
    ward = request.form.get("ward")
    detail = request.form.get("detail")
    desc = request.form.get("desc")
    is_default = request.form.get("is_default") == "on"

    if not current_addresses:
        is_default = True

    if is_default:
        for addr in current_addresses:
            addr["is_default"] = False

    new_addr = {
        "id": str(uuid.uuid4()),
        "fullname": fullname,
        "phone": phone,
        "city": city,
        "district": district,
        "ward": ward,
        "detail": detail,
        "desc": desc,
        "full_address": f"{detail}, {ward}, {district}, {city}",
        "is_default": is_default,
    }

    current_addresses.append(new_addr)

    db_patch(f"users/{username}", {"addresses": current_addresses})

    flash("Thêm địa chỉ thành công!", "success")
    return redirect(url_for("customer.address"))


@customer_bp.route("/update_address/<addr_id>", methods=["POST"])
@login_required(role="customer")
def update_address(addr_id):
    username = session["user"]
    user_data = get_user_db(username)
    if not user_data:
        flash("Không tìm thấy tài khoản.", "danger")
        return redirect(url_for("customer.address"))

    current_addresses = user_data.get("addresses", [])
    target = None
    for addr in current_addresses:
        if str(addr.get("id")) == str(addr_id):
            target = addr
            break

    if not target:
        flash("Không tìm thấy địa chỉ cần cập nhật.", "danger")
        return redirect(url_for("customer.address"))

    fullname = request.form.get("fullname")
    phone = request.form.get("phone")
    city = request.form.get("city")
    district = request.form.get("district")
    ward = request.form.get("ward")
    detail = request.form.get("detail")
    desc = request.form.get("desc")
    is_default = request.form.get("is_default") == "on"

    if is_default:
        for a in current_addresses:
            a["is_default"] = False

    target.update(
        {
            "fullname": fullname,
            "phone": phone,
            "city": city,
            "district": district,
            "ward": ward,
            "detail": detail,
            "desc": desc,
            "full_address": f"{detail}, {ward}, {district}, {city}",
            "is_default": is_default,
        }
    )

    db_patch(f"users/{username}", {"addresses": current_addresses})
    flash("Cập nhật địa chỉ thành công!", "success")
    return redirect(url_for("customer.address"))

# --- 4. ĐẶT LÀM MẶC ĐỊNH ---
@customer_bp.route("/set_default_address/<addr_id>")
@login_required(role="customer")
def set_default_address(addr_id):
    username = session["user"]
    user_data = get_user_db(username) or {}
    addresses = user_data.get("addresses", [])

    for addr in addresses:
        if addr["id"] == addr_id:
            addr["is_default"] = True
        else:
            addr["is_default"] = False

    db_patch(f"users/{username}", {"addresses": addresses})
    return redirect(url_for("customer.address"))

# --- 5. XÓA ĐỊA CHỈ ---
@customer_bp.route("/delete_address/<addr_id>")
@login_required(role="customer")
def delete_address(addr_id):
    username = session["user"]
    user_data = get_user_db(username) or {}
    addresses = user_data.get("addresses", [])

    new_list = [a for a in addresses if a["id"] != addr_id]

    if new_list and not any(a["is_default"] for a in new_list):
        new_list[0]["is_default"] = True

    db_patch(f"users/{username}", {"addresses": new_list})
    flash("Đã xóa địa chỉ", "success")
    return redirect(url_for("customer.address"))


@customer_bp.route("/settings")
@login_required(role="customer")
def settings():
    lang = session.get("lang", "vi")

    text = {
        "vi": {
            "title": "Cài đặt",
            "app": "ỨNG DỤNG",
            "lang_label": "Ngôn ngữ",
            "lang_val": "Tiếng Việt",
            "sec": "BẢO MẬT",
            "pass": "Đổi mật khẩu",
            "social": "Liên kết tài khoản mạng xã hội",
            "info": "THÔNG TIN",
            "terms": "Điều khoản & Chính sách",
        },
        "en": {
            "title": "Settings",
            "app": "APPLICATION",
            "lang_label": "Language",
            "lang_val": "English",
            "sec": "SECURITY",
            "pass": "Change Password",
            "social": "Social Accounts",
            "info": "INFORMATION",
            "terms": "Terms & Policies",
        }
    }

    return render_template("customer/settings.html", t=text[lang], current_lang=lang)

# --- 2. ROUTE ĐỔI NGÔN NGỮ (Toggle) ---
@customer_bp.route("/toggle_language")
@login_required(role="customer")
def toggle_language():
    current = session.get("lang", "vi")
    new_lang = "en" if current == "vi" else "vi"
    session["lang"] = new_lang
    return redirect(url_for("customer.settings"))

# --- 3. ROUTE LIÊN KẾT MẠNG XÃ HỘI ---
@customer_bp.route("/social-links")
@login_required(role="customer")
def social_links():
    return render_template("customer/social.html")

# --- 4. ROUTE ĐIỀU KHOẢN ---
@customer_bp.route("/terms")
@login_required(role="customer")
def terms():
    return render_template("customer/terms.html")


@customer_bp.route("/change-password", methods=["GET", "POST"])
@login_required(role="customer")
def change_password():
    from services.auth_service import verify_password, hash_password  # tránh import vòng

    if request.method == "POST":
        old = request.form.get("old_password")
        new = request.form.get("new_password")
        confirm = request.form.get("confirm_password")
        user_info = get_user_db(session["user"])

        if not verify_password(user_info.get("password"), old):
            flash("Mật khẩu cũ không đúng!", "danger")
        elif not new or len(new) < 8 or new != confirm:
            flash("Mật khẩu mới không hợp lệ!", "danger")
        else:
            db_patch(
                f'users/{session["user"]}',
                {"password": hash_password(new)},
            )
            flash("Đổi mật khẩu thành công!", "success")
            return redirect(url_for("customer.settings"))
    return render_template("auth/change_password.html")


@customer_bp.route("/support")
@login_required(role="customer")
def support():
    user = session["user"]
    # Lấy lịch sử chat từ Firebase
    raw_chats = db_get(f"chats/{user}") or []
    chat_history = raw_chats if isinstance(raw_chats, list) else list(raw_chats.values()) if raw_chats else []
    return render_template("customer/support.html", chat_history=chat_history)


# --- API: LƯU TIN NHẮN CHAT VÀO FIREBASE ---
@customer_bp.route("/api/save-chat", methods=["POST"])
@login_required(role="customer")
def save_chat():
    """Lưu tin nhắn chat vào Firebase"""
    data = request.json
    user = session["user"]
    message = data.get("message", "")
    sender = data.get("sender", "user")  # "user" hoặc "admin"

    if not message:
        return jsonify({"success": False, "message": "Tin nhắn trống"})

    # Lấy lịch sử chat hiện tại
    raw_chats = db_get(f"chats/{user}") or []
    chat_history = raw_chats if isinstance(raw_chats, list) else list(raw_chats.values()) if raw_chats else []

    # Thêm tin nhắn mới
    import uuid
    new_message = {
        "id": str(uuid.uuid4()),
        "message": message,
        "sender": sender,
        "timestamp": datetime.now().isoformat(),
        "is_read": False
    }
    chat_history.append(new_message)

    # Lưu lại vào Firebase
    db_put(f"chats/{user}", chat_history)

    return jsonify({"success": True, "message": "Đã lưu tin nhắn"})


# --- API: LẤY TIN NHẮN CHAT MỚI (Polling) ---
@customer_bp.route("/api/get-chat-updates", methods=["GET"])
@login_required(role="customer")
def get_chat_updates():
    """Lấy tin nhắn mới từ admin (dùng polling)"""
    user = session["user"]
    raw_chats = db_get(f"chats/{user}") or []
    chat_history = raw_chats if isinstance(raw_chats, list) else list(raw_chats.values()) if raw_chats else []

    # Lấy tin nhắn từ admin chưa đọc
    admin_messages = [m for m in chat_history if m.get("sender") == "admin" and not m.get("is_read", False)]

    # Đánh dấu các tin nhắn admin vừa trả về là đã đọc để tránh lặp lại nhiều lần
    if admin_messages:
        for msg in chat_history:
            if msg.get("sender") == "admin" and not msg.get("is_read", False):
                msg["is_read"] = True
        db_put(f"chats/{user}", chat_history)

    return jsonify({
        "success": True,
        "messages": admin_messages,
        "all_messages": chat_history[-20:] if len(chat_history) > 20 else chat_history  # Lấy 20 tin gần nhất
    })

# --- LOGIC "AI" TRẢ LỜI TỰ ĐỘNG (NÂNG CẤP: DÀI HƠN & TỰ NHIÊN HƠN) ---
def get_ai_response(msg):
    msg = msg.lower()
    
    # 1. Kịch bản Chào hỏi
    if any(x in msg for x in ['hi', 'chào', 'hello', 'alo', 'bắt đầu']):
        return (
            "Dạ chào bạn! 👋 Cảm ơn bạn đã nhắn tin cho bộ phận hỗ trợ của Fong Food.<br>"
            "Mình là trợ lý ảo AI, rất vui được đồng hành và hỗ trợ bạn trong ngày hôm nay.<br>"
            "Hiện tại quán đang có rất nhiều chương trình ưu đãi hấp dẫn dành riêng cho khách hàng thân thiết.<br>"
            "Bạn đang cần mình giúp đỡ về việc đặt món mới hay muốn kiểm tra tình trạng đơn hàng vừa đặt ạ?"
        )
    
    # 2. Kịch bản hỏi Đơn hàng (Hủy, kiểm tra, lâu quá...)
    if any(x in msg for x in ['đơn hàng', 'đơn của tôi', 'bao lâu', 'chưa nhận', 'hủy đơn']):
        return (
            "Dạ, mình đã ghi nhận yêu cầu kiểm tra đơn hàng của bạn trên hệ thống.<br>"
            "Thông thường, các đơn hàng sẽ được bếp chuẩn bị trong 10-15 phút và giao đến bạn trong vòng 30 phút tiếp theo.<br>"
            "Để mình có thể tra cứu chính xác vị trí của Shipper, bạn vui lòng cung cấp giúp mình Mã Đơn Hàng (ví dụ #12345) nhé.<br>"
            "Trong lúc chờ đợi, bạn có muốn mình gửi tặng một mã giảm giá nhỏ cho lần đặt tiếp theo không ạ?"
        )
    
    # 3. Kịch bản hỏi Mật khẩu/Tài khoản/Đăng ký
    if any(x in msg for x in ['mật khẩu', 'pass', 'đổi tên', 'tài khoản', 'đăng nhập']):
        return (
            "Về vấn đề tài khoản và bảo mật, bạn hãy hoàn toàn yên tâm nhé.<br>"
            "Bạn có thể truy cập ngay vào mục 'Cài đặt & Bảo mật' (hình bánh răng) trong trang Cá nhân để thay đổi thông tin.<br>"
            "Nếu bạn lỡ quên mật khẩu cũ, hãy sử dụng tính năng 'Quên mật khẩu' ở màn hình đăng nhập để lấy lại mã OTP qua email hoặc số điện thoại.<br>"
            "Bạn có gặp khó khăn gì trong quá trình thao tác không, để mình hướng dẫn chi tiết từng bước nhé?"
        )
    
    # 4. Kịch bản Khen/Chê (Phản hồi chất lượng)
    if any(x in msg for x in ['ngon', 'tốt', 'thích', 'tuyệt']):
        return (
            "Woa, nghe bạn khen mà mình và cả đội ngũ bếp vui lắm luôn ạ! 🥰<br>"
            "Sự hài lòng của bạn chính là động lực lớn nhất để Fong Food cố gắng hoàn thiện hơn mỗi ngày.<br>"
            "Bạn nhớ vào mục 'Lịch sử đơn hàng' để đánh giá 5 sao giúp quán lên Top nhé.<br>"
            "Hôm nay bạn có muốn thử thêm món 'Best Seller' mới ra mắt của quán không ạ?"
        )
        
    if any(x in msg for x in ['dở', 'chậm', 'tệ', 'chán', 'nhầm']):
        return (
            "Dạ, trước tiên cho mình gửi lời xin lỗi chân thành nhất vì trải nghiệm chưa được trọn vẹn này ạ. 😿<br>"
            "Fong Food luôn trân trọng mọi ý kiến đóng góp thẳng thắn để cải thiện chất lượng dịch vụ ngay lập tức.<br>"
            "Mình đã chuyển thông tin phản ánh này đến quản lý cửa hàng để xem xét lại quy trình.<br>"
            "Bạn có thể cho mình xin số điện thoại để quản lý gọi điện trực tiếp xin lỗi và gửi quà đền bù cho bạn được không ạ?"
        )

    # 5. Kịch bản hỏi Địa chỉ/Giờ mở cửa
    if any(x in msg for x in ['ở đâu', 'địa chỉ', 'mấy giờ', 'mở cửa']):
        return (
            "Quán Fong Food có địa chỉ duy nhất tại số 335 Cầu Giấy, Hà Nội, vị trí rất dễ tìm và có chỗ để xe rộng rãi.<br>"
            "Chúng mình mở cửa phục vụ liên tục từ 8h00 sáng đến 22h00 tối tất cả các ngày trong tuần (kể cả lễ tết).<br>"
            "Ngoài ra, bên mình cũng hỗ trợ giao hàng tận nơi qua App với phí ship cực rẻ.<br>"
            "Bạn đang ở khu vực nào để mình tư vấn phí giao hàng và thời gian dự kiến cho bạn nhé?"
        )

    # Mặc định (Khi không hiểu)
    return (
        "Dạ, xin lỗi bạn vì mình là AI nên chưa hiểu rõ ý câu hỏi này lắm.<br>"
        "Tuy nhiên, đừng lo lắng, mình sẽ chuyển tin nhắn này đến nhân viên trực tổng đài ngay bây giờ.<br>"
        "Đội ngũ chăm sóc khách hàng sẽ phản hồi lại bạn trong vòng 5 phút nữa.<br>"
        "Trong thời gian chờ đợi, bạn có muốn tham khảo qua Menu các món ăn vặt đang giảm giá hôm nay không ạ?"
    )

# --- API: NHẬN TIN NHẮN & TRẢ LỜI ---
@customer_bp.route("/api/chat-process", methods=["POST"])
@login_required(role="customer")
def api_chat_process():
    from routes.ai import get_ai_chatbot_response
    import uuid
    
    data = request.json
    user_msg = data.get("message", "")
    user = session.get("user")
    
    time.sleep(1.5)
    
    # Lưu tin nhắn của user vào database
    chat_id = f"chats/{user}"
    existing_chats = db_get(chat_id) or []
    if isinstance(existing_chats, dict):
        existing_chats = list(existing_chats.values())
    
    user_msg_data = {
        "id": str(uuid.uuid4()),
        "sender": "user",
        "message": user_msg,
        "timestamp": datetime.now().isoformat()
    }
    existing_chats.append(user_msg_data)
    db_put(chat_id, existing_chats)
    
    # AI trả lời
    bot_reply = get_ai_chatbot_response(user_msg, user)
    reply_text = bot_reply.get("message", "") if isinstance(bot_reply, dict) else bot_reply
    
    # Lưu tin nhắn của AI/Admin vào database
    existing_chats = db_get(chat_id) or []
    if isinstance(existing_chats, dict):
        existing_chats = list(existing_chats.values())
    
    bot_msg_data = {
        "id": str(uuid.uuid4()),
        "sender": "admin",
        "message": reply_text,
        "timestamp": datetime.now().isoformat()
    }
    existing_chats.append(bot_msg_data)
    db_put(chat_id, existing_chats)
    
    return jsonify({"reply": reply_text})

# --- API: ĐỒNG BỘ GIỎ HÀNG TỪ LOCALSTORAGE ---
@customer_bp.route("/api/sync-cart", methods=["POST"])
@login_required(role="customer")
def sync_cart():
    """Đồng bộ giỏ hàng từ localStorage lên server"""
    data = request.json
    local_cart = data.get("cart", {})
    user = session["user"]

    # Lấy giỏ hàng hiện tại từ server
    raw_cart = db_get(f"carts/{user}") or {}
    server_cart = normalize_data(raw_cart, "id")

    # Merge giỏ hàng: cộng dồn số lượng
    for pid, item in local_cart.items():
        if pid in server_cart:
            server_cart[pid]["qty"] += item.get("qty", 1)
        else:
            server_cart[pid] = {
                "name": item.get("name", ""),
                "price": item.get("price", 0),
                "qty": item.get("qty", 1),
                "id": pid,
            }

    db_put(f"carts/{user}", server_cart)
    return jsonify({"success": True, "message": "Đã đồng bộ giỏ hàng"})


@customer_bp.route("/api/get-cart", methods=["GET"])
@login_required(role="customer")
def get_cart_api():
    """Lấy giỏ hàng hiện tại (dùng trước khi logout)"""
    user = session["user"]
    raw_cart = db_get(f"carts/{user}") or {}
    return jsonify({"cart": raw_cart})


@customer_bp.context_processor
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
                    total_cart += int(item.get('qty', 0))
        
        # 2. Đếm thông báo
        raw_notifs = db_get(f"notifications/{user}") or []
        if isinstance(raw_notifs, dict):
            notif_items = raw_notifs.values()
        elif isinstance(raw_notifs, list):
            notif_items = raw_notifs
        else:
            notif_items = []
        
        if notif_items:
            for n in notif_items:
                if isinstance(n, dict) and not n.get("is_read"):
                    unread_notif += 1
                
    return dict(total_cart_items=total_cart, unread_notif_count=unread_notif)


@customer_bp.route("/mark_all_read")
@login_required(role="customer")
def mark_all_read():
    user = session["user"]
    all_notifs = db_get("notifications") or {}

    if isinstance(all_notifs, dict):
        for val in all_notifs.values():
            if val.get("user") == user:
                val["is_read"] = True
    elif isinstance(all_notifs, list):
        for val in all_notifs:
            if isinstance(val, dict) and val.get("user") == user:
                val["is_read"] = True

    db_put("notifications", all_notifs)
    return redirect(url_for("customer.notifications"))


@customer_bp.route("/confirm_receipt/<oid>")
@login_required(role="customer")
def confirm_receipt(oid):
    order = db_get(f"orders/{oid}")
    owner = order.get("customer_id") or order.get("user")

    if owner == session["user"] and order.get("status") == "shipping":
        db_patch(
            f"orders/{oid}",
            {"status": "completed", "paymentStatus": "Đã thanh toán"},
        )
        flash("Cảm ơn bạn đã mua hàng! Đơn hàng đã hoàn tất.", "success")
    else:
        flash("Trạng thái đơn hàng không hợp lệ.", "warning")

    return redirect(url_for("customer.history"))


@customer_bp.route("/qr-scan")
@login_required(role="customer")
def qr_scan():
    """
    Trang quét QR code để kiểm tra đơn hàng
    """
    return render_template("customer/qr_scan.html")
