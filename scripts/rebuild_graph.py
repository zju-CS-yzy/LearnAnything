#!/usr/bin/env python3
"""
重建知识库数据库脚本（Schema 扩展后）

用法: python rebuild_graph.py [subject_id] [--force]
"""

import sys
import argparse

sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.graph_builder import GraphBuilder


def rebuild(subject: str, force: bool = True):
    """重建指定学科的图数据库"""
    print(f"=== 重建图数据库: {subject} ===")
    print(f"force_rebuild={force}")

    builder = GraphBuilder(f"{subject}_v1")
    result = builder.build_all(force_rebuild=force)

    print("\n=== 重建结果 ===")
    for key, value in result.items():
        print(f"  {key}: {value}")

    return result


def main():
    parser = argparse.ArgumentParser(description="重建知识库图数据库")
    parser.add_argument("subject", nargs="?", default="generic", help="学科ID (默认: generic)")
    parser.add_argument("--force", action="store_true", default=True, help="强制重建")
    parser.add_argument("--no-force", action="store_true", help="不强制重建")

    args = parser.parse_args()
    force = not args.no_force

    rebuild(args.subject, force=force)


if __name__ == "__main__":
    main()
