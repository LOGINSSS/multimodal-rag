"""LangGraph 编排：改写(R1) → HyDE → 混合检索 → 精排 → 生成(Qwen-VL)。

图结构：
    START -> rewrite -> hyde -> retrieve -> rerank -> generate -> END

- rewrite: DeepSeek-R1 把口语化/多意图问题改写成更利于检索的查询
- hyde:    用 chat 模型生成「假设性答案」，拿去检索可召回更贴合语义的片段
- retrieve: 对 [改写query, hyde, 原始query] 各做一次混合检索，合并去重
- rerank:  DashScope gte-rerank 对候选精排，取 top-K
- generate: Qwen-VL 依据 top-K 片段生成最终答案（附来源）

想看到算子意图 / trace：跑 app.py 后调 /ask，或在代码里给 run 传 langfuse 回调。
"""
from __future__ import annotations

from typing import Dict, List, TypedDict

from langgraph.graph import END, START, StateGraph

from . import config, llm, store

# ---------- 提示词 ----------

_REWRITE_PROMPT = """你是一个检索查询改写器。请把用户的问题改写成 1 个更适合向量检索和全文检索的查询。
要求：保留原意、补全隐含的上下文、去掉口语填充词，只输出改写后的查询，不要解释。

用户问题：{question}

改写后的查询："""

_HYDE_PROMPT = """你是一个知识助手。请根据你的知识，写一段能回答下面问题的文字（200 字以内）。
这段文字会被用来做检索，所以请写得更接近「知识库中可能存在的原文表达」。

问题：{question}

假设性回答："""

_GENERATE_PROMPT = """根据下面给出的参考资料回答用户问题。只依据参考资料作答，不要编造。
如果资料不足以回答，请直接说明「现有资料不足以回答」。

参考资料：
{context}

用户问题：{question}

回答："""


# ---------- 状态 ----------

class RAGState(TypedDict):
    question: str
    rewritten: str
    hyde: str
    queries: List[str]
    retrieved: List[Dict]
    reranked: List[Dict]
    answer: str
    sources: List[Dict]


# ---------- 节点 ----------

def rewrite_node(state: RAGState) -> Dict:
    question = state["question"]
    resp = llm.rewrite_llm.invoke(_REWRITE_PROMPT.format(question=question))
    rewritten = (resp.content or "").strip()
    return {"rewritten": rewritten, "queries": [question, rewritten]}


def hyde_node(state: RAGState) -> Dict:
    resp = llm.chat_llm.invoke(_HYDE_PROMPT.format(question=state["question"]))
    hyde_text = (resp.content or "").strip()
    queries = list(state["queries"]) + [hyde_text]
    return {"hyde": hyde_text, "queries": queries}


def _dedup(docs: List[Dict]) -> List[Dict]:
    seen: set = set()
    out: List[Dict] = []
    for d in docs:
        key = d["text"]
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def retrieve_node(state: RAGState) -> Dict:
    merged: List[Dict] = []
    for q in state["queries"]:
        if not q:
            continue
        merged.extend(store.hybrid_search(q, top_k=config.HYBRID_FETCH_K))
    retrieved = _dedup(merged)
    return {"retrieved": retrieved}


def rerank_node(state: RAGState) -> Dict:
    docs = state["retrieved"]
    if not docs:
        return {"reranked": []}
    texts = [d["text"] for d in docs]
    idxs = llm.rerank(state["question"], texts, top_n=config.RERANK_TOP_K)
    reranked = [docs[i] for i in idxs]
    return {"reranked": reranked}


def generate_node(state: RAGState) -> Dict:
    reranked = state["reranked"]
    if not reranked:
        return {"answer": "知识库为空或未检索到相关内容，请先入库文档。"}

    context = "\n\n".join(f"[{i + 1}] {d['text']}" for i, d in enumerate(reranked))
    resp = llm.generator.invoke(
        _GENERATE_PROMPT.format(context=context, question=state["question"])
    )
    sources = [
        {"source": d["source"], "doc_type": d["doc_type"], "text": d["text"]}
        for d in reranked
    ]
    return {"answer": (resp.content or "").strip(), "sources": sources}


# ---------- 组装图 ----------

def build_graph():
    g = StateGraph(RAGState)
    g.add_node("rewrite", rewrite_node)
    g.add_node("hyde", hyde_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("rerank", rerank_node)
    g.add_node("generate", generate_node)

    g.add_edge(START, "rewrite")
    g.add_edge("rewrite", "hyde")
    g.add_edge("hyde", "retrieve")
    g.add_edge("retrieve", "rerank")
    g.add_edge("rerank", "generate")
    g.add_edge("generate", END)
    return g.compile()


# 模块级单例，供 app / cli 复用
graph = build_graph()


def run_rag(question: str, callbacks: list | None = None) -> Dict:
    """执行一次完整 RAG，返回 {"answer", "sources", ...}。

    callbacks: 可选的回调列表（如 LangFuse CallbackHandler），用于观测 trace。
    """
    config_dict = {"callbacks": callbacks} if callbacks else None
    result = graph.invoke({"question": question}, config=config_dict)
    return result
