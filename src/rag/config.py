"""全局配置：从项目根目录的 .env 读取环境变量。"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录：src/rag/config.py -> 上三级到 RAG/
ROOT = Path(__file__).resolve().parents[2]

# 加载 ROOT/.env（不存在则忽略，走系统环境变量）
load_dotenv(ROOT / ".env")

# ---------- 目录 ----------
DATA_DIR = ROOT / "data"          # 上传/临时文档落盘目录
DATA_DIR.mkdir(exist_ok=True)

# ---------- API key ----------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")

# ---------- Milvus ----------
MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "rag_chunks")
DENSE_DIM = int(os.getenv("DENSE_DIM", "1024"))

# ---------- 模型名 ----------
DEEPSEEK_REASONER_MODEL = os.getenv("DEEPSEEK_REASONER_MODEL", "deepseek-reasoner")
DEEPSEEK_CHAT_MODEL = os.getenv("DEEPSEEK_CHAT_MODEL", "deepseek-chat")
DASHSCOPE_EMBEDDING_MODEL = os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3")
QWEN_VL_MODEL = os.getenv("QWEN_VL_MODEL", "qwen-vl-max")
RERANK_MODEL = os.getenv("RERANK_MODEL", "gte-rerank-v2")

# DashScope 的 OpenAI 兼容端点（embedding + Qwen-VL 都走这里）
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# ---------- 可选：LangFuse ----------
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "")

# ---------- 可选：HuggingFace 国内镜像 ----------
HF_ENDPOINT = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
if HF_ENDPOINT:
    os.environ.setdefault("HF_ENDPOINT", HF_ENDPOINT)

# ---------- MinerU（PDF 版面解析） ----------
MINERU_MODEL_SOURCE = os.getenv("MINERU_MODEL_SOURCE", "modelscope")
MINERU_BACKEND = os.getenv("MINERU_BACKEND", "pipeline")   # pipeline / vlm-* / hybrid-*
MINERU_METHOD = os.getenv("MINERU_METHOD", "auto")         # auto / txt / ocr
MINERU_LANG = os.getenv("MINERU_LANG", "ch")               # 文档语言（提高 OCR 准确率）
MINERU_TIMEOUT = int(os.getenv("MINERU_TIMEOUT", "600"))   # 单文件解析超时（秒）
os.environ.setdefault("MINERU_MODEL_SOURCE", MINERU_MODEL_SOURCE)

# ---------- 检索参数 ----------
HYBRID_FETCH_K = 20          # 每一路检索预取的候选数
RERANK_TOP_K = 5             # 精排后保留的条数
RRF_K = 60                   # RRF 平滑常数
