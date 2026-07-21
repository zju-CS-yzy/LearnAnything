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
from typing import List, Dict, Any, Optional, Union
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
from core.subject_manager import (
    create_subject, list_subjects, get_subject, delete_subject,
    detect_subject, ensure_default_subjects, record_import,
)
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
from core.graph_store import GraphStore


# ========== Global GraphStore cache (avoid KuzuDB repeated connections / file locking) ==========
_graph_store_cache = {}  # subject -> GraphStore

def get_graph_store(subject: str) -> GraphStore:
    """Get or create shared GraphStore instance (P0-QUIZ-fix: avoid KuzuDB file locking)"""
    key = f"{subject}_v1"
    if key not in _graph_store_cache:
        _graph_store_cache[key] = GraphStore(key)
        print(f"[API] Created shared GraphStore for {key}")
    return _graph_store_cache[key]


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


# ========== 启动初始化 ==========

# 确保默认学科存在
ensure_default_subjects()


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
    media: Optional[List[Dict[str, Any]]] = None  # LA-IMG: 关联的媒体资源
    sources: Optional[List[Dict[str, Any]]] = None  # LA-047: 引用来源


class QuizRequest(BaseModel):
    """出题请求"""
    topic: str = Field(..., description="出题主题", min_length=1)
    subject: str = Field("generic", description="学科标识")
    count: int = Field(5, ge=1, le=20, description="题目数量")
    user_id: Optional[str] = Field(None, description="用户ID（用于P0模块能力画像和自适应出题）")


class QuizQuestion(BaseModel):
    """单道题目"""
    id: Union[int, str]
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
    user_id: Optional[str] = Field(None, description="用户ID（用于P0模块能力画像）")

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


# ========== 学科管理模型 ==========

class SubjectCreateRequest(BaseModel):
    """创建学科请求"""
    id: str = Field(..., description="学科标识（英文，如 ai_llm）")
    name: str = Field(..., description="学科名称（中文，如 AI大模型）")
    description: str = Field("", description="学科描述")
    keywords: List[str] = Field(default_factory=list, description="关键词列表，用于自动识别")


class SubjectItem(BaseModel):
    """学科条目"""
    id: str
    name: str
    description: str
    keywords: List[str]
    created_at: str
    document_count: int


class SubjectListResponse(BaseModel):
    """学科列表响应"""
    subjects: List[SubjectItem]


