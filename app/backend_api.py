#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LearnAnything API Backend
FastAPI 后端 — 封装 core/ + agents/ 能力为 REST API

启动方式:
    cd D:\MyCS\AI\Project\LearnAnything
    python -m app.backend_api

或:
    uvicorn app.backend_api:app --host 127.0.0.1 --port 5000 --reload

API 文档:
    http://127.0.0.1:5000/docs  (Swagger UI)
    http://127.0.0.1:5000/redoc (ReDoc)
"""

import sys
from pathlib import Path

import re  # 用于 SSE 流式接口的文本切分

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uuid
import time
import json
import asyncio

from agents.coordinator import Coordinator
from agents.coach_agent import CoachAgent
from agents.quiz_agent import QuizAgent
from agents.tutor_agent import TutorAgent
from core.document_processor import DocumentProcessor
from core.vector_store import VectorStore
from core.subject_analyzer import SubjectAnalyzer, save_subject_config
from core.llm_client import LLMClient
from core.quiz_bank import (
    save_question as qb_save,
    batch_save_questions as qb_batch_save,
    random_questions as qb_random,
    list_questions as qb_list,
    approve_question as qb_approve,
    delete_question as qb_delete,
    get_stats as qb_stats,
)



# ========== 路径解析（兼容开发环境和 PyInstaller 打包环境） ==========

def get_project_root() -> Path:
    """获取项目根目录，兼容 PyInstaller 6 one-dir 模式"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 6 one-dir 模式：数据文件在 _internal/ 中
        exe_dir = Path(sys.executable).parent
        internal_dir = exe_dir / '_internal'
        # 优先检查 _internal 目录（PyInstaller 6 的数据文件位置）
        if internal_dir.exists() and (internal_dir / 'web').exists():
            return internal_dir
        # 回退到 exe 目录（PyInstaller 5 或自定义布局）
        return exe_dir
    else:
        # 开发环境
        return Path(__file__).parent.parent


PROJECT_ROOT = get_project_root()
WEB_DIR = PROJECT_ROOT / "web"
CONFIG_DIR = PROJECT_ROOT / "config"

# 添加项目根目录到 sys.path（确保 core/ agents/ config/ 等可被导入）
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ========== FastAPI 应用 ==========

app = FastAPI(
    title="LearnAnything API",
    description="通用知识学习 RAG 系统 — REST API",
    version="1.0.0",
)

# CORS 中间件（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制为前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== 内存会话存储（评测用） ==========
# 生产环境应使用 Redis 或数据库
_eval_sessions: Dict[str, Dict[str, Any]] = {}


def _cleanup_session(session_id: str):
    """清理过期会话（24小时）"""
    if session_id in _eval_sessions:
        del _eval_sessions[session_id]


# ========== Pydantic 模型（请求/响应） ==========

class AskRequest(BaseModel):
    """提问请求"""
    query: str = Field(..., description="用户问题", min_length=1)
    subject: str = Field("generic", description="学科标识")
    user_id: Optional[str] = Field(None, description="用户ID（可选，用于监控）")
    session_id: Optional[str] = Field(None, description="会话ID（可选）")


class AskResponse(BaseModel):
    """提问响应"""
    question: str
    answer: str
    intent: Dict[str, Any]
    agent: str
    duration_ms: float
    query_id: str


class QuizRequest(BaseModel):
    """出题请求"""
    topic: str = Field(..., description="出题主题", min_length=1)
    subject: str = Field("generic", description="学科标识")
    count: int = Field(5, ge=1, le=20, description="题目数量")


class QuizQuestion(BaseModel):
    """单道题目"""
    id: int
    type: str
    question: str
    options: List[str] = []
    answer: str
    explanation: str


class QuizResponse(BaseModel):
    """出题响应"""
    topic: str
    questions: List[QuizQuestion]
    subject_name: str
    question_types: List[str]


class EvaluateStartRequest(BaseModel):
    """开始评测请求"""
    topic: str = Field(..., description="评测主题")
    subject: str = Field("generic", description="学科标识")
    count: int = Field(5, ge=1, le=10, description="题目数量")
    mode: str = Field("generate", description="出题模式: generate(生成新题) / bank(从题库抽题) / mixed(混合)")

class QuizBankQuestion(BaseModel):
    """题库题目"""
    id: str
    type: str
    question: str
    options: List[str] = []
    answer: str
    explanation: str

