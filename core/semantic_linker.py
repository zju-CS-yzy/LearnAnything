"""
全局语义推断模块 (Semantic Linker)

Phase 2 核心模块：在去重后的概念空间中建立跨文档/跨 chunk 的语义连接。

设计原则：
1. 先提取，后推断 — 提取时不做跨文档推断，避免缺少全局信息
2. 显式标记 — 推断完成后在数据库中持久化连接边，降低后续操作成本
3. DAG 存储 — 允许多父节点，可视化层再做树形渲染

支持的范式（当前先实现工程分解）：
- engineering: requirement → technology → sub_requirement → sub_technology
  - requirement -(SOLUTION)-> technology: 需求被技术解决
  - technology -(DEPENDS_ON)-> sub_requirement: 技术实现依赖于子需求
  - sub_requirement -(SOLUTION)-> sub_technology: 子需求被子技术解决

使用方式：
    from core.semantic_linker import SemanticLinker
    linker = SemanticLinker(subject="ai_llm_v2")
    edges = linker.link_all()

输出格式：
    [
        {
            "parent_id": "concept_xxx",
            "child_id": "concept_yyy",
            "relation_type": "SOLUTION",
            "confidence": 0.92,
            "reason": "Ring AllReduce算法是为了实现多GPU并行训练而提出的具体技术方案"
        }
    ]
"""

import csv
import json
from typing import List, Dict, Any, Optional, Tuple, Set

import numpy as np
from core.graph_store import GraphStore
from core.llm_client import LLMClient
from config.settings import KNOWLEDGE_BASE_DIR


def _load_paradigms_from_yaml() -> Dict[str, Any]:
    """加载 paradigms.yaml 中的 relation_map 等配置。"""
    import yaml
    yaml_path = KNOWLEDGE_BASE_DIR.parent / "config" / "paradigms.yaml"
    if not yaml_path.exists():
        return {}
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("paradigms", {})
    except Exception as e:
        print(f"[SemanticLinker] 加载 paradigms.yaml 失败: {e}")
        return {}


# 从 paradigms.yaml 加载的范式配置
_PARADIGMS_YAML = _load_paradigms_from_yaml()


def _build_relation_validator(paradigm_id: str) -> Optional[Dict[str, Dict[str, List[str]]]]:
    """
    从 paradigms.yaml 构建关系合法性校验器。
    
    Returns:
        {source_type: {relation_type: [target_types]}} 或 None
    """
    p = _PARADIGMS_YAML.get(paradigm_id)
    if not p:
        return None
    return p.get("relation_map")


def _is_valid_relation(
    relation_map: Optional[Dict],
    source_type: str,
    relation_type: str,
    target_type: str,
) -> bool:
    """
    校验关系是否合法。
    
    Args:
        relation_map: paradigms.yaml 中的 relation_map
        source_type: 源节点类型
        relation_type: 关系类型
        target_type: 目标节点类型
        
    Returns:
        True if 合法（或未配置校验器），False if 非法
    """
    if not relation_map:
        return True  # 没有配置则放行
    
    source_map = relation_map.get(source_type)
    if not source_map:
        return False  # source_type 不在 relation_map 中 → 非法
    
    allowed_targets = source_map.get(relation_type)
    if allowed_targets is None:
        return False  # relation_type 不合法
    
    return target_type in allowed_targets


def _build_paradigm_config(paradigm_id: str) -> Optional[Dict[str, Any]]:
    """
    从 paradigms.yaml 构建 SemanticLinker 内部使用的范式配置。
    优先使用 YAML 配置，YAML 不存在时 fallback 到 PARADIGM_LEVELS 硬编码。
    
    Returns:
        {
            "levels": [...],
            "transitions": {(source_type, target_type): relation_type, ...},
            "relation_map": {...},
            "relations": {...},
            "cyclic": bool,
            "gap_rules": {...},
            "fallback": {...},
        }
    """
    p = _PARADIGMS_YAML.get(paradigm_id)
    if not p:
        # Fallback 到硬编码（向后兼容）
        hardcoded = PARADIGM_LEVELS.get(paradigm_id)
        if not hardcoded:
            return None
        return {
            "levels": hardcoded["levels"],
            "transitions": hardcoded["transitions"],
            "relation_map": None,
            "relations": {},
            "cyclic": False,
            "gap_rules": {},
            "fallback": {},
        }
    
    # 从 YAML 的 relation_map 推导 transitions
    # transitions 格式: {(source_type, target_type): relation_type}
    levels = list(p.get("types", {}).keys())
    transitions = {}
    for source_type, rel_map in p.get("relation_map", {}).items():
        for relation_type, target_types in rel_map.items():
            for target_type in target_types:
                transitions[(source_type, target_type)] = relation_type
    
    return {
        "levels": levels,
        "transitions": transitions,
        "relation_map": p.get("relation_map"),
        "relations": p.get("relations", {}),
        "cyclic": p.get("cyclic", False),
        "gap_rules": p.get("gap_rules", {}),
        "fallback": p.get("fallback", {}),
    }


# ========== 范式层级配置（向后兼容 — 优先使用 paradigms.yaml）==========

