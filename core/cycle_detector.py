#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CycleDetector — 增量环检测器（范式无关）
"""

import sys
import os

# 确保项目根目录在路径中，避免 core/types.py 命名冲突
# 当从 scripts/ 运行测试时，不需要此操作
if __name__ != "__main__":
    _project_root = os.path.dirname(os.path.abspath(__file__))
    _parent = os.path.dirname(_project_root)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)

from typing import Dict, Set, List, Optional
from collections import defaultdict


class CycleError(Exception):
    """检测到环时抛出"""
    def __init__(self, path: List[str]):
        self.path = path
        super().__init__(f"Cycle detected: {' -> '.join(path)}")


class CycleDetector:
    """增量环检测器"""
    
    def __init__(self):
        # 邻接表：node -> set of neighbors
        self._graph: Dict[str, Set[str]] = defaultdict(set)
        # 所有节点
        self._nodes: Set[str] = set()
    
    def add_edge(self, source: str, target: str, raise_on_cycle: bool = True) -> bool:
        """
        添加一条边，如果会形成环则拒绝。
        
        Args:
            source: 源节点
            target: 目标节点
            raise_on_cycle: 为 True 时抛出 CycleError，为 False 时返回 False
            
        Returns:
            True: 边添加成功
            False: 边会形成环（仅当 raise_on_cycle=False）
            
        Raises:
            CycleError: 当边会形成环时（raise_on_cycle=True）
        """
        if self.would_form_cycle(source, target):
            # 找到环路径
            cycle_path = self._find_cycle_path(source, target)
            if raise_on_cycle:
                raise CycleError(cycle_path)
            return False
        
        self._graph[source].add(target)
        self._nodes.add(source)
        self._nodes.add(target)
        return True
    
    def would_form_cycle(self, source: str, target: str) -> bool:
        """
        检查添加边 source→target 是否会形成环。
        
        方法：从 target 出发 DFS，看能否到达 source。
        """
        # 如果 target 不在图中，或 source == target（自环），直接判断
        if source == target:
            return True
        if target not in self._nodes:
            return False
        
        # DFS 从 target 出发
        visited = set()
        stack = [target]
        
        while stack:
            node = stack.pop()
            if node == source:
                return True
            if node in visited:
                continue
            visited.add(node)
            for neighbor in self._graph.get(node, set()):
                if neighbor not in visited:
                    stack.append(neighbor)
        
        return False
    
    def _find_cycle_path(self, source: str, target: str) -> List[str]:
        """找到会形成环的路径"""
        # BFS 找从 target 到 source 的路径
        from collections import deque
        
        queue = deque([(target, [target])])
        visited = {target}
        
        while queue:
            node, path = queue.popleft()
            if node == source:
                return path + [source]
            
            for neighbor in self._graph.get(node, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        
        return [target, source]  # fallback
    
    def get_edges(self) -> List[tuple]:
        """获取当前所有边"""
        edges = []
        for source, targets in self._graph.items():
            for target in targets:
                edges.append((source, target))
        return edges
    
    def validate_paradigm_types(self, paradigm_id: str, relation_map: Dict) -> Optional[str]:
        """
        静态检查：验证范式配置在 type 层面是否存在环。
        
        注意：
        - type-level 环不一定意味着实例-level 一定会环
        - 但如果 type-level 无环，则实例-level 也绝对不会环
        - 对于允许双向连接的范式（如 engineering），type-level 可能有"环"，
          但实例-level 通过 would_form_cycle 可以防止
        """
        detector = CycleDetector()
        
        for source_type, rel_map in relation_map.items():
            for relation, target_types in rel_map.items():
                for target_type in target_types:
                    try:
                        detector.add_edge(source_type, target_type)
                    except CycleError as e:
                        return (
                            f"范式 '{paradigm_id}' 的 relation_map 在 type 层面存在环: "
                            f"{e.path}. 请检查 relation_map 配置，"
                            f"确保实例层面通过 CycleDetector 进行增量检测。"
                        )
        
        return None  # 无环


# ========== 与 GraphStore 集成 ==========

def build_detector_from_graph(subject_id: str) -> Optional[CycleDetector]:
    """
    从现有 GraphStore 构建 CycleDetector。
    
    用途：在已有图谱上增量添加边时防止环。
    """
    try:
        from core.graph_store import GraphStore
        
        store = GraphStore(subject_id)
        detector = CycleDetector()
        
        # 查询所有 CanonicalConcept 之间的边
        conn = store._ensure_db()
        query = """
        MATCH (a)-[r]->(b)
        RETURN a.canonical_id AS source, b.canonical_id AS target
        """
        
        result = store._execute(conn, query)
        while result.has_next():
            row = result.get_next()
            detector.add_edge(row[0], row[1], raise_on_cycle=False)
        
        store.close()
        return detector
    except Exception as e:
        print(f"[CycleDetector] 从图谱构建检测器失败: {e}")
        return None


# ========== 单元测试 ==========

def _test():
    """内部测试"""
    print("[CycleDetector] 运行内部测试...")
    
    # 测试 1: 基本无环
    d = CycleDetector()
    assert d.add_edge("A", "B")
    assert d.add_edge("B", "C")
    assert d.add_edge("C", "D")
    print("  [PASS] 基本无环")
    
    # 测试 2: 检测环
    try:
        d.add_edge("D", "A")
        assert False, "应该检测到环"
    except CycleError as e:
        print(f"  [PASS] 正确检测到环: {e}")
    
    # 测试 3: 自环
    assert d.would_form_cycle("X", "X")
    print("  [PASS] 自环检测")
    
    # 测试 4: 不形成环
    assert not d.would_form_cycle("D", "E")
    print("  [PASS] 不形成环")
    
    # 测试 5: 范式 type-level 检查
    result = d.validate_paradigm_types("test", {
        "A": {"R1": ["B"]},
        "B": {"R2": ["C"]},
    })
    assert result is None
    print("  [PASS] 无环范式检查")
    
    result = d.validate_paradigm_types("test", {
        "A": {"R1": ["B"]},
        "B": {"R2": ["A"]},
    })
    assert result is not None
    print(f"  [PASS] 有环范式检查: {result}")
    
    print("[CycleDetector] 所有测试通过!")


if __name__ == "__main__":
    _test()
