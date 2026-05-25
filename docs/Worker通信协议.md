# 织梦纪 DreamWeave Worker 通信协议

版本：v0.1  
更新日期：2026-05-24

## 1. 协议目标

本协议定义线上服务器与本地 AI Worker 之间的 WebSocket 通信格式。

第一版目标是跑通：

```text
服务器创建 AI 任务
        ↓
通过 WebSocket 下发给本地 Worker
        ↓
Worker 调用本地 Ollama
        ↓
Worker 返回 AI 结果
        ↓
服务器返回给前端并保存记录
```

---

## 2. 连接原则

### 2.1 连接方向

本地 Worker 主动连接线上服务器。

```text
本地 Python Worker → 线上服务器 WebSocket
```

服务器不要主动访问本地电脑。

### 2.2 建议地址

开发环境：

```text
ws://127.0.0.1:3000/ws/worker
```

生产环境：

```text
wss://api.example.com/ws/worker
```

### 2.3 传输格式

所有消息使用 JSON 文本格式。

所有消息必须包含：

```json
{
  "type": "message.type",
  "request_id": "req_001",
  "timestamp": "2026-05-24T15:00:00.000Z",
  "payload": {}
}
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `type` | 是 | 消息类型 |
| `request_id` | 否 | 请求追踪 ID，同一条链路尽量保持一致 |
| `timestamp` | 否 | 消息创建时间，ISO 8601 格式 |
| `payload` | 是 | 消息内容 |

第一版实现中，`timestamp` 可以由发送方生成，也可以暂时省略。

---

## 3. 消息类型总览

| 方向 | 类型 | 说明 |
| --- | --- | --- |
| Worker → Server | `worker.register` | Worker 注册 |
| Server → Worker | `worker.registered` | 注册成功 |
| Server → Worker | `worker.rejected` | 注册失败 |
| Worker → Server | `worker.heartbeat` | Worker 心跳 |
| Server → Worker | `worker.heartbeat_ack` | 心跳确认 |
| Server → Worker | `ai.task` | AI 任务下发 |
| Worker → Server | `ai.task_ack` | Worker 确认收到任务 |
| Worker → Server | `ai.result` | AI 任务最终结果 |
| Worker → Server | `ai.task_error` | AI 任务错误 |
| Server → Worker | `ai.task_cancel` | 取消任务 |
| 双向 | `error` | 协议级错误 |

第一版必须实现：

- `worker.register`
- `worker.registered`
- `worker.heartbeat`
- `worker.heartbeat_ack`
- `ai.task`
- `ai.result`
- `ai.task_error`
- `error`

`ai.task_ack` 和 `ai.task_cancel` 建议预留，第一版可后置。

---

## 4. Worker 注册

### 4.1 注册请求

方向：

```text
Worker → Server
```

类型：

```text
worker.register
```

示例：

```json
{
  "type": "worker.register",
  "request_id": "req_register_001",
  "timestamp": "2026-05-24T15:00:00.000Z",
  "payload": {
    "worker_id": "local-dev-001",
    "worker_name": "Admin PC Worker",
    "protocol_version": "0.1",
    "default_model": "qwen3:14b",
    "available_models": [
      "qwen3:14b",
      "llama33-novel:latest"
    ],
    "max_concurrency": 1,
    "capabilities": {
      "story_continue": true,
      "stream_result": false,
      "thinking_control": true
    }
  }
}
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `worker_id` | 是 | Worker 唯一标识 |
| `worker_name` | 否 | 方便后台展示的名称 |
| `protocol_version` | 是 | 协议版本 |
| `default_model` | 是 | Worker 默认模型 |
| `available_models` | 是 | 本地 Ollama 可用模型列表 |
| `max_concurrency` | 是 | Worker 最大并发任务数 |
| `capabilities` | 是 | Worker 能力描述 |

### 4.2 注册成功

方向：

```text
Server → Worker
```

类型：

```text
worker.registered
```

示例：

```json
{
  "type": "worker.registered",
  "request_id": "req_register_001",
  "timestamp": "2026-05-24T15:00:01.000Z",
  "payload": {
    "worker_id": "local-dev-001",
    "server_id": "server-001",
    "heartbeat_interval_ms": 15000,
    "task_timeout_ms": 180000
  }
}
```

### 4.3 注册失败

方向：

