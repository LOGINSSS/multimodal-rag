# 拾光 RAG · multimodal-rag

> LangGraph 编排的**多模态**检索增强生成（RAG）系统：文档 + 图片混合检索，DeepSeek-R1 查询增强，Qwen-VL 生成。
>
> 一句话：把 md/txt/docx/pptx/pdf 和图片丢进去，用自然语言提问，得到带出处、能「看图」的答案。

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/编排-LangGraph-1C3C3C)](https://www.langchain.com/langgraph)
[![Milvus](https://img.shields.io/badge/向量库-Milvus%202.5-00A1EA)](https://milvus.io/)
[![FastAPI](https://img.shields.io/badge/后端-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/前端-React%20%2B%20Vite-61DAFB?logo=react)](https://vite.dev/)

---

## ✨ 特性

- **多模态入库**：文本（md / txt / docx / pptx / pdf）+ 图片（png / jpg / jpeg / bmp / webp）
- **PDF 版面解析**：MinerU `pipeline` 后端（版面 + OCR + 公式 + 表格），退回 PyMuPDF 纯文本兜底
- **图片理解**：RapidOCR 抽文字 + Qwen-VL 生成语义描述，两者都入向量库
- **查询增强**：DeepSeek-R1 改写 query + HyDE 生成假设答案缩小语义鸿沟
- **混合检索**：BM25（稀疏）+ 稠密向量，`RRFRanker` 按名次融合
- **精排 + 生成**：DashScope `gte-rerank-v2` 精排，`qwen-vl-max` 生成（多模态）
- **可观测**：LangFuse（可选，配好 `LANGFUSE_*` 自动开启 trace）
- **一键启动**：双击 `start.bat`，自动拉起 Docker、Milvus、前后端

## 🏗 架构

```
文档(md/txt/docx/pptx/pdf) ── 结构化分片(按标题) ──┐
图片 ── OCR + Qwen-VL 描述(+base64) ──────────────┤
                                                  ├─> embedding(text-embedding-v3) ─> Milvus
                                                  └─> BM25 全文索引 ──────────────> Milvus

提问 ── DeepSeek-R1 改写 ── HyDE ── 混合检索(BM25+语义, RRF) ── 精排(gte-rerank) ── Qwen-VL 生成
```

| 层 | 技术 | 说明 |
|----|------|------|
| 查询增强 | `deepseek-reasoner`（R1） | query 改写 |
| 假设答案 | `deepseek-chat` | HyDE 生成假设性答案辅助检索 |
| Embedding | DashScope `text-embedding-v3` | 1024 维，OpenAI 兼容端点 |
| 向量库 | Milvus 2.5+（Docker） | 内置 BM25 全文 + 稠密向量 |
| 混合检索 | BM25 + 语义，`RRFRanker` | RRF 融合 |
| 精排 | DashScope `gte-rerank-v2` | 重排候选 |
| 生成 | DashScope `qwen-vl-max` | 多模态 |
| 观测 | LangFuse（可选） | 每步 trace |

## 📋 环境要求

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | ≥ 3.13 | 后端（`uv` 管理依赖） |
| [uv](https://docs.astral.sh/uv/) | 最新 | Python 包管理与运行 |
| Node.js | 最新 LTS | 前端（Vite + React） |
| Docker Desktop | 最新 | 运行 Milvus |

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

不下载也能跑，只是 PDF 会退回 PyMuPDF 纯文本抽取（丢表格 / 公式 / 版面）。

### 1. 配置环境变量

```bash
cp .env.example .env
# 填写 DEEPSEEK_API_KEY / DASHSCOPE_API_KEY
```

- `DEEPSEEK_API_KEY`：https://platform.deepseek.com
- `DASHSCOPE_API_KEY`：https://bailian.console.aliyun.com

### 2. 启动 Milvus

```bash
docker compose up -d
```

### 3. 启动后端与前端

```bash
# 后端（终端 1）
uv run rag serve        # 或 uv run uvicorn rag.app:app --reload

# 前端（终端 2）
cd frontend && npm install && npm run dev
```

打开 http://127.0.0.1:13080/docs 查看接口文档。

## 🔧 配置项（.env）

完整变量见 [.env.example](.env.example)，关键项如下：

| 变量 | 必填 | 默认值 | 说明 |
|------|:----:|--------|------|
| `DEEPSEEK_API_KEY` | ✅ | — | DeepSeek（R1 改写 + chat HyDE） |
| `DASHSCOPE_API_KEY` | ✅ | — | DashScope（embedding / 生成 / 精排） |
| `MILVUS_URI` | | `http://localhost:19530` | Milvus gRPC 地址 |
| `MILVUS_COLLECTION` | | `rag_chunks` | 集合名 |
| `DENSE_DIM` | | `1024` | embedding 维度（`text-embedding-v3`） |
| `DEEPSEEK_REASONER_MODEL` | | `deepseek-reasoner` | 查询改写 |
| `DEEPSEEK_CHAT_MODEL` | | `deepseek-chat` | HyDE |
| `DASHSCOPE_EMBEDDING_MODEL` | | `text-embedding-v3` | embedding |
| `QWEN_VL_MODEL` | | `qwen-vl-max` | 生成 |
| `RERANK_MODEL` | | `gte-rerank-v2` | 精排 |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | | 空 | 留空不启用观测；自托管填 `http://localhost:3000` |
| `HF_ENDPOINT` | | `https://hf-mirror.com` | HuggingFace 国内镜像 |
| `MINERU_MODEL_SOURCE` | | `modelscope` | MinerU 模型下载源 |

> 检索参数（`src/rag/config.py` 内常量，非环境变量）：`HYBRID_FETCH_K=20`（每路预取）、`RERANK_TOP_K=5`（精排后保留）、`RRF_K=60`（RRF 平滑常数）。

## 📡 使用

### HTTP 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 + Milvus 连通性 + 条数 |
| POST | `/ingest` | 上传文档/图片入库（multipart 文件） |
| POST | `/ingest/text` | 入库一段文本 `{"text": "...", "source": "..."}` |
| POST | `/ask` | 问答 `{"question": "..."}`，返回 `answer` / `sources` / `rewritten` / `hyde` |

支持的入库文件类型：`.md` `.markdown` `.txt` `.docx` `.pptx` `.pdf` `.png` `.jpg` `.jpeg` `.bmp` `.webp`

### 命令行

```bash
uv run rag ingest docs/xxx.md    # 入库文档
uv run rag ask "你的问题"        # 问答
uv run rag count                 # 查看向量库条数
uv run rag serve                 # 启动服务
```

## 📁 项目结构

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
frontend/            # React + Vite + TS 前端
  src/api.ts         # 后端请求封装（VITE_API_BASE 可覆盖后端地址）
  src/App.tsx        # 聊天界面
```

## TODO / 后续增强

- [ ] **图片 base64 召回**：描述 chunk 的 `metadata.image_base64` 已存，可在生成时把图片回传给 Qwen-VL 看图回答
- [ ] **CLIP 视觉向量**：用 `open-clip-torch` 生成图片视觉向量，与文字向量同空间做图文检索（依赖已在，代码未接）
- [ ] **图片 OCR 走 API**：当前图片用 RapidOCR（首次会下 onnx 模型），可改纯 Qwen-VL 一步到位（OCR + 描述）
- [ ] **Ragas 评测**：ragas 与 langchain 1.x 有依赖冲突，建议单独 venv 或用 DeepEval
- [ ] **精排本地化**：`llm.rerank` 换本地 Qwen3-Reranker / bge-reranker 省 API 调用

## License

本仓库为**私有项目**，未开源。仅供个人学习与使用，请勿分发。
