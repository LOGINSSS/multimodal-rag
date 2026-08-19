"""FastAPI 接口：健康检查 / 文档入库 / 问答。

启动： uv run uvicorn rag.app:app --reload
之后访问 http://127.0.0.1:13080/docs 查看交互式文档。
"""
from __future__ import annotations

import logging
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import config, files, ingest, store
from .graph import run_rag
from .observability import get_langfuse_callback

logger = logging.getLogger(__name__)

app = FastAPI(title="RAG 后端", version="0.1.0")

# ---------- 入库异步任务池 ----------
# /ingest 只负责收文件并提交任务（秒回 task_id），后台线程池并发解析；
# 同名文件冲突时任务进入 awaiting_decision，等前端弹窗决策后继续。
# 前端轮询 /task/{id} 获取进度，避免长任务（MinerU 解析）阻塞请求。

_TASKS: dict[str, dict] = {}
_TASKS_LOCK = threading.Lock()
_EXECUTOR = ThreadPoolExecutor(max_workers=3)  # MinerU 较重，限制并发数


def _doc_type(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".") or "file"


def _create_ingest_task(tmp_path: Path, filename: str) -> str:
    """提交入库任务。同名文件已存在时暂存文件、等待用户决策（覆盖/加后缀/取消）。"""
    task_id = uuid.uuid4().hex[:12]
    doc_id = files.new_doc_id()
    conflict = files.find_by_filename(filename) is not None
    with _TASKS_LOCK:
        _TASKS[task_id] = {
            "task_id": task_id,
            "status": "awaiting_decision" if conflict else "pending",
            "source": filename,
            "inserted": 0,
            "error": "",
            "progress": 0,
            "doc_id": doc_id,
            "conflict": conflict,
            "created_at": time.time(),
        }
    if conflict:
        staging = files.staging_path(doc_id, filename)
        staging.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.replace(staging)
        return task_id
    final = files.final_path(doc_id, filename)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.replace(final)
    files.add(files.make_entry(doc_id, filename, _doc_type(filename), status="ingesting"))
    _EXECUTOR.submit(_run_ingest, task_id)
    return task_id


def _run_ingest(task_id: str) -> None:
    """后台执行入库（文件已就位于 final_path）。"""
    with _TASKS_LOCK:
        t = _TASKS[task_id]
        doc_id, filename = t["doc_id"], t["source"]
        t["status"] = "running"
        t["progress"] = 1  # 开始解析

    def _cb(fraction: float) -> None:
        with _TASKS_LOCK:
            t["progress"] = max(1, min(100, int(fraction * 100)))

    try:
        n = ingest.ingest_file(
            files.final_path(doc_id, filename), source=filename, doc_id=doc_id, progress_cb=_cb
        )
        with _TASKS_LOCK:
            t.update({"status": "done", "inserted": n, "progress": 100})
        files.update(doc_id, chunk_count=n, status="done")
    except Exception as e:  # noqa: BLE001
        with _TASKS_LOCK:
            t.update({"status": "failed", "error": str(e)})
        files.update(doc_id, status="failed")


def _run_decision(task_id: str, action: str) -> None:
    """处理同名冲突决策：overwrite 覆盖 / rename 加后缀另存 / cancel 取消。"""
    with _TASKS_LOCK:
        t = _TASKS[task_id]
        doc_id, filename = t["doc_id"], t["source"]
    staging = files.staging_path(doc_id, filename)

    if action == "cancel":
        staging.unlink(missing_ok=True)
        with _TASKS_LOCK:
            t.update({"status": "cancelled"})
        return

    if action == "overwrite":
        old = files.find_by_filename(filename)
        if old:
            try:
                store.delete_by_doc_id(old["doc_id"])
            except Exception:  # noqa: BLE001
                pass
            files.final_path(old["doc_id"], filename).unlink(missing_ok=True)
            files.pop(old["doc_id"])
        final = files.final_path(doc_id, filename)
        staging.replace(final)
        files.add(files.make_entry(doc_id, filename, _doc_type(filename), status="ingesting"))
        _run_ingest(task_id)
        return

    # rename：加后缀另存为新文件
    new_name = files.next_rename(filename)
    with _TASKS_LOCK:
        t["source"] = new_name
    final = files.final_path(doc_id, new_name)
    staging.replace(final)
    files.add(files.make_entry(doc_id, new_name, _doc_type(new_name), status="ingesting"))
    _run_ingest(task_id)

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
    conflict: bool = False
    progress: int = 0


