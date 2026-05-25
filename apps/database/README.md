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

当前只完成数据库设计和 SQL 初始化脚本。

server 尚未接入 PostgreSQL。下一步需要在 `apps/server` 中增加数据库连接和消息写入逻辑。
