# Deploy lên Render

## Các bước deploy:

### 1. Chuẩn bị trên Render.com

1. Đăng nhập [Render](https://render.com)
2. Tạo Web Service mới
3. Kết nối với GitHub repository của bạn
4. Chọn branch `dev`

### 2. Cấu hình Environment Variables

Thêm các biến môi trường sau trong Render Dashboard:

| Key | Value |
|-----|-------|
| `FLASK_DEBUG` | `0` |
| `FLASK_ENV` | `production` |
| `SECRET_KEY` | (tạo ngẫu nhiên) |
| `FIREBASE_URL` | `https://foodappdb-5fe2e-default-rtdb.firebaseio.com/` |
| `GEMINI_API_KEY` | (API key của bạn - nếu có) |

### 3. Cấu hình khác (tùy chọn)

Nếu bạn muốn sử dụng thanh toán, thêm:

- `VNPAY_TMN_CODE`, `VNPAY_HASH_SECRET`
- `MOMO_PARTNER_CODE`, `MOMO_ACCESS_KEY`, `MOMO_SECRET_KEY`
- `ZALOPAY_APP_ID`, `ZALOPAY_KEY1`
- `GOOGLE_MAPS_API_KEY`

### 4. Deploy

- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app --workers 4 --bind 0.0.0.0:$PORT`

---

## Hoặc sử dụng render.yaml (Auto-deploy)

1. Đẩy `render.yaml` lên GitHub
2. Trên Render, tạo "Blueprint" và tải lên file `render.yaml`

---

## Lưu ý quan trọng

- Database của bạn là Firebase Realtime Database, không cần cài đặt database riêng
- App sẽ chạy với gunicorn thay vì Flask dev server
- Cổng sẽ được Render gán tự động qua biến `$PORT`
