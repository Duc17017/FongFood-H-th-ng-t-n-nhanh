-- =====================================================
-- FONG FOOD - DATABASE SCHEMA (SQL)
-- =====================================================
-- Database: MySQL/PostgreSQL
-- Created based on current Firebase data structure
-- =====================================================

-- =====================================================
-- 1. USERS TABLE
-- =====================================================
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,  -- Phone number as username
    password VARCHAR(255) NOT NULL,         -- Hashed password
    name VARCHAR(100),
    email VARCHAR(100),
    phone VARCHAR(20),
    role ENUM('admin', 'customer') DEFAULT 'customer',
    avatar VARCHAR(500),
    points INT DEFAULT 0,                   -- Loyalty points
    total_spent DECIMAL(15,0) DEFAULT 0,    -- Total amount spent
    order_count INT DEFAULT 0,               -- Number of orders
    rank ENUM('Đồng', 'Bạc', 'Vàng', 'Kim Cương') DEFAULT 'Đồng',
    login_token VARCHAR(255),
    last_login DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_username (username),
    INDEX idx_email (email),
    INDEX idx_phone (phone)
);

-- =====================================================
-- 2. PRODUCTS TABLE
-- =====================================================
CREATE TABLE products (
    id VARCHAR(50) PRIMARY KEY,             -- Product ID (e.g., p12345)
    name VARCHAR(200) NOT NULL,
    description TEXT,
    price DECIMAL(15,0) NOT NULL,
    image TEXT,                              -- Base64 or URL
    category VARCHAR(50),
    subcategory VARCHAR(50),
    isAvailable BOOLEAN DEFAULT TRUE,
    isPromoted BOOLEAN DEFAULT FALSE,
    isFeatured BOOLEAN DEFAULT FALSE,
    rating DECIMAL(3,2) DEFAULT 0,
    review_count INT DEFAULT 0,
    sold_count INT DEFAULT 0,               -- Number sold
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_category (category),
    INDEX idx_is_available (isAvailable),
    INDEX idx_is_promoted (isPromoted)
);

-- =====================================================
-- 3. ORDERS TABLE
-- =====================================================
CREATE TABLE orders (
    id VARCHAR(50) PRIMARY KEY,             -- Order ID (e.g., A1B2C3D4)
    user_id VARCHAR(50),                    -- Username/phone
    customer_name VARCHAR(100),
    phone VARCHAR(20),
    address TEXT,
    total DECIMAL(15,0) NOT NULL,
    discount DECIMAL(15,0) DEFAULT 0,        -- Discount amount
    final_total DECIMAL(15,0) NOT NULL,
    status ENUM('pending', 'confirmed', 'preparing', 'ready', 'delivering', 'completed', 'cancelled') DEFAULT 'pending',
    payment_method VARCHAR(50),             -- cod, vnpay, momo, zalopay
    payment_status ENUM('Chưa thanh toán', 'Đã thanh toán', 'Thanh toán thất bại') DEFAULT 'Chưa thanh toán',
    notes TEXT,
    points_used INT DEFAULT 0,               -- Points redeemed
    points_earned INT DEFAULT 0,             -- Points earned
    voucher_code VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    confirmed_at DATETIME,
    completed_at DATETIME,
    cancelled_at DATETIME,
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE SET NULL
);

-- =====================================================
-- 4. ORDER ITEMS TABLE
-- =====================================================
CREATE TABLE order_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL,
    product_id VARCHAR(50),
    product_name VARCHAR(200),
    price DECIMAL(15,0) NOT NULL,
    quantity INT NOT NULL,
    subtotal DECIMAL(15,0) NOT NULL,
    notes TEXT,
    INDEX idx_order_id (order_id),
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
);

