# Count Time Game ⏱️

بازی آنلاین چندنفره‌ای که هر بازیکن باید زمان سپری‌شده از یک نوبت را حدس بزند. برنده کسی است که **کمترین تغییر** بین حدسش و زمان واقعی داشته باشد.

---

## ✨ امکانات کلیدی

- **بازی Real-Time** با Flask-SocketIO (همه چیز در لحظه‌ای انجام می‌شود)
- **اتاق‌های خصوصی** با کد یکتا (۸ نفری)
- **زمان‌سنجی سمت سرور** با `time.perf_counter()` (ضد تقلب از دست‌کاری مرورگر)
- **احراز هویت کاربران** با Flask-Login (ثبت‌نام / ورود / خروج)
- **ذخیره داده‌ها** در SQLite از طریق Flask-SQLAlchemy
- **صفحه‌های تخصصی**: داشبورد، صفحه بازی، نتایج نهایی (زمان درست، جدول رتبه‌بندی ۱، ۲، ۳، ۴ …)، جدول امتیازات، تاریخچه بازی
- **رابط کاربری مدرن، تاریک و واکنش‌گرا** (راست‌به‌چپ فارسی)

---

## 🧱 پشته فناوری

| لایه | فناوری |
|------|--------|
| **Backend** | Python 3.10+, Flask 3.0.3 |
| **Real-Time** | Flask-SocketIO 5.3.6 (async_mode=threading) |
| **Database** | SQLite + Flask-SQLAlchemy |
| **Authentication** | Flask-Login 0.6.3, Werkzeug password hashing |
| **Frontend** | HTML5, CSS3, Vanilla JS, Socket.IO client |

---

## 📁 ساختار پروژه

```
Count Time Game/
├── run.py                  # نقطه‌ی شروع اجرای سرور (create_app + socketio.run)
├── config.py               # تنظیمات (Dev / Prod / Testing)
├── requirements.txt        # تمام وابستگی‌های pip
├── .env                    # متغیرهای محیطی (DATABASE_URL، ROOM_CAPACITY و …)
└── app/
    ├── __init__.py         # Application Factory — ساخت نمونه Flask
    ├── extensions.py       # Singletonها: db, login_manager, socketio, csrf
    ├── models.py           # مدل‌های SQLAlchemy: User, Game, GamePlayer
    ├── pages/
    │   ├── routes/         # روت‌های HTTP (Blueprintها)
    │   │   ├── __init__.py     # جمع‌آوری ۵ Blueprint
    │   │   ├── home.py         # صفحه اصلی
    │   │   ├── login_register.py  # ثبت‌نام / ورود / خروج
    │   │   ├── dashboard_and_room.py  # داشبورد، ایجاد Room، /results/<game_id>
    │   │   ├── leaderboard_and_History.py  # جدول امتیازات + تاریخچه
    │   │   └── API.py          # APIهای JSON (/api/leaderboard)
    │   ├── socket_on/       # Eventهای Socket.IO + مدیریت وضعیت بازی
    │   │   ├── __init__.py     # تمام handlerها (connect, join, start, stop, guess, finalize, ping)
    │   │   └── room_manager.py  # Room/PlayerState + timing + winner logic (Thread-safe)
    │   └── templates/        # صفحه‌های HTML (Jinja2)
    └── static/
        ├── css/            # استایل‌ها (responsive, ۷۶۸px breakpoint)
        └── js/             # Logic کلاینت (game.js)
```

---

## ⚙️ نصب و اجرا

### ۱. ساخت محیط مجازی

```bash
python -m venv .venv
```

فعال‌سازی در ویندوز:

```bash
.venv\Scripts\activate
```

### ۲. نصب وابستگی‌ها

```bash
pip install -r requirements.txt
```

### ۳. تنظیمات محیطی

فایل `.env` را بسازید (یا از مقادیر پیش‌فرض استفاده کنید). پیش‌فرض از SQLite استفاده می‌شود:

```env
DATABASE_URL=sqlite:///count_time_game.db
ROOM_CAPACITY=8
ROOM_CODE_LENGTH=6
SECRET_KEY=count-time-game-dev-secret
SOCKETIO_ASYNC_MODE=threading
SOCKETIO_PING_TIMEOUT=30
SOCKETIO_PING_INTERVAL=10
```

### ۴. اجرای برنامه

```bash
python run.py
```

