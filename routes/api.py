import base64
import uuid
import time
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from decorators import login_required, admin_required
from utils import db_get, db_put, db_patch
import re

api_bp = Blueprint("api_v1", __name__)

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


# ==================== AUTH API ====================

def require_login(f):
    """Decorator đơn giản cho API - không conflict"""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return jsonify({"success": False, "error": "Unauthorized", "message": "Vui lòng đăng nhập"}), 401
        return f(*args, **kwargs)
    return wrapper


def require_admin(f):
    """Decorator đơn giản cho admin API - không conflict"""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return jsonify({"success": False, "error": "Unauthorized", "message": "Vui lòng đăng nhập"}), 401
        if session.get("role") != "admin":
            return jsonify({"success": False, "error": "Forbidden", "message": "Không có quyền"}), 403
        return f(*args, **kwargs)
    return wrapper


@api_bp.route("/auth/register", methods=["POST"])
def api_register():
    """API đăng ký tài khoản"""
    data = request.json
    username = data.get("username")
    password = data.get("password")
    name = data.get("name")
    phone = data.get("phone")
    email = data.get("email")

    if not username or not password:
        return jsonify({"success": False, "message": "Thiếu thông tin bắt buộc"}), 400

    users = db_get("users") or {}
    if isinstance(users, dict) and username in users:
        return jsonify({"success": False, "message": "Tài khoản đã tồn tại"}), 400

    from services.auth_service import hash_password
    new_user = {
        "username": username,
        "password": hash_password(password),
        "name": name or username,
        "phone": phone,
        "email": email,
        "role": "customer",
        "created_at": datetime.now().isoformat(),
        "points": 0,
        "rank": "Đồng",
        "total_spent": 0,
        "order_count": 0,
    }

    if isinstance(users, dict):
        users[username] = new_user
    else:
        users = {username: new_user}
    
    db_put("users", users)
    return jsonify({"success": True, "message": "Đăng ký thành công", "user": username})


@api_bp.route("/auth/login", methods=["POST"])
def api_login():
    """API đăng nhập - Hỗ trợ mobile/web API"""
    data = request.json
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"success": False, "message": "Thiếu thông tin đăng nhập"}), 400

    users = db_get("users") or {}
    user = None
    
    if isinstance(users, dict):
        user = users.get(username)
    else:
        for u in users:
            if u.get("username") == username:
                user = u
                break

    if not user:
        return jsonify({"success": False, "message": "Tài khoản không tồn tại"}), 401

    from services.auth_service import verify_password
    if not verify_password(user.get("password", ""), password):
        return jsonify({"success": False, "message": "Mật khẩu không đúng"}), 401

    login_token = str(uuid.uuid4())

    # Cập nhật token trong DB
    db_patch(f"users/{username}", {"login_token": login_token, "last_login": datetime.now().isoformat()})

    # Nếu là request từ web có session, lưu vào session
    if session.get("user"):
        session["login_token"] = login_token

    return jsonify({
        "success": True,
        "message": "Đăng nhập thành công",
        "user": {
            "username": username,
            "name": user.get("name"),
            "email": user.get("email"),
            "phone": user.get("phone"),
            "role": user.get("role"),
            "points": user.get("points", 0),
            "rank": user.get("rank", "Đồng"),
            "avatar": user.get("avatar", ""),
        },
        "token": login_token  # Token dùng cho mobile API
    })


@api_bp.route("/auth/logout", methods=["POST"])
def api_logout():
    """API đăng xuất"""
    username = session.get("user")
    if username:
        db_patch(f"users/{username}", {"login_token": None})
    session.clear()
    return jsonify({"success": True, "message": "Đăng xuất thành công"})


