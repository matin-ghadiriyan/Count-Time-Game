/**
 * static/js/game.js — Client logic for Count Time Game.
 *
 * Responsibilities:
 *   - Connect to Socket.IO and join the Room
 *   - Manage the UI (player list, game state, buttons)
 *   - Display the timer locally (without polling the server)
 *   - Emit the start_game and stop_game events
 *   - Display the final result coming from the server
 *
 * Important note:
 *   This file never computes the real time; it only shows the elapsed
 *   time for local display. The final value comes from the server.
 */

(function () {
  "use strict";

  // --- Read data injected by the template ---
  const root = document.querySelector(".game-wrap");
  if (!root) return;

  const roomCode = root.dataset.roomCode;
  const username = root.dataset.username;

  // --- References to UI elements ---
  const els = {
    stateDot: document.getElementById("state-dot"),
    stateText: document.getElementById("state-text"),
    playersList: document.getElementById("players-list"),
    playerCount: document.getElementById("player-count"),
    timerDisplay: document.getElementById("timer-display"),
    timerHint: document.getElementById("timer-hint"),
    startBtn: document.getElementById("start-btn"),
    stopBtn: document.getElementById("stop-btn"),
    hostControls: document.getElementById("host-controls"),
    beginBtn: document.getElementById("begin-btn"),
    resultBanner: document.getElementById("result-banner"),
    resultsPanel: document.getElementById("results-panel"),
    resultsList: document.getElementById("results-list"),
    roomCodeBtn: document.getElementById("room-code-btn"),
    guessBox: document.getElementById("guess-box"),
    guessInput: document.getElementById("guess-input"),
    guessBtn: document.getElementById("guess-btn"),
    guessFeedback: document.getElementById("guess-feedback"),
  };

  // --- Local client state ---
  const local = {
    myUserId: null,
    isHost: false,
    gameState: "WAITING",
    hasStarted: false,
    hasStopped: false,
    hasGuessed: false,
    isMyTurn: false,
    rafId: null,
    localStart: 0,
  };

  // ================================================================
  // UI helpers
  // ================================================================
  const STATE_LABELS = {
    WAITING: "در انتظار شروع",
    RUNNING: "بازی در جریان است",
    FINISHED: "بازی تمام شد",
  };

  function setState(state) {
    local.gameState = state;
    els.stateText.textContent = STATE_LABELS[state] || state;
    els.stateDot.className = "state-dot state-dot--" + state.toLowerCase();
  }

  function setHint(text) {
    els.timerHint.textContent = text;
  }

  function formatTime(seconds) {
    return Number(seconds).toFixed(3);
  }

  function renderPlayers(players) {
    els.playersList.innerHTML = "";
    els.playerCount.textContent = players.length;

    players.forEach((p) => {
      const li = document.createElement("li");
      li.className = "player-item";

      if (p.user_id === local.myUserId) li.classList.add("player-item--me");
      if (!p.connected) li.classList.add("player-item--offline");
      if (p.has_stopped) li.classList.add("player-item--done");
      if (p.has_guessed) li.classList.add("player-item--guessed");
      if (p.is_current_turn) li.classList.add("player-item--turn");

      const name = document.createElement("span");
      name.className = "player-name";
      name.textContent = p.username + (p.user_id === local.myUserId ? " (شما)" : "");

      const status = document.createElement("span");
      status.className = "player-status";
      if (!p.connected) {
        status.textContent = "قطع";
      } else if (p.has_guessed) {
        status.textContent = "✓ حدس ثبت شد";
      } else if (p.has_stopped) {
        status.textContent = "✎ در انتظار حدس";
      } else if (p.is_current_turn) {
        status.textContent = "🎯 نوبت او";
      } else {
        status.textContent = "منتظر";
      }

      li.appendChild(name);
      li.appendChild(status);
      els.playersList.appendChild(li);
    });
  }

  // ================================================================
  // Local timer (display only; the real result comes from the server)
  // ================================================================
  function startLocalTimer() {
    // The time is not shown to the player whose turn it is; so the local
    // timer only runs for non-turn players (opponents) as a display counter.
    if (local.isMyTurn) return;

    local.localStart = performance.now();

    function tick() {
      const elapsed = (performance.now() - local.localStart) / 1000;
      els.timerDisplay.textContent = formatTime(elapsed);
      local.rafId = requestAnimationFrame(tick);
    }
    stopLocalTimer();
    tick();
  }

  function stopLocalTimer() {
    if (local.rafId !== null) {
      cancelAnimationFrame(local.rafId);
      local.rafId = null;
    }
  }

  // ================================================================
  // Update the buttons based on state
  // ================================================================
  function refreshControls() {
    const running = local.gameState === "RUNNING";
    const turn = local.isMyTurn;

    els.startBtn.disabled = !running || !turn || local.hasStarted || local.hasStopped;
    els.stopBtn.disabled = !running || !turn || !local.hasStarted || local.hasStopped;

    els.startBtn.classList.toggle("is-active", running && turn && !local.hasStarted && !local.hasStopped);
    els.stopBtn.classList.toggle("is-active", running && turn && local.hasStarted && !local.hasStopped);
  }

  // ================================================================
  // Time guess box
  // ================================================================
  function showGuessBox() {
    if (local.hasGuessed) return;
    els.guessBox.hidden = false;
    els.guessInput.disabled = false;
    els.guessBtn.disabled = false;
    els.guessFeedback.hidden = true;
    els.guessInput.value = "";
    els.guessInput.focus();
  }

  function hideGuessBox() {
    els.guessBox.hidden = true;
  }

  // ================================================================
  // Socket.IO
  // ================================================================
  const socket = io({
    transports: ["websocket", "polling"],
    reconnection: true,
    reconnectionDelay: 1000,
  });

  socket.on("connect", () => {
    // After connecting, send a request to join the Room.
    socket.emit("join_room", { room_code: roomCode });
  });

  socket.on("connected", (data) => {
    if (data && data.username) {
      setHint(`خوش آمدی ${data.username}!`);
    }
  });

  socket.on("joined_room", (data) => {
    if (!data.ok) return;
    local.myUserId = data.players.find((p) => p.username === username)?.user_id ?? null;
    local.isHost = data.host_id === local.myUserId;

    els.hostControls.hidden = !local.isHost || data.state !== "WAITING";
    setState(data.state);
    renderPlayers(data.players);
    refreshControls();

    if (data.state === "WAITING") {
      setHint(local.isHost ? "می‌توانی بازی را شروع کنی." : "منتظر شروع بازی توسط میزبان بمان…");
    }
  });

  socket.on("room_state", (data) => {
    setState(data.state);
    renderPlayers(data.players);

    const me = data.players.find((p) => p.user_id === local.myUserId);
    if (me) {
      local.hasStarted = me.has_started;
      local.hasStopped = me.has_stopped;
      local.hasGuessed = me.has_guessed;
      local.isMyTurn = !!me.is_current_turn;
      if (me.has_stopped && !me.has_guessed) {
        showGuessBox();
      }
      if (me.has_guessed) {
        hideGuessBox();
      }
    }

    // Show the current turn
    const turnPlayer = data.players.find((p) => p.is_current_turn);
    if (local.gameState === "RUNNING" && turnPlayer) {
      if (local.isMyTurn) {
        setHint("نوبت توست! دکمه‌ی Start را بزن.");
      } else {
        setHint("نوبت " + turnPlayer.username + " است. زمان او را ببین…");
      }
    }

    // If the game is over and all turns are done, wait for the result
    if (local.gameState === "RUNNING" && !turnPlayer && data.players.length > 0) {
      const allGuessed = data.players.every(
        (p) => !p.connected || p.has_guessed
      );
      if (allGuessed) {
        setHint("همه نوبت‌ها تمام شد. در حال محاسبه‌ی نتیجه…");
      }
    }

    els.hostControls.hidden = !(local.isHost && data.state === "WAITING");
    refreshControls();
  });

  socket.on("game_started", () => {
    setState("RUNNING");
    setHint("دکمه‌ی Start را بزن و در زمان مناسب Stop کن.");
    els.resultBanner.hidden = true;
    els.resultsPanel.hidden = true;
    local.hasStarted = false;
    local.hasStopped = false;
    local.hasGuessed = false;
    hideGuessBox();
    els.timerDisplay.textContent = "—";
    setHint("بازی شروع شد. منتظر نوبتت بمان…");
    refreshControls();
  });

  socket.on("player_started", (data) => {
    if (data.user_id === local.myUserId) {
      local.hasStarted = true;
      // The player whose turn it is does not see their own time; only the Stop button is active.
      els.timerDisplay.textContent = "؟.؟؟؟";
      setHint("زمان مخفی است! هر وقت خواستی Stop بزن.");
    } else {
      // The opponent's time is visible to us.
      setHint(data.username + " شروع کرد… زمان او را ببین.");
      startLocalTimer();
    }
    refreshControls();
  });

  socket.on("opponent_elapsed", (data) => {
    // The opponent's time is visible to us, but they cannot see it themselves.
    if (data.user_id !== local.myUserId) {
      stopLocalTimer();
      els.timerDisplay.textContent = formatTime(data.elapsed_time);
      setHint("⏱ زمان " + data.username + ": " + formatTime(data.elapsed_time) + " ثانیه");
    }
  });

  socket.on("turn_changed", (data) => {
    local.isMyTurn = data.current_player_id === local.myUserId;
    local.hasStarted = false;
    local.hasStopped = false;
    local.hasGuessed = false;
    stopLocalTimer();
    hideGuessBox();
    els.timerDisplay.textContent = "—";
    if (data.all_done) {
      setHint("همه نوبت‌ها تمام شد. در حال محاسبه‌ی نتیجه…");
    } else if (local.isMyTurn) {
      setHint("نوبت توست! Start را بزن.");
    } else {
      setHint("منتظر بمان تا نوبتت شود…");
    }
    refreshControls();
  });

  socket.on("player_stopped", (data) => {
    if (data.user_id === local.myUserId) {
      local.hasStopped = true;
      stopLocalTimer();
      // The time is not shown to the user; they must guess it.
      els.timerDisplay.textContent = "؟.؟؟؟";
      setHint("حالا حدس بزن چند ثانیه گذشت!");
      showGuessBox();
      refreshControls();
    } else {
      // The opponent stopped; their time was shown to us (via opponent_elapsed).
      setHint(data.username + " Stop کرد.");
    }
  });

  socket.on("player_guessed", (data) => {
    if (data.user_id === local.myUserId) {
      local.hasGuessed = true;
      hideGuessBox();
      els.guessFeedback.hidden = false;
      els.guessFeedback.textContent =
        "حدس ثبت شد. اختلاف تو با زمان واقعی: " +
        formatTime(data.guess_diff) +
        " ثانیه";
      setHint("منتظر بمان تا نوبت بعدی شروع شود…");
      refreshControls();
    }
  });

  socket.on("game_finished", (data) => {
    setState("FINISHED");
    stopLocalTimer();

    // --- Result banner ---
    if (data.winner) {
      els.resultBanner.hidden = false;
      els.resultBanner.className = "result-banner result-banner--show";
      els.resultBanner.innerHTML =
        '🏆 برنده: <strong>' + data.winner + "</strong>";
    } else {
      els.resultBanner.hidden = false;
      els.resultBanner.className = "result-banner result-banner--muted";
      els.resultBanner.textContent = "برنده‌ای تعیین نشد.";
    }

    // --- Results list ---
    els.resultsPanel.hidden = false;
    els.resultsList.innerHTML = "";
    (data.results || []).forEach((r, index) => {
      const li = document.createElement("li");
      li.className = "result-item" + (r.result === "WINNER" ? " result-item--winner" : "");

      const rank = document.createElement("span");
      rank.className = "result-rank";
      rank.textContent = r.rank !== undefined ? r.rank : index + 1;

      const name = document.createElement("span");
      name.className = "result-name";
      name.textContent = r.username;

      const detail = document.createElement("span");
      detail.className = "result-time";
      const realTime = formatTime(r.time);
      const guessTime = r.guess !== null && r.guess !== undefined ? formatTime(r.guess) : "—";
      const diffTime = r.diff !== null && r.diff !== undefined ? formatTime(r.diff) : "—";
      detail.textContent = `واقعی ${realTime}s · حدس ${guessTime}s · اختلاف ${diffTime}s`;

      li.appendChild(rank);
      li.appendChild(name);
      li.appendChild(detail);
      els.resultsList.appendChild(li);
    });

    setHint("بازی تمام شد. رتبه‌بندی نهایی بر اساس نزدیک‌ترین حدس نمایش داده شد.");
    els.startBtn.disabled = true;
    els.stopBtn.disabled = true;
    hideGuessBox();

    // --- Redirect to the final results page ---
    // After a short pause, the user goes to the dedicated results page that
    // shows the correct time, the players' times, the differences, and the
    // ranked table (1, 2, 3, 4).
    const gameId = data.game_id;
    if (gameId) {
      setTimeout(() => {
        window.location.href = "/results/" + gameId;
      }, 1800);
    }
  });

  socket.on("player_disconnected", (data) => {
    console.warn("بازیکن قطع شد:", data.username);
  });

  socket.on("player_left", (data) => {
    console.info("بازیکن خارج شد:", data.username);
  });

  socket.on("error", (data) => {
    if (data && data.message) {
      setHint("⚠️ " + data.message);
    }
  });

  socket.on("disconnect", () => {
    setState("WAITING");
    setHint("اتصال قطع شد. در حال تلاش برای اتصال مجدد…");
    stopLocalTimer();
  });

  // ================================================================
  // UI events
  // ================================================================
  els.beginBtn.addEventListener("click", () => {
    socket.emit("start_game", { room_code: roomCode, action: "begin" });
  });

  els.startBtn.addEventListener("click", () => {
    if (els.startBtn.disabled) return;
    socket.emit("start_game", { room_code: roomCode, action: "self" });
  });

  els.stopBtn.addEventListener("click", () => {
    if (els.stopBtn.disabled) return;
    socket.emit("stop_game", { room_code: roomCode });
  });

  function submitGuess() {
    if (els.guessBtn.disabled) return;
    const raw = els.guessInput.value.trim();
    const value = Number(raw);
    if (raw === "" || Number.isNaN(value) || value < 0) {
      els.guessFeedback.hidden = false;
      els.guessFeedback.textContent = "یک عدد معتبر و نامنفی وارد کن.";
      return;
    }
    els.guessBtn.disabled = true;
    els.guessInput.disabled = true;
    socket.emit("submit_guess", { room_code: roomCode, guessed_time: value });
  }

  els.guessBtn.addEventListener("click", submitGuess);
  els.guessInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submitGuess();
    }
  });

  els.roomCodeBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(roomCode);
      els.roomCodeBtn.classList.add("copied");
      setTimeout(() => els.roomCodeBtn.classList.remove("copied"), 1200);
    } catch (e) {
      /* clipboard is not available */
    }
  });

  // --- Notify Room exit before the page is closed ---
  window.addEventListener("beforeunload", () => {
    socket.emit("leave_room", { room_code: roomCode });
  });

  refreshControls();
})();