سرور روی `http://0.0.0.0:5000` اجرا می‌شود. مرورگر را باز کنید: [http://localhost:5000](http://localhost:5000)

---

## 🎮 نحوه بازی

### مرحله ۱: ورود و ثبت‌نام
1. روی «ورود» یا «ثبت‌نام» کلیک کنید.
2. اگر هنوز اکانت ندارید، ثبت‌نام کنید (نام کاربری، رمز عبور).
3. به داشبورد هدایت می‌شوید.

### مرحله ۲: ایجاد/.هم‌شار شدن اتاق
1. از داشبورد، روی **«ایجاد اتاق»** کلیک کنید.
2. کد اتاق یکتایی (۶ کاراکتر از `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`) ساخته می‌شود.
3. کد را برای دوستان خود ارسال کنید (یا خودتان با یک بستر دیگر وارد شوید).

### مرحله ۳: شروع بازی (میزبان)
1. وقتی همه بازیکن وارد اتاق شدند، میزبان روی **«شروع بازی»** می‌زند.
2. بازی وارد فاز **RUNNING** می‌شود.
3. نوبت بازیکنان به‌صورت انجامی پیش می‌رود (۱ → ۲ → ۳ → ۴).

### مرحله ۴: ثبت زمان (هر بازیکن)
1. **بازیکن نوبت‌دار** روی **«شروع»** می‌زند.
   - سرور زمان شروع را با `time.perf_counter()` ثبت می‌کند.
   - **بازیکن زمان واقعی خود را نمی‌بیند** (مخفی می‌شود).
2. **بازیکن نوبت‌دار** وقتی خواسته، روی **«توقف»** می‌زند.
   - سرور زمان واقعی سپری‌شده (`elapsed_time`) را حساب می‌کند.
   - زمان به **حریفان** نشان داده می‌شود (بازیکن خودش نمی‌بیند).
3. **بازیکن** مقدار دقیق ثانیه‌های سپری‌شده را در Input وارد می‌کند (حدس).
4. **بازیکنان دیگر** می‌توانند زمان این بازیکن را زنده ببینند.

### مرحله ۵: حدس کردن و نوبت بعدی
1. حدس بازیکن ثبت می‌شود → `guess_diff` (= `|guessed_time - elapsed_time|`) محاسبه می‌شود.
2. نوبت به بازیکن بعدی منتقل می‌شود (اتوماتیک).
3. همه بازیکنان باید Stop کنند و حدس بزنند.

### مرحله ۶: پایان بازی و نتایج
1. وقتی `all_turns_done=True` شد، بازی نهایی می‌شود (`_finalize_game`).
2. **برنده**: نفر اول که `guess_diff` کمترین مقدار را دارد.
3. صفحه **نتایج نهایی** باز می‌شود شامل:
   - **کارت برنده** (🏆)
   - **زمان درست** (مرجع = میانگین زمان‌های واقعی همه بازیکنان)
   - **جدول رتبه‌بندی** (۱ → ۴): رتبه، نام بازیکن، زمان واقعی، زمان حدس شده شده، اختلاف، وضعیت
   - **کمک**: دکمه بازی دوباره / داشبورد / جدول امتیازات

---

## 🛠️ توسعه

اگر می‌خواهید پروژه را تغییر دهید یا گسترش دهید:

- **وارد کردن اینترنت**: `pip install -r requirements.txt` را دوباره اجرا کنید.
- **تغییر تنظیمات**: `config.py` را ویرایش کنید (Dev/Prod/Test).
- **اضافه کردن API جدید**: `app/pages/routes/API.py` را بررسی کنید.
- **تغییر نموذج دیتابیس**: `app/models.py` را ویرایش کنید و بعد `python run.py` را اجرا کنید (یا `flask db migrate` اگر Alembic نصب باشد).
- **افزایش oldal‌های Socket.IO**: `app/pages/socket_on/__init__.py` را باز کنید.

---

## 📄 مجوز

این پروژه تحت **MIT License** منتشر شده است. شما آزادید استفاده، تغییر و توزیع کنید — تنها شرط حفظ اصل منبع و یادداشت مجوز.

---

## 👥 مشارکت

برای گزارش باگ یا پیشنهادی، Issue ایجاد کنید یا Pull Request ارسال کنید. لطفاً از کامنت‌های فارسی در کد به‌گونه‌ای لذت‌بین باشید 🎉