@api_bp.route("/auth/profile", methods=["GET"])
@require_login
def api_get_profile():
    """API lấy thông tin profile"""
    username = session["user"]
    users = db_get("users") or {}
    user = users.get(username) if isinstance(users, dict) else None
    
    if not user:
        return jsonify({"success": False, "message": "Không tìm thấy người dùng"}), 404

    return jsonify({
        "success": True,
        "user": {
            "username": username,
            "name": user.get("name"),
            "email": user.get("email"),
            "phone": user.get("phone"),
            "dob": user.get("dob"),
            "gender": user.get("gender"),
            "avatar": user.get("avatar", ""),
            "points": user.get("points", 0),
            "rank": user.get("rank", "Đồng"),
            "total_spent": user.get("total_spent", 0),
            "order_count": user.get("order_count", 0),
            "addresses": user.get("addresses", []),
            "created_at": user.get("created_at"),
        }
    })


@api_bp.route("/auth/profile", methods=["PUT"])
@require_login
def api_update_profile():
    """API cập nhật profile"""
    username = session["user"]
    data = request.json

    update_data = {
        "name": data.get("name"),
        "phone": data.get("phone"),
        "dob": data.get("dob"),
        "gender": data.get("gender"),
    }

    if data.get("avatar"):
        update_data["avatar"] = data.get("avatar")

    db_patch(f"users/{username}", update_data)
    return jsonify({"success": True, "message": "Cập nhật thành công"})


# ==================== PRODUCTS API ====================

@api_bp.route("/products", methods=["GET"])
def api_products():
    """API lấy danh sách sản phẩm"""
    category = request.args.get("category", "all")
    search = request.args.get("search", "").lower()

    raw_products = db_get("products") or {}
    products = normalize_data(raw_products, "id")

    result = []
    for pid, p in products.items():
        if category != "all" and p.get("category") != category:
            continue
        if search and search not in p.get("name", "").lower():
            continue
        result.append({
            "id": pid,
            "name": p.get("name"),
            "price": p.get("price"),
            "category": p.get("category"),
            "description": p.get("description"),
            "image": p.get("image"),
            "isPromoted": p.get("isPromoted", False),
        })

    return jsonify({"success": True, "products": result})


@api_bp.route("/products/<pid>", methods=["GET"])
def api_product_detail(pid):
    """API lấy chi tiết sản phẩm"""
    product = db_get(f"products/{pid}")
    if not product:
        return jsonify({"success": False, "message": "Sản phẩm không tồn tại"}), 404

    return jsonify({
        "success": True,
        "product": {
            "id": pid,
            **product
        }
    })


# ==================== CART API ====================

@api_bp.route("/cart", methods=["GET"])
@require_login
def api_get_cart():
    """API lấy giỏ hàng"""
    user = session["user"]
    raw_cart = db_get(f"carts/{user}") or {}
    cart = normalize_data(raw_cart, "id")

    raw_products = db_get("products") or {}
    all_products = normalize_data(raw_products, "id")

    items = []
    total = 0
    for pid, item in cart.items():
        product = all_products.get(pid, {})
        item_total = item.get("qty", 0) * item.get("price", 0)
        items.append({
            "id": pid,
            "name": item.get("name"),
            "price": item.get("price"),
            "qty": item.get("qty"),
            "image": product.get("image", ""),
            "total": item_total,
        })
        total += item_total

    return jsonify({
        "success": True,
        "items": items,
        "total": total,
        "item_count": len(items)
    })


@api_bp.route("/cart/add", methods=["POST"])
@require_login
def api_add_to_cart():
    """API thêm vào giỏ hàng"""
    user = session["user"]
    data = request.json
    product_id = data.get("product_id")
    quantity = data.get("quantity", 1)

    raw_products = db_get("products") or {}
    products = normalize_data(raw_products, "id")
    product = products.get(product_id)

    if not product:
        return jsonify({"success": False, "message": "Sản phẩm không tồn tại"}), 404

    raw_cart = db_get(f"carts/{user}") or {}
    cart = normalize_data(raw_cart, "id")

    if product_id in cart:
        cart[product_id]["qty"] += quantity
    else:
        cart[product_id] = {
            "name": product["name"],
            "price": product.get("price", 0),
            "qty": quantity,
            "id": product_id,
        }

    db_put(f"carts/{user}", cart)
    return jsonify({"success": True, "message": f"Đã thêm {product['name']} vào giỏ"})


