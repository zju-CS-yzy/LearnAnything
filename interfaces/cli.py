#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行接口 (CLI)

使用方式:
    python -m interfaces.cli import --subject chemistry --path ./materials/
    python -m interfaces.cli ask --subject chemistry "解释化学键"
    python -m interfaces.cli quiz --subject chemistry "出题" --count 5
"""

import json
import argparse
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.document_processor import DocumentProcessor
from core.vector_store import VectorStore
from agents.coordinator import Coordinator
from agents.coach_agent import CoachAgent


def import_documents(args):
    """导入文档到知识库"""
    path = Path(args.path)
    if not path.exists():
        print(f"Error: Path not found: {path}")
        return 1

    processor = DocumentProcessor()
    store = VectorStore(f"{args.subject}_v1")

    files = []
    if path.is_file():
        files = [str(path)]
    elif path.is_dir():
        extensions = args.extensions.split(",") if args.extensions else [".txt", ".md", ".pdf", ".png", ".jpg"]
        for ext in extensions:
            files.extend([str(p) for p in path.rglob(f"*{ext}")])

    print(f"Found {len(files)} files to process")
    total_chunks = 0

    for i, fp in enumerate(files, 1):
        print(f"[{i}/{len(files)}] Processing {fp}...")
        try:
            chunks = processor.process_file(fp, subject=args.subject)
            if chunks:
                store.add_documents(chunks)
                total_chunks += len(chunks)
                print(f"  -> {len(chunks)} chunks added")
        except Exception as e:
            print(f"  -> Error: {e}")

    print(f"\nDone! Total chunks: {total_chunks}")
    print(f"Collection: {store.count()} documents")
    return 0


def ask_question(args):
    """回答用户问题"""
    coordinator = Coordinator(collection_name=f"{args.subject}_v1")
    result = coordinator.handle(args.query)

    print(f"\n{'='*60}")
    print(f"Intent: {result['intent']['resolved']} (confidence: {result['intent']['confidence']})")
    print(f"Agent: {result['agent']}")
    print(f"Duration: {result['monitoring']['total_duration_ms']}ms")
    print(f"{'='*60}")
    print(result['text'])
    print(f"{'='*60}")
    return 0


def generate_quiz(args):
    """生成题目"""
    coordinator = Coordinator(collection_name=f"{args.subject}_v1")
    result = coordinator.handle(f"给我出{args.count}道{args.topic or args.subject}面试题")
    print(result['text'])
    return 0


def evaluate_user(args):
    """评测用户能力 — 交互式出题 + 自动评分"""
    coach = CoachAgent(
        collection_name=f"{args.subject}_v1",
        subject=args.subject,
    )

    # 1. 出题
    print(f"\n{'='*60}")
    print("📝 正在生成评测题目...")
    print(f"{'='*60}")

    quiz_result = coach.handle(f"评测我的{args.topic or args.subject}水平", n_questions=args.count)
    questions = quiz_result.get("questions", [])

    if not questions:
        print("❌ 未生成题目，请确认知识库中已有材料。")
        return 1

    print(quiz_result.get("text", ""))

    # 2. 交互式收集答案
    print(f"\n{'='*60}")
    print("✏️ 请逐题作答（输入你的答案，按回车提交）")
    print(f"{'='*60}\n")

    user_answers = []
    for i, q in enumerate(questions, 1):
        q_text = q.get("question", "")
        q_type = q.get("type", "")
        print(f"【第 {i} 题】({q_type}) {q_text}")
        if q.get("options"):
            for opt in q.get("options"):
                print(f"  {opt}")
        try:
            answer = input("你的答案: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n❌ 评测已取消")
            return 1
        user_answers.append(answer)
        print()

    # 3. 自动评分
    print(f"{'='*60}")
    print("🤖 正在自动评分...")
    print(f"{'='*60}\n")

    report = coach.evaluate(questions, user_answers)

    # 4. 输出结果
    print(report.get("text", ""))

    # 5. 可选保存详细报告到文件
    if args.save_report:
        report_path = Path(args.save_report)
        # 移除 text 字段（可读文本），保留结构化数据
        report_data = {k: v for k, v in report.items() if k != "text"}
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        print(f"\n📄 详细报告已保存到: {report_path}")

    return 0


def score_batch(args):
    """批量评分 — 从文件读取答案"""
    answers_path = Path(args.answers_file)
    if not answers_path.exists():
        print(f"Error: Answers file not found: {answers_path}")
        return 1

    with open(answers_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    questions = data.get("questions", [])
    user_answers = data.get("answers", [])

    if not questions:
        print("Error: No questions in answers file")
        return 1

    coach = CoachAgent(
        collection_name=f"{args.subject}_v1",
        subject=args.subject,
    )

    report = coach.evaluate(questions, user_answers)
    print(report.get("text", ""))

    if args.save_report:
        report_path = Path(args.save_report)
        report_data = {k: v for k, v in report.items() if k != "text"}
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        print(f"\n📄 详细报告已保存到: {report_path}")

    return 0


def main():
    parser = argparse.ArgumentParser(description="LearnAnything CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # import
    import_parser = subparsers.add_parser("import", help="Import documents into knowledge base")
    import_parser.add_argument("--subject", required=True, help="Subject identifier")
    import_parser.add_argument("--path", required=True, help="Path to file or directory")
    import_parser.add_argument("--extensions", default=".txt,.md,.pdf,.png,.jpg", help="File extensions to process")

    # ask
    ask_parser = subparsers.add_parser("ask", help="Ask a question")
    ask_parser.add_argument("--subject", required=True, help="Subject identifier")
    ask_parser.add_argument("query", nargs="+", help="Question to ask")

    # quiz
    quiz_parser = subparsers.add_parser("quiz", help="Generate quiz questions")
    quiz_parser.add_argument("--subject", required=True, help="Subject identifier")
    quiz_parser.add_argument("--topic", default="", help="Topic for the quiz")
    quiz_parser.add_argument("--count", type=int, default=5, help="Number of questions")

    # evaluate — 交互式评测
    eval_parser = subparsers.add_parser("evaluate", help="Interactive evaluation: generate quiz and auto-score")
    eval_parser.add_argument("--subject", required=True, help="Subject identifier")
    eval_parser.add_argument("--topic", default="", help="Topic for evaluation")
    eval_parser.add_argument("--count", type=int, default=5, help="Number of questions")
    eval_parser.add_argument("--save-report", default="", help="Path to save JSON report")

    # score — 批量评分（从文件）
    score_parser = subparsers.add_parser("score", help="Batch scoring from answers file")
    score_parser.add_argument("--subject", required=True, help="Subject identifier")
    score_parser.add_argument("--answers-file", required=True, help="JSON file with questions and answers")
    score_parser.add_argument("--save-report", default="", help="Path to save JSON report")

    args = parser.parse_args()

    if args.command == "import":
        return import_documents(args)
    elif args.command == "ask":
        args.query = " ".join(args.query)
        return ask_question(args)
    elif args.command == "quiz":
        return generate_quiz(args)
    elif args.command == "evaluate":
        return evaluate_user(args)
    elif args.command == "score":
        return score_batch(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
