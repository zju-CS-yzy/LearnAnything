"""
LA-040-P0: 测试 Fixture

为 ConceptRetriever 和 SubgraphBuilder 提供测试数据和 mock 数据库
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
import kuzu

sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

# Monkey-patch kuzu.Database to use small buffer pool for tests
# 避免默认 8TB buffer pool 导致内存分配失败
_original_kuzu_database = kuzu.Database.__init__

def _patched_kuzu_database(self, database_path=None, *, buffer_pool_size=0, max_num_threads=0, compression=True, lazy_init=False, read_only=False, max_db_size=1073741824, auto_checkpoint=True, checkpoint_threshold=-1):
    """使用 1GB max_db_size 和 64MB buffer_pool_size 进行测试"""
    if buffer_pool_size == 0:
        buffer_pool_size = 64 * 1024 * 1024  # 64MB
    if max_db_size == 1073741824:
        max_db_size = 1073741824  # 1GB
    _original_kuzu_database(self, database_path, buffer_pool_size=buffer_pool_size, max_num_threads=max_num_threads, compression=compression, lazy_init=lazy_init, read_only=read_only, max_db_size=max_db_size, auto_checkpoint=auto_checkpoint, checkpoint_threshold=checkpoint_threshold)

kuzu.Database.__init__ = _patched_kuzu_database

from core.graph_store import GraphStore
from core.graph_education.types import ConceptNode, ContextBudget, QuestionPattern
from core.graph_education.concept_retriever import ConceptRetriever
from core.graph_education.subgraph_builder import SubgraphBuilder


# ───────────────────────────────────────────────
# 测试数据库 Fixture
# ───────────────────────────────────────────────

@pytest.fixture(scope="function")
def test_graph_store():
    """
    创建临时测试数据库，每次测试后自动清理
    """
    # 使用临时目录
    temp_dir = Path(tempfile.mkdtemp(prefix="la_test_"))
    db_path = temp_dir / "test_graph"
    
    store = GraphStore(str(db_path))
    store.init_schema(force=True)
    
    # 预填充测试数据
    _seed_test_data(store)
    
    yield store
    
    # 清理
    store._db = None
    store._conn = None
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except:
        pass


def _seed_test_data(store: GraphStore):
    """向测试数据库填充样本数据"""
    
    # 1. 添加 Chunk 节点（底层依赖）
    chunks = [
        {
            "id": "chunk_001",
            "text": "注意力机制是 Transformer 的核心组件",
            "metadata": {"source": "test.pdf", "subject": "test_transformer"},
        },
        {
            "id": "chunk_002", 
            "text": "多头注意力允许模型在不同位置共同关注不同表示子空间",
            "metadata": {"source": "test.pdf", "subject": "test_transformer"},
        },
        {
            "id": "chunk_003",
            "text": "缩放点积注意力通过除以 sqrt(d_k) 防止 softmax 饱和",
            "metadata": {"source": "test.pdf", "subject": "test_transformer"},
        },
    ]
    store.add_chunk_nodes(chunks)
    
    # 2. 添加 CanonicalConcept 节点
    concepts = [
        {
            "canonical_id": "concept_c1_attention",
            "name": "注意力机制",
            "concept_type": "concept",
            "description": "一种让模型自动关注输入中重要部分的技术机制",
            "parent_hint": "",
            "aliases": json.dumps(["Attention Mechanism", "Attention"]),
            "source_chunks": "chunk_001",
        },
        {
            "canonical_id": "concept_c2_mha",
            "name": "多头注意力",
            "concept_type": "technology",
            "description": "并行运行多组注意力计算，允许模型同时关注不同表示子空间",
            "parent_hint": "",
            "aliases": json.dumps(["Multi-Head Attention", "MHA"]),
            "source_chunks": "chunk_002",
        },
        {
            "canonical_id": "concept_c3_scaled_dot",
            "name": "缩放点积注意力",
            "concept_type": "sub_technology",
            "description": "通过缩放点积计算注意力权重，除以 sqrt(d_k) 防止梯度消失",
            "parent_hint": "",
            "aliases": json.dumps(["Scaled Dot-Product Attention"]),
            "source_chunks": "chunk_003",
        },
        {
            "canonical_id": "concept_c4_transformer",
            "name": "Transformer",
            "concept_type": "technology",
            "description": "基于自注意力机制的深度学习模型架构",
            "parent_hint": "",
            "aliases": json.dumps(["Transformer", "Transformer模型"]),
            "source_chunks": "chunk_001",
        },
        {
            "canonical_id": "concept_c5_pos_enc",
            "name": "位置编码",
            "concept_type": "sub_technology",
            "description": "为序列中的每个位置添加位置信息，使模型感知顺序",
            "parent_hint": "",
            "aliases": json.dumps(["Positional Encoding"]),
            "source_chunks": "",
        },
    ]
    
    conn = store._ensure_db()
    for c in concepts:
        cypher = f"""
            CREATE (c:CanonicalConcept {{
                canonical_id: '{c['canonical_id']}',
                name: '{c['name']}',
                concept_type: '{c['concept_type']}',
                description: '{store._escape_cypher_string(c['description'])}',
                parent_hint: '{c['parent_hint']}',
                aliases: '{c['aliases']}',
                source_chunks: '{c['source_chunks']}'
            }})
        """
        store._execute(conn, cypher)
    
    # 3. 添加语义边
    edges = [
        ("concept_c2_mha", "concept_c3_scaled_dot", "DEPENDS_ON", 0.95),
        ("concept_c2_mha", "concept_c1_attention", "SOLUTION", 0.9),
        ("concept_c3_scaled_dot", "concept_c1_attention", "DEPENDS_ON", 0.95),
        ("concept_c4_transformer", "concept_c2_mha", "SOLUTION", 0.9),
        ("concept_c4_transformer", "concept_c5_pos_enc", "DEPENDS_ON", 0.8),
    ]
    
    for src, dst, rel_type, conf in edges:
        cypher = f"""
            MATCH (a:CanonicalConcept {{canonical_id: '{src}'}}), 
                  (b:CanonicalConcept {{canonical_id: '{dst}'}})
            CREATE (a)-[:{rel_type} {{confidence: {conf}}}]->(b)
        """
        store._execute(conn, cypher)


# ───────────────────────────────────────────────
# Mock 缓存
# ───────────────────────────────────────────────

class MockCache:
    """内存缓存，模拟 Redis"""
    
    def __init__(self):
        self._data = {}
    
    def get(self, key: str, default=None):
        return self._data.get(key, default)
    
    def set(self, key: str, value, ttl=None):
        self._data[key] = value
    
    def delete(self, key: str):
        self._data.pop(key, None)
    
    def clear(self):
        self._data.clear()


@pytest.fixture
def mock_cache():
    return MockCache()


# ───────────────────────────────────────────────
# 模块 Fixture
# ───────────────────────────────────────────────

@pytest.fixture
def concept_retriever(test_graph_store, mock_cache):
    """已初始化的 ConceptRetriever，连接测试数据库"""
    return ConceptRetriever(
        graph_store=test_graph_store,
        vector_store=None,  # P0 阶段不使用 Embedding 回退
        cache=mock_cache
    )


@pytest.fixture
def subgraph_builder(test_graph_store, mock_cache):
    """已初始化的 SubgraphBuilder，连接测试数据库"""
    return SubgraphBuilder(
        graph_store=test_graph_store,
        centrality_cache=mock_cache
    )


@pytest.fixture
def sample_concept_nodes(test_graph_store):
    """返回测试数据库中的 ConceptNode 列表"""
    # 从数据库加载所有概念
    conn = test_graph_store._ensure_db()
    cypher = """
        MATCH (c:CanonicalConcept)
        RETURN c.canonical_id, c.name, c.concept_type, c.description, c.parent_hint, c.aliases
    """
    result = test_graph_store._execute(conn, cypher)
    
    nodes = []
    while result.has_next():
        row = result.get_next()
        aliases = []
        if row[5]:
            try:
                aliases = json.loads(row[5])
            except:
                pass
        nodes.append(ConceptNode(
            canonical_id=row[0],
            name=row[1],
            concept_type=row[2] or "concept",
            description=row[3] or "",
            parent_hint=row[4] or "",
            aliases=aliases,
        ))
    
    return nodes


@pytest.fixture
def attention_concept(sample_concept_nodes):
    """返回'注意力机制'概念节点"""
    for n in sample_concept_nodes:
        if n.name == "注意力机制":
            return n
    pytest.fail("测试数据缺少'注意力机制'概念")


@pytest.fixture
def mha_concept(sample_concept_nodes):
    """返回'多头注意力'概念节点"""
    for n in sample_concept_nodes:
        if n.name == "多头注意力":
            return n
    pytest.fail("测试数据缺少'多头注意力'概念")


@pytest.fixture
def transformer_concept(sample_concept_nodes):
    """返回'Transformer'概念节点"""
    for n in sample_concept_nodes:
        if n.name == "Transformer":
            return n
    pytest.fail("测试数据缺少'Transformer'概念")


@pytest.fixture
def sample_subgraph(subgraph_builder, attention_concept):
    """返回一个样本星型子图"""
    return subgraph_builder.build_star(attention_concept, max_nodes=5)
