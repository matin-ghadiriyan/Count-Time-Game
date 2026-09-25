/**
 * static/js/game.js — منطق کلاینت بازی Count Time Game
 *
 * مسئولیت‌ها:
 *   - اتصال به Socket.IO و عضویت در Room
 *   - مدیریت UI (لیست بازیکنان، وضعیت بازی، دکمه‌ها)
 *   - نمایش Timer به‌صورت محلی (بدون دریافت مکرر از سرور)
 *   - ارسال Eventهای start_game و stop_game
 *   - نمایش نتیجه‌ی نهایی که از سرور می‌آید
 *
 * نکته‌ی مهم:
 *   این فایل هرگز زمان را محاسبه نمی‌کند؛ فقط زمان سپری‌شده را
 *   برای نمایش محلی نشان می‌دهد. مقدار نهایی از سرور می‌آید.
 */

(function () {
  "use strict";

  // --- خواندن اطلاعات تزریق‌شده از قالب ---
  const root = document.querySelector(".game-wrap");
  if (!root) return;

  const roomCode = root.dataset.roomCode;
  const username = root.dataset.username;

  // --- ارجاع به عناصر UI ---
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
  };

  // --- وضعیت محلی کلاینت ---
  const local = {
    myUserId: null,
    isHost: false,
    gameState: "WAITING",
    hasStarted: false,
    hasStopped: false,
    rafId: null,
    localStart: 0,
  };

  // ================================================================
  // ابزارهای UI
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

      const name = document.createElement("span");
      name.className = "player-name";
      name.textContent = p.username + (p.user_id === local.myUserId ? " (شما)" : "");

      const status = document.createElement("span");
      status.className = "player-status";
      if (!p.connected) {
        status.textContent = "قطع";
      } else if (p.has_stopped) {
        status.textContent = "✓ ثبت شد";
      } else if (p.has_started) {
        status.textContent = "⏱ در حال اجرا";
      } else {
        status.textContent = "منتظر";
      }

      li.appendChild(name);
      li.appendChild(status);
      els.playersList.appendChild(li);
    });
  }

  // ================================================================
  // Timer محلی (فقط برای نمایش؛ نتیجه‌ی واقعی از سرور می‌آید)
  // ================================================================
  function startLocalTimer() {
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
  // به‌روزرسانی دکمه‌ها بر اساس وضعیت
  // ================================================================
  function refreshControls() {
    const running = local.gameState === "RUNNING";

    els.startBtn.disabled = !running || local.hasStarted || local.hasStopped;
    els.stopBtn.disabled = !running || !local.hasStarted || local.hasStopped;

    els.startBtn.classList.toggle("is-active", running && !local.hasStarted && !local.hasStopped);
    els.stopBtn.classList.toggle("is-active", running && local.hasStarted && !local.hasStopped);
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
    // پس از اتصال، درخواست عضویت در Room ارسال می‌شود.
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
    els.timerDisplay.textContent = "0.000";
    refreshControls();
  });

  socket.on("player_started", (data) => {
    if (data.user_id === local.myUserId) {
      local.hasStarted = true;
      setHint("زمان در حال ثبت است… حالا Stop کن!");
      startLocalTimer();
      refreshControls();
    }
  });

  socket.on("player_stopped", (data) => {
    if (data.user_id === local.myUserId) {
      local.hasStopped = true;
      stopLocalTimer();
      els.timerDisplay.textContent = formatTime(data.elapsed_time);
      setHint(`زمان ثبت‌شده‌ی تو: ${formatTime(data.elapsed_time)} ثانیه`);
      refreshControls();
    }
  });

  socket.on("game_finished", (data) => {
    setState("FINISHED");
    stopLocalTimer();

    // --- بنر نتیجه ---
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

    // --- لیست نتایج ---
    els.resultsPanel.hidden = false;
    els.resultsList.innerHTML = "";
    (data.results || []).forEach((r, index) => {
      const li = document.createElement("li");
      li.className = "result-item" + (r.result === "WINNER" ? " result-item--winner" : "");

      const rank = document.createElement("span");
      rank.className = "result-rank";
      rank.textContent = index + 1;

      const name = document.createElement("span");
      name.className = "result-name";
      name.textContent = r.username;

      const time = document.createElement("span");
      time.className = "result-time";
      time.textContent = formatTime(r.time) + "s";

      li.appendChild(rank);
      li.appendChild(name);
      li.appendChild(time);
      els.resultsList.appendChild(li);
    });

    setHint("بازی تمام شد. برای بازی جدید یک Room تازه بساز.");
    els.startBtn.disabled = true;
    els.stopBtn.disabled = true;
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
  // رویدادهای UI
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

  els.roomCodeBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(roomCode);
      els.roomCodeBtn.classList.add("copied");
      setTimeout(() => els.roomCodeBtn.classList.remove("copied"), 1200);
    } catch (e) {
      /* clipboard در دسترس نیست */
    }
  });

  // --- پیش از بستن صفحه، خروج از Room اطلاع داده شود ---
  window.addEventListener("beforeunload", () => {
    socket.emit("leave_room", { room_code: roomCode });
  });

  refreshControls();
})();
