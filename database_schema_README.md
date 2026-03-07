# FONG FOOD - Database Schema

## Giới thiệu

File `database_schema.sql` chứa đầy đủ cấu trúc database SQL (MySQL/PostgreSQL) cho ứng dụng Fong Food, dựa trên cấu trúc Firebase hiện tại.

## Các bảng dữ liệu

| Bảng | Mô tả |
|------|-------|
| **users** | Thông tin người dùng (đăng ký, đăng nhập, điểm tích lũy, hạng thành viên) |
| **products** | Sản phẩm (món ăn, đồ uống) |
| **orders** | Đơn hàng |
| **order_items** | Chi tiết các món trong đơn hàng |
| **vouchers** | Mã giảm giá |
| **carts** | Giỏ hàng (theo user) |
| **notifications** | Thông báo |
| **reviews** | Đánh giá sản phẩm |
| **addresses** | Địa chỉ giao hàng |
| **points_history** | Lịch sử tích/sử dụng điểm |

## Cách sử dụng

### 1. Import vào MySQL

```bash
mysql -u root -p fongfood < database_schema.sql
```

Hoặc chạy từ MySQL Workbench / phpMyAdmin.

### 2. Cấu hình kết nối

Tạo file `.env`:

```env
DB_HOST=localhost
DB_PORT=3306
DB_NAME=fongfood
DB_USER=root
DB_PASSWORD=your_password
```

### 3. Cập nhật code

Sửa `utils.py` để dùng SQL thay vì Firebase:

```python
import pymysql

def get_db_connection():
    return pymysql.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 3306)),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'fongfood'),
        cursorclass=pymysql.cursors.DictCursor
    )
```

## Quan hệ giữa các bảng

```
users (1) ──────< (N) orders
users (1) ──────< (N) carts  
users (1) ──────< (N) addresses
users (1) ──────< (N) notifications
users (1) ──────< (N) reviews
users (1) ──────< (N) vouchers
users (1) ──────< (N) points_history

products (1) ───< (N) order_items
products (1) ───< (N) carts
products (1) ───< (N) reviews

orders (1) ─────< (N) order_items
orders (1) ─────< (N) reviews
orders (1) ─────< (N) points_history
```

## Views hữu ích

- `v_top_products` - Top sản phẩm bán chạy
- `v_user_stats` - Thống kê khách hàng
- `v_daily_revenue` - Doanh thu theo ngày

## Stored Procedures

- `sp_create_order` - Tạo đơn hàng
- `sp_add_order_item` - Thêm món vào đơn
- `sp_update_order_status` - Cập nhật trạng thái đơn
- `sp_calculate_points` - Tính điểm tích lũy
