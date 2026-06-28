# LearnAnything API 设计文档

> 后端: `app/backend_api.py` (FastAPI)  
> 测试前端: `web/test_frontend.html`

---

## 接口总览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/ask` | 智能问答 |
| POST | `/api/quiz` | 生成题目 |
| POST | `/api/evaluate/start` | 开始评测（出题） |
| POST | `/api/evaluate/submit` | 提交评测答案（评分） |
| POST | `/api/import/text` | 导入文本材料 |
| POST | `/api/import/file` | 上传文件导入 |
| GET | `/api/subjects` | 列出已配置学科 |
| GET | `/api/subjects/{subject}` | 获取学科配置 |
| POST | `/api/subjects/{subject}/analyze` | 分析材料并生成学科配置 |
| GET | `/api/knowledge-base/{subject}/stats` | 知识库统计 |
| GET | `/` | API 根信息 |

---

## 详细接口说明

### 1. 健康检查

```
GET /api/health
```

**响应：**
```json
{
  "status": "ok",
  "service": "learnanything-backend",
  "version": "1.0.0",
  "uptime_seconds": 120.5
}
```

---

### 2. 智能问答

```
POST /api/ask
```

**请求：**
```json
{
  "query": "什么是 RAG？",
  "subject": "generic",
  "user_id": "user_001",
  "session_id": null
}
```

