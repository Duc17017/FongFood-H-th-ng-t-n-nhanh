import base64
import time
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, url_for, flash, redirect, jsonify

from decorators import admin_required
from services.analytics_service import analyze_business_data
from utils import db_get, db_put, db_patch


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

def normalize_data(data, key_field='id'):
    if isinstance(data, dict): return data
    if isinstance(data, list):
        res = {}
        for i, item in enumerate(data):
            if isinstance(item, dict):
                k = item.get(key_field, str(i))
                res[str(k)] = item
        return res
    return {}


def _send_notification(username, title, message, link="/", notif_type="system"):
    """Hàm gửi thông báo cho user"""
    import uuid
    notif_id = str(uuid.uuid4())
    notif = {
        "id": notif_id,
        "title": title,
        "message": message,
        "link": link,
        "time": datetime.now().strftime("%H:%M %d/%m"),
        "is_read": False,
        "type": notif_type,
    }

    # Lưu vào notifications/{username} - KHÔNG dùng cache
    existing = db_get(f"notifications/{username}", use_cache=False) or []
    if isinstance(existing, dict):
        existing[notif_id] = notif
    else:
        if not isinstance(existing, list):
            existing = []
        existing.append(notif)

    db_put(f"notifications/{username}", existing)

@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    time_filter = request.args.get("time", "week")

    raw_orders = db_get("orders") or {}
    orders = normalize_data(raw_orders, "id")
    raw_products = db_get("products") or {}
    products = normalize_data(raw_products, "id")

    report = analyze_business_data(orders, products, time_filter)
    revenue = report.get("revenue", 0)
    total = report.get("total_orders", 0)
    return render_template(
        "admin/dashboard.html",
        report=report,
        revenue=revenue,
        total=total,
        time_filter=time_filter,
    )


# Đăng ký thêm endpoint alias để tránh lỗi url_for cũ
admin_bp.add_url_rule("/dashboard", endpoint="admin_dashboard", view_func=dashboard)


@admin_bp.route("/stats")
@admin_required
def stats():
    time_filter = request.args.get("time", "week")
    raw_orders = db_get("orders") or {}
    orders = normalize_data(raw_orders, "id")

    # 1. Gọi hàm phân tích cũ (nếu có)
    try:
        from services.analytics_service import analyze_business_data
        data = analyze_business_data(orders, {}, time_filter)
    except:
        data = {}

    if not data:
        data = {}

    # Bổ sung các thông số bắt buộc nếu thiếu
    if 'status_counts' not in data:
        data['status_counts'] = {'pending':0, 'shipping':0, 'completed':0, 'cancelled':0}
        for o in orders.values():
            st = o.get('status')
            if st in data['status_counts']:
                data['status_counts'][st] += 1
                
    if 'total_orders' not in data:
        data['total_orders'] = len(orders)
        
    if 'revenue' not in data:
        data['revenue'] = sum(float(o.get('total', 0)) for o in orders.values() if o.get('status') == 'completed')

    # 2. TỰ ĐỘNG TÍNH TOP ĐỒ ĂN BÁN CHẠY NHẤT TỪ DATABASE
    product_stats = {}
    for oid, order in orders.items():
        if order.get('status') == 'completed':
            items = order.get('items') or order.get('details') or []
            for item in items:
                name = item.get('name', 'Khác')
                try:
                    qty = int(item.get('qty', 1))
                    price = float(item.get('price', 0))
                except:
                    qty = 1
                    price = 0
                
                if name not in product_stats:
                    product_stats[name] = {'name': name, 'sold': 0, 'revenue': 0}
                
                product_stats[name]['sold'] += qty
                product_stats[name]['revenue'] += (price * qty)
    
    # Sắp xếp lấy 5 món đồ ăn doanh thu cao nhất
    top_products = sorted(product_stats.values(), key=lambda x: x['revenue'], reverse=True)[:5]
    data['top_products'] = top_products

    return render_template("admin/stats.html", data=data, time_filter=time_filter)

# --- CÁC ROUTE CŨ (GIỮ NGUYÊN KHÔNG SỬA) ---
@admin_bp.route("/orders")
@admin_required
def orders():
    st = request.args.get("status", "all")
    target_user = request.args.get("user")

    raw_orders = db_get("orders") or {}
    orders = normalize_data(raw_orders, "id")

    lst = [{"id": k, **v} for k, v in orders.items()]

    if st != "all":
        lst = [o for o in lst if o.get("status") == st]

    if target_user:
        lst = [
            o
            for o in lst
            if o.get("user") == target_user or o.get("customer_id") == target_user
        ]

    try:
        lst.sort(
            key=lambda x: datetime.strptime(
                x.get("date", ""), "%H:%M %d/%m/%Y"
            ),
            reverse=True,
        )
    except: pass

    return render_template("admin/orders.html", orders=lst)


