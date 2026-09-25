from flask import render_template , Blueprint , redirect , url_for , flash , request
from flask_login import current_user , login_user , logout_user , login_required
from app.models import User
from app.extensions import db


LoginRegister = Blueprint("LoginRegister", __name__)

@LoginRegister.route("/register", methods=["GET", "POST"])
def register():
    """Register a new user. The password is stored only as a hash."""
    if current_user.is_authenticated:
        return redirect(url_for("pages.dashboard"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""

        # --- Input validation ---
        if not (3 <= len(username) <= 32):
            flash("نام کاربری باید بین ۳ تا ۳۲ کاراکتر باشد.", "danger")
        elif not username.isalnum():
            flash("نام کاربری فقط می‌تواند شامل حروف و اعداد باشد.", "danger")
        elif len(password) < 6:
            flash("رمز عبور باید حداقل ۶ کاراکتر باشد.", "danger")
        elif password != confirm:
            flash("تکرار رمز عبور مطابقت ندارد.", "danger")
        elif User.query.filter_by(username=username).first() is not None:
            flash("این نام کاربری قبلاً ثبت شده است.", "danger")
        else:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("حساب کاربری با موفقیت ساخته شد. خوش آمدید!", "success")
            return redirect(url_for("pages.dashboard"))

    return render_template("register.html")


@LoginRegister.route("/login", methods=["GET", "POST"])
def login():
    """Log the user in. After login, the user is redirected to the dashboard."""
    if current_user.is_authenticated:
        return redirect(url_for("pages.dashboard"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            flash("نام کاربری یا رمز عبور اشتباه است.", "danger")
        else:
            login_user(user, remember=True)
            flash("خوش آمدید!", "success")
            return redirect(url_for("pages.dashboard"))

    return render_template("login.html")


@LoginRegister.route("/logout")
@login_required
def logout():
    """Log the user out."""
    logout_user()
    flash("با موفقیت خارج شدید.", "info")
    return redirect(url_for("pages.index"))