class QuizBankListResponse(BaseModel):
    """题库列表响应"""
    questions: List[QuizBankQuestion]
    total: int

class QuizBankSaveRequest(BaseModel):
    """保存题目到题库请求"""
    subject: str = Field("generic", description="学科标识")
    topic: str = Field("", description="主题")
    questions: List[QuizQuestion]
    is_approved: bool = Field(False, description="是否直接标记为已确认")

class QuizBankStatsResponse(BaseModel):
    """题库统计响应"""
    total: int
    approved: int
    pending: int
    by_type: Dict[str, int]


class EvaluateStartResponse(BaseModel):
    """开始评测响应"""
    session_id: str
    topic: str
    subject_name: str
    questions: List[QuizQuestion]
    instructions: str


class EvaluateSubmitRequest(BaseModel):
    """提交评测答案请求"""
    session_id: str = Field(..., description="评测会话ID")
    answers: List[str] = Field(..., description="用户答案列表，顺序与题目对应")


class EvaluateDetail(BaseModel):
    """单题评分详情"""
    id: int
    type: str
    question: str
    user_answer: str
    correct_answer: str
    score: int
    max_score: int
    is_correct: bool
    feedback: str


class EvaluateResponse(BaseModel):
    """评测结果响应"""
    total_score: int
    max_score: int
    percentage: float
    correct_count: int
    total_questions: int
    level: str
    summary: str
    weak_areas: List[str]
    strong_areas: List[str]
    details: List[EvaluateDetail]


class ImportRequest(BaseModel):
    """导入材料请求（URL 或文本）"""
    subject: str = Field(..., description="学科标识")
    text: str = Field(..., description="文本内容")
    source_name: str = Field("user_input", description="来源名称")


class ImportResponse(BaseModel):
    """导入响应"""
    subject: str
    chunks_added: int
    total_documents: int
    message: str


class SubjectConfig(BaseModel):
    """学科配置响应"""
    subject: str
    name: str
    description: str
    question_types: Dict[str, Any]
    difficulty_levels: Dict[str, Any]
    special_features: List[str]


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    service: str
    version: str
    uptime_seconds: float


class SubjectListResponse(BaseModel):
    """学科列表响应"""
    subjects: List[Dict[str, str]]


# ========== API 路由 ==========

_start_time = time.time()


@app.get("/api/health", response_model=HealthResponse)
def health_check():
    """健康检查接口"""
    return HealthResponse(
        status="ok",
        service="learnanything-backend",
        version="1.0.0",
        uptime_seconds=round(time.time() - _start_time, 1),
    )


@app.post("/api/ask", response_model=AskResponse)
def ask_question(request: AskRequest):
    """
    智能问答接口（非流式）。

    根据用户问题自动路由到合适的 Agent，返回完整回答。
    """
    print(f"[API] /api/ask called: query={request.query}, subject={request.subject}")
    coordinator = Coordinator(
        collection_name=f"{request.subject}_v1",
        top_k=5,
    )
    result = coordinator.handle(
        query=request.query,
        user_id=request.user_id,
        session_id=request.session_id,
    )
    print(f"[API] /api/ask returning answer length={len(result.get('text', ''))}")

    return AskResponse(
        question=request.query,
        answer=result.get("text", ""),
        intent=result.get("intent", {}),
        agent=result.get("agent", ""),
        duration_ms=result.get("monitoring", {}).get("total_duration_ms", 0),
        query_id=result.get("monitoring", {}).get("query_id", ""),
    )


