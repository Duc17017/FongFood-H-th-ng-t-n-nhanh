import os
from pathlib import Path

from dotenv import load_dotenv

# Luôn nạp .env theo đường dẫn tuyệt đối để tránh chạy Flask ở cwd khác
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "dev_secret_key_change_me")
FIREBASE_URL = os.getenv(
    "FIREBASE_URL",
    "https://foodappdb-5fe2e-default-rtdb.firebaseio.com/",
)
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"

# API Configuration
API_PREFIX = "/api/v1"
CORS_ORIGINS = ["*"]

# AI Configuration (for future integration with Gemini/ChatGPT)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Payment Gateway Configuration
VNPAY_TMN_CODE = os.getenv("VNPAY_TMN_CODE", "")
VNPAY_HASH_SECRET = os.getenv("VNPAY_HASH_SECRET", "")
VNPAY_URL = os.getenv("VNPAY_URL", "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html")

MOMO_PARTNER_CODE = os.getenv("MOMO_PARTNER_CODE", "")
MOMO_ACCESS_KEY = os.getenv("MOMO_ACCESS_KEY", "")
MOMO_SECRET_KEY = os.getenv("MOMO_SECRET_KEY", "")
MOMO_ENDPOINT = os.getenv("MOMO_ENDPOINT", "https://test-payment.momo.vn/v2/gateway/api/create")

ZALOPAY_APP_ID = os.getenv("ZALOPAY_APP_ID", "")
ZALOPAY_KEY1 = os.getenv("ZALOPAY_KEY1", "")
ZALOPAY_ENDPOINT = os.getenv("ZALOPAY_ENDPOINT", "https://sb-openapi.zalopay.vn/v2/create")

# Google Maps API
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# Weather API (OpenWeatherMap)
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

# Firebase Cloud Messaging (Push Notifications)
FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY", "")