@admin_bp.route("/products", methods=["GET", "POST"])
@admin_required
def products():
    if request.method == "POST":
        pid = request.form.get("pid")
        data = {
            "name": request.form.get("name"),
            "price": float(request.form.get("price", 0)),
            "category": request.form.get("category"),
            "description": request.form.get("description"),
            "isPromoted": request.form.get("isPromoted") == "on",
        }
        f = request.files.get("image_file")
        if f and f.filename:
            try:
                b64 = base64.b64encode(f.read()).decode('utf-8')
                data["image"] = f"data:{f.content_type};base64,{b64}"
            except: pass
        elif request.form.get("image_base64"):
            data["image"] = request.form.get("image_base64")
             
        if pid: 
            curr = db_get(f"products/{pid}")
            if curr and "image" in curr and "image" not in data:
                data["image"] = curr["image"]
            db_patch(f"products/{pid}", data)
        else:
            import random

            db_put(f"products/p{random.randint(10000,99999)}", data)
        return redirect(url_for("admin.products"))

    raw_products = db_get("products") or {}
    products = normalize_data(raw_products, "id")
    cat = request.args.get("category", "all")
    return render_template("admin/products.html", products=products, cat=cat)

# --- ROUTE QUẢN LÝ KHÁCH HÀNG (NÂNG CẤP) ---
@admin_bp.route("/customers")
@admin_required
def customers():
    raw_users = db_get("users") or {}
    if isinstance(raw_users, list): 
        users = {u.get('username'): u for u in raw_users if u}
    else: 
        users = raw_users
    
    raw_orders = db_get("orders") or {}
    all_orders = normalize_data(raw_orders, "id")

    custs = []
    for username, u in users.items():
        if u.get("role") == "admin":
            continue

        user_orders = [
            o
            for o in all_orders.values()
            if o.get("user") == username or o.get("customer_id") == username
        ]

        total_spent = sum(
            float(o.get("total", 0))
            for o in user_orders
            if o.get("status") == "completed"
        )
        order_count = len(user_orders)
        last_order = (
            max([o.get("date") for o in user_orders]) if user_orders else "Chưa có"
        )

        rank = "Thành viên"
        if total_spent > 5_000_000:
            rank = "VIP Vàng"
        elif total_spent > 2_000_000:
            rank = "VIP Bạc"

        u["total_spent"] = total_spent
        u["order_count"] = order_count
        u["last_order"] = last_order
        u["rank"] = rank
        u["id"] = username
        
        custs.append(u)

    # Sắp xếp: Ai mua nhiều tiền nhất lên đầu
    custs.sort(key=lambda x: x["total_spent"], reverse=True)

    return render_template("admin/customers.html", customers=custs)


@admin_bp.route("/customer/delete/<username>")
@admin_required
def delete_customer(username):
    users = db_get("users") or {}

    if isinstance(users, list):
        new_users = [u for u in users if u.get("username") != username]
        db_put("users", new_users)
    elif isinstance(users, dict):
        if username in users:
            del users[username]
            db_put("users", users)

    flash(f"Đã xóa khách hàng {username} thành công!", "success")
    return redirect(url_for("admin.customers"))


@admin_bp.route("/update_status/<oid>/<status>")
@admin_required
def update_status(oid, status):
    if status in ["pending", "shipping", "completed", "cancelled"]:
        db_patch(f"orders/{oid}", {"status": status})
        flash("Đã cập nhật trạng thái đơn hàng!", "success")
    return redirect(url_for("admin.orders"))


@admin_bp.route("/product/delete/<pid>")
@admin_required
def delete_product(pid):
    raw = db_get("products") or {}
    products = normalize_data(raw, "id")
    if pid in products:
        del products[pid]
        db_put("products", products)
    return redirect(url_for("admin.products"))


@admin_bp.route("/api/generate_description", methods=["POST"])
def generate_ai_desc():
    name = request.json.get("name")
    return jsonify(
        {
            "description": f"Món {name} tuyệt ngon, đậm đà hương vị truyền thống."
        }
    )


