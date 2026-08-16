"""Milvus 向量库：建集合 + 混合检索（BM25 全文 + 稠密向量，RRF 融合）。

用 pymilvus 的 MilvusClient 直接操作，BM25 走 Milvus 2.5+ 的内置全文检索
（text 字段 enable_analyzer=True），不需要手动生成稀疏向量。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pymilvus import AnnSearchRequest, DataType, MilvusClient, RRFRanker

from . import config, llm

# 懒连接：MilvusClient 构造时就会连服务器，没起 Docker 时会抛异常，
# 所以首次真正使用时才建连接。
_client: Optional[MilvusClient] = None


def get_client() -> MilvusClient:
    global _client
    if _client is None:
        _client = MilvusClient(uri=config.MILVUS_URI)
    return _client


def ensure_collection() -> None:
    """建集合（若不存在）并建索引。幂等，可重复调用。"""
    client = get_client()
    if client.has_collection(config.MILVUS_COLLECTION):
        return

    # 字段：pk 主键 / text 全文检索字段(中文分词) / dense 稠密向量 / source 来源 / metadata 元数据JSON
    schema = client.create_schema(auto_id=True, enable_dynamic_field=False)
    schema.add_field("pk", DataType.INT64, is_primary=True)
    schema.add_field(
        "text",
        DataType.VARCHAR,
        max_length=65535,
        enable_analyzer=True,
        analyzer_params={"type": "chinese"},
    )
    schema.add_field("dense", DataType.FLOAT_VECTOR, dim=config.DENSE_DIM)
    schema.add_field("source", DataType.VARCHAR, max_length=512, nullable=True)
    schema.add_field("doc_type", DataType.VARCHAR, max_length=32, nullable=True)
    schema.add_field("metadata", DataType.VARCHAR, max_length=2048, nullable=True)

    client.create_collection(config.MILVUS_COLLECTION, schema=schema)

    # 索引：dense 用 COSINE（DashScope embedding 归一化后余弦最合适）
    #       text 用 BM25 全文检索索引（Milvus 2.5+ 专用 metric_type）
    dense_index = client.prepare_index_params()
    dense_index.add_index(
        field_name="dense",
        metric_type="COSINE",
        index_type="AUTOINDEX",
    )
    client.create_index(config.MILVUS_COLLECTION, index_params=dense_index)

    bm25_index = client.prepare_index_params()
    bm25_index.add_index(
        field_name="text",
        metric_type="BM25",
        index_type="AUTOINDEX",
    )
    client.create_index(config.MILVUS_COLLECTION, index_params=bm25_index)

    client.load_collection(config.MILVUS_COLLECTION)


def insert(chunks: List[Dict]) -> int:
    """插入 chunks，返回插入条数。chunk 形如
    {"text": str, "dense": List[float], "source": str, "doc_type": str, "metadata": str}
    """
    ensure_collection()
    if not chunks:
        return 0
    client = get_client()
    res = client.insert(config.MILVUS_COLLECTION, data=chunks)
    return res.get("insert_count", len(chunks))


def hybrid_search(
    query: str,
    top_k: int = 5,
    fetch_k: Optional[int] = None,
    expr: Optional[str] = None,
) -> List[Dict]:
    """混合检索：BM25 + 稠密向量，RRF 融合，返回 top_k 条。

    返回 [{"text": str, "source": str, "doc_type": str, "metadata": str, "score": float}]
    """
    ensure_collection()
    fetch_k = fetch_k or config.HYBRID_FETCH_K
    client = get_client()

    # 一路：BM25 全文检索（data 直接传原始 query 文本）
    bm25_req = AnnSearchRequest(
        data=[query],
        anns_field="text",
        param={"metric_type": "BM25"},
        limit=fetch_k,
        expr=expr,
    )
    # 一路：稠密向量检索
    dense_vec = llm.embeddings.embed_query(query)
    dense_req = AnnSearchRequest(
        data=[dense_vec],
        anns_field="dense",
        param={"metric_type": "COSINE", "params": {"nprobe": 16}},
        limit=fetch_k,
        expr=expr,
    )

    results = client.hybrid_search(
        config.MILVUS_COLLECTION,
        reqs=[bm25_req, dense_req],
        ranker=RRFRanker(k=config.RRF_K),
        limit=top_k,
        output_fields=["text", "source", "doc_type", "metadata"],
    )

    out: List[Dict] = []
    for hit in results[0]:
        entity = hit["entity"]
        out.append(
            {
                "text": entity["text"],
                "source": entity.get("source", ""),
                "doc_type": entity.get("doc_type", ""),
                "metadata": entity.get("metadata", ""),
                "score": hit["distance"],
            }
        )
    return out


def count() -> int:
    """集合里的向量条数。"""
    client = get_client()
    if not client.has_collection(config.MILVUS_COLLECTION):
        return 0
    stats = client.get_collection_stats(config.MILVUS_COLLECTION)
    return stats.get("row_count", 0)
