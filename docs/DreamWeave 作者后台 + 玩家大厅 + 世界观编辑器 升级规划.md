# DreamWeave 作者后台 + 玩家大厅 + 世界观编辑器 升级规划

更新日期：2026-05-28

---

# 1. 新阶段目标

DreamWeave 当前已经完成：

```text
H5
Server
Worker
Ollama
StoryState
多故事
最小 Agent
```

下一阶段目标：

```text
把 DreamWeave 从：
“单用户 AI 小说工具”

升级为：

“AI互动小说平台”
```

核心结构：

```text
作者创建世界
↓
玩家点击进入世界
↓
AI 驱动长期互动剧情
```

---

# 2. 新系统结构

系统需要拆成：

```text
作者端（Creator）
+
玩家端（Player）
```

---

# 3. 作者端目标

作者负责：

```text
创建作品
编辑世界观
编辑角色
编辑 Lore
编辑规则
编辑开场白
发布作品
管理作品
```

作者端是：

```text
复杂编辑后台
```

---

# 4. 玩家端目标

玩家负责：

```text
浏览作品
点击作品
开始游玩
持续互动
保存存档
继续剧情
```

玩家端应该：

```text
极简
像游戏平台
```

类似：

```text
AI Dungeon
NovelAI
Character.AI
互动视觉小说
```

---

# 5. 新系统架构

```text
玩家 H5
    ↓
作品大厅
    ↓
点击作品
    ↓
创建 PlaySession
    ↓
初始化 StoryState
    ↓
进入聊天页面
    ↓
Worker + Ollama
    ↓
持续互动剧情
```

---

# 6. 新核心概念

---

# 6.1 Work（作品模板）

作者创建的公共作品。

例如：

```text
修仙世界
赛博朋克世界
黑暗奇幻
恋爱校园
```

Work 是：

```text
公共模板
```

包含：

```text
世界观
角色
Lore
开场白
Prompt
规则
```

---

# 6.2 PlaySession（玩家存档）

玩家点击：

```text
开始游玩
```

后：

系统创建：

```text
独立 Session
```

每个玩家：

```text
拥有自己的剧情进度
```

即：

```text
同一个作品
不同玩家
不同剧情
```

---

# 6.3 StoryState（世界状态）

每个 Session：

```text
拥有独立 StoryState
```

包括：

```json
{
  "current_scene": "",
  "story_stage": "",
  "relationships": {},
  "inventory": {},
  "world_flags": {},
  "characters": {}
}
```

---

# 7. 作者端页面结构

---

# 7.1 作品管理页

```text
/creator/works
```

支持：

```text
创建作品
编辑作品
删除作品
发布作品
下架作品
```

---

# 7.2 世界观编辑器

```text
/creator/works/:id/world
```

支持：

```text
Lore 编辑
角色编辑
规则编辑
势力编辑
地点编辑
文风编辑
```

---

# 7.3 Lore 编辑器

支持：

```text
标题
关键词
正文
分类
优先级
启用/禁用
```

---

# 7.4 开场白编辑器

作者编辑：

```text
玩家首次进入剧情时
AI 自动发送内容
```

例如：

```text
夜雨落下。

你缓缓睁开眼。

破旧的客栈里，
只有一盏昏黄油灯还亮着。
```

---

# 8. 玩家端页面结构

---

# 8.1 作品大厅

```text
/discover
```

类似：

```text
游戏平台首页
```

展示：

```text
作品封面
标题
标签
热度
作者
简介
```

---

# 8.2 作品详情页

```text
/works/:id
```

展示：

```text
封面
简介
标签
世界观介绍
角色介绍
开始游玩按钮
```

---

# 8.3 游玩页

```text
/play/:session_id
```

展示：

```text
聊天UI
CG
选项
状态
角色
```

---

# 9. 数据库升级

---

# 9.1 works

作品模板。

```sql
CREATE TABLE works (
  id text PRIMARY KEY,
  author_id text NOT NULL,
  title text NOT NULL,
  description text,
  cover_image text,
  tags text[] NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'draft',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
```

---

# 9.2 play_sessions

玩家存档。

```sql
CREATE TABLE play_sessions (
  id text PRIMARY KEY,
  work_id text NOT NULL REFERENCES works(id),
  player_id text NOT NULL,
  current_state_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
```

---

# 9.3 story_states

当前世界状态。

```sql
CREATE TABLE story_states (
  id text PRIMARY KEY,
  session_id text NOT NULL REFERENCES play_sessions(id),
  state jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

---

# 9.4 lore_entries

世界观条目。

```sql
CREATE TABLE lore_entries (
  id text PRIMARY KEY,
  work_id text NOT NULL REFERENCES works(id),
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

# 10. Lore 分类

支持：

```text
lore
character
location
faction
rule
style
event
```

---

# 11. RAG 系统

---

# 11.1 当前

```text
Lore 文件
+
简单检索
```

---

# 11.2 升级后

```text
Chroma / Qdrant
+
向量检索
+
RAG
```

---

# 11.3 流程

```text
作者编辑 Lore
        ↓
保存 PostgreSQL
        ↓
生成 embedding
        ↓
写入 Chroma
```

---

# 11.4 玩家互动时

```text
用户输入
        ↓
Worker retrieve_lore
        ↓
Chroma 检索
        ↓
返回相关世界观
        ↓
注入 Prompt
        ↓
Ollama 生成剧情
```

---

# 12. 向量数据库设计

第一阶段：

```text
Chroma
```

后续：

```text
Qdrant
```

---

# 12.1 Collection

```text
work_{work_id}
```

例如：

```text
work_cultivation
work_cyberpunk
```

---

# 12.2 Metadata

```json
{
  "work_id": "",
  "category": "",
  "priority": 80,
  "enabled": true
}
```

---

# 13. Worker 升级

新增：

```text
retrieve_lore
embedding
vector_store
rag_search
```

---

# 13.1 新目录

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

# 14. 新 Agent 工作流

```text
用户输入
    ↓
load_story_state
    ↓
load_memory
    ↓
retrieve_lore
    ↓
plan_narrative
    ↓
generate_story
    ↓
quality_check
    ↓
build_state_update
    ↓
save_story_state
```

---

# 15. 玩家大厅 UI

目标：

```text
像 AI 小说游戏平台
```

类似：

```text
卡片式作品广场
```

每个卡片：

```text
封面
标题
标签
作者
热度
简介
开始游玩
```

---

# 16. 开发阶段

---

# 阶段 A

```text
作品大厅
作品详情页
开始游玩
```

---

# 阶段 B

```text
作者后台
作品 CRUD
Lore CRUD
```

---

# 阶段 C

```text
世界观编辑器
角色编辑器
规则编辑器
```

---

# 阶段 D

```text
Chroma
embedding
RAG
```

---

# 阶段 E

```text
RAG 调试页
Prompt 可视化
```

---

# 17. 当前阶段不要做

暂时不要：

```text
多 Agent NPC
自动剧情树
AI 自动支线
复杂自治 NPC
自动世界生成
```

先把：

```text
作品
+
世界观
+
StoryState
+
RAG
```

稳定。

---

# 18. 最终目标

DreamWeave 最终目标：

不是：

```text
聊天机器人
```

而是：

```text
AI互动小说平台
+
AI世界引擎
```

核心：

```text
作者创造世界
玩家进入世界
AI长期运行世界
```
