# DreamWeave Server

这是第一版最小服务器，用于跑通：

```text
HTTP 请求 → Server → Worker WebSocket → Ollama → Worker → Server → HTTP 返回
```

当前使用 Node.js 内置 `http`、`net`、`crypto` 实现最小 HTTP 和 WebSocket 能力，并通过 `pg` 接入 PostgreSQL 做第一版消息持久化。后续功能稳定后，可以迁移到 NestJS、Redis/BullMQ。

## 配置

server 会自动读取以下 `.env` 位置：

- 当前启动目录下的 `.env`
- 项目根目录 `.env`
- `/opt/dreamweave/.env`

关键配置：

```text
DREAMWEAVE_SERVER_HOST=127.0.0.1
DREAMWEAVE_SERVER_PORT=3000
DREAMWEAVE_WORKER_PATH=/ws/worker
DATABASE_URL=postgres://dreamweave_app:change_me@127.0.0.1:5432/dreamweave
```

## 启动

```powershell
cd E:\ai_home\AI_Projects\DreamWeave\apps\server
npm install
npm run start
```

默认地址：

```text
http://127.0.0.1:3000
ws://127.0.0.1:3000/ws/worker
```

`http://127.0.0.1:3000/` 会直接打开 `apps/mobile-web` 页面。

## 健康检查

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:3000/health"
```

## 创建测试任务

需要先启动本地 Worker：

```powershell
. E:\ai_home\AI_Projects\llm_env\Scripts\Activate.ps1
cd E:\ai_home\AI_Projects\DreamWeave
python .\apps\local-ai-worker\main.py connect --server ws://127.0.0.1:3000/ws/worker
```

然后调用：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:3000/api/story/continue" `
  -ContentType "application/json" `
  -Body '{"message":"我推开了古堡的大门。","model":"qwen3:14b"}'
```

## 当前接口

### `GET /health`

查看服务器、数据库和 Worker 状态。

### `GET /`

打开 H5 互动页面。

### `GET /workers`

查看已连接 Worker。

### `GET /api/sessions/:session_id/messages`

读取某个会话的历史消息。当前 H5 默认读取：

```text
/api/sessions/local_session/messages
```

### `POST /api/story/continue`

创建小说续写任务。配置 `DATABASE_URL` 后，server 会保存用户输入、AI 回复和 AI 任务状态。

请求体示例：

```json
{
  "user_id": "user_001",
  "session_id": "session_001",
  "story_id": "story_001",
  "model": "qwen3:14b",
  "message": "我推开了古堡的大门。",
  "timeout_ms": 180000,
  "generation_options": {
    "num_predict": 220,
    "temperature": 0.66,
    "top_p": 0.85,
    "think": false
  },
  "context": {
    "story_title": "黑夜古堡",
    "world_setting": "中世纪奇幻世界",
    "character_setting": "用户是失忆的贵族继承人",
    "recent_messages": []
  }
}
```

返回成功示例：

```json
{
  "task_id": "task_xxx",
  "status": "success",
  "content": "沉重的木门缓缓打开……",
  "model": "qwen3:14b",
  "worker_id": "local-dev-001"
}
```