@app.post("/api/ask/stream")
def ask_stream(request: AskRequest):
    """
    智能问答流式接口（SSE）。

    先检索知识并路由到合适 Agent，然后将回答分段流式发送。
    注意：为避免重复调用 LLM，coordinator.handle() 的结果直接分段发送，
    而不是重新调用一次 LLM 流式生成。

    SSE 格式：
        event: meta\n
        data: {"intent": ..., "agent": ...}\n\n
        event: chunk\n
        data: {"text": "..."}\n\n
        event: done\n
        data: {}\n\n
    """
    async def event_generator():
        # 1. 同步检索和路由（coordinator.handle 内部 TutorAgent 会调用一次 LLM）
        coordinator = Coordinator(
            collection_name=f"{request.subject}_v1",
            top_k=5,
        )
        result = coordinator.handle(
            query=request.query,
            user_id=request.user_id,
            session_id=request.session_id,
        )

        intent = result.get("intent", {})
        agent_name = result.get("agent", "")
        query_id = result.get("monitoring", {}).get("query_id", "")
        answer_text = result.get("text", "")

        # 发送元数据事件
        meta = json.dumps({
            "intent": intent,
            "agent": agent_name,
            "query_id": query_id,
            "question": request.query,
        }, ensure_ascii=False)
        yield f"event: meta\ndata: {meta}\n\n"

        # 2. 将已有回答分段流式发送（避免重复调用 LLM）
        # 按段落、句子或固定长度切分，模拟打字机效果
        if answer_text:
            # 按段落切分，每个段落作为一个 chunk
            paragraphs = answer_text.split('\n\n')
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                # 如果段落太长，再按句子切分
                if len(para) > 200:
                    sentences = re.split(r'([。！？.!?]\s*)', para)
                    buffer = ""
                    for s in sentences:
                        buffer += s
                        if len(buffer) >= 80 or s.strip() and s.strip()[-1] in '。！？.!?':
                            chunk_data = json.dumps({"text": buffer}, ensure_ascii=False)
                            yield f"event: chunk\ndata: {chunk_data}\n\n"
                            buffer = ""
                            await asyncio.sleep(0.03)  # 模拟打字延迟
                    if buffer:
                        chunk_data = json.dumps({"text": buffer}, ensure_ascii=False)
                        yield f"event: chunk\ndata: {chunk_data}\n\n"
                else:
                    chunk_data = json.dumps({"text": para + '\n\n'}, ensure_ascii=False)
                    yield f"event: chunk\ndata: {chunk_data}\n\n"
                    await asyncio.sleep(0.05)
        else:
            err_data = json.dumps({"text": "抱歉，未能生成回答。"}, ensure_ascii=False)
            yield f"event: chunk\ndata: {err_data}\n\n"

        # 3. 发送完成事件
        yield f"event: done\ndata: {{}}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )


@app.post("/api/quiz", response_model=QuizResponse)
def generate_quiz(request: QuizRequest):
    """
    出题接口。

    基于知识库检索内容生成指定数量的题目。
    """
    quiz_agent = QuizAgent(
        collection_name=f"{request.subject}_v1",
        subject=request.subject,
        top_k=5,
    )
    result = quiz_agent.handle(
        query=f"给我出{request.count}道{request.topic}题目",
        n_questions=request.count,
    )

    questions = result.get("questions", [])
    # 转换为 Pydantic 模型
    quiz_questions = [
        QuizQuestion(
            id=q.get("id", 0),
            type=q.get("type", "short_answer"),
            question=q.get("question", ""),
            options=q.get("options", []),
            answer=q.get("answer", ""),
            explanation=q.get("explanation", ""),
        )
        for q in questions
    ]

    subject_config = result.get("subject_config", {})
    return QuizResponse(
        topic=result.get("topic", request.topic),
        questions=quiz_questions,
        subject_name=subject_config.get("name", "通用"),
        question_types=subject_config.get("question_types_used", ["single_choice", "short_answer"]),
    )


