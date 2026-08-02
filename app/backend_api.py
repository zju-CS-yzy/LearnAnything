#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# LA-040-P2-DIAG: 诊断当前加载的文件路径
import os
import sys
print(f"[DIAG] Loading backend_api.py from: {os.path.abspath(__file__)}")
# LA-DEPLOY-FIX: 在 PyInstaller 打包环境下，__file__ 可能指向不存在的路径
# 使用 getattr 安全获取 mtime，失败时跳过
try:
    print(f"[DIAG] File mtime: {os.path.getmtime(__file__)}")
except (OSError, FileNotFoundError):
    print(f"[DIAG] File mtime: N/A (frozen environment)")

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
import sqlite3  # LA-044: 对话上下文会话列表查询

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks, Header
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
from core.user_manager import get_user_manager  # LA-052: 用户管理
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
from core.dialog_context import DialogContextManager
from core.permission_manager import PermissionManager, Role  # LA-051: 权限管理
from app.setup_api import router as setup_router, is_first_run


# ========== Global instances ==========
_graph_store_cache = {}  # subject -> GraphStore
_dialog_manager = DialogContextManager()

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

# LA-040-P2-WORKAROUND: 直接调用端点函数，绕过 FastAPI 路由调度 bug
# 原因：@app.get 装饰器注册的路由在运行时无法被 Starlette Router 正确匹配（返回 Match.FULL 但请求 404）
@app.middleware("http")
async def visualization_workaround(request, call_next):
    path = request.url.path
    method = request.method
    
    if path == "/api/visualization/progress" and method == "GET":
        from fastapi.responses import JSONResponse
        try:
            result = get_progress_chart(
                user_id=request.query_params.get("user_id", "default"),
                subject=request.query_params.get("subject", "generic"),
                days=int(request.query_params.get("days", 30)),
                x_user_id=request.headers.get("X-User-ID")
            )
            return JSONResponse(content=result.dict())
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    if path == "/api/visualization/wrong-answers" and method == "GET":
        from fastapi.responses import JSONResponse
        try:
            result = get_wrong_answers(
                user_id=request.query_params.get("user_id", "default"),
                subject=request.query_params.get("subject", "generic"),
                concept=request.query_params.get("concept"),
                mastered=request.query_params.get("mastered"),
                sort=request.query_params.get("sort", "last_wrong_desc"),
                limit=int(request.query_params.get("limit", 50)),
                offset=int(request.query_params.get("offset", 0)),
                x_user_id=request.headers.get("X-User-ID")
            )
            return JSONResponse(content=result.dict())
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    return await call_next(request)

# LA-DEPLOY: 注册配置向导路由
app.include_router(setup_router)


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
    user_theta: Optional[float] = Field(None, ge=0.0, le=1.0, description="用户能力水平 0.0~1.0（可选，用于个性化讲解深度）")


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
    current_topic: Optional[str] = None  # LA-044: 当前话题


# LA-044-#3: 用户状态 API 模型
class UserStateUpdateRequest(BaseModel):
    """用户状态更新请求"""
    user_id: str = Field(..., description="用户ID")
    subject: str = Field("generic", description="学科标识")
    global_theta: Optional[float] = Field(None, ge=0.0, le=1.0, description="全局能力值 0.0~1.0")
    weak_areas: Optional[List[str]] = Field(None, description="薄弱点列表")


class UserStateResponse(BaseModel):
    """用户状态响应"""
    user_id: str
    subject_id: str
    profile: Dict[str, Any]
    concept_states: List[Dict[str, Any]]
    stats: Dict[str, Any]


# ========== LA-052: 认证相关 Pydantic 模型 ==========

class RegisterRequest(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, description="密码")
    display_name: Optional[str] = Field(None, description="显示昵称")


class LoginRequest(BaseModel):
    """用户登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class AuthResponse(BaseModel):
    """认证响应"""
    success: bool
    user_id: str
    username: str
    display_name: str
    token: str
    message: str


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
    bloom_level: Optional[str] = None  # LA-040-P3: Bloom 认知层次


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
    document_count: int = 0  # LA-056: 创建时可能没有此字段，设默认值
    # LA-051: 权限相关字段
    owner_id: str = "system"
    visibility: str = "public"
    updated_at: str = ""
    # LA-051: 前端权限显示
    role: str = ""  # owner / maintainer / contributor / reader
    can_write: bool = False
    can_manage: bool = False
    can_review: bool = False


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
    bloom_level: Optional[str] = None  # LA-040-P3: Bloom 认知层次


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


# ========== LA-052: 统一身份验证 ==========

def get_current_user_id(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
) -> str:
    """
    LA-052 + LA-052-A: 统一身份验证

    优先级：
    1. Authorization: Bearer <token> → 验证 token 获取 user_id
    2. X-User-ID Header → 向后兼容
    3. 默认 default（本地用户，无需密码）

    Returns:
        user_id 字符串
    """
    # 优先验证 token
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        try:
            um = get_user_manager()
            user_id = um.verify_token(token)
            if user_id:
                return user_id
        except Exception as e:
            print(f"[Auth] Token 验证失败: {e}")

    # 回退到 X-User-ID
    if x_user_id:
        return x_user_id

    # LA-052-A: 默认 default 用户（替代 anonymous）
    return "default"
    if x_user_id:
        return x_user_id

    return "default"


# 便捷函数：供现有端点快速获取 effective_user_id
def _get_effective_user_id(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
) -> str:
    """LA-052-A: 获取有效用户 ID（token 优先，默认 default）"""
    return get_current_user_id(x_user_id, authorization)


@app.get("/api/health", response_model=HealthResponse)
def health_check():
    """健康检查接口"""
    return HealthResponse(
        status="ok",
        service="learnanything-backend",
        version="1.0.0",
        uptime_seconds=round(time.time() - _start_time, 1),
    )


# ========== LA-052: 认证 API ==========

@app.post("/api/auth/register", response_model=AuthResponse)
def auth_register(request: RegisterRequest):
    """
    LA-052: 用户注册

    创建新用户并返回认证 token。
    """
    um = get_user_manager()
    try:
        user = um.create_user(
            username=request.username,
            password=request.password,
            display_name=request.display_name,
        )
        token = um.generate_token(user["user_id"])
        return AuthResponse(
            success=True,
            user_id=user["user_id"],
            username=user["username"],
            display_name=user["display_name"],
            token=token,
            message="注册成功",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/auth/login", response_model=AuthResponse)
def auth_login(request: LoginRequest):
    """
    LA-052: 用户登录

    验证用户名密码，成功返回认证 token。
    """
    um = get_user_manager()
    user = um.verify_password(request.username, request.password)
    if not user:
        # 延迟响应（防暴力破解）
        import time
        time.sleep(1)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = um.generate_token(user["user_id"])
    return AuthResponse(
        success=True,
        user_id=user["user_id"],
        username=user["username"],
        display_name=user["display_name"] or user["username"],
        token=token,
        message="登录成功",
    )


@app.post("/api/auth/logout")
def auth_logout(authorization: Optional[str] = Header(None)):
    """
    LA-052: 用户登出

    注销当前 token。
    """
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        um = get_user_manager()
        um.revoke_token(token)
    return {"success": True, "message": "已登出"}


@app.get("/api/auth/me")
def auth_me(authorization: Optional[str] = Header(None)):
    """
    LA-052: 获取当前登录用户信息

    需要 Authorization: Bearer <token> Header。
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证 token")

    token = authorization[7:]
    um = get_user_manager()
    user_id = um.verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")

    user = um.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return {
        "user_id": user_id,
        "username": user["username"],
        "display_name": user.get("display_name", user["username"]),
    }


