import base64
import uuid
import json
import re
import time
import requests
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session
from utils import db_get, db_put, db_patch
import logging

# Thêm decorators cho API - đặt ở đầu file
def require_login(f):
    """Decorator đơn giản cho API"""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return jsonify({"success": False, "error": "Unauthorized", "message": "Vui lòng đăng nhập"}), 401
        return f(*args, **kwargs)
    return wrapper


def require_admin(f):
    """Decorator đơn giản cho admin API"""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return jsonify({"success": False, "error": "Unauthorized", "message": "Vui lòng đăng nhập"}), 401
        if session.get("role") != "admin":
            return jsonify({"success": False, "error": "Forbidden", "message": "Không có quyền"}), 403
        return f(*args, **kwargs)
    return wrapper


ai_bp = Blueprint("ai_v1", __name__)
logger = logging.getLogger(__name__)

# ==================== AI VOICE ORDERING ====================

@ai_bp.route("/voice-order", methods=["POST"])
@require_login
def ai_voice_order():
    """
    AI Voice Ordering - Xử lý đặt hàng bằng giọng nói
    Khách hàng nói: "Cho anh 2 bún bò nhiều thịt không hành và 1 trà đá ít đá đến 335 Cầu Giấy"
    AI tự động nhận diện món, số lượng, ghi chú và địa chỉ
    """
    try:
        data = request.json
        voice_text = data.get("text", "").strip()
        user = session["user"]

        if not voice_text:
            return jsonify({"success": False, "message": "Vui lòng nhập nội dung"}), 400

        # Gọi AI xử lý ngôn ngữ tự nhiên (simulated - có thể thay bằng Gemini/ChatGPT)
        order_data = process_voice_order(voice_text)

        if not order_data.get("items"):
            return jsonify({
                "success": False, 
                "message": "Không nhận diện được món ăn. Bạn vui lòng đặt qua menu nhé!"
            }), 400

        # Lưu vào giỏ hàng tạm thời
        temp_cart_id = str(uuid.uuid4())
        db_put(f"temp_cart/{temp_cart_id}", {
            "user": user,
            "items": order_data.get("items", []),
            "notes": order_data.get("notes", ""),
            "address": order_data.get("address", ""),
            "created_at": datetime.now().isoformat()
        })

        return jsonify({
            "success": True,
            "message": "Đã nhận diện đơn hàng!",
            "order_data": order_data,
            "temp_cart_id": temp_cart_id,
            "cart_items": order_data.get("items", []),
            "total": order_data.get("total", 0),
            "detected_address": order_data.get("address", ""),
            "detected_notes": order_data.get("notes", "")
        })

    except Exception as e:
        logger.error(f"AI Voice Order Error: {e}")
        return jsonify({"success": False, "message": "Lỗi xử lý giọng nói"}), 500


def process_voice_order(text):
    """Xử lý ngôn ngữ tự nhiên để trích xuất thông tin đơn hàng"""
    text = text.lower()
    
    # Lấy danh sách sản phẩm từ database
    raw_products = db_get("products") or {}
    products = {}
    if isinstance(raw_products, dict):
        for pid, p in raw_products.items():
            if isinstance(p, dict):
                products[pid] = p
                # Tạo từ khóa cho tìm kiếm
                p["keywords"] = p.get("name", "").lower()
    
    # Tìm kiếm món ăn trong text
    found_items = []
    detected_address = ""
    detected_notes = []
    
    # Các từ chỉ số lượng
    quantity_patterns = [
        (r'một|1', 1),
        (r'hai|2', 2),
        (r'ba|3', 3),
        (r'bốn|4', 4),
        (r'năm|5', 5),
        (r'sáu|6', 6),
        (r'bảy|7', 7),
        (r'tám|8', 8),
        (r'chín|9', 9),
        (r'mười|10', 10),
    ]
    
    # Các từ chỉ địa chỉ
    address_keywords = ["đến", "tại", "giao đến", "ship", "địa chỉ"]
    
    # Các từ chỉ ghi chú
    note_keywords = {
        "nhiều thịt": "nhiều thịt",
        "ít thịt": "ít thịt", 
        "không hành": "không hành",
        "ít hành": "ít hành",
        "nhiều hành": "nhiều hành",
        "không cay": "không cay",
        "ít cay": "ít cay",
        "nhiều cay": "nhiều cay",
        "ít đá": "ít đá",
        "nhiều đá": "nhiều đá",
        "không đá": "không đá",
        "đá riêng": "đá riêng",
        "nóng": "nóng",
        "lạnh": "lạnh",
        "ấm": "ấm",
    }
    
    # Tách text thành các phần
    parts = text.split("và")
    
    for part in parts:
        part = part.strip()
        quantity = 1
        
        # Tìm số lượng
        for pattern, num in quantity_patterns:
            if re.search(pattern, part):
                quantity = num
                break
        
        # Tìm địa chỉ
        for kw in address_keywords:
            if kw in part:
                idx = part.find(kw) + len(kw)
                detected_address = part[idx:].strip().strip(",.")
                break
        
        # Tìm ghi chú
        for note_kw, note_val in note_keywords.items():
            if note_kw in part:
                detected_notes.append(note_val)
        
        # Tìm sản phẩm
        best_match = None
        best_score = 0
        
        for pid, p in products.items():
            pname = p.get("name", "").lower()
            # Tìm kiếm theo từ khóa
            words = part.split()
            match_count = sum(1 for w in words if w in pname and len(w) > 2)
            
            if match_count > best_score:
                best_score = match_count
                best_match = {
                    "id": pid,
                    "name": p.get("name"),
                    "price": p.get("price", 0),
                    "quantity": quantity,
                    "notes": [n for n in detected_notes if n in part]
                }
        
        if best_match:
            found_items.append(best_match)
    
    # Tính tổng tiền
    total = sum(item.get("price", 0) * item.get("quantity", 1) for item in found_items)
    
    return {
        "items": found_items,
        "total": total,
        "address": detected_address,
        "notes": list(set(detected_notes))
    }


# ==================== AI SMART UPSELLING ====================

