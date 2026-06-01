# IntelliTrans-Message-Station

基于 Redis 中间件与 AI 工作流的实时多语言在线交流系统。

## 架构概览

```
┌──────────────┐     Socket.IO / HTTP      ┌──────────────────┐
│   浏览器      │ ◄─────────────────────────►│  Flask + SocketIO │
│  (chat.js)   │                            │   (threading)     │
└──────────────┘                            └────────┬─────────┘
                                                     │
                          ┌──────────────────────────┼──────────────────────────┐
                          │              Redis 中间件                           │
                          │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐    │
                          │  │ Pub/Sub  │ │  List    │ │  Set             │    │
                          │  │ 消息广播  │ │ 历史记录  │ │ 房间 / 私聊索引   │    │
                          │  └──────────┘ └──────────┘ └──────────────────┘    │
                          │  ┌──────────────────────────────────────────┐     │
                          │  │  String (TTL) — 在线用户 Presence       │     │
                          │  └──────────────────────────────────────────┘     │
                          └──────────────────────────────────────────────────┘
                                                     │
                          ┌──────────────────────────┼──────────────────────────┐
                          │              AI 工作流中间件                        │
                          │  安全检查 → 语言检测 → 自动翻译 → 推荐回复          │
                          │              ↕ fail-open 容错降级                  │
                          └──────────────────────────────────────────────────┘
```

## 功能特性

- **实时群聊** — 多房间消息广播，支持创建/删除群聊会话
- **一对一私聊** — 点击在线用户即可发起私密对话
- **AI 安全审查** — 每条消息经外部工作流审核，违规内容自动拦截
- **多语言翻译** — 自动检测源语言并翻译，支持手动指定目标语言（7 种预设 + 自定义）
- **智能推荐回复** — AI 根据上下文生成建议回复快捷填入
- **双重在线检测** — Socket.IO 长连接 + HTTP 心跳轮询互补
- **Fail-open 降级** — 外部 AI 服务不可用时自动放行消息，保证核心功能不中断
- **HTTP 全兜底** — WebSocket 不可用时自动切换 HTTP 轮询模式，消息收发不间断

## 技术栈

| 层级 | 技术 |
|------|------|
| Web 框架 | Flask 3.1 |
| 实时通信 | Flask-SocketIO 5.5（threading 模式） |
| 消息中间件 | Redis Pub/Sub + List + Set + String |
| 用户认证 | Flask-Login（轻量级内存模型） |
| AI 工作流 | Coze API（HTTP 外部调用） |
| 前端 | Jinja2 模板 + 原生 JavaScript + Socket.IO 客户端 |
| 测试 | pytest（44 条用例） |

## 快速开始

### 环境要求

- Python 3.11+
- Redis 7.0+（本地运行，默认 `127.0.0.1:6379`）

### 安装

```bash
git clone <repo-url>
cd IntelliTrans-Message-Station
pip install -r requirements.txt
```

### 配置

复制并编辑环境变量文件：

```bash
cp .env.example .env   # 如未提供，直接编辑 .env
```

关键配置项（`.env`）：

```ini
FLASK_ENV=development
SECRET_KEY=change-me-to-a-random-secret-key

# Redis 连接
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0

# AI 工作流（可选，不填则仅降级运行）
WORKFLOW_ENABLED=true
WORKFLOW_API_URL=https://your-workflow-api/run
WORKFLOW_API_TOKEN=your-api-token
WORKFLOW_FAIL_OPEN=true          # 工作流失败时放行消息
WORKFLOW_TIMEOUT_SECONDS=12
```

### 运行

```bash
# 确保 Redis 已启动
redis-server

# 启动应用
python run.py
```

访问 http://localhost:5000，输入任意用户名即可进入聊天室。

## 项目结构