# ==================== AI FRAUD DETECTION ====================
@admin_bp.route("/api/fraud-check", methods=["POST"])
@admin_required
def check_fraud():
    """
    AI Fraud Detection - Kiểm tra đơn hàng có bất thường không
    """
    try:
        data = request.json
        order = data.get("order", {})
        
        # Các yếu tố cần kiểm tra
        risk_score = 0
        risk_factors = []
        
        # 1. Tài khoản mới tinh (chưa có đơn nào)
        user = order.get("user")
        if user:
            raw_orders = db_get("orders") or {}
            user_orders = [o for o in raw_orders.values() if isinstance(o, dict) and o.get("user") == user]
            if len(user_orders) == 0:
                risk_score += 30
                risk_factors.append("Tài khoản mới chưa có đơn hàng nào")
        
        # 2. Đơn hàng lớn bất thường (> 1 triệu)
        total = float(order.get("total", 0))
        if total > 1000000:
            risk_score += 40
            risk_factors.append(f"Đơn hàng lớn ({total:,.0f}đ)")
        
        # 3. Thanh toán tiền mặt (COD) + đơn lớn
        payment = order.get("paymentMethod", "").lower()
        if "cod" in payment or "tiền mặt" in payment:
            if total > 500000:
                risk_score += 20
                risk_factors.append("Thanh toán COD với đơn > 500k")
        
        # 4. Nhiều món giống nhau trong 1 đơn
        items = order.get("items") or order.get("details") or []
        if items:
            item_names = [item.get("name", "").lower() for item in items]
            if len(item_names) != len(set(item_names)):
                risk_score += 15
                risk_factors.append("Có nhiều món giống nhau trong đơn")
        
        # Xác định mức độ rủi ro
        if risk_score >= 70:
            risk_level = "HIGH"
            recommendation = "Cần xác nhận qua điện thoại trước khi chế biến"
        elif risk_score >= 40:
            risk_level = "MEDIUM"
            recommendation = "Theo dõi đặc biệt, kiểm tra địa chỉ giao hàng"
        else:
            risk_level = "LOW"
            recommendation = "Đơn hàng bình thường, tiếp tục xử lý"
        
        return jsonify({
            "success": True,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "recommendation": recommendation,
            "needs_verification": risk_score >= 40
        })
        
    except Exception as e:
        logger.error(f"AI Fraud Check Error: {e}")
        return jsonify({"success": False, "message": "Lỗi kiểm tra fraud"}), 500


@admin_bp.route("/order/<oid>")
@admin_required
def order_detail(oid):
    order = db_get(f"orders/{oid}")

    if not order:
        flash("Đơn hàng không tồn tại", "error")
        return redirect(url_for("admin.orders"))

    return render_template(
        "admin/order_detail.html",
        order=order,
    )


@admin_bp.route("/profile")
@admin_required
def profile():
    """Trang hồ sơ admin (admin không lưu trong DB)."""
    admin_info = {"username": "admin", "name": "Admin", "role": "admin"}
    return render_template("admin/profile.html", user=admin_info)


@admin_bp.route("/chat")
@admin_required
def admin_chat():
    """Trang quản lý tin nhắn chat của khách hàng"""
    from routes.user import normalize_data
    
    raw_users = db_get("users") or {}
    if isinstance(raw_users, list):
        users = {u.get('username'): u for u in raw_users if u}
    else:
        users = raw_users
    
    # Lấy tất cả khách hàng có tin nhắn
    customers = []
    total_unread = 0
    
    for username, u in users.items():
        if u.get("role") == "admin":
            continue
        
        # Lấy chat history
        raw_chats = db_get(f"chats/{username}") or []
        chat_history = raw_chats if isinstance(raw_chats, list) else list(raw_chats.values()) if raw_chats else []
        
        # Đếm tin nhắn chưa đọc
        unread = sum(1 for m in chat_history if m.get("sender") == "user" and not m.get("is_read", False))
        total_unread += unread
        
        # Tin nhắn cuối cùng
        last_msg = chat_history[-1] if chat_history else None
        last_message = last_msg.get("message", "")[:50] if last_msg else ""
        last_time = ""
        if last_msg and last_msg.get("timestamp"):
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(last_msg["timestamp"])
                last_time = dt.strftime("%H:%M %d/%m")
            except:
                pass
        
        customers.append({
            "username": username,
            "name": u.get("name", username),
            "chat_history": chat_history[-20:],  # Lấy 20 tin gần nhất
            "unread": unread,
            "last_message": last_message,
            "last_time": last_time
        })
    
    # Sắp xếp: ai có tin nhắn mới lên đầu
    customers.sort(key=lambda x: (x["unread"], x["last_time"]), reverse=True)
    
    return render_template("admin/chat.html", customers=customers, total_unread=total_unread)


