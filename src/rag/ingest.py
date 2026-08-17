"""文档入库：提取文本 → 结构化分片 → embedding → 写入 Milvus。

支持：.md / .txt / .docx / .pptx / .pdf（简单文本抽取）/ 图片（OCR + VLM 描述）。
MinerU 的完整版面解析（PDF 表格/公式/图）是后续增强项，见 README 的 TODO。
"""
from __future__ import annotations

import base64
import json
import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from . import config, llm, store

logger = logging.getLogger(__name__)

# ---------- 分片 ----------

_HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3"), ("####", "h4")]

# 超大块兜底切分（中文友好的分隔符）
_FALLBACK = RecursiveCharacterTextSplitter(
    chunk_size=900,
    chunk_overlap=100,
    separators=["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " ", ""],
)


def split_text(text: str) -> List[Dict]:
    """按 Markdown 标题结构化分片；无标题则退化为递归分片。返回 [{text, metadata}]。"""
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=_HEADERS, strip_headers=False
    )
    md_docs = md_splitter.split_text(text)

    chunks: List[Dict] = []
    for d in md_docs:
        meta = dict(d.metadata)
        if len(d.page_content) > 1200:
            for sub in _FALLBACK.split_text(d.page_content):
                chunks.append({"text": sub.strip(), "metadata": meta})
        else:
            if d.page_content.strip():
                chunks.append({"text": d.page_content.strip(), "metadata": meta})
    return chunks


# ---------- 文本抽取（按扩展名分派） ----------

def _mineru_exe() -> str:
    """找到 mineru 可执行文件（优先 PATH，退回当前 venv 的 Scripts 目录）。"""
    exe = shutil.which("mineru")
    if exe:
        return exe
    name = "mineru.exe" if sys.platform == "win32" else "mineru"
    candidate = Path(sys.executable).parent / name
    return str(candidate) if candidate.exists() else "mineru"


def _pdf_to_markdown(path: Path) -> str:
    """用 MinerU 把 PDF 转 markdown（版面解析 + OCR + 公式 + 表格）。

    以子进程方式运行，把 PyTorch 模型隔离在独立进程里，不污染 FastAPI 进程。
    产出的 markdown 会继续走 split_text() 的结构化分片。
    """
    workdir = Path(tempfile.mkdtemp(prefix="mineru_", dir=config.DATA_DIR))
    try:
        cmd = [
            _mineru_exe(),
            "-p", str(path),
            "-o", str(workdir),
            "-b", config.MINERU_BACKEND,
            "-m", config.MINERU_METHOD,
            "-l", config.MINERU_LANG,
        ]
        logger.info("MinerU 解析 %s (backend=%s, method=%s)", path.name, config.MINERU_BACKEND, config.MINERU_METHOD)
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=config.MINERU_TIMEOUT)

        stem = path.stem
        matches = list(workdir.rglob(f"{stem}.md"))
        if not matches:
            raise FileNotFoundError(f"MinerU 未产出 markdown：{workdir}")
        return max(matches, key=lambda p: p.stat().st_size).read_text(encoding="utf-8")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".md", ".markdown", ".txt"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if ext == ".docx":
        import docx  # python-docx

        doc = docx.Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if ext == ".pptx":
        from pptx import Presentation  # python-pptx

        prs = Presentation(str(path))
        parts = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    parts.append(shape.text)
        return "\n".join(parts)
    if ext == ".pdf":
        try:
            return _pdf_to_markdown(path)
        except subprocess.CalledProcessError as e:
            logger.warning("MinerU 解析失败，回退 PyMuPDF 纯文本：%s", (e.stderr or "")[-2000:])
        except Exception as e:  # noqa: BLE001
            logger.warning("MinerU 解析失败，回退 PyMuPDF 纯文本：%s", e)
        import fitz  # PyMuPDF 兜底

        doc = fitz.open(str(path))
        return "\n".join(page.get_text() for page in doc)
    raise ValueError(f"不支持的文档类型: {ext}")


# ---------- 图片处理 ----------

def _describe_image(path: Path) -> str:
    """用 Qwen-VL 描述图片语义（DashScope API，无需本地模型）。"""
    b64 = base64.b64encode(path.read_bytes()).decode()
    msg = llm.generator.invoke(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "详细描述这张图片的内容、关键文字和图表数据。"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }
        ]
    )
    return msg.content if isinstance(msg.content, str) else str(msg.content)


def _ocr_image(path: Path) -> str:
    """RapidOCR 抽取图片里的文字（首次调用会下载 onnx 模型）。失败返回空串。"""
    try:
        from rapidocr_onnxruntime import RapidOCR

        ocr = RapidOCR()
        result, _ = ocr(str(path))
        if not result:
            return ""
        return "\n".join(r[1] for r in result)
    except Exception:  # noqa: BLE001 —— OCR 失败不阻断入库
        return ""


def ingest_image(path: Path) -> int:
    """图片入库：OCR 文字 + VLM 描述分别作为一个 chunk。"""
    source = path.name

    ocr_text = _ocr_image(path)
    description = _describe_image(path)

    chunks = []
    if description:
        chunks.append(
            {
                "text": f"[图片描述] {description}",
                "metadata": json.dumps({"kind": "image_description"}, ensure_ascii=False),
            }
        )
    if ocr_text:
        chunks.append(
            {
                "text": f"[图片OCR文字] {ocr_text}",
                "metadata": json.dumps({"kind": "image_ocr"}, ensure_ascii=False),
            }
        )
    if not chunks:
        return 0
    return _embed_and_insert(chunks, source, "image")


# ---------- 核心入库 ----------

def _embed_and_insert(chunks: List[Dict], source: str, doc_type: str) -> int:
    texts = [c["text"] for c in chunks]
    vectors = llm.embeddings.embed_documents(texts)
    data = [
        {
            "text": c["text"],
            "dense": v,
            "source": source,
            "doc_type": doc_type,
            "metadata": json.dumps(c["metadata"], ensure_ascii=False),
        }
        for c, v in zip(chunks, vectors)
    ]
    return store.insert(data)


def ingest_text(text: str, source: str = "inline", doc_type: str = "text") -> int:
    """纯文本入库。"""
    chunks = split_text(text)
    return _embed_and_insert(chunks, source, doc_type)


def ingest_file(path: str | Path) -> int:
    """按文件类型入库，返回写入的 chunk 数。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
        return ingest_image(path)

    text = _extract_text(path)
    chunks = split_text(text)
    doc_type = path.suffix.lower().lstrip(".")
    return _embed_and_insert(chunks, path.name, doc_type)
