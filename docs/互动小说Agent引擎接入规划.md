# 织梦纪 DreamWeave 互动小说 Agent 引擎接入规划

更新日期：2026-05-27

## 1. 结论

`docs/互动小说Agent引擎.md` 的方向适合作为后续智能叙事内核，但它更像一份“从零生成 Python + FastAPI + LangGraph 项目”的架构提示词。

当前 DreamWeave 已经具备：

- H5 页面
- Node.js Server
- PostgreSQL 持久化
- WebSocket Worker 通信协议
- Python Local AI Worker
- Ollama 本地推理

因此不建议推倒现有架构重写为 FastAPI 后端。

更合理的接入方式是：

```text
H5
  ↓
Node.js Server
  - API
  - WebSocket 转发
  - PostgreSQL 持久化
  - 故事 / 会话 / 状态管理
  ↓
Python Local AI Worker
  - Agent 引擎
  - LangGraph 工作流
  - Prompt 编排
  - Lore 检索
  - Ollama 调用
  ↓
Ollama
```

也就是说，Agent 引擎应该作为 Python Worker 内部的“叙事生成内核”，而不是替换当前 Server。

---

## 2. 接入目标

把当前的“单次 Prompt 续写”升级为“状态化互动小说 Agent”。

升级后，每次用户输入时，系统应能够：

1. 读取当前故事状态。
2. 读取最近剧情历史。
3. 读取长期剧情摘要。
4. 读取角色、关系、世界事件、物品等状态。
5. 根据当前场景检索世界观资料。
6. 规划下一段剧情方向。
7. 调用 Ollama 生成小说正文。
8. 检查输出质量。
9. 更新故事状态。
10. 保存消息、任务和状态。
11. 返回最终小说正文给 H5。

---

## 3. 与现有项目的职责划分

### 3.1 H5

继续负责：

- 用户输入
- 展示 AI 回复
- 展示故事 / 会话列表
- 展示连接状态
- 切换模型
- 编辑故事基础设定

不建议让 H5 继续承担复杂上下文组装。

后续应逐步减少前端传入的 `recent_messages`，改为由 Server 从数据库读取。

### 3.2 Node.js Server

继续负责：

- HTTP API
- Worker WebSocket 管理
- PostgreSQL 读写
- `users`
- `stories`
- `sessions`
- `messages`
- `ai_tasks`
- `story_states`
- 任务下发和结果接收

Server 不负责复杂 Agent 推理。

Server 负责把数据库里的上下文组装成一个更完整的 AI 任务，然后交给 Worker。

### 3.3 Python Worker

升级为 Agent 执行层。

继续负责：

- 主动连接 Server
- 接收 `ai.task`
- 调用 Ollama
- 返回 `ai.result` / `ai.task_error`

新增负责：

- StoryState 解释和补全
- Memory 装载
- Lore 文件检索
- Narrative Prompt 编排
- LangGraph 工作流执行
- 输出质量检查
- 生成状态更新结果

### 3.4 PostgreSQL

继续作为主状态数据库。

当前已有：

- `users`
- `stories`
- `sessions`
- `messages`
- `ai_tasks`

建议新增：

- `story_states`

后续再考虑：

- `story_lore_documents`
- `story_memory_summaries`
- `story_checkpoints`

### 3.5 向量数据库

Qdrant / Chroma 暂不建议马上接入。

第一版先使用本地 Lore 文件 + 简单关键词检索。

等以下能力稳定后再接向量数据库：

- 多故事管理
- StoryState 持久化
- Agent 工作流稳定
- Lore 文件格式稳定

---

## 4. StoryState 设计

### 4.1 状态对象

建议第一版 StoryState 使用 JSON 对象保存：

