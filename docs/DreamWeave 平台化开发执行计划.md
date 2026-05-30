# DreamWeave 平台化开发执行计划

更新日期：2026-05-30

当前执行状态：P0-P2 第一版已完成本地实现和线上验证；P3 作者后台 MVP 与 P4 Lore CRUD 已完成本地实现，待线上部署验证。

## 1. 目标

把当前已经可用的“多故事 / 多会话 AI 小说工具”推进到第一版“AI 互动小说平台”：

```text
作者创建作品和世界观
        ↓
玩家在大厅浏览作品
        ↓
玩家开始游玩并创建独立存档
        ↓
Worker 基于 StoryState + Lore / RAG 生成剧情
        ↓
玩家持续互动
```

本计划只覆盖下一阶段开发落地，不替代已有需求规划文档：

- `docs/DreamWeave 作者后台 + 玩家大厅 + 世界观编辑器 升级规划.md`
- `docs/DreamWeave 世界观编辑器与 RAG 升级规划.md`
- `docs/项目进度.md`

## 2. 当前基线

已具备：

- Node.js Server 单文件实现，负责 HTTP API、WebSocket Worker 管理和 PostgreSQL 持久化。
- H5 单页面应用，已支持故事 / 会话库、故事设定保存、聊天生成和 StoryState 展示。
- Python Worker 已接入最小 Agent 工作流、Lore 文件检索、质量检查、自动修订和 `state_update`。
- PostgreSQL 已有 `users`、`stories`、`sessions`、`messages`、`ai_tasks`、`story_states`。
- 当前 Lore 来源仍是 `packages/worlds/default_world/` 文件系统和简单关键词检索。

本阶段开发原则：

- 不重写现有 Server。
- 不破坏现有 `/api/story/continue` 和 Worker WebSocket 协议。
- 不立刻做完整多用户权限系统。
- 不立刻做 LangGraph、多 Agent、NPC 自主行为或自动剧情树。
- 新能力优先复用现有 `stories` / `sessions`，等体验跑通后再抽象 `works` / `play_sessions`。

## 3. 总体阶段

推荐开发顺序：

```text
P0 数据模型决策和兼容层
P1 玩家大厅 MVP
P2 开始游玩和存档创建
P3 作者后台 MVP
P4 Lore CRUD 和世界观编辑器
P5 RAG 数据入库
P6 Worker RAG 检索
P7 RAG 调试页和 Prompt 可视化
P8 安全、权限、队列和生产化
```

## 4. P0：数据模型决策和兼容层

### 4.1 目标

先明确平台化概念与当前表结构的映射，避免过早迁移导致现有功能不稳定。

### 4.2 决策

第一版采用兼容映射：

```text
Work       → 第一版复用 stories
PlaySession → 第一版复用 sessions
World      → 第一版先作为 story 的结构化扩展，后续可独立 worlds 表
LoreEntry  → 新增 lore_entries 表
```

原因：

- 当前 `stories` 已有标题、世界观、角色设定、默认模型和生成参数。
- 当前 `sessions` 已能承载独立剧情进度和 StoryState。
- 玩家大厅可以先读取公开状态的 stories。
- 作者后台可以先管理 stories，再逐步迁移到 works 命名。

### 4.3 第一版最小字段补充

建议新增 migration `003_platform_fields.sql`：

```sql
ALTER TABLE stories
  ADD COLUMN IF NOT EXISTS description text,
  ADD COLUMN IF NOT EXISTS cover_image text,
  ADD COLUMN IF NOT EXISTS tags text[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'draft',
  ADD COLUMN IF NOT EXISTS opening_message text,
  ADD COLUMN IF NOT EXISTS author_id text;

CREATE INDEX IF NOT EXISTS idx_stories_status_updated
  ON stories(status, updated_at DESC);
```

说明：

- `status` 第一版使用 `draft`、`published`、`archived`。
- `author_id` 第一版可等同 `user_id`，为后续多用户作者系统预留。
- `opening_message` 用于玩家首次进入作品时自动创建开场消息。

### 4.4 验收

- 现有故事 / 会话功能不受影响。
- 旧数据在 migration 后仍能读取。
- 没有 `status` 的旧故事默认视为 `draft` 或在 seed 中补齐。

## 5. P1：玩家大厅 MVP

### 5.1 目标

新增玩家端作品大厅，让玩家可以浏览已发布作品。

页面：

```text
/discover
```

API：

