# IntelliTrans 消息站 — 系统架构设计文档

## 系统架构图

```
                         ┌─────────────────────────┐
                         │        浏览器 (chat.js)   │
                         │  Socket.IO / HTTP 双通道  │
                         └──────────┬──────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
               WebSocket                      HTTP REST
                    │                               │
                    ▼                               ▼
┌──────────────────────────────────────────────────────────┐
│              Flask + Flask-SocketIO (threading)          │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐      │
│  │  auth.py │  │  main.py │  │   messages.py      │      │ 
│  │ 登录/登出 │  │ 首页路由  │ │  REST + Socket 事件 │      │
│  └──────────┘  └──────────┘  └────────┬───────────┘      │
│                                       │                  │
│                          ┌────────────┴────────────┐     │
│                          │    app/services/        │     │
│                          │  ┌───────────────────┐  │     │
│                          │  │  redis_service.py │  │     │
│                          │  │  workflow_service │  │     │
│                          │  └───────────────────┘  │     │
│                          └────────────┬────────────┘     │
└───────────────────────────────────────┼──────────────────┘
                                        │
                    ┌───────────────────┴───────────────────┐
                    │                                       │
                    ▼                                       ▼
        ┌──────────────────┐                  ┌──────────────────┐
        │      Redis       │                  │  AI 工作流 (Coze) │
        │                  │                  │                  │
        │  Pub/Sub 消息广播 │                  │  安全检查        │
        │  List    历史记录 │                  │  语言检测        │
        │  Set     房间索引 │                  │  智能翻译        │
        │  String  在线状态 │                  │  推荐回复        │
        └──────────────────┘                  └──────────────────┘
```

---

## 数据流

### 消息发送流程（Socket.IO 通道）

```
1. 用户输入消息 → Socket emit("send_message")
2. 服务端 _socket_username() 解析身份 + 续期在线键
3. 调用 workflow_service.process_new_message()
   ├─ 向 Coze API 发送: { new_message, chat_history, is_translation_requested: false }
   ├─ 返回: { is_safe, needs_translation, translation_result, suggested_replies }
   └─ 容错: 失败时 fail-open 放行
4. is_safe=false → emit("message_rejected") 拦截
5. is_safe=true → publish_message() 发布到 Redis
   ├─ PUBLISH intellitrans:messages {payload}   → 实时广播
   ├─ RPUSH intellitrans:history:{room}         → 追加历史
   └─ LTRIM 裁剪至最近 200 条
6. emit("new_message", message, to=room)        → 房间内广播
```

### 消息发送流程（HTTP 降级通道）

```
1. 用户输入消息 → fetch POST /messages/send
2. 服务端处理同上（工作流 + Redis）
3. socketio.emit("new_message", message, to=room) → 仍走 Socket 广播
4. 返回 HTTP 200 + message 对象
5. 前端 socket.connected=false 时手动 appendMessage 回显
```

### 在线状态流转

```
Socket 连接建立
  → mark_user_online(username)                 # SETEX intellitrans:online:{user} 60 "1"
  → _broadcast_online_users()                  # 全客户端接收更新

每次 Socket 事件（发消息、切房间等）
  → _socket_username() 自动调用 mark_user_online()  # 续期 TTL

Socket 断开
  → 所有 sid 都断开后 remove_user_online()     # DEL intellitrans:online:{user}

HTTP 心跳（每 8 秒）
  → POST /messages/presence → mark_user_online()

获取在线列表
  → redis_get_online_users()                   # SCAN intellitrans:online:*
```

---

## Redis 数据结构设计

| 键模式 | 类型 | 操作 | 用途 |
|--------|------|------|------|
| `intellitrans:messages` | Channel | `PUBLISH` | 实时消息广播（Pub/Sub） |
| `intellitrans:history:{room}` | List | `RPUSH` / `LRANGE` / `LTRIM` | 房间消息历史（上限 200 条） |
| `intellitrans:rooms` | Set | `SADD` / `SMEMBERS` / `SREM` / `SISMEMBER` | 群聊房间注册表 |
| `intellitrans:user_dm:{user}` | Set | `SADD` / `SMEMBERS` / `SREM` | 用户私聊会话索引 |
| `intellitrans:online:{user}` | String | `SETEX` / `EXISTS` / `DEL` / `SCAN` | 在线状态（TTL 60s 自动过期） |

---

## 模块职责

### `app/__init__.py` — 应用工厂
- `create_app()` 工厂函数，支持 `development` / `production` / `testing` 环境
- 初始化扩展（Redis、Socket.IO、Flask-Login）
- 注册蓝图、全局登录拦截钩子

### `app/config.py` — 配置管理
- `BaseConfig` / `DevelopmentConfig` / `ProductionConfig` 三层配置
- 所有配置可通过 `.env` 环境变量覆盖
- `get_config()` 根据 `FLASK_ENV` 返回对应配置类

### `app/extensions.py` — 扩展初始化
- Socket.IO 实例（`async_mode="threading"`）
- Flask-Login 管理器
- `init_redis(app)` — 创建 Redis 客户端并挂载到 `app.extensions`

### `app/routes/messages.py` — 消息核心逻辑
- REST 端点：历史查询、在线用户、心跳、HTTP 发送兜底、会话快照
- Socket.IO 事件：connect/disconnect、join/leave、send_message、translate_message
- 群聊/私聊房间的创建、删除、加入
- 在线用户状态管理（Redis 键 + 活动续期）

### `app/services/redis_service.py` — Redis 操作层
- 群聊房间 CRUD
- 私聊会话索引管理
- 消息发布与历史查询
- 在线用户 Presence（SETEX + SCAN）

### `app/services/workflow_service.py` — AI 工作流调用层
- `process_new_message()` — 新消息安全审查 + 翻译 + 推荐回复
- `request_manual_translation()` — 手动翻译（不生成推荐回复）
- `_normalize_result()` — 响应规范化（支持多种字段别名）
- `_find_value()` — 深度递归 JSON 搜索

---

## 关键设计决策

### 1. 零数据库架构
全部状态（消息历史、房间注册、用户在线、私聊索引）存储在 Redis 中，无需 MySQL/PostgreSQL。部署仅需 Python + Redis 两个依赖。

### 2. 模块引用而非值导入
```python
# redis_service.py
import app.extensions as _ext  # ✅ 模块引用，运行时获取最新值
# from app.extensions import redis_client  # ❌ 值导入，无法感知 global 重赋值
```

### 3. Fail-open 容错优先
AI 增强是附加值，核心消息传递永不被外部服务中断阻塞。工作流不可用时自动降级为纯文本消息。

### 4. 双通道互补
Socket.IO（WebSocket 优先）用于实时通信，HTTP REST 作为降级通道。前端 5 秒连接超时后自动切换 HTTP 轮询。

### 5. 在线状态 TTL 自愈
Redis 键 60 秒自动过期 → 每次 Socket 活动续期 → 无需手动清理断开连接。

---

## 测试策略

| 测试层 | 文件 | 覆盖范围 | 隔离方式 |
|--------|------|----------|----------|
| Redis 服务层 | `test_redis_service.py`（16 条） | 房间管理、消息发布/历史、在线 Presence | Redis DB #9 + FLUSHDB |
| 工作流解析层 | `test_workflow_service.py`（28 条） | JSON 解析、类型转换、结果规范化 | 纯函数，无外部依赖 |