@api_bp.route("/cart/update", methods=["PUT"])
@require_login
def api_update_cart():
    """API cập nhật số lượng trong giỏ"""
    user = session["user"]
    data = request.json
    product_id = data.get("product_id")
    quantity = data.get("quantity")

    raw_cart = db_get(f"carts/{user}") or {}
    cart = normalize_data(raw_cart, "id")

    if product_id not in cart:
        return jsonify({"success": False, "message": "Sản phẩm không trong giỏ"}), 404

    if quantity <= 0:
        del cart[product_id]
    else:
        cart[product_id]["qty"] = quantity

    db_put(f"carts/{user}", cart)
    return jsonify({"success": True, "message": "Cập nhật giỏ hàng thành công"})


@api_bp.route("/cart/remove/<pid>", methods=["DELETE"])
@require_login
def api_remove_from_cart(pid):
    """API xóa sản phẩm khỏi giỏ"""
    user = session["user"]
    raw_cart = db_get(f"carts/{user}") or {}
    cart = normalize_data(raw_cart, "id")

    if pid in cart:
        del cart[pid]
        db_put(f"carts/{user}", cart)
        return jsonify({"success": True, "message": "Đã xóa sản phẩm"})
    
    return jsonify({"success": False, "message": "Sản phẩm không trong giỏ"}), 404


@api_bp.route("/cart/clear", methods=["DELETE"])
@require_login
def api_clear_cart():
    """API xóa toàn bộ giỏ hàng"""
    user = session["user"]
    db_put(f"carts/{user}", {})
    return jsonify({"success": True, "message": "Đã xóa giỏ hàng"})


# ==================== ORDERS API ====================

@api_bp.route("/orders", methods=["GET"])
@require_login
def api_orders():
    """API lấy danh sách đơn hàng"""
    user = session["user"]
    role = session.get("role")

    raw_orders = db_get("orders") or {}
    orders = normalize_data(raw_orders, "id")

    result = []
    for oid, order in orders.items():
        if role == "customer" and order.get("user") != user:
            continue
        result.append({
            "id": oid,
            "customerName": order.get("customerName"),
            "phone": order.get("phone"),
            "address": order.get("address"),
            "total": order.get("total"),
            "status": order.get("status"),
            "paymentMethod": order.get("paymentMethod"),
            "paymentStatus": order.get("paymentStatus"),
            "date": order.get("date"),
            "items": order.get("items", []),
        })

    result.sort(key=lambda x: x.get("date", ""), reverse=True)
    return jsonify({"success": True, "orders": result})


@api_bp.route("/orders/<oid>", methods=["GET"])
@require_login
def api_order_detail(oid):
    """API lấy chi tiết đơn hàng"""
    user = session["user"]
    role = session.get("role")

    order = db_get(f"orders/{oid}")
    if not order:
        return jsonify({"success": False, "message": "Đơn hàng không tồn tại"}), 404

    if role == "customer" and order.get("user") != user:
        return jsonify({"success": False, "message": "Không có quyền truy cập"}), 403

    return jsonify({
        "success": True,
        "order": {
            "id": oid,
            **order
        }
    })