```text
Server → Worker
```

类型：

```text
worker.rejected
```

示例：

```json
{
  "type": "worker.rejected",
  "request_id": "req_register_001",
  "timestamp": "2026-05-24T15:00:01.000Z",
  "payload": {
    "error_code": "WORKER_UNAUTHORIZED",
    "message": "Worker token 无效"
  }
}
```

---

## 5. 心跳

### 5.1 Worker 心跳

方向：

```text
Worker → Server
```

类型：

```text
worker.heartbeat
```

示例：

```json
{
  "type": "worker.heartbeat",
  "request_id": "req_heartbeat_001",
  "timestamp": "2026-05-24T15:00:15.000Z",
  "payload": {
    "worker_id": "local-dev-001",
    "status": "idle",
    "running_tasks": 0,
    "max_concurrency": 1,
    "default_model": "qwen3:14b",
    "available_models": [
      "qwen3:14b",
      "llama33-novel:latest"
    ]
  }
}
```

`status` 可选值：

```text
idle
busy
degraded
offline
```

### 5.2 心跳确认

方向：

```text
Server → Worker
```

类型：

```text
worker.heartbeat_ack
```

示例：

```json
{
  "type": "worker.heartbeat_ack",
  "request_id": "req_heartbeat_001",
  "timestamp": "2026-05-24T15:00:15.100Z",
  "payload": {
    "worker_id": "local-dev-001"
  }
}
```

### 5.3 心跳策略

建议：

- Worker 每 15 秒发送一次心跳。
- Server 超过 45 秒没有收到心跳，标记 Worker 为 `offline`。
- Worker 连接断开后，应自动重连。
- 重连成功后，Worker 必须重新发送 `worker.register`。

---

## 6. AI 任务下发

### 6.1 任务消息

方向：

```text
Server → Worker
```

类型：

```text
ai.task
```

示例：

```json
{
  "type": "ai.task",
  "request_id": "req_story_001",
  "timestamp": "2026-05-24T15:01:00.000Z",
  "payload": {
    "task_id": "task_001",
    "task_type": "story_continue",
    "user_id": "user_001",
    "session_id": "session_001",
    "story_id": "story_001",
    "model": "qwen3:14b",
    "timeout_ms": 180000,
    "input": "我推开了古堡的大门。",
    "generation_options": {
      "num_predict": 220,
      "temperature": 0.66,
      "top_p": 0.85,
      "repeat_penalty": 1.08,
      "think": false
    },
    "context": {
      "story_title": "黑夜古堡",
      "world_setting": "中世纪奇幻世界",
      "character_setting": "用户是失忆的贵族继承人",
      "recent_messages": [
        "夜色压在山谷上，古堡的轮廓像一只沉睡的巨兽。"
      ]
    }
  }
}
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `task_id` | 是 | AI 任务 ID |
| `task_type` | 是 | 任务类型，第一版为 `story_continue` |
| `user_id` | 是 | 用户 ID |
| `session_id` | 是 | 会话 ID |
| `story_id` | 是 | 小说项目 ID |
| `model` | 否 | 本次任务指定模型，不传则使用 Worker 默认模型 |
| `timeout_ms` | 否 | 本次任务处理超时时间，不传则使用 Worker 默认值 |
| `input` | 是 | 用户输入 |
| `generation_options` | 否 | 本次任务生成参数 |
| `context` | 是 | 小说上下文 |

### 6.2 任务类型

第一版只要求支持：

```text
story_continue
```

后续可扩展：

```text
story_summary
character_reply
world_update
```

### 6.3 模型选择规则

Worker 收到任务后按以下优先级选择模型：

```text
任务 payload.model
        ↓
