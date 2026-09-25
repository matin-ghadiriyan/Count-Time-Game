"""
app/pages/socket_on/room_manager.py — مدیریت وضعیت Roomها در حافظه‌ی سرور

مسئولیت این فایل:
    - نگه‌داری وضعیت جاری هر Room (بازیکنان، وضعیت بازی، زمان‌ها)
    - عملیات اتمی روی Room: ساخت، عضویت، خروج، Start/Stop، پایان بازی
    - محاسبه‌ی زمان با time.perf_counter (monotonic)

چرا این فایل لازم است؟
    وضعیت لحظه‌ای بازی (چه کسی Start کرده، چه زمانی) نباید در دیتابیس
    ذخیره شود چون به‌ازای هر کلیک تغییر می‌کند و باعث فشار روی DB می‌شود.
    دیتابیس فقط نتیجه‌ی نهایی را نگه می‌دارد. این الگوی رایج در بازی‌های
    Real-Time است: State در حافظه، Result در DB.

نکته‌ی مهم:
    این ساختار Thread-Safe است چون در async_mode="threading" ممکن است
    چند Event همزمان اجرا شوند. قفل سراسری از Race Condition جلوگیری می‌کند.
"""

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime


class RoomState:
    """وضعیت‌های ممکن یک Room. مقادیر رشته‌ای برای ارسال ساده به Client."""

    WAITING = "WAITING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"


@dataclass
class PlayerState:
    """وضعیت یک بازیکن در یک راند بازی.

    start_time و stop_time با time.perf_counter() ثبت می‌شوند که یک ساعت
    monotonic است و تحت تأثیر تغییر ساعت سیستم قرار نمی‌گیرد.
    """

    user_id: int
    username: str
    sid: str | None = None
    start_time: float | None = None
    stop_time: float | None = None
    elapsed_time: float | None = None
    result: str = "NO_RESULT"
    connected: bool = True

    @property
    def has_started(self) -> bool:
        return self.start_time is not None

    @property
    def has_stopped(self) -> bool:
        return self.stop_time is not None


@dataclass
class Room:
    """یک اتاق بازی. room_code هم‌زمان به‌عنوان شناسه‌ی SocketIO Room استفاده می‌شود."""

    code: str
    host_id: int
    capacity: int = 8
    state: str = RoomState.WAITING
    players: dict[int, PlayerState] = field(default_factory=dict)
    game_db_id: int | None = None
    created_at: float = field(default_factory=time.perf_counter)

    def is_full(self) -> bool:
        return len(self.players) >= self.capacity

    def all_stopped(self) -> bool:
        """آیا همه‌ی بازیکنانِ متصل، Stop کرده‌اند؟"""
        active = [p for p in self.players.values() if p.connected]
        if not active:
            return False
        return all(p.has_stopped for p in active)

    def public_players(self) -> list[dict]:
        """اطلاعات قابل‌ارسال به Client (بدون افشای زمان‌های داخلی)."""
        return [
            {
                "user_id": p.user_id,
                "username": p.username,
                "has_started": p.has_started,
                "has_stopped": p.has_stopped,
                "connected": p.connected,
            }
            for p in self.players.values()
        ]