@api_bp.route("/orders", methods=["POST"])
@require_login
def api_create_order():
    """API tạo đơn hàng mới"""
    user = session["user"]
    data = request.json

    name = data.get("name")
    phone = data.get("phone")
    address = data.get("address")
    payment_method = data.get("payment_method", "cod")
    notes = data.get("notes", "")

    raw_cart = db_get(f"carts/{user}") or {}
    cart = normalize_data(raw_cart, "id")

    if not cart:
        return jsonify({"success": False, "message": "Giỏ hàng trống"}), 400

    total = sum(item.get("price", 0) * item.get("qty", 0) for item in cart.values())
    order_id = str(uuid.uuid4())[:8].upper()

    new_order = {
        "id": order_id,
        "customer_id": user,
        "user": user,
        "customerName": name,
        "phone": phone,
        "address": address,
        "total": total,
        "status": "pending",
        "paymentMethod": payment_method,
        "paymentStatus": "Chưa thanh toán" if payment_method == "cod" else "Đã thanh toán",
        "date": datetime.now().strftime("%H:%M %d/%m/%Y"),
        "items": list(cart.values()),
        "notes": notes,
    }

    db_put(f"orders/{order_id}", new_order)
    db_put(f"carts/{user}", {})

    # Cập nhật điểm tích lũy
    users = db_get("users") or {}
    user_data = users.get(user) if isinstance(users, dict) else None
    if user_data:
        points_earned = int(total / 10000)
        new_points = user_data.get("points", 0) + points_earned
        new_total_spent = user_data.get("total_spent", 0) + total
        new_order_count = user_data.get("order_count", 0) + 1

        new_rank = "Đồng"
        if new_total_spent > 10_000_000:
            new_rank = "Kim Cương"
        elif new_total_spent > 5_000_000:
            new_rank = "Vàng"
        elif new_total_spent > 2_000_000:
            new_rank = "Bạc"

        db_patch(f"users/{user}", {
            "points": new_points,
            "total_spent": new_total_spent,
            "order_count": new_order_count,
            "rank": new_rank
        })

    return jsonify({
        "success": True,
        "message": "Đặt hàng thành công",
        "order_id": order_id,
        "points_earned": points_earned
    })


@api_bp.route("/orders/<oid>/cancel", methods=["POST"])
@require_login
def api_cancel_order(oid):
    """API hủy đơn hàng"""
    user = session["user"]
    order = db_get(f"orders/{oid}")

    if not order:
        return jsonify({"success": False, "message": "Đơn hàng không tồn tại"}), 404

    if order.get("user") != user:
        return jsonify({"success": False, "message": "Không có quyền hủy đơn này"}), 403

    if order.get("status") != "pending":
        return jsonify({"success": False, "message": "Đơn hàng đã được xử lý, không thể hủy"}), 400

    db_patch(f"orders/{oid}", {"status": "cancelled"})
    return jsonify({"success": True, "message": "Đã hủy đơn hàng"})


# ==================== ADDRESS API ====================

@api_bp.route("/addresses", methods=["GET"])
@require_login
def api_get_addresses():
    """API lấy danh sách địa chỉ"""
    username = session["user"]
    users = db_get("users") or {}
    user_data = users.get(username) if isinstance(users, dict) else None

    if not user_data:
        return jsonify({"success": False, "message": "Không tìm thấy người dùng"}), 404

    addresses = user_data.get("addresses", [])
    return jsonify({"success": True, "addresses": addresses})


@api_bp.route("/addresses", methods=["POST"])
@require_login
def api_add_address():
    """API thêm địa chỉ mới"""
    username = session["user"]
    data = request.json

    users = db_get("users") or {}
    user_data = users.get(username) if isinstance(users, dict) else None

    if not user_data:
        return jsonify({"success": False, "message": "Không tìm thấy người dùng"}), 404

    addresses = user_data.get("addresses", [])
    is_default = data.get("is_default", False)

    if is_default:
        for addr in addresses:
            addr["is_default"] = False

    new_addr = {
        "id": str(uuid.uuid4()),
        "fullname": data.get("fullname"),
        "phone": data.get("phone"),
        "city": data.get("city"),
        "district": data.get("district"),
        "ward": data.get("ward"),
        "detail": data.get("detail"),
        "full_address": f"{data.get('detail')}, {data.get('ward')}, {data.get('district')}, {data.get('city')}",
        "is_default": is_default or len(addresses) == 0,
    }

    addresses.append(new_addr)
    db_patch(f"users/{username}", {"addresses": addresses})

    return jsonify({"success": True, "message": "Thêm địa chỉ thành công", "address": new_addr})


