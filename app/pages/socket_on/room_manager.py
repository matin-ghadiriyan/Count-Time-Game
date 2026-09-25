"""
app/pages/socket_on/room_manager.py — In-memory room state management.

Responsibilities of this file:
    - Keep the current state of each Room (players, game state, timings)
    - Atomic Room operations: create, join, leave, Start/Stop, finish game
    - Compute elapsed time with time.perf_counter (monotonic)

Why is this file needed?
    The live game state (who started, when) must not be stored in the
    database because it changes on every click and would put pressure on
    the DB. The database only keeps the final result. This is the common
    pattern in real-time games: state in memory, result in the DB.

Important note:
    This structure is thread-safe because with async_mode="threading"
    multiple events may run at the same time. The global lock prevents
    race conditions.
"""

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime


class RoomState:
    """Possible states of a Room. String values for easy client transport."""

    WAITING = "WAITING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"


@dataclass
class PlayerState:
    """State of a player in a game round.

    start_time and stop_time are recorded with time.perf_counter(), a
    monotonic clock that is not affected by system clock changes.
    """

    user_id: int
    username: str
    sid: str | None = None
    start_time: float | None = None
    stop_time: float | None = None
    elapsed_time: float | None = None
    guessed_time: float | None = None
    guess_diff: float | None = None
    result: str = "NO_RESULT"
    connected: bool = True

    @property
    def has_started(self) -> bool:
        return self.start_time is not None

    @property
    def has_stopped(self) -> bool:
        return self.stop_time is not None

    @property
    def has_guessed(self) -> bool:
        return self.guessed_time is not None


@dataclass
class Room:
    """A game room. room_code is also used as the SocketIO room identifier."""

    code: str
    host_id: int
    capacity: int = 8
    state: str = RoomState.WAITING
    players: dict[int, PlayerState] = field(default_factory=dict)
    game_db_id: int | None = None
    created_at: float = field(default_factory=time.perf_counter)
    turn_order: list[int] = field(default_factory=list)
    current_turn_index: int = 0

    def current_player_id(self) -> int | None:
        """ID of the player whose turn it is."""
        if not self.turn_order:
            return None
        if self.current_turn_index >= len(self.turn_order):
            return None
        return self.turn_order[self.current_turn_index]

    def advance_turn(self) -> int | None:
        """Move to the next turn. Returns None if no turns remain."""
        self.current_turn_index += 1
        return self.current_player_id()

    def all_turns_done(self) -> bool:
        """Have all turns finished?"""
        if not self.turn_order:
            return False
        return self.current_turn_index >= len(self.turn_order)

    def build_turn_order(self) -> None:
        """Build the turn order based on the current connected players."""
        self.turn_order = [
            p.user_id for p in self.players.values() if p.connected
        ]
        self.current_turn_index = 0

    def is_full(self) -> bool:
        return len(self.players) >= self.capacity

    def all_stopped(self) -> bool:
        """Have all connected players stopped?"""
        active = [p for p in self.players.values() if p.connected]
        if not active:
            return False
        return all(p.has_stopped for p in active)

    def all_guessed(self) -> bool:
        """Have all players who stopped submitted their time guess?"""
        stopped = [
            p for p in self.players.values() if p.connected and p.has_stopped
        ]
        if not stopped:
            return False
        return all(p.has_guessed for p in stopped)

    def public_players(self) -> list[dict]:
        """Client-safe player info (without exposing internal timings)."""
        return [
            {
                "user_id": p.user_id,
                "username": p.username,
                "has_started": p.has_started,
                "has_stopped": p.has_stopped,
                "has_guessed": p.has_guessed,
                "connected": p.connected,
                "is_current_turn": p.user_id == self.current_player_id(),
            }
            for p in self.players.values()
        ]