class TaskDecisionRequest(BaseModel):
    action: str  # overwrite | rename | cancel


# ---------- 路由 ----------

def _reconcile_stuck_files() -> None:
    """启动时校正遗留的 ingesting 状态（进程重启会丢失内存任务）。

    按 Milvus 实际条数修正：有 chunk → done + 校正 chunk_count；无 → failed。
    """
    for f in files.all_files():
        if f.get("status") != "ingesting":
            continue
        try:
            n = store.count_by_doc_id(f["doc_id"])
        except Exception:  # noqa: BLE001
            n = 0
        if n > 0:
            logger.info("校正孤儿任务 %s -> done（%s 条）", f["filename"], n)
            files.update(f["doc_id"], chunk_count=n, status="done")
        else:
            logger.warning("校正孤儿任务 %s -> failed（无数据）", f["filename"])
            files.update(f["doc_id"], status="failed")


# 启动时校正（放 app 构建后，避免循环导入）
_reconcile_stuck_files()


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
    task_id = _create_ingest_task(tmp_path, file.filename or "upload")
    return IngestTaskResponse(task_id=task_id)


@app.get("/task/{task_id}", response_model=TaskStatusResponse)
def task_status(task_id: str) -> TaskStatusResponse:
    """查询入库任务状态（pending/awaiting_decision/running/done/failed/cancelled）。"""
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
        conflict=t["conflict"],
        progress=t.get("progress", 0),
    )


@app.post("/task/{task_id}/decision", response_model=TaskStatusResponse)
def task_decision(task_id: str, req: TaskDecisionRequest) -> TaskStatusResponse:
    """同名冲突决策：overwrite 覆盖 / rename 加后缀另存 / cancel 取消。"""
    if req.action not in ("overwrite", "rename", "cancel"):
        raise HTTPException(status_code=400, detail="action 必须是 overwrite/rename/cancel")
    with _TASKS_LOCK:
        t = _TASKS.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t["status"] != "awaiting_decision":
        raise HTTPException(status_code=400, detail="任务不在待决策状态")
    with _TASKS_LOCK:
        t["status"] = "running"  # 先占位，避免重复决策
    _EXECUTOR.submit(_run_decision, task_id, req.action)
    return TaskStatusResponse(
        task_id=t["task_id"],
        status=t["status"],
        source=t["source"],
        inserted=t["inserted"],
        error=t["error"],
        conflict=t["conflict"],
        progress=t.get("progress", 0),
    )


# ---------- 知识库文件管理 ----------

@app.get("/files")
def list_files() -> dict:
    """知识库文件列表（名称/类型/chunk数/时间/状态）。"""
    return {"files": files.all_files()}


@app.get("/files/{doc_id}/download")
def download_file(doc_id: str) -> FileResponse:
    """下载知识库中的原始文件。"""
    entry = files.get(doc_id)
    if not entry:
        raise HTTPException(status_code=404, detail="文件不存在")
    p = files.final_path(doc_id, entry["filename"])
    if not p.exists():
        raise HTTPException(status_code=404, detail="原始文件不存在")
    return FileResponse(p, filename=entry["filename"])


@app.delete("/files/{doc_id}")
def delete_file(doc_id: str) -> dict:
    """删除文件：清空其全部向量 chunks + 删除原始文件 + 移除注册记录。"""
    entry = files.get(doc_id)
    if not entry:
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        store.delete_by_doc_id(doc_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"删除向量失败: {e}")
    files.final_path(doc_id, entry["filename"]).unlink(missing_ok=True)
    files.pop(doc_id)
    return {"ok": True, "deleted": entry["filename"]}


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