```
├── run.py                     # 应用入口
├── requirements.txt           # Python 依赖
├── .env                       # 环境变量配置
├── README.md
├── app/
│   ├── __init__.py            # Flask 工厂函数 + 扩展初始化
│   ├── config.py              # 配置类（开发/生产/测试）
│   ├── extensions.py          # SocketIO / LoginManager / Redis 客户端
│   ├── models/
│   │   └── user.py            # 轻量级内存用户模型
│   ├── routes/
│   │   ├── auth.py            # 登录/登出
│   │   ├── main.py            # 首页路由
│   │   └── messages.py        # 消息 REST + Socket.IO 事件处理器
│   ├── services/
│   │   ├── redis_service.py   # Redis 操作（Pub/Sub、历史、房间、在线状态）
│   │   └── workflow_service.py # AI 工作流调用与响应规范化
│   ├── static/
│   │   ├── css/style.css      # 粉蓝渐变云朵 UI
│   │   └── js/
│   │       ├── chat.js        # 前端 Socket.IO 客户端 + HTTP 降级
│   │       └── socket.io.min.js
│   └── templates/
│       ├── base.html          # 基础布局
│       ├── index.html         # 聊天室主界面
│       └── login.html         # 登录页
└── tests/
    ├── conftest.py            # 测试夹具（隔离 Redis DB #9）
    ├── test_redis_service.py  # Redis 服务层测试（16 条）
    └── test_workflow_service.py # 工作流解析测试（28 条）
```

## 运行测试

```bash
pip install pytest
python -m pytest tests/ -v
```

测试使用独立的 Redis DB #9，不会污染开发数据。每次测试前后自动 `FLUSHDB` 清理。

## Redis 数据结构设计

| 键模式 | 类型 | 用途 | TTL |
|--------|------|------|-----|
| `intellitrans:messages` | Pub/Sub 频道 | 实时消息广播 | — |
| `intellitrans:history:{room}` | List | 房间消息历史（LTRIM 保留最近 200 条） | — |
| `intellitrans:rooms` | Set | 群聊房间注册表 | — |
| `intellitrans:user_dm:{user}` | Set | 用户的私聊会话索引 | — |
| `intellitrans:online:{user}` | String | 在线状态（SETEX） | 60s 自动过期 |

## 消息处理流程

```
用户发送消息
     │
     ▼
┌──────────┐    失败     ┌─────────────┐
│ AI 工作流  │ ─────────► │ fail-open？  │──是──► 放行消息
│ 安全审查  │            │              │
└────┬─────┘            └──────┬───────┘
     │ 通过                    │ 否
     ▼                         ▼
┌──────────┐            ┌─────────────┐
│ 语言检测  │            返回 502 错误  │
│ 自动翻译  │            └─────────────┘
│ 推荐回复  │
└────┬─────┘
     │
     ▼
┌──────────────┐     ┌──────────────┐
│ Redis Pub/Sub │ ──► │ 广播给房间    │
│ 发布消息      │     │ 所有在线用户  │
└──────┬───────┘     └──────────────┘
       │
       ▼
┌──────────────┐
│ Redis List   │
│ 追加历史记录  │
│ LTRIM 裁剪   │
└──────────────┘
```

## 降级策略

| 场景 | 策略 |
|------|------|
| WebSocket 连接失败 | 5 秒超时后自动切换 HTTP 轮询（2.5s 拉历史 + 8s 拉在线列表） |
| AI 工作流超时/错误 | `WORKFLOW_FAIL_OPEN=true` 时放行消息，附带 `workflow_error` |
| AI 工作流未配置 | 仅关闭 AI 增强功能，聊天核心功能正常运行 |
| Socket.IO 脚本未加载 | 页面初始化时立即启动 HTTP 轮询模式 |

## 设计决策

- **零数据库**：全部状态存储在 Redis 中，部署仅需一个 Redis 实例
- **threading 模式**：替代 eventlet，Windows / Linux 均可稳定运行
- **Fail-open 优先**：AI 增强是附加值，核心消息传递永远不因外部服务中断而阻塞
- **模块引用而非值导入**：`import app.extensions as _ext` 确保 `init_redis` 后运行时获取最新客户端引用

## License

MIT