@api_bp.route("/addresses/<addr_id>", methods=["PUT"])
@require_login
def api_update_address(addr_id):
    """API cập nhật địa chỉ"""
    username = session["user"]
    data = request.json

    users = db_get("users") or {}
    user_data = users.get(username) if isinstance(users, dict) else None

    if not user_data:
        return jsonify({"success": False, "message": "Không tìm thấy người dùng"}), 404

    addresses = user_data.get("addresses", [])
    updated = False

    for addr in addresses:
        if addr["id"] == addr_id:
            addr.update({
                "fullname": data.get("fullname", addr.get("fullname")),
                "phone": data.get("phone", addr.get("phone")),
                "city": data.get("city", addr.get("city")),
                "district": data.get("district", addr.get("district")),
                "ward": data.get("ward", addr.get("ward")),
                "detail": data.get("detail", addr.get("detail")),
                "full_address": f"{data.get('detail', addr.get('detail'))}, {data.get('ward', addr.get('ward'))}, {data.get('district', addr.get('district'))}, {data.get('city', addr.get('city'))}",
            })
            updated = True
            break

    if updated:
        db_patch(f"users/{username}", {"addresses": addresses})
        return jsonify({"success": True, "message": "Cập nhật địa chỉ thành công"})
    
    return jsonify({"success": False, "message": "Địa chỉ không tồn tại"}), 404


@api_bp.route("/addresses/<addr_id>/default", methods=["PUT"])
@require_login
def api_set_default_address(addr_id):
    """API đặt làm địa chỉ mặc định"""
    username = session["user"]
    users = db_get("users") or {}
    user_data = users.get(username) if isinstance(users, dict) else None

    if not user_data:
        return jsonify({"success": False, "message": "Không tìm thấy người dùng"}), 404

    addresses = user_data.get("addresses", [])

    for addr in addresses:
        addr["is_default"] = (addr["id"] == addr_id)

    db_patch(f"users/{username}", {"addresses": addresses})
    return jsonify({"success": True, "message": "Đặt địa chỉ mặc định thành công"})


@api_bp.route("/addresses/<addr_id>", methods=["DELETE"])
@require_login
def api_delete_address(addr_id):
    """API xóa địa chỉ"""
    username = session["user"]
    users = db_get("users") or {}
    user_data = users.get(username) if isinstance(users, dict) else None

    if not user_data:
        return jsonify({"success": False, "message": "Không tìm thấy người dùng"}), 404

    addresses = user_data.get("addresses", [])
    new_addresses = [a for a in addresses if a["id"] != addr_id]

    if new_addresses and not any(a.get("is_default") for a in new_addresses):
        new_addresses[0]["is_default"] = True

    db_patch(f"users/{username}", {"addresses": new_addresses})
    return jsonify({"success": True, "message": "Xóa địa chỉ thành công"})


# ==================== NOTIFICATIONS API ====================

@api_bp.route("/notifications", methods=["GET"])
@require_login
def api_notifications():
    """API lấy danh sách thông báo"""
    user = session["user"]
    raw_notifs = db_get(f"notifications/{user}") or []
    notifications = list(raw_notifs.values()) if isinstance(raw_notifs, dict) else raw_notifs

    return jsonify({
        "success": True,
        "notifications": notifications
    })


@api_bp.route("/notifications/read-all", methods=["PUT"])
@require_login
def api_mark_all_read():
    """API đánh dấu tất cả đã đọc"""
    user = session["user"]
    all_notifs = db_get(f"notifications/{user}") or []

    if isinstance(all_notifs, dict):
        for val in all_notifs.values():
            if isinstance(val, dict):
                val["is_read"] = True
    elif isinstance(all_notifs, list):
        for val in all_notifs:
            if isinstance(val, dict):
                val["is_read"] = True

    db_put(f"notifications/{user}", all_notifs)
    return jsonify({"success": True, "message": "Đã đánh dấu tất cả là đã đọc"})


# ==================== CATEGORIES API ====================

@api_bp.route("/categories", methods=["GET"])
def api_categories():
    """API lấy danh mục sản phẩm"""
    categories = [
        {"id": "combo", "name": "Combo", "icon": "fa-combo"},
        {"id": "ga", "name": "Gà", "icon": "fa-drumstick"},
        {"id": "bun", "name": "Bún/Phở", "icon": "fa-bowl-food"},
        {"id": "trang_mieng", "name": "Tráng miệng", "icon": "fa-ice-cream"},
        {"id": "do_uong", "name": "Đồ uống", "icon": "fa-glass-water"},
        {"id": "mon_phu", "name": "Món phụ", "icon": "fa-utensils"},
    ]
    return jsonify({"success": True, "categories": categories})


