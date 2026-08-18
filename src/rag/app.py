"""FastAPI 接口：健康检查 / 文档入库 / 问答。

启动： uv run uvicorn rag.app:app --reload
之后访问 http://127.0.0.1:13080/docs 查看交互式文档。
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config, ingest, store
from .graph import run_rag
from .observability import get_langfuse_callback

app = FastAPI(title="RAG 后端", version="0.1.0")

# 允许前端 dev server 跨域访问（Vite 端口 18080）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:18080",
        "http://127.0.0.1:18080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- 请求/响应模型 ----------

class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    sources: list[dict]
    rewritten: str = ""
    hyde: str = ""


class IngestTextRequest(BaseModel):
    text: str
    source: str = "inline"


class IngestResponse(BaseModel):
    inserted: int


# ---------- 路由 ----------

@app.get("/health")
def health() -> dict:
    """检查服务与 Milvus 连通性。"""
    try:
        store.ensure_collection()
        milvus_ok = True
        rows = store.count()
    except Exception as e:  # noqa: BLE001
        milvus_ok = False
        rows = 0
        err = str(e)
    return {
        "status": "ok" if milvus_ok else "degraded",
        "milvus_ok": milvus_ok,
        "rows": rows,
        "error": err if not milvus_ok else "",
    }


@app.post("/ingest", response_model=IngestResponse)
def ingest_upload(file: UploadFile = File(...)) -> IngestResponse:
    """上传文档（md/txt/docx/pptx/pdf/图片）入库。

    用同步 def（FastAPI 会自动放到线程池），避免 MinerU 等长任务
    阻塞事件循环导致整个服务卡死。
    """
    suffix = Path(file.filename or "").suffix.lower()
    allowed = {".md", ".markdown", ".txt", ".docx", ".pptx", ".pdf",
               ".png", ".jpg", ".jpeg", ".bmp", ".webp"}
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {suffix}")

    tmp_path = config.DATA_DIR / (file.filename or "upload")
    with tmp_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        n = ingest.ingest_file(tmp_path)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"入库失败: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)
    return IngestResponse(inserted=n)


@app.post("/ingest/text", response_model=IngestResponse)
def ingest_text(req: IngestTextRequest) -> IngestResponse:
    """直接入库一段文本。"""
    n = ingest.ingest_text(req.text, source=req.source)
    return IngestResponse(inserted=n)


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    """RAG 问答：改写 → HyDE → 检索 → 精排 → 生成。"""
    callbacks = get_langfuse_callback()
    try:
        result = run_rag(req.question, callbacks=callbacks)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"问答失败: {e}")
    return AskResponse(
        answer=result.get("answer", ""),
        sources=result.get("sources", []),
        rewritten=result.get("rewritten", ""),
        hyde=result.get("hyde", ""),
    )
