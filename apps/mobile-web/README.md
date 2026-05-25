# DreamWeave Mobile Web

第一版 H5 页面，用于跑通手机端互动小说输入和 AI 回复展示。

当前页面由 `apps/server` 托管，不需要单独启动前端 dev server。

## 启动顺序

启动 server：

```powershell
cd E:\ai_home\AI_Projects\DreamWeave\apps\server
npm run start
```

启动 Worker：

```powershell
. E:\ai_home\AI_Projects\llm_env\Scripts\Activate.ps1
cd E:\ai_home\AI_Projects\DreamWeave
python .\apps\local-ai-worker\main.py connect --server ws://127.0.0.1:3000/ws/worker
```

打开页面：

```text
http://127.0.0.1:3000/
```

## 当前能力

- 查看 Worker 连接状态。
- 自动读取 Worker 可用模型。
- 选择模型。
- 编辑故事标题、世界观和角色设定。
- 输入用户行动。
- 调用 `POST /api/story/continue`。
- 显示用户输入、AI 回复和错误状态。
- 使用 localStorage 暂存本地历史记录。