# ==================== PAYMENT API ====================

@api_bp.route("/payment/create-qr", methods=["POST"])
@require_login
def api_create_payment_qr():
    """API tạo mã QR thanh toán"""
    data = request.json
    order_id = data.get("order_id")
    amount = data.get("amount")
    payment_method = data.get("payment_method", "vnpay")

    order = db_get(f"orders/{order_id}")
    if not order:
        return jsonify({"success": False, "message": "Đơn hàng không tồn tại"}), 404

    qr_data = {
        "order_id": order_id,
        "amount": amount,
        "method": payment_method,
        "created_at": datetime.now().isoformat(),
    }

    if payment_method == "vnpay":
        qr_data["qr_url"] = f"https://img.vnpay.vn/vnpayqr?amount={amount}&order={order_id}"
    elif payment_method == "momo":
        qr_data["qr_url"] = f"https://momo.vn/qr?partnerId=FONGFOOD&amount={amount}&orderId={order_id}"
    elif payment_method == "zalopay":
        qr_data["qr_url"] = f"https://zalo.me/pay?amount={amount}&order={order_id}"

    return jsonify({
        "success": True,
        "qr_data": qr_data
    })


@api_bp.route("/payment/callback", methods=["POST"])
def api_payment_callback():
    """API nhận callback từ cổng thanh toán"""
    data = request.json
    order_id = data.get("order_id")
    status = data.get("status")
    transaction_id = data.get("transaction_id")

    if status == "success":
        db_patch(f"orders/{order_id}", {
            "paymentStatus": "Đã thanh toán",
            "status": "shipping",
            "transaction_id": transaction_id
        })
        return jsonify({"success": True, "message": "Thanh toán thành công"})
    
    return jsonify({"success": False, "message": "Thanh toán thất bại"})


# ==================== QR CODE CHECK API ====================

# ==================== VOUCHER API ====================

@api_bp.route("/voucher/check", methods=["POST"])
def api_check_voucher():
    """
    API kiểm tra voucher trước khi áp dụng - dùng cho AJAX validation
    """
    import logging
    logger = logging.getLogger(__name__)
    
    data = request.json or {}
    voucher_code = (data.get("code") or "").strip().upper()
    username = session.get("user", "")
    
    if not voucher_code:
        return jsonify({"success": False, "message": "Vui lòng nhập mã voucher"}), 400
    
    vouchers = db_get("vouchers") or {}
    logger.info(f"=== CHECK_VOUCHER: code='{voucher_code}', all_vouchers={vouchers} ===")
    
    voucher = None
    if isinstance(vouchers, dict):
        # Search by code in the voucher object, not by key
        for v_key, v_data in vouchers.items():
            if isinstance(v_data, dict) and v_data.get("code") == voucher_code:
                voucher = v_data
                break
    elif isinstance(vouchers, list):
        for v in vouchers:
            if isinstance(v, dict) and v.get("code") == voucher_code:
                voucher = v
                break
    
    if not voucher:
        return jsonify({"success": False, "message": "Mã voucher không tồn tại"}), 404
    
    target_user = voucher.get("user") or "all"
    valid_for_user = target_user in ("all", username)
    
    valid_until = voucher.get("valid_until")
    still_valid = True
    if valid_until:
        try:
            dt_valid = datetime.fromisoformat(valid_until)
            still_valid = dt_valid >= datetime.now()
        except Exception:
            still_valid = True
    
    if not valid_for_user:
        return jsonify({"success": False, "message": "Voucher không dành cho tài khoản này"}), 400
    
    if not still_valid:
        return jsonify({"success": False, "message": "Voucher đã hết hạn"}), 400
    
    v_type = voucher.get("type", "percent")
    v_discount = float(voucher.get("discount", 0) or 0)
    min_order = float(voucher.get("min_order", 0) or 0)

    # Get order_total from request to calculate discount
    order_total = float(data.get("order_total", 0) or 0)

    # Check minimum order
    if order_total > 0 and order_total < min_order:
        return jsonify({"success": False, "message": f"Đơn hàng tối thiểu {min_order:,}đ để dùng voucher này"}), 400

    # Calculate discount amount
    discount_amount = 0
    if v_type == "percent":
        discount_amount = int(order_total * v_discount / 100)

    return jsonify({
        "success": True,
        "message": f"Voucher hợp lệ! Giảm {v_discount}%",
        "voucher": {
            "code": voucher.get("code"),
            "discount": v_discount,
            "type": v_type,
            "min_order": min_order
        },
        "discount_amount": discount_amount
    })


