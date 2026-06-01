# IntelliTrans 消息站 — AI 工作流 API 文档

> 外部工作流（Coze 平台）为消息站提供智能 API 服务，实现内容安全检查、多语言翻译和推荐回复生成。

## 工作流流程

```
API 调用
  │
  ▼
┌────────────┐    不安全
│ ① 安全检查  │─────────► 拦截返回（is_safe = false）
└─────┬──────┘
      │ 安全
      ▼
┌────────────┐
│ ② 语言检测  │
└─────┬──────┘
      │
      ▼
  需要翻译？
   ├── 是 ──► [③ 翻译] ──► 手动翻译？ ──► 是 ──► 结束（仅返回翻译，无推荐回复）
   │                         └── 否 ──► [④ 生成推荐回复] ──► 结束
   └── 否 ──► 手动翻译？ ──► 是 ──► 结束（无操作）
               └── 否 ──► [④ 生成推荐回复] ──► 结束
```

---

## API 端点

```
POST {WORKFLOW_API_URL}
Authorization: Bearer {WORKFLOW_API_TOKEN}
Content-Type: application/json
```

---

## 输入参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `new_message` | string | ✅ | 用户发送的最新消息内容 |
| `chat_history` | array | — | 聊天历史记录，每条包含 `role` 和 `content` |
| `is_translation_requested` | boolean | ✅ | `true` = 用户手动点击翻译按钮；`false` = 新消息系统自动调用 |
| `target_language` | string | — | 翻译目标语言（仅 `is_translation_requested=true` 时使用） |
| `user_language` | string | — | 发送方用户的常用语言（默认中文），用于判断是否需要翻译 |
| `recipient_language` | string | — | 接收方用户的常用语言（默认中文），用于确定推荐回复的语言 |

---

## 输出结果

| 字段 | 类型 | 说明 |
|------|------|------|
| `is_safe` | boolean | 内容是否通过安全检查 |
| `safety_reason` | string | 不安全原因（`is_safe=false` 时返回） |
| `needs_translation` | boolean | 是否需要翻译 |
| `translation_result` | string | 翻译后的文本（翻译场景返回） |
| `suggested_replies` | array | 推荐回复列表（3~5 条，仅新消息自动调用时返回） |

> **兼容说明**：服务端代码同时支持 `is_safe`/`safe`/`is_valid`、`needs_translation`/`need_translate`、`translation_result`/`translated_text` 等多种别名字段，具备良好的 API 适配能力。

---

## 调用场景

### 场景 1：新消息到达（系统自动调用）

当用户在聊天室中发送一条新消息时，系统自动调用工作流进行安全检查、语言检测、智能翻译和推荐回复生成。

**请求示例：**

```json
{
  "new_message": "Hi, how are you today?",
  "chat_history": [
    { "role": "user", "content": "你好" },
    { "role": "assistant", "content": "你好！" }
  ],
  "is_translation_requested": false,
  "user_language": "中文",
  "recipient_language": "中文"
}
```

**响应示例：**

```json
{
  "is_safe": true,
  "needs_translation": true,
  "translation_result": "嗨，你今天过得怎么样？",
  "suggested_replies": [
    "我挺好的，谢谢关心！你今天过得怎么样呀？",
    "我今天状态不错～你呢，有没有什么有意思的事发生呀？",
    "还行，就是有点忙。你呢？"
  ]
}
```

---

### 场景 2：用户手动翻译

用户点击消息旁的「翻译」按钮，系统仅请求翻译结果，不生成推荐回复以节省资源。

**请求示例：**

```json
{
  "new_message": "Hello, how are you?",
  "is_translation_requested": true,
  "target_language": "中文",
  "user_language": "中文"
}
```

**响应示例：**

```json
{
  "is_safe": true,
  "needs_translation": true,
  "translation_result": "你好，最近怎么样？"
}
```

---

### 场景 3：内容安全检查拦截

当消息包含不合规内容时，工作流直接拦截并返回原因。

**请求示例：**

```json
{
  "new_message": "包含攻击性言论的内容",
  "is_translation_requested": false,
  "user_language": "中文"
}
```

**响应示例：**

```json
{
  "is_safe": false,
  "safety_reason": "检测到人身攻击和侮辱性言论"
}
```

**服务端处理**：拦截后返回 HTTP 422，前端显示 `"🚫 消息被拦截: {reason}"`。

---

## 关键逻辑说明

### 翻译触发规则

| 条件 | 行为 |
|------|------|
| `is_translation_requested = true` | **硬翻译**：直接翻译到 `target_language` |
| `is_translation_requested = false` | **智能翻译**：工作流自动判断源语言与 `user_language` 是否不同，仅在需要时翻译 |

### 推荐回复生成规则

| 条件 | 行为 |
|------|------|
| `is_translation_requested = false`（新消息） | 生成 3~5 条推荐回复，语言使用 `recipient_language` |
| `is_translation_requested = true`（手动翻译） | **不生成**推荐回复，节省 token 消耗 |
| 自己的消息 | 前端过滤，不显示推荐回复 |

### 语言参数用途

| 参数 | 用途 |
|------|------|
| `user_language` | 发送方常用语言，用于判断是否需要翻译（新消息与 user_language 不同时触发翻译） |
| `recipient_language` | 接收方常用语言，用于决定推荐回复的语言（使回复更符合对方习惯） |
| `target_language` | 手动翻译时指定的目标语言 |

---

## 容错与降级

工作流服务端实现了 **fail-open** 容错策略（配置项 `WORKFLOW_FAIL_OPEN=true`）：

| 故障场景 | 策略 |
|----------|------|
| API 超时（默认 12s） | 放行消息，附 `workflow_error` 标记 |
| HTTP 错误（4xx/5xx） | 放行消息 |
| 响应非合法 JSON | 放行消息 |
| 工作流未启用（`WORKFLOW_ENABLED=false`） | 跳过所有 AI 增强，仅做基础消息收发 |

> 这是本项目的核心设计决策之一：**AI 增强是附加值，核心消息传递永不被外部服务中断阻塞**。

---

## 配置参数

所有参数通过 `.env` 文件或环境变量配置：
建议外部工作流根据此文档在coze平台创建一个新的工作流，命名为 `intellitrans_message_workflow`，并实现上述逻辑。完成后将生成的 API URL 和 Token 填入下表：
```ini
# 工作流开关
WORKFLOW_ENABLED=true

# 工作流 API 地址和认证
WORKFLOW_API_URL=https://w3f64kykmn.coze.site/run
WORKFLOW_API_TOKEN=your_coze_api_token_here

# 超时与容错
WORKFLOW_TIMEOUT_SECONDS=12    # 请求超时秒数
WORKFLOW_FAIL_OPEN=true        # 故障时是否放行消息
WORKFLOW_HISTORY_WINDOW=20     # 传入工作流的上下文消息条数
```