@app.post("/api/evaluate/start", response_model=EvaluateStartResponse)
def start_evaluation(request: EvaluateStartRequest):
    """
    开始评测 — 生成题目或从题库抽题并创建会话。

    mode: generate(生成新题) / bank(从题库抽题) / mixed(混合)
    返回 session_id 和题目列表，前端保存 session_id 供后续提交答案。
    """
    session_id = str(uuid.uuid4())

    questions = []
    instructions = ""
    subject_name = "通用"

    if request.mode == "bank":
        # 从题库抽题
        bank_questions = qb_random(
            count=request.count,
            subject=request.subject,
            topic=request.topic,
            is_approved=True,
        )
        if not bank_questions:
            raise HTTPException(status_code=400, detail="题库中没有符合条件的题目，请先用'生成新题'模式或导入题目")
        questions = bank_questions
        instructions = f"本次评测从题库中抽取了 {len(questions)} 道题目。"

    elif request.mode == "mixed":
        # 混合模式：一半题库 + 一半生成
        bank_count = request.count // 2
        gen_count = request.count - bank_count

        bank_questions = qb_random(
            count=bank_count,
            subject=request.subject,
            topic=request.topic,
            is_approved=True,
        )

        if gen_count > 0:
            coach = CoachAgent(
                collection_name=f"{request.subject}_v1",
                subject=request.subject,
                top_k=5,
            )
            quiz_result = coach.handle(
                query=f"评测我的{request.topic}水平",
                n_questions=gen_count,
            )
            gen_questions = quiz_result.get("questions", [])
        else:
            gen_questions = []

        questions = bank_questions + gen_questions
        # 重新编号
        for i, q in enumerate(questions):
            q["id"] = i + 1
        instructions = f"本次评测包含 {len(bank_questions)} 道题库题目和 {len(gen_questions)} 道生成题目。"

    else:
        # 默认：生成新题
        coach = CoachAgent(
            collection_name=f"{request.subject}_v1",
            subject=request.subject,
            top_k=5,
        )
        quiz_result = coach.handle(
            query=f"评测我的{request.topic}水平",
            n_questions=request.count,
        )

        questions = quiz_result.get("questions", [])
        if not questions:
            raise HTTPException(status_code=400, detail="无法生成评测题目，请确认知识库中已有材料")

        subject_config = quiz_result.get("subject_config", {})
        subject_name = subject_config.get("name", "通用")
        instructions = quiz_result.get("text", "").split("\n\n")[0] if quiz_result.get("text") else ""

    # 保存会话
    _eval_sessions[session_id] = {
        "questions": questions,
        "subject": request.subject,
        "topic": request.topic,
        "mode": request.mode,
        "created_at": time.time(),
    }

    quiz_questions = [
        QuizQuestion(
            id=q.get("id", 0),
            type=q.get("type", "short_answer"),
            question=q.get("question", ""),
            options=q.get("options", []),
            answer=q.get("answer", ""),
            explanation=q.get("explanation", ""),
        )
        for q in questions
    ]

    return EvaluateStartResponse(
        session_id=session_id,
        topic=request.topic,
        subject_name=subject_name,
        questions=quiz_questions,
        instructions=instructions,
    )


@app.post("/api/evaluate/submit", response_model=EvaluateResponse)
def submit_evaluation(request: EvaluateSubmitRequest):
    """
    提交评测答案 — 自动评分并返回报告。

    需要传入之前 /api/evaluate/start 返回的 session_id。
    """
    session = _eval_sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="评测会话不存在或已过期")

    questions = session.get("questions", [])
    if not questions:
        raise HTTPException(status_code=400, detail="会话中没有题目")

    if len(request.answers) != len(questions):
        raise HTTPException(
            status_code=400,
            detail=f"答案数量不匹配：期望 {len(questions)} 个，实际收到 {len(request.answers)} 个"
        )

    coach = CoachAgent(
        collection_name=f"{session['subject']}_v1",
        subject=session["subject"],
    )
    report = coach.evaluate(questions, request.answers)

    # 清理会话
    del _eval_sessions[request.session_id]

    details = [
        EvaluateDetail(
            id=d.get("id", 0),
            type=d.get("type", ""),
            question=d.get("question", ""),
            user_answer=d.get("user_answer", ""),
            correct_answer=d.get("correct_answer", ""),
            score=d.get("score", 0),
            max_score=d.get("max_score", 0),
            is_correct=d.get("is_correct", False),
            feedback=d.get("feedback", ""),
        )
        for d in report.get("details", [])
    ]

    return EvaluateResponse(
        total_score=report.get("total_score", 0),
        max_score=report.get("max_score", 0),
        percentage=report.get("percentage", 0.0),
        correct_count=report.get("correct_count", 0),
        total_questions=report.get("total_questions", 0),
        level=report.get("level", "未知"),
        summary=report.get("summary", ""),
        weak_areas=report.get("weak_areas", []),
        strong_areas=report.get("strong_areas", []),
        details=details,
    )


