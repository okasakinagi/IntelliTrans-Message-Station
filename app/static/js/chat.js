/* chat.js — Socket.IO client for IntelliTrans Message Station */
(function () {
  "use strict";

  const socket = io({ transports: ["websocket", "polling"] });

  let currentRoom = "general";

  // ----------------------------------------------------------------
  // DOM refs
  // ----------------------------------------------------------------
  const messageList = document.getElementById("messageList");
  const messageForm = document.getElementById("messageForm");
  const messageInput = document.getElementById("messageInput");
  const currentRoomLabel = document.getElementById("currentRoom");
  const roomItems = document.querySelectorAll(".room-item");

  // ----------------------------------------------------------------
  // Helpers
  // ----------------------------------------------------------------
  function formatTime(ts) {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function appendMessage(msg) {
    const isMe = msg.username === CURRENT_USER;
    const li = document.createElement("li");
    li.className =
      "message-item " + (isMe ? "message--me" : "message--other");

    const meta = document.createElement("div");
    meta.className = "message-meta";
    meta.textContent = isMe
      ? formatTime(msg.timestamp)
      : msg.username + " · " + formatTime(msg.timestamp);

    const text = document.createElement("div");
    text.className = "message-text";
    text.textContent = msg.text;

    li.appendChild(meta);
    li.appendChild(text);
    messageList.appendChild(li);
    messageList.scrollTop = messageList.scrollHeight;
  }

  function appendStatus(text) {
    const li = document.createElement("li");
    li.className = "message-item message--status";
    li.textContent = text;
    messageList.appendChild(li);
    messageList.scrollTop = messageList.scrollHeight;
  }

  function clearMessages() {
    messageList.innerHTML = "";
  }

  function joinRoom(room) {
    if (room === currentRoom) return;
    socket.emit("leave", { room: currentRoom });
    currentRoom = room;
    clearMessages();

    roomItems.forEach((el) => {
      el.classList.toggle("active", el.dataset.room === room);
    });

    const labels = {
      general: "💬 大厅",
      tech: "🛠 技术",
      random: "🎲 随意",
    };
    currentRoomLabel.textContent = labels[room] || room;
    socket.emit("join", { room });
  }

  // ----------------------------------------------------------------
  // Socket events
  // ----------------------------------------------------------------
  socket.on("connect", function () {
    socket.emit("join", { room: currentRoom });
  });

  socket.on("history", function (messages) {
    clearMessages();
    messages.forEach(appendMessage);
  });

  socket.on("new_message", appendMessage);

  socket.on("status", function (data) {
    appendStatus(data.msg);
  });

  socket.on("connect_error", function () {
    appendStatus("⚠️ 连接失败，正在重试…");
  });

  // ----------------------------------------------------------------
  // User interactions
  // ----------------------------------------------------------------
  messageForm.addEventListener("submit", function (e) {
    e.preventDefault();
    const text = messageInput.value.trim();
    if (!text) return;
    socket.emit("send_message", { room: currentRoom, text });
    messageInput.value = "";
  });

  roomItems.forEach(function (item) {
    item.addEventListener("click", function () {
      joinRoom(item.dataset.room);
    });
  });
})();
