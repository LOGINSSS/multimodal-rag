# RAG

LangGraph 编排的多模态检索增强生成（RAG）系统。

## 架构

```
文档(md/txt/docx/pptx/pdf) ── 结构化分片(按标题) ──┐
图片 ── OCR + Qwen-VL 描述(+base64) ──────────────┤
                                                  ├─> embedding(text-embedding-v3) ─> Milvus
                                                  └─> BM25 全文索引 ──────────────> Milvus

提问 ── DeepSeek-R1 改写 ── HyDE ── 混合检索(BM25+语义, RRF) ── 精排(gte-rerank) ── Qwen-VL 生成
```

- **查询改写**：`deepseek-reasoner`（R1）
- **HyDE**：`deepseek-chat` 生成假设性答案辅助检索
- **Embedding**：DashScope `text-embedding-v3`（1024 维，OpenAI 兼容端点）
- **向量库**：Milvus 2.5+（Docker Compose），内置 BM25 全文检索 + 稠密向量
- **混合检索**：BM25 + 语义，`RRFRanker` 融合
- **精排**：DashScope `gte-rerank-v2`
- **生成**：DashScope `qwen-vl-max`（多模态）
- **观测**：LangFuse（可选，配置 `LANGFUSE_*` 后自动开启）

## 快速开始

### 0. 一键启动（推荐）

双击项目根目录的 `start.bat`，它会自动：

1. 检查 `uv` / `node` / `.env`（缺 `.env` 会自动从 `.env.example` 复制）
2. 检查并启动 Docker Desktop（如未运行）
3. `docker compose up -d` 起 Milvus，并等待端口 19530 就绪
4. 检查后端 13080 / 前端 18080 是否被占用，占用则先结束旧进程
5. 弹出两个终端窗口分别启动后端与前端

- 后端 API：http://127.0.0.1:13080/docs
- 前端：http://localhost:18080

### 0.5 一次性：下载 MinerU 模型（PDF 版面解析用）

PDF 解析走 MinerU `pipeline` 后端（版面解析 + OCR + 公式 + 表格），模型从 ModelScope 下载（国内直连，无需代理），约 1~3 GB，只需执行一次：

```bash
uv run mineru-models-download -s modelscope -m pipeline
```

不下载也能跑，只是 PDF 会退回 PyMuPDF 纯文本抽取（丢表格/公式/版面）。

### 1. 配置环境变量

```bash
cp .env.example .env
# 填写 DEEPSEEK_API_KEY / DASHSCOPE_API_KEY
```

### 2. 启动 Milvus

```bash
docker compose up -d
```

### 3. 启动后端

```bash
uv run rag serve        # 或 uv run uvicorn rag.app:app --reload
```

打开 http://127.0.0.1:13080/docs 查看接口文档。

## 使用

### HTTP 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/health` | 健康检查 + Milvus 连通性 + 条数 |
| POST | `/ingest` | 上传文档/图片入库（multipart 文件） |
| POST | `/ingest/text` | 入库一段文本 `{"text": "...", "source": "..."}` |
| POST | `/ask` | 问答 `{"question": "..."}` |

### 命令行

```bash
uv run rag ingest docs/xxx.md    # 入库文档
uv run rag ask "你的问题"        # 问答
uv run rag count                 # 查看向量库条数
uv run rag serve                 # 启动服务
```

## 项目结构

```
src/rag/
  config.py          # 配置（读 .env）
  llm.py             # DeepSeek / DashScope(embedding/Qwen-VL/rerank) 客户端
  store.py           # Milvus 建集合 + BM25/语义混合检索(RRF)
  ingest.py          # 文档解析 + 结构化分片 + embedding + 入库
  graph.py           # LangGraph 图：改写→HyDE→检索→精排→生成
  observability.py   # LangFuse 回调（可选）
  app.py             # FastAPI 接口
  cli.py             # 命令行
```

## TODO / 后续增强

- [ ] **图片 base64 召回**：描述 chunk 的 `metadata.image_base64` 已存，可在生成时把图片回传给 Qwen-VL 看图回答
- [ ] **CLIP 视觉向量**：用 `open-clip-torch` 生成图片视觉向量，与文字向量同空间做图文检索（依赖已在，代码未接）
- [ ] **图片 OCR 走 API**：当前图片用 RapidOCR（首次会下 onnx 模型），可改纯 Qwen-VL 一步到位（OCR + 描述）
- [ ] **Ragas 评测**：ragas 与 langchain 1.x 有依赖冲突（见记忆），建议单独 venv 或用 DeepEval
- [ ] **精排本地化**：`llm.rerank` 换本地 Qwen3-Reranker / bge-reranker 省 API 调用
