# DreamWeave Database

第一版数据库使用 PostgreSQL。

当前目录提供：

```text
apps/database/
├── migrations/
│   └── 001_init.sql
└── seeds/
    └── 001_local_dev.sql
```

## 初始化数据库

示例：

```powershell
createdb dreamweave
psql -d dreamweave -f .\apps\database\migrations\001_init.sql
psql -d dreamweave -f .\apps\database\seeds\001_local_dev.sql
```

如果使用连接串：

```powershell
$env:DATABASE_URL = "postgres://postgres:postgres@127.0.0.1:5432/dreamweave"
psql $env:DATABASE_URL -f .\apps\database\migrations\001_init.sql
psql $env:DATABASE_URL -f .\apps\database\seeds\001_local_dev.sql
```

## 本地开发默认数据

seed 会创建：

```text
user_local
story_local
session_local
```

这些 ID 与当前 H5 / Server 的本地默认值保持一致。

## 当前状态

当前已完成第一版数据库设计、SQL 初始化脚本和 server 运行时接入。

已完成：

- `apps/server` 通过 `DATABASE_URL` 连接 PostgreSQL。
- `apps/server` 在 `POST /api/story/continue` 请求中自动 upsert `users`、`stories`、`sessions`。
- 用户输入和 AI 回复会写入 `messages`。
- AI 任务状态、输出和错误信息会写入 `ai_tasks`。
- `GET /api/sessions/:session_id/messages` 可以读取会话历史消息。

下一步是在服务器拉取最新代码，执行 `npm install --omit=dev` 安装 `pg` 依赖，重启 PM2，并在线上用一次真实生成验证 `messages` 和 `ai_tasks` 写入结果。