Worker 默认模型
```

如果最终选择的模型不在本地 Ollama 模型列表中，Worker 返回：

```text
MODEL_NOT_FOUND
```

---

## 7. 任务确认

### 7.1 任务确认消息

方向：

```text
Worker → Server
```

类型：

```text
ai.task_ack
```

示例：

```json
{
  "type": "ai.task_ack",
  "request_id": "req_story_001",
  "timestamp": "2026-05-24T15:01:00.100Z",
  "payload": {
    "task_id": "task_001",
    "worker_id": "local-dev-001",
    "status": "accepted"
  }
}
```

第一版可以不实现 `ai.task_ack`，直接等待 `ai.result` 或 `ai.task_error`。

如果要实现，`status` 可选值：

```text
accepted
rejected
```

---

## 8. AI 结果返回

### 8.1 成功结果

方向：

```text
Worker → Server
```

类型：

```text
ai.result
```

示例：

```json
{
  "type": "ai.result",
  "request_id": "req_story_001",
  "timestamp": "2026-05-24T15:01:05.000Z",
  "payload": {
    "task_id": "task_001",
    "status": "success",
    "worker_id": "local-dev-001",
    "model": "qwen3:14b",
    "content": "沉重的木门缓缓打开，腐朽的冷风从黑暗深处涌出。墙上的烛火忽明忽暗，仿佛有什么东西正从古堡深处醒来。",
    "usage": {
      "prompt_tokens": null,
      "completion_tokens": null,
      "total_tokens": null
    },
    "duration_ms": 4200
  }
}
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `task_id` | 是 | AI 任务 ID |
| `status` | 是 | 固定为 `success` |
| `worker_id` | 是 | 返回结果的 Worker |
| `model` | 是 | 实际使用的模型 |
| `content` | 是 | AI 生成内容 |
| `usage` | 否 | token 使用统计，第一版可为空 |
| `duration_ms` | 否 | 任务耗时 |

### 8.2 错误结果

方向：

```text
Worker → Server
```

类型：

```text
ai.task_error
```

示例：

```json
{
  "type": "ai.task_error",
  "request_id": "req_story_001",
  "timestamp": "2026-05-24T15:01:05.000Z",
  "payload": {
    "task_id": "task_001",
    "status": "error",
    "worker_id": "local-dev-001",
    "model": "missing-model:latest",
    "error_code": "MODEL_NOT_FOUND",
    "message": "本地 Ollama 未找到模型：missing-model:latest",
    "retryable": false
  }
}
```

---

## 9. 任务取消

### 9.1 取消任务

方向：

```text
Server → Worker
```

类型：

```text
ai.task_cancel
```

示例：

```json
{
  "type": "ai.task_cancel",
  "request_id": "req_story_001",
  "timestamp": "2026-05-24T15:01:02.000Z",
  "payload": {
    "task_id": "task_001",
    "reason": "client_disconnected"
  }
}
```

第一版可以暂不实现真正取消 Ollama 请求，但需要预留消息类型。

---

## 10. 协议级错误

### 10.1 错误消息

方向：

```text
双向
```

类型：

```text
error
```

示例：

```json
{
  "type": "error",
  "request_id": "req_story_001",
  "timestamp": "2026-05-24T15:01:00.000Z",
  "payload": {
    "error_code": "INVALID_MESSAGE",
    "message": "消息缺少 type 字段",
    "detail": {
      "field": "type"
    }
  }
}
```

---

## 11. 错误码

### 11.1 协议错误

| 错误码 | 说明 | 是否可重试 |
| --- | --- | --- |
| `INVALID_MESSAGE` | 消息格式错误 | 否 |
| `UNSUPPORTED_MESSAGE_TYPE` | 不支持的消息类型 | 否 |
| `INVALID_PAYLOAD` | payload 字段不合法 | 否 |
| `WORKER_UNAUTHORIZED` | Worker 鉴权失败 | 否 |
| `PROTOCOL_VERSION_MISMATCH` | 协议版本不兼容 | 否 |

### 11.2 任务错误

| 错误码 | 说明 | 是否可重试 |
| --- | --- | --- |
| `MODEL_NOT_FOUND` | 本地不存在指定模型 | 否 |
| `OLLAMA_TIMEOUT` | Ollama 生成超时 | 是 |
| `OLLAMA_HTTP_ERROR` | Ollama HTTP 调用失败 | 是 |
| `EMPTY_RESPONSE` | 模型返回空内容 | 是 |
| `TASK_TIMEOUT` | Worker 任务执行超时 | 是 |
| `TASK_CANCELLED` | 任务被取消 | 否 |
| `WORKER_BUSY` | Worker 当前并发已满 | 是 |
| `WORKER_ERROR` | Worker 内部错误 | 视情况 |

---

## 12. 任务状态流转

服务器侧建议维护任务状态：

```text
created
queued
sent_to_worker
running
success
error
timeout
cancelled
```

第一版最小状态流：

