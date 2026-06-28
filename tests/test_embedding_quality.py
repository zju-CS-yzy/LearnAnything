#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Embedding 质量与切割粒度评估脚本

评估目标：
1. 智谱 embedding-3 在不同维度下的向量质量
2. 不同 chunk_size 对检索效果的影响
3. Parent-Child 双层分块 vs 单层分块的效果对比

使用方法：
    cd D:\MyCS\AI\Project\LearnAnything
    set ZHIPU_API_KEY=your_key
    python tests/test_embedding_quality.py

输出：
    - 向量质量统计报告
    - 不同参数组合的检索命中率对比表
    - 推荐配置建议
"""

import sys
import json
import time
import numpy as np
from pathlib import Path
from itertools import combinations
from typing import List, Dict, Any, Tuple

# 将项目根目录加入路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.embedding import EmbeddingManager
from core.chunking import DocumentChunker, ParentChildChunker
from core.vector_store import VectorStore


# ==================== 测试材料 ====================

TEST_CORPUS = [
    # 第一组：深度学习（语义相关）
    """## 第一章：深度学习基础

深度学习是机器学习的一个子领域，它基于人工神经网络，特别是深层神经网络。
通过多层非线性变换，深度学习模型能够从大量数据中自动学习层次化的特征表示。

### 1.1 神经网络原理

神经网络由输入层、隐藏层和输出层组成。每个神经元接收多个输入信号，
经过加权求和并通过激活函数（如 ReLU、Sigmoid）产生输出。
反向传播算法是训练神经网络的核心方法，通过计算损失函数对参数的梯度，
使用梯度下降法更新网络权重。

### 1.2 卷积神经网络

卷积神经网络（CNN）是处理图像数据的主流架构。它包含卷积层、池化层和全连接层。
卷积层通过滑动窗口（卷积核）提取局部特征，池化层降低特征维度。
经典 CNN 架构包括 LeNet、AlexNet、VGG、ResNet 等。""",

    # 第二组：机器学习（与第一组语义相近）
    """## 第二章：机器学习概述

机器学习是人工智能的一个分支，它使计算机能够从数据中学习规律，
而不需要显式编程。机器学习主要分为监督学习、无监督学习和强化学习三大类。

### 2.1 监督学习

监督学习使用带标签的数据进行训练。常见的监督学习算法包括：
线性回归、逻辑回归、支持向量机（SVM）、决策树、随机森林等。
评估指标包括准确率、精确率、召回率、F1 分数、AUC 等。

### 2.2 无监督学习

无监督学习处理未标注数据，目标是发现数据中的隐藏结构。
主要方法包括聚类（K-means、DBSCAN）和降维（PCA、t-SNE）。""",

    # 第三组：数据库（与第一组语义无关）
    """## 第三章：关系型数据库

关系型数据库是基于关系模型的数据库管理系统，使用表格（关系）存储数据。
SQL 是关系型数据库的标准查询语言，支持数据定义、查询、更新和控制操作。

### 3.1 数据库设计范式

第一范式（1NF）：属性原子性，不可再分。
第二范式（2NF）：满足 1NF，且非主属性完全依赖于主键。
第三范式（3NF）：满足 2NF，且不存在传递依赖。
BCNF 是对 3NF 的进一步约束，消除了主属性对候选键的部分依赖。

### 3.2 索引与查询优化

B+ 树索引是数据库中最常用的索引结构。索引能够加速等值查询和范围查询，
但会增加插入和更新的开销。查询优化器根据统计信息选择最优执行计划。""",

    # 第四组：前端开发（与其他组都无关）
    """## 第四章：Web 前端开发

前端开发是构建用户界面的技术领域，涉及 HTML、CSS 和 JavaScript 三大核心技术。
现代前端开发使用框架和库（如 React、Vue、Angular）提高开发效率。

### 4.1 响应式布局

响应式布局使网页能够适应不同屏幕尺寸。CSS Flexbox 和 Grid 布局是现代响应式设计的基础。
媒体查询（@media）根据设备特性应用不同的样式规则。""",

    # 第五组：操作系统（与第三组有些相关，与第一组无关）
    """## 第五章：操作系统原理

操作系统是管理计算机硬件与软件资源的系统软件，提供用户接口和资源管理功能。
进程管理、内存管理、文件系统和 I/O 设备管理是操作系统的四大核心功能。

### 5.1 进程调度