@api_bp.route("/qr/check", methods=["POST"])
def api_qr_check():
    """
    API kiểm tra mã QR khi quét - dùng cho scanner thực tế
    """
    import logging
    logger = logging.getLogger(__name__)
    
    data = request.json or {}
    qr_data = data.get("qr_data", "").strip()
    
    logger.info(f"=== QR SCAN: received qr_data='{qr_data}' ===")
    
    logger.info(f"=== QR SCAN: received qr_data='{qr_data}' ===")
    
    if not qr_data:
        return jsonify({"success": False, "message": "Mã QR trống"}), 400
    
    # Các format QR có thể nhận:
    # 1. Mã đơn hàng trực tiếp (ví dụ: "ORD123")
    # 2. URL có chứa order_id (ví dụ: "https://fongfood.com/order/ABC123")
    # 3. JSON string chứa order_id
    
    order_id = None
    
    # Thử parse JSON nếu là JSON
    try:
        qr_json = json.loads(qr_data)
        order_id = qr_json.get("order_id") or qr_json.get("id")
    except:
        # Không phải JSON, thử các cách khác
        pass
    
    # Nếu chưa có order_id, thử extract từ URL hoặc string
    if not order_id:
        if "order" in qr_data.lower():
            # Extract order ID from URL
            parts = qr_data.split("/")
            for i, p in enumerate(parts):
                if "order" in p.lower() and i + 1 < len(parts):
                    order_id = parts[i + 1]
                    break
        else:
            # Coi như QR chứa trực tiếp mã đơn
            order_id = qr_data
    
    # Clean order_id
    order_id = order_id.strip().upper() if order_id else None
    
    logger.info(f"=== QR SCAN: looking for order_id='{order_id}' ===")
    
    if not order_id:
        return jsonify({"success": False, "message": "Không thể parse mã đơn từ QR"}), 400
    
    # Tìm đơn hàng trong Firebase
    # Thử tìm theo key trực tiếp
    order = db_get(f"orders/{order_id}")
    
    # Nếu không tìm thấy, thử duyệt qua tất cả orders
    if not order:
        all_orders = db_get("orders") or {}
        if isinstance(all_orders, dict):
            for oid, od in all_orders.items():
                if isinstance(od, dict):
                    # Kiểm tra nếu order_id khớp với id hoặc một trường nào đó
                    if order_id.upper() == oid.upper():
                        order = od
                        order_id = oid
                        break
                    # Kiểm tra order_id trong các trường khác
                    if od.get("order_id") and order_id.upper() == str(od.get("order_id")).upper():
                        order = od
                        break
    
    if not order:
        logger.warning(f"=== QR SCAN: order not found for '{order_id}' ===")
        return jsonify({
            "success": False, 
            "message": f"Đơn hàng '{order_id}' không tồn tại!"
        }), 404
    
    logger.info(f"=== QR SCAN: found order {order_id}, status={order.get('status')} ===")
    
    # Trả về thông tin đơn hàng
    return jsonify({
        "success": True,
        "order_id": order_id,
        "customer_name": order.get("customerName", order.get("name", "Khách lẻ")),
        "total": float(order.get("total", 0) or 0),
        "status": order.get("status", "unknown"),
        "paymentStatus": order.get("paymentStatus", "Chưa thanh toán"),
        "date": order.get("date", ""),
        "items": order.get("details", order.get("items", []))
    })
