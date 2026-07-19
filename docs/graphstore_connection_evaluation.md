
# GraphStore 连接管理方案评估

## 一、当前方案（全局共享 GraphStore）的实际情况

### 谁持有 KuzuDB 连接？

```
backend_api.py 启动后:
  ┌─────────────────┐
  │ FastAPI 进程    │  ← 单进程（默认 uvicorn，1 worker）
  │  ┌──────────┐  │
  │  │ _graph_store_cache = {}  │  ← 全局变量，进程内共享
  │  │  "rag_v1" → GraphStore → kuzu.Connection (db: rag_v1_graph) │
  │  │  "transformer_v1" → GraphStore → kuzu.Connection │
  │  └──────────┘  │
  │                 │
  │  /api/quiz ──→ Coordinator(g.shared_graph) → QuizAgent
  │  /api/knowledge-graph/nodes ──→ GraphStore(rag_v1)  → 同一个实例
  │  /api/knowledge-graph/build ──→ GraphStore(rag_v1)  → 同一个实例
  │  /api/subgraph/{id} ──→ GraphStore(rag_v1)  → 同一个实例
  │  /api/import/file ──→ GraphStore(rag_v1) → init_schema + add_chunk_nodes
  │  ...
  └─────────────────┘
```

### 关键事实

1. **FastAPI 默认是单进程**（uvicorn 单 worker）
   - 在单进程内，全局变量是共享的
   - 多个 API 端点访问同一个 `GraphStore` 实例 → 同一个 `kuzu.Database` 连接
   - 这意味着只有一个物理 KuzuDB 文件连接

2. **asyncio 的协程是单线程的**
   - 如果 `GraphStore` 的方法是同步阻塞的（调用 `conn.execute`），同一时间只有一个协程执行
   - 所以即使多个请求同时来，也不会并发修改数据库

3. **KuzuDB 的单进程并发访问是安全的**
   - 在同一个进程内的多个线程使用同一个 `kuzu.Database` 实例是安全的
   - 但 KuzuDB 明确不支持**多进程**同时打开同一个数据库文件

4. **P0 流程是只读的**
   - `ConceptRetriever.resolve()`: 读取概念 → 只读
   - `SubgraphBuilder.build()`: 读取边和节点 → 只读
   - `ContextAssembler.assemble()`: 读取文本 → 只读
   - 只有 `/api/knowledge-graph/{subject}/build` 和 `/api/import/file` 是写入操作

---

## 二、用户担忧的实际场景分析

### 场景 A：出题请求和知识图谱查询并发

```
请求1: GET /api/knowledge-graph/rag_v1/nodes  → 读取节点列表
请求2: POST /api/quiz                        → 读取概念 → 构建子图 → 组装上下文
```

- 两者都是**只读**操作
- 共享同一个 `GraphStore` 连接
- 不存在数据不一致问题（KuzuDB 的 MVCC 保证读一致性）

### 场景 B：导入新文档时其他请求在读取

```
请求1: POST /api/import/file                → 写入 chunks + 边
请求2: GET /api/knowledge-graph/rag_v1/nodes  → 读取节点列表
```

- 这里可能有**读写冲突**
- KuzuDB 的写入是 ACID 的，但**正在写入的事务**可能不会被同时进行的读取看到
- 如果写入耗时较长，读取可能读到旧数据或等待写入完成

### 场景 C：用户编辑图谱（未来功能）

```
请求1: POST /api/knowledge-graph/rag_v1/edit  → 修改节点/边
请求2: GET /api/knowledge-graph/rag_v1/nodes  → 读取节点列表
```

- 如果读取发生在写入的同一事务中，可能看到不一致状态
- 但如果写入后事务提交，后续读取看到新数据

### 场景 D：多进程部署（gunicorn workers > 1）

```
进程1: uvicorn worker 1 → GraphStore(rag_v1) → 打开 rag_v1_graph
进程2: uvicorn worker 2 → GraphStore(rag_v1) → 尝试打开 rag_v1_graph → 错误！
```

- KuzuDB 不支持多进程同时打开同一个文件
- 这是**致命问题**，当前方案无法解决

---

## 三、用户提出的中间模块方案评估

### 方案设计

