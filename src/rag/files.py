"""知识库文件注册表：管理原始文件存储 + 文件元数据索引。

- 原始文件存 `data/files/{doc_id}{ext}`
- 注册表存 `data/files_index.json`（doc_id -> 文件信息），进程内缓存 + 落盘
- 文件名只作展示；文件身份是 doc_id，同名冲突由前端弹窗让用户决定
  （覆盖 / 加后缀另存 / 取消）。
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from . import config

FILES_DIR = config.DATA_DIR / "files"
_INDEX_PATH = config.DATA_DIR / "files_index.json"
_LOCK = threading.Lock()

FILES_DIR.mkdir(parents=True, exist_ok=True)


def _load() -> Dict[str, dict]:
    if _INDEX_PATH.exists():
        try:
            return json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 —— 索引损坏时从空开始
            return {}
    return {}


_index: Dict[str, dict] = _load()


def _save() -> None:
    _INDEX_PATH.write_text(
        json.dumps(_index, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def new_doc_id() -> str:
    return uuid.uuid4().hex[:12]


def final_path(doc_id: str, filename: str) -> Path:
    """最终存储路径（正式文件名）。"""
    return FILES_DIR / f"{doc_id}{Path(filename).suffix.lower()}"


def staging_path(doc_id: str, filename: str) -> Path:
    """暂存路径（等待决策/待入库）。"""
    return FILES_DIR / f".staging_{doc_id}{Path(filename).suffix.lower()}"


def all_files() -> List[dict]:
    with _LOCK:
        return sorted(
            _index.values(), key=lambda f: f.get("uploaded_at", 0), reverse=True
        )


def get(doc_id: str) -> Optional[dict]:
    with _LOCK:
        return _index.get(doc_id)


def find_by_filename(filename: str) -> Optional[dict]:
    with _LOCK:
        for f in _index.values():
            if f.get("filename") == filename:
                return f
    return None


def add(entry: dict) -> None:
    with _LOCK:
        _index[entry["doc_id"]] = entry
        _save()


def update(doc_id: str, **fields) -> None:
    with _LOCK:
        entry = _index.get(doc_id)
        if entry:
            entry.update(fields)
            _save()


def pop(doc_id: str) -> Optional[dict]:
    with _LOCK:
        entry = _index.pop(doc_id, None)
        if entry:
            _save()
        return entry


def make_entry(doc_id: str, filename: str, doc_type: str, status: str = "ingesting") -> dict:
    return {
        "doc_id": doc_id,
        "filename": filename,
        "doc_type": doc_type,
        "chunk_count": 0,
        "status": status,
        "uploaded_at": time.time(),
    }


def next_rename(filename: str) -> str:
    """为同名文件找下一个可用序号名：'x.pdf' -> 'x (1).pdf' -> 'x (2).pdf'…"""
    stem = Path(filename).stem
    ext = Path(filename).suffix
    with _LOCK:
        names = {f.get("filename") for f in _index.values()}
    n = 1
    while f"{stem} ({n}){ext}" in names:
        n += 1
    return f"{stem} ({n}){ext}"