class RoomManager:
    """Central manager for all rooms. A module-level singleton is created."""

    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._lock = threading.RLock()

    # ---------------- Room management ----------------
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
        """Find a Room by connection SID (for disconnect handling)."""
        with self._lock:
            for room in self._rooms.values():
                for player in room.players.values():
                    if player.sid == sid:
                        return room
        return None

    # ---------------- Membership ----------------
    def join(
        self, code: str, user_id: int, username: str, sid: str, capacity: int = 8
    ) -> tuple[Room | None, str | None]:
        """Join a user to a Room. Returns: (room, error_message)."""
        with self._lock:
            room = self._rooms.get(code)
            if room is None:
                # If the Room does not exist, it is created with the user as host.
                room = self.create_room(code, host_id=user_id, capacity=capacity)

            existing = room.players.get(user_id)
            if existing is not None:
                # The user is already a member; just refresh the SID (page refresh).
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
        """Remove a user from a Room. The Room is deleted if it becomes empty."""
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
        """Record a player's start time. Only the player whose turn it is can start.

        Returns: (start_time, error_message).
        """
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
            if room.current_player_id() != user_id:
                return None, "الان نوبت شما نیست."

            player.start_time = time.perf_counter()
            return player.start_time, None

    def stop_player(self, code: str, user_id: int) -> tuple[float | None, str | None]:
        """Record the stop time and compute the elapsed time. Returns: (elapsed, error_message)."""
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
            # Time is computed on the server; the client has no part in this value.
            player.elapsed_time = round(player.stop_time - player.start_time, 3)
            return player.elapsed_time, None

    def visible_elapsed(self, room: Room, viewer_id: int) -> dict[int, float]:
        """Elapsed time of each player for display to a viewer.

        Important rule: the player whose turn it is must not see their own
        time; only opponents may see it. So the current player's time is
        removed from that viewer's output.
        """
        current = room.current_player_id()
        result: dict[int, float] = {}
        for p in room.players.values():
            if p.elapsed_time is None:
                continue
            # The player whose turn it is does not see their own time.
            if p.user_id == viewer_id and p.user_id == current:
                continue
            result[p.user_id] = p.elapsed_time
        return result

    # ---------------- Time guess submission ----------------
    def submit_guess(
        self, code: str, user_id: int, guessed_time: float
    ) -> tuple[float | None, str | None]:
        """Record a player's time guess and compute the difference from the real time.

        After the guess is recorded, the turn moves to the next player.
        Returns: (guess_diff, error_message)
        """
        with self._lock:
            room = self._rooms.get(code)
            if room is None:
                return None, "Room یافت نشد."

            player = room.players.get(user_id)
            if player is None:
                return None, "شما عضو این Room نیستید."
            if not player.has_stopped:
                return None, "ابتدا باید دکمه‌ی توقف را بزنید."
            if player.has_guessed:
                return None, "قبلاً حدس خود را ثبت کرده‌اید."
            if guessed_time < 0:
                return None, "زمان حدس نمی‌تواند منفی باشد."

            player.guessed_time = round(float(guessed_time), 3)
            player.guess_diff = round(
                abs(player.guessed_time - (player.elapsed_time or 0.0)), 3
            )
            return player.guess_diff, None

    def advance_turn(self, code: str) -> tuple[int | None, bool]:
        """Advance the turn to the next player.

        Returns: (current_player_id, all_done)
        """
        with self._lock:
            room = self._rooms.get(code)
            if room is None:
                return None, True
            room.advance_turn()
            return room.current_player_id(), room.all_turns_done()

    # ---------------- Game end ----------------
    def determine_winner(self, room: Room) -> tuple[int | None, list[dict]]:
        """Determine the winner by the closest guess to the real time.

        Rules:
            - Only players who started, stopped, and guessed are valid.
            - The smallest difference (guess_diff) wins.
            - If there are fewer than 2 valid players, no winner is set.
        Returns: (winner_user_id, results_list)
        """
        valid_players = [
            p
            for p in room.players.values()
            if p.has_started
            and p.has_stopped
            and p.elapsed_time is not None
            and p.guess_diff is not None
        ]
        valid_players.sort(key=lambda p: p.guess_diff if p.guess_diff is not None else float("inf"))

        results = [
            {
                "user_id": p.user_id,
                "username": p.username,
                "time": p.elapsed_time,
                "guess": p.guessed_time,
                "diff": p.guess_diff,
                "rank": index + 1,
                "result": "WINNER" if index == 0 else "LOSER",
            }
            for index, p in enumerate(valid_players)
        ]

        if len(valid_players) < 2:
            return None, results

        winner = valid_players[0]
        # Store the final result on the PlayerState objects themselves
        for p in valid_players:
            p.result = "WINNER" if p is winner else "LOSER"

        return winner.user_id, results

    def mark_disconnected(self, code: str, user_id: int) -> Room | None:
        """Mark a player as disconnected (without removing them from the Room)."""
        with self._lock:
            room = self._rooms.get(code)
            if room is None:
                return None
            player = room.players.get(user_id)
            if player is not None:
                player.connected = False
                player.sid = None
            return room


# Singleton instance; imported by all Socket handlers.
room_manager = RoomManager()
