# DreamWeave 世界观编辑器与 RAG 升级规划

更新日期：2026-05-28

---

# 1. 项目目标

当前 DreamWeave 已完成：

* H5 前端
* Node.js Server
* PostgreSQL
* Python Local AI Worker
* Ollama 本地模型
* StoryState
* 多故事 / 多会话
* 最小 Agent 工作流
* Lore 文件系统

下一阶段目标：

```text
把“简单 Lore 文件系统”
升级为
“可视化世界观编辑器 + RAG 检索系统”
```

最终实现：

```text
用户在网页端编辑世界观
↓
系统保存 Lore
↓
自动写入向量数据库
↓
生成剧情时自动检索相关设定
↓
AI 根据世界观稳定生成剧情
```

---

# 2. 当前系统架构

```text
H5 / Mobile Web
        ↓
Node.js Server
        ├─ HTTP API
        ├─ PostgreSQL
        ├─ StoryState
        ├─ Session 管理
        └─ Worker 管理
        ↓ WebSocket
Python Local AI Worker
        ├─ Agent Workflow
        ├─ Prompt 编排
        ├─ Lore 检索
        ├─ Memory
        └─ Ollama Gateway
        ↓
Ollama
```

当前 Lore：

```text
Lore 文件
+
简单关键词检索
```

下一阶段升级为：

```text
网页端 Lore 编辑器
+
结构化世界书
+
Chroma / Qdrant
+
RAG 检索
```

---

# 3. 新阶段目标

新增：

```text
世界观编辑器
Lore 条目管理
关键词触发
优先级控制
启用 / 禁用
向量库入库
RAG 检索
```

但：

```text
不能破坏现有 WebSocket Worker 架构
不能替换当前 Server
不能影响当前 StoryState
```

---

# 4. 世界观编辑器设计

---

# 4.1 编辑器目标

网页端支持：

```text
创建世界
编辑世界
创建 Lore 条目
编辑 Lore 条目
启用 / 禁用
关键词配置
分类管理
优先级管理
RAG 测试
```

---

# 4.2 页面结构

```text
世界管理页
 ├─ 世界列表
 ├─ 创建世界
 ├─ 编辑世界
 └─ 删除世界

Lore 编辑页
 ├─ Lore 条目列表
 ├─ 搜索
 ├─ 分类过滤
 ├─ 编辑器
 ├─ 启用 / 禁用
 ├─ 优先级
 └─ RAG 测试
```

---

# 4.3 Lore 条目结构

```json
{
  "id": "lore_xxx",
  "world_id": "cultivation_world",
  "category": "location",
  "title": "玄阴谷",
  "keywords": [
    "玄阴谷",
    "禁地",
    "魔气",
    "后山"
  ],
  "content": "玄阴谷是青云宗禁地，金丹以下弟子禁止进入。",
  "priority": 80,
  "enabled": true,
  "metadata": {
    "author": "system"
  }
}
```

---

# 5. Lore 分类设计

支持：

```text
lore
character
rule
location
faction
style
event
```

---

# 5.1 lore

世界背景。

例如：

```text
历史
文明
神话
世界结构
```

---

# 5.2 character

角色设定。

例如：

```text
性格
身份
秘密
行为风格
```

---

# 5.3 rule

世界规则。

例如：

```text
修炼等级
禁忌
法则
```

---

# 5.4 location

地点设定。

例如：

```text
城市
宗门
地下城
```

---

# 5.5 faction

势力设定。

例如：

```text
宗门
帝国
公司
组织
```

---

# 5.6 style

文风设定。

例如：

```text
黑暗压抑
轻小说
克苏鲁
赛博朋克
```

---

# 6. 数据库升级

新增表：

---

# 6.1 worlds

```sql
CREATE TABLE worlds (
  id text PRIMARY KEY,
  user_id text NOT NULL,
  title text NOT NULL,
  description text,
  cover_image text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
```

---

# 6.2 lore_entries

```sql
CREATE TABLE lore_entries (
  id text PRIMARY KEY,
  world_id text NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
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
```

---

# 6.3 索引

```sql
CREATE INDEX idx_lore_world
ON lore_entries(world_id);

CREATE INDEX idx_lore_category
ON lore_entries(category);

CREATE INDEX idx_lore_enabled
ON lore_entries(enabled);
```

---

# 7. 向量数据库设计

第一版推荐：

```text
Chroma
```

后续再升级：

```text
Qdrant
```

---

# 7.1 Collection 结构

```text
world_{world_id}
```

例如：

```text
world_cultivation_world
world_cyberpunk_world
world_dark_fantasy
```

---

# 7.2 向量内容

每条 Lore：

```text
title
+
keywords
+
content
```

组合后生成 embedding。

---

# 7.3 Metadata