# 向后兼容配置 — 注意：关系类型名称必须与 paradigms.yaml 中的 relations 完全一致
PARADIGM_LEVELS = {
    "engineering": {
        "levels": ["requirement", "technology"],
        # 层级间允许的连接规则：(parent_type, child_type) -> relation_type
        # 必须与 paradigms.yaml 中 engineering.relations 的 key 一致
        "transitions": {
            ("requirement", "technology"): "IMPLEMENTS",
            ("technology", "requirement"): "DEPEND_ON",
        },
    },
    "theory": {
        "levels": ["definition", "law", "application", "extension"],
        "transitions": {
            ("definition", "law"): "HAS_LAW",
            ("law", "application"): "APPLIES_TO",
            ("application", "extension"): "EXTENDS",
        },
    },
    "hierarchical": {
        "levels": ["fact", "concept", "method", "evaluation"],
        "transitions": {
            ("fact", "concept"): "DEFINES_AS",
            ("concept", "method"): "USES",
            ("method", "evaluation"): "EVALUATES",
        },
    },
}


# ========== LLM 二次确认提示词 ==========

_LINK_JUDGE_PROMPT = """你是一个知识图谱关系判断专家。

请判断以下两个概念之间是否存在"上层→下层"的语义关系。

父概念: {parent_name} (类型: {parent_type})
父概念描述: {parent_description}

子概念: {child_name} (类型: {child_type})
子概念描述: {child_description}

候选连接类型: {relation_type}
连接类型含义: {relation_meaning}

判断标准：
- 子概念是否是为了实现/解决/基于/扩展父概念而存在的？
- 父概念是否是子概念的上层需求/定义/原理/目标？
- 重点关注子概念的描述中是否明确提到与父概念的关联。

返回严格 JSON 格式，不要包含任何解释性文字：
{{"has_relation": true/false, "confidence": 0.0-1.0, "reason": "简要说明判断依据（20-40字）"}}
"""