-- =====================================================
-- 5. VOUCHERS TABLE
-- =====================================================
CREATE TABLE vouchers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    discount DECIMAL(5,2) NOT NULL,          -- Discount percentage (e.g., 20 = 20%)
    type ENUM('percent', 'fixed') DEFAULT 'percent',
    min_order DECIMAL(15,0) DEFAULT 0,       -- Minimum order amount
    max_discount DECIMAL(15,0),              -- Maximum discount for percent type
    quantity INT DEFAULT 1,                   -- Number of uses remaining
    user_id VARCHAR(50),                     -- NULL = all users, otherwise specific user
    valid_from DATETIME,
    valid_until DATETIME NOT NULL,
    reason VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_code (code),
    INDEX idx_user_id (user_id),
    INDEX idx_valid_until (valid_until),
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE
);

-- =====================================================
-- 6. CARTS TABLE (Per User)
-- =====================================================
CREATE TABLE carts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    product_id VARCHAR(50) NOT NULL,
    product_name VARCHAR(200),
    price DECIMAL(15,0) NOT NULL,
    quantity INT DEFAULT 1,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_user_product (user_id, product_id),
    INDEX idx_user_id (user_id),
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

-- =====================================================
-- 7. NOTIFICATIONS TABLE
-- =====================================================
CREATE TABLE notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT,
    type ENUM('order', 'promotion', 'system', 'warning', 'success') DEFAULT 'system',
    is_read BOOLEAN DEFAULT FALSE,
    link VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_is_read (is_read),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE
);

-- =====================================================
-- 8. REVIEWS TABLE
-- =====================================================
CREATE TABLE reviews (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    product_id VARCHAR(50),
    order_id VARCHAR(50),
    rating INT NOT NULL,                     -- 1-5 stars
    review_text TEXT,
    sentiment VARCHAR(20),                    -- positive, negative, neutral (AI analyzed)
    is_ai_analyzed BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_product_id (product_id),
    INDEX idx_order_id (order_id),
    INDEX idx_rating (rating),
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL
);

-- =====================================================
-- 9. ADDRESSES TABLE
-- =====================================================
CREATE TABLE addresses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    label VARCHAR(50),                       -- Nhà riêng, Cơ quan, ...
    address TEXT NOT NULL,
    ward VARCHAR(100),
    district VARCHAR(100),
    city VARCHAR(100),
    phone VARCHAR(20),
    is_default BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_is_default (is_default),
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE
);

-- =====================================================
-- 10. USER POINTS HISTORY (Optional - for tracking)
-- =====================================================
CREATE TABLE points_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    points INT NOT NULL,                     -- Positive = earned, Negative = redeemed
    type ENUM('order_earn', 'order_spend', 'voucher_redeem', 'bonus', 'expire') NOT NULL,
    order_id VARCHAR(50),
    description VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_order_id (order_id),
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL
);

-- =====================================================
-- SAMPLE DATA
-- =====================================================

-- Admin user (password: admin123 - hashed with pbkdf2)
INSERT INTO users (username, password, name, email, role) VALUES 
('admin', 'pbkdf2:sha256:260000$randomsalt$hashedpassword', 'Admin', 'admin@fongfood.com', 'admin');

-- Sample products
INSERT INTO products (id, name, description, price, category, isAvailable) VALUES
('p10001', 'Gà Rán Giòn', 'Gà rán giòn tan, thơm ngon', 35000, 'Gà Rán', TRUE),
('p10002', 'Burger Bò', 'Burger bò với phô mai', 45000, 'Burger', TRUE),
('p10003', 'Khoai Tây Chiên', 'Khoai tây chiên vàng giòn', 25000, 'Phụ Liện', TRUE),
('p10004', 'Nước Ngọt', 'Coca Cola / Pepsi', 10000, 'Đồ Uống', TRUE),
('p10005', 'Combo Gà 2 Người', '2 miếng gà + 2 khoai + 2 nước', 120000, 'Combo', TRUE);

-- =====================================================
-- VIEWS
-- =====================================================

-- View: Top selling products
CREATE VIEW v_top_products AS
SELECT 
    p.id,
    p.name,
    p.category,
    SUM(oi.quantity) as total_sold,
    SUM(oi.subtotal) as total_revenue
FROM products p
JOIN order_items oi ON p.id = oi.product_id
JOIN orders o ON oi.order_id = o.id
WHERE o.status = 'completed'
GROUP BY p.id, p.name, p.category
ORDER BY total_sold DESC;

