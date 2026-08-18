"""命令行入口：rag serve / rag ingest / rag ask / rag count。"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rag", description="RAG 命令行工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_serve = sub.add_parser("serve", help="启动 FastAPI 服务（uvicorn）")
    p_serve.add_argument(
        "--reload",
        action="store_true",
        help="开发模式：代码变更自动重启（注意会中断正在进行的入库任务，如 MinerU 解析）",
    )

    p_ingest = sub.add_parser("ingest", help="入库文档")
    p_ingest.add_argument("path", help="文档或图片路径")

    p_ask = sub.add_parser("ask", help="问答")
    p_ask.add_argument("question", help="问题")

    sub.add_parser("count", help="查看向量库条数")

    args = parser.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn

        # 默认关闭 reload：热重载会在入库（MinerU 子进程）进行中被文件变化打断，
        # 需要自动重启时显式加 --reload。
        uvicorn.run("rag.app:app", host="127.0.0.1", port=13080, reload=args.reload)
        return 0

    if args.cmd == "ingest":
        from . import ingest

        n = ingest.ingest_file(args.path)
        print(f"已入库 {n} 个 chunk")
        return 0

    if args.cmd == "ask":
        from .graph import run_rag

        result = run_rag(args.question)
        print("=" * 40)
        print(result.get("answer", ""))
        print("=" * 40)
        for s in result.get("sources", []):
            print(f"  - [{s.get('doc_type')}] {s.get('source')}")
        return 0

    if args.cmd == "count":
        from . import store

        store.ensure_collection()
        print(f"向量库条数: {store.count()}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