@ai_bp.route("/smart-upselling", methods=["GET"])
@require_login
def ai_smart_upselling():
    """
    AI Smart Upselling - Gợi ý chéo thông minh
    Khi khách bỏ "Gà rán" vào giỏ, AI gợi ý: "Trời đang mưa, thêm trà đào ấm và khoai tây chiên nhé!"
    """
    try:
        user = session["user"]
        
        # Lấy giỏ hàng hiện tại
        raw_cart = db_get(f"carts/{user}") or {}
        cart = raw_cart if isinstance(raw_cart, dict) else {}
        cart_items = list(cart.values()) if isinstance(cart, dict) else cart
        
        if not cart_items:
            return jsonify({"success": False, "message": "Giỏ hàng trống"}), 400
        
        # Lấy thời tiết hiện tại (simulated - có thể tích hợp weather API)
        weather = get_current_weather()
        
        # Lấy giờ trong ngày
        current_hour = datetime.now().hour
        
        # Lấy lịch sử mua hàng
        user_history = get_user_purchase_history(user)
        
        # Lấy danh sách sản phẩm
        raw_products = db_get("products") or {}
        products = raw_products if isinstance(raw_products, dict) else {}
        
        # AI phân tích và đề xuất
        suggestions = generate_smart_suggestions(cart_items, weather, current_hour, user_history, products)
        
        # Tạo thông điệp gợi ý
        message = generate_upsell_message(weather, current_hour, suggestions)
        
        return jsonify({
            "success": True,
            "message": message,
            "suggestions": suggestions,
            "weather": weather,
            "time_period": "sáng" if current_hour < 12 else ("trưa" if current_hour < 14 else ("chiều" if current_hour < 18 else "tối"))
        })
        
    except Exception as e:
        logger.error(f"AI Smart Upselling Error: {e}")
        return jsonify({"success": False, "message": "Lỗi AI gợi ý"}), 500


def get_current_weather():
    """Lấy thông tin thời tiết (simulated)"""
    # Trong thực tế, tích hợp OpenWeatherMap API
    hour = datetime.now().hour
    
    if 6 <= hour < 12:
        return {"condition": "sunny", "temp": 28, "description": "Trời nắng đẹp"}
    elif 12 <= hour < 14:
        return {"condition": "hot", "temp": 35, "description": "Trời nóng bức"}
    elif 14 <= hour < 18:
        return {"condition": "rainy", "temp": 25, "description": "Trời mưa rào"}
    else:
        return {"condition": "cool", "temp": 24, "description": "Trời mát mẻ"}


def get_user_purchase_history(user):
    """Lấy lịch sử mua hàng của khách"""
    raw_orders = db_get("orders") or {}
    orders = raw_orders if isinstance(raw_orders, dict) else {}
    
    user_orders = []
    for oid, order in orders.items():
        if isinstance(order, dict) and order.get("user") == user:
            user_orders.append(order)
    
    # Lấy các món đã mua
    purchased_items = set()
    for order in user_orders:
        items = order.get("items", [])
        for item in items:
            if isinstance(item, dict):
                purchased_items.add(item.get("name", ""))
    
    return {
        "total_orders": len(user_orders),
        "purchased_items": list(purchased_items)
    }


def generate_suggestions(cart_items, weather, current_hour, user_history, products):
    """Tạo danh sách gợi ý dựa trên context"""
    suggestions = []
    cart_names = [item.get("name", "").lower() for item in cart_items]
    
    # Mapping sản phẩm gợi ý theo điều kiện
    upsell_rules = {
        "gà": [
            {"name": "Khoai tây chiên", "category": "mon_phu", "reason": "ăn kèm gà rán"},
            {"name": "Trà đào", "category": "do_uong", "reason": "giải ngấy"},
            {"name": "Cola", "category": "do_uong", "reason": "uống với gà"},
        ],
        "bún": [
            {"name": "Trà đá", "category": "do_uong", "reason": "giải khát"},
        ],
        "phở": [
            {"name": "Chả", "category": "mon_phu", "reason": "thêm topping"},
        ],
        "combo": [
            {"name": "Trà đào", "category": "do_uong", "reason": "combo hoàn hảo"},
        ]
    }
    
    # Tìm sản phẩm phù hợp
    for cart_item in cart_items:
        item_name = cart_item.get("name", "").lower()
        
        for key, rules in upsell_rules.items():
            if key in item_name:
                for rule in rules:
                    # Tìm sản phẩm trong database
                    for pid, p in products.items():
                        if isinstance(p, dict) and rule["name"].lower() in p.get("name", "").lower():
                            # Kiểm tra điều kiện thời tiết
                            if weather.get("condition") == "rainy" and "ấm" in rule.get("reason", ""):
                                suggestions.append({
                                    "id": pid,
                                    "name": p.get("name"),
                                    "price": p.get("price"),
                                    "reason": f"Trời đang mưa, {rule['reason']} sẽ rất ngon!",
                                    "discount": 10
                                })
                            elif weather.get("condition") == "hot" and "lạnh" in rule.get("reason", ""):
                                suggestions.append({
                                    "id": pid,
                                    "name": p.get("name"),
                                    "price": p.get("price"),
                                    "reason": f"Trời nóng, uống {rule['name']} lạnh rất tuyệt!",
                                    "discount": 5
                                })
                            else:
                                suggestions.append({
                                    "id": pid,
                                    "name": p.get("name"),
                                    "price": p.get("price"),
                                    "reason": f"Thêm {rule['name']} {rule['reason']} nhé!",
                                    "discount": 0
                                })
    
    # Loại bỏ trùng lặp
    seen = set()
    unique_suggestions = []
    for s in suggestions:
        if s["id"] not in seen:
            seen.add(s["id"])
            unique_suggestions.append(s)
    
    return unique_suggestions[:5]


def generate_upsell_message(weather, current_hour, suggestions):
    """Tạo thông điệp gợi ý tự nhiên"""
    if not suggestions:
        return ""
    
    weather_desc = weather.get("description", "")
    
    if weather.get("condition") == "rainy":
        prefix = f"🌧️ Trời đang mưa ngoài kia, "
    elif weather.get("condition") == "hot":
        prefix = f"☀️ Trời nóng quá nhiệt nè, "
    elif current_hour >= 18:
        prefix = f"🌙 Buổi tối mát mẻ, "
    else:
        prefix = f"✨ "
    
    items_text = ", ".join([s["name"] for s in suggestions[:3]])
    discount_text = " giảm 10%" if any(s.get("discount", 0) > 0 for s in suggestions) else ""
    
    message = f"{prefix}thêm {items_text} vào đơn{discount_text} sẽ rất tuyệt đấy ạ!"
    
    return message


# ==================== AI VISUAL FOOD SEARCH ====================

@ai_bp.route("/visual-search", methods=["POST"])
@require_login
def ai_visual_search():
    """
    AI Visual Food Search - Tìm món bằng hình ảnh
    Khách chụp ảnh món ăn trên Tiktok, AI quét và nhận diện món
    """
    try:
        data = request.json
        image_base64 = data.get("image")

        if not image_base64:
            return jsonify({"success": False, "message": "Vui lòng gửi hình ảnh"}), 400

        # Gọi AI vision để nhận diện món ăn (simulated - có thể dùng Google Cloud Vision)
        food_result = analyze_food_image(image_base64)

        if not food_result:
            return jsonify({
                "success": False, 
                "message": "Không nhận diện được món ăn. Bạn thử chụp rõ hơn nhé!"
            }), 400

        # Tìm sản phẩm tương tự trong menu
        similar_products = find_similar_products(food_result.get("name", ""))

        return jsonify({
            "success": True,
            "detected_food": food_result,
            "similar_products": similar_products,
            "message": f"Đây có vẻ là {food_result.get('name')}. Quán đang có món này giá {food_result.get('price', 0)}k!"
        })

    except Exception as e:
        logger.error(f"AI Visual Search Error: {e}")
        return jsonify({"success": False, "message": "Lỗi nhận diện hình ảnh"}), 500


