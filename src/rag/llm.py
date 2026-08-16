"""模型客户端：DeepSeek（R1/chat）、DashScope（embedding + Qwen-VL + rerank）。

客户端**惰性构建**：首次真正调用时才创建连接对象。这样没配 API key 时
`import rag` / `rag count` 也不会在 import 阶段就抛错。
用法：`from . import llm`，再 `llm.rewrite_llm` / `llm.embeddings` / `llm.generator`。
"""
from __future__ import annotations

from typing import List

import dashscope
from dashscope import TextReRank
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from . import config

_CACHE: dict = {}


def _build_rewrite_llm():
    # R1：query 重构（推理能力强，慢一点没关系）
    return ChatDeepSeek(
        model=config.DEEPSEEK_REASONER_MODEL,
        api_key=config.DEEPSEEK_API_KEY,
        temperature=0,
        timeout=120,
    )


def _build_chat_llm():
    # chat：HyDE 等便宜、快的小任务
    return ChatDeepSeek(
        model=config.DEEPSEEK_CHAT_MODEL,
        api_key=config.DEEPSEEK_API_KEY,
        temperature=0.7,
        timeout=60,
    )


def _build_embeddings():
    # DashScope embedding（OpenAI 兼容端点）
    return OpenAIEmbeddings(
        model=config.DASHSCOPE_EMBEDDING_MODEL,
        base_url=config.DASHSCOPE_BASE_URL,
        api_key=config.DASHSCOPE_API_KEY,
    )


def _build_generator():
    # Qwen-VL 生成（多模态，OpenAI 兼容端点）
    return ChatOpenAI(
        model=config.QWEN_VL_MODEL,
        base_url=config.DASHSCOPE_BASE_URL,
        api_key=config.DASHSCOPE_API_KEY,
        temperature=0,
        timeout=120,
    )


_FACTORIES = {
    "rewrite_llm": _build_rewrite_llm,
    "chat_llm": _build_chat_llm,
    "embeddings": _build_embeddings,
    "generator": _build_generator,
}


def __getattr__(name: str):
    if name in _FACTORIES:
        if name not in _CACHE:
            _CACHE[name] = _FACTORIES[name]()
        return _CACHE[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ---------- DashScope rerank 精排 ----------
def rerank(query: str, documents: List[str], top_n: int) -> List[int]:
    """对 documents 精排，返回按相关度降序的「原下标」列表。

    用 DashScope 的 rerank 模型（默认 gte-rerank-v2）。
    想换本地 Qwen3-Reranker / bge-reranker 时，只改这个函数即可。
    """
    if not documents:
        return []
    resp: TextReRank = TextReRank.call(
        model=config.RERANK_MODEL,
        query=query,
        documents=documents,
        top_n=min(top_n, len(documents)),
        api_key=config.DASHSCOPE_API_KEY,
    )
    if resp.status_code != 200:  # type: ignore[attr-defined]
        raise RuntimeError(f"rerank 失败: {resp.message}")  # type: ignore[attr-defined]

    results = resp.output.results  # type: ignore[attr-defined]
    ordered = sorted(results, key=lambda r: r.relevance_score, reverse=True)
    return [r.index for r in ordered]