```json
{
  "world_id": "cultivation_world",
  "category": "location",
  "priority": 80,
  "enabled": true
}
```

---

# 8. RAG 工作流

---

# 8.1 保存 Lore

```text
H5 编辑 Lore
        ↓
POST /api/worlds/:world_id/lore
        ↓
保存 PostgreSQL
        ↓
生成 embedding
        ↓
写入 Chroma
```

---

# 8.2 生成剧情

```text
用户输入
        ↓
Server 读取 StoryState
        ↓
Worker 执行 Agent
        ↓
retrieve_lore
        ↓
Chroma 检索
        ↓
返回相关 Lore
        ↓
注入 Prompt
        ↓
Ollama 生成剧情
```

---

# 9. 检索逻辑

---

# 9.1 检索输入

使用：

```text
user_input
+
current_scene
+
active_characters
+
story_stage
```

组合为查询。

---

# 9.2 检索过滤

必须过滤：

```text
world_id
enabled = true
```

避免：

```text
不同小说世界观污染
```

---

# 9.3 检索数量

第一版：

```text
top_k = 5
```

---

# 10. Worker 升级

---

# 10.1 当前

```text
Lore 文件读取
+
关键词检索
```

---

# 10.2 升级后

```text
Chroma 检索
+
RAG
```

---

# 10.3 新增模块

```text
agent/
├── rag.py
├── embeddings.py
├── vector_store.py
└── lore_repository.py
```

---

# 11. Worker 流程图

```text
用户输入
    ↓
Server
    ↓
读取 StoryState
    ↓
发送 ai.task
    ↓
Worker
    ↓
load_context
    ↓
retrieve_lore
    ↓
Chroma 检索
    ↓
plan_narrative
    ↓
generate_story
    ↓
quality_check
    ↓
build_state_update
    ↓
返回 content + state_update
    ↓
Server 保存
    ↓
H5 显示剧情
```

---

# 12. API 设计

---

# 12.1 世界管理

```text
POST   /api/worlds
GET    /api/worlds
GET    /api/worlds/:id
PUT    /api/worlds/:id
DELETE /api/worlds/:id
```

---

# 12.2 Lore 管理

```text
POST   /api/worlds/:world_id/lore
GET    /api/worlds/:world_id/lore
PUT    /api/worlds/:world_id/lore/:id
DELETE /api/worlds/:world_id/lore/:id
```

---

# 12.3 RAG 调试

```text
POST /api/worlds/:world_id/rag/test
```

请求：

```json
{
  "query": "我进入玄阴谷"
}
```

返回：

```json
{
  "results": [
    {
      "title": "玄阴谷",
      "score": 0.92
    }
  ]
}
```

---

# 13. H5 页面设计

---

# 13.1 世界管理页

```text
世界列表
+
创建世界
+
编辑世界
```

---

# 13.2 Lore 编辑器

支持：

```text
标题
关键词
分类
正文
优先级
启用/禁用
```

---

# 13.3 RAG 测试页

输入：

```text
测试查询
```

查看：

```text
实际检索结果
```

用于调试世界观。

---

# 14. 目录结构升级

---

# 14.1 Server

```text
apps/server/src/
├── modules/
│   ├── worlds/
│   ├── lore/
│   └── rag/
```

---

# 14.2 Worker

```text
apps/local-ai-worker/src/dreamweave_worker/
├── agent/
│   ├── graph.py
│   ├── nodes.py
│   ├── rag.py
│   ├── embeddings.py
│   ├── vector_store.py
│   └── lore_repository.py
```

---

# 14.3 Packages

```text
packages/
├── worlds/
├── prompts/
└── schemas/
```

---

# 15. 开发阶段

---

# 阶段 A

```text
世界管理
Lore CRUD
PostgreSQL 保存
```

---

# 阶段 B

```text
Lore 编辑器
分类
关键词
优先级
启用/禁用
```

---

# 阶段 C

```text
Chroma 接入
embedding
向量入库
```

---

# 阶段 D

```text
Worker retrieve_lore
改为 Chroma 检索
```

---

# 阶段 E

```text
RAG 调试页
检索测试
Prompt 可视化
```

---

# 16. 当前阶段不要做的内容

暂时不要：

```text
复杂多 Agent
NPC 自主行为
自动剧情树
长期记忆向量化
复杂角色 AI
自动世界生成
```

先把：

```text
Lore
+
RAG
+
世界状态
```

稳定。

---

# 17. 最终目标

最终：

DreamWeave 不只是：

```text
AI聊天
```

而是：

```text
AI世界引擎
```

核心结构：

```text
StoryState
+
Lore
+
Memory
+
RAG
+
Agent Workflow
+
LLM
```

形成：

```text
长期运行中的互动小说宇宙
```