```
                    ┌─────────────────┐
                    │  FastAPI 进程   │
                    │                 │
  /api/quiz ──→  ┌──────┐           │
  /api/nodes ──→ │ 消息队列 │ ──→  │  │
  /api/build ──→ │ asyncio.Queue │  │  │
  /api/import ──→└──────┘         │  │
                    │              │  │
                    │  ┌──────────┐  │  │
                    │  │ 中间模块 │  │  │  ← 守护线程/异步任务
                    │  │ (DatabaseManager) │  │  │
                    │  │              │  │  │
                    │  │ 串行消费队列    │  │  │
                    │  │ 单一 KuzuDB 连接 │  │  │
                    │  └──────────┘  │  │
                    │              │  │
                    │  ┌──────────┐  │  │
                    │  │ KuzuDB   │  │  │
                    │  │ rag_v1_graph │  │  │
                    │  └──────────┘  │  │
                    └─────────────────┘
```

### 优点

1. **真正的串行化**：所有数据库操作排队执行，不会有任何并发冲突
2. **单一连接点**：只有中间模块持有数据库连接，其他组件不直接接触数据库
3. **统一事务管理**：可以在中间模块实现事务包装（开始 → 执行 → 提交/回滚）
4. **错误隔离**：数据库连接异常可以集中处理，其他请求不受影响
5. **连接管理**：可以统计连接使用情况，实现连接池（未来扩展到多数据库）

### 缺点与风险

| 问题 | 严重程度 | 说明 |
|------|---------|------|
| **复杂度** | 🔴 高 | 需要重写所有数据库访问为异步消息模式；GraphStore 的每个方法都需要改为 "发送消息 → 等待响应" |
| **性能下降** | 🟡 中 | 串行处理 vs. 并行处理。如果读取操作很多（如 `/api/nodes` 返回 500+ 节点），队列会阻塞后续请求。需要区分读写队列 |
| **超时/阻塞** | 🟡 中 | 如果写入操作（如导入大文档）耗时 30 秒，队列中所有请求都等待。需要超时机制 + 异步写入（后台任务） |
| **错误处理** | 🟡 中 | 请求失败后的重试、超时、死锁检测。消息队列需要完整的生命周期管理 |
| **调试难度** | 🟡 中 | 排查问题需要查看队列状态、消息日志，增加一层抽象 |
| **KuzuDB 多进程限制** | 🔴 未解决 | 中间模块仍然只能在一个进程中运行。如果部署为多进程（gunicorn），中间模块只能在其中一个进程，其他进程需要通过 IPC（如 ZeroMQ、HTTP）连接中间模块，这就变成微服务架构了 |
| **FastAPI 异步兼容** | 🟡 中 | 中间模块需要与 FastAPI 的 asyncio 兼容。如果 KuzuDB 是同步阻塞的，需要 run_in_executor |

### 方案变体：读写分离队列

```
┌──────────────┐   ┌──────────────┐
│ 读队列 (R)    │   │ 写队列 (W)   │  ← 允许多读并发，但读写互斥
│ 允许多并发    │   │ 串行执行     │
└──────────────┘   └──────────────┘
```

- 读操作可以并行（KuzuDB 支持多 reader）
- 写操作串行，且写时阻塞所有读
- 但这需要 KuzuDB 显式支持读写锁，KuzuDB 是否有这个特性不确定

---

## 四、替代方案评估

### 方案 A：当前方案 + asyncio.Lock（最轻量）

```python
_graph_store_cache = {}
_graph_store_locks = {}

async def get_graph_store_with_lock(subject: str) -> GraphStore:
    key = f"{subject}_v1"
    if key not in _graph_store_cache:
        _graph_store_cache[key] = GraphStore(key)
    if key not in _graph_store_locks:
        _graph_store_locks[key] = asyncio.Lock()
    return _graph_store_cache[key], _graph_store_locks[key]

# 写入时加锁
async def import_document(subject, data):
    store, lock = await get_graph_store_with_lock(subject)
    async with lock:
        store.add_chunk_nodes(data)  # 串行写入
    
# 读取时无锁（或共享锁）
async def get_nodes(subject):
    store, lock = await get_graph_store_with_lock(subject)
    return store.get_chunk_nodes()  # 并发读取
```

- **优点**：实现简单，不需要额外模块，性能影响最小
- **缺点**：只解决单进程并发写入问题；不解决多进程部署问题
- **适用**：如果确定单进程部署，这是最佳方案

### 方案 B：中间模块（用户提出的方案）

- **优点**：最彻底，单一连接点，统一事务管理
- **缺点**：实现复杂，性能可能下降，需要异步适配
- **适用**：如果数据库访问模式复杂，需要事务管理，或未来扩展多数据库

### 方案 C：进程级单例 + 多进程不可用的明确约束（实际方案）

