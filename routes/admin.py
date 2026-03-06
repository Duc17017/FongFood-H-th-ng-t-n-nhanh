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


@admin_bp.route("/qr-scan")
@admin_required
def admin_qr_scan():
    """
    Trang quét QR code dành cho Admin
    """
    return render_template("admin/qr_scan.html")


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