def analyze_food_image(image_base64):
    """Phân tích hình ảnh để nhận diện món ăn (simulated)"""
    # Trong thực tế, tích hợp Google Cloud Vision API hoặc AWS Rekognition
    # Đây là code mẫu simulation
    
    # Danh sách món ăn phổ biến để matching
    known_foods = {
        "gà rán": {"name": "Gà rán giòn", "category": "ga", "estimated_price": 55000},
        "gà nướng": {"name": "Gà nướng", "category": "ga", "estimated_price": 65000},
        "bún bò": {"name": "Bún bò", "category": "bun", "estimated_price": 45000},
        "phở": {"name": "Phở bò", "category": "bun", "estimated_price": 50000},
        "bánh mì": {"name": "Bánh mì", "category": "mon_phu", "estimated_price": 25000},
        "khoai": {"name": "Khoai tây chiên", "category": "mon_phu", "estimated_price": 25000},
        "trà đào": {"name": "Trà đào", "category": "do_uong", "estimated_price": 20000},
        "cà phê": {"name": "Cà phê", "category": "do_uong", "estimated_price": 25000},
        "sinh tố": {"name": "Sinh tố", "category": "do_uong", "estimated_price": 30000},
        "mì": {"name": "Mì tôm", "category": "bun", "estimated_price": 30000},
    }
    
    # Simulated - trong thực tế sẽ gọi AI vision API
    import random
    detected = random.choice(list(known_foods.values()))
    detected["confidence"] = random.uniform(0.75, 0.98)
    detected["description"] = f"Món {detected['name']} hấp dẫn, đậm đà hương vị"
    
    return detected

def find_similar_products(food_name):
    """Tìm sản phẩm tương tự trong menu"""
    raw_products = db_get("products") or {}
    products = raw_products if isinstance(raw_products, dict) else {}
    
    similar = []
    search_terms = food_name.lower().split()
    
    for pid, p in products.items():
        if not isinstance(p, dict):
            continue
        
        pname = p.get("name", "").lower()
        if any(term in pname for term in search_terms):
            similar.append({
                "id": pid,
                "name": p.get("name"),
                "price": p.get("price"),
                "image": p.get("image"),
                "category": p.get("category")
            })
    
    return similar[:5]


# ==================== AI CHATBOT CSKH 24/7 ====================

@ai_bp.route("/chatbot", methods=["POST"])
@require_login
def ai_chatbot():
    """
    AI Chatbot CSKH 24/7 - Trả lời tự động như nhân viên thật
    """
    try:
        data = request.json
        user_message = data.get("message", "").strip()
        user = session["user"]

        if not user_message:
            return jsonify({"success": False, "message": "Vui lòng nhập tin nhắn"}), 400

        # Xử lý AI response
        response = get_ai_chatbot_response(user_message, user)

        return jsonify({
            "success": True,
            "reply": response.get("message"),
            "quick_replies": response.get("quick_replies", []),
            "suggested_actions": response.get("suggested_actions", [])
        })

    except Exception as e:
        logger.error(f"AI Chatbot Error: {e}")
        return jsonify({"success": False, "message": "Xin lỗi, có lỗi xảy ra. Vui lòng thử lại sau."}), 500