```python
# 在启动时创建 GraphStore，后续使用同一个
_graph_store_singleton = {}

def init_graph_stores(app: FastAPI):
    """应用启动时预创建所有 GraphStore"""
    for subject in ["rag", "transformer", "generic"]:
        _graph_store_singleton[f"{subject}_v1"] = GraphStore(f"{subject}_v1")

def get_graph_store(subject: str) -> GraphStore:
    return _graph_store_singleton[f"{subject}_v1"]
```

- **优点**：生命周期清晰，启动时创建，运行时只使用不创建
- **缺点**：启动时加载所有学科，内存开销大；新学科需要重启
- **适用**：学科数量有限，且需要严格控制数据库生命周期

### 方案 D：使用 KuzuDB 的 Read-Only 模式（如果支持）

- 如果 KuzuDB 支持只读连接，可以为只读操作创建额外的只读连接
- 写入操作使用唯一的主连接
- 但这取决于 KuzuDB 的实现，不确定是否支持

---

## 五、我的建议

### 短期（当前场景）：方案 A（当前方案 + asyncio.Lock）

```python
# 在 backend_api.py 的 get_graph_store 基础上增加锁

_graph_store_cache = {}
_graph_store_locks = {}

async def get_graph_store(subject: str) -> GraphStore:
    key = f"{subject}_v1"
    if key not in _graph_store_cache:
        _graph_store_cache[key] = GraphStore(key)
        _graph_store_locks[key] = asyncio.Lock()
        print(f"[API] Created shared GraphStore for {key}")
    return _graph_store_cache[key]

async def get_graph_lock(subject: str) -> asyncio.Lock:
    key = f"{subject}_v1"
    if key not in _graph_store_locks:
        _graph_store_locks[key] = asyncio.Lock()
    return _graph_store_locks[key]
```

- 写入操作（import, build）使用 `async with lock:`
- 读取操作（quiz, nodes, subgraph）不使用锁
- 这解决了场景 B（并发读写）的问题，且不引入额外复杂度

### 长期（如果多进程部署）：方案 C + 外部服务

```
如果必须使用多进程（gunicorn）：
  ┌──────────────┐
  │ 进程1 (worker) │ ──HTTP──→ ┌──────────────┐
  │ 进程2 (worker) │ ──HTTP──→ │ KuzuDB 服务   │  ← 单独进程，只此一个连接
  │ 进程3 (worker) │ ──HTTP──→ │ 封装 REST API  │
  │ 进程4 (worker) │ ──HTTP──→ └──────────────┘
  └──────────────┘              │
                                ↓
                          ┌──────────────┐
                          │ KuzuDB 文件  │
                          └──────────────┘
```

- 但这实际上是微服务架构，与当前架构差异太大

### 中间模块方案的适用条件

只有当以下条件全部满足时，才值得实现中间模块：
1. 单进程无法满足性能需求（必须多进程/多机器）
2. 数据库操作需要复杂的事务管理（跨多个表/节点的原子操作）
3. 需要连接多个数据库（KuzuDB + SQLite + 其他）
4. 团队有足够资源维护这一层抽象

**当前条件：**
- 条件 1：否（FastAPI 单进程足够）
- 条件 2：否（KuzuDB 事务支持有限，当前操作比较简单）
- 条件 3：否（只有 KuzuDB）
- 条件 4：否（资源有限，需要快速推进）

**结论：不建议实现中间模块，建议方案 A（加锁）即可。**

---

## 六、实施建议（如果采纳方案 A）

需要修改的点：

1. `backend_api.py` 的 `get_graph_store`：改为 `async def`，增加 `asyncio.Lock`
2. `import_document` 和 `build_knowledge_graph` 端点：加锁
3. 其他只读端点：不加锁（保持并发）

```python
# 在 backend_api.py 中

import asyncio

_graph_store_cache = {}
_graph_store_locks: Dict[str, asyncio.Lock] = {}

async def get_graph_store(subject: str) -> GraphStore:
    key = f"{subject}_v1"
    if key not in _graph_store_cache:
        _graph_store_cache[key] = GraphStore(key)
        _graph_store_locks[key] = asyncio.Lock()
    return _graph_store_cache[key]

async def get_graph_lock(subject: str) -> asyncio.Lock:
    key = f"{subject}_v1"
    if key not in _graph_store_locks:
        _graph_store_locks[key] = asyncio.Lock()
    return _graph_store_locks[key]

# 在写入端点中（如 import）
@app.post("/api/import/file")
async def import_file(request: ImportFileRequest):
    lock = await get_graph_lock(request.subject)
    async with lock:
        store = await get_graph_store(request.subject)
        store.add_chunk_nodes(docs)
        store.build_belongs_to_relations()
```