@app.post("/api/import/text", response_model=ImportResponse)
def import_text(request: ImportRequest):
    """
    导入文本材料到知识库。

    将纯文本内容分块、生成向量并存储到指定学科的知识库中。
    """
    processor = DocumentProcessor()
    store = VectorStore(f"{request.subject}_v1")

    # 创建临时文件让 DocumentProcessor 处理
    from core.chunking import DocumentChunker
    chunker = DocumentChunker()
    metadata = {
        "source": request.source_name,
        "subject": request.subject,
    }
    chunks = chunker.chunk(request.text, metadata)

    # 转换为 VectorStore 需要的格式
    docs = []
    for i, chunk in enumerate(chunks):
        docs.append({
            "id": f"{request.subject}_text_{i}",
            "text": chunk["text"],
            "metadata": {**metadata, **chunk.get("metadata", {})},
        })

    store.add_documents(docs)
    total_docs = store.count()

    return ImportResponse(
        subject=request.subject,
        chunks_added=len(docs),
        total_documents=total_docs,
        message=f"成功导入 {len(docs)} 个文本片段到「{request.subject}」知识库",
    )


@app.post("/api/import/file")
def import_file(
    subject: str = Form(..., description="学科标识"),
    file: UploadFile = File(..., description="上传文件（支持 .txt, .md, .pdf, .png, .jpg）"),
    background_tasks: BackgroundTasks = None,
):
    """
    上传文件导入知识库。

    支持格式：文本、Markdown、PDF（文字型/扫描件）、图片（OCR）。
    """
    import tempfile

    # 保存上传文件到临时位置
    suffix = Path(file.filename).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = file.file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        processor = DocumentProcessor()
        store = VectorStore(f"{subject}_v1")

        chunks = processor.process_file(tmp_path, subject=subject)
        if chunks:
            store.add_documents(chunks)
            total_docs = store.count()
            return {
                "subject": subject,
                "filename": file.filename,
                "chunks_added": len(chunks),
                "total_documents": total_docs,
                "message": f"成功导入「{file.filename}」，生成 {len(chunks)} 个知识片段",
            }
        else:
            raise HTTPException(status_code=400, detail="文件处理失败，未提取到有效内容")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件处理失败: {str(e)}")
    finally:
        # 清理临时文件
        try:
            Path(tmp_path).unlink()
        except:
            pass


@app.get("/api/subjects", response_model=SubjectListResponse)
def list_subjects():
    """
    列出已配置的学科。

    扫描 config/subjects/ 目录，返回所有已配置的学科列表。
    """
    from config.settings import SUBJECT_CONFIG_DIR

    subjects = []
    if SUBJECT_CONFIG_DIR.exists():
        for config_file in SUBJECT_CONFIG_DIR.glob("*.json"):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                subjects.append({
                    "subject": config.get("subject", config_file.stem),
                    "name": config.get("name", config_file.stem),
                    "description": config.get("description", ""),
                })
            except:
                pass

    return SubjectListResponse(subjects=subjects)


@app.get("/api/subjects/{subject}", response_model=SubjectConfig)
def get_subject_config(subject: str):
    """
    获取指定学科的配置详情。
    """
    config = SubjectAnalyzer.load_config(subject)
    if not config:
        raise HTTPException(status_code=404, detail=f"学科「{subject}」配置不存在")

    return SubjectConfig(
        subject=config.get("subject", subject),
        name=config.get("name", subject),
        description=config.get("description", ""),
        question_types=config.get("question_types", {}),
        difficulty_levels=config.get("difficulty_levels", {}),
        special_features=config.get("special_features", []),
    )


@app.post("/api/subjects/{subject}/analyze")
def analyze_subject_materials(
    subject: str,
    request: ImportRequest,
    background_tasks: BackgroundTasks = None,
):
    """
    分析文本材料并自动生成学科配置。

    上传材料后，系统会自动分析内容特征（题型、难度、公式密度等），
    生成学科配置文件并保存。
    """
    from core.chunking import DocumentChunker

    chunker = DocumentChunker()
    metadata = {"source": "api_analysis", "subject": subject}
    chunks = chunker.chunk(request.text, metadata)

    if not chunks:
        raise HTTPException(status_code=400, detail="无法从文本中提取有效内容")

    analyzer = SubjectAnalyzer()
    config = analyzer.analyze_materials(chunks, subject_name=subject)
    config_path = save_subject_config(config, subject_name=subject)

    return {
        "subject": subject,
        "config_path": str(config_path),
        "name": config.get("name", subject),
        "question_types": list(config.get("question_types", {}).keys()),
        "difficulty_levels": list(config.get("difficulty_levels", {}).keys()),
        "special_features": config.get("special_features", []),
        "analysis_basis": config.get("analysis_basis", {}),
    }


