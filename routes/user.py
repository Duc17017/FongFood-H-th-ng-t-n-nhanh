import base64
import logging
import time
import uuid
from datetime import datetime

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

# --- AI GỢI Ý MÓN ĂN ---
def get_ai_recommendations(username, products):
    """AI gợi ý món ăn dựa trên thời gian và lịch sử"""
    from datetime import datetime
    import random
    
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
    
    # Lọc sản phẩm theo gợi ý
    recommendations = []
    for pid, p in products.items():
        score = 0
        name = p.get("name", "").lower()
        
        # Ưu tiên theo thời gian
        if time_category == "food" and any(x in name for x in ["com", "pho", "chao", "mi", "ga", "bo"]):
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
            recommendations.append((pid, p, score))
    
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
    
    return render_template("customer/home.html", hot_products=hot_products, ai_recommendations=ai_recommendations)


@customer_bp.route("/menu")
@login_required(role="customer")
def menu():
    cat = request.args.get("category") or request.args.get("q") or "all"
    search = request.args.get("search", "").lower()

    raw_products = db_get("products") or {}
    products = normalize_data(raw_products, "id")

    filtered_products = {}
    for pid, p in products.items():
        if cat != "all" and p.get("category") != cat:
            continue
        if search and search not in p.get("name", "").lower():
            continue
        filtered_products[pid] = p
    return render_template("customer/menu.html", products=filtered_products)

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
    raw_notifs = db_get(f'notifications/{session["user"]}') or []
    notifications = list(raw_notifs.values()) if isinstance(raw_notifs, dict) else raw_notifs

    return render_template("customer/notifications.html", notifications=notifications)

# --- ROUTE: XEM LỊCH SỬ ĐƠN HÀNG ---
@customer_bp.route("/history")
@login_required(role="customer")
def history():
    user = session["user"]
    raw_orders = db_get("orders") or {}
    all_orders = normalize_data(raw_orders, "id")

    my_orders = []
    for oid, order in all_orders.items():
        if order.get("user") == user:
            order = dict(order)
            order["id"] = oid
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

    user_info = get_user_db(user)
    return render_template("customer/cart.html", cart=display_cart, user=user_info)


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


@customer_bp.route("/add_to_cart/<pid>")
@login_required(role="customer")
def add_to_cart(pid):
    user = session["user"]

    raw_products = db_get("products") or {}
    products = normalize_data(raw_products, "id")
    product = products.get(pid)
    
    if product:
        raw_cart = db_get(f"carts/{user}") or {}
        user_cart = normalize_data(raw_cart, "id")

        if pid in user_cart:
            user_cart[pid]["qty"] += 1
        else:
            user_cart[pid] = {
                "name": product["name"],
                "price": product.get("price", 0),
                "qty": 1,
                "id": pid,
            }
        db_put(f"carts/{user}", user_cart)
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
    return render_template("customer/support.html")

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
def api_chat_process():
    data = request.json
    user_msg = data.get("message", "")

    time.sleep(1.5)
    
    bot_reply = get_ai_response(user_msg)
    return jsonify({"reply": bot_reply})

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
        
        # 2. Đếm thông báo (Fix lỗi List/Dict)
        raw_notifs = db_get("notifications") or {}
        notif_items = raw_notifs if isinstance(raw_notifs, list) else raw_notifs.values()
        
        if notif_items:
            for n in notif_items:
                if isinstance(n, dict):
                    if n.get("user") == user and not n.get("is_read"):
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