class SemanticLinker:
    """
    全局语义推断器 — 在概念空间中建立跨 chunk 语义连接。
    """

    def __init__(
        self,
        collection_name: str,
        llm_client: Optional[LLMClient] = None,
        embedding_threshold: float = 0.72,
        llm_threshold: float = 0.80,
        graph_store=None,
    ):
        """
        Args:
            collection_name: 学科集合名（如 "ai_llm_v2"）
            llm_client: 可选的 LLMClient 实例
            embedding_threshold: embedding 相似度阈值，低于此值的候选对不送入 LLM
            llm_threshold: LLM 判断置信度阈值，低于此值不建立连接
            graph_store: 可选的外部 GraphStore 实例（避免重复创建数据库连接）
        """
        self.collection_name = collection_name
        self.graph_store = graph_store or GraphStore(collection_name)
        self.graph_store.init_schema()
        self.llm = llm_client or LLMClient()
        self.embedding_threshold = embedding_threshold
        self.llm_threshold = llm_threshold

        # 初始化 embedding 服务
        from core.embedding import EmbeddingManager
        self.embeddings = EmbeddingManager()
        self._embedding_cache = {}

    # ========== 核心 API ==========

    def link_all(self, paradigm: str = "engineering") -> Dict[str, Any]:
        """
        对指定范式执行全局语义连接推断。

        流程：
        1. 从数据库读取所有 canonical 概念（去重后的）
        2. 按范式层级分组
        3. 阶段1: parent_hint 精确匹配
        4. 阶段2: embedding 相似度初筛
        5. 阶段3: LLM 二次确认
        6. 写入数据库

        Args:
            paradigm: 分解范式，当前仅支持 "engineering"

        Returns:
            {"edges_created": int, "by_stage": {...}, "paradigm": str}
        """
        # LA-027 FIX: 优先从 paradigms.yaml 加载配置，替代硬编码 PARADIGM_LEVELS
        config = _build_paradigm_config(paradigm)
        if not config:
            raise ValueError(f"不支持的范式: {paradigm}")

        # 1. 读取所有概念
        concepts = self._load_canonical_concepts()
        if not concepts:
            return {"edges_created": 0, "by_stage": {}, "paradigm": paradigm, "message": "无可用概念"}

        # 2. 按层级分组
        level_groups = self._group_by_level(concepts, config["levels"])

        # 3. 阶段1: parent_hint 精确匹配
        edges_stage1 = self._stage1_parent_hint_match(level_groups, config, paradigm)

        # 4. 阶段2+3: embedding 初筛 + LLM 确认（排除已有连接的节点对）
        # LA-035 Phase 3: 同时排除已建立 HAS_DETAIL 关系的概念对
        existing_pairs = {(e["parent_id"], e["child_id"]) for e in edges_stage1}
        has_detail_pairs = self._get_has_detail_pairs()
        existing_pairs.update(has_detail_pairs)
        
        edges_stage23 = self._stage23_embedding_then_llm(
            level_groups, config, existing_pairs
        )

        # 5. LA-046: Gap 检测 + 虚拟节点创建（移到 relation_map 校验之前）
        # 策略: 先让同类型连接通过 gap 检测生成虚拟节点，再用 relation_map 校验替换后的合法边
        paradigm_config = _PARADIGMS_YAML.get(paradigm, {})
        fallback_config = paradigm_config.get("fallback", {})
        
        all_edges = edges_stage1 + edges_stage23
        
        virtual_nodes_created = 0
        gap_edges_detected = 0
        if fallback_config.get("create_virtual_nodes", False):
            all_edges, gap_info = self._process_gaps_and_virtual_nodes(
                all_edges, paradigm_config, paradigm
            )
            virtual_nodes_created = gap_info.get("virtual_nodes", 0)
            gap_edges_detected = gap_info.get("gap_edges", 0)
            if gap_edges_detected > 0:
                print(f"[SemanticLinker] LA-046: 检测到 {gap_edges_detected} 条 gap 边，创建 {virtual_nodes_created} 个虚拟节点")
        
        # 6. LA-027 FIX: 使用 paradigms.yaml 的 relation_map 校验连接合法性
        # 在 gap 检测之后执行，确保虚拟节点产生的合法边不被误杀
        relation_map = _build_relation_validator(paradigm)
        if relation_map:
            valid_edges = []
            rejected = []
            for edge in all_edges:
                # 查询 parent 和 child 的实际类型
                parent_type = self._get_concept_type(edge["parent_id"])
                child_type = self._get_concept_type(edge["child_id"])
                relation_type = edge["relation_type"]
                
                if _is_valid_relation(relation_map, parent_type, relation_type, child_type):
                    valid_edges.append(edge)
                else:
                    rejected.append({
                        "parent": edge.get("parent_name", edge["parent_id"]),
                        "parent_type": parent_type,
                        "relation": relation_type,
                        "child": edge.get("child_name", edge["child_id"]),
                        "child_type": child_type,
                        "reason": f"relation_map 禁止 {parent_type} --{relation_type}--> {child_type}",
                    })
            
            if rejected:
                print(f"[SemanticLinker] relation_map 校验拒绝 {len(rejected)} 条非法连接:")
                for r in rejected[:5]:  # 最多打印5条
                    print(f"  ❌ {r['parent']}({r['parent_type']}) --{r['relation']}--> {r['child']}({r['child_type']})")
                if len(rejected) > 5:
                    print(f"  ... 还有 {len(rejected) - 5} 条")
            
            all_edges = valid_edges
        
        # 7. 写入数据库
        self._write_edges(all_edges)

        return {
            "edges_created": len(all_edges),
            "by_stage": {
                "parent_hint_match": len(edges_stage1),
                "embedding_llm": len(edges_stage23),
            },
            "paradigm": paradigm,
            "concept_count": len(concepts),
            "gap_detection": {
                "gap_edges": gap_edges_detected,
                "virtual_nodes": virtual_nodes_created,
            },
        }

    # ========== 辅助: 获取已有 HAS_DETAIL 关系对 ==========

    def _get_has_detail_pairs(self) -> Set[Tuple[str, str]]:
        """
        获取数据库中已有的 HAS_DETAIL 关系对。
        
        LA-035 Phase 3: 语义聚合阶段建立的 HAS_DETAIL 关系
        不应被 SemanticLinker 的 embedding+LLM 阶段重复评估。
        
        Returns:
            {(source_canonical_id, target_canonical_id), ...}
        """
        try:
            edges = self.graph_store.get_has_detail_edges(limit=5000)
            pairs = {(e["source"], e["target"]) for e in edges}
            if pairs:
                print(f"[SemanticLinker] 已有 HAS_DETAIL 关系对: {len(pairs)}")
            return pairs
        except Exception as e:
            print(f"[SemanticLinker] 获取 HAS_DETAIL 关系对失败: {e}")
            return set()

    # ========== 阶段1: parent_hint 精确匹配 ==========

    def _stage1_parent_hint_match(
        self,
        level_groups: Dict[str, List[Dict]],
        config: Dict,
        paradigm: str = "engineering",
    ) -> List[Dict[str, Any]]:
        """
        基于提取时记录的 parent_hint 进行精确匹配。
        匹配策略（按优先级）：
        1. parent_hint 与 immediate upper level 的 canonical name 精确匹配
        2. parent_hint 通过名称映射表查找 canonical ID，再匹配 immediate upper level
        3. parent_hint 在所有层级中搜索（处理 LLM 层级判断不准确的情况）
        4. 【循环范式】同类型 parent_hint（如 technology->technology），用于 gap 检测
        """
        edges = []
        transitions = config["transitions"]
        existing_pairs = set()  # 避免重复边

        # 加载 "原始名称 → canonical ID" 映射表
        name_mapping = self._load_name_mapping()

        # 预先构建"所有概念"的映射（用于策略3）
        all_concepts_map = {}
        all_concepts_id_map = {}
        for level_concepts in level_groups.values():
            for c in level_concepts:
                all_concepts_map[c["name"].strip().lower()] = c
                all_concepts_id_map[c["id"]] = c
                for alias in c.get("aliases", []):
                    if alias:
                        all_concepts_map[alias.strip().lower()] = c

        for (upper_type, lower_type), relation_type in transitions.items():
            parents = level_groups.get(upper_type, [])
            children = level_groups.get(lower_type, [])
            if not parents or not children:
                continue

            # 建立 immediate upper level 的映射
            parent_map = {}
            parent_id_map = {}
            for p in parents:
                parent_map[p["name"].strip().lower()] = p
                parent_id_map[p["id"]] = p
                for alias in p.get("aliases", []):
                    if alias:
                        parent_map[alias.strip().lower()] = p

            for child in children:
                hint = child.get("parent_hint", "").strip()
                if not hint:
                    continue

                hint_lower = hint.lower()
                pair_key = (hint_lower, child["id"])
                if pair_key in existing_pairs:
                    continue

                matched_parent = None
                match_reason = ""

                # 策略1: 精确匹配 immediate upper level
                matched_parent = parent_map.get(hint_lower)
                if matched_parent:
                    match_reason = f"精确匹配: '{hint}' -> '{matched_parent['name']}'"

                # 策略2: 通过名称映射表查找 canonical ID（在 immediate upper level 中）
                if not matched_parent and name_mapping:
                    canonical_id = name_mapping.get(hint_lower)
                    if canonical_id and canonical_id in parent_id_map:
                        matched_parent = parent_id_map[canonical_id]
                        match_reason = f"映射表匹配: '{hint}' -> '{matched_parent['name']}'"

                # 策略3: 在所有层级中搜索（LLM 层级判断不准确时的 fallback）
                if not matched_parent:
                    # 先在所有概念中精确匹配
                    matched_parent = all_concepts_map.get(hint_lower)
                    if matched_parent:
                        match_reason = f"全局搜索: '{hint}' -> '{matched_parent['name']}'"
                    else:
                        # 通过映射表在所有概念中查找
                        canonical_id = name_mapping.get(hint_lower)
                        if canonical_id and canonical_id in all_concepts_id_map:
                            matched_parent = all_concepts_id_map[canonical_id]
                            match_reason = f"全局映射: '{hint}' -> '{matched_parent['name']}'"

                if matched_parent:
                    # 如果匹配到的 parent 类型和期望的 upper_type 不同，调整关系类型
                    actual_relation = relation_type
                    if matched_parent.get("type") != upper_type:
                        # 跨层级连接：根据实际类型调整关系
                        actual_relation = self._determine_cross_level_relation(
                            matched_parent.get("type"), child.get("type")
                        )

                    edges.append({
                        "parent_id": matched_parent["id"],
                        "parent_name": matched_parent["name"],
                        "child_id": child["id"],
                        "child_name": child["name"],
                        "relation_type": actual_relation,
                        "confidence": 1.0,
                        "reason": match_reason,
                        "stage": "parent_hint",
                    })
                    existing_pairs.add(pair_key)

        # 策略4: 【循环范式】同类型 parent_hint（如 technology->technology）
        # 这些连接会被 gap 检测识别为同类型 gap，自动创建虚拟 requirement 节点
        paradigm_config = _PARADIGMS_YAML.get(paradigm, {})
        if paradigm_config.get("cyclic") and paradigm_config.get("gap_rules", {}).get("detect_by_same_type", False):
            for concept_type in level_groups:
                nodes = level_groups.get(concept_type, [])
                if len(nodes) < 2:
                    continue
                # 建立本类型的名称映射
                type_map = {}
                type_id_map = {}
                for n in nodes:
                    type_map[n["name"].strip().lower()] = n
                    type_id_map[n["id"]] = n
                    for alias in n.get("aliases", []):
                        if alias:
                            type_map[alias.strip().lower()] = n

                for child in nodes:
                    hint = child.get("parent_hint", "").strip()
                    if not hint:
                        continue
                    hint_lower = hint.lower()
                    pair_key = (hint_lower, child["id"])
                    if pair_key in existing_pairs:
                        continue

                    matched_parent = type_map.get(hint_lower)
                    if not matched_parent and name_mapping:
                        canonical_id = name_mapping.get(hint_lower)
                        if canonical_id and canonical_id in type_id_map:
                            matched_parent = type_id_map[canonical_id]

                    if matched_parent:
                        # LA-027 FIX: 从 YAML 推导同类型连接的关系类型（替代硬编码 DEPEND_ON）
                        # 对于循环范式，同类型连接使用 concept_type -> cycle_pattern[next] 的关系
                        cycle_pattern = paradigm_config.get("cycle_pattern", [])
                        same_type_relation = "DEPEND_ON"  # fallback
                        if len(cycle_pattern) >= 2:
                            try:
                                idx = cycle_pattern.index(concept_type)
                                next_type = cycle_pattern[(idx + 1) % len(cycle_pattern)]
                                same_type_relation = self._determine_cross_level_relation(
                                    concept_type, next_type, paradigm
                                )
                            except ValueError:
                                pass
                        
                        edges.append({
                            "parent_id": matched_parent["id"],
                            "parent_name": matched_parent["name"],
                            "child_id": child["id"],
                            "child_name": child["name"],
                            "relation_type": same_type_relation,
                            "confidence": 1.0,
                            "reason": f"同类型parent_hint: '{hint}' -> '{matched_parent['name']}' ({concept_type})",
                            "stage": "parent_hint_same_type",
                        })
                        existing_pairs.add(pair_key)

        return edges

    def _determine_cross_level_relation(
        self, parent_type: str, child_type: str, paradigm: str = ""
    ) -> str:
        """
        根据实际类型确定跨层级连接的关系类型。
        优先从 paradigms.yaml 的 relation_map 推导，fallback 到硬编码规则。
        """
        # 优先从 YAML relation_map 查询
        if paradigm:
            p = _PARADIGMS_YAML.get(paradigm, {})
            relation_map = p.get("relation_map", {})
            source_map = relation_map.get(parent_type, {})
            for relation_type, targets in source_map.items():
                if child_type in targets:
                    return relation_type
        
        # Fallback 硬编码规则（向后兼容）
        if parent_type == "requirement" and child_type == "technology":
            return "IMPLEMENTS"
        if parent_type == "technology" and child_type == "requirement":
            return "DEPEND_ON"
        return "DEPEND_ON"

    # ========== LA-046: Gap 检测与虚拟节点 ==========

    def _calculate_gap(self, parent_type: str, child_type: str, paradigm_config: dict) -> int:
        """
        计算层级跳跃的 gap 数。

        非循环范式（theory/hierarchical）: ideal_chain 位置差
        循环范式（engineering）: 同类型连接 = gap=1，反类型连接 = gap=0
        """
        gap_rules = paradigm_config.get("gap_rules", {})

        # 循环范式检测
        if paradigm_config.get("cyclic") and gap_rules.get("detect_by_same_type", False):
            if parent_type == child_type:
                return 1  # 同类型连接 = 缺少中间交替层
            return 0      # 反类型连接 = 正常

        # 非循环范式检测
        ideal_chain = paradigm_config.get("ideal_chain", [])
        if not ideal_chain:
            return 0

        try:
            p_idx = ideal_chain.index(parent_type)
            c_idx = ideal_chain.index(child_type)
            idx_diff = abs(c_idx - p_idx)
            return max(0, idx_diff - 1)
        except ValueError:
            return 0

    def _process_gaps_and_virtual_nodes(
        self,
        edges: List[Dict[str, Any]],
        paradigm_config: dict,
        paradigm: str = "",
    ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """
        LA-046: 遍历所有边，检测 gap，创建虚拟节点替换 gap 边。

        Args:
            paradigm: 范式ID，用于从 YAML 推导关系类型

        Returns:
            (new_edges, {"gap_edges": int, "virtual_nodes": int})
        """
        import uuid

        new_edges = []
        virtual_nodes = []
        gap_edges = 0
        seen_virtual = {}  # (parent_id, child_id) -> virtual_node_id

        for edge in edges:
            parent_id = edge["parent_id"]
            child_id = edge["child_id"]
            relation_type = edge["relation_type"]

            # 查询类型
            parent_type = self._get_concept_type(parent_id)
            child_type = self._get_concept_type(child_id)

            gap = self._calculate_gap(parent_type, child_type, paradigm_config)

            if gap > 0:
                gap_edges += 1

                # 推断缺失的中间层类型
                missing_type = self._infer_missing_type(parent_type, child_type, paradigm_config)
                if not missing_type:
                    # 无法推断缺失类型，保留原始边
                    new_edges.append(edge)
                    continue

                # 创建或复用虚拟节点
                vkey = (parent_id, child_id)
                if vkey in seen_virtual:
                    virtual_id = seen_virtual[vkey]
                else:
                    virtual_id = self._create_virtual_node_id(parent_id, child_id, missing_type)
                    virtual_name = self._build_virtual_node_name(missing_type, paradigm_config)
                    virtual_nodes.append({
                        "canonical_id": virtual_id,
                        "name": virtual_name,
                        "concept_type": missing_type,
                        "description": f"[VIRTUAL] 从 '{edge.get('parent_name', parent_id)}' 到 '{edge.get('child_name', child_id)}' 推断出的缺失 {missing_type} 层",
                        "is_virtual": True,
                        "source_chunks": '["__virtual__"]',
                    })
                    seen_virtual[vkey] = virtual_id

                # 推断两条正常边
                # edge1: parent -> virtual（使用正常关系）
                rel1 = self._determine_cross_level_relation(parent_type, missing_type, paradigm)
                new_edges.append({
                    "parent_id": parent_id,
                    "parent_name": edge.get("parent_name", ""),
                    "child_id": virtual_id,
                    "child_name": virtual_nodes[-1]["name"],
                    "relation_type": rel1,
                    "confidence": edge.get("confidence", 0.5) * 0.9,  # gap 边置信度折扣
                    "reason": f"[GAP] {edge.get('reason', '')} (中间缺失 {missing_type})",
                })

                # edge2: virtual -> child（使用正常关系）
                rel2 = self._determine_cross_level_relation(missing_type, child_type, paradigm)
                new_edges.append({
                    "parent_id": virtual_id,
                    "parent_name": virtual_nodes[-1]["name"],
                    "child_id": child_id,
                    "child_name": edge.get("child_name", ""),
                    "relation_type": rel2,
                    "confidence": edge.get("confidence", 0.5) * 0.9,
                    "reason": f"[GAP] {edge.get('reason', '')} (中间缺失 {missing_type})",
                })
            else:
                new_edges.append(edge)

        # 先写入虚拟节点
        if virtual_nodes:
            self._write_virtual_nodes(virtual_nodes)

        return new_edges, {"gap_edges": gap_edges, "virtual_nodes": len(virtual_nodes)}

    def _infer_missing_type(self, parent_type: str, child_type: str, paradigm_config: dict) -> Optional[str]:
        """推断 gap 中间缺失的类型。"""
        if paradigm_config.get("cyclic"):
            # 循环范式：同类型 gap = 中间是另一种类型
            cycle_pattern = paradigm_config.get("cycle_pattern", [])
            if not cycle_pattern:
                return None
            if parent_type == child_type:
                # 找到 parent_type 在 cycle_pattern 中的下一个类型
                try:
                    idx = cycle_pattern.index(parent_type)
                    next_idx = (idx + 1) % len(cycle_pattern)
                    return cycle_pattern[next_idx]
                except ValueError:
                    return None
            return None

        # 非循环范式：ideal_chain 中缺失的中间类型
        ideal_chain = paradigm_config.get("ideal_chain", [])
        try:
            p_idx = ideal_chain.index(parent_type)
            c_idx = ideal_chain.index(child_type)
            if abs(c_idx - p_idx) == 2:
                # 跳过一层
                mid_idx = (p_idx + c_idx) // 2
                return ideal_chain[mid_idx]
        except ValueError:
            pass
        return None

    def _create_virtual_node_id(self, parent_id: str, child_id: str, missing_type: str) -> str:
        """生成唯一的虚拟节点 canonical_id。"""
        import uuid
        short_parent = parent_id.replace("concept_canonical_", "")[:8]
        short_child = child_id.replace("concept_canonical_", "")[:8]
        return f"__virtual_{uuid.uuid4().hex[:8]}_{missing_type}_{short_parent}_{short_child}"

    def _build_virtual_node_name(self, missing_type: str, paradigm_config: dict) -> str:
        """构建虚拟节点的显示名称：[缺失]类型名。"""
        types = paradigm_config.get("types", {})
        type_label = types.get(missing_type, missing_type)
        return f"[缺失]{type_label}"

    def _write_virtual_nodes(self, virtual_nodes: List[Dict[str, Any]]) -> int:
        """将虚拟节点写入 KùzuDB。"""
        conn = self.graph_store._ensure_db()
        esc = self.graph_store._escape_cypher_string
        written = 0

        for node in virtual_nodes:
            safe_id = esc(node["canonical_id"])
            safe_name = esc(node["name"])
            safe_type = esc(node["concept_type"])
            safe_desc = esc(node["description"])
            safe_chunks = esc(node.get("source_chunks", '["__virtual__"]'))

            # KùzuDB 的 BOOL 类型可能不支持，使用 STRING 回退
            is_virtual_val = "true"  # Cypher 中 bool 小写

            cypher = f"""
                MERGE (c:CanonicalConcept {{
                    canonical_id: '{safe_id}'
                }})
                ON CREATE SET c.name = '{safe_name}',
                              c.concept_type = '{safe_type}',
                              c.description = '{safe_desc}',
                              c.source_chunks = '{safe_chunks}',
                              c.is_virtual = {is_virtual_val}
            """
            try:
                conn.execute(cypher)
                written += 1
            except Exception as e:
                # 如果 is_virtual BOOL 失败，尝试不设置该字段
                print(f"[SemanticLinker] 虚拟节点写入带 is_virtual 失败: {e}")
                fallback_cypher = f"""
                    MERGE (c:CanonicalConcept {{
                        canonical_id: '{safe_id}'
                    }})
                    ON CREATE SET c.name = '{safe_name}',
                                  c.concept_type = '{safe_type}',
                                  c.description = '{safe_desc}',
                                  c.source_chunks = '{safe_chunks}'
                """
                try:
                    conn.execute(fallback_cypher)
                    written += 1
                except Exception as e2:
                    print(f"[SemanticLinker] 虚拟节点写入完全失败: {e2}")

        print(f"[SemanticLinker] 写入 {written} 个虚拟节点")
        return written

    def _load_name_mapping(self) -> Dict[str, str]:
        """
        加载 "原始名称 → canonical ID" 映射表。
        由 ConceptDeduper 在去重后生成。
        """
        mapping_path = KNOWLEDGE_BASE_DIR / f"{self.collection_name}_name_mapping.json"
        if not mapping_path.exists():
            return {}

        try:
            with open(mapping_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[SemanticLinker] 加载名称映射表失败: {e}")
            return {}

    # ========== 阶段2+3: embedding 初筛 + LLM 确认 ==========

    def _stage23_embedding_then_llm(
        self,
        level_groups: Dict[str, List[Dict]],
        config: Dict,
        existing_pairs: set,
    ) -> List[Dict[str, Any]]:
        """
        对没有 parent_hint 匹配的概念对，进行 embedding 相似度初筛 + LLM 二次确认。
        """
        edges = []
        transitions = config["transitions"]

        for (upper_type, lower_type), relation_type in transitions.items():
            parents = level_groups.get(upper_type, [])
            children = level_groups.get(lower_type, [])
            if not parents or not children:
                continue

            # LA-027 FIX: 从 config.relations 动态获取关系含义，替代硬编码字典
            relations_dict = config.get("relations", {})
            relation_meaning = relations_dict.get(
                relation_type,
                "上层概念与下层概念存在语义关联"
            )

            # 阶段2: embedding 初筛
            candidate_pairs = []
            for parent in parents:
                for child in children:
                    pair_key = (parent["id"], child["id"])
                    if pair_key in existing_pairs:
                        continue

                    sim = self._compute_similarity(parent, child)
                    if sim >= self.embedding_threshold:
                        candidate_pairs.append((parent, child, sim))

            if not candidate_pairs:
                continue

            # 按相似度排序，优先处理相似度高的对
            candidate_pairs.sort(key=lambda x: x[2], reverse=True)

            # 阶段3: LLM 二次确认
            for parent, child, sim in candidate_pairs:
                pair_key = (parent["id"], child["id"])
                if pair_key in existing_pairs:
                    continue

                result = self._llm_judge(
                    parent, child, relation_type, relation_meaning
                )

                if result.get("has_relation") and result.get("confidence", 0) >= self.llm_threshold:
                    edges.append({
                        "parent_id": parent["id"],
                        "parent_name": parent["name"],
                        "child_id": child["id"],
                        "child_name": child["name"],
                        "relation_type": relation_type,
                        "confidence": result.get("confidence", 0.0),
                        "reason": result.get("reason", ""),
                        "stage": "embedding_llm",
                    })
                    existing_pairs.add(pair_key)

        return edges

    # ========== LLM 判断 ==========

    def _llm_judge(
        self,
        parent: Dict[str, Any],
        child: Dict[str, Any],
        relation_type: str,
        relation_meaning: str,
    ) -> Dict[str, Any]:
        """
        使用 LLM 判断两个概念之间是否存在语义连接。
        """
        if not self.llm.available:
            return {"has_relation": False, "confidence": 0.0, "reason": "LLM不可用"}

        prompt = _LINK_JUDGE_PROMPT.format(
            parent_name=parent["name"],
            parent_type=parent["type"],
            parent_description=parent.get("description", ""),
            child_name=child["name"],
            child_type=child["type"],
            child_description=child.get("description", ""),
            relation_type=relation_type,
            relation_meaning=relation_meaning,
        )

        try:
            result = self.llm.chat_json(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200,
            )
            if isinstance(result, dict):
                return result
            return {"has_relation": False, "confidence": 0.0, "reason": "解析失败"}
        except Exception as e:
            print(f"[SemanticLinker] LLM 判断失败: {e}")
            return {"has_relation": False, "confidence": 0.0, "reason": str(e)}

    # ========== 相似度计算 ==========

    def _get_embedding(self, text: str) -> List[float]:
        """获取文本的 embedding 向量。"""
        if not text:
            return [0.0] * 2048
        try:
            emb = self._embedding_cache.get(text)
            if emb is not None:
                return emb
            emb = self.embeddings.embed_single(text)
            self._embedding_cache[text] = emb
            return emb
        except Exception:
            return [0.0] * 2048

    def _compute_similarity(self, parent: Dict, child: Dict) -> float:
        """
        计算两个概念的 embedding 相似度。

        策略：比较 parent 的 name+description 与 child 的 name+description+parent_hint。
        使用 cosine 相似度。
        """
        parent_emb = parent.get("embedding")
        child_emb = child.get("embedding")

        if parent_emb is None or child_emb is None:
            return 0.0

        try:
            parent_vec = np.array(parent_emb, dtype=np.float32)
            child_vec = np.array(child_emb, dtype=np.float32)

            # 归一化
            parent_norm = np.linalg.norm(parent_vec)
            child_norm = np.linalg.norm(child_vec)

            if parent_norm == 0 or child_norm == 0:
                return 0.0

            cosine_sim = np.dot(parent_vec, child_vec) / (parent_norm * child_norm)
            return float(cosine_sim)
        except Exception as e:
            print(f"[SemanticLinker] 相似度计算失败: {e}")
            return 0.0

    # ========== 数据加载与分组 ==========

    def _load_canonical_concepts(self) -> List[Dict[str, Any]]:
        """
        加载所有 canonical 概念。
        优先从 KùzuDB 读取，fallback 到 CSV。

        返回的概念包含:
        - id: canonical 概念 ID
        - name: 概念名称
        - type: 概念类型
        - description: 描述
        - aliases: 别名列表
        - embedding: embedding 向量（实时计算）
        - parent_hint: parent_hint
        - source_chunks: 来源 chunk ID 列表
        """
        # LA-027 FIX: 初始化类型缓存
        self._concept_type_cache = {}
        
        # 1. 优先从 KùzuDB 读取
        db_concepts = self._load_from_kuzudb()
        if db_concepts:
            return db_concepts

        # 2. Fallback: 从 CSV 读取（兼容旧数据）
        csv_concepts = self._load_from_csv()

        merged = []
        for concept_id, csv_info in csv_concepts.items():
            merged.append({
                "id": concept_id,
                "name": csv_info.get("name", ""),
                "type": csv_info.get("concept_type", ""),
                "description": csv_info.get("description", ""),
                "aliases": csv_info.get("aliases", []),
                "embedding": csv_info.get("embedding", None),
                "parent_hint": csv_info.get("parent_hint", ""),
                "source_chunks": csv_info.get("source_chunks", []),
            })
            # 填充类型缓存
            self._concept_type_cache[concept_id] = csv_info.get("concept_type", "")

        return merged

    def _load_from_kuzudb(self) -> List[Dict[str, Any]]:
        """
        从 KùzuDB 读取 CanonicalConcept 节点。
        embedding 使用批量计算（减少 API 调用次数）。
        """
        try:
            nodes = self.graph_store.get_canonical_concepts(limit=10000)
            if not nodes:
                return []

            # 批量计算所有概念的 embedding
            names = [n.get("name", "") for n in nodes if n.get("name", "").strip()]
            if names:
                try:
                    embs = self.embeddings.embed(names)
                    name_to_emb = {name: emb for name, emb in zip(names, embs)}
                except Exception as e:
                    print(f"[SemanticLinker] 批量 embedding 计算失败: {e}")
                    name_to_emb = {}
            else:
                name_to_emb = {}

            result = []
            for node in nodes:
                name = node.get("name", "")
                if not name:
                    continue

                emb = name_to_emb.get(name)

                # 解析 source_chunks（JSON 字符串）
                source_chunks_raw = node.get("source_chunks", "[]")
                try:
                    source_chunks = json.loads(source_chunks_raw) if isinstance(source_chunks_raw, str) else source_chunks_raw
                except json.JSONDecodeError:
                    source_chunks = []

                # 解析 aliases（JSON 字符串）
                aliases_raw = node.get("aliases", "[]")
                try:
                    aliases = json.loads(aliases_raw) if isinstance(aliases_raw, str) else aliases_raw
                except json.JSONDecodeError:
                    aliases = []

                result.append({
                    "id": node.get("id", ""),
                    "name": name,
                    "type": node.get("type", ""),
                    "description": node.get("description", ""),
                    "aliases": aliases,
                    "embedding": emb,
                    "parent_hint": node.get("parent_hint", ""),
                    "source_chunks": source_chunks,
                })
                # LA-027 FIX: 填充类型缓存
                self._concept_type_cache[node.get("id", "")] = node.get("type", "")

            return result
        except Exception as e:
            print(f"[SemanticLinker] 从 KùzuDB 读取 canonical 概念失败: {e}")
            return []

    def _load_from_csv(self) -> Dict[str, Dict]:
        """
        从去重后的 CSV 文件读取概念完整信息。

        CSV 文件路径: knowledge_base/{subject}_concepts.csv
        """
        csv_path = KNOWLEDGE_BASE_DIR / f"{self.collection_name}_concepts.csv"
        if not csv_path.exists():
            return {}

        result = {}
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    concept_id = row.get("id", "").strip()
                    if not concept_id:
                        continue

                    # 解析 embedding（JSON 数组字符串）
                    embedding = None
                    emb_str = row.get("embedding", "")
                    if emb_str:
                        try:
                            embedding = json.loads(emb_str)
                        except json.JSONDecodeError:
                            pass

                    # 解析 aliases（分号分隔）
                    aliases = []
                    alias_str = row.get("aliases", "")
                    if alias_str:
                        aliases = [a.strip() for a in alias_str.split(";") if a.strip()]

                    # 解析 source_chunks（逗号分隔）
                    chunks = []
                    chunk_str = row.get("source_chunks", "")
                    if chunk_str:
                        chunks = [c.strip() for c in chunk_str.split(",") if c.strip()]

                    result[concept_id] = {
                        "name": row.get("name", ""),
                        "concept_type": row.get("concept_type", ""),
                        "description": row.get("description", ""),
                        "aliases": aliases,
                        "embedding": embedding,
                        "parent_hint": row.get("parent_hint", ""),
                        "source_chunks": chunks,
                    }
        except Exception as e:
            print(f"[SemanticLinker] 读取 CSV 失败: {e}")

        return result

    def _get_concept_type(self, canonical_id: str) -> str:
        """
        根据 canonical_id 查询概念类型。
        
        LA-027 FIX: relation_map 校验需要知道边的两端实际类型。
        优先从已加载的概念缓存查询，否则查数据库。
        """
        # 尝试从缓存查询（如果 _load_canonical_concepts 已被调用）
        if hasattr(self, '_concept_type_cache') and canonical_id in self._concept_type_cache:
            return self._concept_type_cache[canonical_id]
        
        # 查数据库
        try:
            result = self.graph_store._execute(
                self.graph_store._ensure_db(),
                f"MATCH (c:CanonicalConcept {{canonical_id: '{self.graph_store._escape_cypher_string(canonical_id)}'}}) RETURN c.concept_type"
            )
            if result.has_next():
                return result.get_next()[0] or ""
        except Exception:
            pass
        return ""

    def _group_by_level(
        self,
        concepts: List[Dict],
        level_types: List[str],
    ) -> Dict[str, List[Dict]]:
        """
        按概念类型分组。
        """
        groups = {t: [] for t in level_types}
        for c in concepts:
            ct = c.get("type", "").lower()
            if ct in groups:
                groups[ct].append(c)
        return groups

    # ========== 数据库写入 ==========

    def _write_edges(self, edges: List[Dict[str, Any]]) -> int:
        """
        将语义连接边写入 KùzuDB。
        如果 canonical 概念节点不存在，则先创建。
        """
        conn = self.graph_store._ensure_db()
        written = 0
        esc = self.graph_store._escape_cypher_string

        for edge in edges:
            # 先确保两端节点存在（MERGE canonical 概念节点）
            for node_id, node_name in [(edge['parent_id'], edge.get('parent_name', '')),
                                        (edge['child_id'], edge.get('child_name', ''))]:
                safe_id = esc(node_id)
                safe_name = esc(node_name)
                merge_node_cypher = f"""
                    MERGE (c:CanonicalConcept {{
                        canonical_id: '{safe_id}'
                    }})
                    ON CREATE SET c.name = '{safe_name}', c.is_virtual = false
                """
                try:
                    conn.execute(merge_node_cypher)
                except Exception as e:
                    # 如果 is_virtual BOOL 失败，尝试不带该字段
                    if "is_virtual" in str(e) or "BOOL" in str(e):
                        merge_node_cypher_fallback = f"""
                            MERGE (c:CanonicalConcept {{
                                canonical_id: '{safe_id}'
                            }})
                            ON CREATE SET c.name = '{safe_name}'
                        """
                        try:
                            conn.execute(merge_node_cypher_fallback)
                        except Exception as e2:
                            print(f"[SemanticLinker] 创建节点失败 {node_id}: {e2}")
                    else:
                        print(f"[SemanticLinker] 创建节点失败 {node_id}: {e}")

            # 创建关系
            safe_parent_id = esc(edge['parent_id'])
            safe_child_id = esc(edge['child_id'])
            safe_relation = esc(edge['relation_type'])
            confidence = float(edge.get('confidence', 0.0))
            cypher = f"""
                MATCH (p:CanonicalConcept {{canonical_id: '{safe_parent_id}'}}),
                      (c:CanonicalConcept {{canonical_id: '{safe_child_id}'}})
                CREATE (p)-[:{safe_relation} {{confidence: {confidence}}}]->(c)
            """
            try:
                conn.execute(cypher)
                written += 1
            except Exception as e:
                print(f"[SemanticLinker] 写入边失败: {e}")

        print(f"[SemanticLinker] 写入 {written} 条语义连接边")
        return written


# ========== CLI 测试入口 ==========

def main():
    import sys

    subject = sys.argv[1] if len(sys.argv) > 1 else "ai_llm_v2"
    print(f"=== SemanticLinker: {subject} ===")

    linker = SemanticLinker(subject)
    result = linker.link_all(paradigm="engineering")

    print(f"\n结果:")
    print(f"  创建边数: {result['edges_created']}")
    print(f"  parent_hint 匹配: {result['by_stage']['parent_hint_match']}")
    print(f"  embedding+LLM: {result['by_stage']['embedding_llm']}")
    print(f"  概念总数: {result['concept_count']}")


if __name__ == "__main__":
    main()