```text
GET /api/works
GET /api/works/:id
```

第一版实现时可由 Server 从 `stories` 读取：

```text
GET /api/works      → 查询 stories where status = 'published'
GET /api/works/:id  → 查询单个 story
```

### 5.2 展示字段

作品卡片：

- 封面
- 标题
- 标签
- 作者
- 简介
- 开始游玩入口

详情页：

- 封面
- 标题
- 简介
- 标签
- 世界观介绍
- 角色介绍
- 开场白预览
- 开始游玩按钮

### 5.3 前端实现建议

当前 H5 是单页面结构，第一版可以先不引入路由框架，使用 hash 或内存视图：

```text
#/discover
#/works/:id
#/play/:session_id
#/creator/works
```

如果继续使用静态托管，避免引入复杂构建链。

### 5.4 验收

- 玩家打开 `/discover` 能看到已发布作品。
- 点击作品能进入详情页。
- 未发布作品不出现在大厅。
- 原聊天页仍可使用。

## 6. P2：开始游玩和存档创建

### 6.1 目标

玩家从作品详情页点击“开始游玩”，系统创建独立存档并进入游玩页。

API：

```text
POST /api/works/:id/play
```

请求：

```json
{
  "player_id": "user_local"
}
```

响应：

```json
{
  "story_id": "story_xxx",
  "session_id": "session_xxx"
}
```

### 6.2 后端流程

```text
1. 校验作品存在且 status = published
2. 创建 sessions 记录
3. 初始化 story_states
4. 如果作品有 opening_message，插入 assistant message
5. 返回 session_id
```

### 6.3 StoryState 初始化

第一版建议：

```json
{
  "current_world": "default_world",
  "current_scene": "",
  "story_stage": "opening",
  "long_summary": "",
  "characters": {},
  "relationships": {},
  "world_flags": {},
  "inventory": [],
  "pending_events": [],
  "user_preferences": {},
  "style_profile": {}
}
```

### 6.4 验收

- 同一个作品可以创建多个 session。
- 每个 session 有独立 StoryState。
- 从大厅创建的 session 可以继续使用现有 `/api/story/continue` 生成。
- 开场白只在新存档创建时写入一次。

## 7. P3：作者后台 MVP

### 7.1 目标

新增作者端作品管理页，管理作品草稿、发布和下架。

页面：

```text
/creator/works
/creator/works/:id
```

API：

```text
GET    /api/creator/works
POST   /api/creator/works
GET    /api/creator/works/:id
PUT    /api/creator/works/:id
DELETE /api/creator/works/:id
POST   /api/creator/works/:id/publish
POST   /api/creator/works/:id/unpublish
```

第一版仍可落到 `stories` 表。

### 7.2 编辑字段

- 标题
- 简介
- 封面地址
- 标签
- 世界观设定
- 角色设定
- 默认模型
- 生成参数
- 开场白
- 发布状态

### 7.3 验收

- 作者可以创建草稿作品。
- 作者可以编辑作品设定并保存。
- 作者可以发布作品，发布后出现在玩家大厅。
- 作者可以下架作品，下架后不再出现在玩家大厅。
- 删除作品仍沿用当前级联删除策略，必须二次确认。

## 8. P4：Lore CRUD 和世界观编辑器

### 8.1 目标

把当前文件 Lore 升级为数据库 Lore 条目管理。

新增 migration `004_lore_entries.sql`：

```sql
CREATE TABLE IF NOT EXISTS lore_entries (
  id text PRIMARY KEY,
  story_id text NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  category text NOT NULL,
  title text NOT NULL,
  keywords text[] NOT NULL DEFAULT '{}',
  content text NOT NULL,
  priority integer NOT NULL DEFAULT 50,
  enabled boolean NOT NULL DEFAULT true,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lore_entries_story
  ON lore_entries(story_id);

CREATE INDEX IF NOT EXISTS idx_lore_entries_category
  ON lore_entries(category);

CREATE INDEX IF NOT EXISTS idx_lore_entries_enabled
  ON lore_entries(enabled);
```

说明：

- 第一版使用 `story_id`，后续如果拆出 `works` / `worlds`，再迁移为 `work_id` 或 `world_id`。
- PostgreSQL 是权威数据源。

### 8.2 API

```text
GET    /api/creator/works/:story_id/lore
POST   /api/creator/works/:story_id/lore
PUT    /api/creator/works/:story_id/lore/:id
DELETE /api/creator/works/:story_id/lore/:id
```

