"""Milvus 向量库：建集合 + 混合检索（BM25 全文 + 稠密向量，RRF 融合）。

用 pymilvus 的 MilvusClient 直接操作，BM25 走 Milvus 2.5+ 的全文检索：
text 字段 enable_analyzer=True + BM25 函数生成稀疏向量字段 sparse_bm25，
混合检索时 BM25 一路检索 sparse_bm25（不能直接在 VARCHAR 字段上搜）。
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from pymilvus import AnnSearchRequest, DataType, Function, FunctionType, MilvusClient, RRFRanker

from . import config, llm

logger = logging.getLogger(__name__)

# 懒连接：MilvusClient 构造时就会连服务器，没起 Docker 时会抛异常，
# 所以首次真正使用时才建连接。
_client: Optional[MilvusClient] = None


def get_client() -> MilvusClient:
    global _client
    if _client is None:
        _client = MilvusClient(uri=config.MILVUS_URI)
    return _client


def _build_bm25_schema(client: MilvusClient):
    """构造带 BM25 函数（text -> sparse_bm25 稀疏向量）的集合 schema。"""
    bm25_function = Function(
        name="bm25",
        function_type=FunctionType.BM25,
        input_field_names=["text"],
        output_field_names=["sparse_bm25"],
    )
    schema = client.create_schema(auto_id=True, enable_dynamic_field=False, functions=[bm25_function])
    schema.add_field("pk", DataType.INT64, is_primary=True)
    schema.add_field(
        "text",
        DataType.VARCHAR,
        max_length=65535,
        enable_analyzer=True,
        analyzer_params={"type": "chinese"},
    )
    schema.add_field("sparse_bm25", DataType.SPARSE_FLOAT_VECTOR)
    schema.add_field("dense", DataType.FLOAT_VECTOR, dim=config.DENSE_DIM)
    schema.add_field("source", DataType.VARCHAR, max_length=512, nullable=True)
    schema.add_field("doc_type", DataType.VARCHAR, max_length=32, nullable=True)
    schema.add_field("metadata", DataType.VARCHAR, max_length=2048, nullable=True)
    return schema


def _create_indexes(client: MilvusClient) -> None:
    """dense(COSINE) + sparse_bm25(BM25) 双索引。"""
    dense_index = client.prepare_index_params()
    dense_index.add_index(field_name="dense", metric_type="COSINE", index_type="AUTOINDEX")
    client.create_index(config.MILVUS_COLLECTION, index_params=dense_index)

    bm25_index = client.prepare_index_params()
    bm25_index.add_index(field_name="sparse_bm25", metric_type="BM25", index_type="SPARSE_INVERTED_INDEX")
    client.create_index(config.MILVUS_COLLECTION, index_params=bm25_index)


def _migrate_legacy_collection(client: MilvusClient) -> None:
    """旧结构集合（缺 sparse_bm25 字段）无损迁移：导出 → 重建 → 回填。

    Milvus 2.5 不支持 AlterCollectionSchema，无法原地给集合加函数字段，
    只能重建；重建前先把旧数据（text/dense/元数据）导出，重建后回填。
    """
    name = config.MILVUS_COLLECTION
    client.load_collection(name)
    rows = client.query(
        name,
        filter="pk >= 0",
        output_fields=["text", "dense", "source", "doc_type", "metadata"],
        limit=100000,
    )
    client.drop_collection(name)
    client.create_collection(name, schema=_build_bm25_schema(client))
    _create_indexes(client)
    data = [
        {
            "text": r["text"],
            "dense": r["dense"],
            "source": r.get("source"),
            "doc_type": r.get("doc_type"),
            "metadata": r.get("metadata"),
        }
        for r in rows
    ]
    if data:
        client.insert(name, data=data)
    client.load_collection(name)


def ensure_collection() -> None:
    """建集合（若不存在）并建索引。幂等，可重复调用。

    若发现旧结构集合（缺 sparse_bm25 字段），自动做无损迁移。
    """
    client = get_client()
    if client.has_collection(config.MILVUS_COLLECTION):
        desc = client.describe_collection(config.MILVUS_COLLECTION)
        fields = {f["name"] for f in desc.get("fields", [])}
        if "sparse_bm25" not in fields:
            logger.warning("检测到旧结构集合（缺 sparse_bm25 字段），执行无损迁移…")
            _migrate_legacy_collection(client)
        return

    client.create_collection(config.MILVUS_COLLECTION, schema=_build_bm25_schema(client))
    _create_indexes(client)
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

    # 一路：BM25 全文检索（搜 BM25 函数生成的稀疏向量字段）
    bm25_req = AnnSearchRequest(
        data=[query],
        anns_field="sparse_bm25",
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