class SubjectDetectResponse(BaseModel):
    """学科识别响应"""
    query: str
    detected_subject: Optional[str]
    confidence: str  # high / medium / low / none


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
    id: Union[int, str]
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

    # LA-IMG: 提取 metadata 中的媒体资源
    # FIX-LA049: agent_result 在 result["result"] 中，而非 result["metadata"]
    agent_result = result.get("result", {})
    metadata = agent_result.get("metadata", {}) if isinstance(agent_result, dict) else {}
    media = metadata.get("media") if isinstance(metadata, dict) else None
    # LA-047: 提取引用来源
    sources = metadata.get("sources") if isinstance(metadata, dict) else None

    return AskResponse(
        question=request.query,
        answer=result.get("text", ""),
        intent=result.get("intent", {}),
        agent=result.get("agent", ""),
        duration_ms=result.get("monitoring", {}).get("total_duration_ms", 0),
        query_id=result.get("monitoring", {}).get("query_id", ""),
        media=media,
        sources=sources,
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
        # LA-IMG: 传递媒体资源到前端
        # FIX-LA049: 从 result["result"] 的 metadata 中提取 media
        agent_result = result.get("result", {})
        metadata = agent_result.get("metadata", {}) if isinstance(agent_result, dict) else {}
        media = metadata.get("media") if isinstance(metadata, dict) else None
        # LA-047: 传递引用来源
        sources = metadata.get("sources") if isinstance(metadata, dict) else None
        meta = json.dumps({
            "intent": intent,
            "agent": agent_name,
            "query_id": query_id,
            "question": request.query,
            "media": media,
            "sources": sources,
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
    Quiz API (P0-QUIZ-fix: use Coordinator + shared GraphStore).

    Routes through Coordinator to enable P0 graph-education pipeline:
    ConceptRetriever -> SubgraphBuilder -> ContextAssembler -> QuizAgent.
    """
    # P0-QUIZ-fix: use shared GraphStore to avoid KuzuDB file locking
    graph_store = get_graph_store(request.subject)

    coordinator = Coordinator(
        collection_name=f"{request.subject}_v1",
        top_k=5,
        graph_store=graph_store,  # shared GraphStore, avoids duplicate connections
    )

    result = coordinator.handle(
        query=f"give me {request.count} questions on {request.topic}",
        user_id=request.user_id,
    )

    # Coordinator returns {"result": {"questions": [...], ...}}
    agent_result = result.get("result", {})
    questions = agent_result.get("questions", [])

    # Convert to Pydantic model
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

    subject_config = agent_result.get("subject_config", {})
    return QuizResponse(
        topic=agent_result.get("topic", request.topic),
        questions=quiz_questions,
        subject_name=subject_config.get("name", "generic"),
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
            # P0-QUIZ-fix: use Coordinator + shared GraphStore
            graph_store = get_graph_store(request.subject)
            coordinator = Coordinator(
                collection_name=f"{request.subject}_v1",
                top_k=5,
                graph_store=graph_store,
            )
            result = coordinator.handle(
                query=f"evaluate my {request.topic} level",
                user_id=request.user_id,
            )
            agent_result = result.get("result", {})
            gen_questions = agent_result.get("questions", [])
        else:
            gen_questions = []

        questions = bank_questions + gen_questions
        # 重新编号
        for i, q in enumerate(questions):
            q["id"] = i + 1
        instructions = f"本次评测包含 {len(bank_questions)} 道题库题目和 {len(gen_questions)} 道生成题目。"

    else:
        # Default: generate new questions (P0-QUIZ-fix: use Coordinator + shared GraphStore)
        graph_store = get_graph_store(request.subject)
        coordinator = Coordinator(
            collection_name=f"{request.subject}_v1",
            top_k=5,
            graph_store=graph_store,
        )
        result = coordinator.handle(
            query=f"evaluate my {request.topic} level",
            user_id=request.user_id,
        )
        agent_result = result.get("result", {})

        questions = agent_result.get("questions", [])
        if not questions:
            raise HTTPException(status_code=400, detail="Cannot generate evaluation questions. Please verify knowledge base has materials.")

        subject_config = agent_result.get("subject_config", {})
        subject_name = subject_config.get("name", "generic")
        instructions = agent_result.get("text", "").split("\n\n")[0] if agent_result.get("text") else ""

    # 保存会话
    _eval_sessions[session_id] = {
        "questions": questions,
        "subject": request.subject,
        "topic": request.topic,
        "mode": request.mode,
        "created_at": time.time(),
    }
    print(f"[EvalStart] session={session_id} mode={request.mode} questions={len(questions)} sessions_count={len(_eval_sessions)}")

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
    print(f"[EvalSubmit] session_id={request.session_id} available_sessions={list(_eval_sessions.keys())}")
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

    # 同时写入 KùzuDB 图数据库
    from core.graph_store import GraphStore
    graph_store = GraphStore(f"{request.subject}_v1")
    graph_store.init_schema()
    graph_store.add_chunk_nodes(docs)
    graph_store.build_belongs_to_relations()
    graph_store.build_adjacent_relations()

    # 记录到学科管理
    record_import(request.subject, request.source_name, len(docs))

    return ImportResponse(
        subject=request.subject,
        chunks_added=len(docs),
        total_documents=total_docs,
        message=f"成功导入 {len(docs)} 个文本片段到「{request.subject}」知识库",
    )


@app.post("/api/import/file")
def import_file(
    subject: str = Form(..., description="学科标识"),
    files: List[UploadFile] = File(..., description="上传文件（支持 .txt, .md, .pdf, .png, .jpg），可多选"),
    background_tasks: BackgroundTasks = None,
):
    """
    上传文件导入知识库（支持批量）。

    支持格式：文本、Markdown、PDF（文字型/扫描件）、图片（OCR）。
    """
    import tempfile
    import traceback

    results = []
    total_chunks = 0
    total_docs = 0

    for file in files:
        print(f"[ImportFile] Starting upload: filename={file.filename}, subject={subject}")

        # 保存上传文件到临时位置
        suffix = Path(file.filename).suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = file.file.read()
            tmp.write(content)
            tmp_path = tmp.name
            print(f"[ImportFile] Saved to temp: {tmp_path}, size={len(content)} bytes")

        try:
            print(f"[ImportFile] Initializing DocumentProcessor...")
            processor = DocumentProcessor()
            print(f"[ImportFile] DocumentProcessor OK")

            print(f"[ImportFile] Initializing VectorStore({subject}_v1)...")
            store = VectorStore(f"{subject}_v1")
            print(f"[ImportFile] VectorStore OK, count={store.count()}")

            # 先保存原始文件到学科 raw 文件夹（获取 raw_path）
            print(f"[ImportFile] Saving raw file...")
            from core.subject_manager import save_raw_file
            raw_path = save_raw_file(subject, file.filename, content)
            print(f"[ImportFile] Raw file saved: {raw_path}")

            print(f"[ImportFile] Processing file...")
            chunks = processor.process_file(tmp_path, subject=subject, source_name=file.filename, raw_path=str(raw_path))
            print(f"[ImportFile] Processed, chunks={len(chunks)}")

            if chunks:
                print(f"[ImportFile] Adding documents to vector store...")
                store.add_documents(chunks)
                total_docs = store.count()
                print(f"[ImportFile] Added to vector store, total_docs={total_docs}")
                
                # 同时写入 KùzuDB 图数据库
                print(f"[ImportFile] Writing to KùzuDB...")
                from core.graph_store import GraphStore
                graph_store = GraphStore(f"{subject}_v1")
                graph_store.init_schema()
                graph_store.add_chunk_nodes(chunks)
                graph_store.build_belongs_to_relations()
                graph_store.build_adjacent_relations()
                print(f"[ImportFile] KùzuDB write complete")

                # 记录到学科管理
                record_import(subject, file.filename, str(raw_path), len(chunks))
                print(f"[ImportFile] Done successfully")

                results.append({
                    "filename": file.filename,
                    "raw_path": str(raw_path),
                    "chunks_added": len(chunks),
                    "success": True,
                    "message": f"成功导入，生成 {len(chunks)} 个知识片段",
                })
                total_chunks += len(chunks)
            else:
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "message": "文件处理失败，未提取到有效内容",
                })
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            print(f"[ImportFile] ERROR for {file.filename}: {error_msg}")
            traceback.print_exc()
            results.append({
                "filename": file.filename,
                "success": False,
                "message": f"文件处理失败: {error_msg}",
            })
        finally:
            # 清理临时文件
            try:
                Path(tmp_path).unlink()
            except:
                pass

    # 汇总结果
    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count

    return {
        "subject": subject,
        "total_files": len(files),
        "success_count": success_count,
        "fail_count": fail_count,
        "total_chunks_added": total_chunks,
        "total_documents": total_docs,
        "results": results,
        "message": f"批量导入完成：{success_count} 个成功，{fail_count} 个失败，共生成 {total_chunks} 个知识片段",
    }


# 旧的学科列表路由已替换为新的 subject_manager 路由（见下方学科管理 API 区域）


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
        # 动态计算原始文件数量
        from core.subject_manager import list_raw_files
        raw_files = list_raw_files(subject)
        return {
            "subject": subject,
            "collection": f"{subject}_v1",
            "document_count": count,
            "raw_files_count": len(raw_files),
            "status": "active" if count > 0 else "empty",
        }
    except Exception as e:
        return {
            "subject": subject,
            "collection": f"{subject}_v1",
            "document_count": 0,
            "status": f"error: {str(e)}",
        }


@app.get("/api/knowledge-base/{subject}/chunks")
def knowledge_base_chunks(subject: str, limit: int = 50, offset: int = 0):
    """
    获取知识库中的知识片段列表（用于可视化）。
    """
    try:
        store = VectorStore(f"{subject}_v1")
        chunks = store.list_all(limit=limit, offset=offset)
        return {
            "subject": subject,
            "collection": f"{subject}_v1",
            "total": store.count(),
            "count": len(chunks),
            "chunks": chunks,
        }
    except Exception as e:
        return {
            "subject": subject,
            "collection": f"{subject}_v1",
            "total": 0,
            "count": 0,
            "chunks": [],
            "error": str(e),
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


# ========== 学科管理 API ==========

@app.post("/api/subjects", response_model=SubjectItem)
def api_create_subject(request: SubjectCreateRequest):
    """
    创建新学科。
    """
    result = create_subject(
        id=request.id,
        name=request.name,
        description=request.description,
        keywords=request.keywords,
    )
    return result


@app.get("/api/subjects")
def api_list_subjects():
    """
    列出所有已创建的学科。
    """
    subjects = list_subjects()
    return {"subjects": subjects}


@app.get("/api/subjects/{subject_id}")
def api_get_subject(subject_id: str):
    """
    获取学科详情。
    """
    sub = get_subject(subject_id)
    if not sub:
        raise HTTPException(status_code=404, detail=f"学科「{subject_id}」不存在")
    return sub


@app.delete("/api/subjects/{subject_id}")
def api_delete_subject(subject_id: str):
    """
    删除学科（同时清空关联知识库）。
    """
    # 删除知识库
    try:
        from config.settings import VECTOR_DB_DIR
        db_path = VECTOR_DB_DIR / f"{subject_id}_v1.db"
        if db_path.exists():
            db_path.unlink()
    except Exception as e:
        print(f"[SubjectDelete] 删除知识库失败: {e}")

    success = delete_subject(subject_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"学科「{subject_id}」不存在")
    return {"message": f"学科「{subject_id}」已删除", "deleted": True}


@app.post("/api/subjects/detect", response_model=SubjectDetectResponse)
def api_detect_subject(query: str = Form(...)):
    """
    自动识别查询所属学科。
    """
    detected = detect_subject(query)
    confidence = "high" if detected else "none"
    return SubjectDetectResponse(
        query=query,
        detected_subject=detected,
        confidence=confidence,
    )



# ========== 知识图谱 API ==========

@app.post("/api/knowledge-graph/{subject}/build")
def build_knowledge_graph(subject: str, body: Dict[str, Any] = None):
    """
    构建知识图谱 — 从向量库读取 chunk，生成图数据库结构。

    支持通过 body 传入参数：
    - paradigm: 语义提取范式（"theory"/"engineering"/"hierarchical"），如传入则自动触发语义层构建
    - force_rebuild: 是否强制重建（默认 false）
    """
    from core.graph_builder import GraphBuilder

    body = body or {}
    paradigm = body.get("paradigm", "theory")
    force_rebuild = body.get("force_rebuild", False)

    try:
        # Phase 1: 结构层构建
        builder = GraphBuilder(f"{subject}_v1", paradigm=paradigm)
        result = builder.build_all(force_rebuild=force_rebuild)

        # Phase 2: 如果传入了 paradigm（非默认 theory 或明确请求），自动执行语义层
        semantic_result = None
        dedupe_result = None
        link_result = None
        if body.get("with_semantic", True):
            semantic_result = builder.extract_all_concepts()
            dedupe_result = builder.dedupe_concepts()
            # Phase 2.5: 构建语义连接
            link_result = builder.link_concepts(paradigm=paradigm)

        # Phase 2.6: 计算图中心性（PageRank）- 非阻塞
        try:
            from core.graph_store import GraphStore as _GS
            _store = _GS(f"{subject}_v1")
            _store.init_schema()
            _centrality_cache = _store.compute_and_cache_centrality()
            print(f"[build_knowledge_graph] P0-INT-5: PageRank 缓存已更新，{len(_centrality_cache)} 个节点")
        except Exception as e:
            print(f"[build_knowledge_graph] P0-INT-5: 中心性计算失败（非阻塞）: {e}")

        return {
            "subject": subject,
            "paradigm": paradigm,
            **result,
            "semantic": semantic_result,
            "dedupe": dedupe_result,
            "link": link_result,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"图谱构建失败: {str(e)}")


@app.get("/api/knowledge-graph/{subject}/stats")
def get_graph_stats(subject: str):
    """
    获取知识图谱统计信息。
    """
    from core.graph_store import GraphStore

    try:
        store = GraphStore(f"{subject}_v1")
        store.init_schema()
        stats = store.get_graph_stats()
        return {
            "subject": subject,
            **stats,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"统计失败: {str(e)}")


@app.get("/api/knowledge-graph/{subject}/nodes")
def list_graph_nodes(subject: str, limit: int = 5000):
    """
    获取图谱中的 Chunk 节点（用于前端全局浏览，排除 parent 节点）。
    P30-FIX: 默认 limit 从 500 增大到 5000，避免大文档 chunk 节点被截断
    """
    from core.graph_store import GraphStore

    # 限制最大返回数量，防止性能问题
    limit = max(1, min(limit, 2000))

    try:
        store = GraphStore(f"{subject}_v1")
        store.init_schema()
        conn = store._ensure_db()

        result = conn.execute(f"""
            MATCH (c:Chunk)
            WHERE c.chunk_type <> 'parent'
            RETURN c.chunk_id, c.heading_path, c.source, c.page_number, c.chunk_type, c.text,
                   c.image_path, c.thumbnail_path, c.width, c.height
            LIMIT {limit}
        """)

        nodes = []
        while result.has_next():
            row = result.get_next()
            node = {
                "id": row[0],
                "heading_path": row[1] or "",
                "source": row[2],
                "page_number": row[3],
                "chunk_type": row[4],
                "text": row[5] or "",
            }
            # LA-035: 图片字段（仅图片节点）
            # P30-FIX: 兼容 image_pseudo 类型（ImageConceptExtractor 创建的 pseudo chunk）
            if row[4] in ('image', 'image_pseudo', 'formula_pseudo'):
                node["image_path"] = row[6] or ""
                node["thumbnail_path"] = row[7] or ""
                node["width"] = row[8] or 0
                node["height"] = row[9] or 0
            nodes.append(node)

        count_result = conn.execute("MATCH (c:Chunk) WHERE c.chunk_type <> 'parent' RETURN COUNT(c) AS cnt")
        total = count_result.get_next()[0] if count_result.has_next() else 0

        return {
            "subject": subject,
            "total": total,
            "count": len(nodes),
            "nodes": nodes,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"节点查询失败: {str(e)}")


@app.get("/api/knowledge-graph/{subject}/edges")
def list_graph_edges(subject: str, limit: int = 5000):
    """
    获取 Chunk 节点之间的边（排除 parent 节点相关的边）。
    P30-FIX-2: limit 从 200 增大到 5000，避免大量 BELONGS_TO 边被截断
    """
    from core.graph_store import GraphStore

    # 限制最大返回数量，防止性能问题
    limit = max(1, min(limit, 5000))

    try:
        store = GraphStore(f"{subject}_v1")
        store.init_schema()
        conn = store._ensure_db()

        edges = []
        try:
            result = conn.execute(f"""
                MATCH (a:Chunk)-[r:BELONGS_TO]->(b:Chunk)
                WHERE a.chunk_type <> 'parent' AND b.chunk_type <> 'parent'
                RETURN a.chunk_id, b.chunk_id
                LIMIT {limit}
            """)
            while result.has_next():
                row = result.get_next()
                edges.append({
                    "source": row[0],
                    "target": row[1],
                    "type": "BELONGS_TO",
                })
        except Exception:
            pass

        try:
            result = conn.execute(f"""
                MATCH (a:Chunk)-[r:ADJACENT_TO]->(b:Chunk)
                WHERE a.chunk_type <> 'parent' AND b.chunk_type <> 'parent'
                RETURN a.chunk_id, b.chunk_id
                LIMIT {limit}
            """)
            while result.has_next():
                row = result.get_next()
                edges.append({
                    "source": row[0],
                    "target": row[1],
                    "type": "ADJACENT_TO",
                })
        except Exception:
            pass

        return {
            "subject": subject,
            "count": len(edges),
            "edges": edges,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"边查询失败: {str(e)}")


@app.get("/api/knowledge-graph/{subject}/subgraph/{chunk_id}")
def get_subgraph(subject: str, chunk_id: str, depth: int = 2):
    """
    获取以指定 chunk 为中心的子图。
    """
    from core.graph_store import GraphStore

    try:
        store = GraphStore(f"{subject}_v1")
        store.init_schema()
        subgraph = store.get_subgraph(chunk_id, depth=depth)
        return {
            "subject": subject,
            "center_chunk": chunk_id,
            "depth": depth,
            "node_count": len(subgraph["nodes"]),
            "edge_count": len(subgraph["edges"]),
            **subgraph,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"子图查询失败: {str(e)}")


# ==================== LA-035: 图片静态文件服务 ====================

@app.get("/api/images/{subject}/{filename}")
def get_image(subject: str, filename: str):
    """
    提供学科知识库中的图片文件访问。
    
    路径: /api/images/<subject>/<filename>
    实际文件: knowledge_base/<subject>_v1_images/<filename>
    """
    from config.settings import KNOWLEDGE_BASE_DIR
    
    # 安全检查：防止目录遍历
    safe_filename = Path(filename).name
    
    # 尝试 images 目录
    img_path = KNOWLEDGE_BASE_DIR / f"{subject}_v1_images" / safe_filename
    if img_path.exists():
        return FileResponse(str(img_path))
    
    # 尝试 thumbnails 目录
    thumb_path = KNOWLEDGE_BASE_DIR / f"{subject}_v1_thumbnails" / safe_filename
    if thumb_path.exists():
        return FileResponse(str(thumb_path))
    
    raise HTTPException(status_code=404, detail=f"图片不存在: {filename}")


# ========== 知识图谱 API (Phase 2: 语义层) ==========

@app.post("/api/knowledge-graph/{subject}/extract/{chunk_id}")
async def extract_chunk_concepts(subject: str, chunk_id: str, body: Dict[str, Any] = None):
    """
    对指定 chunk 进行语义提取，分析其内部概念结构。

    支持范式选择：theory / engineering / hierarchical
    """
    from core.graph_store import GraphStore
    from core.semantic_extractor import SemanticExtractor

    try:
        graph_store = GraphStore(f"{subject}_v1")
        graph_store.init_schema()
        conn = graph_store._ensure_db()
        safe_chunk_id = graph_store._escape_cypher_string(chunk_id)
        result = conn.execute(f"""
            MATCH (c:Chunk {{chunk_id: '{safe_chunk_id}'}})
            RETURN c.text
        """)
        if not result.has_next():
            raise HTTPException(status_code=404, detail=f"Chunk {chunk_id} 不存在")

        chunk_text = result.get_next()[0] or ""
        if not chunk_text.strip():
            raise HTTPException(status_code=400, detail=f"Chunk {chunk_id} 文本为空")

        paradigm = "theory"
        if body and isinstance(body, dict):
            paradigm = body.get("paradigm", "theory")
        extractor = SemanticExtractor(paradigm=paradigm)
        concepts = extractor.extract_concepts(chunk_text)

        for c in concepts:
            c["id"] = extractor.generate_concept_id(c["name"], chunk_id)

        added = graph_store.add_concepts(chunk_id, concepts)

        return {
            "subject": subject,
            "chunk_id": chunk_id,
            "paradigm": paradigm,
            "status": "success",
            "concepts_extracted": len(concepts),
            "concepts_added": added,
            "concepts": concepts,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"语义提取失败: {str(e)}")


@app.get("/api/knowledge-graph/{subject}/chunk/{chunk_id}/concepts")
def get_chunk_concepts(subject: str, chunk_id: str):
    """
    获取指定 chunk 已提取的概念列表。
    """
    from core.graph_store import GraphStore

    try:
        graph_store = GraphStore(f"{subject}_v1")
        graph_store.init_schema()
        concepts = graph_store.get_concepts_for_chunk(chunk_id)

        return {
            "subject": subject,
            "chunk_id": chunk_id,
            "concepts_count": len(concepts),
            "concepts": concepts,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取概念失败: {str(e)}")


def _get_chunk_meta(graph_store, chunk_id: str) -> dict:
    """
    查询 Chunk 节点的元数据，构建人类可读的来源引用。
    
    Returns:
        {"source": 文件名, "heading_path": 章节路径, "page_number": 页码}
        或 None（chunk 不存在）
    """
    try:
        conn = graph_store._ensure_db()
        result = conn.execute(f"""
            MATCH (ch:Chunk {{chunk_id: '{chunk_id}'}})
            RETURN ch.source, ch.heading_path, ch.page_number
        """)
        if result.has_next():
            row = result.get_next()
            return {
                "source": row[0] or "",
                "heading_path": row[1] or "",
                "page_number": int(row[2]) if row[2] is not None else 0,
            }
    except Exception:
        pass
    return None


@app.get("/api/knowledge-graph/{subject}/concepts")
def list_graph_concepts(subject: str, limit: int = 2000):
    """
    获取图谱中的所有概念节点。
    优先从 KùzuDB 读取（确保 ID 与 /concept-links 接口中的边源/目标一致），
    从 CSV 补充 description / parent_hint 等额外字段。
    """
    import csv
    from config.settings import KNOWLEDGE_BASE_DIR
    from core.graph_store import GraphStore

    try:
        # 1. 从 CSV 读取额外字段（description, parent_hint）
        csv_path = KNOWLEDGE_BASE_DIR / f"{subject}_v1_concepts.csv"
        csv_data = {}
        if csv_path.exists():
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    cid = row.get("id", "").strip()
                    if not cid:
                        continue
                    csv_data[cid] = {
                        "name": row.get("name", ""),
                        "type": row.get("concept_type", ""),
                        "description": row.get("description", ""),
                        "parent_hint": row.get("parent_hint", ""),
                        "source_chunks": row.get("source_chunks", ""),
                    }

        # 2. 从 KùzuDB 读取概念节点（确保 ID 与边一致）
        graph_store = GraphStore(f"{subject}_v1")
        graph_store.init_schema()
        db_nodes = graph_store.get_canonical_concepts(limit=limit)

        # 3. 合并：优先使用 KùzuDB 的 ID，从 CSV 补充额外字段
        concepts = []
        # 预加载 chunk 元数据缓存（避免重复查询）
        chunk_meta_cache = {}
        
        for node in db_nodes:
            db_id = node["id"]
            csv_info = csv_data.get(db_id, {})
            
            # 解析 source_chunks（KùzuDB 中是 JSON 字符串）
            source_chunks_raw = node.get("source_chunks", "") or csv_info.get("source_chunks", "")
            source_chunk_ids = []
            if source_chunks_raw:
                try:
                    parsed = json.loads(source_chunks_raw)
                    if isinstance(parsed, list):
                        source_chunk_ids = parsed
                except (json.JSONDecodeError, TypeError):
                    # 可能是逗号分隔的字符串
                    source_chunk_ids = [s.strip() for s in str(source_chunks_raw).split(",") if s.strip()]
            
            # 构建人类可读的 source_refs
            source_refs = []
            for chunk_id in source_chunk_ids:
                if chunk_id in chunk_meta_cache:
                    meta = chunk_meta_cache[chunk_id]
                else:
                    # 查询 Chunk 节点获取元数据
                    meta = _get_chunk_meta(graph_store, chunk_id)
                    chunk_meta_cache[chunk_id] = meta
                
                if meta:
                    ref_parts = []
                    if meta.get("source"):
                        ref_parts.append(meta["source"])
                    if meta.get("heading_path"):
                        ref_parts.append(meta["heading_path"])
                    if meta.get("page_number") and meta["page_number"] > 0:
                        ref_parts.append(f"第 {meta['page_number']} 页")
                    
                    if ref_parts:
                        source_refs.append(" | ".join(ref_parts))
                    else:
                        source_refs.append(chunk_id)  # fallback
                else:
                    source_refs.append(chunk_id)  # fallback
            
            concepts.append({
                "id": db_id,
                "name": node["name"] or csv_info.get("name", ""),
                "type": node["type"] or csv_info.get("type", ""),
                "description": node.get("description") or csv_info.get("description", ""),
                "parent_hint": csv_info.get("parent_hint", ""),
                "source_chunks": source_chunk_ids,
                "source_refs": source_refs,
                "media_refs": node.get("media_refs", []),
                "is_virtual": node.get("is_virtual", False),  # LA-046
            })

        # 4. 补充 CSV 中有但 KùzuDB 中没有的概念（孤立概念）
        db_ids = {n["id"] for n in db_nodes}
        for csv_id, csv_info in csv_data.items():
            if csv_id not in db_ids:
                concepts.append({
                    "id": csv_id,
                    "name": csv_info.get("name", ""),
                    "type": csv_info.get("type", ""),
                    "description": csv_info.get("description", ""),
                    "parent_hint": csv_info.get("parent_hint", ""),
                    "source_chunks": [],
                    "source_refs": [],
                    "media_refs": [],
                    "is_virtual": False,
                })

        return {
            "subject": subject,
            "count": len(concepts),
            "concepts": concepts,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取概念节点失败: {str(e)}")


@app.get("/api/knowledge-graph/{subject}/concept-links")
def list_concept_links(subject: str, limit: int = 500):
    """
    获取概念间的语义连接边（全局推断生成的 SOLUTION / DEPENDS_ON）。
    """
    from core.graph_store import GraphStore

    try:
        graph_store = GraphStore(f"{subject}_v1")
        graph_store.init_schema()
        edges = graph_store.get_concept_links(limit=limit)

        return {
            "subject": subject,
            "count": len(edges),
            "edges": edges,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取语义连接边失败: {str(e)}")


# ========== 批量语义提取 + 去重 ==========

@app.post("/api/knowledge-graph/{subject}/build/semantic")
async def build_semantic_layer(subject: str, body: Dict[str, Any] = None):
    """
    批量构建语义层 — 对所有 chunk 提取概念。
    """
    from core.graph_builder import GraphBuilder

    try:
        paradigm = "theory"
        if body and isinstance(body, dict):
            paradigm = body.get("paradigm", "theory")
        builder = GraphBuilder(f"{subject}_v1", paradigm=paradigm)
        result = builder.extract_all_concepts()
        return {
            "subject": subject,
            "paradigm": paradigm,
            "status": "success",
            **result,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"语义层构建失败: {str(e)}")


@app.post("/api/knowledge-graph/{subject}/build/link")
async def build_semantic_links(subject: str, body: Dict[str, Any] = None):
    """
    执行全局语义连接推断（在已有去重概念基础上）。
    """
    from core.graph_builder import GraphBuilder

    try:
        body = body or {}
        paradigm = body.get("paradigm", "engineering")
        builder = GraphBuilder(f"{subject}_v1", paradigm=paradigm)
        result = builder.link_concepts(paradigm=paradigm)
        return {
            "subject": subject,
            "paradigm": paradigm,
            **result,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"语义连接构建失败: {str(e)}")


@app.post("/api/knowledge-graph/{subject}/dedupe")
async def dedupe_concepts(subject: str):
    """
    对全局概念空间进行去重。
    """
    from core.graph_builder import GraphBuilder

    try:
        builder = GraphBuilder(f"{subject}_v1")
        result = builder.dedupe_concepts()
        return {
            "subject": subject,
            **result,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"概念去重失败: {str(e)}")


# ========== 范式管理 API ==========

@app.get("/api/knowledge-graph/paradigms")
def list_paradigms():
    """
    获取所有可用的分解范式。
    """
    from core.semantic_extractor import get_paradigm_names

    paradigms = get_paradigm_names()
    return {
        "paradigms": [
            {"id": p[0], "name": p[1], "description": p[2]}
            for p in paradigms
        ]
    }


@app.get("/api/subjects/{subject_id}/raw-files")
def api_list_raw_files(subject_id: str):
    """
    列出学科的原始资料文件。
    """
    from core.subject_manager import list_raw_files, get_subject_dir
    subj = get_subject(subject_id)
    if not subj:
        raise HTTPException(status_code=404, detail=f"学科「{subject_id}」不存在")
    files = list_raw_files(subject_id)
    return {
        "subject": subject_id,
        "files": files,
        "count": len(files),
    }


@app.get("/api/subjects/{subject_id}/meta")
def api_get_subject_meta(subject_id: str):
    """
    获取学科的完整元数据（含原始文件列表）。
    """
    from core.subject_manager import get_subject_meta
    meta = get_subject_meta(subject_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"学科「{subject_id}」不存在")
    return meta


# ========== LA-035: 媒体文件静态服务 ==========

@app.get("/api/media/{path:path}")
def serve_media(path: str):
    """
    提供知识库中的图片等媒体文件的静态访问。
    
    路径中的正斜杠会被还原为系统路径分隔符，
    确保 Windows 路径也能正确解析。
    """
    from urllib.parse import unquote
    import os
    from config.settings import KNOWLEDGE_BASE_DIR
    
    # 解码 URL 编码
    decoded_path = unquote(path)
    
    # 替换 URL 正斜杠为系统路径分隔符
    normalized_path = decoded_path.replace('/', os.sep)
    
    # 构建完整路径
    full_path = KNOWLEDGE_BASE_DIR / normalized_path
    
    # 安全检查：确保路径在知识库目录内（防止目录遍历攻击）
    try:
        full_path = full_path.resolve()
        kb_root = KNOWLEDGE_BASE_DIR.resolve()
        if not str(full_path).startswith(str(kb_root)):
            raise HTTPException(status_code=403, detail="Forbidden: path outside knowledge base")
    except Exception:
        raise HTTPException(status_code=403, detail="Forbidden: invalid path")
    
    if full_path.exists() and full_path.is_file():
        return FileResponse(full_path)
    
    raise HTTPException(status_code=404, detail=f"File not found: {path}")


# ========== 静态前端文件 ==========
# 如果 web 目录存在且包含 index.html，挂载静态文件服务
# 否则保留 root() 路由返回 API 信息
# 优先使用构建后的前端（web/dist/），否则回退到源码（web/）
WEB_DIR = PROJECT_ROOT / "web" / "dist"
INDEX_FILE = WEB_DIR / "dist" / "index.html"
if not INDEX_FILE.exists():
    INDEX_FILE = WEB_DIR / "index.html"

if INDEX_FILE.exists():
    # 有前端文件，挂载静态文件服务到 /，index.html 作为默认页
    app.mount("/", StaticFiles(directory=str(INDEX_FILE.parent), html=True), name="static")
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