def get_ai_chatbot_response(message, user):
    """AI xử lý tin nhắn và trả lời thông minh"""
    message = message.lower()
    
    # Lấy thông tin user
    users = db_get("users") or {}
    user_data = users.get(user) if isinstance(users, dict) else None
    
    # Lấy đơn hàng gần nhất
    raw_orders = db_get("orders") or {}
    orders = raw_orders if isinstance(raw_orders, dict) else {}
    
    user_orders = []
    for oid, order in orders.items():
        if isinstance(order, dict) and order.get("user") == user:
            order["id"] = oid
            user_orders.append(order)
    
    # Sắp xếp theo thời gian
    user_orders.sort(key=lambda x: x.get("date", ""), reverse=True)
    last_order = user_orders[0] if user_orders else None
    
    # Xử lý theo kịch bản
    response = {"message": "", "quick_replies": [], "suggested_actions": []}
    
    # 1. Chào hỏi
    if any(x in message for x in ['hi', 'chào', 'hello', 'alo', 'xin chào', 'bắt đầu']):
        response["message"] = (
            "Dạ chào anh/chị! 👋 Cảm ơn anh/chị đã nhắn tin cho Fong Food.\n\n"
            "Em là trợ lý AI 24/7, rất vui được hỗ trợ anh/chị.\n\n"
            "Anh/chị đang cần em giúp gì ạ?"
        )
        response["quick_replies"] = ["📋 Xem đơn hàng", "🍔 Xem menu", "📞 Liên hệ support"]
        response["suggested_actions"] = [
            {"type": "link", "label": "Xem menu", "url": "/menu"},
            {"type": "link", "label": "Đơn hàng của tôi", "url": "/history"}
        ]
    
    # 2. Hỏi về đơn hàng
    elif any(x in message for x in ['đơn hàng', 'đơn của tôi', 'bao giờ', 'chưa nhận', 'ship', 'giao']):
        if last_order:
            status = last_order.get("status", "unknown")
            status_text = {
                "pending": "đang chờ xác nhận",
                "shipping": "đang được giao",
                "completed": "đã hoàn thành",
                "cancelled": "đã bị hủy"
            }.get(status, "đang xử lý")
            
            response["message"] = (
                f"Dạ, em đã kiểm tra cho anh/chị rồi ạ!\n\n"
                f"📦 Đơn hàng #{last_order.get('id')} của anh/chị hiện đang **{status_text}**.\n"
                f"⏰ Thời gian đặt: {last_order.get('date')}\n"
                f"💰 Tổng tiền: {last_order.get('total', 0):,.0f}đ\n\n"
            )
            
            if status == "shipping":
                response["message"] += "🚴 Shipper đang trên đường, anh/chị vui lòng đợi nhé!"
            elif status == "pending":
                response["message"] += "⏳ Đơn hàng đang được nhà bếp chuẩn bị, khoảng 15-20 phút nữa sẽ giao ạ!"
            
            response["quick_replies"] = ["📋 Chi tiết đơn", "❌ Hủy đơn", "🏠 Trang chủ"]
            response["suggested_actions"] = [
                {"type": "link", "label": "Xem chi tiết", "url": f"/order/{last_order.get('id')}"}
            ]
        else:
            response["message"] = (
                "Dạ anh/chị chưa có đơn hàng nào trong hệ thống ạ.\n\n"
                "Anh/chị muốn đặt món gì hôm nay? Em có thể giới thiệu menu hoặc anh/chị có thể xem menu trực tiếp!"
            )
            response["quick_replies"] = ["🍔 Xem menu", "🎁 Khuyến mãi"]
    
    # 3. Hỏi về món ăn/menu
    elif any(x in message for x in ['menu', 'món', 'ăn', 'gì', 'có', 'bán']):
        response["message"] = (
            "Dạ, Fong Food có rất nhiều món ngon anh/chị ạ! 🍔\n\n"
            "📋 Các danh mục:\n"
            "• 🍗 Gà các loại\n"
            "• 🍜 Bún/Phở\n"
            "• 🥤 Đồ uống\n"
            "• 🍟 Món phụ\n\n"
            "Anh/chị muốn xem món nào cụ thể hoặc em gợi ý món hot nhất hôm nay?"
        )
        response["quick_replies"] = ["🔥 Món hot", "🍗 Gà", "🍜 Bún/Phở", "🥤 Đồ uống"]
        response["suggested_actions"] = [
            {"type": "link", "label": "Xem full menu", "url": "/menu"}
        ]
    
    # 4. Hỏi về thanh toán
    elif any(x in message for x in ['thanh toán', 'tiền', 'mã giảm', 'voucher', 'coupon', 'giảm giá']):
        response["message"] = (
            "Dạ về thanh toán và khuyến mãi anh/chị nhé! 💰\n\n"
            "📱 Các hình thức thanh toán:\n"
            "• Tiền mặt (COD)\n"
            "• QR Code (Momo, VNPay, ZaloPay)\n\n"
            "🎫 Mã giảm giá đang có:\n"
            "• NEWUSER: Giảm 20% đơn đầu\n"
            "• FREESHIP: Miễn phí giao hàng\n"
            "• FONGFOOD: Giảm 15%\n\n"
        )
        response["quick_replies"] = ["📱 Thanh toán QR", "🎫 Nhập mã giảm giá"]
    
    # 5. Hỏi về tài khoản
    elif any(x in message for x in ['tài khoản', 'điểm', 'thành viên', 'rank', 'hạng']):
        if user_data:
            points = user_data.get("points", 0)
            rank = user_data.get("rank", "Đồng")
            total_spent = user_data.get("total_spent", 0)
            
            response["message"] = (
                f"Thông tin tài khoản của anh/chị: 💳\n\n"
                f"⭐ Hạng thành viên: **{rank}**\n"
                f"🎯 Điểm tích lũy: **{points} điểm**\n"
                f"💵 Tổng chi tiêu: **{total_spent:,.0f}đ**\n\n"
            )
            
            if rank == "Đồng":
                next_rank = "Bạc"
                next_spent = 2_000_000
            elif rank == "Bạc":
                next_rank = "Vàng"
                next_spent = 5_000_000
            elif rank == "Vàng":
                next_rank = "Kim Cương"
                next_spent = 10_000_000
            else:
                next_rank = None
                next_spent = 0
            
            if next_rank:
                remaining = next_spent - total_spent
                response["message"] += f"📈 Lên {next_rank} chỉ cần thêm {remaining:,.0f}đ nữa thôi!"
            
            response["quick_replies"] = ["🎁 Đổi điểm", "📋 Lịch sử đơn"]
        
    # 6. Phàn nàn/khiếu nại
    elif any(x in message for x in ['tệ', 'dở', 'chậm', 'nhầm', 'lỗi', 'khiếu nại', 'phàn nàn']):
        response["message"] = (
            "Dạ em rất tiếc khi nghe anh/chị phản hồi như vậy ạ. 😢\n\n"
            "Fong Food rất trân trọng ý kiến của anh/chị.\n"
            "Em đã ghi nhận và chuyển phản hồi đến quản lý ngay.\n\n"
            "Anh/chị có thể cho em biết chi tiết vấn đề để em hỗ trợ tốt hơn không ạ?"
        )
        response["quick_replies"] = ["📞 Gọi hotline", "💬 Chat với nhân viên"]
        response["suggested_actions"] = [
            {"type": "action", "label": "Báo cáo vấn đề", "action": "report_issue"}
        ]
    
    # 7. Khen ngợi
    elif any(x in message for x in ['ngon', 'tuyệt', 'tốt', 'thích', 'hài lòng', 'đẹp']):
        response["message"] = (
            "Woa, cảm ơn anh/chị rất nhiều! 🥰\n\n"
            "Đội ngũ Fong Food rất vui khi anh/chị hài lòng với dịch vụ.\n"
            "Anh/chị nhớ đánh giá 5 sao và giới thiệu cho bạn bè nhé!\n\n"
            "Hôm nay anh/chị có muốn đặt thêm món gì không ạ?"
        )
        response["quick_replies"] = ["🍔 Đặt thêm", "🎁 Xem khuyến mãi"]
    
    # 8. Hỏi về địa chỉ
    elif any(x in message for x in ['địa chỉ', 'ở đâu', 'mấy giờ', 'mở cửa', 'đóng cửa']):
        response["message"] = (
            "Dạ thông tin cửa hàng Fong Food: 📍\n\n"
            "🏠 Địa chỉ: 335 Cầu Giấy, Hà Nội\n"
            "🕐 Giờ mở cửa: 8:00 - 22:00 (tất cả các ngày)\n"
            "📞 Hotline: 1900-xxxx\n\n"
            "Ngoài ra, Fong Food còn giao hàng tận nơi qua app với phí ship rẻ nhất!"
        )
        response["quick_replies"] = ["🚴 Tính phí ship", "🗺️ Xem bản đồ"]
    
    # Mặc định
    else:
        response["message"] = (
            "Dạ, em là AI nên đôi khi chưa hiểu rõ ý anh/chị lắm ạ. 😅\n\n"
            "Nhưng đừng lo, em sẽ chuyển tin nhắn này đến đội ngũ CSKH.\n"
            "Nhân viên sẽ phản hồi trong vòng 5 phút!\n\n"
            "Trong lúc chờ, anh/chị có thể xem menu hoặc các khuyến mãi hiện có:"
        )
        response["quick_replies"] = ["🍔 Xem menu", "🎁 Khuyến mãi", "📋 Đơn hàng của tôi"]
    
    return response


# ==================== AI INVENTORY FORECAST ====================

