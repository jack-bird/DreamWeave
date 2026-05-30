# DreamWeave 本地 Worker 向量库安装流程

更新日期：2026-05-30

## 1. 安装位置说明

当前默认架构：

```text
云服务器：Node.js Server + PostgreSQL + Nginx + PM2
本地电脑：Python local-ai-worker + Ollama + Chroma / sentence-transformers
```

向量库依赖安装在实际运行 Worker 的机器上。当前 Worker 在本地 Windows 电脑运行，因此 Chroma 和 sentence-transformers 安装在本地 Python 虚拟环境中。

不要在云服务器上安装这些 Python 向量库依赖，除非以后把 Worker 也部署到云服务器。

## 2. 需要的依赖

`apps/local-ai-worker/requirements.txt` 当前包含：

```text
httpx>=0.28.1
websockets>=15.0
chromadb>=0.4.0
sentence-transformers>=2.2.0
```

依赖用途：

- `httpx`：Worker 调用 Ollama HTTP API。
- `websockets`：Worker 通过 WebSocket 主动连接线上 Server。
- `chromadb`：本地向量库，保存 Lore embedding 索引。
- `sentence-transformers`：生成文本 embedding。

## 3. 激活本地虚拟环境

在 Windows PowerShell 执行：

```powershell
cd E:\ai_home\AI_Projects\DreamWeave
. E:\ai_home\AI_Projects\llm_env\Scripts\Activate.ps1
```

确认 Python 来自虚拟环境：

```powershell
python -c "import sys; print(sys.executable)"
```

预期路径包含：

```text
E:\ai_home\AI_Projects\llm_env
```

## 4. 推荐安装命令

如果直接安装 `requirements.txt` 卡在 Chroma 版本回溯，可以先安装明确版本：

```powershell
python -m pip install "setuptools<82" wheel
python -m pip install --only-binary=:all: "chromadb==1.5.9"
python -m pip install "sentence-transformers==2.7.0"
```

然后补装完整 requirements：

```powershell
python -m pip install -r .\apps\local-ai-worker\requirements.txt
```

如果下载很慢，可以加超时：

```powershell
python -m pip install --timeout 120 --only-binary=:all: "chromadb==1.5.9"
python -m pip install --timeout 120 "sentence-transformers==2.7.0"
```

如果网络仍慢，可以临时使用清华源：

```powershell
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 120 --only-binary=:all: "chromadb==1.5.9"
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 120 "sentence-transformers==2.7.0"
```

## 5. 验证安装

```powershell
python -c "import chromadb; import sentence_transformers; print('RAG dependencies OK')"
```

预期输出：

```text
RAG dependencies OK
```

检查 Worker 健康状态：

```powershell
python .\apps\local-ai-worker\main.py health
```

## 6. 启动本地 Worker

```powershell
.\start-online-worker.bat
```

`start-online-worker.bat` 默认会设置：

```bat
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
```

这会让 `sentence-transformers` 优先使用本地 Hugging Face 缓存，避免 Worker 每次启动或检索时访问外网。前提是 embedding 模型已经至少成功下载过一次。

启动后，在服务器确认 Worker 已连接：

```bash
curl http://127.0.0.1:3000/health
```

预期：

```text
worker_count = 1
```

## 7. Chroma 数据目录

本地启动脚本会从项目根目录启动 Worker，因此 Chroma 默认数据目录是：

```text
E:\ai_home\AI_Projects\DreamWeave\chroma_db
```

这个目录保存向量索引。PostgreSQL 仍然是主数据库，Lore 原文保存在服务器 `lore_entries` 表中。

如果 `chroma_db` 丢失，理论上可以从 PostgreSQL 的 Lore 原文重新生成索引。

## 8. 常见问题

### 8.1 chroma-hnswlib 编译失败

错误示例：

```text
error: Microsoft Visual C++ 14.0 or greater is required
Failed building wheel for chroma-hnswlib
```

原因：pip 没有找到匹配的 Windows 预编译包，尝试本地编译 C++ 扩展。

优先解决方式：安装新版 Chroma wheel，避免本地编译。

```powershell
python -m pip install --only-binary=:all: "chromadb==1.5.9"
```

不要优先安装 Visual Studio Build Tools，除非新版 Chroma wheel 也无法安装。

### 8.2 setuptools 与 torch 冲突

错误示例：

```text
torch 2.11.0+cu128 requires setuptools<82
```

解决：

```powershell
python -m pip install "setuptools<82" wheel
```

### 8.3 pip 版本回溯很慢

错误表现：

```text
pip is looking at multiple versions of chromadb
```

解决：先安装明确版本。

```powershell
python -m pip install --only-binary=:all: "chromadb==1.5.9"
python -m pip install "sentence-transformers==2.7.0"
```

### 8.4 Worker 能启动但 RAG 不生效

确认依赖：

```powershell
python -c "import chromadb; import sentence_transformers; print('RAG dependencies OK')"
```

确认 Worker 已连接服务器：

```bash
curl http://127.0.0.1:3000/health
```

确认新增 Lore 后本地是否生成：

```text
E:\ai_home\AI_Projects\DreamWeave\chroma_db
```