# ========== ADMIN CHAT API ==========
@admin_bp.route("/api/admin/save-chat", methods=["POST"])
@admin_required
def admin_save_chat():
    """Admin gửi tin nhắn cho khách"""
    data = request.json
    username = data.get("username")
    message = data.get("message")
    
    if not username or not message:
        return jsonify({"success": False, "message": "Thiếu thông tin"})
    
    # Lấy chat history hiện tại
    raw_chats = db_get(f"chats/{username}") or []
    chat_history = raw_chats if isinstance(raw_chats, list) else list(raw_chats.values()) if raw_chats else []
    
    # Thêm tin nhắn mới
    import uuid
    new_message = {
        "id": str(uuid.uuid4()),
        "message": message,
        "sender": "admin",
        "timestamp": datetime.now().isoformat(),
        # is_read = False để phía khách phát hiện là tin mới,
        # sau khi client đọc xong sẽ được đánh dấu True trong get_chat_updates
        "is_read": False
    }
    chat_history.append(new_message)
    
    db_put(f"chats/{username}", chat_history)
    
    return jsonify({"success": True})


@admin_bp.route("/api/admin/get-chat/<username>", methods=["GET"])
@admin_required
def admin_get_chat(username):
    """Admin lấy tin nhắn của khách"""
    raw_chats = db_get(f"chats/{username}") or []
    chat_history = raw_chats if isinstance(raw_chats, list) else list(raw_chats.values()) if raw_chats else []
    
    return jsonify({
        "success": True,
        "messages": chat_history[-50:]  # Lấy 50 tin gần nhất
    })


@admin_bp.route("/api/admin/mark-chat-read", methods=["POST"])
@admin_required
def admin_mark_chat_read():
    """Đánh dấu tin nhắn đã đọc"""
    data = request.json
    username = data.get("username")
    
    raw_chats = db_get(f"chats/{username}") or []
    chat_history = raw_chats if isinstance(raw_chats, list) else list(raw_chats.values()) if raw_chats else []
    
    for msg in chat_history:
        if msg.get("sender") == "user":
            msg["is_read"] = True
    
    db_put(f"chats/{username}", chat_history)
    
    return jsonify({"success": True})


@admin_bp.route("/api/admin/clear-chat", methods=["POST"])
@admin_required
def admin_clear_chat():
    """Xóa tin nhắn của khách"""
    data = request.json
    username = data.get("username")
    
    db_put(f"chats/{username}", [])
    
    return jsonify({"success": True})