@ai_bp.route("/inventory-forecast", methods=["GET"])
def ai_inventory_forecast():
    """
    AI Inventory Forecast - Dự đoán nhập hàng
    Phân tệu để báo cáo: "Cuích dữ liối tuần này mưa lạnh, nên nhập thêm 50kg Gà"
    """
    try:
        # Lấy dữ liệu đơn hàng
        raw_orders = db_get("orders") or {}
        orders = raw_orders if isinstance(raw_orders, dict) else {}
        
        # Lấy dữ liệu sản phẩm
        raw_products = db_get("products") or {}
        products = raw_products if isinstance(raw_products, dict) else {}
        
        # Phân tích xu hướng
        forecast = analyze_inventory_forecast(orders, products)
        
        return jsonify({
            "success": True,
            "forecast": forecast,
            "generated_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"AI Inventory Forecast Error: {e}")
        return jsonify({"success": False, "message": "Lỗi dự đoán tồn kho"}), 500


def analyze_inventory_forecast(orders, products):
    """Phân tích và dự báo tồn kho"""
    from collections import defaultdict
    
    # Thống kê bán hàng theo danh mục
    category_sales = defaultdict(int)
    product_sales = defaultdict(int)
    
    for oid, order in orders.items():
        if not isinstance(order, dict):
            continue
        
        items = order.get("items", [])
        for item in items:
            if isinstance(item, dict):
                name = item.get("name", "")
                qty = item.get("qty", 0)
                
                # Tìm category
                category = "Khác"
                for pid, p in products.items():
                    if isinstance(p, dict) and p.get("name") == name:
                        category = p.get("category", "Khác")
                        break
                
                category_sales[category] += qty
                product_sales[name] += qty
    
    # Lấy thông tin thời tiết dự báo (simulated)
    weather_forecast = get_weather_forecast()
    
    # Đưa ra khuyến nghị
    recommendations = []
    
    # Dựa trên thời tiết
    if weather_forecast.get("weekend") == "rainy":
        recommendations.append({
            "type": "increase",
            "item": "Gà",
            "quantity": "30-50 kg",
            "reason": "Cuối tuần dự báo mưa, khách thường order gà ăn tại nhà nhiều hơn"
        })
        recommendations.append({
            "type": "increase",
            "item": " Bia/Nước ngọt",
            "quantity": "20-30 thùng",
            "reason": "Mưa + xem bóng đá = tăng tiêu thụ đồ uống"
        })
        recommendations.append({
            "type": "decrease",
            "item": "Bún/Phở",
            "quantity": "giảm 20%",
            "reason": "Trời mưa lạnh, khách ít ăn đồ lạnh"
        })
    
    # Dựa trên xu hướng
    if category_sales.get("ga", 0) > category_sales.get("bun", 0):
        recommendations.append({
            "type": "increase",
            "item": "Gà các loại",
            "quantity": "tăng 15%",
            "reason": "Tuần này gà bán chạy hơn bún 30%"
        })
    
    # Top sản phẩm bán chạy
    top_products = sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return {
        "weather_forecast": weather_forecast,
        "category_sales": dict(category_sales),
        "top_products": [{"name": k, "qty": v} for k, v in top_products],
        "recommendations": recommendations,
        "summary": f"Dự báo cuối tuần: {weather_forecast.get('description', 'bình thường')}"
    }


def get_weather_forecast():
    """Lấy dự báo thời tiết (simulated)"""
    # Trong thực tế, tích hợp weather API
    import random
    
    weekend_conditions = ["sunny", "rainy", "cloudy"]
    condition = random.choice(weekend_conditions)
    
    return {
        "weekend": condition,
        "temp": "20-28°C",
        "description": "Mưa rào vào Thứ 7, Chủ nhật nắng nhẹ" if condition == "rainy" else "Nắng đẹp cuối tuần",
        "humidity": "75%"
    }


# ==================== AI DYNAMIC PRICING ====================

@ai_bp.route("/dynamic-pricing", methods=["GET"])
def ai_dynamic_pricing():
    """
    AI Dynamic Pricing - Định giá tự động theo thời gian thực
    Giống Grab/Uber: cao điểm tăng giá, thấp điểm giảm giá
    """
    try:
        # Lấy dữ liệu đơn hàng gần đây
        raw_orders = db_get("orders") or {}
        orders = raw_orders if isinstance(raw_orders, dict) else {}
        
        # Phân tích và đề xuất giá
        pricing = analyze_dynamic_pricing(orders)
        
        return jsonify({
            "success": True,
            "pricing": pricing,
            "generated_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"AI Dynamic Pricing Error: {e}")
        return jsonify({"success": False, "message": "Lỗi phân tích giá"}), 500


def analyze_dynamic_pricing(orders):
    """Phân tích và đề xuất giá động"""
    from collections import defaultdict
    
    # Thống kê đơn hàng theo giờ
    hourly_orders = defaultdict(int)
    hourly_revenue = defaultdict(float)
    
    for oid, order in orders.items():
        if not isinstance(order, dict):
            continue
        
        date_str = order.get("date", "")
        try:
            # Parse thời gian
            if " " in date_str:
                time_part = date_str.split()[0]
                hour = int(time_part.split(":")[0])
                
                hourly_orders[hour] += 1
                hourly_revenue[hour] += order.get("total", 0)
        except:
            continue
    
    # Xác định giờ cao điểm
    current_hour = datetime.now().hour
    
    peak_hours = []
    off_peak_hours = []
    
    for hour in range(8, 22):
        order_count = hourly_orders.get(hour, 0)
        
        if hour in [11, 12, 13, 18, 19, 20]:
            peak_hours.append(hour)
        elif hour in [14, 15, 16]:
            off_peak_hours.append(hour)
    
    # Tính toán multiplier
    current_load = hourly_orders.get(current_hour, 0)
    max_load = max(hourly_orders.values()) if hourly_orders else 10
    
    if max_load == 0:
        max_load = 10
    
    load_ratio = current_load / max_load
    
    if load_ratio > 0.8:
        price_multiplier = 1.15  # Tăng 15%
        status = "peak"
        status_text = "Ca cao điểm - Giá tăng"
        message = "Hiện tại đang cao điểm, giá món có thể tăng 5-15%"
    elif load_ratio < 0.3:
        price_multiplier = 0.9  # Giảm 10%
        status = "off_peak"
        status_text = "Ca thấp điểm - Khuyến mãi"
        message = "Quán đang vắng, áp dụng giảm giá để kích cầu"
    else:
        price_multiplier = 1.0
        status = "normal"
        status_text = "Bình thường"
        message = "Lượng khách ổn định, giá bình thường"
    
    # Đề xuất flash sale nếu cần
    suggestions = []
    
    if status == "off_peak":
        suggestions.append({
            "type": "flash_sale",
            "title": "Flash Sale 3h chiều",
            "discount": "15-20%",
            "time": "14:00 - 17:00",
            "reason": "Kích cầu giờ thấp điểm"
        })
    
    if load_ratio > 0.9:
        suggestions.append({
            "type": "surcharge",
            "title": "Phí cao điểm",
            "amount": "5-10%",
            "reason": "Quá đông khách"
        })
    
    return {
        "status": status,
        "status_text": status_text,
        "message": message,
        "price_multiplier": price_multiplier,
        "current_hour": current_hour,
        "current_load": current_load,
        "max_load": max_load,
        "suggestions": suggestions,
        "hourly_stats": {str(h): {"orders": hourly_orders[h], "revenue": hourly_revenue[h]} 
                        for h in range(8, 22)}
    }


# ==================== AI REVIEW SENTIMENT ====================

@ai_bp.route("/review-sentiment", methods=["POST"])
def ai_review_sentiment():
    """
    AI Review Sentiment - Phân tích đánh giá
    Nếu khách đánh giá 1 sao và viết "Đồ ăn bị chua", AI tự động gửi xin lỗi, đền bù voucher
    """
    try:
        data = request.json
        review_text = data.get("review", "")
        rating = data.get("rating", 5)
        order_id = data.get("order_id")
        user = data.get("user")

        if not review_text:
            return jsonify({"success": False, "message": "Vui lòng nhập đánh giá"}), 400

        # Phân tích cảm xúc
        sentiment = analyze_review_sentiment(review_text, rating)
        
        actions_taken = []
        
        # Nếu là đánh giá tiêu cực, thực hiện các hành động tự động
        if sentiment["sentiment"] == "negative" and rating <= 2:
            # Gửi xin lỗi tự động
            actions_taken.append("sent_apology")
            
            # Tạo voucher đền bù
            voucher_code = f"SORRY{str(uuid.uuid4())[:6].upper()}"
            vouchers = db_get("vouchers") or {}
            
            vouchers[voucher_code] = {
                "code": voucher_code,
                "discount": 20,
                "type": "percent",
                "min_order": 50000,
                "valid_until": (datetime.now() + timedelta(days=7)).isoformat(),
                "user": user,
                "reason": f"Đền bù đánh giá {rating} sao: {review_text[:50]}",
                "created_at": datetime.now().isoformat()
            }
            db_put("vouchers", vouchers)
            actions_taken.append(f"created_voucher_{voucher_code}")
            
            # Gửi thông báo cho admin nếu nghiêm trọng
            if any(word in review_text.lower() for word in ["chua", "hỏng", "ôi", "thiu", "bệnh"]):
                # Gửi alert cho admin
                admin_notif = {
                    "id": str(uuid.uuid4()),
                    "title": "⚠️ Cảnh báo chất lượng",
                    "message": f"Khách {user} đánh giá 1 sao: '{review_text}'. Có thể có vấn đề về nguyên liệu!",
                    "type": "warning",
                    "is_read": False,
                    "created_at": datetime.now().isoformat()
                }
                
                raw_notifs = db_get("notifications/admin") or []
                notifs = raw_notifs if isinstance(raw_notifs, list) else []
                notifs.insert(0, admin_notif)
                db_put("notifications/admin", notifs)
                
                actions_taken.append("alert_admin")

        return jsonify({
            "success": True,
            "sentiment": sentiment,
            "actions_taken": actions_taken,
            "message": "Cảm ơn đánh giá của quý khách!"
        })

    except Exception as e:
        logger.error(f"AI Review Sentiment Error: {e}")
        return jsonify({"success": False, "message": "Lỗi phân tích đánh giá"}), 500


def analyze_review_sentiment(review_text, rating):
    """Phân tích cảm xúc đánh giá"""
    text = review_text.lower()
    
    # Từ khóa tích cực
    positive_words = ["ngon", "tuyệt", "tốt", "thích", "hài lòng", " tuyệt vời", "đỉnh", "chuẩn", "ngon"]
    
    # Từ khóa tiêu cực
    negative_words = ["dở", "tệ", "chua", "hỏng", "ôi", "thiu", "bệnh", "chậm", "nhầm", "không ngon", "thất vọng"]
    
    # Từ khóa cảnh báo (cần alert admin)
    warning_words = ["chua", "hỏng", "ôi", "thiu", "bệnh", "ngộ độc"]
    
    positive_count = sum(1 for word in positive_words if word in text)
    negative_count = sum(1 for word in negative_words if word in text)
    warning_count = sum(1 for word in warning_words if word in text)
    
    # Xác định sentiment
    if rating >= 4 or positive_count > negative_count:
        sentiment = "positive"
        emoji = "😊"
    elif rating <= 2 or negative_count > positive_count:
        sentiment = "negative"
        emoji = "😞"
    else:
        sentiment = "neutral"
        emoji = "😐"
    return {
        "sentiment": sentiment,
        "emoji": emoji,
        "positive_score": positive_count,
        "negative_score": negative_count,
        "warning_detected": warning_count > 0,
        "keywords_found": {
            "positive": [w for w in positive_words if w in text],
            "negative": [w for w in negative_words if w in text],
            "warning": [w for w in warning_words if w in text]
        }
    }


# ==================== AI AUTO-MARKETING ====================

@ai_bp.route("/auto-marketing", methods=["POST"])
def ai_auto_marketing():
    """
    AI Auto-Marketing - Tự động tạo content marketing
    Admin up 1 tấm ảnh món ăn, AI tự tạo caption, đăng Facebook/Tiktok
    """
    try:
        data = request.json
        image_base64 = data.get("image")
        product_id = data.get("product_id")

        if not image_base64 and not product_id:
            return jsonify({"success": False, "message": "Cần cung cấp ảnh hoặc product_id"}), 400

        # Lấy thông tin sản phẩm
        product = None
        if product_id:
            product = db_get(f"products/{product_id}")
            if not product:
                return jsonify({"success": False, "message": "Sản phẩm không tồn tại"}), 404

        # Tạo content tự động
        marketing_content = generate_marketing_content(product, image_base64)

        return jsonify({
            "success": True,
            "content": marketing_content
        })

    except Exception as e:
        logger.error(f"AI Auto-Marketing Error: {e}")
        return jsonify({"success": False, "message": "Lỗi tạo content"}), 500


def generate_marketing_content(product, image_base64):
    """Tạo nội dung marketing tự động"""
    import random
    
    if not product:
        product_name = "Món ăn ngon"
        price = 0
    else:
        product_name = product.get("name", "Món ăn")
        price = product.get("price", 0)
    
    # Các caption gợi ý
    caption_templates = [
        "🔥 {name} - Đậm đà hương vị! \n\n"
        "Thơm lừng, giòn rụm - đảm bảo ăn là ghiền!\n\n"
        "📦 Đặt ngay: Fong Food\n"
        "📍 335 Cầu Giấy\n"
        "#FongFood #AnhChị #MonNgon",
        
        "🍔 {name} cực ngon đây! \n\n"
        "Nhà mình làm fresh mỗi ngày, đảm bảo chất lượng!\n"
        "Ai thèm thì nhắn Fong Food nhé 😋\n\n"
        "#FongFood #Foodie #HanoiFood",
        
        " ⭐ Review5 sao cho {name} của Fong Food!\n\n"
        "Khách khen nức nở: 'Ngon như ở nhà mẹ nấu!'\n"
        "Đặt liền kẻo hết hot! 🔥\n\n"
        "#FongFood #Review #MonNgon",
        
        "🌟 {name} - Món 'must-try' tại Fong Food!\n\n"
        "Combo tiết kiệm, ăn no bụng!\n"
        "Giao hàng nhanh trong 30 phút 🚀\n\n"
        "Call: 1900-xxxx\n"
        "#FongFood #GiaoHang #Hanoi",
    ]
    
    # Hashtags bổ sung
    hashtag_sets = [
        ["#FongFood", "#AnViet", "#HanoiFood", "#FoodBlog"],
        ["#MonNgon", "#DoAnVat", "#Foodie", "#Yummy"],
        ["#AnToanVeSinh", "#ChatLuong", "#HangDau", "#VN_Food"],
    ]
    
    # Tạo caption
    caption = random.choice(caption_templates).format(name=product_name)
    hashtags = " ".join(random.choice(hashtag_sets))
    caption += f"\n\n{hashtags}"
    
    # Tạo kịch bản Tiktok
    tiktok_scripts = [
        {
            "duration": 15,
            "scenes": [
                {"time": "0-3s", "text": f"🍜 {product_name} Fong Food đây! 🔥", "action": "Show food"},
                {"time": "3-8s", "text": "Đậm đà, thơm nức mũi!", "action": "Zoom in"},
                {"time": "8-12s", "text": "Đặt ngay ở link bio!", "action": "Point to camera"},
                {"time": "12-15s", "text": "#FongFood #Foodie", "action": "End screen"}
            ],
            "music_suggestion": "Nhạc trending, beat nhanh"
        },
        {
            "duration": 30,
            "scenes": [
                {"time": "0-5s", "text": f"Review {product_name} siêu ngon!", "action": "Unbox"},
                {"time": "5-15s", "text": "Thử ăn ngay...", "action": "Eat"},
                {"time": "15-25s", "text": "Tuyệt vời! 10/10!", "action": "React"},
                {"time": "25-30s", "text": "Đặt ngay Fong Food nhé!", "action": "Call to action"}
            ],
            "music_suggestion": "Nhạc nền vui nhộn"
        }
    ]
    
    # Tạo đề xuất đăng
    posts = [
        {
            "platform": "Facebook",
            "content": caption,
            "suggested_time": "12:00 - 13:00 (giờ vàng)",
            "hashtags": hashtag_sets[0]
        },
        {
            "platform": "Instagram",
            "content": caption[:2200],  # IG giới hạn
            "suggested_time": "18:00 - 20:00",
            "hashtags": hashtag_sets[1]
        },
        {
            "platform": "Tiktok",
            "script": random.choice(tiktok_scripts),
            "suggested_time": "19:00 - 21:00",
            "hashtags": hashtag_sets[2]
        }
    ]
    
    return {
        "product_name": product_name,
        "price": price,
        "caption": caption,
        "posts": posts,
        "tips": [
            "Nên quay video chậm để show rõ món ăn",
            "Ánh sáng tự nhiên sẽ đẹp hơn",
            "Thêm emoji để thu hút attention",
            "Post vào giờ vàng để tăng reach"
        ]
    }


# ==================== GOOGLE MAPS & TRACKING ====================

@ai_bp.route("/calculate-shipping", methods=["POST"])
def ai_calculate_shipping():
    """Tính phí vận chuyển dựa trên khoảng cách"""
    try:
        data = request.json
        from_lat = data.get("from_lat")
        from_lng = data.get("from_lng")
        to_lat = data.get("to_lat")
        to_lng = data.get("to_lng")
        
        # Trong thực tế, gọi Google Distance Matrix API
        # Đây là simulation
        import random
        
        # Tính khoảng cách ảo
        distance_km = random.uniform(1, 10)
        
        # Tính phí ship
        base_fee = 15000
        per_km = 3000
        shipping_fee = base_fee + (distance_km * per_km)
        
        # Thời gian giao hàng
        estimated_time = int(distance_km * 3) + 15  # 15 phút chuẩn bị + 3 phút/km
        
        return jsonify({
            "success": True,
            "distance_km": round(distance_km, 1),
            "shipping_fee": int(shipping_fee),
            "estimated_time_minutes": estimated_time,
            "route": {
                "from": {"lat": from_lat, "lng": from_lng},
                "to": {"lat": to_lat, "lng": to_lng}
            }
        })
        
    except Exception as e:
        logger.error(f"Shipping Calculate Error: {e}")
        return jsonify({"success": False, "message": "Lỗi tính phí vận chuyển"}), 500


@ai_bp.route("/track-order/<order_id>", methods=["GET"])
def ai_track_order(order_id):
    """Theo dõi đơn hàng real-time (simulated)"""
    try:
        order = db_get(f"orders/{order_id}")
        if not order:
            return jsonify({"success": False, "message": "Đơn hàng không tồn tại"}), 404
        
        import random
        
        # Simulated vị trí shipper
        status = order.get("status", "pending")
        
        if status == "shipping":
            # Random vị trí dọc đường
            progress = random.uniform(0.3, 0.9)
            
            return jsonify({
                "success": True,
                "order_id": order_id,
                "status": "shipping",
                "shipper": {
                    "name": "Nguyễn Văn A",
                    "phone": "0912-345-678",
                    "vehicle": "Xe máy",
                    "rating": 4.8
                },
                "location": {
                    "lat": 21.0285 + (0.01 * progress),
                    "lng": 105.8542 + (0.005 * progress)
                },
                "progress": int(progress * 100),
                "estimated_arrival": f"{random.randint(10, 25)} phút",
                "steps": [
                    {"status": "confirmed", "time": order.get("date"), "completed": True},
                    {"status": "preparing", "time": order.get("date"), "completed": True},
                    {"status": "picked_up", "time": order.get("date"), "completed": True},
                    {"status": "shipping", "time": "Bây giờ", "completed": False},
                    {"status": "delivered", "time": "Sắp tới", "completed": False}
                ]
            })
        elif status == "pending":
            return jsonify({
                "success": True,
                "order_id": order_id,
                "status": "pending",
                "message": "Đơn hàng đang chờ xác nhận",
                "steps": [
                    {"status": "confirmed", "time": order.get("date"), "completed": True},
                    {"status": "preparing", "time": "Đang chuẩn bị", "completed": False},
                    {"status": "shipping", "time": "Sắp tới", "completed": False},
                    {"status": "delivered", "time": "Hoàn thành", "completed": False}
                ]
            })
        else:
            return jsonify({
                "success": True,
                "order_id": order_id,
                "status": status,
                "message": f"Đơn hàng đã {status}"
            })
            
    except Exception as e:
        logger.error(f"Track Order Error: {e}")
        return jsonify({"success": False, "message": "Lỗi theo dõi đơn hàng"}), 500


# ==================== GAMIFICATION ====================

@ai_bp.route("/gamification/profile", methods=["GET"])
@require_login
def ai_gamification_profile():
    """Lấy thông tin gamification của user"""
    try:
        user = session["user"]
        users = db_get("users") or {}
        user_data = users.get(user) if isinstance(users, dict) else None
        
        if not user_data:
            return jsonify({"success": False, "message": "Không tìm thấy người dùng"}), 404
        
        points = user_data.get("points", 0)
        rank = user_data.get("rank", "Đồng")
        total_spent = user_data.get("total_spent", 0)
        
        # Tính progress lên rank tiếp theo
        rank_info = {
            "Đồng": {"next": "Bạc", "required": 2_000_000, "color": "#CD7F32"},
            "Bạc": {"next": "Vàng", "required": 5_000_000, "color": "#C0C0C0"},
            "Vàng": {"next": "Kim Cương", "required": 10_000_000, "color": "#FFD700"},
            "Kim Cương": {"next": None, "required": 0, "color": "#B9F2FF"}
        }
        
        current_rank_info = rank_info.get(rank, rank_info["Đồng"])
        next_rank = current_rank_info["next"]
        required = current_rank_info["required"]
        
        progress = 0
        if next_rank:
            progress = int((total_spent / required) * 100)
        
        # Quà tặng theo rank
        benefits = {
            "Đồng": ["Tích điểm 1%"],
            "Bạc": ["Tích điểm 1.5%", "Miễn phí ship đơn >100k"],
            "Vàng": ["Tích điểm 2%", "Miễn phí ship", "Giảm giá 5%"],
            "Kim Cương": ["Tích điểm 3%", "Miễn phí ship", "Giảm giá 10%", "Quà sinh nhật"]
        }
        
        return jsonify({
            "success": True,
            "profile": {
                "username": user,
                "rank": rank,
                "points": points,
                "total_spent": total_spent,
                "rank_color": current_rank_info["color"],
                "next_rank": next_rank,
                "progress_to_next": progress,
                "required_for_next_rank": required,
                "benefits": benefits.get(rank, [])
            }
        })
        
    except Exception as e:
        logger.error(f"Gamification Profile Error: {e}")
        return jsonify({"success": False, "message": "Lỗi lấy thông tin"}), 500


@ai_bp.route("/gamification/spin-wheel", methods=["GET"])
@require_login
def ai_spin_wheel():
    """Vòng quay may mắn"""
    try:
        user = session["user"]
        users = db_get("users") or {}
        user_data = users.get(user) if isinstance(users, dict) else None
        
        if not user_data:
            return jsonify({"success": False, "message": "Không tìm thấy người dùng"}), 404
        
        points = user_data.get("points", 0)
        
        # Cần tối thiểu 100 điểm để quay
        if points < 100:
            return jsonify({
                "success": False, 
                "message": "Bạn cần ít nhất 100 điểm để quay vòng quay!",
                "current_points": points
            }), 400
        
        import random
        
        # Giảm điểm
        points_cost = 100
        remaining_points = points - points_cost
        
        # Phần thưởng
        prizes = [
            {"id": 1, "name": "Giảm giá 10%", "type": "voucher", "value": 10, "weight": 30},
            {"id": 2, "name": "Giảm giá 20%", "type": "voucher", "value": 20, "weight": 15},
            {"id": 3, "name": "Miễn phí ship", "type": "voucher", "value": 100, "weight": 20},
            {"id": 4, "name": "50 điểm thưởng", "type": "points", "value": 50, "weight": 25},
            {"id": 5, "name": "100 điểm thưởng", "type": "points", "value": 100, "weight": 8},
            {"id": 6, "name": "Rất tiếc, không trúng", "type": "none", "value": 0, "weight": 2},
        ]
        
        # Chọn phần thưởng
        weights = [p["weight"] for p in prizes]
        prize = random.choices(prizes, weights=weights)[0]
        
        # Cập nhật điểm
        if prize["type"] == "points":
            remaining_points += prize["value"]
        
        db_patch(f"users/{user}", {"points": remaining_points})
        
        return jsonify({
            "success": True,
            "prize": prize,
            "remaining_points": remaining_points,
            "message": f"Chúc mừng! Bạn đã trúng: {prize['name']}!"
        })
        
    except Exception as e:
        logger.error(f"Spin Wheel Error: {e}")
        return jsonify({"success": False, "message": "Lỗi quay vòng quay"}), 500


# ==================== PUSH NOTIFICATIONS ====================

@ai_bp.route("/notifications/send", methods=["POST"])
def ai_send_notification():
    """Gửi thông báo đẩy (simulated)"""
    try:
        data = request.json
        user = data.get("user")
        title = data.get("title")
        body = data.get("body")
        type = data.get("type", "general")
        
        if not user or not title:
            return jsonify({"success": False, "message": "Thiếu thông tin"}), 400
        
        # Lưu notification vào database
        notif = {
            "id": str(uuid.uuid4()),
            "title": title,
            "message": body,
            "type": type,
            "user": user,
            "is_read": False,
            "created_at": datetime.now().isoformat()
        }
        
        raw_notifs = db_get(f"notifications/{user}") or []
        notifs = list(raw_notifs.values()) if isinstance(raw_notifs, dict) else raw_notifs
        notifs.insert(0, notif)
        db_put(f"notifications/{user}", notifs)
        
        # Trong thực tế, gọi FCM (Firebase Cloud Messaging) để gửi push notification
        # response = send_push_notification(user, title, body)
        
        return jsonify({
            "success": True,
            "message": "Đã gửi thông báo",
            "notification_id": notif["id"]
        })
        
    except Exception as e:
        logger.error(f"Send Notification Error: {e}")
        return jsonify({"success": False, "message": "Lỗi gửi thông báo"}), 500


@ai_bp.route("/notifications/campaign", methods=["POST"])
@require_login
def ai_send_campaign():
    """Gửi thông báo cho nhiều người dùng (marketing)"""
    try:
        if session.get("role") != "admin":
            return jsonify({"success": False, "message": "Không có quyền"}), 403
        
        data = request.json
        title = data.get("title")
        body = data.get("body")
        target_segment = data.get("segment", "all")  # all, new, vip, inactive
        
        users = db_get("users") or {}
        all_users = users if isinstance(users, dict) else {}
        
        # Lọc theo segment
        target_users = []
        for username, user_data in all_users.items():
            if not isinstance(user_data, dict):
                continue
            
            if user_data.get("role") == "admin":
                continue
                
            if target_segment == "vip" and user_data.get("rank") in ["Vàng", "Kim Cương"]:
                target_users.append(username)
            elif target_segment == "new" and user_data.get("order_count", 0) < 3:
                target_users.append(username)
            elif target_segment == "inactive":
                # Chưa order trong 30 ngày
                target_users.append(username)
            elif target_segment == "all":
                target_users.append(username)
        
        # Gửi thông báo cho từng user
        sent_count = 0
        for u in target_users:
            notif = {
                "id": str(uuid.uuid4()),
                "title": title,
                "message": body,
                "type": "campaign",
                "is_read": False,
                "created_at": datetime.now().isoformat()
            }
            
            raw_notifs = db_get(f"notifications/{u}") or []
            notifs = list(raw_notifs.values()) if isinstance(raw_notifs, dict) else raw_notifs
            notifs.insert(0, notif)
            db_put(f"notifications/{u}", notifs)
            sent_count += 1
        
        return jsonify({
            "success": True,
            "message": f"Đã gửi thông báo đến {sent_count} người dùng",
            "target_segment": target_segment,
            "sent_count": sent_count
        })
        
    except Exception as e:
        logger.error(f"Send Campaign Error: {e}")
        return jsonify({"success": False, "message": "Lỗi gửi chiến dịch"}), 500
