# DreamWeave Local AI Worker

本地 AI Worker 负责接收小说生成任务、组装 Prompt、调用本机 Ollama，并把结果返回给服务器。

当前阶段先支持本地命令行验证 Ollama 调用链路，WebSocket 连接模式已预留，等服务端完成后再联调。

## 环境

推荐使用已有虚拟环境：

```powershell
. E:\ai_home\AI_Projects\llm_env\Scripts\Activate.ps1
```

检查 Ollama：

```powershell
ollama list
```

当前默认模型：

```text
qwen3:14b
```

可以通过环境变量切换模型：

```powershell
$env:DREAMWEAVE_OLLAMA_MODEL = "llama33-novel:latest"
```

可以通过环境变量限制单次生成长度：

```powershell
$env:DREAMWEAVE_NUM_PREDICT = "220"
```

常用生成参数：

```powershell
$env:DREAMWEAVE_TEMPERATURE = "0.66"
$env:DREAMWEAVE_TOP_P = "0.85"
$env:DREAMWEAVE_REPEAT_PENALTY = "1.08"
```

任务级超时和 Ollama 请求超时：

```powershell
$env:DREAMWEAVE_TASK_TIMEOUT = "180"
$env:DREAMWEAVE_REQUEST_TIMEOUT = "180"
```

WebSocket 连接配置：

```powershell
$env:DREAMWEAVE_WORKER_ID = "local-dev-001"
$env:DREAMWEAVE_WORKER_NAME = "DreamWeave Local Worker"
$env:DREAMWEAVE_SERVER_WS = "ws://127.0.0.1:3000/ws/worker"
$env:DREAMWEAVE_HEARTBEAT_INTERVAL = "15"
$env:DREAMWEAVE_RECONNECT_MIN_DELAY = "3"
$env:DREAMWEAVE_RECONNECT_MAX_DELAY = "30"
```

如果使用带 thinking 能力的模型，例如 `qwen3:14b`，默认会关闭思考输出：

```powershell
$env:DREAMWEAVE_THINK = "false"
```

## 本地生成测试

在项目根目录执行：

```powershell
python .\apps\local-ai-worker\main.py health
python .\apps\local-ai-worker\main.py local "我推开了古堡的大门。"
```

如需输出结构化 JSON：

```powershell
python .\apps\local-ai-worker\main.py local "我走进森林深处。" --json
```

单次任务也可以覆盖模型和生成参数：

```powershell
python .\apps\local-ai-worker\main.py local "我推开了古堡的大门。" --model qwen3:14b --num-predict 220 --json
```

也可以覆盖本次任务的处理超时：

```powershell
python .\apps\local-ai-worker\main.py local "我推开了古堡的大门。" --task-timeout 60 --json
```

## WebSocket Worker 预留命令

安装依赖后可连接服务器。当前不需要线上服务器，可以先连接本地测试服务器：

```powershell
python -m pip install -r .\apps\local-ai-worker\requirements.txt
python .\apps\local-ai-worker\main.py connect --server ws://127.0.0.1:3000/ws/worker
```

连接模式会按 `docs/Worker通信协议.md` 执行：

- 连接成功后发送 `worker.register`
- 等待 `worker.registered`
- 定时发送 `worker.heartbeat`
- 接收 `ai.task`
- 返回 `ai.result` 或 `ai.task_error`
- 收到 `ai.task_cancel` 时取消正在运行的任务
- 断线后自动重连

服务端尚未启动时，这个命令会连接失败并自动重试，属于预期。
