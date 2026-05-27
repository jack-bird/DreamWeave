请帮我把当前项目升级为“互动小说 Agent 引擎”。

项目目标：
用户在手机端输入一句话，系统根据当前小说世界观、角色设定、历史剧情、用户意图和故事状态，自动生成下一段小说内容，并更新故事状态。

核心架构要求：

1. StoryState 故事状态系统
需要建立统一状态对象，用来记录：
- current_world：当前小说/世界
- current_scene：当前场景
- story_stage：剧情阶段
- user_input：用户本轮输入
- recent_history：最近对话/剧情
- long_summary：长期剧情摘要
- characters：角色状态
- relationships：角色关系
- world_flags：世界事件标记
- inventory：物品/能力/资源
- pending_events：待触发事件
- retrieved_lore：本轮检索到的世界观资料
- final_response：最终返回给用户的小说文本

2. LangGraph 流程控制层
使用 LangGraph 作为 Agent 工作流引擎。
LangGraph 适合 long-running、stateful workflow / agent，用来管理状态、记忆、分支和多节点流程。

需要设计这些节点：
- analyze_input：分析用户输入意图
- load_memory：读取历史剧情和长期记忆
- retrieve_lore：根据当前场景检索世界观设定
- update_state_before_generation：生成前更新状态
- narrative_planner：规划下一段剧情方向
- character_reaction：生成角色反应逻辑
- generate_story：调用 Ollama 生成小说正文
- quality_check：检查是否符合世界观、角色设定和文风
- revise_story：如果质量不合格则重写
- save_memory：保存本轮剧情和状态变化
- return_response：返回最终小说文本

3. Khora/叙事逻辑层
先不要做成复杂框架，先实现为 narrative prompt 模板系统。
它负责：
- 小说文风
- 角色语气
- 情绪陪伴
- 剧情节奏
- 用户沉浸感
- NPC反应
- 伏笔和转折

4. Memory 记忆系统
需要分两类：
- 短期记忆：最近 10-20 轮对话
- 长期记忆：剧情摘要、角色关系、关键事件、用户偏好

5. Lore / RAG 世界观知识库
每本小说有独立世界观文件：
- lore.md
- characters.json
- style.md
- rules.md
- locations.md
- factions.md

使用向量数据库保存世界观内容，例如 Chroma 或 Qdrant。
每次生成前，根据 user_input + current_scene + characters 检索相关设定。

6. LLM Gateway
封装 Ollama 调用，不要在业务代码里直接调用 Ollama。
需要支持：
- model_name
- temperature
- max_tokens
- system_prompt
- user_prompt
- stream 输出
- timeout
- error retry

7. 数据库
建议：
- PostgreSQL：保存用户、小说、存档、StoryState
- Qdrant/Chroma：保存世界观、长期记忆向量

8. API 设计
需要提供：
- POST /story/start：开始一本小说
- POST /story/continue：用户输入一句，返回下一段剧情
- GET /story/state/{session_id}：查看当前故事状态
- POST /story/save：保存存档
- POST /story/load：读取存档

9. 最小可行版本
请先实现 MVP，不要一次做太复杂。

MVP 只需要：
- StoryState
- LangGraph 基础流程
- Ollama 调用
- 简单 Memory
- 简单 Lore 文件读取
- /story/continue 接口

10. 目录结构建议

app/
  main.py
  api/
    story.py
  core/
    config.py
    llm_gateway.py
  agents/
    graph.py
    nodes.py
    prompts.py
  story/
    state.py
    memory.py
    lore.py
    rules.py
  data/
    worlds/
      default_world/
        lore.md
        characters.json
        style.md
        rules.md
  db/
    models.py
    session.py

请按照这个架构帮我生成第一版代码。
要求代码清晰、可扩展、先能跑通。
优先使用 Python + FastAPI + LangGraph + Ollama。