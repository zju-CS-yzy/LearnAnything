"""
LA-040-P0: Subgraph Builder（子图构建器）

围绕目标概念构建用于出题/讲解的局部子图
"""

from typing import Dict, List, Optional, Set, Tuple, Any

from core.graph_education.types import ConceptNode, SemanticEdge, Subgraph, QuestionPattern
from core.graph_store import GraphStore


class SubgraphBuilder:
    """
    子图构建器：围绕目标概念构建用于出题/讲解的局部子图
    
    支持三种模式：
    - Star: 中心 + 1-hop 邻居
    - Chain: 两点间最短路径
    - Tree: BFS 展开
    """
    
    def __init__(
        self,
        graph_store: GraphStore,
        centrality_cache: Optional[Dict[str, float]] = None
    ):
        self.graph_store = graph_store
        self.centrality_cache = centrality_cache or {}
    
    # ───────────────────────────────────────────────
    # 核心接口
    # ───────────────────────────────────────────────
    
    def build(
        self,
        seed_concepts: List[ConceptNode],
        related_concepts: Optional[List[ConceptNode]] = None,
        mode: str = "auto",
        max_depth: int = 2,
        max_nodes: int = 20
    ) -> Subgraph:
        """
        构建通用子图
        
        Args:
            seed_concepts: 种子概念列表
            related_concepts: 已扩展的相关概念（可选，如来自 ConceptRetriever.expand）
            mode: 构建模式（auto / star / chain / tree）
            max_depth: 最大深度
            max_nodes: 最大节点数
            
        Returns:
            Subgraph: 构建的子图
            
        Raises:
            ValueError: 种子概念为空
        """
        if not seed_concepts:
            raise ValueError("LA-0403001: 种子概念为空，无法构建子图")
        
        if mode == "auto":
            # 自动选择模式：单种子 → Star，多种子 → Tree
            if len(seed_concepts) == 1:
                mode = "star"
            else:
                mode = "tree"
        
        if mode == "star":
            return self.build_star(
                seed_concepts[0], 
                include_derived=True, 
                max_nodes=max_nodes
            )
        elif mode == "chain" and len(seed_concepts) >= 2:
            return self.build_chain(
                seed_concepts[0], 
                seed_concepts[-1],
                max_nodes=max_nodes
            )
        elif mode == "tree":
            return self.build_tree(
                seed_concepts[0], 
                max_depth=max_depth, 
                max_nodes=max_nodes
            )
        else:
            # 默认：包含所有种子 + 相关概念的通用子图
            return self._build_from_seed_set(
                seed_concepts, 
                related_concepts or [], 
                max_nodes=max_nodes
            )
    
    def build_for_pattern(
        self,
        target_concept: ConceptNode,
        pattern: QuestionPattern
    ) -> Subgraph:
        """
        根据题型构建专用子图
        
        选择题（depth=1）→ Star 子图
        解答题（depth=2, chain）→ 包含依赖链的 Tree 子图
        
        Args:
            target_concept: 目标概念
            pattern: 题型配置
            
        Returns:
            Subgraph: 适合该题型的子图
        """
        if pattern.concept_depth == 1:
            # 简单题型：星型子图
            return self.build_star(
                target_concept,
                max_nodes=pattern.max_concepts_per_question
            )
        else:
            # 复杂题型：树型子图，包含依赖链
            subgraph = self.build_tree(
                target_concept,
                max_depth=pattern.concept_depth,
                max_nodes=pattern.max_concepts_per_question
            )
            
            # 如果需要概念链，确保包含依赖链
            if pattern.require_concept_chain:
                self._ensure_concept_chain(subgraph, target_concept)
            
            return subgraph
    
    def build_for_explanation(
        self,
        question: Any,  # 使用 Any 避免循环导入
        depth: str = "L2"
    ) -> Subgraph:
        """
        为讲解构建子图
        
        Args:
            question: 题目对象（需有 primary_concepts 属性）
            depth: 讲解深度（L1/L2/L3/L4）
            
        Returns:
            Subgraph: 适合讲解的子图
        """
        # 获取题目的目标概念
        primary_concepts = getattr(question, 'primary_concepts', [])
        if not primary_concepts and hasattr(question, 'knowledge_trace') and question.knowledge_trace is not None:
            primary_concepts = question.knowledge_trace.primary_concepts
        
        if not primary_concepts:
            raise ValueError("LA-0403001: 题目没有关联概念，无法构建讲解子图")
        
        # 根据深度确定构建参数
        depth_map = {
            "L1": {"max_depth": 1, "max_nodes": 5},
            "L2": {"max_depth": 2, "max_nodes": 12},
            "L3": {"max_depth": 2, "max_nodes": 20},
            "L4": {"max_depth": 3, "max_nodes": 30},
        }
        params = depth_map.get(depth, {"max_depth": 2, "max_nodes": 12})
        
        # 加载目标概念节点
        nodes = self._load_nodes_by_ids(primary_concepts)
        if not nodes:
            raise ValueError(f"LA-0403001: 无法加载概念: {primary_concepts}")
        
        # 构建子图
        return self.build(
            seed_concepts=nodes,
            mode="tree",
            max_depth=params["max_depth"],
            max_nodes=params["max_nodes"]
        )
    
    # ───────────────────────────────────────────────
    # 子图模式
    # ───────────────────────────────────────────────
    
    def build_star(
        self,
        center: ConceptNode,
        include_derived: bool = True,
        max_nodes: int = 10
    ) -> Subgraph:
        """
        星型子图：中心 + 1-hop 邻居
        
        Args:
            center: 中心概念
            include_derived: 是否包含 DERIVED_FROM 来源
            max_nodes: 最大节点数
            
        Returns:
            Subgraph: 星型子图
        """
        conn = self.graph_store._ensure_db()
        
        # 查询 1-hop 邻居（所有方向）
        cypher = f"""
            MATCH (c:CanonicalConcept {{canonical_id: '{center.canonical_id}'}})
                   -[r:SOLUTION|DEPENDS_ON|HAS_DETAIL]-(n:CanonicalConcept)
            RETURN DISTINCT n.canonical_id, n.name, n.concept_type, n.description, 
                   n.parent_hint, n.aliases
            LIMIT {max_nodes}
        """
        
        nodes = [center]
        edges = []
        
        try:
            result = self.graph_store._execute(conn, cypher)
            while result.has_next():
                row = result.get_next()
                neighbor = self._row_to_node(row)
                nodes.append(neighbor)
                # 注意：这里需要知道边的方向，简化处理为双向
                edges.append(SemanticEdge(
                    source_id=center.canonical_id,
                    target_id=neighbor.canonical_id,
                    edge_type="RELATED"  # 统一标记，后续可优化
                ))
        except Exception as e:
            pass
        
        return Subgraph(
            nodes=nodes,
            edges=edges,
            seed_concepts=[center.canonical_id],
            build_mode="star"
        )
    
    def build_chain(
        self,
        start: ConceptNode,
        end: ConceptNode,
        max_nodes: int = 20
    ) -> Subgraph:
        """
        链型子图：两点间最短路径
        
        Args:
            start: 起点概念
            end: 终点概念
            max_nodes: 最大节点数
            
        Returns:
            Subgraph: 链型子图
            
        Raises:
            ValueError: 两点间无路径
        """
        conn = self.graph_store._ensure_db()
        
        # 使用 Cypher 查询最短路径
        cypher = f"""
            MATCH path = shortestPath(
                (start:CanonicalConcept {{canonical_id: '{start.canonical_id}'}})
                -[:SOLUTION|DEPENDS_ON|HAS_DETAIL*]-
                (end:CanonicalConcept {{canonical_id: '{end.canonical_id}'}})
            )
            RETURN path
            LIMIT 1
        """
        
        try:
            result = self.graph_store._execute(conn, cypher)
            if not result.has_next():
                raise ValueError(
                    f"LA-0403003: 概念 '{start.name}' 与 '{end.name}' 之间无路径"
                )
            
            # KùzuDB 的 shortestPath 返回路径节点列表
            # 注意：KùzuDB Cypher 的 shortestPath 语法可能不同，这里用简化实现
            row = result.get_next()
            # 解析路径...
            
        except Exception as e:
            if "LA-0403003" in str(e):
                raise
            # 回退：手动 BFS 找路径
            return self._build_chain_bfs(start, end, max_nodes)
        
        # 如果上面的查询成功，解析结果
        # 简化：返回包含两个端点的子图
        nodes = [start, end]
        edges = [SemanticEdge(
            source_id=start.canonical_id,
            target_id=end.canonical_id,
            edge_type="PATH"
        )]
        
        return Subgraph(
            nodes=nodes,
            edges=edges,
            seed_concepts=[start.canonical_id, end.canonical_id],
            build_mode="chain"
        )
    
    def build_tree(
        self,
        root: ConceptNode,
        max_depth: int = 2,
        max_nodes: int = 20
    ) -> Subgraph:
        """
        树型子图：BFS 展开
        
        Args:
            root: 根概念
            max_depth: 最大深度
            max_nodes: 最大节点数
            
        Returns:
            Subgraph: 树型子图
        """
        conn = self.graph_store._ensure_db()
        
        nodes = [root]
        edges = []
        node_ids = {root.canonical_id}
        
        current_level = [root.canonical_id]
        
        for depth in range(max_depth):
            if not current_level or len(nodes) >= max_nodes:
                break
            
            # 查询当前层的邻居
            frontier_str = ", ".join([f"'{cid}'" for cid in current_level])
            
            cypher = f"""
                MATCH (c:CanonicalConcept)-[r:SOLUTION|DEPENDS_ON|HAS_DETAIL]-(n:CanonicalConcept)
                WHERE c.canonical_id IN [{frontier_str}]
                RETURN DISTINCT c.canonical_id as source_id, n.canonical_id as target_id, 
                       n.name, n.concept_type, n.description, n.parent_hint, n.aliases
                LIMIT {max_nodes * 2}
            """
            
            next_level = []
            try:
                result = self.graph_store._execute(conn, cypher)
                while result.has_next():
                    row = result.get_next()
                    source_id = row[0]
                    target_id = row[1]
                    
                    if target_id not in node_ids and len(nodes) < max_nodes:
                        node_ids.add(target_id)
                        next_level.append(target_id)
                        
                        # 添加节点
                        nodes.append(self._row_to_node(row[2:]))
                        
                        # 添加边（KùzuDB 查询使用了多种关系类型，统一标记为 RELATED）
                        edges.append(SemanticEdge(
                            source_id=source_id,
                            target_id=target_id,
                            edge_type="RELATED"
                        ))
            except Exception as e:
                break
            
            current_level = next_level
        
        return Subgraph(
            nodes=nodes,
            edges=edges,
            seed_concepts=[root.canonical_id],
            build_mode="tree",
            max_depth=max_depth
        )
    
    # ───────────────────────────────────────────────
    # 序列化
    # ───────────────────────────────────────────────
    
    def to_snapshot(self, subgraph: Subgraph) -> Dict:
        """序列化子图为字典"""
        return {
            "seed_concepts": subgraph.seed_concepts,
            "build_mode": subgraph.build_mode,
            "max_depth": subgraph.max_depth,
            "nodes": [
                {
                    "canonical_id": n.canonical_id,
                    "name": n.name,
                    "concept_type": n.concept_type,
                    "description": n.description,
                    "aliases": n.aliases,
                }
                for n in subgraph.nodes
            ],
            "edges": [
                {
                    "source_id": e.source_id,
                    "target_id": e.target_id,
                    "edge_type": e.edge_type,
                    "confidence": e.confidence,
                }
                for e in subgraph.edges
            ]
        }
    
    def from_snapshot(self, snapshot: Dict) -> Subgraph:
        """从字典重建子图"""
        nodes = [
            ConceptNode(
                canonical_id=n["canonical_id"],
                name=n["name"],
                concept_type=n.get("concept_type", "concept"),
                description=n.get("description", ""),
                aliases=n.get("aliases", []),
            )
            for n in snapshot.get("nodes", [])
        ]
        
        edges = [
            SemanticEdge(
                source_id=e["source_id"],
                target_id=e["target_id"],
                edge_type=e.get("edge_type", "RELATED"),
                confidence=e.get("confidence", 1.0),
            )
            for e in snapshot.get("edges", [])
        ]
        
        return Subgraph(
            nodes=nodes,
            edges=edges,
            seed_concepts=snapshot.get("seed_concepts", []),
            build_mode=snapshot.get("build_mode", "auto"),
            max_depth=snapshot.get("max_depth", 2)
        )
    
    # ───────────────────────────────────────────────
    # 内部方法
    # ───────────────────────────────────────────────
    
    def _build_from_seed_set(
        self,
        seed_concepts: List[ConceptNode],
        related_concepts: List[ConceptNode],
        max_nodes: int = 20
    ) -> Subgraph:
        """从种子概念集合构建子图"""
        all_nodes = list(seed_concepts)
        node_ids = {n.canonical_id for n in seed_concepts}
        
        # 添加相关概念（不超过上限）
        for rc in related_concepts:
            if rc.canonical_id not in node_ids and len(all_nodes) < max_nodes:
                all_nodes.append(rc)
                node_ids.add(rc.canonical_id)
        
        # 查询所有节点间的边
        edges = self._query_edges_between(node_ids)
        
        return Subgraph(
            nodes=all_nodes,
            edges=edges,
            seed_concepts=[n.canonical_id for n in seed_concepts],
            build_mode="auto"
        )
    
    def _query_edges_between(self, node_ids: Set[str]) -> List[SemanticEdge]:
        """查询节点集合之间的所有边"""
        if not node_ids:
            return []
        
        conn = self.graph_store._ensure_db()
        id_str = ", ".join([f"'{cid}'" for cid in node_ids])
        
        cypher = f"""
            MATCH (a:CanonicalConcept)-[r:SOLUTION|DEPENDS_ON|HAS_DETAIL]-(b:CanonicalConcept)
            WHERE a.canonical_id IN [{id_str}] AND b.canonical_id IN [{id_str}]
            RETURN a.canonical_id, b.canonical_id
        """
        
        edges = []
        try:
            result = self.graph_store._execute(conn, cypher)
            while result.has_next():
                row = result.get_next()
                edges.append(SemanticEdge(
                    source_id=row[0],
                    target_id=row[1],
                    edge_type="RELATED"
                ))
        except Exception as e:
            pass
        
        return edges
    
    def _build_chain_bfs(
        self,
        start: ConceptNode,
        end: ConceptNode,
        max_nodes: int = 20
    ) -> Subgraph:
        """手动 BFS 找最短路径（回退实现）"""
        conn = self.graph_store._ensure_db()
        
        # BFS
        visited = {start.canonical_id: None}
        queue = [start.canonical_id]
        found = False
        
        while queue and not found:
            current = queue.pop(0)
            if current == end.canonical_id:
                found = True
                break
            
            # 查询邻居
            cypher = f"""
                MATCH (c:CanonicalConcept {{canonical_id: '{current}'}})
                       -[:SOLUTION|DEPENDS_ON|HAS_DETAIL]-(n:CanonicalConcept)
                RETURN n.canonical_id
                LIMIT 50
            """
            
            try:
                result = self.graph_store._execute(conn, cypher)
                while result.has_next():
                    row = result.get_next()
                    neighbor_id = row[0]
                    if neighbor_id not in visited:
                        visited[neighbor_id] = current
                        queue.append(neighbor_id)
            except:
                pass
        
        if not found:
            raise ValueError(
                f"LA-0403003: 概念 '{start.name}' 与 '{end.name}' 之间无路径"
            )
        
        # 重建路径
        path = [end.canonical_id]
        current = end.canonical_id
        while current != start.canonical_id:
            current = visited[current]
            path.append(current)
        path.reverse()
        
        # 加载路径上的节点
        nodes = self._load_nodes_by_ids(path)
        
        # 构建边
        edges = []
        for i in range(len(path) - 1):
            edges.append(SemanticEdge(
                source_id=path[i],
                target_id=path[i + 1],
                edge_type="PATH"
            ))
        
        return Subgraph(
            nodes=nodes,
            edges=edges,
            seed_concepts=[start.canonical_id, end.canonical_id],
            build_mode="chain"
        )
    
    def _ensure_concept_chain(self, subgraph: Subgraph, target: ConceptNode) -> None:
        """确保子图包含概念依赖链"""
        # 查找 target 的 DEPENDS_ON 前置概念
        predecessors = subgraph.get_incoming(target.canonical_id, "DEPENDS_ON")
        
        # 如果没有前置概念在子图中，尝试添加
        if not predecessors:
            conn = self.graph_store._ensure_db()
            cypher = f"""
                MATCH (c:CanonicalConcept {{canonical_id: '{target.canonical_id}'}})
                       <-[:DEPENDS_ON]-(p:CanonicalConcept)
                RETURN p.canonical_id, p.name, p.concept_type, p.description, p.parent_hint, p.aliases
                LIMIT 3
            """
            
            try:
                result = self.graph_store._execute(conn, cypher)
                if result.has_next():
                    row = result.get_next()
                    prereq = self._row_to_node(row)
                    
                    if prereq.canonical_id not in subgraph.node_map:
                        subgraph.nodes.append(prereq)
                        subgraph.edges.append(SemanticEdge(
                            source_id=target.canonical_id,
                            target_id=prereq.canonical_id,
                            edge_type="DEPENDS_ON"
                        ))
            except:
                pass
    
    def _load_nodes_by_ids(self, ids: List[str]) -> List[ConceptNode]:
        """批量加载节点"""
        if not ids:
            return []
        
        conn = self.graph_store._ensure_db()
        id_str = ", ".join([f"'{cid}'" for cid in ids])
        
        cypher = f"""
            MATCH (c:CanonicalConcept)
            WHERE c.canonical_id IN [{id_str}]
            RETURN c.canonical_id, c.name, c.concept_type, c.description, 
                   c.parent_hint, c.aliases
        """
        
        nodes = {}
        try:
            result = self.graph_store._execute(conn, cypher)
            while result.has_next():
                row = result.get_next()
                node = self._row_to_node(row)
                nodes[node.canonical_id] = node
        except:
            pass
        
        # 按原始顺序返回
        return [nodes[cid] for cid in ids if cid in nodes]
    
    def _row_to_node(self, row) -> ConceptNode:
        """将查询结果行转换为 ConceptNode"""
        if isinstance(row, dict):
            return ConceptNode(
                canonical_id=row.get("canonical_id", ""),
                name=row.get("name", ""),
                concept_type=row.get("concept_type", "concept"),
                description=row.get("description", ""),
                aliases=row.get("aliases", []),
                parent_hint=row.get("parent_hint", ""),
            )
        
        # Tuple 模式
        length = len(row)
        return ConceptNode(
            canonical_id=row[0] if length > 0 else "",
            name=row[1] if length > 1 else "",
            concept_type=row[2] if length > 2 else "concept",
            description=row[3] if length > 3 else "",
            parent_hint=row[4] if length > 4 else "",
            aliases=row[5] if length > 5 else [],
        )