### 8.3 分类

第一版固定支持：

```text
lore
character
location
faction
rule
style
event
```

### 8.4 页面能力

- Lore 列表
- 搜索
- 分类过滤
- 启用 / 禁用
- 优先级编辑
- 关键词编辑
- 正文编辑

### 8.5 验收

- 作者可以为作品新增、编辑、删除 Lore。
- 禁用 Lore 不参与检索。
- Lore 可按分类过滤。
- 不影响现有文件 Lore；第一版可以保留文件 Lore 作为兜底。

## 9. P5：RAG 数据入库

### 9.1 目标

Lore 保存后生成 embedding，并写入 Chroma。

第一版组件：

```text
PostgreSQL lore_entries
        ↓
Embedding provider
        ↓
Chroma collection
```

Collection 命名：

```text
story_{story_id}
```

后续迁移到作品模型后可改为：

```text
work_{work_id}
world_{world_id}
```

### 9.2 Worker 新模块

```text
apps/local-ai-worker/src/dreamweave_worker/agent/
├── embeddings.py
├── vector_store.py
├── rag.py
└── lore_repository.py
```

### 9.3 同步策略

第一版推荐同步写入：

```text
保存 lore_entries 成功
        ↓
调用 embedding
        ↓
写入 Chroma
        ↓
返回保存结果
```

如果 Chroma 写入失败：

- PostgreSQL 保存仍然成功。
- 返回中附带 `rag_index_status = failed`。
- 后续提供重新索引接口。

### 9.4 API

```text
POST /api/creator/works/:story_id/lore/:id/reindex
POST /api/creator/works/:story_id/lore/reindex
```

### 9.5 验收

- 新增 Lore 后 Chroma 中有对应向量。
- 更新 Lore 后向量同步更新。
- 删除 Lore 后向量同步删除或标记失效。
- Chroma 失败不影响基础作品编辑。

## 10. P6：Worker RAG 检索

### 10.1 目标

把 Worker 的 `retrieve_lore` 从文件关键词检索升级为 RAG 检索。

检索输入：

```text
user_input
+
current_scene
+
active_characters
+
story_stage
```

过滤条件：

```text
story_id
enabled = true
```

第一版：

```text
top_k = 5
```

### 10.2 兼容策略

检索顺序：

```text
1. 如果 Chroma 可用，使用 Chroma RAG
2. 如果 Chroma 不可用，使用 PostgreSQL Lore 关键词检索
3. 如果数据库 Lore 不可用，回退到 packages/worlds/default_world 文件检索
```

### 10.3 验收

- Worker 生成任务时能读取当前 story 的 Lore。
- 不同 story 的 Lore 不互相污染。
- 禁用 Lore 不会注入 Prompt。
- Chroma 不可用时，生成链路仍可工作。

## 11. P7：RAG 调试页和 Prompt 可视化

### 11.1 目标

让作者能看到某个查询实际召回了哪些 Lore，便于调试世界观。

API：

```text
POST /api/creator/works/:story_id/rag/test
```

请求：

```json
{
  "query": "我进入玄阴谷"
}
```

响应：

```json
{
  "results": [
    {
      "id": "lore_xxx",
      "title": "玄阴谷",
      "category": "location",
      "score": 0.92,
      "priority": 80,
      "content_preview": "玄阴谷是青云宗禁地..."
    }
  ]
}
```

### 11.2 页面能力

- 输入测试 query。
- 查看召回结果。
- 查看分数和优先级。
- 查看是否来自 Chroma、PostgreSQL 关键词检索或文件兜底。
- 后续可展示本轮 Prompt 注入片段。

### 11.3 验收

- 作者可用自然语言测试召回。
- 结果能定位 Lore 标题、分类、分数和内容预览。
- 可以发现跨作品污染、漏召、禁用条目误召回等问题。

## 12. P8：生产化后置项

这些暂不阻塞平台化 MVP：

- Worker 鉴权。
- 用户注册 / 登录。
- 作者与玩家权限隔离。
- Redis / BullMQ 任务队列。
- HTTPS 和域名。
- PostgreSQL 自动备份。
- Chroma 持久化部署方案。
- Qdrant 替换或多向量库适配。
- 日志分级和管理后台。

## 13. 第一轮开工建议

建议第一轮只做 P0 到 P2：

```text
003_platform_fields.sql
        ↓
GET /api/works
GET /api/works/:id
POST /api/works/:id/play
        ↓
H5 discover 视图
H5 work detail 视图
开始游玩创建 session
        ↓
复用现有 play / chat 生成链路
```