class RoomManager:
    """مدیریت متمرکز همه‌ی Roomها. یک نمونه‌ی Singleton در سطح ماژول ساخته می‌شود."""

    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._lock = threading.RLock()

    # ---------------- مدیریت Room ----------------
    def create_room(self, code: str, host_id: int, capacity: int = 8) -> Room:
        with self._lock:
            room = self._rooms.get(code)
            if room is None:
                room = Room(code=code, host_id=host_id, capacity=capacity)
                self._rooms[code] = room
            return room

    def get_room(self, code: str) -> Room | None:
        with self._lock:
            return self._rooms.get(code)

    def remove_room(self, code: str) -> None:
        with self._lock:
            self._rooms.pop(code, None)

    def find_room_by_sid(self, sid: str) -> Room | None:
        """پیدا کردن Room بر اساس SID اتصال (برای مدیریت Disconnect)."""
        with self._lock:
            for room in self._rooms.values():
                for player in room.players.values():
                    if player.sid == sid:
                        return room
        return None

    # ---------------- عضویت ----------------
    def join(
        self, code: str, user_id: int, username: str, sid: str, capacity: int = 8
    ) -> tuple[Room | None, str | None]:
        """ورود کاربر به Room. خروجی: (room, error_message)."""
        with self._lock:
            room = self._rooms.get(code)
            if room is None:
                # اگر Room وجود ندارد، به‌عنوان میزبان ساخته می‌شود.
                room = self.create_room(code, host_id=user_id, capacity=capacity)

            existing = room.players.get(user_id)
            if existing is not None:
                # کاربر قبلاً عضو است؛ فقط SID را به‌روز می‌کنیم (رفرش صفحه).
                existing.sid = sid
                existing.connected = True
                return room, None

            if room.is_full():
                return None, "ظرفیت این Room تکمیل است."

            if room.state == RoomState.RUNNING:
                return None, "بازی در این Room در حال اجراست."

            room.players[user_id] = PlayerState(
                user_id=user_id, username=username, sid=sid
            )
            return room, None

    def leave(self, code: str, user_id: int) -> Room | None:
        """خروج کاربر از Room. اگر Room خالی شد حذف می‌شود."""
        with self._lock:
            room = self._rooms.get(code)
            if room is None:
                return None
            room.players.pop(user_id, None)
            if not room.players:
                self._rooms.pop(code, None)
                return None
            return room

    # ---------------- Start / Stop ----------------
    def start_player(self, code: str, user_id: int) -> tuple[float | None, str | None]:
        """ثبت زمان شروع بازیکن. خروجی: (start_time, error_message)."""
        with self._lock:
            room = self._rooms.get(code)
            if room is None:
                return None, "Room یافت نشد."
            if room.state != RoomState.RUNNING:
                return None, "بازی در وضعیت اجرا نیست."

            player = room.players.get(user_id)
            if player is None:
                return None, "شما عضو این Room نیستید."
            if player.has_started:
                return None, "قبلاً بازی را شروع کرده‌اید."

            player.start_time = time.perf_counter()
            return player.start_time, None

    def stop_player(self, code: str, user_id: int) -> tuple[float | None, str | None]:
        """ثبت زمان توقف و محاسبه‌ی زمان سپری‌شده. خروجی: (elapsed, error_message)."""
        with self._lock:
            room = self._rooms.get(code)
            if room is None:
                return None, "Room یافت نشد."
            if room.state != RoomState.RUNNING:
                return None, "بازی در وضعیت اجرا نیست."

            player = room.players.get(user_id)
            if player is None:
                return None, "شما عضو این Room نیستید."
            if not player.has_started:
                return None, "ابتدا باید بازی را شروع کنید."
            if player.has_stopped:
                return None, "قبلاً بازی را متوقف کرده‌اید."

            player.stop_time = time.perf_counter()
            # محاسبه‌ی زمان در سرور؛ Client هیچ دخالتی در این مقدار ندارد.
            player.elapsed_time = round(player.stop_time - player.start_time, 3)
            return player.elapsed_time, None

    # ---------------- پایان بازی ----------------
    def determine_winner(self, room: Room) -> tuple[int | None, list[dict]]:
        """تعیین برنده بر اساس کمترین زمان معتبر.

        قوانین:
            - فقط بازیکنانی که هم Start و هم Stop کرده‌اند معتبرند.
            - کمترین elapsed_time برنده است.
            - اگر تعداد معتبرها کمتر از ۲ باشد، برنده‌ای تعیین نمی‌شود.
        خروجی: (winner_user_id, results_list)
        """
        valid_players = [
            p
            for p in room.players.values()
            if p.has_started and p.has_stopped and p.elapsed_time is not None
        ]
        valid_players.sort(key=lambda p: p.elapsed_time or float("inf"))

        results = [
            {
                "user_id": p.user_id,
                "username": p.username,
                "time": p.elapsed_time,
                "result": "WINNER" if p is valid_players[0] else "LOSER",
            }
            for p in valid_players
        ]

        if len(valid_players) < 2:
            return None, results

        winner = valid_players[0]
        # ثبت نتیجه‌ی نهایی روی خودِ PlayerStateها
        for p in valid_players:
            p.result = "WINNER" if p is winner else "LOSER"

        return winner.user_id, results

    def mark_disconnected(self, code: str, user_id: int) -> Room | None:
        """علامت‌گذاری بازیکن به‌عنوان قطع‌شده (بدون حذف از Room)."""
        with self._lock:
            room = self._rooms.get(code)
            if room is None:
                return None
            player = room.players.get(user_id)
            if player is not None:
                player.connected = False
                player.sid = None
            return room


# نمونه‌ی Singleton؛ در همه‌ی Socket Handlerها import می‌شود.
room_manager = RoomManager()
