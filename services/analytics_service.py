from datetime import datetime, timedelta
from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)


def analyze_business_data(
    orders: Dict[str, Dict[str, Any]],
    products: Dict[str, Dict[str, Any]] | None = None,
    time_filter: str = "week",
) -> Dict[str, Any]:
    """
    Phân tích dữ liệu kinh doanh + sinh insight dạng 'AI'.

    - Tính doanh thu
    - Đếm trạng thái đơn
    - Thống kê doanh thu theo ngày/tháng tùy filter
    - Tỷ lệ món ăn / đồ uống
    - Gợi ý insight kinh doanh
    """
    total_revenue = 0.0
    filtered_orders_count = 0
    status_counts = {
        "pending": 0,
        "shipping": 0,
        "completed": 0,
        "cancelled": 0,
    }
    
    # revenue_data: danh sách dict {label, value}
    revenue_data: List[Dict[str, Any]] = []
    
    # Labels cho chart
    chart_labels: List[str] = []
    chart_values: List[float] = []

    cat_sales = {"food": 0, "drink": 0}
    pending_orders: List[Dict[str, Any]] = []

    now = datetime.now()

    def _parse_order_date(raw_date: str) -> datetime | None:
        if not raw_date:
            return None
        try:
            # Format: "HH:MM DD/MM/YYYY" hoặc "DD/MM/YYYY"
            d_str = raw_date.strip()
            if " " in d_str:
                d_str = d_str.split(" ")[1]
            return datetime.strptime(d_str, "%d/%m/%Y")
        except Exception:
            return None

    # Khởi tạo revenue_data theo filter
    if time_filter == "week":
        # 7 ngày gần nhất
        for i in range(6, -1, -1):
            d = now.date() - timedelta(days=i)
            chart_labels.append(d.strftime("%d/%m"))
            chart_values.append(0.0)
        revenue_data = [{"label": l, "value": v} for l, v in zip(chart_labels, chart_values)]
    elif time_filter == "month":
        # Các ngày trong tháng (1-31)
        import calendar
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        for d in range(1, days_in_month + 1):
            chart_labels.append(f"{d:02d}")
            chart_values.append(0.0)
        revenue_data = [{"label": l, "value": v} for l, v in zip(chart_labels, chart_values)]
    elif time_filter == "year":
        # 12 tháng
        month_names = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12"]
        for m in month_names:
            chart_labels.append(m)
            chart_values.append(0.0)
        revenue_data = [{"label": l, "value": v} for l, v in zip(chart_labels, chart_values)]
    else:
        # Mặc định: 7 ngày
        for i in range(6, -1, -1):
            d = now.date() - timedelta(days=i)
            chart_labels.append(d.strftime("%d/%m"))
            chart_values.append(0.0)
        revenue_data = [{"label": l, "value": v} for l, v in zip(chart_labels, chart_values)]

    # Map ngày/tháng -> index trong chart_values
    def _get_data_index(parsed: datetime) -> int | None:
        if time_filter == "week":
            # So sánh ngày cụ thể
            d = parsed.date()
            for i, label in enumerate(chart_labels):
                label_date = datetime.strptime(label, "%d/%m").date()
                if label_date.year == now.year and label_date.month == now.month and label_date.day == d.day:
                    return i
            return None
        elif time_filter == "month":
            # Ngày trong tháng (1-31)
            if parsed.year == now.year and parsed.month == now.month:
                return parsed.day - 1  # 0-indexed
            return None
        elif time_filter == "year":
            # Tháng (1-12)
            return parsed.month - 1  # 0-indexed
        return None

    for oid, order in orders.items():
        if not isinstance(order, dict):
            continue

        parsed_date = _parse_order_date(order.get("date") or "")
        
        # Lọc theo time_filter
        in_range = True
        if parsed_date:
            d = parsed_date.date()
            if time_filter == "week":
                in_range = d >= (now.date() - timedelta(days=7))
            elif time_filter == "month":
                in_range = d.year == now.year and d.month == now.month
            elif time_filter == "year":
                in_range = d.year == now.year
        
        if not in_range:
            continue

        filtered_orders_count += 1
        status = order.get("status", "pending")
        total = float(order.get("total", 0) or 0)

        if status in status_counts:
            status_counts[status] += 1

        if status == "pending":
            pending_orders.append({
                "id": oid,
                "customerName": order.get("customerName", "Khách lẻ"),
                "total": total,
                "status": "pending",
            })

        if status in ["completed", "shipping"]:
            total_revenue += total

            # Cộng vào chart đúng ngày/tháng
            if parsed_date:
                idx = _get_data_index(parsed_date)
                if idx is not None and idx < len(chart_values):
                    # Lưu theo triệu đồng
                    chart_values[idx] += total / 1_000_000

            items = order.get("details") or order.get("items") or []
            for item in items:
                if not isinstance(item, dict):
                    continue
                name_lower = (item.get("name") or "").lower()
                qty = int(item.get("qty", 0) or 0)

                if any(x in name_lower for x in ["trà", "nước", "cafe", "coffee", "sinh tố", "bia", "coca", "pepsi"]):
                    cat_sales["drink"] += qty
                else:
                    cat_sales["food"] += qty

    # Cập nhật revenue_data với giá trị mới
    revenue_data = [{"label": l, "value": round(v, 2)} for l, v in zip(chart_labels, chart_values)]

    total_items = sum(cat_sales.values()) or 1
    food_pct = round((cat_sales["food"] / total_items) * 100)
    drink_pct = 100 - food_pct

    ai_insight = "Mọi chỉ số kinh doanh đều đang ổn định."
    if total_revenue == 0:
        ai_insight = f"Chưa có doanh thu trong kỳ này. Hãy thử chạy chương trình khuyến mãi!"
    elif status_counts["pending"] >= 3:
        ai_insight = f"Cảnh báo: Có {status_counts['pending']} đơn hàng đang chờ xử lý. Cần duyệt ngay!"
    elif drink_pct < 20:
        ai_insight = "Tỷ lệ bán đồ uống thấp (<20%). Nên tạo Combo Đồ ăn + Nước để kích cầu."
    elif chart_values and max(chart_values) > sum(chart_values) / len(chart_values) * 3:
        ai_insight = "Doanh thu có ngày tăng đột biến. Cần chuẩn bị thêm nguyên liệu cho các ngày cao điểm."

    logger.info(f"=== ANALYTICS: time_filter={time_filter}, orders={filtered_orders_count}, revenue={total_revenue}, revenue_data={revenue_data} ===")

    return {
        "revenue": total_revenue,
        "total_orders": filtered_orders_count,
        "status_counts": status_counts,
        "revenue_daily": revenue_data,
        "chart_labels": chart_labels,
        "chart_values": chart_values,
        "food_pct": food_pct,
        "drink_pct": drink_pct,
        "ai_insight": ai_insight,
        "pending_orders": pending_orders,
    }