@app.post("/api/ask", response_model=AskResponse)
def ask_question(
    request: AskRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    智能问答接口（非流式）。
    LA-044: 当 user_theta 未传入时，自动从 UserStateStore 读取用户的当前 theta。
    LA-051: 支持权限感知的跨用户数据访问。
    """
    # LA-051: 获取真实用户身份
    effective_user_id = get_current_user_id(x_user_id, authorization)
    # LA-051-SESSION: header 无有效身份时，回退到请求体中的 user_id
    if effective_user_id in ("anonymous", "default") and request.user_id and request.user_id not in ("anonymous", "default"):
        effective_user_id = request.user_id
    
    # LA-051: 权限感知的 store 获取
    subject = request.subject
    graph_store = _get_accessible_graph_store(subject, effective_user_id)
    vector_store = _get_accessible_vector_store(subject, effective_user_id)
    
    # LA-044-FIX: 如果请求中未传 user_theta，从 UserStateStore 读取
    user_theta = request.user_theta
    if user_theta is None and effective_user_id not in ("anonymous", "default"):
        try:
            store = _get_isolated_state_store(effective_user_id)
            subject_id = f"{subject}_v1"
            state = store.get_full_user_state(effective_user_id, subject_id)
            user_theta = state.get("profile", {}).get("global_theta")
            print(f"[LA-044-FIX] /api/ask: 从 UserStateStore 读取 theta={user_theta} | user={effective_user_id}, subject={subject_id}")
        except Exception as e:
            print(f"[LA-044-FIX] /api/ask: 读取 UserStateStore 失败: {e}")
            user_theta = None

    print(f"[API] /api/ask called: query={request.query}, subject={subject}, user={effective_user_id}, user_theta={user_theta}")
    coordinator = Coordinator(
        collection_name=f"{subject}_v1",
        top_k=5,
        user_theta=user_theta,
        graph_store=graph_store,
        vector_store=vector_store,
    )
    # LA-050-HISTORY-FIX: 注入用户隔离的 DialogContextManager
    if effective_user_id not in ("anonymous", "default"):
        from core.user_context import UserContext
        ctx = UserContext(effective_user_id)
        coordinator._dialog_manager = ctx.dialog_manager
        print(f"[LA-050-HISTORY-FIX] ask_question: 注入用户隔离 DialogContextManager | user={effective_user_id}, db={ctx.dialog_manager.db_path}")
    result = coordinator.handle(
        query=request.query,
        user_id=effective_user_id,
        session_id=request.session_id,
        user_theta=user_theta,
    )
    print(f"[API] /api/ask returning answer length={len(result.get('text', ''))}")

    # LA-044-#3: 对话结束时自动保存用户状态
    _save_user_state_after_dialog(effective_user_id, request, result)

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
        current_topic=_get_session_topic(request.session_id),
    )


@app.post("/api/ask/stream")
def ask_stream(
    request: AskRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
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
        # LA-044-FIX: 如果请求中未传 user_theta，从 UserStateStore 读取
        # LA-051-SESSION: 从 header 获取真实身份，不依赖请求体中的 user_id
        effective_user_id = get_current_user_id(x_user_id, authorization)
        user_theta = request.user_theta
        if user_theta is None and effective_user_id not in ("anonymous", "default"):
            try:
                store = _get_isolated_state_store(effective_user_id)
                subject_id = f"{request.subject}_v1"
                state = store.get_full_user_state(effective_user_id, subject_id)
                user_theta = state.get("profile", {}).get("global_theta")
                print(f"[LA-044-FIX] /api/ask/stream: 从 UserStateStore 读取 theta={user_theta} | user={effective_user_id}, subject={subject_id}")
            except Exception as e:
                print(f"[LA-044-FIX] /api/ask/stream: 读取 UserStateStore 失败: {e}")
                user_theta = None

        # 1. 同步检索和路由（coordinator.handle 内部 TutorAgent 会调用一次 LLM）
        # LA-051: 权限感知的 store 获取
        subject = request.subject
        graph_store = _get_accessible_graph_store(subject, effective_user_id)
        vector_store = _get_accessible_vector_store(subject, effective_user_id)
        
        coordinator = Coordinator(
            collection_name=f"{subject}_v1",
            top_k=5,
            user_theta=user_theta,
            graph_store=graph_store,
            vector_store=vector_store,
        )
        # LA-050-HISTORY-FIX: 注入用户隔离的 DialogContextManager
        # 确保对话消息保存到用户隔离数据库，而非共享数据库
        # LA-051-SESSION: 使用已验证的 effective_user_id（已在上方从 header 获取）
        if effective_user_id not in ("anonymous", "default"):
            from core.user_context import UserContext
            ctx = UserContext(effective_user_id)
            coordinator._dialog_manager = ctx.dialog_manager
            print(f"[LA-050-HISTORY-FIX] ask_stream: 注入用户隔离 DialogContextManager | user={effective_user_id}, db={ctx.dialog_manager.db_path}")
        result = coordinator.handle(
            query=request.query,
            user_id=effective_user_id,
            session_id=request.session_id,
            user_theta=request.user_theta,
        )

        intent = result.get("intent", {})
        agent_name = result.get("agent", "")
        query_id = result.get("monitoring", {}).get("query_id", "")
        answer_text = result.get("text", "")
        # LA-050-HISTORY-FIX: 获取后端生成的 session_id，返回给前端
        response_session_id = result.get("session_id", request.session_id)

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
            "current_topic": _get_session_topic(response_session_id),
            # LA-050-HISTORY-FIX: 返回后端 session_id，前端需要用它加载历史
            "session_id": response_session_id,
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
def generate_quiz(
    request: QuizRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
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
    # LA-050-HISTORY-FIX: 注入用户隔离的 DialogContextManager
    # LA-050-HISTORY-FIX: 注入用户隔离的 DialogContextManager
    # LA-051-SESSION: 从 header 获取真实身份
    effective_user_id = get_current_user_id(x_user_id, authorization)
    if effective_user_id not in ("anonymous", "default"):
        from core.user_context import UserContext
        ctx = UserContext(effective_user_id)
        coordinator._dialog_manager = ctx.dialog_manager
        print(f"[LA-050-HISTORY-FIX] generate_quiz: 注入用户隔离 DialogContextManager | user={effective_user_id}")

    result = coordinator.handle(
        query=f"give me {request.count} questions on {request.topic}",
        user_id=effective_user_id,
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
            bloom_level=q.get("bloom_level"),  # LA-040-P3: 传递 Bloom 层次
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
def start_evaluation(
    request: EvaluateStartRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    开始评测 — 生成题目或从题库抽题并创建会话。

    mode: generate(生成新题) / bank(从题库抽题) / mixed(混合)
    返回 session_id 和题目列表，前端保存 session_id 供后续提交答案。
    """
    session_id = str(uuid.uuid4())

    # LA-051-SESSION: 在函数开头统一获取真实用户身份
    effective_user_id = get_current_user_id(x_user_id, authorization)

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
            # LA-050-HISTORY-FIX: 注入用户隔离的 DialogContextManager
            # LA-050-HISTORY-FIX: 注入用户隔离 DialogContextManager
            # LA-051-SESSION: 使用函数开头统一获取的 effective_user_id
            if effective_user_id not in ("anonymous", "default"):
                from core.user_context import UserContext
                ctx = UserContext(effective_user_id)
                coordinator._dialog_manager = ctx.dialog_manager
                print(f"[LA-050-HISTORY-FIX] evaluate_start(mixed): 注入用户隔离 DialogContextManager | user={effective_user_id}")
            result = coordinator.handle(
                query=f"evaluate my {request.topic} level",
                user_id=effective_user_id,
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
        # LA-050-HISTORY-FIX: 注入用户隔离的 DialogContextManager
        # LA-050-HISTORY-FIX: 注入用户隔离 DialogContextManager
        # LA-051-SESSION: 使用函数开头统一获取的 effective_user_id
        if effective_user_id not in ("anonymous", "default"):
            from core.user_context import UserContext
            ctx = UserContext(effective_user_id)
            coordinator._dialog_manager = ctx.dialog_manager
            print(f"[LA-050-HISTORY-FIX] evaluate_start(generate): 注入用户隔离 DialogContextManager | user={effective_user_id}")
        result = coordinator.handle(
            query=f"evaluate my {request.topic} level",
            user_id=effective_user_id,
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
        "user_id": request.user_id or "default",  # LA-040-P2: 保存 user_id 用于历史记录
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
            bloom_level=q.get("bloom_level"),  # LA-040-P3: 传递 Bloom 层次
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

    # LA-040-P2: 写入评测历史 + 错题本
    _save_evaluation_history(request.session_id, session, report)

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
            bloom_level=d.get("bloom_level"),  # LA-040-P3: 传递 Bloom 层次
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


def _save_evaluation_history(eval_session_id: str, session: Dict, report: Dict):
    """
    LA-040-P2: 评测提交后自动保存历史记录和错题。
    LA-050-Phase4: 使用用户隔离的 state_store 路径。

    写入两张表：
    1. evaluation_history — 本次评测的整体结果
    2. wrong_answers — 答错的题目（去重更新 wrong_count）
    """
    import sqlite3
    from datetime import datetime

    now = datetime.now().isoformat()
    user_id = session.get("user_id", "anonymous")
    subject_id = f"{session['subject']}_v1"

    # LA-050-Phase4: 使用用户隔离的 state_store 路径
    store = _get_isolated_state_store(user_id)
    db_path = store.db_path

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 1. 写入 evaluation_history
        history_id = str(uuid.uuid4())
        weak_areas = json.dumps(report.get("weak_areas", []), ensure_ascii=False)
        strong_areas = json.dumps(report.get("strong_areas", []), ensure_ascii=False)

        cursor.execute("""
            INSERT INTO evaluation_history
            (history_id, user_id, subject_id, eval_session_id, topic, theta,
             total_score, max_score, correct_count, total_questions, accuracy,
             weak_areas, strong_areas, evaluated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            history_id, user_id, subject_id, eval_session_id,
            session.get("topic", ""),
            report.get("theta", 0.0),
            report.get("total_score", 0),
            report.get("max_score", 0),
            report.get("correct_count", 0),
            report.get("total_questions", 0),
            report.get("percentage", 0.0),
            weak_areas, strong_areas, now
        ))
        print(f"[EvalSubmit-P2] 评测历史已保存: history_id={history_id[:8]}..., accuracy={report.get('percentage', 0):.1f}%")

        # 2. 写入 wrong_answers（答错的题目）
        wrong_count = 0
        for detail in report.get("details", []):
            if detail.get("is_correct", True):
                continue  # 答对的跳过

            wrong_count += 1
            qid = str(detail.get("id", "0"))
            question_text = detail.get("question", "")
            qtype = detail.get("type", "")
            user_ans = detail.get("user_answer", "")
            correct_ans = detail.get("correct_answer", "")
            explanation = detail.get("feedback", "")
            bloom_level = detail.get("bloom_level", "")  # LA-040-P3: 获取 Bloom 层次

            # 尝试从题目中解析概念名称（从 question_text 中提取核心名词，简化处理）
            concept_name = ""
            # 如果题目文本包含书名号或引号，提取为概念名
            import re
            m = re.search(r'[《"]([^》"]+)[》"]', question_text)
            if m:
                concept_name = m.group(1)
            else:
                # 取前 10 个字符作为概念名回退
                concept_name = question_text[:10] if len(question_text) <= 20 else question_text[:10] + "..."

            # 检查是否已有记录（同一题多次错）
            cursor.execute("""
                SELECT wrong_id, wrong_count FROM wrong_answers
                WHERE user_id = ? AND subject_id = ? AND question_id = ?
            """, (user_id, subject_id, qid))
            existing = cursor.fetchone()

            if existing:
                # 更新：wrong_count + 1，更新 last_wrong_at
                cursor.execute("""
                    UPDATE wrong_answers
                    SET wrong_count = wrong_count + 1,
                        last_wrong_at = ?,
                        user_answer = ?,
                        bloom_level = COALESCE(?, bloom_level)
                    WHERE wrong_id = ?
                """, (now, user_ans, bloom_level or None, existing[0]))
            else:
                # 新建
                wrong_id = str(uuid.uuid4())
                cursor.execute("""
                    INSERT INTO wrong_answers
                    (wrong_id, user_id, subject_id, question_id, question_text,
                     question_type, user_answer, correct_answer, explanation,
                     concept_name, bloom_level, wrong_count, first_wrong_at, last_wrong_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    wrong_id, user_id, subject_id, qid, question_text,
                    qtype, user_ans, correct_ans, explanation,
                    concept_name, bloom_level or None, 1, now, now
                ))

        conn.commit()
        print(f"[EvalSubmit-P2] 错题本已更新: {wrong_count} 道错题")

    except Exception as e:
        print(f"[EvalSubmit-P2] 保存评测历史/错题失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'conn' in locals():
            conn.close()


# LA-040-P2: 评测历史读取 API
class EvalHistoryItem(BaseModel):
    """评测历史条目"""
    history_id: str
    topic: str
    theta: float
    total_score: int
    max_score: int
    correct_count: int
    total_questions: int
    accuracy: float
    weak_areas: List[str]
    strong_areas: List[str]
    evaluated_at: str


class EvalHistoryResponse(BaseModel):
    """评测历史列表响应"""
    user_id: str
    subject: str
    total: int
    items: List[EvalHistoryItem]


@app.get("/api/evaluation/history", response_model=EvalHistoryResponse)
def get_evaluation_history(
    user_id: str = "default",
    subject: str = "generic",
    limit: int = 50,
    offset: int = 0,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    LA-040-P2: 获取用户的评测历史列表。
    LA-050-Phase4: 支持 X-User-ID Header 实现用户隔离。
    """
    effective_user_id = x_user_id or user_id or "default"
    # LA-050-Phase4: 使用用户隔离的 state_store 路径
    store = _get_isolated_state_store(effective_user_id)
    db_path = store.db_path
    subject_id = f"{subject}_v1"

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 查询总数
        cursor.execute("""
            SELECT COUNT(*) FROM evaluation_history
            WHERE user_id = ? AND subject_id = ?
        """, (effective_user_id, subject_id))
        total = cursor.fetchone()[0]

        # 查询数据
        cursor.execute("""
            SELECT history_id, topic, theta, total_score, max_score,
                   correct_count, total_questions, accuracy,
                   weak_areas, strong_areas, evaluated_at
            FROM evaluation_history
            WHERE user_id = ? AND subject_id = ?
            ORDER BY evaluated_at DESC
            LIMIT ? OFFSET ?
        """, (effective_user_id, subject_id, limit, offset))
        rows = cursor.fetchall()
        conn.close()

        items = []
        for row in rows:
            weak_areas = []
            strong_areas = []
            try:
                if row[8]:
                    weak_areas = json.loads(row[8])
            except:
                pass
            try:
                if row[9]:
                    strong_areas = json.loads(row[9])
            except:
                pass

            # LA-040-P2-FIX: accuracy 在数据库中存储的是百分比值（如 46.0 = 46%）
            # 需要转换为小数（0-1 范围）供前端统一显示
            raw_accuracy = row[7] or 0.0
            if raw_accuracy > 1:
                accuracy = round(raw_accuracy / 100, 3)
            else:
                accuracy = round(raw_accuracy, 3)

            items.append(EvalHistoryItem(
                history_id=row[0],
                topic=row[1] or "",
                theta=round(row[2] or 0.0, 3),
                total_score=row[3] or 0,
                max_score=row[4] or 0,
                correct_count=row[5] or 0,
                total_questions=row[6] or 0,
                accuracy=accuracy,
                weak_areas=weak_areas,
                strong_areas=strong_areas,
                evaluated_at=row[10] or "",
            ))

        print(f"[API] LA-040-P2: GET /api/evaluation/history | user={effective_user_id}, subject={subject}, returned={len(items)}/{total}")

        return EvalHistoryResponse(
            user_id=effective_user_id,
            subject=subject,
            total=total,
            items=items
        )

    except Exception as e:
        print(f"[API] LA-040-P2: 获取评测历史失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取评测历史失败: {str(e)}")


@app.post("/api/import/text", response_model=ImportResponse)
def import_text(
    request: ImportRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    导入文本材料到知识库。
    LA-050-Phase5: 支持 X-User-ID Header，使用用户隔离的知识库。
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)

    # LA-050-Phase5: 使用用户隔离的知识库
    if effective_user_id != "default":
        ctx = _get_user_context_from_header(effective_user_id)
        store = ctx.get_user_vector_store(request.subject)
        graph_store = ctx.get_user_graph_store(request.subject)
        subject_mgr = ctx.subject_manager
    else:
        # 向后兼容：anonymous 用户使用共享路径
        store = VectorStore(f"{request.subject}_v1")
        from core.graph_store import GraphStore
        graph_store = GraphStore(f"{request.subject}_v1")
        from core.subject_manager import record_import as _record_import
        subject_mgr = None

    processor = DocumentProcessor()

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
    graph_store.init_schema()
    graph_store.add_chunk_nodes(docs)
    graph_store.build_belongs_to_relations()
    graph_store.build_adjacent_relations()

    # 记录到学科管理
    if subject_mgr:
        subject_mgr.record_import(request.subject, request.source_name, chunk_count=len(docs))
    else:
        from core.subject_manager import record_import as _record_import
        _record_import(request.subject, request.source_name, len(docs))

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
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    上传文件导入知识库（支持批量）。
    LA-051: 仅可写用户(owner/maintainer)可直接导入。contributor 需通过审批队列（Task 4）。

    支持格式：文本、Markdown、PDF（文字型/扫描件）、图片（OCR）。
    """
    import tempfile
    import traceback

    effective_user_id = get_current_user_id(x_user_id, authorization)

    # LA-051: 权限检查 — 添加诊断日志
    print(f"[ImportFile-DIAG] user_id={effective_user_id}, subject={subject}")
    sub = _get_subject_anywhere(subject, effective_user_id)
    print(f"[ImportFile-DIAG] sub={sub}")
    if not sub:
        raise HTTPException(status_code=404, detail=f"学科「{subject}」不存在")

    owner_id = sub.get("owner_id", "system")
    pm = PermissionManager()
    user_role = pm.get_user_role(effective_user_id, subject, owner_id, sub.get("visibility"))
    print(f"[ImportFile-DIAG] owner_id={owner_id}, role={user_role}")

    # contributor: 返回提示，引导使用审批流程（Task 4）
    if pm.can_contribute(effective_user_id, subject, owner_id) and not pm.can_write(effective_user_id, subject, owner_id):
        raise HTTPException(
            status_code=403,
            detail="您当前是贡献者(contributor)，请使用变更提交功能上传文件（审批后自动导入）"
        )

    if not pm.can_write(effective_user_id, subject, owner_id):
        print(f"[ImportFile-DIAG] can_write=False, raising 403")
        raise HTTPException(status_code=403, detail="您没有权限向此学科导入内容")
    print(f"[ImportFile-DIAG] can_write=True, proceeding")

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

            # LA-050-Phase5 + LA-051: 使用用户隔离的知识库
            if effective_user_id != "default":
                ctx = _get_user_context_from_header(effective_user_id)
                store = ctx.get_user_vector_store(subject)
                graph_store = ctx.get_user_graph_store(subject)
                subject_mgr = ctx.subject_manager
            else:
                store = VectorStore(f"{subject}_v1")
                graph_store = None
                subject_mgr = None
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
                if graph_store is None:
                    from core.graph_store import GraphStore
                    graph_store = GraphStore(f"{subject}_v1")
                graph_store.init_schema()
                graph_store.add_chunk_nodes(chunks)
                graph_store.build_belongs_to_relations()
                graph_store.build_adjacent_relations()
                print(f"[ImportFile] KùzuDB write complete")

                # 记录到学科管理
                if subject_mgr:
                    subject_mgr.record_import(subject, file.filename, str(raw_path), len(chunks))
                else:
                    from core.subject_manager import record_import as _record_import
                    _record_import(subject, file.filename, str(raw_path), len(chunks))
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
def knowledge_base_stats(
    subject: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    获取知识库统计信息。
    LA-051-P1-FIX: 使用 _get_accessible_vector_store 支持跨用户数据访问。
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)

    try:
        # LA-051-P1-FIX: 使用权限感知的 VectorStore
        store = _get_accessible_vector_store(subject, effective_user_id)
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
def knowledge_base_chunks(
    subject: str,
    limit: int = 50,
    offset: int = 0,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    获取知识库中的知识片段列表（用于可视化）。
    LA-051-P1-FIX: 使用 _get_accessible_vector_store 支持跨用户数据访问。
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)

    try:
        # LA-051-P1-FIX: 使用权限感知的 VectorStore
        store = _get_accessible_vector_store(subject, effective_user_id)
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


# ========== LA-040-P2: 题库 Bloom 认知层次标注 API ==========

class BloomLabelRequest(BaseModel):
    """Bloom 标注请求"""
    qid: str
    bloom_level: str = Field(..., description="Bloom认知层次: remember/understand/apply/analyze/evaluate/create")


class BatchBloomLabelRequest(BaseModel):
    """批量 Bloom 标注请求"""
    questions: List[BloomLabelRequest]


@app.get("/api/quiz-bank/bloom-stats")
def get_bloom_stats(subject: str = "generic"):
    """
    LA-040-P2: 获取题库的 Bloom 认知层次统计。

    返回各层次的题目数量、已标注覆盖率等。
    """
    from core.quiz_bank import get_bloom_stats as _qb_bloom_stats
    stats = _qb_bloom_stats(subject=subject)
    return stats


@app.post("/api/quiz-bank/bloom-label/{qid}")
def label_bloom_level(qid: str, body: Dict[str, str] = None):
    """
    LA-040-P2: 为单道题目标注 Bloom 认知层次。

    请求体: {"bloom_level": "analyze"}
    """
    from core.quiz_bank import update_bloom_level

    if not body or "bloom_level" not in body:
        raise HTTPException(status_code=400, detail="请求体必须包含 bloom_level 字段")

    level = body["bloom_level"].lower()
    valid = {"remember", "understand", "apply", "analyze", "evaluate", "create"}
    if level not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"无效的 Bloom 层次: {level}。可选: {', '.join(valid)}"
        )

    success = update_bloom_level(qid, level)
    if not success:
        raise HTTPException(status_code=404, detail=f"题目 {qid} 不存在或标注失败")

    return {"success": True, "qid": qid, "bloom_level": level}


@app.post("/api/quiz-bank/bloom-label-batch")
def batch_label_bloom_level(request: BatchBloomLabelRequest):
    """
    LA-040-P2: 批量标注题目的 Bloom 认知层次。

    请求体:
        {
            "questions": [
                {"qid": "qb-xxx", "bloom_level": "analyze"},
                {"qid": "qb-yyy", "bloom_level": "remember"}
            ]
        }
    """
    from core.quiz_bank import batch_update_bloom

    data = [{"id": q.qid, "bloom_level": q.bloom_level} for q in request.questions]
    result = batch_update_bloom(questions=data)

    return {
        "success": True,
        "updated": result["updated"],
        "skipped": result["skipped"],
    }


@app.post("/api/quiz-bank/auto-bloom-label")
def auto_label_bloom_level(
    subject: str = "generic",
    limit: int = 50,
    model: str = "deepseek-chat"
):
    """
    LA-040-P2: 使用 LLM 自动为未标注的题目标注 Bloom 认知层次。

    参数:
        subject: 学科标识
        limit: 每次处理的最大题目数（防止 API 调用过多）
        model: 使用的 LLM 模型

    返回:
        {"labeled": N, "skipped": M, "details": [...]}
    """
    from core.llm_client import LLMClient
    from core.quiz_bank import list_questions, update_bloom_level

    valid_levels = {"remember", "understand", "apply", "analyze", "evaluate", "create"}

    # 1. 获取未标注的题目
    questions = list_questions(subject=subject, is_approved=True, limit=limit * 2)
    unlabeled = [q for q in questions if not q.get("bloom_level")]
    unlabeled = unlabeled[:limit]

    if not unlabeled:
        return {"labeled": 0, "skipped": 0, "message": "没有需要标注的题目"}

    # 2. 构建 LLM prompt
    prompt = """请为以下每道题目标注 Bloom 认知层次。

Bloom 认知层次定义：
- remember（记忆）：考察事实性知识的回忆和识别
- understand（理解）：考察概念的理解、解释和归纳
- apply（应用）：考察知识的应用和解决问题
- analyze（分析）：考察分解信息、识别关系和模式
- evaluate（评估）：考察判断、评价和论证
- create（创造）：考察综合、设计和创新

对每道题目，只输出一行：
<qid> | <bloom_level> | <简短理由(10字内)>

题目列表：
"""
    for q in unlabeled:
        prompt += f"\n[{q['id']}] {q['question'][:100]}...\n类型: {q.get('type', 'unknown')}, 答案: {q.get('answer', 'N/A')[:30]}"

    prompt += "\n\n请输出标注结果："

    # 3. 调用 LLM
    try:
        client = LLMClient()
        response = client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
        )
        content = response.get("content", "")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 调用失败: {str(e)}")

    # 4. 解析 LLM 输出
    labeled = 0
    skipped = 0
    details = []

    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or "|" not in line:
            continue

        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue

        qid = parts[0].strip("[] ")
        level = parts[1].lower()
        reason = parts[2] if len(parts) > 2 else ""

        if level not in valid_levels:
            skipped += 1
            details.append({"qid": qid, "status": "skipped", "reason": f"无效层次: {level}"})
            continue

        success = update_bloom_level(qid, level)
        if success:
            labeled += 1
            details.append({"qid": qid, "status": "labeled", "bloom_level": level, "reason": reason})
        else:
            skipped += 1
            details.append({"qid": qid, "status": "skipped", "reason": "题目不存在"})

    return {
        "labeled": labeled,
        "skipped": skipped,
        "total_processed": len(unlabeled),
        "details": details,
    }


# ========== 学科管理 API ==========

@app.post("/api/subjects", response_model=SubjectItem)
def api_create_subject(
    request: SubjectCreateRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    创建新学科。
    LA-051: 创建学科时自动设置 owner_id = current_user_id，默认 private。
    """
    # LA-052-ISOLATION-FIX: 使用统一身份验证，token 优先
    effective_user_id = get_current_user_id(x_user_id, authorization)

    # LA-051: 默认创建私有学科，owner 为当前用户
    owner_id = effective_user_id if effective_user_id not in ("anonymous", "default") else "system"
    visibility = "private"  # 默认私有，用户后续可改为 public

    if effective_user_id not in ("anonymous", "default"):
        ctx = _get_user_context_from_header(effective_user_id)
        result = ctx.subject_manager.create_subject(
            id=request.id,
            name=request.name,
            description=request.description,
            keywords=request.keywords,
            owner_id=owner_id,
            visibility=visibility,
        )
    else:
        result = create_subject(
            id=request.id,
            name=request.name,
            description=request.description,
            keywords=request.keywords,
            owner_id=owner_id,
            visibility=visibility,
        )
    # LA-051: 创建者自动为 owner
    result["role"] = "owner"
    result["can_write"] = True
    result["can_manage"] = True
    result["can_review"] = True
    return result


@app.get("/api/subjects")
def api_list_subjects(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    列出所有已创建的学科。
    LA-051: 使用 PermissionManager 过滤，只返回用户可访问的学科。
    包括：用户自己的学科 + 全局学科 + 被授权访问的其他用户学科。
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)

    # 收集所有学科（用户私有 + 共享 + 授权学科）
    all_subjects = []
    seen = set()

    # 1. 用户私有学科
    if effective_user_id not in ("anonymous", "default"):
        ctx = _get_user_context_from_header(effective_user_id)
        for s in ctx.subject_manager.list_subjects():
            if s["id"] not in seen:
                seen.add(s["id"])
                all_subjects.append(s)

    # 2. 全局学科
    for s in list_subjects():
        if s["id"] not in seen:
            seen.add(s["id"])
            all_subjects.append(s)

    # 3. LA-051: 从权限表中查找用户被授权的学科
    pm = PermissionManager()
    if effective_user_id not in ("anonymous", "default"):
        conn = pm._get_conn()
        try:
            rows = conn.execute(
                "SELECT subject_id FROM subject_permissions WHERE user_id = ?",
                (effective_user_id,)
            ).fetchall()
            for row in rows:
                subject_id = row["subject_id"]
                if subject_id not in seen:
                    subj = _get_subject_anywhere(subject_id, effective_user_id)
                    if subj:
                        seen.add(subject_id)
                        all_subjects.append(subj)
        finally:
            conn.close()

    # 权限过滤（只返回可访问的学科）
    accessible = pm.list_accessible_subjects(effective_user_id, all_subjects)
    return {
        "subjects": [
            {
                "id": s["id"],
                "name": s["name"],
                "description": s.get("description", ""),
                "keywords": s.get("keywords", []),
                "is_private": s.get("is_private", True),
                "created_at": s.get("created_at", ""),
                "owner_id": s.get("owner_id"),
                "visibility": s.get("visibility", "private"),
                "updated_at": s.get("updated_at"),
                "role": s.get("role", "reader"),
                # LA-051-P2-FIX: 前端需要这些字段判断 contributor 模式
                "can_read": s.get("can_read", True),
                "can_write": s.get("can_write", False),
                "can_contribute": s.get("can_contribute", False),
            }
            for s in accessible
        ]
    }


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
def api_delete_subject(
    subject_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    删除学科（同时清空关联知识库）。
    LA-051: 仅 owner/maintainer 可删除。
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)

    # LA-051: 获取学科信息并检查权限
    sub = get_subject(subject_id)
    if not sub:
        raise HTTPException(status_code=404, detail=f"学科「{subject_id}」不存在")

    owner_id = sub.get("owner_id", "system")
    pm = PermissionManager()
    if not pm.can_manage(effective_user_id, subject_id, owner_id):
        raise HTTPException(status_code=403, detail="您没有权限删除此学科")

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


# ========== LA-051: 权限管理 API ==========

@app.get("/api/subjects/{subject_id}/permissions")
def api_list_permissions(
    subject_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    获取学科权限列表（仅 owner/maintainer 可查看）。
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)
    sub = _get_subject_anywhere(subject_id, effective_user_id)
    if not sub:
        raise HTTPException(status_code=404, detail="学科不存在")

    owner_id = sub.get("owner_id", "system")
    pm = PermissionManager()
    if not pm.can_manage(effective_user_id, subject_id, owner_id):
        raise HTTPException(status_code=403, detail="您没有权限查看此学科的权限设置")

    perms = pm.list_permissions(subject_id)
    return {"subject_id": subject_id, "permissions": perms}


@app.post("/api/subjects/{subject_id}/permissions")
def api_grant_permission(
    subject_id: str,
    body: Dict[str, Any],
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    授予/修改权限（仅 owner）。
    
    Body: {"user_id": str, "role": str}
    role: owner | maintainer | contributor | reader
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)
    sub = _get_subject_anywhere(subject_id, effective_user_id)
    if not sub:
        raise HTTPException(status_code=404, detail="学科不存在")

    owner_id = sub.get("owner_id", "system")
    target_user = body.get("user_id")
    role = body.get("role", "reader")

    pm = PermissionManager()
    try:
        pm.grant_permission(subject_id, target_user, role, effective_user_id, owner_id)
        return {"success": True, "message": f"已授予 {target_user} {role} 权限"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.delete("/api/subjects/{subject_id}/permissions/{target_user}")
def api_revoke_permission(
    subject_id: str,
    target_user: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    撤销权限（仅 owner）。
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)
    sub = _get_subject_anywhere(subject_id, effective_user_id)
    if not sub:
        raise HTTPException(status_code=404, detail="学科不存在")

    owner_id = sub.get("owner_id", "system")
    pm = PermissionManager()
    try:
        deleted = pm.revoke_permission(subject_id, target_user, effective_user_id, owner_id)
        return {"success": True, "deleted": deleted}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.post("/api/subjects/{subject_id}/changes/file")
def api_submit_file_change(
    subject_id: str,
    description: str = Form(""),
    file: UploadFile = File(...),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    LA-051-Task4: contributor 提交文件变更（进入审批队列）。
    
    contributor 可以上传文件，文件内容存入审批队列（BLOB）。
    owner/maintainer 审批通过后，自动执行导入流程。
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)
    sub = _get_subject_anywhere(subject_id, effective_user_id)
    if not sub:
        raise HTTPException(status_code=404, detail="学科不存在")

    owner_id = sub.get("owner_id", "system")
    pm = PermissionManager()

    # 权限检查：contributor 及以上
    if not pm.can_contribute(effective_user_id, subject_id, owner_id):
        raise HTTPException(status_code=403, detail="您没有权限向此学科提交变更")

    # contributor 不能直接进入 import_file（403），必须通过审批队列
    if pm.can_write(effective_user_id, subject_id, owner_id):
        # owner/maintainer 可以直接导入，不需要走审批
        raise HTTPException(
            status_code=400,
            detail="您是拥有者/维护者，请直接使用导入功能，无需审批"
        )

    try:
        # 读取文件内容
        file_data = file.file.read()
        file_name = file.filename or "untitled"

        # 提交到审批队列
        change_id = pm.submit_change(
            subject_id=subject_id,
            submitted_by=effective_user_id,
            change_type="import",
            description=description or f"上传文件: {file_name}",
            file_data=file_data,
            file_name=file_name,
            subject_owner_id=owner_id,
        )

        return {
            "success": True,
            "change_id": change_id,
            "status": "pending",
            "message": f"文件已提交，等待审批。变更ID: {change_id}",
            "file_name": file_name,
            "file_size": len(file_data),
        }
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"提交失败: {str(e)}")


# LA-051-Task4: 审批通过后自动导入的辅助函数
def _auto_import_from_change(subject_id: str, change: Dict[str, Any], reviewer_id: str) -> Dict[str, Any]:
    """
    审批通过后，自动执行文件导入。
    
    从审批记录中提取 file_data，写入临时文件，调用 DocumentProcessor 处理，
    最终导入到 owner 的 vector_store 和 graph_store 中。
    
    Returns:
        导入结果字典
    """
    import tempfile
    from core.document_processor import DocumentProcessor
    from core.vector_store import VectorStore
    from core.graph_store import GraphStore
    from core.subject_manager import save_raw_file, record_import
    from core.user_manager import get_user_manager

    file_data = change.get("file_data")
    file_name = change.get("file_name") or "unknown"
    submitted_by = change.get("submitted_by")

    if not file_data:
        return {"success": False, "message": "审批记录中没有文件数据"}

    # 1. 确定数据目录（使用 owner 的数据目录，因为 contributor 只读）
    subj = _get_subject_anywhere(subject_id, reviewer_id)
    owner_id = subj.get("owner_id", "system") if subj else reviewer_id

    um = get_user_manager()
    owner_vector_dir = um.get_user_vector_db_dir(owner_id)
    owner_graph_dir = um.get_user_graph_db_dir(owner_id)
    owner_raw_dir = um.get_user_kb_dir(owner_id) / subject_id / "raw"
    owner_raw_dir.mkdir(parents=True, exist_ok=True)

    # 2. 写入临时文件
    suffix = Path(file_name).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        # file_data 可能是 bytes 或 memoryview
        if isinstance(file_data, memoryview):
            tmp.write(file_data.tobytes())
        else:
            tmp.write(file_data)
        tmp_path = tmp.name

    try:
        # 3. 处理文件
        processor = DocumentProcessor()

        # VectorStore: 使用 owner 的路径
        db_path = owner_vector_dir / f"{subject_id}_v1.db"
        store = VectorStore(subject_id, db_path=str(db_path))

        # 保存原始文件到 owner 的 raw 目录
        raw_path = save_raw_file(subject_id, file_name, file_data.tobytes() if isinstance(file_data, memoryview) else file_data)

        # 处理文件
        chunks = processor.process_file(tmp_path, subject=subject_id, source_name=file_name, raw_path=str(raw_path))

        if not chunks:
            return {"success": False, "message": "文件处理失败，未提取到有效内容"}

        # 4. 写入 VectorStore
        store.add_documents(chunks)

        # 5. 写入 GraphStore（owner 的目录）
        graph_db_path = owner_graph_dir / f"{subject_id}_v1"
        graph_store = GraphStore(f"{subject_id}_v1", db_path=str(graph_db_path))
        graph_store.init_schema()
        graph_store.add_chunk_nodes(chunks)
        graph_store.build_belongs_to_relations()
        graph_store.build_adjacent_relations()

        # 6. 记录导入
        record_import(subject_id, file_name, str(raw_path), len(chunks))

        return {
            "success": True,
            "message": f"自动导入成功: {file_name} ({len(chunks)} 个片段)",
            "chunks_added": len(chunks),
            "file_name": file_name,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"自动导入失败: {str(e)}"}

    finally:
        try:
            Path(tmp_path).unlink()
        except:
            pass
    """
    contributor 提交变更。
    
    Body: {"change_type": str, "description": str}
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)
    sub = _get_subject_anywhere(subject_id, effective_user_id)
    if not sub:
        raise HTTPException(status_code=404, detail="学科不存在")

    owner_id = sub.get("owner_id", "system")
    pm = PermissionManager()

    change_type = body.get("change_type", "import")
    description = body.get("description", "")

    try:
        change_id = pm.submit_change(
            subject_id, effective_user_id, change_type, description,
            subject_owner_id=owner_id,
        )
        return {"success": True, "change_id": change_id, "status": "pending"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.get("/api/subjects/{subject_id}/changes/pending")
def api_list_pending_changes(
    subject_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    列出待审批变更（owner/maintainer 可查看）。
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)
    sub = _get_subject_anywhere(subject_id, effective_user_id)
    if not sub:
        raise HTTPException(status_code=404, detail="学科不存在")

    owner_id = sub.get("owner_id", "system")
    pm = PermissionManager()
    if not pm.can_review(effective_user_id, subject_id, owner_id):
        raise HTTPException(status_code=403, detail="您没有权限查看审批队列")

    pending = pm.list_pending_changes(subject_id)
    return {"subject_id": subject_id, "pending": pending}


@app.post("/api/subjects/changes/{change_id}/review")
def api_review_change(
    change_id: str,
    body: Dict[str, Any],
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    owner/maintainer 审批变更。
    LA-051-Task4: 审批通过时自动执行文件导入。
    
    Body: {"approve": bool, "note": str}
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)
    pm = PermissionManager()

    # LA-051: 先获取变更记录以确定学科（需要 file_data，使用 get_change_with_data）
    change = pm.get_change_with_data(change_id)
    if not change:
        raise HTTPException(status_code=404, detail=f"变更不存在: {change_id}")
    
    subject_id = change["subject_id"]
    sub = _get_subject_anywhere(subject_id, effective_user_id)
    owner_id = sub.get("owner_id", "system") if sub else "system"

    approve = body.get("approve", False)
    note = body.get("note", "")

    try:
        result = pm.review_change(change_id, effective_user_id, approve, note, owner_id)
        
        # LA-051-Task4: 审批通过时自动执行导入
        import_result = None
        if approve and change.get("change_type") == "import":
            print(f"[LA-051-Task4] 审批通过，开始自动导入 | change_id={change_id}, subject={subject_id}")
            import_result = _auto_import_from_change(subject_id, change, effective_user_id)
            print(f"[LA-051-Task4] 自动导入结果: {import_result}")
            
            # 将导入结果写入审批备注
            if import_result:
                result["import_result"] = import_result
        
        return {"success": True, "change": result}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
def build_knowledge_graph(
    subject: str,
    body: Dict[str, Any] = None,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
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
    llm_provider = body.get("llm_provider")  # LA-ROBUST: 支持切换 LLM 提供商

    try:
        # LA-050-Phase5: 使用用户隔离的 GraphBuilder
        effective_user_id = get_current_user_id(x_user_id, authorization)
        print(f"[LA-051-DEBUG] build: user_id={x_user_id}, auth_present={authorization is not None}, effective={effective_user_id}")
        if effective_user_id not in ("anonymous", "default"):
            ctx = _get_user_context_from_header(effective_user_id)
            vector_store = ctx.get_user_vector_store(subject)
            graph_store = ctx.get_user_graph_store(subject)
            builder = GraphBuilder(f"{subject}_v1", paradigm=paradigm,
                                   vector_store=vector_store, graph_store=graph_store,
                                   llm_provider=llm_provider)
        else:
            builder = GraphBuilder(f"{subject}_v1", paradigm=paradigm,
                                   llm_provider=llm_provider)
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
def get_graph_stats(
    subject: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    获取知识图谱统计信息。
    LA-051-P1-FIX: 使用 _get_accessible_graph_store 支持跨用户数据访问。
    LA-051-P2-FIX: 支持 Authorization header 获取用户身份。
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)

    try:
        # LA-051-P1-FIX: 使用权限感知的 GraphStore
        store = _get_accessible_graph_store(subject, effective_user_id)
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
def list_graph_nodes(
    subject: str,
    limit: int = 5000,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    获取图谱中的 Chunk 节点（用于前端全局浏览，排除 parent 节点）。
    LA-051-P1-FIX: 使用 _get_accessible_graph_store 支持跨用户数据访问。
    LA-051-P2-FIX: 支持 Authorization header 获取用户身份。
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)
    # 限制最大返回数量，防止性能问题
    limit = max(1, min(limit, 2000))

    try:
        # LA-051-P1-FIX: 使用权限感知的 GraphStore
        store = _get_accessible_graph_store(subject, effective_user_id)
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
                # LA-035-P42-FIX: image_pseudo 节点如果 image_path 为空，尝试从 media_refs 提取
                if not node["image_path"] and row[4] == 'image_pseudo':
                    try:
                        media_result = conn.execute(f'''
                            MATCH (c:Chunk {{chunk_id: "{row[0]}"}})
                            RETURN c.media_refs
                        ''')
                        if media_result.has_next():
                            import json
                            media_raw = media_result.get_next()[0] or "[]"
                            media_refs = json.loads(media_raw) if isinstance(media_raw, str) else media_raw
                            if media_refs and isinstance(media_refs, list) and len(media_refs) > 0:
                                first_ref = media_refs[0]
                                if isinstance(first_ref, dict):
                                    node["image_path"] = first_ref.get("path", "") or first_ref.get("image_path", "")
                                    node["thumbnail_path"] = first_ref.get("thumbnail_path", "") or first_ref.get("thumbnail", "")
                                    print(f"[API] LA-035-P42-FIX: 从 media_refs 补全 image_path for {row[0]}: {node['image_path']}")
                    except Exception as e:
                        print(f"[API] LA-035-P42-FIX: 补全 image_path 失败 for {row[0]}: {e}")
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
def list_graph_edges(
    subject: str,
    limit: int = 5000,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    获取 Chunk 节点之间的边（排除 parent 节点相关的边）。
    LA-051-P1-FIX: 使用 _get_accessible_graph_store 支持跨用户数据访问。
    LA-051-P2-FIX: 支持 Authorization header 获取用户身份。
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)
    # 限制最大返回数量，防止性能问题
    limit = max(1, min(limit, 5000))

    try:
        # LA-051-P1-FIX: 使用权限感知的 GraphStore
        store = _get_accessible_graph_store(subject, effective_user_id)
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
def get_subgraph(
    subject: str,
    chunk_id: str,
    depth: int = 2,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    获取以指定 chunk 为中心的子图。
    LA-051-P1-FIX: 使用 _get_accessible_graph_store 支持跨用户数据访问。
    LA-051-P2-FIX: 支持 Authorization header 获取用户身份。
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)

    try:
        # LA-051-P1-FIX: 使用权限感知的 GraphStore
        store = _get_accessible_graph_store(subject, effective_user_id)
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
def get_image(
    subject: str,
    filename: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    提供学科知识库中的图片文件访问。
    LA-051-STRUCT: 使用新目录结构（学科内聚）
    
    路径: /api/images/<subject>/<filename>
    """
    from config.settings import get_subject_images_dir, get_subject_thumbnails_dir
    effective_user_id = get_current_user_id(x_user_id, authorization)
    
    # 安全检查：防止目录遍历
    safe_filename = Path(filename).name
    
    # LA-051-STRUCT: 优先查找用户私有目录
    if effective_user_id != "default":
        ctx = _get_user_context_from_header(effective_user_id)
        user_img_dir = ctx.get_user_images_dir(subject)
        user_img = user_img_dir / safe_filename
        if user_img.exists():
            return FileResponse(str(user_img))
        
        user_thumb_dir = ctx.get_user_thumbnails_dir(subject)
        user_thumb = user_thumb_dir / safe_filename
        if user_thumb.exists():
            return FileResponse(str(user_thumb))
    
    # Fallback: 共享目录（新结构）
    share_img_dir = get_subject_images_dir(subject)
    img_path = share_img_dir / safe_filename
    if img_path.exists():
        return FileResponse(str(img_path))
    
    share_thumb_dir = get_subject_thumbnails_dir(subject)
    thumb_path = share_thumb_dir / safe_filename
    if thumb_path.exists():
        return FileResponse(str(thumb_path))
    
    raise HTTPException(status_code=404, detail=f"图片不存在: {filename}")


# ========== 知识图谱 API (Phase 2: 语义层) ==========

@app.post("/api/knowledge-graph/{subject}/extract/{chunk_id}")
async def extract_chunk_concepts(
    subject: str,
    chunk_id: str,
    body: Dict[str, Any] = None,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    effective_user_id = get_current_user_id(x_user_id, authorization)
    """
    对指定 chunk 进行语义提取，分析其内部概念结构。

    支持范式选择：theory / engineering / hierarchical
    """
    from core.graph_store import GraphStore
    from core.semantic_extractor import SemanticExtractor

    try:
        if effective_user_id != "default":
            ctx = _get_user_context_from_header(effective_user_id)
            graph_store = ctx.get_user_graph_store(subject)
        else:
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
def get_chunk_concepts(
    subject: str,
    chunk_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    获取指定 chunk 已提取的概念列表。
    LA-051-P1-FIX: 使用 _get_accessible_graph_store 支持跨用户数据访问。
    LA-051-P2-FIX: 支持 Authorization header 获取用户身份。
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)

    try:
        # LA-051-P1-FIX: 使用权限感知的 GraphStore
        graph_store = _get_accessible_graph_store(subject, effective_user_id)
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
def list_graph_concepts(
    subject: str,
    limit: int = 2000,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    获取图谱中的所有概念节点。
    LA-051-P1-FIX: 使用 _get_accessible_graph_store 支持跨用户数据访问。
    LA-051-P2-FIX: 支持 Authorization header 获取用户身份。
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)
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
        # LA-051-P1-FIX: 使用权限感知的 GraphStore
        graph_store = _get_accessible_graph_store(subject, effective_user_id)
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
def list_concept_links(
    subject: str,
    limit: int = 500,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    获取概念间的语义连接边（全局推断生成的 SOLUTION / DEPENDS_ON）。
    LA-051-P1-FIX: 使用 _get_accessible_graph_store 支持跨用户数据访问。
    LA-051-P2-FIX: 支持 Authorization header 获取用户身份。
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)

    try:
        # LA-051-P1-FIX: 使用权限感知的 GraphStore
        graph_store = _get_accessible_graph_store(subject, effective_user_id)
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


@app.get("/api/knowledge-graph/{subject}/paradigm")
def get_paradigm_config(subject: str):
    """
    LA-052: 获取指定学科的范式配置（供前端动态渲染使用）。
    """
    try:
        # 从学科配置读取范式ID
        paradigm_id = _get_subject_paradigm(subject)
        
        # 从 YAML 加载范式配置
        from core.semantic_linker import _PARADIGMS_YAML
        config = _PARADIGMS_YAML.get(paradigm_id)
        
        if not config:
            raise HTTPException(
                status_code=404,
                detail=f"范式配置未找到: paradigm={paradigm_id}, subject={subject}"
            )
        
        # 组装响应（增加 styles 和 types 等前端所需字段）
        relations = config.get("relations", {})
        styles = config.get("styles", {})
        
        # 为没有 styles 的关系类型补充默认样式
        default_palette = ["#e67e22", "#9b59b6", "#3498db", "#27ae60", "#e74c3c", "#f39c12"]
        for i, rel_type in enumerate(relations.keys()):
            if rel_type not in styles:
                styles[rel_type] = {
                    "color": default_palette[i % len(default_palette)],
                    "lineStyle": "solid" if i % 2 == 0 else "dashed",
                    "width": 2 if i % 2 == 0 else 1.5,
                }
        
        return {
            "paradigm_id": paradigm_id,
            "name": config.get("name", paradigm_id),
            "description": config.get("description", ""),
            "levels": list(config.get("types", {}).keys()),
            "types": config.get("types", {}),
            "relations": relations,
            "relation_map": config.get("relation_map", {}),
            "cyclic": config.get("cyclic", False),
            "cycle_pattern": config.get("cycle_pattern", []),
            "styles": styles,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取范式配置失败: {str(e)}")


# ========== LA-052: 范式管理 API ==========

@app.get("/api/paradigms")
def list_paradigms():
    """
    获取所有可用范式列表（内置 + 自定义）
    """
    try:
        from core.paradigm_manager import get_paradigm_manager
        manager = get_paradigm_manager()
        return {"paradigms": manager.list_paradigms()}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取范式列表失败: {str(e)}")


@app.get("/api/paradigms/{paradigm_id}")
def get_paradigm_detail(paradigm_id: str):
    """
    获取指定范式的完整配置
    """
    try:
        from core.paradigm_manager import get_paradigm_manager
        manager = get_paradigm_manager()
        config = manager.get_paradigm(paradigm_id)
        if not config:
            raise HTTPException(status_code=404, detail=f"范式未找到: {paradigm_id}")
        return config
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取范式详情失败: {str(e)}")


class CreateParadigmRequest(BaseModel):
    """创建范式请求体"""
    paradigm_id: str = Field(..., min_length=1, max_length=50, description="范式唯一标识")
    name: str = Field(..., min_length=1, max_length=50, description="显示名称")
    description: str = Field(..., min_length=1, max_length=200, description="范式描述")
    icon: str = Field(default="", max_length=10, description="图标 emoji")
    color: str = Field(default="#3498db", max_length=20, description="主题色")
    types: Dict[str, str] = Field(..., description="概念类型 {key: label}")
    relations: Dict[str, str] = Field(..., description="关系类型 {key: label}")
    relation_map: Dict[str, Dict[str, List[str]]] = Field(..., description="连接规则")
    ideal_chain: Optional[List[str]] = Field(default=None, description="理想层级链条")
    cyclic: bool = Field(default=False, description="是否循环范式")
    cycle_pattern: Optional[List[str]] = Field(default=None, description="循环模式")
    fallback: Optional[Dict] = Field(default=None, description="降级策略")
    gap_rules: Optional[Dict] = Field(default=None, description="Gap 检测规则")
    styles: Optional[Dict] = Field(default=None, description="可视化样式（可选，自动分配）")
    prompt_addon: Optional[str] = Field(default=None, description="LLM 提示词附加（可选，自动生成）")


@app.post("/api/paradigms")
def create_paradigm_api(request: CreateParadigmRequest):
    """
    创建新范式
    
    前端提交最小必填集，后端自动推导 parent_rules、styles、ideal_chain、prompt_addon。
    """
    try:
        from core.paradigm_manager import get_paradigm_manager
        manager = get_paradigm_manager()
        
        # 将 Pydantic 模型转为字典
        data = request.dict()
        
        result = manager.create_paradigm(data)
        
        if not result.get("success"):
            errors = result.get("errors", ["未知错误"])
            raise HTTPException(status_code=400, detail="; ".join(errors))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"创建范式失败: {str(e)}")


@app.delete("/api/paradigms/{paradigm_id}")
def delete_paradigm_api(paradigm_id: str):
    """
    删除自定义范式（内置范式不允许删除）
    """
    try:
        from core.paradigm_manager import get_paradigm_manager
        manager = get_paradigm_manager()
        
        result = manager.delete_paradigm(paradigm_id)
        
        if not result.get("success"):
            errors = result.get("errors", ["未知错误"])
            raise HTTPException(status_code=400, detail="; ".join(errors))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"删除范式失败: {str(e)}")


def _get_subject_paradigm(subject: str) -> str:
    """
    获取学科使用的范式ID。
    优先从学科配置文件读取，fallback 到默认范式。
    """
    import json
    from config.settings import PROJECT_ROOT
    
    # 尝试读取学科配置
    subject_config_path = PROJECT_ROOT / "config" / "subjects" / f"{subject}.json"
    if subject_config_path.exists():
        try:
            with open(subject_config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                paradigm = cfg.get("paradigm")
                if paradigm:
                    return paradigm
        except Exception:
            pass
    
    # Fallback: 从已构建的图谱元数据推断
    meta_path = PROJECT_ROOT / "knowledge_base" / f"{subject}_build_meta.json"
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                paradigm = meta.get("paradigm")
                if paradigm:
                    return paradigm
        except Exception:
            pass
    
    # 默认 fallback
    return "engineering"


# ========== 批量语义提取 + 去重 ==========

@app.post("/api/knowledge-graph/{subject}/build/semantic")
async def build_semantic_layer(
    subject: str,
    body: Dict[str, Any] = None,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    批量构建语义层 — 对所有 chunk 提取概念。
    LA-050-Phase5: 支持 X-User-ID Header。
    """
    from core.graph_builder import GraphBuilder
    effective_user_id = get_current_user_id(x_user_id, authorization)

    try:
        paradigm = "theory"
        if body and isinstance(body, dict):
            paradigm = body.get("paradigm", "theory")
        if effective_user_id != "default":
            ctx = _get_user_context_from_header(effective_user_id)
            vector_store = ctx.get_user_vector_store(subject)
            graph_store = ctx.get_user_graph_store(subject)
            builder = GraphBuilder(f"{subject}_v1", paradigm=paradigm,
                                   vector_store=vector_store, graph_store=graph_store)
        else:
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
async def build_semantic_links(
    subject: str,
    body: Dict[str, Any] = None,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    执行全局语义连接推断（在已有去重概念基础上）。
    LA-050-Phase5: 支持 X-User-ID Header。
    """
    from core.graph_builder import GraphBuilder
    effective_user_id = get_current_user_id(x_user_id, authorization)

    try:
        body = body or {}
        paradigm = body.get("paradigm", "engineering")
        if effective_user_id != "default":
            ctx = _get_user_context_from_header(effective_user_id)
            vector_store = ctx.get_user_vector_store(subject)
            graph_store = ctx.get_user_graph_store(subject)
            builder = GraphBuilder(f"{subject}_v1", paradigm=paradigm,
                                   vector_store=vector_store, graph_store=graph_store)
        else:
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
async def dedupe_concepts(
    subject: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    对全局概念空间进行去重。
    LA-050-Phase5: 支持 X-User-ID Header。
    """
    from core.graph_builder import GraphBuilder
    effective_user_id = get_current_user_id(x_user_id, authorization)

    try:
        if effective_user_id != "default":
            ctx = _get_user_context_from_header(effective_user_id)
            vector_store = ctx.get_user_vector_store(subject)
            graph_store = ctx.get_user_graph_store(subject)
            builder = GraphBuilder(f"{subject}_v1",
                                   vector_store=vector_store, graph_store=graph_store)
        else:
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


# ========== LA-044: 对话上下文 API (必须在 /api/media/{path:path} 通配路由之前定义) ==========

class DialogSessionCreate(BaseModel):
    user_id: str
    subject_id: Optional[str] = None

@app.get("/api/dialog/sessions")
def list_dialog_sessions(
    user_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    获取用户的活跃对话会话列表。
    LA-050-Phase4-FIX + LA-052-ISOLATION-FIX: 使用统一身份验证，确保 token 优先。
    LA-051: 当 header 身份验证失败时，回退到 query 参数 user_id（前端显式传递）。
    """
    # LA-052-ISOLATION-FIX: 使用统一身份验证，token 优先
    effective_user_id = get_current_user_id(x_user_id, authorization)
    
    # LA-051: 如果 header 验证回退到 default/anonymous，但前端显式传了 user_id，则使用前端传的值
    # 这确保登录用户（前端知道 user_id）能正确查看自己的会话，而不是看到 default 用户的共享会话
    if effective_user_id in ("anonymous", "default") and user_id and user_id not in ("anonymous", "default"):
        effective_user_id = user_id
        print(f"[LA-051] list_dialog_sessions: header 无有效身份，使用 query user_id={user_id}")

    try:
        # LA-050-Phase4-FIX: 使用用户隔离的 DialogContextManager
        if effective_user_id in ("anonymous", "default"):
            mgr = _dialog_manager  # 向后兼容
        else:
            ctx = _get_user_context_from_header(effective_user_id)
            mgr = ctx.dialog_manager

        conn = sqlite3.connect(str(mgr.db_path))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT session_id, subject_id, current_topic, turn_count, status, created_at, updated_at
            FROM dialog_sessions
            WHERE user_id = ? AND status IN ('active', 'suspended')
            ORDER BY updated_at DESC
        """, (effective_user_id,))
        rows = cursor.fetchall()
        conn.close()

        sessions = []
        for row in rows:
            sessions.append({
                "id": row[0],
                "subject_id": row[1],
                "current_topic": row[2] or "",
                "turn_count": row[3] or 0,
                "status": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            })
        return {"user_id": effective_user_id, "sessions": sessions}
    except Exception as e:
        print(f"[API] 获取会话列表失败: {e}")
        return {"user_id": effective_user_id, "sessions": []}


@app.post("/api/dialog/sessions")
def create_dialog_session(
    request: DialogSessionCreate,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    创建新对话会话。
    创建前会暂停用户该学科的所有其他活跃会话，确保新会话独立。
    LA-050-Phase4-FIX + LA-052-ISOLATION-FIX: 使用统一身份验证。
    """
    # LA-052-ISOLATION-FIX: 使用统一身份验证，token 优先
    # LA-051-SESSION: 当 header 身份验证失败时，回退到请求体中的 user_id
    effective_user_id = get_current_user_id(x_user_id, authorization)
    if effective_user_id in ("anonymous", "default") and request.user_id and request.user_id not in ("anonymous", "default"):
        effective_user_id = request.user_id
        print(f"[LA-051-SESSION] create_dialog_session: header 无有效身份，使用 body user_id={request.user_id}")

    try:
        # LA-050-Phase4-FIX: 使用用户隔离的 DialogContextManager
        if effective_user_id in ("anonymous", "default"):
            mgr = _dialog_manager  # 向后兼容
        else:
            ctx = _get_user_context_from_header(effective_user_id)
            mgr = ctx.dialog_manager

        # 先暂停用户同学科的其他活跃会话
        mgr._suspend_user_subject_sessions(
            user_id=effective_user_id,
            subject_id=request.subject_id,
        )

        session_id, session = mgr.get_or_create_session(
            user_id=effective_user_id,
            subject_id=request.subject_id,
        )
        return {
            "session_id": session_id,
            "subject_id": session.get("subject_id", ""),
            "status": session.get("status", "active"),
            "current_topic": session.get("current_topic", ""),
        }
    except Exception as e:
        print(f"[API] 创建会话失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建会话失败: {e}")


@app.get("/api/dialog/sessions/{session_id}/messages")
def get_session_messages(
    session_id: str,
    user_id: Optional[str] = None,  # LA-051-SESSION: query 参数回退
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    获取指定会话的历史消息列表。
    LA-050-Phase4-FIX + LA-052-ISOLATION-FIX: 使用统一身份验证。
    """
    # LA-052-ISOLATION-FIX: 使用统一身份验证，token 优先
    # LA-051-SESSION: 当 header 身份验证失败时，回退到 query 参数 user_id
    effective_user_id = get_current_user_id(x_user_id, authorization)
    if effective_user_id in ("anonymous", "default") and user_id and user_id not in ("anonymous", "default"):
        effective_user_id = user_id
        print(f"[LA-051-SESSION] get_session_messages: header 无有效身份，使用 query user_id={user_id}")

    try:
        # LA-050-Phase4-FIX: 使用用户隔离的 DialogContextManager
        if effective_user_id in ("anonymous", "default"):
            mgr = _dialog_manager
        else:
            ctx = _get_user_context_from_header(effective_user_id)
            mgr = ctx.dialog_manager

        # 验证 session 是否属于当前用户
        conn = sqlite3.connect(str(mgr.db_path))
        cursor = conn.cursor()

        # 先验证 session 所有权
        cursor.execute("SELECT user_id FROM dialog_sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail=f"会话 {session_id[:8]}... 不存在")
        session_owner = row[0]
        if session_owner != effective_user_id:
            conn.close()
            raise HTTPException(status_code=403, detail="无权访问该会话")

        # 查询消息
        cursor.execute("""
            SELECT turn_number, role, agent_name, content, intent, created_at, metadata
            FROM dialog_messages
            WHERE session_id = ?
            ORDER BY turn_number ASC, message_id ASC
        """, (session_id,))
        rows = cursor.fetchall()
        conn.close()

        messages = []
        for row in rows:
            metadata = {}
            if row[6]:
                try:
                    metadata = json.loads(row[6])
                except json.JSONDecodeError:
                    pass
            messages.append({
                "turn_number": row[0],
                "role": row[1],
                "agent": row[2] or "",
                "content": row[3],
                "intent": row[4] or "",
                "time": row[5],
                "sources": metadata.get("sources", []),
                "media": metadata.get("media", []),
            })
        return {"session_id": session_id, "messages": messages}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] 获取会话消息失败: {e}")
        return {"session_id": session_id, "messages": []}


@app.delete("/api/dialog/sessions/{session_id}")
def delete_dialog_session(
    session_id: str,
    user_id: Optional[str] = None,  # LA-051-SESSION: query 参数回退
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    删除指定会话及其所有消息。
    LA-050-Phase4-FIX + LA-052-ISOLATION-FIX: 使用统一身份验证。
    """
    # LA-052-ISOLATION-FIX: 使用统一身份验证，token 优先
    # LA-051-SESSION: 当 header 身份验证失败时，回退到 query 参数 user_id
    effective_user_id = get_current_user_id(x_user_id, authorization)
    if effective_user_id in ("anonymous", "default") and user_id and user_id not in ("anonymous", "default"):
        effective_user_id = user_id
        print(f"[LA-051-SESSION] delete_dialog_session: header 无有效身份，使用 query user_id={user_id}")

    try:
        # LA-050-Phase4-FIX: 使用用户隔离的 DialogContextManager
        if effective_user_id in ("anonymous", "default"):
            mgr = _dialog_manager
        else:
            ctx = _get_user_context_from_header(effective_user_id)
            mgr = ctx.dialog_manager

        conn = sqlite3.connect(str(mgr.db_path))
        cursor = conn.cursor()

        # 先验证 session 所有权
        cursor.execute("SELECT user_id FROM dialog_sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail=f"会话 {session_id[:8]}... 不存在")
        session_owner = row[0]
        if session_owner != effective_user_id:
            conn.close()
            raise HTTPException(status_code=403, detail="无权删除该会话")

        # 删除会话的消息
        cursor.execute("DELETE FROM dialog_messages WHERE session_id = ?", (session_id,))
        msg_deleted = cursor.rowcount

        # 删除会话
        cursor.execute("DELETE FROM dialog_sessions WHERE session_id = ? AND user_id = ?",
                       (session_id, effective_user_id))
        session_deleted = cursor.rowcount

        # 删除话题追踪
        cursor.execute("DELETE FROM dialog_topics WHERE session_id = ?", (session_id,))

        conn.commit()
        conn.close()

        print(f"[API] 删除会话 {session_id[:8]}: {session_deleted} 个会话, {msg_deleted} 条消息")
        return {"success": True, "session_id": session_id, "messages_deleted": msg_deleted}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] 删除会话失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除会话失败: {e}")


# ========== LA-035: 媒体文件静态服务 ==========

@app.get("/api/media/{path:path}")
def serve_media(path: str, x_user_id: Optional[str] = Header(None, alias="X-User-ID"), authorization: Optional[str] = Header(None)):
    """
    提供知识库中的图片等媒体文件的静态访问。
    LA-050-Phase5: 支持 X-User-ID Header，优先查找用户私有目录。
    
    路径中的正斜杠会被还原为系统路径分隔符，
    确保 Windows 路径也能正确解析。
    """
    from urllib.parse import unquote
    import os
    from config.settings import KNOWLEDGE_BASE_DIR
    
    effective_user_id = get_current_user_id(x_user_id, authorization)
    
    # 解码 URL 编码
    decoded_path = unquote(path)
    print(f"[API] LA-IMG: 媒体请求: raw='{path}', decoded='{decoded_path}', user={effective_user_id}")
    
    # 替换 URL 正斜杠为系统路径分隔符
    normalized_path = decoded_path.replace('/', os.sep)
    
    # LA-050-Phase5: 优先检查用户私有目录
    if effective_user_id != "default":
        try:
            from core.user_manager import get_user_manager
            um = get_user_manager()
            user_kb = um.get_user_kb_dir(effective_user_id)
            user_path = user_kb / normalized_path
            user_path = user_path.resolve()
            if user_path.exists() and user_path.is_file():
                print(f"[API] LA-IMG: 200 返回用户文件: {user_path}")
                return FileResponse(user_path)
        except Exception as e:
            print(f"[API] LA-IMG: 用户目录查找失败: {e}")
    
    # Fallback: 共享目录
    full_path = KNOWLEDGE_BASE_DIR / normalized_path
    print(f"[API] LA-IMG: 解析路径: {full_path}")
    
    # 安全检查：确保路径在知识库目录内（防止目录遍历攻击）
    try:
        full_path = full_path.resolve()
        kb_root = KNOWLEDGE_BASE_DIR.resolve()
        if not str(full_path).startswith(str(kb_root)):
            print(f"[API] LA-IMG: 403 路径越界: {full_path}")
            raise HTTPException(status_code=403, detail="Forbidden: path outside knowledge base")
    except Exception:
        print(f"[API] LA-IMG: 403 无效路径: {full_path}")
        raise HTTPException(status_code=403, detail="Forbidden: invalid path")
    
    if full_path.exists() and full_path.is_file():
        print(f"[API] LA-IMG: 200 返回文件: {full_path}")
        return FileResponse(full_path)
    
    print(f"[API] LA-IMG: 404 文件不存在: {full_path}")
    raise HTTPException(status_code=404, detail=f"File not found: {path}")


# ========== 静态前端文件 ==========
# 如果 web 目录存在且包含 index.html，挂载静态文件服务
# 否则保留 root() 路由返回 API 信息
# 优先使用构建后的前端（web/dist/），否则回退到源码（web/）
WEB_DIR = PROJECT_ROOT / "web" / "dist"
INDEX_FILE = WEB_DIR / "index.html"
if not INDEX_FILE.exists():
    # 回退：检查 web/index.html（旧结构）
    INDEX_FILE = PROJECT_ROOT / "web" / "index.html"

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


# LA-044: 辅助函数 — 获取会话当前话题
def _get_session_topic(session_id: Optional[str]) -> Optional[str]:
    """从 DialogContextManager 获取会话的 current_topic。"""
    if not session_id:
        return None
    try:
        session = _dialog_manager._load_session(session_id)
        return session.get("current_topic") if session else None
    except Exception as e:
        print(f"[API] 获取会话话题失败: {e}")
        return None


# ========== LA-044-#3: 用户状态自动保存与 API ==========

# ========== LA-050-Phase4: 用户上下文依赖注入 ==========

# 全局 UserContext 缓存（按 user_id）
_user_context_cache: Dict[str, Any] = {}


def _get_user_context_from_header(x_user_id: Optional[str] = None) -> Any:
    """
    LA-050-Phase4: 根据 X-User-ID Header 获取或创建 UserContext。

    Args:
        x_user_id: 请求头中的 X-User-ID，如果为空则使用 "default"

    Returns:
        UserContext 实例（用户隔离的数据访问上下文）
    """
    user_id = x_user_id or "default"

    if user_id not in _user_context_cache:
        from core.user_context import UserContext
        _user_context_cache[user_id] = UserContext(user_id)
        print(f"[API] LA-050-Phase4: UserContext 初始化 | user_id={user_id}")

    return _user_context_cache[user_id]


def _get_subject_anywhere(subject_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    LA-051: 在全局和所有用户私有数据库中查找学科。
    
    搜索顺序：全局 subjects.db → 当前用户 subjects.db → 其他用户 subjects.db
    
    Returns:
        学科字典或 None
    """
    from core.subject_manager import SubjectManager
    from config.settings import USERS_DIR

    # 1. 查全局
    subj = get_subject(subject_id)
    if subj:
        return subj
    
    # 2. 查指定用户私有
    if user_id and user_id not in ("anonymous", "default"):
        try:
            user_db = USERS_DIR / user_id / "subjects.db"
            if user_db.exists():
                sm = SubjectManager(db_path=str(user_db))
                subj = sm.get_subject(subject_id)
                if subj:
                    return subj
        except Exception:
            pass
    
    # 3. 遍历所有用户的 subjects.db（应对 owner 私有学科被授权给 contributor 的场景）
    try:
        if USERS_DIR.exists():
            for user_dir in USERS_DIR.iterdir():
                if not user_dir.is_dir():
                    continue
                user_db = user_dir / "subjects.db"
                if user_db.exists():
                    try:
                        sm = SubjectManager(db_path=str(user_db))
                        subj = sm.get_subject(subject_id)
                        if subj:
                            return subj
                    except Exception:
                        continue
    except Exception:
        pass
    
    return None


# ========== LA-051-P1-FIX: 跨用户数据访问辅助函数 ==========

def _get_accessible_vector_store(subject_id: str, user_id: str):
    """
    根据用户权限获取可访问的 VectorStore。
    
    对于 owner/maintainer: 使用自己的数据目录
    对于 reader/contributor: 使用 owner 的数据目录（只读）
    对于无权限: 抛出 403
    
    Returns:
        VectorStore 实例
    """
    from core.vector_store import VectorStore
    from core.permission_manager import PermissionManager
    from core.user_manager import get_user_manager
    from config.settings import VECTOR_DB_DIR
    
    # 1. 获取学科信息
    subj = _get_subject_anywhere(subject_id, user_id)
    if not subj:
        # 学科不存在，fallback 到默认路径
        return VectorStore(f"{subject_id}_v1")
    
    owner_id = subj.get("owner_id", "system")
    pm = PermissionManager()
    
    if not pm.can_read(user_id, subject_id, owner_id):
        raise HTTPException(status_code=403, detail="无权访问该学科")
    
    # 2. 判断使用哪个用户的数据目录
    # LA-051-P1-FIX: 只有 owner 使用自己的目录。
    # Maintainer/Contributor/Reader 都访问 owner 的数据（权限控制是逻辑层面的，数据物理位置统一在 owner 目录）。
    if user_id == owner_id:
        data_user_id = user_id
    else:
        data_user_id = owner_id
    
    # 3. 构建路径并返回 VectorStore
    um = get_user_manager()
    db_path = um.get_user_vector_db_dir(data_user_id) / f"{subject_id}_v1.db"
    
    if db_path.exists():
        return VectorStore(subject_id, db_path=str(db_path))
    
    # fallback 到共享路径
    share_db = VECTOR_DB_DIR / f"{subject_id}_v1.db"
    if share_db.exists():
        return VectorStore(subject_id, db_path=str(share_db))
    
    # 返回空存储（路径正确但不存在）
    return VectorStore(subject_id, db_path=str(db_path))


def _get_accessible_graph_store(subject_id: str, user_id: str):
    """
    根据用户权限获取可访问的 GraphStore。
    
    对于 owner/maintainer: 使用自己的数据目录
    对于 reader/contributor: 使用 owner 的数据目录（只读）
    对于无权限: 抛出 403
    
    Returns:
        GraphStore 实例
    """
    from core.graph_store import GraphStore
    from core.permission_manager import PermissionManager
    from core.user_manager import get_user_manager
    from config.settings import GRAPH_DB_DIR
    
    # 1. 获取学科信息
    subj = _get_subject_anywhere(subject_id, user_id)
    if not subj:
        # 学科不存在，fallback 到默认路径
        return GraphStore(f"{subject_id}_v1")
    
    owner_id = subj.get("owner_id", "system")
    pm = PermissionManager()
    
    if not pm.can_read(user_id, subject_id, owner_id):
        raise HTTPException(status_code=403, detail="无权访问该学科")
    
    # 2. 判断使用哪个用户的数据目录
    # LA-051-P1-FIX: 只有 owner 使用自己的目录。
    # Maintainer/Contributor/Reader 都访问 owner 的数据（权限控制是逻辑层面的，数据物理位置统一在 owner 目录）。
    if user_id == owner_id:
        data_user_id = user_id
    else:
        data_user_id = owner_id
    
    # 3. 构建路径并返回 GraphStore
    um = get_user_manager()
    db_path = um.get_user_graph_db_dir(data_user_id) / f"{subject_id}_v1"
    
    if db_path.exists():
        return GraphStore(f"{subject_id}_v1", db_path=str(db_path))
    
    # fallback 到共享路径
    share_db = GRAPH_DB_DIR / f"{subject_id}_v1"
    if share_db.exists():
        return GraphStore(f"{subject_id}_v1", db_path=str(share_db))
    
    # 返回空存储（路径正确但不存在）
    return GraphStore(f"{subject_id}_v1", db_path=str(db_path))


def _get_isolated_state_store(user_id: str) -> Any:
    """
    LA-050-Phase4: 获取用户隔离的 UserStateStore 实例。

    根据 user_id 获取对应的 UserContext，返回其 state_store。
    如果 user_id 是 anonymous 且使用默认配置，返回共享 store（向后兼容）。
    """
    if user_id in ("anonymous", "default"):
        # 向后兼容：anonymous 用户使用默认共享路径
        return _get_user_state_store()

    ctx = _get_user_context_from_header(user_id)
    store = ctx.state_store
    # 确保通过 _get_user_state_store 的缓存机制（按 db_path 缓存）
    return _get_user_state_store(db_path=str(store.db_path))


# 全局 UserStateStore 实例（延迟初始化，按 db_path 缓存）
_user_state_store_map: Dict[str, Any] = {}

def _get_user_state_store(db_path: Optional[str] = None):
    """
    获取或创建 UserStateStore 实例。

    LA-050-Phase2: 支持按 db_path 获取用户隔离实例。
    如果不传 db_path，使用默认共享路径（向后兼容 anonymous 用户）。
    """
    global _user_state_store_map

    cache_key = db_path or "__default__"
    if cache_key not in _user_state_store_map:
        from core.graph_education.user_state_store import UserStateStore
        store = UserStateStore(db_path=db_path)
        _user_state_store_map[cache_key] = store
        print(f"[API] LA-044-#3/LA-050: UserStateStore 初始化完成 | db={db_path or 'default'}")
    return _user_state_store_map[cache_key]


def _save_user_state_after_dialog(user_id: str, request: AskRequest, result: Dict[str, Any]):
    """LA-044-#3: 对话结束后自动保存用户状态（theta + 薄弱点）

    从对话结果中提取 theta 和薄弱点信息，写回 UserStateStore。
    此函数在 /api/ask 返回响应前调用，不阻塞响应。
    """
    subject_id = f"{request.subject}_v1"

    print(f"\n[API] LA-044-#3: ====== 自动保存用户状态 ======")
    print(f"[API] 输入: user_id={user_id}, subject_id={subject_id}")

    # 1. 提取 theta（从 IRT 结果或 user_theta 请求参数）
    theta = None
    agent_result = result.get("result", {})
    if isinstance(agent_result, dict):
        # 从 evaluate 意图的 IRT 结果中提取
        if "irt_theta" in agent_result:
            theta = agent_result["irt_theta"]
            print(f"[API] LA-044-#3: 从 IRT 结果提取 theta={theta}")
        # 从 user_theta 请求参数回写（如果用户传了）
        elif request.user_theta is not None:
            theta = request.user_theta
            print(f"[API] LA-044-#3: 从请求参数回写 theta={theta}")

    # 2. 提取薄弱点（从对话上下文的答错记录或 streak 信息）
    weak_areas = []
    if isinstance(agent_result, dict) and agent_result.get("metadata"):
        metadata = agent_result["metadata"]
        # 薄弱点可能存储在 metadata 中（由 CoachAgent 或 TutorAgent 标注）
        if metadata.get("weak_areas"):
            weak_areas = metadata["weak_areas"]
            print(f"[API] LA-044-#3: 从 metadata 提取薄弱点={weak_areas}")

    # 3. 如果没有任何可保存的数据，跳过
    if theta is None and not weak_areas:
        print(f"[API] LA-044-#3: 无状态更新（theta=None, weak_areas=[]），跳过保存")
        return

    # 4. 调用 UserStateStore 保存
    # LA-050-Phase4-FIX: 使用用户隔离的 state_store
    try:
        store = _get_isolated_state_store(user_id)
        success = store.update_from_dialog(
            user_id=user_id,
            subject_id=subject_id,
            theta=theta,
            weak_areas=weak_areas if weak_areas else None,
        )
        if success:
            print(f"[API] LA-044-#3: 用户状态自动保存成功")
        else:
            print(f"[API] LA-044-#3: 用户状态自动保存失败")
    except Exception as e:
        print(f"[API] LA-044-#3: 自动保存异常: {e}")
        import traceback
        traceback.print_exc()


@app.get("/api/user-state", response_model=UserStateResponse)
def get_user_state(
    user_id: str,
    subject: str = "generic",
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    """
    LA-044-#3: 获取用户完整状态（全局画像 + 概念级别知识状态）
    LA-050-Phase4: 支持 X-User-ID Header 实现用户隔离。

    参数:
        user_id: 用户ID（URL 参数，向后兼容）
        subject: 学科标识（默认 generic）
        x_user_id: 请求头 X-User-ID（优先于 user_id 参数）

    返回:
        {
            "user_id": "...",
            "subject_id": "...",
            "profile": {...},
            "concept_states": [...],
            "stats": {...}
        }
    """
    # LA-050-Phase4: 优先使用 Header 中的 user_id
    effective_user_id = x_user_id or user_id or "default"
    print(f"\n[API] LA-044-#3/LA-050: GET /api/user-state | user_id={effective_user_id}, subject={subject}")

    if not effective_user_id:
        raise HTTPException(status_code=400, detail="user_id 不能为空")

    try:
        # LA-050-Phase4: 使用用户隔离的 state_store
        store = _get_isolated_state_store(effective_user_id)
        subject_id = f"{subject}_v1"
        state = store.get_full_user_state(effective_user_id, subject_id)
        print(f"[API] LA-044-#3: 返回用户状态 | concepts={len(state['concept_states'])}, "
              f"theta={state['profile']['global_theta']:.2f}")
        return UserStateResponse(**state)
    except Exception as e:
        print(f"[API] LA-044-#3: 获取用户状态失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取用户状态失败: {str(e)}")


@app.post("/api/user-state")
def update_user_state(
    request: UserStateUpdateRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    """
    LA-044-#3: 更新用户全局画像（theta + 薄弱点）
    LA-050-Phase4: 支持 X-User-ID Header 实现用户隔离。

    请求体:
        {
            "user_id": "user123",
            "subject": "rag",
            "global_theta": 0.65,
            "weak_areas": ["向量检索", "BM25"]
        }

    返回:
        {"success": true, "message": "..."}
    """
    # LA-050-Phase4: 优先使用 Header 中的 user_id
    effective_user_id = x_user_id or request.user_id or "default"
    print(f"\n[API] LA-044-#3/LA-050: POST /api/user-state | user_id={effective_user_id}, subject={request.subject}")
    print(f"[API] LA-044-#3: 请求数据: theta={request.global_theta}, weak_areas={request.weak_areas}")

    if not effective_user_id:
        raise HTTPException(status_code=400, detail="user_id 不能为空")

    try:
        # LA-050-Phase4: 使用用户隔离的 state_store
        store = _get_isolated_state_store(effective_user_id)
        subject_id = f"{request.subject}_v1"

        success = store.update_from_dialog(
            user_id=effective_user_id,
            subject_id=subject_id,
            theta=request.global_theta,
            weak_areas=request.weak_areas,
        )

        if success:
            print(f"[API] LA-044-#3: 用户状态更新成功")
            return {"success": True, "message": "用户状态更新成功"}
        else:
            print(f"[API] LA-044-#3: 用户状态更新失败")
            raise HTTPException(status_code=500, detail="用户状态更新失败")
    except Exception as e:
        print(f"[API] LA-044-#3: 更新用户状态异常: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"更新用户状态失败: {str(e)}")


# ========== LA-040-P1-VIS: 评测结果可视化 API ==========

class BarItem(BaseModel):
    """能力条形图单项"""
    concept_id: str
    concept_name: str
    mastery_level: float
    test_count: int
    correct_count: int
    last_tested: Optional[str]
    status: str  # strong / medium / weak
    last_mastery: Optional[float] = None
    change: Optional[float] = None


class VisualizationBarsResponse(BaseModel):
    """能力条形图响应"""
    total_concepts: int
    displayed: int
    items: List[BarItem]
    summary: Dict[str, Any]


@app.get("/api/visualization/bars", response_model=VisualizationBarsResponse)
def get_visualization_bars(
    user_id: str = "default",
    subject: str = "generic",
    sort: str = "mastery_asc",
    limit: int = 20,
    filter_status: str = "all",
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    """
    LA-040-P1-VIS Phase 1: 获取能力条形图数据
    LA-050-Phase4: 支持 X-User-ID Header 实现用户隔离。

    参数:
        user_id: 用户ID（默认 default，向后兼容）
        subject: 学科标识
        sort: 排序方式 — mastery_asc(掌握度升序) / mastery_desc(掌握度降序) / name(名称)
        limit: 返回数量上限
        filter_status: 筛选 — all(全部) / weak(薄弱<40%) / medium(中等40-70%) / strong(强项≥70%)
        x_user_id: 请求头 X-User-ID（优先于 user_id 参数）

    返回:
        各概念的掌握度条形数据，含统计摘要
    """
    # LA-050-Phase4: 优先使用 Header 中的 user_id
    effective_user_id = x_user_id or user_id or "default"
    print(f"\n[API] LA-040-P1-VIS/LA-050: GET /api/visualization/bars | user={effective_user_id}, subject={subject}, sort={sort}, filter={filter_status}")

    try:
        # LA-050-Phase4: 使用用户隔离的 state_store
        store = _get_isolated_state_store(effective_user_id)
        subject_id = f"{subject}_v1"

        # 1. 加载用户的所有概念状态
        states = store.load_by_user(effective_user_id, subject_id)
        print(f"[API] LA-040-P1-VIS: 加载到 {len(states)} 个概念状态")

        if not states:
            print(f"[API] LA-040-P1-VIS: 无数据，返回空结果")
            return VisualizationBarsResponse(
                total_concepts=0,
                displayed=0,
                items=[],
                summary={
                    "strong_count": 0,
                    "medium_count": 0,
                    "weak_count": 0,
                    "avg_mastery": 0.0,
                    "last_evaluated": None
                }
            )

        # 2. 转换为 BarItem 并计算状态
        items = []
        for s in states:
            # 确定状态
            if s.mastery_level >= 0.7:
                status = "strong"
            elif s.mastery_level >= 0.4:
                status = "medium"
            else:
                status = "weak"

            # 计算较上次变化（简化：用 streak 推断趋势）
            change = None
            if s.streak > 0:
                change = 0.05 * s.streak  # 连胜，估算进步
            elif s.streak < 0:
                change = -0.05 * abs(s.streak)  # 连败，估算退步

            items.append(BarItem(
                concept_id=s.canonical_id,
                concept_name=s.canonical_name or s.canonical_id,
                mastery_level=round(s.mastery_level, 2),
                test_count=s.test_count,
                correct_count=s.correct_count,
                last_tested=s.last_tested.isoformat() if s.last_tested else None,
                status=status,
                last_mastery=round(max(0.0, s.mastery_level - (change or 0)), 2) if change else None,
                change=round(change, 2) if change else None
            ))

        # 3. 筛选
        if filter_status != "all":
            items = [it for it in items if it.status == filter_status]
            print(f"[API] LA-040-P1-VIS: 筛选后 {len(items)} 个概念 (filter={filter_status})")

        # 4. 排序
        if sort == "mastery_asc":
            items.sort(key=lambda x: x.mastery_level)
        elif sort == "mastery_desc":
            items.sort(key=lambda x: x.mastery_level, reverse=True)
        elif sort == "name":
            items.sort(key=lambda x: x.concept_name)
        else:
            items.sort(key=lambda x: x.mastery_level)  # 默认升序

        # 5. 截取上限
        total = len(items)
        displayed = min(total, limit)
        items = items[:limit]

        # 6. 统计摘要
        strong_count = sum(1 for it in items if it.status == "strong")
        medium_count = sum(1 for it in items if it.status == "medium")
        weak_count = sum(1 for it in items if it.status == "weak")
        avg_mastery = round(sum(it.mastery_level for it in items) / max(len(items), 1), 3)
        last_evaluated = max(
            (it.last_tested for it in items if it.last_tested),
            default=None
        )

        summary = {
            "strong_count": strong_count,
            "medium_count": medium_count,
            "weak_count": weak_count,
            "avg_mastery": avg_mastery,
            "last_evaluated": last_evaluated
        }

        print(f"[API] LA-040-P1-VIS: 返回 {displayed}/{total} 个概念 | avg_mastery={avg_mastery:.2f}")

        return VisualizationBarsResponse(
            total_concepts=total,
            displayed=displayed,
            items=items,
            summary=summary
        )

    except Exception as e:
        print(f"[API] LA-040-P1-VIS: 获取条形图数据失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取能力条形图失败: {str(e)}")


# ========== LA-040-P2: 评测结果可视化 Phase 2 API ==========

class ProgressDataPoint(BaseModel):
    """进步曲线数据点"""
    date: str
    theta: float
    accuracy: float
    total_questions: int
    correct_count: int


class ProgressResponse(BaseModel):
    """进步曲线响应"""
    user_id: str
    subject: str
    data_points: List[ProgressDataPoint]
    trend: str  # improving / stable / declining
    total_evaluations: int


class WrongAnswerItem(BaseModel):
    """错题本单项"""
    wrong_id: str
    question_text: str
    question_type: str
    user_answer: str
    correct_answer: str
    explanation: str
    concept_name: str
    bloom_level: Optional[str]
    wrong_count: int
    is_mastered: bool
    is_in_review: bool
    first_wrong_at: Optional[str]
    last_wrong_at: str


class WrongAnswerListResponse(BaseModel):
    """错题本列表响应"""
    total: int
    mastered_count: int
    reviewing_count: int
    items: List[WrongAnswerItem]


class UpdateWrongAnswerRequest(BaseModel):
    """更新错题状态请求"""
    is_mastered: Optional[bool] = None
    is_in_review: Optional[bool] = None


@app.get("/api/visualization/progress")
def get_progress_chart(
    user_id: str = "default",
    subject: str = "generic",
    days: int = 30,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    """
    LA-040-P2: 获取进步曲线数据。
    LA-050-Phase4: 支持 X-User-ID Header 实现用户隔离。
    """
    effective_user_id = x_user_id or user_id or "default"
    print(f"[DIAG-ENTER] get_progress_chart called with user_id={effective_user_id}, subject={subject}, days={days}")
    
    from datetime import datetime, timedelta

    from config.settings import KNOWLEDGE_BASE_DIR

    # LA-050-Phase4: 使用用户隔离的 state_store 路径
    store = _get_isolated_state_store(effective_user_id)
    db_path = store.db_path
    subject_id = f"{subject}_v1"
    since = (datetime.now() - timedelta(days=days)).isoformat()

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT theta, accuracy, total_questions, correct_count, evaluated_at
            FROM evaluation_history
            WHERE user_id = ? AND subject_id = ? AND evaluated_at >= ?
            ORDER BY evaluated_at ASC
        """, (effective_user_id, subject_id, since))
        rows = cursor.fetchall()
        conn.close()

        data_points = []
        for row in rows:
            # LA-040-P2-FIX: accuracy 在数据库中存储的是百分比值（如 46.0 = 46%）
            # 需要转换为小数（0-1 范围）供前端统一显示
            raw_accuracy = row[1] or 0.0
            if raw_accuracy > 1:
                accuracy = round(raw_accuracy / 100, 3)
            else:
                accuracy = round(raw_accuracy, 3)
            
            data_points.append(ProgressDataPoint(
                date=row[4][:10] if row[4] else "",  # YYYY-MM-DD
                theta=round(row[0] or 0.0, 3),
                accuracy=accuracy,
                total_questions=row[2] or 0,
                correct_count=row[3] or 0,
            ))

        # 计算趋势
        trend = "stable"
        if len(data_points) >= 3:
            first_half = sum(dp.theta for dp in data_points[:len(data_points)//2]) / max(len(data_points)//2, 1)
            second_half = sum(dp.theta for dp in data_points[len(data_points)//2:]) / max(len(data_points) - len(data_points)//2, 1)
            if second_half > first_half + 0.05:
                trend = "improving"
            elif second_half < first_half - 0.05:
                trend = "declining"

        print(f"[API] LA-040-P2: GET /api/visualization/progress | user={user_id}, points={len(data_points)}, trend={trend}")

        return ProgressResponse(
            user_id=effective_user_id,
            subject=subject,
            data_points=data_points,
            trend=trend,
            total_evaluations=len(data_points)
        )

    except Exception as e:
        print(f"[API] LA-040-P2: 获取进步曲线失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取进步曲线失败: {str(e)}")


@app.get("/api/visualization/wrong-answers")
def get_wrong_answers(
    user_id: str = "default",
    subject: str = "generic",
    concept: str = None,
    mastered: bool = None,
    sort: str = "last_wrong_desc",
    limit: int = 50,
    offset: int = 0,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    LA-040-P2: 获取错题本数据。
    LA-050-Phase4: 支持 X-User-ID Header 实现用户隔离。

    参数:
        user_id: 用户ID
        subject: 学科标识
        concept: 按概念名筛选（可选）
        mastered: 按掌握状态筛选（可选）
        sort: 排序 — last_wrong_desc(最近错题) / wrong_count_desc(错误次数) / first_wrong_asc(最早)
        limit/offset: 分页
    """
    # LA-050-Phase4-FIX: 使用用户隔离的 state_store 路径
    effective_user_id = x_user_id or user_id or "default"
    store = _get_isolated_state_store(effective_user_id)
    db_path = store.db_path
    subject_id = f"{subject}_v1"

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 构建查询
        where_clauses = ["user_id = ?", "subject_id = ?"]
        params = [effective_user_id, subject_id]

        if concept:
            where_clauses.append("concept_name LIKE ?")
            params.append(f"%{concept}%")
        if mastered is not None:
            where_clauses.append("is_mastered = ?")
            params.append(1 if mastered else 0)

        where_sql = " AND ".join(where_clauses)

        # 排序
        order_map = {
            "last_wrong_desc": "last_wrong_at DESC",
            "wrong_count_desc": "wrong_count DESC",
            "first_wrong_asc": "first_wrong_at ASC",
        }
        order_sql = order_map.get(sort, "last_wrong_at DESC")

        # 查询总数
        cursor.execute(f"""
            SELECT COUNT(*) FROM wrong_answers WHERE {where_sql}
        """, params)
        total = cursor.fetchone()[0]

        # 查询数据
        cursor.execute(f"""
            SELECT wrong_id, question_text, question_type, user_answer, correct_answer,
                   explanation, concept_name, bloom_level, wrong_count, is_mastered,
                   is_in_review, first_wrong_at, last_wrong_at
            FROM wrong_answers
            WHERE {where_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
        """, params + [limit, offset])
        rows = cursor.fetchall()
        conn.close()

        items = []
        for row in rows:
            items.append(WrongAnswerItem(
                wrong_id=row[0],
                question_text=row[1] or "",
                question_type=row[2] or "",
                user_answer=row[3] or "",
                correct_answer=row[4] or "",
                explanation=row[5] or "",
                concept_name=row[6] or "",
                bloom_level=row[7],
                wrong_count=row[8] or 1,
                is_mastered=bool(row[9]),
                is_in_review=bool(row[10]),
                first_wrong_at=row[11],
                last_wrong_at=row[12] or "",
            ))

        mastered_count = sum(1 for it in items if it.is_mastered)
        reviewing_count = sum(1 for it in items if it.is_in_review)

        print(f"[API] LA-040-P2: GET /api/visualization/wrong-answers | user={effective_user_id}, total={total}, returned={len(items)}")

        return WrongAnswerListResponse(
            total=total,
            mastered_count=mastered_count,
            reviewing_count=reviewing_count,
            items=items
        )

    except Exception as e:
        print(f"[API] LA-040-P2: 获取错题本失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取错题本失败: {str(e)}")


@app.post("/api/visualization/wrong-answers/{wrong_id}")
def update_wrong_answer(
    wrong_id: str,
    request: UpdateWrongAnswerRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
):
    """
    LA-040-P2: 更新错题状态（标记已掌握 / 加入复习）。
    LA-050-Phase4-FIX: 支持 X-User-ID Header，使用隔离路径，按 user_id 过滤。
    """
    effective_user_id = get_current_user_id(x_user_id, authorization)

    # LA-050-Phase4-FIX: 使用用户隔离的 state_store 路径
    store = _get_isolated_state_store(effective_user_id)
    db_path = store.db_path

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        updates = []
        params = []
        if request.is_mastered is not None:
            updates.append("is_mastered = ?")
            params.append(1 if request.is_mastered else 0)
        if request.is_in_review is not None:
            updates.append("is_in_review = ?")
            params.append(1 if request.is_in_review else 0)

        if not updates:
            raise HTTPException(status_code=400, detail="无更新字段")

        # LA-050-Phase4-FIX: 添加 user_id 条件，防止跨用户修改
        params.append(wrong_id)
        params.append(effective_user_id)
        cursor.execute(f"""
            UPDATE wrong_answers SET {', '.join(updates)} WHERE wrong_id = ? AND user_id = ?
        """, params)
        conn.commit()
        updated = cursor.rowcount
        conn.close()

        if updated == 0:
            raise HTTPException(status_code=404, detail=f"错题记录 {wrong_id} 不存在")

        print(f"[API] LA-040-P2: 更新错题状态: wrong_id={wrong_id[:8]}..., mastered={request.is_mastered}, review={request.is_in_review}")
        return {"success": True, "wrong_id": wrong_id}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] LA-040-P2: 更新错题状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


# ========== LA-040-P3: Bloom 认知雷达图 API ==========

class BloomRadarDimension(BaseModel):
    """Bloom 雷达图单个维度数据"""
    level: str  # remember/understand/apply/analyze/evaluate/create
    name: str   # 记忆/理解/应用/分析/评估/创造
    mastery: Optional[float]  # 掌握度 0-1，null 表示未评估
    wrong_count: int          # 该层次错题数
    bank_count: int           # 题库中该层次总题数
    estimated_attempted: int  # 估计做过的题数


class BloomRadarResponse(BaseModel):
    """Bloom 认知雷达图响应"""
    user_id: str
    subject: str
    dimensions: List[BloomRadarDimension]
    total_evaluated: int       # 总评测题数
    total_correct: int         # 总正确数
    overall_accuracy: float    # 整体正确率
    summary: Dict[str, Any]    # 统计摘要


@app.get("/api/visualization/bloom-radar", response_model=BloomRadarResponse)
def get_bloom_radar(
    user_id: str = "default",
    subject: str = "generic",
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    effective_user_id = x_user_id or user_id or "default"
    """
    LA-040-P3: 获取 Bloom 认知层次雷达图数据。

    基于用户的错题本 + 评测历史 + 题库分布，计算用户在 Bloom 六个认知层次上的掌握度。

    计算逻辑：
    1. 从 wrong_answers 获取各层次错题数
    2. 从 question_bank 获取该学科各层次总题数
    3. 从 evaluation_history 获取总评测题数和正确数
    4. 假设用户做过的题在各层次分布与题库一致，估算掌握度
    """
    import sqlite3
    from config.settings import KNOWLEDGE_BASE_DIR

    # LA-050-Phase4: 使用用户隔离的 state_store 路径
    store = _get_isolated_state_store(effective_user_id)
    db_path = store.db_path
    quiz_bank_path = KNOWLEDGE_BASE_DIR / f"{subject}_quiz_bank.db"
    subject_id = f"{subject}_v1"

    BLOOM_LEVELS = ["remember", "understand", "apply", "analyze", "evaluate", "create"]
    BLOOM_NAMES = {
        "remember": "记忆", "understand": "理解", "apply": "应用",
        "analyze": "分析", "evaluate": "评估", "create": "创造",
    }

    try:
        # 1. 从 evaluation_history 获取总评测数据
        eval_total = 0
        eval_correct = 0
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("""
                SELECT SUM(total_questions), SUM(correct_count)
                FROM evaluation_history
                WHERE user_id = ? AND subject_id = ?
            """, (effective_user_id, subject_id))
            row = cursor.fetchone()
            eval_total = row[0] or 0
            eval_correct = row[1] or 0
            conn.close()
        except Exception as e:
            print(f"[API] LA-040-P3: 读取评测历史失败: {e}")

        # 2. 从 wrong_answers 获取各层次错题数
        wrong_counts = {level: 0 for level in BLOOM_LEVELS}
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("""
                SELECT bloom_level, SUM(wrong_count)
                FROM wrong_answers
                WHERE user_id = ? AND subject_id = ? AND bloom_level IS NOT NULL AND bloom_level != ''
                GROUP BY bloom_level
            """, (effective_user_id, subject_id))
            for row in cursor.fetchall():
                level = row[0].lower() if row[0] else ""
                if level in wrong_counts:
                    wrong_counts[level] = row[1] or 0
            conn.close()
        except Exception as e:
            print(f"[API] LA-040-P3: 读取错题本失败: {e}")

        # 3. 从 question_bank 获取各层次总题数
        bank_counts = {level: 0 for level in BLOOM_LEVELS}
        bank_total = 0
        try:
            if quiz_bank_path.exists():
                conn = sqlite3.connect(str(quiz_bank_path))
                cursor = conn.cursor()
                # 检查表和字段是否存在
                cursor.execute("PRAGMA table_info(question_bank)")
                cols = {c[1] for c in cursor.fetchall()}
                if "bloom_level" in cols:
                    cursor.execute("""
                        SELECT bloom_level, COUNT(*)
                        FROM question_bank
                        WHERE bloom_level IS NOT NULL AND bloom_level != ''
                        GROUP BY bloom_level
                    """)
                    for row in cursor.fetchall():
                        level = row[0].lower() if row[0] else ""
                        if level in bank_counts:
                            bank_counts[level] = row[1] or 0
                    cursor.execute("SELECT COUNT(*) FROM question_bank")
                    bank_total = cursor.fetchone()[0] or 0
                conn.close()
        except Exception as e:
            print(f"[API] LA-040-P3: 读取题库失败: {e}")

        # 4. 计算各层次掌握度
        dimensions = []
        for level in BLOOM_LEVELS:
            bank_count = bank_counts[level]
            wrong_count = wrong_counts[level]
            mastery = None
            estimated_attempted = 0

            if bank_count > 0 and bank_total > 0 and eval_total > 0:
                # 估计该层次做过的题数 = 总评测题数 × 该层次在题库中的占比
                estimated_attempted = round(eval_total * (bank_count / bank_total))
                estimated_correct = max(0, estimated_attempted - wrong_count)
                if estimated_attempted > 0:
                    mastery = round(estimated_correct / estimated_attempted, 2)

            dimensions.append(BloomRadarDimension(
                level=level,
                name=BLOOM_NAMES[level],
                mastery=mastery,
                wrong_count=wrong_count,
                bank_count=bank_count,
                estimated_attempted=estimated_attempted,
            ))

        overall_accuracy = round(eval_correct / eval_total, 2) if eval_total > 0 else 0.0

        # 统计摘要
        strongest = max([d for d in dimensions if d.mastery is not None], key=lambda x: x.mastery, default=None)
        weakest = min([d for d in dimensions if d.mastery is not None], key=lambda x: x.mastery, default=None)

        summary = {
            "strongest_dimension": strongest.name if strongest else None,
            "strongest_mastery": strongest.mastery if strongest else None,
            "weakest_dimension": weakest.name if weakest else None,
            "weakest_mastery": weakest.mastery if weakest else None,
            "dimensions_evaluated": sum(1 for d in dimensions if d.mastery is not None),
        }

        print(f"[API] LA-040-P3: GET /api/visualization/bloom-radar | user={user_id}, subject={subject}, "
              f"evaluated={eval_total}, correct={eval_correct}")

        return BloomRadarResponse(
            user_id=effective_user_id,
            subject=subject,
            dimensions=dimensions,
            total_evaluated=eval_total,
            total_correct=eval_correct,
            overall_accuracy=overall_accuracy,
            summary=summary,
        )

    except Exception as e:
        print(f"[API] LA-040-P3: 获取 Bloom 雷达图失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取 Bloom 雷达图失败: {str(e)}")


# ========== LA-040-P3: 学习建议面板 API ==========

class RecommendationItem(BaseModel):
    """学习建议单项"""
    concept_name: str
    mastery_level: float           # 估算掌握度 0-1
    wrong_count: int               # 该概念错题数
    last_tested: Optional[str]     # 最近测试时间
    reason: str                    # 推荐理由
    actions: List[Dict[str, str]]  # 推荐操作 [{"label": "去复习", "action": "tutor"}, ...]


class RecommendationsResponse(BaseModel):
    """学习建议响应"""
    user_id: str
    subject: str
    total_weak: int
    items: List[RecommendationItem]


@app.get("/api/visualization/recommendations", response_model=RecommendationsResponse)
def get_recommendations(
    user_id: str = "default",
    subject: str = "generic",
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    effective_user_id = x_user_id or user_id or "default"
    """
    LA-040-P3: 获取基于薄弱点的学习建议。

    逻辑：
    1. 从 wrong_answers 按 concept_name 聚合，找出错题最多的薄弱概念
    2. 结合 mastery_level（估算）排序
    3. 为每个薄弱概念生成推荐操作（去复习 / 去练习）
    """
    import sqlite3
    from config.settings import KNOWLEDGE_BASE_DIR

    # LA-050-Phase4: 使用用户隔离的 state_store 路径
    store = _get_isolated_state_store(effective_user_id)
    db_path = store.db_path
    subject_id = f"{subject}_v1"

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 按 concept_name 聚合错题（未掌握的）
        cursor.execute("""
            SELECT concept_name,
                   SUM(wrong_count) as total_wrong,
                   MAX(last_wrong_at) as last_wrong,
                   COUNT(*) as question_count
            FROM wrong_answers
            WHERE user_id = ? AND subject_id = ? AND is_mastered = 0
              AND concept_name IS NOT NULL AND concept_name != ''
            GROUP BY concept_name
            ORDER BY total_wrong DESC, last_wrong DESC
            LIMIT 10
        """, (effective_user_id, subject_id))
        rows = cursor.fetchall()
        conn.close()

        items = []
        for row in rows:
            concept_name = row[0]
            wrong_count = row[1] or 0
            last_wrong = row[2]
            q_count = row[3] or 1

            # 估算掌握度：错题越多，掌握度越低
            # 简单公式：1 / (1 + wrong_count / q_count)，即每题平均错题越多掌握度越低
            avg_wrong = wrong_count / q_count
            mastery = max(0.0, 1.0 - avg_wrong * 0.3)

            if mastery >= 0.7:
                reason = f"该概念掌握较好，仅有 {wrong_count} 次错题，建议巩固复习"
            elif mastery >= 0.4:
                reason = f"该概念掌握一般，有 {wrong_count} 次错题，建议重点复习"
            else:
                reason = f"该概念是薄弱点，累计错题 {wrong_count} 次，建议立即针对性学习"

            items.append(RecommendationItem(
                concept_name=concept_name,
                mastery_level=round(mastery, 2),
                wrong_count=wrong_count,
                last_tested=last_wrong,
                reason=reason,
                actions=[
                    {"label": "📖 去复习", "action": "tutor", "topic": concept_name},
                    {"label": "📝 去练习", "action": "quiz", "topic": concept_name},
                ]
            ))

        print(f"[API] LA-040-P3: GET /api/visualization/recommendations | user={user_id}, "
              f"subject={subject}, weak_concepts={len(items)}")

        return RecommendationsResponse(
            user_id=effective_user_id,
            subject=subject,
            total_weak=len(items),
            items=items,
        )

    except Exception as e:
        print(f"[API] LA-040-P3: 获取学习建议失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取学习建议失败: {str(e)}")


# ========== 诊断端点：列出所有已注册路由 ==========
@app.get("/api/debug/routes")
def debug_list_routes():
    """诊断端点：列出所有已注册路由"""
    routes = []
    for route in app.routes:
        if hasattr(route, 'path'):
            routes.append({
                "path": route.path,
                "methods": list(route.methods) if hasattr(route, 'methods') else [],
                "name": route.name if hasattr(route, 'name') else ""
            })
    return {"total": len(routes), "routes": routes}


# ========== LA-040-P2-FIX: 直接注册路由（绕过可能的装饰器问题） ==========
# 确保 visualization 路由被正确注册
print(f"[DIAG] Routes before add_api_route fix: {len(app.routes)}")

# 手动注册进步曲线路由（如果尚未注册）
try:
    if not any(hasattr(r, 'path') and r.path == '/api/visualization/progress' for r in app.routes):
        print("[DIAG] Manually adding /api/visualization/progress")
        app.add_api_route(
            "/api/visualization/progress",
            get_progress_chart,
            methods=["GET"],
            response_model=ProgressResponse,
        )
    else:
        print("[DIAG] /api/visualization/progress already registered")

    # 手动注册错题本路由（如果尚未注册）
    if not any(hasattr(r, 'path') and r.path == '/api/visualization/wrong-answers' for r in app.routes):
        print("[DIAG] Manually adding /api/visualization/wrong-answers")
        app.add_api_route(
            "/api/visualization/wrong-answers",
            get_wrong_answers,
            methods=["GET"],
            response_model=WrongAnswerListResponse,
        )
    else:
        print("[DIAG] /api/visualization/wrong-answers already registered")

    # LA-040-P3-FIX: 手动注册 Bloom 雷达图路由（如果尚未注册）
    if not any(hasattr(r, 'path') and r.path == '/api/visualization/bloom-radar' for r in app.routes):
        print("[DIAG] Manually adding /api/visualization/bloom-radar")
        app.add_api_route(
            "/api/visualization/bloom-radar",
            get_bloom_radar,
            methods=["GET"],
            response_model=BloomRadarResponse,
        )
    else:
        print("[DIAG] /api/visualization/bloom-radar already registered")

    # LA-040-P3-FIX: 手动注册学习建议路由（如果尚未注册）
    if not any(hasattr(r, 'path') and r.path == '/api/visualization/recommendations' for r in app.routes):
        print("[DIAG] Manually adding /api/visualization/recommendations")
        app.add_api_route(
            "/api/visualization/recommendations",
            get_recommendations,
            methods=["GET"],
            response_model=RecommendationsResponse,
        )
    else:
        print("[DIAG] /api/visualization/recommendations already registered")

    print(f"[DIAG] Routes after add_api_route fix: {len(app.routes)}")
except Exception as e:
    print(f"[DIAG] add_api_route fix failed: {e}")
    import traceback
    traceback.print_exc()

# LA-040-P2-FIX-ULTIMATE: 添加一个通配符路由来捕获所有 /api/visualization/* 请求
from starlette.requests import Request

@app.get("/api/visualization/{path:path}")
def visualization_catch_all(path: str, request: Request):
    """
    LA-040-P2: 临时通配符路由，捕获所有 visualization 子路径。
    根据 path 分发到正确的处理函数。
    """
    print(f"[DIAG-CATCH-ALL] path={path}, full_url={request.url}")
    
    if path == "progress":
        return get_progress_chart(
            user_id=request.query_params.get("user_id", "anonymous"),
            subject=request.query_params.get("subject", "generic"),
            days=int(request.query_params.get("days", 30)),
            x_user_id=request.headers.get("X-User-ID")
        )
    elif path == "wrong-answers":
        return get_wrong_answers(
            user_id=request.query_params.get("user_id", "anonymous"),
            subject=request.query_params.get("subject", "generic"),
            concept=request.query_params.get("concept"),
            mastered=request.query_params.get("mastered"),
            sort=request.query_params.get("sort", "last_wrong_desc"),
            limit=int(request.query_params.get("limit", 50)),
            offset=int(request.query_params.get("offset", 0)),
            x_user_id=request.headers.get("X-User-ID")
        )
    elif path == "bloom-radar":
        return get_bloom_radar(
            user_id=request.query_params.get("user_id", "anonymous"),
            subject=request.query_params.get("subject", "generic"),
            x_user_id=request.headers.get("X-User-ID")
        )
    elif path == "recommendations":
        return get_recommendations(
            user_id=request.query_params.get("user_id", "anonymous"),
            subject=request.query_params.get("subject", "generic"),
            x_user_id=request.headers.get("X-User-ID")
        )
    else:
        raise HTTPException(status_code=404, detail=f"Unknown visualization path: {path}")

# ========== LA-040-P3-ROOT-CAUSE-FIX: 重排路由确保 API 优先于 Mount ==========
# 问题：app.mount("/", StaticFiles(...)) 在 Starlette 路由列表中排在 API 路由之前，
# 导致所有请求先匹配 Mount，StaticFiles 找不到文件返回 404。
# 修复：将所有 Mount 路由移到列表末尾，确保 API 路由优先匹配。
from starlette.routing import Mount

print(f"[DIAG] Reordering routes: {len(app.routes)} total routes")
# 分离 Mount 和非 Mount 路由
non_mount_routes = [r for r in app.routes if not isinstance(r, Mount)]
mount_routes = [r for r in app.routes if isinstance(r, Mount)]
print(f"[DIAG]   Non-Mount routes: {len(non_mount_routes)}")
print(f"[DIAG]   Mount routes: {len(mount_routes)}")
# API 路由在前，Mount 路由在后
# app.routes 是只读属性，直接修改底层 router.routes
app.router.routes = non_mount_routes + mount_routes
print(f"[DIAG] Routes after reorder: {len(app.router.routes)}")
# 验证关键路由的顺序
for i, route in enumerate(app.router.routes):
    if hasattr(route, 'path') and 'visualization' in route.path:
        print(f"[DIAG]   Route {i}: {route.path}")

# ========== 启动入口 ==========

if __name__ == "__main__":
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