-- View: User order statistics
CREATE VIEW v_user_stats AS
SELECT 
    u.username,
    u.name,
    u.email,
    u.rank,
    COUNT(o.id) as total_orders,
    COALESCE(SUM(o.final_total), 0) as total_spent,
    u.points
FROM users u
LEFT JOIN orders o ON u.username = o.user_id AND o.status = 'completed'
WHERE u.role = 'customer'
GROUP BY u.username, u.name, u.email, u.rank, u.points;

-- View: Daily revenue
CREATE VIEW v_daily_revenue AS
SELECT 
    DATE(created_at) as date,
    COUNT(*) as order_count,
    SUM(final_total) as revenue
FROM orders
WHERE status = 'completed'
GROUP BY DATE(created_at);

-- =====================================================
-- STORED PROCEDURES
-- =====================================================

DELIMITER //

-- Procedure: Create order with items
CREATE PROCEDURE sp_create_order(
    IN p_id VARCHAR(50),
    IN p_user_id VARCHAR(50),
    IN p_customer_name VARCHAR(100),
    IN p_phone VARCHAR(20),
    IN p_address TEXT,
    IN p_total DECIMAL(15,0),
    IN p_discount DECIMAL(15,0),
    IN p_final_total DECIMAL(15,0),
    IN p_payment_method VARCHAR(50),
    IN p_notes TEXT,
    IN p_voucher_code VARCHAR(50)
)
BEGIN
    INSERT INTO orders (id, user_id, customer_name, phone, address, total, discount, final_total, payment_method, notes, voucher_code)
    VALUES (p_id, p_user_id, p_customer_name, p_phone, p_address, p_total, p_discount, p_final_total, p_payment_method, p_notes, p_voucher_code);
END //

-- Procedure: Add order item
CREATE PROCEDURE sp_add_order_item(
    IN p_order_id VARCHAR(50),
    IN p_product_id VARCHAR(50),
    IN p_product_name VARCHAR(200),
    IN p_price DECIMAL(15,0),
    IN p_quantity INT
)
BEGIN
    INSERT INTO order_items (order_id, product_id, product_name, price, quantity, subtotal)
    VALUES (p_order_id, p_product_id, p_product_name, p_price, p_quantity, p_price * p_quantity);
END //

-- Procedure: Update order status
CREATE PROCEDURE sp_update_order_status(
    IN p_order_id VARCHAR(50),
    IN p_status VARCHAR(20)
)
BEGIN
    UPDATE orders 
    SET status = p_status,
        confirmed_at = CASE WHEN p_status = 'confirmed' AND confirmed_at IS NULL THEN NOW() ELSE confirmed_at END,
        completed_at = CASE WHEN p_status = 'completed' AND completed_at IS NULL THEN NOW() ELSE completed_at END,
        cancelled_at = CASE WHEN p_status = 'cancelled' AND cancelled_at IS NULL THEN NOW() ELSE cancelled_at END
    WHERE id = p_order_id;
END //

-- Procedure: Calculate user points from order
CREATE PROCEDURE sp_calculate_points(
    IN p_user_id VARCHAR(50),
    IN p_order_id VARCHAR(50)
)
BEGIN
    DECLARE v_total DECIMAL(15,0);
    
    SELECT final_total INTO v_total FROM orders WHERE id = p_order_id;
    
    -- Earn 1 point per 10,000 VND
    UPDATE users 
    SET points = points + FLOOR(v_total / 10000),
        order_count = order_count + 1,
        total_spent = total_spent + v_total,
        rank = CASE 
            WHEN total_spent + v_total > 10000000 THEN 'Kim Cương'
            WHEN total_spent + v_total > 5000000 THEN 'Vàng'
            WHEN total_spent + v_total > 2000000 THEN 'Bạc'
            ELSE 'Đồng'
        END
    WHERE username = p_user_id;
    
    -- Log points history
    INSERT INTO points_history (user_id, points, type, order_id, description)
    VALUES (p_user_id, FLOOR(v_total / 10000), 'order_earn', p_order_id, 'Points earned from order');
END //

DELIMITER ;
