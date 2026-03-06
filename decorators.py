from functools import wraps

from flask import session, redirect, url_for, flash


def login_required(role: str | None = None):
    """Decorator kiểm tra đăng nhập (WEB)."""

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user" not in session:
                flash("Vui lòng đăng nhập để tiếp tục.", "warning")
                return redirect(url_for("auth.login"))

            if role:
                current_role = session.get("role")
                if current_role != role:
                    flash("Bạn không có quyền truy cập chức năng này.", "danger")
                    # Admin cố vào trang khách hoặc ngược lại -> đẩy về trang phù hợp
                    if current_role == "admin":
                        # Điều hướng thẳng bằng URL để tránh lỗi endpoint
                        return redirect("/admin/dashboard")
                    return redirect("/home")

            return f(*args, **kwargs)

        return wrapped

    return decorator


def admin_required(f):
    """Chỉ cho phép admin truy cập."""
    return login_required(role="admin")(f)