```text
created → sent_to_worker → success
created → sent_to_worker → error
created → sent_to_worker → timeout
```

---

## 13. 超时策略

第一版采用三层超时：

```text
Worker Ollama 调用超时
        ↓
Server 等待 Worker 结果超时
        ↓
Frontend 等待接口响应超时
```

建议默认值：

| 项目 | 默认值 |
| --- | --- |
| Worker 心跳间隔 | 15 秒 |
| Worker 离线判定 | 45 秒 |
| Worker 任务处理超时 | 180 秒 |
| Worker Ollama 请求超时 | 180 秒 |
| Server 等待 Worker 结果超时 | 200 秒 |
| Frontend 请求等待超时 | 210-220 秒 |
| WebSocket 重连间隔 | 3 秒起步，最多 30 秒 |

### 13.1 Worker 超时

Worker 需要控制两类超时：

```text
任务级超时：限制整个 AI 任务最多运行多久
Ollama 请求超时：限制 Ollama HTTP 调用最多等待多久
```

如果 Ollama HTTP 调用超时，Worker 返回：

```json
{
  "type": "ai.task_error",
  "request_id": "req_story_001",
  "timestamp": "2026-05-24T15:01:05.000Z",
  "payload": {
    "task_id": "task_001",
    "status": "error",
    "worker_id": "local-dev-001",
    "model": "qwen3:14b",
    "error_code": "OLLAMA_TIMEOUT",
    "message": "Ollama 生成超时",
    "retryable": true
  }
}
```

如果整个任务超过 `timeout_ms` 或 Worker 默认任务超时时间，Worker 返回：

```json
{
  "type": "ai.task_error",
  "request_id": "req_story_001",
  "timestamp": "2026-05-24T15:01:05.000Z",
  "payload": {
    "task_id": "task_001",
    "status": "error",
    "worker_id": "local-dev-001",
    "model": "qwen3:14b",
    "error_code": "TASK_TIMEOUT",
    "message": "AI 任务处理超时：180 秒",
    "retryable": true
  }
}
```

### 13.2 Server 超时

Server 下发任务后必须记录任务开始时间。

如果 Server 在 `server_task_timeout_ms` 内没有收到 `ai.result` 或 `ai.task_error`：

- 将任务状态标记为 `timeout`。
- 返回前端“生成超时，请稍后重试”。
- 如果后续 Worker 又返回结果，该结果视为 late result。
- late result 可以记录日志，但不再返回给原 HTTP 请求。

建议 Server 超时时间略大于 Worker 任务超时：

```text
Worker 任务超时：180 秒
Server 等待超时：200 秒
```

### 13.3 Frontend 超时

Frontend 请求超时应略大于 Server 等待超时。

建议：

```text
Server 等待超时：200 秒
Frontend 请求超时：210-220 秒
```

Frontend 超时后应展示可恢复错误，例如：

```text
生成时间过长，请稍后重试。
```

### 13.4 超时处理原则

任务超时由服务器和 Worker 双方都应控制：

- 服务器负责前端请求超时。
- Worker 负责 Ollama 调用超时。
- 任一方超时，都应该返回结构化错误。
- Server 已经超时的任务，不应因为 Worker 的 late result 改写前端响应。
- 可重试的超时错误可以保留给后续重试队列使用。

---

## 14. 第一版最小实现要求

### 14.1 Worker 必须实现

- 主动连接服务器 WebSocket。
- 连接成功后发送 `worker.register`。
- 定时发送 `worker.heartbeat`。
- 接收 `ai.task`。
- 调用 Ollama。
- 返回 `ai.result` 或 `ai.task_error`。
- 断线后自动重连。

### 14.2 Server 必须实现

- 接收 Worker WebSocket 连接。
- 接收并记录 Worker 注册信息。
- 接收 Worker 心跳。
- 提供一个 HTTP 测试接口创建 AI 任务。
- 把 AI 任务发送给已连接 Worker。
- 等待 Worker 返回结果。
- 把结果返回给 HTTP 调用方。

---

## 15. 后续扩展

第一版跑通后可扩展：

- 流式 token 返回。
- 多 Worker 选择。
- Worker 权重和负载均衡。
- Redis / BullMQ 任务队列。
- Worker 鉴权 token。
- 任务重试。
- 任务恢复。
- 模型能力声明。
- 用户级模型权限控制。
