"""LangFuse 观测：可选，配置了 LANGFUSE_* 环境变量才启用。"""
from __future__ import annotations

from . import config


def get_langfuse_callback():
    """返回 LangFuse CallbackHandler，未配置时返回 None。"""
    if not (config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY):
        return None
    from langfuse.callback import CallbackHandler

    return CallbackHandler(
        public_key=config.LANGFUSE_PUBLIC_KEY,
        secret_key=config.LANGFUSE_SECRET_KEY,
        host=config.LANGFUSE_HOST or None,
    )
