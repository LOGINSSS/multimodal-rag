"""FastAPI 接口：健康检查 / 文档入库 / 问答。

启动： uv run uvicorn rag.app:app --reload
之后访问 http://127.0.0.1:13080/docs 查看交互式文档。
"""
from __future__ import annotations

import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config, ingest, store
from .graph import run_rag
from .observability import get_langfuse_callback

app = FastAPI(title="RAG 后端", version="0.1.0")

# ---------- 入库异步任务池 ----------
# /ingest 只负责收文件并提交任务（秒回 task_id），后台线程池并发解析；
# 前端轮询 /task/{id} 获取进度，避免长任务（MinerU 解析）阻塞请求。

_TASKS: dict[str, dict] = {}
_TASKS_LOCK = threading.Lock()
_EXECUTOR = ThreadPoolExecutor(max_workers=3)  # MinerU 较重，限制并发数


def _submit_ingest(tmp_path: Path, filename: str) -> str:
    task_id = uuid.uuid4().hex[:12]
    with _TASKS_LOCK:
        _TASKS[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "source": filename,
            "inserted": 0,
            "error": "",
            "created_at": time.time(),
        }
    _EXECUTOR.submit(_run_ingest, task_id, tmp_path)
    return task_id


def _run_ingest(task_id: str, tmp_path: Path) -> None:
    try:
        with _TASKS_LOCK:
            _TASKS[task_id]["status"] = "running"
        n = ingest.ingest_file(tmp_path)
        with _TASKS_LOCK:
            _TASKS[task_id].update({"status": "done", "inserted": n})
    except Exception as e:  # noqa: BLE001
        with _TASKS_LOCK:
            _TASKS[task_id].update({"status": "failed", "error": str(e)})
    finally:
        tmp_path.unlink(missing_ok=True)

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


class IngestTaskResponse(BaseModel):
    task_id: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    source: str
    inserted: int = 0
    error: str = ""


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


@app.post("/ingest", response_model=IngestTaskResponse)
def ingest_upload(file: UploadFile = File(...)) -> IngestTaskResponse:
    """上传文档（md/txt/docx/pptx/pdf/图片）入库（异步）。

    秒回 task_id，后台线程池解析入库；前端轮询 /task/{id} 查进度。
    """
    suffix = Path(file.filename or "").suffix.lower()
    allowed = {".md", ".markdown", ".txt", ".docx", ".pptx", ".pdf",
               ".png", ".jpg", ".jpeg", ".bmp", ".webp"}
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {suffix}")

    tmp_path = config.DATA_DIR / (file.filename or "upload")
    with tmp_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    task_id = _submit_ingest(tmp_path, file.filename or "upload")
    return IngestTaskResponse(task_id=task_id)


@app.get("/task/{task_id}", response_model=TaskStatusResponse)
def task_status(task_id: str) -> TaskStatusResponse:
    """查询入库任务状态（pending/running/done/failed）。"""
    with _TASKS_LOCK:
        t = _TASKS.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskStatusResponse(
        task_id=t["task_id"],
        status=t["status"],
        source=t["source"],
        inserted=t["inserted"],
        error=t["error"],
    )


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
