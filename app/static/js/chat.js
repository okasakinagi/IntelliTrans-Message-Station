/* chat.js — IntelliTrans 消息站前端 Socket.IO 客户端 */
(function () {
  "use strict";

  // 建立 Socket.IO 连接，优先使用 WebSocket，降级时回退到长轮询
  const socket = io({ transports: ["websocket", "polling"] });

  // 当前所在房间，默认为"大厅"
  let currentRoom = "general";

  // ----------------------------------------------------------------
  // 获取页面 DOM 元素引用
  // ----------------------------------------------------------------
  const messageList = document.getElementById("messageList");       // 消息列表容器
  const messageForm = document.getElementById("messageForm");       // 发送消息表单
  const messageInput = document.getElementById("messageInput");     // 消息输入框
  const currentRoomLabel = document.getElementById("currentRoom");  // 当前房间标题
  const roomItems = document.querySelectorAll(".room-item");        // 侧边栏频道列表项

  // ----------------------------------------------------------------
  // 工具函数
  // ----------------------------------------------------------------

  /**
   * 将 Unix 时间戳（秒）格式化为本地时间字符串（时:分）。
   */
  function formatTime(ts) {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  /**
   * 将一条消息追加到消息列表，自己发的消息右对齐，他人消息左对齐。
   * 使用 textContent 赋值，避免 XSS 风险。
   */
  function appendMessage(msg) {
    const isMe = msg.username === CURRENT_USER;
    const li = document.createElement("li");
    li.className =
      "message-item " + (isMe ? "message--me" : "message--other");

    // 消息元信息（发送者 + 时间）
    const meta = document.createElement("div");
    meta.className = "message-meta";
    meta.textContent = isMe
      ? formatTime(msg.timestamp)
      : msg.username + " · " + formatTime(msg.timestamp);

    // 消息正文
    const text = document.createElement("div");
    text.className = "message-text";
    text.textContent = msg.text;

    li.appendChild(meta);
    li.appendChild(text);
    messageList.appendChild(li);
    // 自动滚动到最新消息
    messageList.scrollTop = messageList.scrollHeight;
  }

  /**
   * 追加系统状态通知（如用户进入/离开房间），居中显示。
   */
  function appendStatus(text) {
    const li = document.createElement("li");
    li.className = "message-item message--status";
    li.textContent = text;
    messageList.appendChild(li);
    messageList.scrollTop = messageList.scrollHeight;
  }

  /**
   * 清空消息列表，切换房间时调用。
   */
  function clearMessages() {
    messageList.innerHTML = "";
  }

  /**
   * 切换到指定房间：通知服务端离开旧房间、加入新房间，并更新 UI。
   */
  function joinRoom(room) {
    if (room === currentRoom) return; // 已在目标房间，无需切换
    socket.emit("leave", { room: currentRoom }); // 离开当前房间
    currentRoom = room;
    clearMessages();

    // 更新侧边栏高亮
    roomItems.forEach((el) => {
      el.classList.toggle("active", el.dataset.room === room);
    });

    // 更新顶部房间标题
    const labels = {
      general: "💬 大厅",
      tech: "🛠 技术",
      random: "🎲 随意",
    };
    currentRoomLabel.textContent = labels[room] || room;
    socket.emit("join", { room }); // 加入新房间，服务端会推送历史记录
  }

  // ----------------------------------------------------------------
  // Socket.IO 服务端事件监听
  // ----------------------------------------------------------------

  // 连接成功后自动加入默认房间
  socket.on("connect", function () {
    socket.emit("join", { room: currentRoom });
  });

  // 收到房间历史记录（切换房间时触发）
  socket.on("history", function (messages) {
    clearMessages();
    messages.forEach(appendMessage);
  });

  // 收到新消息（实时广播）
  socket.on("new_message", appendMessage);

  // 收到系统状态通知（用户进出房间）
  socket.on("status", function (data) {
    appendStatus(data.msg);
  });

  // 连接失败时给出提示
  socket.on("connect_error", function () {
    appendStatus("⚠️ 连接失败，正在重试…");
  });

  // ----------------------------------------------------------------
  // 用户交互事件
  // ----------------------------------------------------------------

  // 提交表单发送消息
  messageForm.addEventListener("submit", function (e) {
    e.preventDefault();
    const text = messageInput.value.trim();
    if (!text) return; // 忽略空消息
    socket.emit("send_message", { room: currentRoom, text });
    messageInput.value = ""; // 清空输入框
  });

  // 点击侧边栏频道切换房间
  roomItems.forEach(function (item) {
    item.addEventListener("click", function () {
      joinRoom(item.dataset.room);
    });
  });
})();