第一轮完成后，DreamWeave 会具备最小平台体验：

```text
作者准备一个 published 作品
        ↓
玩家在大厅看到作品
        ↓
玩家点击开始游玩
        ↓
系统创建独立存档
        ↓
玩家进入现有聊天体验继续剧情
```

## 14. 第一轮任务清单

### 14.1 数据库

- [x] 新增 `003_platform_fields.sql`。
- [x] 给 seed 增加一个 `published` 示例作品。
- [x] 更新 `docs/数据库设计.md`，补充平台化字段。

### 14.2 Server

- [x] 新增 `GET /api/works`。
- [x] 新增 `GET /api/works/:id`。
- [x] 新增 `POST /api/works/:id/play`。
- [x] 创建 session 时初始化 StoryState。
- [x] 支持 opening_message 写入第一条 assistant message。

### 14.3 H5

- [x] 增加视图状态或 hash 路由。
- [x] 增加作品大厅视图。
- [x] 增加作品详情视图。
- [x] 增加开始游玩按钮。
- [x] 开始游玩成功后切换到当前 session。

### 14.4 验证

- [x] `node --check apps/server/src/index.js`
- [x] `node --check apps/mobile-web/app.js`
- [x] `python test_agent_workflow.py`
- [x] 本地 smoke test `/api/works`。
- [x] 线上手测开始游玩后继续生成。
- [x] 线上部署后复核 `sessions`、`messages`、`story_states` 写入。

## 15. 第二轮任务清单：P3 作者后台 MVP

### 15.1 Server

- [x] 新增 `GET /api/creator/works`。
- [x] 新增 `POST /api/creator/works`。
- [x] 新增 `GET /api/creator/works/:id`。
- [x] 新增 `PUT /api/creator/works/:id`。
- [x] 新增 `DELETE /api/creator/works/:id`。
- [x] 新增 `POST /api/creator/works/:id/publish`。
- [x] 新增 `POST /api/creator/works/:id/unpublish`。

### 15.2 H5

- [x] 增加作者后台入口。
- [x] 增加 `#/creator/works` 作品管理视图。
- [x] 支持创建草稿作品。
- [x] 支持编辑标题、简介、标签、世界观、角色设定、开场白、默认模型。
- [x] 支持发布 / 下架作品。
- [x] 支持删除作品并二次确认。

### 15.3 验证

- [x] `node --check apps/server/src/index.js`
- [x] `node --check apps/mobile-web/app.js`
- [x] `python test_agent_workflow.py`
- [x] 本地 smoke test `GET /api/creator/works`。
- [ ] 本地手测作者创建草稿、发布后在大厅可见。
- [ ] 线上部署后复核 `stories.status`、`opening_message` 和大厅可见性。

## 16. 第三轮任务清单：P4 Lore CRUD 和世界观编辑器

### 16.1 数据库

- [x] 新增 `004_lore_entries.sql`。
- [x] 新增 `lore_entries` 表、索引和 `updated_at` trigger。

### 16.2 Server

- [x] 新增 `GET /api/creator/works/:story_id/lore`。
- [x] 新增 `POST /api/creator/works/:story_id/lore`。
- [x] 新增 `PUT /api/creator/works/:story_id/lore/:id`。
- [x] 新增 `DELETE /api/creator/works/:story_id/lore/:id`。
- [x] Lore CRUD 按作者作品所有权校验。

### 16.3 H5

- [x] 在作者后台接入 Lore 条目列表。
- [x] 支持新增 Lore。
- [x] 支持编辑标题、分类、关键词、优先级、启用状态和正文。
- [x] 支持删除 Lore 并二次确认。

### 16.4 验证

- [x] `node --check apps/server/src/index.js`
- [x] `node --check apps/mobile-web/app.js`
- [x] `python test_agent_workflow.py`
- [ ] 本地手测 Lore 新增、编辑、禁用、删除。
- [ ] 线上部署后执行 `004_lore_entries.sql` 并复核 Lore CRUD。

## 17. 暂缓事项

第一轮不要做：

- 独立 `works` / `play_sessions` 大迁移。
- Chroma 接入。
- 新前端框架。
- 登录注册。
- 多 Agent。
- LangGraph。
- 图片 / CG。
- 推荐系统。

这些会增加开发面和故障面，不利于先跑通平台化 MVP。