@admin_bp.route("/send_voucher", methods=["GET", "POST"])
@admin_required
def send_voucher():
    """
    Gửi voucher cho toàn bộ khách hàng (hoặc một user cụ thể).
    Form submit từ modal trong trang customers.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Nếu truy cập trực tiếp bằng GET -> điều hướng về trang khách hàng, tránh 404 trắng
    if request.method == "GET":
        return redirect(url_for("admin.customers"))

    username = request.form.get("username", "all")
    code = (request.form.get("code") or "").strip().upper()
    try:
        discount = int(request.form.get("discount") or 0)
    except ValueError:
        discount = 0

    logger.info(f"=== SEND_VOUCHER: code={code}, discount={discount}, username={username} ===")

    if not code or discount <= 0:
        msg = "Mã voucher hoặc phần trăm giảm không hợp lệ."
        flash(msg, "error")
        # Return JSON for AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.form.get('ajax'):
            return jsonify({"success": False, "message": msg}), 400
        return redirect(url_for("admin.customers"))

    vouchers = db_get("vouchers") or {}
    if isinstance(vouchers, list):
        normalized = {}
        for v in vouchers:
            if isinstance(v, dict) and v.get("code"):
                normalized[v["code"]] = v
        vouchers = normalized

    expires_at = datetime.now() + timedelta(days=7)

    vouchers[code] = {
        "code": code,
        "discount": discount,
        "type": "percent",
        "min_order": 50000,
        "valid_until": expires_at.isoformat(),
        "user": username,  # 'all' hoặc 1 username cụ thể
        "reason": f"Admin campaign {code}",
        "created_at": datetime.now().isoformat(),
    }

    db_put("vouchers", vouchers)
    logger.info(f"=== SEND_VOUCHER: saved voucher = {vouchers[code]} ===")

    # Gửi thông báo cho user nhận voucher
    try:
        if username == "all":
            # Gửi cho tất cả users
            all_users = db_get("users") or {}
            if isinstance(all_users, dict):
                for user_key, user_data in all_users.items():
                    _send_notification(
                        user_key,
                        "🎁 Voucher mới!",
                        f"Bạn nhận được voucher giảm {discount}%! Mã: {code}. Đơn tối thiểu 50,000đ",
                        "/my-vouchers",
                        "voucher"
                    )
            logger.info(f"=== SEND_VOUCHER: Đã gửi thông báo cho tất cả users ===")
        else:
            # Gửi cho 1 user cụ thể
            _send_notification(
                username,
                "🎁 Voucher mới!",
                f"Bạn nhận được voucher giảm {discount}%! Mã: {code}. Đơn tối thiểu 50,000đ",
                "/my-vouchers",
                "voucher"
            )
            logger.info(f"=== SEND_VOUCHER: Đã gửi thông báo cho user {username} ===")
    except Exception as notify_err:
        logger.warning(f"Lỗi gửi thông báo voucher: {notify_err}")

    msg = f"Đã tạo voucher {code} giảm {discount}% cho khách hàng."
    flash(msg, "success")
    
    # Return JSON for AJAX
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.form.get('ajax'):
        return jsonify({"success": True, "message": msg, "redirect": url_for("admin.customers")})
    
    return redirect(url_for("admin.customers"))


@admin_bp.route("/reset_all", methods=["POST"])
@admin_required
def reset_all():
    """
    RESET TẤT CẢ DỮ LIỆU - XÓA SẠCH DATABASE
    """
    import requests
    
    firebase_url = "https://foodappdb-5fe2e-default-rtdb.firebaseio.com/.json"
    
    try:
        # Xóa tất cả các node chính
        nodes_to_clear = ["orders", "users", "vouchers", "carts", "addresses", "notifications", "reviews", "products"]
        
        for node in nodes_to_clear:
            url = f"https://foodappdb-5fe2e-default-rtdb.firebaseio.com/{node}.json"
            requests.delete(url)
        
        flash("Đã reset toàn bộ dữ liệu về 0! Database đã sạch.", "success")
    except Exception as e:
        flash(f"Lỗi khi reset: {str(e)}", "error")
    
    return redirect(url_for("admin.dashboard"))


# --------- RESTful API cho Mobile / Frontend khác ----------


@admin_bp.route("/api/products", methods=["GET"])
@admin_required
def api_products_list():
    """Trả về list sản phẩm dạng JSON (RESTful)."""
    raw_products = db_get("products") or {}
    products = normalize_data(raw_products, "id")
    return jsonify(
        [
            {"id": pid, **data}
            for pid, data in products.items()
            if isinstance(data, dict)
        ]
    )


@admin_bp.route("/api/products/<pid>", methods=["DELETE"])
@admin_required
def api_products_delete(pid):
    raw = db_get("products") or {}
    products = normalize_data(raw, "id")
    if pid not in products:
        return jsonify({"error": "Product not found"}), 404
    del products[pid]
    db_put("products", products)
    return jsonify({"status": "success"})


@admin_bp.route("/api/orders", methods=["GET"])
@admin_required
def api_orders_list():
    raw_orders = db_get("orders") or {}
    orders = normalize_data(raw_orders, "id")
    return jsonify(
        [
            {"id": oid, **data}
            for oid, data in orders.items()
            if isinstance(data, dict)
        ]
    )


@admin_bp.route("/api/orders/<oid>", methods=["PUT"])
@admin_required
def api_orders_update(oid):
    raw_orders = db_get("orders") or {}
    orders = normalize_data(raw_orders, "id")
    if oid not in orders:
        return jsonify({"error": "Order not found"}), 404

    payload = request.json or {}
    allowed_fields = {"status", "paymentStatus", "shippingNote"}
    update_data = {k: v for k, v in payload.items() if k in allowed_fields}
    if not update_data:
        return jsonify({"error": "No valid fields to update"}), 400

    db_patch(f"orders/{oid}", update_data)
    return jsonify({"status": "success", "updated": update_data})

