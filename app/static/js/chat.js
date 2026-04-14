/* chat.js — IntelliTrans 消息站前端 Socket.IO 客户端 */
(function () {
  "use strict";

  // 建立 Socket.IO 连接，优先使用 WebSocket，降级时回退到长轮询
  const hasSocketClient = typeof io === "function";
  const socket = hasSocketClient
    ? io({
      transports: ["websocket", "polling"],
      auth: { username: CURRENT_USER },
    })
    : {
      connected: false,
      emit: function () { },
      on: function () { },
    };

  // 当前会话上下文
  let currentRoom = "general";
  let currentRoomType = "group";
  let currentPeer = "";

  let groupRooms = [];
  let privateRooms = [];

  const dmPeerByRoom = {};
  const manualTranslationByMessageId = {};
  let pendingTranslation = null;
  let fallbackPollingStarted = false;
  let historyPollingTimer = null;
  let rosterPollingTimer = null;
  let lastHistorySignature = "";

  // ----------------------------------------------------------------
  // 获取页面 DOM 元素引用
  // ----------------------------------------------------------------
  const messageList = document.getElementById("messageList");
  const messageForm = document.getElementById("messageForm");
  const messageInput = document.getElementById("messageInput");
  const currentRoomLabel = document.getElementById("currentRoom");
  const roomTypeTag = document.getElementById("roomTypeTag");
  const groupList = document.getElementById("groupList");
  const privateList = document.getElementById("privateList");
  const createGroupBtn = document.getElementById("createGroupBtn");
  const userList = document.getElementById("userList");

  const translationModal = document.getElementById("translationModal");
  const translationSourcePreview = document.getElementById("translationSourcePreview");
  const targetLanguageSelect = document.getElementById("targetLanguageSelect");
  const targetLanguageInput = document.getElementById("targetLanguageInput");
  const cancelTranslateBtn = document.getElementById("cancelTranslateBtn");
  const confirmTranslateBtn = document.getElementById("confirmTranslateBtn");

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

  function isDmRoom(room) {
    return room.indexOf("dm:") === 0;
  }

  function buildDmRoom(userA, userB) {
    const members = [userA, userB].sort();
    return "dm:" + members[0] + "|" + members[1];
  }

  function parseDmPeer(room) {
    if (!isDmRoom(room)) return "";
    const members = room.slice(3).split("|");
    if (members.length !== 2) return "";
    return members[0] === CURRENT_USER ? members[1] : members[0];
  }

  function getRoomTitle(room) {
    const labels = {
      general: "👥 大厅",
      tech: "🛠 技术组",
      random: "🎈 闲聊区",
    };
    if (!isDmRoom(room)) {
      return labels[room] || room;
    }
    const peer = dmPeerByRoom[room] || currentPeer || "私聊";
    return "💬 与 " + peer + " 私聊";
  }

  function renderGroupRooms(rooms) {
    groupRooms = Array.isArray(rooms) ? rooms : [];
    groupList.innerHTML = "";

    groupRooms.forEach(function (room) {
      const row = document.createElement("li");
      row.className = "room-row";

      const item = document.createElement("button");
      item.type = "button";
      item.className = "room-item";
      item.dataset.room = room;
      item.textContent = room === "general" ? "👥 大厅" : "# " + room;
      item.addEventListener("click", function () {
        joinRoom(room, { type: "group", peer: "" });
      });
      row.appendChild(item);

      if (room !== "general") {
        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "room-delete-btn";
        delBtn.textContent = "×";
        delBtn.title = "删除会话";
        delBtn.addEventListener("click", function (e) {
          e.stopPropagation();
          socket.emit("delete_group_room", { room: room });
        });
        row.appendChild(delBtn);
      }

      groupList.appendChild(row);
    });

    refreshGroupActiveState();
  }

  function renderPrivateRooms(rooms) {
    privateRooms = Array.isArray(rooms) ? rooms : [];
    privateList.innerHTML = "";

    if (!privateRooms.length) {
      const empty = document.createElement("li");
      empty.className = "user-item user-item--empty";
      empty.textContent = "暂无私聊会话";
      privateList.appendChild(empty);
      return;
    }

    privateRooms.forEach(function (room) {
      const peer = parseDmPeer(room) || "未知用户";
      dmPeerByRoom[room] = peer;

      const row = document.createElement("li");
      row.className = "room-row";

      const item = document.createElement("button");
      item.type = "button";
      item.className = "room-item";
      item.dataset.room = room;
      item.textContent = "💬 " + peer;
      item.addEventListener("click", function () {
        joinRoom(room, { type: "dm", peer: peer });
      });
      row.appendChild(item);

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "room-delete-btn";
      delBtn.textContent = "×";
      delBtn.title = "删除私聊会话";
      delBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        socket.emit("delete_private_chat", { room: room });
      });
      row.appendChild(delBtn);

      privateList.appendChild(row);
    });

    refreshPrivateActiveState();
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
    if (msg.id) {
      li.dataset.messageId = msg.id;
    }

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

    const actions = document.createElement("div");
    actions.className = "message-actions";

    const translateBtn = document.createElement("button");
    translateBtn.type = "button";
    translateBtn.className = "message-action-btn";
    translateBtn.textContent = "翻译";
    translateBtn.addEventListener("click", function () {
      openTranslateModal(msg.id, msg.text);
    });
    actions.appendChild(translateBtn);

    if (Array.isArray(msg.suggested_replies) && msg.suggested_replies.length > 0) {
      const suggestions = document.createElement("div");
      suggestions.className = "message-suggestions";
      msg.suggested_replies.forEach(function (item) {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "suggestion-chip";
        chip.textContent = item;
        chip.addEventListener("click", function () {
          messageInput.value = item;
          messageInput.focus();
        });
        suggestions.appendChild(chip);
      });
      actions.appendChild(suggestions);
    }

    li.appendChild(meta);
    li.appendChild(text);
    if (msg.translated_text) {
      const translated = document.createElement("div");
      translated.className = "message-translation";
      translated.textContent = "自动翻译: " + msg.translated_text;
      li.appendChild(translated);
    }

    const manualTranslation = msg.id ? manualTranslationByMessageId[msg.id] : "";
    if (manualTranslation) {
      const translated = document.createElement("div");
      translated.className = "message-translation message-translation--manual";
      translated.textContent = manualTranslation;
      li.appendChild(translated);
    }
    li.appendChild(actions);
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

  async function fetchJson(url, options) {
    const resp = await fetch(url, options);
    if (!resp.ok) {
      throw new Error("HTTP " + resp.status);
    }
    return await resp.json();
  }

  function historySignature(messages) {
    return JSON.stringify(
      (messages || []).map(function (m) {
        return [m.id || "", m.username || "", m.timestamp || 0, m.text || ""];
      })
    );
  }

  async function syncHistoryViaHttp() {
    try {
      const messages = await fetchJson(
        "/messages/history?room=" + encodeURIComponent(currentRoom) + "&limit=200"
      );
      const signature = historySignature(messages);
      if (signature !== lastHistorySignature) {
        lastHistorySignature = signature;
        clearMessages();
        messages.forEach(appendMessage);
      }
    } catch (_err) {
      // 忽略单次拉取失败，下一轮轮询会重试。
    }
  }

  async function syncSessionsViaHttp() {
    try {
      const data = await fetchJson("/messages/sessions");
      renderGroupRooms(data.group_rooms || []);
      renderPrivateRooms(data.private_rooms || []);
    } catch (_err) { }
  }

  async function syncOnlineUsersViaHttp() {
    try {
      const users = await fetchJson("/messages/online-users");
      renderOnlineUsers(users || []);
    } catch (_err) { }
  }

  async function sendPresenceHeartbeat() {
    try {
      await fetchJson("/messages/presence", { method: "POST" });
    } catch (_err) { }
  }

  function startFallbackPolling(reasonText) {
    if (!fallbackPollingStarted) {
      appendStatus(reasonText || "⚠️ 实时连接不可用，已切换 HTTP 轮询模式。");
    }
    fallbackPollingStarted = true;

    if (!historyPollingTimer) {
      historyPollingTimer = setInterval(function () {
        syncHistoryViaHttp();
      }, 2500);
    }
    if (!rosterPollingTimer) {
      rosterPollingTimer = setInterval(function () {
        sendPresenceHeartbeat();
        syncOnlineUsersViaHttp();
        syncSessionsViaHttp();
      }, 8000);
    }

    sendPresenceHeartbeat();
    syncOnlineUsersViaHttp();
    syncSessionsViaHttp();
    syncHistoryViaHttp();
  }

  function stopFallbackPolling() {
    fallbackPollingStarted = false;
    if (historyPollingTimer) {
      clearInterval(historyPollingTimer);
      historyPollingTimer = null;
    }
    if (rosterPollingTimer) {
      clearInterval(rosterPollingTimer);
      rosterPollingTimer = null;
    }
  }

  /**
   * 清空消息列表，切换房间时调用。
   */
  function clearMessages() {
    messageList.innerHTML = "";
  }

  function setRoomHeader() {
    currentRoomLabel.textContent = getRoomTitle(currentRoom);
    roomTypeTag.textContent = currentRoomType === "dm" ? "私聊" : "群聊";
  }

  function refreshGroupActiveState() {
    const groupItems = groupList.querySelectorAll(".room-item[data-room]");
    groupItems.forEach(function (el) {
      el.classList.toggle("active", el.dataset.room === currentRoom);
    });
  }

  function refreshPrivateActiveState() {
    const dmItems = privateList.querySelectorAll(".room-item[data-room]");
    dmItems.forEach(function (el) {
      el.classList.toggle("active", el.dataset.room === currentRoom && currentRoomType === "dm");
    });
  }

  function refreshUserActiveState() {
    const userItems = userList.querySelectorAll(".user-item[data-username]");
    userItems.forEach(function (el) {
      const username = el.dataset.username;
      el.classList.toggle("active", currentRoomType === "dm" && username === currentPeer);
    });
  }

  /**
   * 切换到指定房间：通知服务端离开旧房间、加入新房间，并更新 UI。
   */
  function joinRoom(room, options) {
    const opts = options || {};
    const previousRoom = currentRoom;

    if (room === previousRoom && !opts.forceJoin && !opts.reloadHistory) {
      return;
    }

    if (room !== previousRoom) {
      socket.emit("leave", { room: currentRoom });
    }

    currentRoom = room;
    currentRoomType = opts.type || (isDmRoom(room) ? "dm" : "group");
    currentPeer = opts.peer || dmPeerByRoom[room] || "";

    clearMessages();
    lastHistorySignature = "";

    refreshGroupActiveState();
    refreshPrivateActiveState();
    refreshUserActiveState();
    setRoomHeader();

    if (opts.forceJoin || room !== previousRoom) {
      if (socket.connected) {
        socket.emit("join", { room });
      } else {
        syncHistoryViaHttp();
      }
      return;
    }

    // room 未变化但需要刷新历史时，显式触发一次 join。
    if (opts.reloadHistory) {
      if (socket.connected) {
        socket.emit("join", { room });
      } else {
        syncHistoryViaHttp();
      }
    }
  }

  function renderOnlineUsers(users) {
    const peers = users.filter(function (name) {
      return name !== CURRENT_USER;
    });

    userList.innerHTML = "";
    if (!peers.length) {
      const empty = document.createElement("li");
      empty.className = "user-item user-item--empty";
      empty.textContent = "暂无在线用户";
      userList.appendChild(empty);
      return;
    }

    peers.forEach(function (name) {
      const li = document.createElement("li");
      li.className = "user-item";
      li.dataset.username = name;
      li.textContent = "🟢 " + name;
      li.addEventListener("click", function () {
        if (socket.connected) {
          socket.emit("open_private_chat", { peer: name });
          return;
        }

        const room = buildDmRoom(CURRENT_USER, name);
        dmPeerByRoom[room] = name;
        if (privateRooms.indexOf(room) === -1) {
          privateRooms.push(room);
          renderPrivateRooms(privateRooms);
        }
        joinRoom(room, { type: "dm", peer: name, forceJoin: false, reloadHistory: true });
      });
      userList.appendChild(li);
    });
    refreshUserActiveState();
  }

  function openTranslateModal(messageId, text) {
    pendingTranslation = { messageId: messageId || "", text: text || "" };
    translationSourcePreview.textContent =
      "原文: " + (text.length > 80 ? text.slice(0, 80) + "..." : text);
    targetLanguageSelect.value = "zh-CN";
    targetLanguageInput.value = "";
    targetLanguageInput.classList.add("hidden");
    translationModal.classList.remove("hidden");
    translationModal.setAttribute("aria-hidden", "false");
  }

  function closeTranslateModal() {
    translationModal.classList.add("hidden");
    translationModal.setAttribute("aria-hidden", "true");
    pendingTranslation = null;
  }

  function applyManualTranslation(messageId, translationText) {
    if (!messageId) return;
    manualTranslationByMessageId[messageId] = translationText;

    const target = messageList.querySelector('[data-message-id="' + messageId + '"]');
    if (!target) return;

    let block = target.querySelector(".message-translation--manual");
    if (!block) {
      block = document.createElement("div");
      block.className = "message-translation message-translation--manual";
      target.appendChild(block);
    }
    block.textContent = translationText;
  }

  async function sendMessageViaHttp(text) {
    const response = await fetch("/messages/send", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        room: currentRoom,
        text: text,
      }),
    });

    const payload = await response.json().catch(function () {
      return {};
    });

    if (!response.ok) {
      if (payload.reason) {
        appendStatus("🚫 消息被拦截: " + payload.reason);
      } else {
        appendStatus("⚠️ 发送失败: " + (payload.error || "未知错误"));
      }
      return;
    }

    if (payload.message && !socket.connected) {
      // Socket 未连接时无法收到广播，手动追加本地回显。
      appendMessage(payload.message);
    }
  }

  // ----------------------------------------------------------------
  // Socket.IO 服务端事件监听
  // ----------------------------------------------------------------

  // 连接成功后自动加入默认房间
  socket.on("connect", function () {
    stopFallbackPolling();
    socket.emit("fetch_sessions");
    setRoomHeader();
    refreshGroupActiveState();
    appendStatus("✅ 实时连接已建立");
    joinRoom(currentRoom, { type: currentRoomType, peer: currentPeer, forceJoin: true });
  });

  socket.on("disconnect", function () {
    startFallbackPolling("⚠️ 实时连接已断开，已切换 HTTP 轮询模式。");
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

  socket.on("online_users", function (data) {
    renderOnlineUsers(data.users || []);
  });

  socket.on("group_rooms_updated", function (data) {
    renderGroupRooms(data.rooms || []);
  });

  socket.on("private_rooms_updated", function (data) {
    renderPrivateRooms(data.rooms || []);
  });

  socket.on("group_room_created", function (data) {
    if (data.room) {
      joinRoom(data.room, { type: "group", peer: "", forceJoin: true });
      appendStatus("✅ 已创建群聊会话: " + data.room);
    }
  });

  socket.on("group_room_error", function (data) {
    appendStatus("⚠️ " + (data.msg || "群聊会话操作失败"));
  });

  socket.on("private_chat_ready", function (data) {
    dmPeerByRoom[data.room] = data.peer;
    joinRoom(data.room, { type: "dm", peer: data.peer, forceJoin: true });
  });

  socket.on("private_chat_invite", function (data) {
    dmPeerByRoom[data.room] = data.peer;
    appendStatus("收到来自 " + data.peer + " 的私聊邀请，点击在线列表可进入。");
  });

  socket.on("private_chat_error", function (data) {
    appendStatus("⚠️ " + data.msg);
  });

  socket.on("room_deleted", function (data) {
    if (!data || !data.room) return;
    if (currentRoom === data.room) {
      appendStatus("ℹ️ 当前会话已删除，已返回大厅。");
      joinRoom("general", { type: "group", peer: "", forceJoin: true });
    }
  });

  socket.on("message_rejected", function (data) {
    appendStatus("🚫 消息被拦截: " + (data.reason || "未通过安全检查"));
  });

  socket.on("message_processing", function (data) {
    appendStatus("🤖 " + ((data && data.msg) || "正在处理消息..."));
  });

  socket.on("error_message", function (data) {
    appendStatus("⚠️ " + data.msg);
  });

  socket.on("translation_result", function (data) {
    const translated = "手动翻译(" + data.target_language + "): " + data.translated_text;
    applyManualTranslation(data.message_id, translated);
    appendStatus("✅ 翻译完成");
  });

  socket.on("translation_blocked", function (data) {
    appendStatus("🚫 翻译被拦截: " + (data.reason || "未通过安全检查"));
  });

  socket.on("translation_error", function (data) {
    appendStatus("⚠️ 翻译失败: " + (data.msg || "未知错误"));
  });

  // 连接失败时给出提示
  socket.on("connect_error", function () {
    startFallbackPolling("⚠️ 实时连接失败，已切换 HTTP 轮询模式。");
  });

  // ----------------------------------------------------------------
  // 用户交互事件
  // ----------------------------------------------------------------

  // 提交表单发送消息
  messageForm.addEventListener("submit", async function (e) {
    e.preventDefault();
    const text = messageInput.value.trim();
    if (!text) return; // 忽略空消息

    if (socket.connected) {
      socket.emit("send_message", { room: currentRoom, text });
    } else {
      appendStatus("ℹ️ 当前使用 HTTP 发送（实时连接未建立）。");
      await sendMessageViaHttp(text);
    }
    messageInput.value = ""; // 清空输入框
  });

  if (createGroupBtn) {
    createGroupBtn.addEventListener("click", function () {
      const roomName = window.prompt("输入群聊会话名（1-32 位，中英文数字下划线或连字符）");
      if (!roomName) return;
      socket.emit("create_group_room", { room_name: roomName.trim() });
    });
  }

  targetLanguageSelect.addEventListener("change", function () {
    const useCustom = targetLanguageSelect.value === "custom";
    targetLanguageInput.classList.toggle("hidden", !useCustom);
    if (useCustom) {
      targetLanguageInput.focus();
    }
  });

  cancelTranslateBtn.addEventListener("click", function () {
    closeTranslateModal();
  });

  confirmTranslateBtn.addEventListener("click", function () {
    if (!pendingTranslation) return;

    const targetLanguage =
      targetLanguageSelect.value === "custom"
        ? targetLanguageInput.value.trim()
        : targetLanguageSelect.value;
    if (!targetLanguage) {
      appendStatus("⚠️ 请输入目标语言");
      return;
    }

    socket.emit("translate_message", {
      message_id: pendingTranslation.messageId,
      text: pendingTranslation.text,
      target_language: targetLanguage,
    });
    closeTranslateModal();
  });

  translationModal.addEventListener("click", function (e) {
    if (e.target === translationModal) {
      closeTranslateModal();
    }
  });

  if (!hasSocketClient) {
    startFallbackPolling("⚠️ Socket 客户端未加载，已切换 HTTP 轮询模式。");
  }
})();