```json
{
  "current_world": "default_world",
  "current_scene": "黑夜古堡大门内侧",
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

### 4.2 不建议放入 StoryState 的字段

以下字段不建议长期存在 `story_states.state` 中：

- `user_input`
- `recent_history`
- `retrieved_lore`
- `final_response`

原因：

- `user_input` 是本轮请求数据。
- `recent_history` 应从 `messages` 表读取。
- `retrieved_lore` 是本轮临时检索结果。
- `final_response` 已保存到 `messages`。

这些字段可以存在于 Worker 运行时的 AgentState，但不应作为长期故事状态保存。

### 4.3 数据库表建议

新增 migration：

```sql
CREATE TABLE IF NOT EXISTS story_states (
  session_id text PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
  user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  story_id text NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  state jsonb NOT NULL DEFAULT '{}'::jsonb,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_story_states_story
  ON story_states(story_id, updated_at DESC);
```

---

## 5. AgentState 运行时结构

Worker 内部可以使用比 StoryState 更完整的运行时状态：

```json
{
  "task_id": "task_xxx",
  "user_id": "local_user",
  "story_id": "local_story",
  "session_id": "local_session",
  "model": "qwen3:14b",
  "user_input": "我推开了古堡的大门。",
  "story_state": {},
  "recent_history": [],
  "long_summary": "",
  "retrieved_lore": [],
  "narrative_plan": "",
  "character_reactions": "",
  "draft_response": "",
  "final_response": "",
  "state_update": {},
  "quality": {
    "passed": true,
    "issues": []
  }
}
```

其中：

- `story_state` 来自 PostgreSQL。
- `recent_history` 来自 `messages`。
- `retrieved_lore` 来自 Lore 文件或未来向量库。
- `final_response` 返回给 Server。
- `state_update` 由 Server 合并回 `story_states.state`。

---

## 6. LangGraph 接入策略

### 6.1 不建议第一版实现完整 11 节点

原文档建议节点：

- `analyze_input`
- `load_memory`
- `retrieve_lore`
- `update_state_before_generation`
- `narrative_planner`
- `character_reaction`
- `generate_story`
- `quality_check`
- `revise_story`
- `save_memory`
- `return_response`

这套结构完整，但第一版过重。

问题：

- 每个节点如果都调用 LLM，生成延迟会明显上升。
- 节点越多，失败点越多。
- 当前项目仍在单用户 MVP 阶段，不需要立刻引入复杂 Agent 编排。

### 6.2 MVP 推荐节点

第一版建议压缩为 5 个节点：

```text
load_context
  ↓
retrieve_lore
  ↓
plan_narrative
  ↓
generate_story
  ↓
quality_check_and_update_state
```

说明：

- `load_context`：整理 Server 传来的历史、状态和任务参数。
- `retrieve_lore`：从本地世界观文件中检索相关片段。
- `plan_narrative`：生成简短剧情规划，可先不单独调用 LLM。
- `generate_story`：调用 Ollama 生成小说正文。
- `quality_check_and_update_state`：检查输出并生成状态更新。

### 6.3 第二阶段再拆细

当 MVP 稳定后，再拆成：

```text
analyze_input
load_memory
retrieve_lore
narrative_planner
character_reaction
generate_story
quality_check
revise_story
build_state_update
```

---

## 7. Worker 目录结构建议

不采用原文档中的独立 `app/` 目录。

建议在当前 Worker 内扩展：

```text
apps/local-ai-worker/src/dreamweave_worker/
├── agent/
│   ├── __init__.py
│   ├── graph.py
│   ├── nodes.py
│   ├── state.py
│   ├── memory.py
│   ├── lore.py
│   └── prompts.py
├── config.py
├── ollama_client.py
├── prompt.py
├── protocol.py
├── schemas.py
└── worker.py
```

其中：

- `ollama_client.py` 继续作为 LLM Gateway 基础。
- `agent/graph.py` 管 LangGraph 流程。
- `agent/nodes.py` 放各节点实现。
- `agent/state.py` 定义 AgentState / StoryState。
- `agent/memory.py` 处理 recent history / summary。
- `agent/lore.py` 处理 Lore 文件读取和简单检索。
- `agent/prompts.py` 组织叙事 Prompt。

---

## 8. Lore 文件系统

第一版先使用文件，不接向量库。

建议新增：

```text
packages/worlds/default_world/
├── lore.md
├── characters.json
├── style.md
├── rules.md
├── locations.md
└── factions.md
```

用途：

- `lore.md`：世界观背景。
- `characters.json`：角色资料。
- `style.md`：文风要求。
- `rules.md`：世界规则和禁忌。
- `locations.md`：地点设定。
- `factions.md`：势力设定。

第一版检索方式：

```text
user_input + current_scene + active_characters
  ↓
关键词匹配 / 分段匹配
  ↓
返回 3-6 段相关 lore
  ↓
注入 generate_story prompt
```

未来再升级：

```text
Lore 文件
  ↓
切分 chunk
  ↓
embedding
  ↓
Qdrant / Chroma
  ↓
语义检索
```

---

## 9. AI 任务协议扩展

当前 `ai.task.payload.context` 已经有：

```json
{
  "story_title": "黑夜古堡",
  "world_setting": "中世纪奇幻世界",
  "character_setting": "用户是失忆的贵族继承人",
  "recent_messages": []
}
```

建议扩展为：

```json
{
  "story_title": "黑夜古堡",
  "world_id": "default_world",
  "world_setting": "中世纪奇幻世界",
  "character_setting": "用户是失忆的贵族继承人",
  "recent_messages": [],
  "story_state": {
    "current_world": "default_world",
    "current_scene": "",
    "story_stage": "opening",
    "long_summary": "",
    "characters": {},
    "relationships": {},
    "world_flags": {},
    "inventory": [],
    "pending_events": []
  }
}
```

Worker 返回成功时，建议扩展为：

```json
{
  "task_id": "task_xxx",
  "status": "success",
  "worker_id": "local-dev-001",
  "model": "qwen3:14b",
  "content": "小说正文",
  "state_update": {
    "current_scene": "古堡门厅",
    "story_stage": "inciting_incident",
    "world_flags": {
      "castle_gate_opened": true
    },
    "pending_events": [
      "门厅深处传来脚步声"
    ]
  },
  "agent_trace": {
    "lore_count": 3,
    "quality_passed": true
  },
  "duration_ms": 4200
}
```

Server 保存：

- `content` → `messages`
- `state_update` → 合并进 `story_states.state`
- `agent_trace` → `ai_tasks.context` 或后续专门字段

---

## 10. Server 改造点

### 10.1 `/api/story/continue`

当前流程：

```text
读取请求 body
  ↓
创建 task
  ↓
发给 Worker
  ↓
保存 messages / ai_tasks
```

Agent 化后：

```text
读取请求 body
  ↓
确保 user / story / session 存在
  ↓
读取最近 10-20 条 messages
  ↓
读取 story_states.state
  ↓
组装 AgentTask
  ↓
发给 Worker
  ↓
收到 content + state_update
  ↓
保存 user message
  ↓
保存 assistant message
  ↓
更新 ai_tasks
  ↓
合并并保存 story_states.state
  ↓
返回 content 给 H5
```

### 10.2 新增状态接口

建议新增：

```text
GET /api/story/state/:session_id
PUT /api/story/state/:session_id
```

用途：

- 调试当前 StoryState。
- 后续做存档和恢复。
- H5 可展示当前场景、阶段、角色状态。

### 10.3 后置接口

以下可以后续再做：

```text
POST /api/story/start
POST /api/story/save
POST /api/story/load
```

因为当前已有 `stories` 和 `sessions`，不需要第一时间引入新的命名体系。

---

## 11. Prompt 层接入

当前已有：

```text
packages/prompts/story_continue.txt
```

建议保留它作为第一版 `generate_story` 主 Prompt。

新增：

```text
packages/prompts/agent_plan.txt
packages/prompts/agent_quality_check.txt
packages/prompts/state_update.txt
```

第一版也可以不新增多个文件，而是在 Worker 的 `agent/prompts.py` 中组合。

推荐最终 Prompt 输入包括：

- 小说标题
- 世界观设定
- 角色设定
- 当前 StoryState
- 最近剧情
- 长期摘要
- 检索到的 Lore
- 用户本轮输入
- 输出规则

---

## 12. MVP 实施顺序

### 阶段 A：状态持久化

目标：

- 新增 `story_states` 表。
- Server 能读取 / 写入 StoryState。
- `/api/story/continue` 返回后能更新状态。

验收：

- 生成一次剧情后，`story_states.state` 有变化。
- 刷新页面后，下一次生成仍能读取上次状态。

### 阶段 B：Worker AgentState

目标：

- Worker 接收 `story_state`。
- Worker 内部构造 AgentState。
- 不接 LangGraph，先用普通函数串联。

验收：

- Worker 能返回 `content` 和 `state_update`。
- Server 能保存 `state_update`。

### 阶段 C：Lore 文件

目标：

- 新增 `packages/worlds/default_world/`。
- Worker 能读取 lore 文件。
- 根据输入做简单检索。

验收：

- 生成内容能稳定引用世界观设定。
- prompt 中能看到本轮检索片段。

### 阶段 D：最小 LangGraph

目标：

- 引入 LangGraph。
- 把函数串联替换成图流程。
- 节点保持 5 个以内。

验收：

- 原有 WebSocket Worker 链路不变。
- AgentGraph 失败时能返回结构化错误。

### 阶段 E：质量检查和重写

目标：

- 增加 `quality_check`。
- 检查是否出现界面提示、替用户行动、越界输出等问题。
- 失败时最多重写一次。

验收：

- 明显违规输出能被拦截或重写。
- 不造成无限重试。

---

## 13. 不建议现在做的内容

暂时不要做：

- 完整 FastAPI 后端重写。
- 复杂多 Agent 协作。
- 每个节点都调用一次 LLM。
- 一开始就接 Qdrant / Chroma。
- 长期记忆向量化。
- 自动剧情分支树。
- 多用户权限系统。
- 复杂存档系统。

原因：

- 当前第一版核心价值是稳定互动和可保存。
- Agent 能力应增量接入，不能破坏已跑通的线上链路。
- 先把状态、记忆、Lore、生成质量跑稳，再扩展复杂能力。

---

## 14. 推荐近期开发路线

```text
1. 线上持久化最终复核
2. 多故事 / 多会话管理
3. 新增 story_states 表
4. Server 组装 recent_messages + story_state
5. Worker 返回 state_update
6. Lore 文件系统
7. 最小 AgentGraph
8. 质量检查和一次重写
9. Worker 鉴权、HTTPS、备份
10. Redis / BullMQ 队列
11. Qdrant / Chroma 语义检索
12. 多用户与长期记忆
```

如果希望更快看到 Agent 效果，可以把第 3-6 步提前，在多故事 / 多会话之前先做一个单会话 Agent MVP。

推荐折中顺序：

```text
1. 线上持久化复核
2. story_states
3. Worker state_update
4. Lore 文件
5. 多故事 / 多会话
6. LangGraph
```

---

## 15. 第一版 Agent MVP 验收标准

当以下流程成功，就算 Agent MVP 完成：

```text
用户输入一句话
  ↓
Server 读取最近历史和 StoryState
  ↓
Worker 读取 Lore 并执行 Agent 流程
  ↓
Worker 返回小说正文和 state_update
  ↓
Server 保存 messages、ai_tasks、story_states
  ↓
下一轮生成能使用上轮更新后的 StoryState
```

同时满足：

- 不影响当前 H5 使用。
- 不影响 Worker 主动连接 Server。
- 不破坏已有 `/api/story/continue`。
- 数据库能保存消息和状态。
- Worker 出错时返回结构化错误。
- Prompt 仍然遵守“不替用户做决定”的互动小说规则。

---

## 16. 总体判断

互动小说 Agent 引擎应该成为 DreamWeave 的核心能力，但接入方式必须贴合当前项目。

最优路线不是重写，而是分层升级：

```text
Server 继续做产品后端
Worker 升级为 Agent 执行器
PostgreSQL 保存长期状态
Lore 文件先替代向量库
LangGraph 后置为流程编排层
```

这样既能保留已完成的线上闭环，又能逐步获得真正的互动小说 Agent 能力。