进程调度算法决定哪个进程获得 CPU 时间。常见算法包括：
先来先服务（FCFS）、最短作业优先（SJF）、时间片轮转（RR）、优先级调度等。
多级反馈队列调度结合了多种算法的优点，是实际系统中常用的方案。""",

    # 第六组：计算机组成原理（与第五组相关，与其他组无关）
    """## 第六章：计算机体系结构

计算机体系结构研究计算机硬件系统的组织和设计。冯·诺依曼体系结构是现代计算机的基础，
包含运算器、控制器、存储器、输入设备和输出设备五大部件。

### 6.1 CPU 流水线

CPU 流水线技术将指令执行过程分为多个阶段，使多条指令能够重叠执行。
经典五级流水线包括：取指（IF）、译码（ID）、执行（EX）、访存（MEM）、写回（WB）。
数据冒险、控制冒险和结构冒险是流水线中的主要问题。""",
]

# 测试问答对（每个问题对应预期答案所在的文档索引）
TEST_QUERIES = [
    ("什么是反向传播算法", 0, "第一组文档应被召回"),
    ("卷积神经网络有哪些经典架构", 0, "第一组文档应被召回"),
    ("监督学习有哪些常见算法", 1, "第二组文档应被召回"),
    ("无监督学习的主要方法是什么", 1, "第二组文档应被召回"),
    ("数据库的三大范式是什么", 2, "第三组文档应被召回"),
    ("B+ 树索引有什么作用", 2, "第三组文档应被召回"),
    ("什么是响应式布局", 3, "第四组文档应被召回"),
    ("CSS Flexbox 和 Grid 的区别", 3, "第四组文档应被召回"),
    ("进程调度算法有哪些", 4, "第五组文档应被召回"),
    ("CPU 流水线分为几个阶段", 5, "第六组文档应被召回"),
    ("深度学习与机器学习的关系", 0, "第一组或第二组应被召回"),
    ("操作系统和计算机体系结构的关系", 4, "第五组或第六组应被召回"),
]


# ==================== 层1：Embedding 内禀特性评估 ====================

def evaluate_embedding_intrinsics(embedding_manager: EmbeddingManager, dims: int = None) -> Dict[str, Any]:
    """
    评估 embedding 向量的内禀特性：
    - 均值范数（是否归一化）
    - 均值/标准差（分布是否正常）
    - 零值比例（维度坍缩检测）
    - 相似度矩阵（区分度测试）
    """
    print(f"\n{'='*60}")
    print(f"[层1] Embedding 内禀特性评估")
    print(f"{'='*60}")
    
    # 语义测试文本
    test_texts = [
        "深度学习是机器学习的一个子领域",
        "神经网络是深度学习的基础技术",
        "机器学习是人工智能的一个分支",
        "数据库管理系统使用表格存储数据",
        "Web 前端开发使用 HTML CSS JavaScript",
        "CPU 流水线将指令执行分为多个阶段",
        "操作系统管理计算机硬件与软件资源",
        "卷积神经网络处理图像数据",
        "反向传播算法训练神经网络",
        "B+ 树索引加速数据库查询",
    ]
    
    print(f"  测试样本数: {len(test_texts)}")
    
    # 获取 embedding
    embeddings = embedding_manager.embed(test_texts)
    emb_array = np.array(embeddings, dtype=np.float32)
    
    # 基础统计
    norms = np.linalg.norm(emb_array, axis=1)
    stats = {
        "dims": emb_array.shape[1],
        "mean_norm": float(np.mean(norms)),
        "std_norm": float(np.std(norms)),
        "mean_value": float(np.mean(emb_array)),
        "std_value": float(np.std(emb_array)),
        "zero_ratio": float(np.sum(np.abs(emb_array) < 1e-6) / emb_array.size),
        "max_value": float(np.max(emb_array)),
        "min_value": float(np.min(emb_array)),
    }
    
    print(f"  维度: {stats['dims']}")
    print(f"  平均范数: {stats['mean_norm']:.4f}")
    print(f"  范数标准差: {stats['std_norm']:.4f}")
    print(f"  均值: {stats['mean_value']:.6f}")
    print(f"  标准差: {stats['std_value']:.6f}")
    print(f"  零值比例: {stats['zero_ratio']:.4%}")
    
    # 维度坍缩检测（协方差矩阵特征值）
    if emb_array.shape[0] >= 5:
        cov = np.cov(emb_array.T)
        eigvals = np.linalg.eigvalsh(cov)
        eigvals_sorted = np.sort(eigvals)[::-1]
        # 前5个主成分解释的方差比例
        explained_ratio = np.sum(eigvals_sorted[:5]) / np.sum(eigvals_sorted)
        stats["top5_explained_ratio"] = float(explained_ratio)
        print(f"  前5主成分方差占比: {explained_ratio:.2%}")
        if explained_ratio > 0.95:
            print(f"  ⚠️ 警告: 前5主成分占比 > 95%，可能存在维度坍缩")
    
    # 相似度矩阵
    print(f"\n  相似度矩阵（语义分组测试）:")
    # 定义语义分组：同组内应高相似，跨组应低相似
    groups = [
        [0, 1, 7, 8],  # 深度学习/神经网络
        [2],            # 机器学习
        [3, 9],         # 数据库
        [4],            # 前端
        [5],            # CPU
        [6],            # 操作系统
    ]
    
    sim_matrix = np.zeros((len(test_texts), len(test_texts)))
    for i, j in combinations(range(len(test_texts)), 2):
        a, b = emb_array[i], emb_array[j]
        norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
        if norm_a > 0 and norm_b > 0:
            sim = float(np.dot(a, b) / (norm_a * norm_b))
        else:
            sim = 0.0
        sim_matrix[i][j] = sim_matrix[j][i] = sim
    
    # 组内平均相似度 vs 组间平均相似度
    intra_sims, inter_sims = [], []
    for group in groups:
        for i in group:
            for j in group:
                if i < j:
                    intra_sims.append(sim_matrix[i][j])
    
    for i in range(len(test_texts)):
        for j in range(i+1, len(test_texts)):
            in_same_group = any(i in g and j in g for g in groups)
            if not in_same_group:
                inter_sims.append(sim_matrix[i][j])
    
    stats["intra_sim_mean"] = float(np.mean(intra_sims)) if intra_sims else 0
    stats["intra_sim_std"] = float(np.std(intra_sims)) if intra_sims else 0
    stats["inter_sim_mean"] = float(np.mean(inter_sims)) if inter_sims else 0
    stats["inter_sim_std"] = float(np.std(inter_sims)) if inter_sims else 0
    stats["discrimination"] = stats["intra_sim_mean"] - stats["inter_sim_mean"]
    
    print(f"  组内相似度: {stats['intra_sim_mean']:.4f} ± {stats['intra_sim_std']:.4f}")
    print(f"  组间相似度: {stats['inter_sim_mean']:.4f} ± {stats['inter_sim_std']:.4f}")
    print(f"  区分度(组内-组间): {stats['discrimination']:.4f}")
    
    if stats["discrimination"] < 0.1:
        print(f"  ⚠️ 警告: 区分度 < 0.1，embedding 对语义差异不敏感")
    
    # 归一化判断
    if abs(stats["mean_norm"] - 1.0) < 0.1:
        print(f"  ✅ Embedding 已归一化（L2 范数 ≈ 1.0）")
    else:
        print(f"  ℹ️ Embedding 未归一化，检索时需自行计算 cosine similarity")
    
    return stats


# ==================== 层2：检索召回质量评估 ====================

def build_test_vector_store(chunks: List[Dict[str, Any]], collection_name: str) -> VectorStore:
    """用测试 chunk 构建向量库"""
    # 先创建临时对象以获取 db_path，然后立即关闭连接
    temp_store = VectorStore(collection_name)
    db_path = temp_store._db_path
    temp_store._conn.close()  # 关闭连接后才能删除文件
    del temp_store
    
    # 清理旧数据
    if db_path.exists():
        db_path.unlink()
    
    # 重新创建向量库
    store = VectorStore(collection_name)
    
    documents = []
    for i, chunk in enumerate(chunks):
        doc_id = chunk.get("id", f"chunk_{i:04d}")
        documents.append({
            "id": doc_id,
            "text": chunk["text"],
            "metadata": chunk.get("metadata", {}),
        })
    
    store.add_documents(documents)
    return store


def evaluate_retrieval(
    store: VectorStore,
    queries: List[Tuple[str, int, str]],
    top_k: int = 5
) -> Dict[str, Any]:
    """
    评估检索质量。
    
    Args:
        store: 向量库
        queries: [(query_text, expected_doc_index, description)]
        top_k: 检索返回数量
    
    Returns:
        命中率统计
    """
    hits = []
    reciprocal_ranks = []
    
    for query, expected_idx, desc in queries:
        results = store.query(query, n_results=top_k)
        
        # 检查结果中是否包含预期文档
        hit_rank = None
        for rank, r in enumerate(results, 1):
            meta = r.get("metadata", {})
            # 检查 metadata 中的 doc_index 或 source 匹配
            if meta.get("doc_index") == expected_idx:
                hit_rank = rank
                break
            # 或者检查 text 中是否包含预期文档的关键特征
            if meta.get("source", "").startswith(f"doc_{expected_idx}"):
                hit_rank = rank
                break
        
        hits.append(1 if hit_rank else 0)
        rr = 1.0 / hit_rank if hit_rank else 0.0
        reciprocal_ranks.append(rr)
    
    hit_rate = sum(hits) / len(hits)
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)
    
    # Hit@K 统计
    hit_at_1 = sum(1 for i, h in enumerate(hits) if h and reciprocal_ranks[i] == 1.0) / len(hits)
    hit_at_3 = sum(1 for i, h in enumerate(hits) if h and reciprocal_ranks[i] >= 1/3) / len(hits)
    hit_at_5 = hit_rate
    
    return {
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
        "hit_at_5": hit_at_5,
        "mrr": mrr,
        "total_queries": len(queries),
        "hits": hits,
    }


def evaluate_chunking_strategy(
    chunk_size: int,
    use_parent_child: bool = False,
    collection_prefix: str = "test"
) -> Dict[str, Any]:
    """
    评估一种分块策略的检索效果。
    
    Args:
        chunk_size: 子 chunk 最大大小
        use_parent_child: 是否使用 Parent-Child 双层分块
        collection_prefix: 向量库集合名前缀
    
    Returns:
        检索统计 + 分块统计
    """
    print(f"\n{'='*60}")
    print(f"[层2] 分块策略评估: chunk_size={chunk_size}, Parent-Child={use_parent_child}")
    print(f"{'='*60}")
    
    # 构建 chunk
    all_chunks = []
    
    if use_parent_child:
        chunker = ParentChildChunker(max_child_size=chunk_size, min_child_size=50)
        for idx, text in enumerate(TEST_CORPUS):
            meta = {
                "doc_index": idx,
                "source": f"doc_{idx}",
                "page_number": 1,
                "document_name": f"test_doc_{idx}.md",
            }
            parent, children = chunker.chunk_page(text, meta)
            all_chunks.append(parent)
            all_chunks.extend(children)
    else:
        chunker = DocumentChunker(max_chunk_size=chunk_size, min_chunk_size=50)
        for idx, text in enumerate(TEST_CORPUS):
            meta = {
                "doc_index": idx,
                "source": f"doc_{idx}",
            }
            chunks = chunker.chunk(text, meta)
            for c in chunks:
                c["metadata"]["doc_index"] = idx
            all_chunks.extend(chunks)
    
    # 统计
    parent_count = sum(1 for c in all_chunks if c.get("metadata", {}).get("chunk_type") == "parent_page")
    child_count = sum(1 for c in all_chunks if c.get("metadata", {}).get("chunk_type") in ("child", "fallback_child", "semantic_child"))
    other_count = len(all_chunks) - parent_count - child_count
    
    sizes = [len(c["text"]) for c in all_chunks]
    
    print(f"  总 chunk 数: {len(all_chunks)}")
    if use_parent_child:
        print(f"    Parent: {parent_count}, Child: {child_count}, Other: {other_count}")
    print(f"  chunk 大小: 平均={np.mean(sizes):.0f}, 中位数={np.median(sizes):.0f}, 最小={min(sizes)}, 最大={max(sizes)}")
    
    # 构建向量库
    collection_name = f"{collection_prefix}_cs{chunk_size}_pc{int(use_parent_child)}"
    store = build_test_vector_store(all_chunks, collection_name)
    
    # 检索评估
    results = evaluate_retrieval(store, TEST_QUERIES, top_k=5)
    
    print(f"  检索结果:")
    print(f"    Hit@1: {results['hit_at_1']:.2%}")
    print(f"    Hit@3: {results['hit_at_3']:.2%}")
    print(f"    Hit@5: {results['hit_at_5']:.2%}")
    print(f"    MRR:   {results['mrr']:.4f}")
    
    return {
        "chunk_size": chunk_size,
        "use_parent_child": use_parent_child,
        "total_chunks": len(all_chunks),
        "parent_count": parent_count,
        "child_count": child_count,
        "avg_chunk_size": float(np.mean(sizes)),
        "hit_at_1": results["hit_at_1"],
        "hit_at_3": results["hit_at_3"],
        "hit_at_5": results["hit_at_5"],
        "mrr": results["mrr"],
    }


# ==================== 主程序 ====================

def main():
    print("=" * 60)
    print("LearnAnything Embedding 质量与切割粒度评估")
    print("=" * 60)
    
    # 检查 API Key
    from config.settings import ZHIPU_API_KEY
    if not ZHIPU_API_KEY:
        print("\n❌ 错误: ZHIPU_API_KEY 未配置")
        print("   请设置环境变量: set ZHIPU_API_KEY=your_key")
        print("   或编辑 config/api_keys.ini")
        return 1
    
    print(f"\n✅ API Key 已配置")
    
    # 初始化 embedding manager
    embedding_manager = EmbeddingManager()
    
    # 检查是否降级模式
    if embedding_manager.is_fallback:
        print("⚠️ 警告: 当前使用降级 embedding（HashEmbedding），评估结果不反映智谱 API 质量")
        print("   请检查 ZHIPU_API_KEY 和网络连接")
        return 1
    
    # 测试连接并获取维度信息
    test_emb = embedding_manager.embed_single("测试")
    print(f"✅ 智谱 Embedding API 连接成功")
    print(f"   实际维度: {len(test_emb)}")
    
    # ===== 层1: Embedding 内禀特性 =====
    intrinsic_stats = evaluate_embedding_intrinsics(embedding_manager)
    
    # ===== 层2: 不同分块策略对比 =====
    all_results = []
    
    # 测试参数组合
    test_configs = [
        (500, False),
        (1000, False),
        (1500, False),
        (500, True),
        (1000, True),
        (1500, True),
    ]
    
    for chunk_size, use_pc in test_configs:
        result = evaluate_chunking_strategy(
            chunk_size=chunk_size,
            use_parent_child=use_pc,
            collection_prefix="test"
        )
        all_results.append(result)
    
    # ===== 汇总报告 =====
    print(f"\n{'='*60}")
    print("[汇总] 分块策略对比")
    print(f"{'='*60}")
    
    print(f"\n{'策略':<20} {'Chunks':<8} {'AvgSize':<10} {'Hit@1':<8} {'Hit@3':<8} {'Hit@5':<8} {'MRR':<8}")
    print("-" * 72)
    
    for r in all_results:
        strategy = f"PC={r['use_parent_child']}, CS={r['chunk_size']}"
        print(f"{strategy:<20} {r['total_chunks']:<8} {r['avg_chunk_size']:<10.0f} "
              f"{r['hit_at_1']:<8.2%} {r['hit_at_3']:<8.2%} {r['hit_at_5']:<8.2%} {r['mrr']:<8.4f}")
    
    # 找出最佳配置
    best = max(all_results, key=lambda x: x["mrr"])
    print(f"\n🏆 最佳配置 (MRR={best['mrr']:.4f}):")
    print(f"   Parent-Child: {best['use_parent_child']}")
    print(f"   Chunk Size: {best['chunk_size']}")
    
    # 保存报告
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "embedding_stats": intrinsic_stats,
        "chunking_results": all_results,
        "recommended_config": {
            "use_parent_child": best["use_parent_child"],
            "chunk_size": best["chunk_size"],
        },
    }
    
    report_path = PROJECT_ROOT / "tests" / "embedding_quality_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n📄 报告已保存: {report_path}")
    
    # 评估结论
    print(f"\n{'='*60}")
    print("[结论]")
    print(f"{'='*60}")
    
    # Embedding 质量判断
    if intrinsic_stats["zero_ratio"] > 0.05:
        print("⚠️ Embedding 零值比例过高，可能存在维度坍缩")
    elif intrinsic_stats["discrimination"] < 0.1:
        print("⚠️ Embedding 区分度不足，建议检查 API 调用或更换模型")
    else:
        print("✅ Embedding 质量正常")
    
    # 分块策略建议
    if best["hit_at_1"] < 0.5:
        print("⚠️ 检索命中率偏低，可能需要:")
        print("   1. 调整 chunk_size（尝试更小粒度）")
        print("   2. 增加测试语料多样性")
        print("   3. 检查 embedding 质量")
    else:
        print(f"✅ 检索效果良好，推荐使用: chunk_size={best['chunk_size']}, Parent-Child={best['use_parent_child']}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