**响应：**
```json
{
  "question": "什么是 RAG？",
  "answer": "RAG（Retrieval-Augmented Generation）是一种...",
  "intent": {
    "original": "concept",
    "resolved": "concept",
    "confidence": 1.0,
    "fallback": false
  },
  "agent": "TutorAgent",
  "duration_ms": 850.5,
  "query_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

### 3. 出题

```
POST /api/quiz
```

**请求：**
```json
{
  "topic": "RAG 技术",
  "subject": "generic",
  "count": 5
}
```

**响应：**
```json
{
  "topic": "RAG 技术",
  "questions": [
    {
      "id": 1,
      "type": "single_choice",
      "question": "RAG 的核心思想是什么？（单选题）",
      "options": ["A. 纯生成", "B. 检索+生成", "C. 纯检索", "D. 微调模型"],
      "answer": "B",
      "explanation": "RAG 结合了检索和生成技术..."
    }
  ],
  "subject_name": "通用",
  "question_types": ["single_choice", "short_answer"]
}
```

---

### 4. 评测（两步流程）

#### 4.1 开始评测 — 生成题目

```
POST /api/evaluate/start
```

**请求：**
```json
{
  "topic": "RAG 技术",
  "subject": "generic",
  "count": 5
}
```

**响应：**
```json
{
  "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "topic": "RAG 技术",
  "subject_name": "通用",
  "questions": [...],
  "instructions": "【能力评测】..."
}
```

> **注意：** 前端需要保存 `session_id`，后续提交答案时使用。

#### 4.2 提交答案 — 自动评分

```
POST /api/evaluate/submit
```

**请求：**
```json
{
  "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "answers": ["B", "A", "RAG 是检索增强生成技术"]
}
```

**响应：**
```json
{
  "total_score": 45,
  "max_score": 60,
  "percentage": 75.0,
  "correct_count": 2,
  "total_questions": 3,
  "level": "良好",
  "summary": "本次评测共 3 题...",
  "weak_areas": ["short_answer"],
  "strong_areas": ["single_choice"],
  "details": [
    {
      "id": 1,
      "type": "single_choice",
      "question": "RAG 的核心思想...",
      "user_answer": "B",
      "correct_answer": "B",
      "score": 20,
      "max_score": 20,
      "is_correct": true,
      "feedback": "回答正确！"
    }
  ]
}
```

**评分策略：**

| 题型 | 评分方式 | 回退 |
|------|----------|------|
| 单选/多选/判断 | 精确匹配 | 无 |
| 填空 | 关键词匹配 | 无 |
| 简答/论述 | LLM-as-judge | 关键词匹配 |
| 计算/推导 | LLM 判断公式等价 | 关键词匹配 |
| 编程 | LLM 判断代码逻辑 | 关键词匹配 |

---

### 5. 导入材料

#### 5.1 导入文本

```
POST /api/import/text
```

**请求：**
```json
{
  "subject": "generic",
  "text": "RAG 是一种...",
  "source_name": "user_notes"
}
```

**响应：**
```json
{
  "subject": "generic",
  "chunks_added": 3,
  "total_documents": 15,
  "message": "成功导入 3 个文本片段到「generic」知识库"
}
```

#### 5.2 上传文件

```
POST /api/import/file
Content-Type: multipart/form-data
```

**参数：**
- `subject` (string): 学科标识
- `file` (file): 上传文件（.txt, .md, .pdf, .png, .jpg）

**响应：**
```json
{
  "subject": "chemistry",
  "filename": "chem_notes.pdf",
  "chunks_added": 12,
  "total_documents": 45,
  "message": "成功导入「chem_notes.pdf」，生成 12 个知识片段"
}
```

---

### 6. 学科管理

#### 6.1 列出学科

```
GET /api/subjects
```

**响应：**
```json
{
  "subjects": [
    { "subject": "generic", "name": "通用", "description": "" },
    { "subject": "chemistry", "name": "化学", "description": "基于 12 个知识片段自动分析" }
  ]
}
```

#### 6.2 获取学科配置

```
GET /api/subjects/chemistry
```

**响应：**
```json
{
  "subject": "chemistry",
  "name": "化学",
  "description": "基于 12 个知识片段自动分析",
  "question_types": { "single_choice": {...}, "calculation": {...} },
  "difficulty_levels": { "easy": {...}, "medium": {...}, "hard": {...} },
  "special_features": ["formula_heavy"]
}
```

#### 6.3 分析材料并生成配置

```
POST /api/subjects/{subject}/analyze
```

**请求：**
```json
{
  "subject": "chemistry",
  "text": "化学键是...",
  "source_name": "analysis_input"
}
```

**响应：**
```json
{
  "subject": "chemistry",
  "config_path": "config/subjects/chemistry.json",
  "name": "化学",
  "question_types": ["single_choice", "calculation", "fill_blank"],
  "difficulty_levels": ["easy", "medium", "hard"],
  "special_features": ["formula_heavy"],
  "analysis_basis": { "sample_chunks": 5, "formula_density": 2.5 }
}
```

---

### 7. 知识库统计

```
GET /api/knowledge-base/{subject}/stats
```

**响应：**
```json
{
  "subject": "generic",
  "collection": "generic_v1",
  "document_count": 45,
  "status": "active"
}
```

---

## 启动方式

### 方式 1: 直接运行（开发调试）

```bash
cd D:\MyCS\AI\Project\LearnAnything
python -m app.backend_api
# 默认监听 127.0.0.1:5000
```

### 方式 2: Uvicorn 启动（推荐）

```bash
uvicorn app.backend_api:app --host 127.0.0.1 --port 5000 --reload
```

### 方式 3: 指定端口

```bash
python -m app.backend_api 8000
```

---

## 测试前端

```bash
# 启动后端后，在浏览器中打开
python -m http.server 8080 --directory web
# 然后访问 http://localhost:8080/test_frontend.html
```

或者直接在后端挂载静态文件（取消 backend_api.py 中的注释）：

```python
WEB_DIR = PROJECT_ROOT / "web"
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="static")
```

---

## 前端集成要点

### 1. 跨域
后端已配置 CORS，允许所有来源 (`allow_origins=["*"]`)。生产环境应限制为实际域名。

### 2. 会话管理
评测使用两步流程（start → submit），需要前端保存 `session_id`。

### 3. 文件上传
文件上传使用 `multipart/form-data`，示例：

```javascript
const form = new FormData();
form.append('subject', 'chemistry');
form.append('file', fileInput.files[0]);

fetch('/api/import/file', {
  method: 'POST',
  body: form
});
```

### 4. 错误处理
后端统一返回 HTTP 状态码 + JSON 错误信息：

```json
{
  "detail": "学科「chemistry」配置不存在"
}
```

---

## 与桌面封装器集成

`desktop_app.py` 只需将 `backend_script` 指向新的 API 入口：

```python
backend_script = project_root / "app" / "backend_api.py"
```

前端页面放在 `web/` 目录中，后端挂载为静态文件，WebView 直接加载 `http://127.0.0.1:5000/` 即可。

---

## 后续扩展

| 功能 | 建议实现 |
|------|----------|
| 用户认证 | 添加 JWT 中间件，保护敏感接口 |
| 会话持久化 | 用 Redis 替代内存字典 `_eval_sessions` |
| 流式输出 | 对 `/api/ask` 添加 SSE 流式响应 |
| 文件上传进度 | 前端用 XMLHttpRequest + progress 事件 |
| 知识库可视化 | 添加 `/api/knowledge-base/{subject}/chunks` 返回片段列表 |
| 监控数据 | 暴露 `/api/monitoring/stats` 返回查询统计 |