@app.get("/api/knowledge-base/{subject}/stats")
def knowledge_base_stats(subject: str):
    """
    获取知识库统计信息。
    """
    try:
        store = VectorStore(f"{subject}_v1")
        count = store.count()
        return {
            "subject": subject,
            "collection": f"{subject}_v1",
            "document_count": count,
            "status": "active" if count > 0 else "empty",
        }
    except Exception as e:
        return {
            "subject": subject,
            "collection": f"{subject}_v1",
            "document_count": 0,
            "status": f"error: {str(e)}",
        }


# ========== 题库管理 API ==========

@app.post("/api/quiz-bank/save")
def save_to_quiz_bank(request: QuizBankSaveRequest):
    """
    保存题目到题库。
    生成题目后，用户可以选择保留的题目加入题库。
    """
    ids = qb_batch_save(
        questions=[q.model_dump() for q in request.questions],
        subject=request.subject,
        topic=request.topic,
        is_approved=request.is_approved,
    )
    return {
        "saved": len(ids),
        "question_ids": ids,
        "message": f"成功保存 {len(ids)} 道题目到题库",
    }


@app.get("/api/quiz-bank/list", response_model=QuizBankListResponse)
def list_quiz_bank(
    subject: str = "generic",
    topic: str = None,
    is_approved: bool = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    查询题库中的题目。
    """
    questions = qb_list(
        subject=subject,
        topic=topic,
        is_approved=is_approved,
        limit=limit,
        offset=offset,
    )
    total = len(qb_list(subject=subject, topic=topic, is_approved=is_approved, limit=10000))

    return QuizBankListResponse(
        questions=[
            QuizBankQuestion(
                id=q["id"],
                type=q["type"],
                question=q["question"],
                options=q.get("options", []),
                answer=q["answer"],
                explanation=q.get("explanation", ""),
            )
            for q in questions
        ],
        total=total,
    )


@app.post("/api/quiz-bank/approve/{qid}")
def approve_quiz_bank_question(qid: str):
    """
    用户确认保留题目（将 is_approved 设为 1）。
    """
    success = qb_approve(qid)
    if not success:
        raise HTTPException(status_code=404, detail=f"题目 {qid} 不存在")
    return {"message": f"题目 {qid} 已确认保留", "approved": True}


@app.delete("/api/quiz-bank/{qid}")
def delete_quiz_bank_question(qid: str):
    """
    删除题库中的题目。
    """
    success = qb_delete(qid)
    if not success:
        raise HTTPException(status_code=404, detail=f"题目 {qid} 不存在")
    return {"message": f"题目 {qid} 已删除", "deleted": True}


@app.get("/api/quiz-bank/stats", response_model=QuizBankStatsResponse)
def quiz_bank_stats(subject: str = "generic"):
    """
    题库统计。
    """
    stats = qb_stats(subject=subject)
    return QuizBankStatsResponse(**stats)


# ========== 静态前端文件 ==========
# 如果 web 目录存在且包含 index.html，挂载静态文件服务
# 否则保留 root() 路由返回 API 信息
# 优先使用构建后的前端（web/dist/），否则回退到源码（web/）
WEB_DIR = PROJECT_ROOT / "web" / "dist"
INDEX_FILE = WEB_DIR / "index.html"
if not INDEX_FILE.exists():
    WEB_DIR = PROJECT_ROOT / "web"
    INDEX_FILE = WEB_DIR / "index.html"

if WEB_DIR.exists() and INDEX_FILE.exists():
    # 有前端文件，挂载静态文件服务到 /，index.html 作为默认页
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="static")
else:
    # 无前端文件，保留 API 根路由
    @app.get("/")
    def root():
        """根路径返回 API 信息"""
        return {
            "service": "LearnAnything API",
            "version": "1.0.0",
            "docs": "/docs",
            "note": "前端文件未部署，请访问 /docs 查看 API 文档",
            "endpoints": [
                "POST /api/ask",
                "POST /api/ask/stream",
                "POST /api/quiz",
                "POST /api/evaluate/start",
                "POST /api/evaluate/submit",
                "POST /api/import/text",
                "POST /api/import/file",
                "GET  /api/subjects",
                "GET  /api/subjects/{subject}",
                "POST /api/subjects/{subject}/analyze",
                "GET  /api/knowledge-base/{subject}/stats",
                "GET  /api/health",
            ],
        }


# ========== 启动入口 ==========

if __name__ == "__main__":
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
