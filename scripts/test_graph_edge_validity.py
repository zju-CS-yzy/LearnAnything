#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
现有图谱边合法性检查脚本

检查已构建的知识图谱中的边是否符合 paradigms.yaml v2.0 的 relation_map。

运行方式:
    cd D:\MyCS\AI\Project\LearnAnything
    python scripts/test_graph_edge_validity.py
"""

import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

import yaml
from pathlib import Path


def load_paradigms():
    path = Path(r"D:\MyCS\AI\Project\LearnAnything\config\paradigms.yaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["paradigms"]


def check_graph_edges(subject_id: str, paradigm_id: str):
    """检查指定学科的图谱边合法性"""
    paradigms = load_paradigms()
    paradigm = paradigms.get(paradigm_id)
    if not paradigm:
        print(f"[ERROR] 未知范式: {paradigm_id}")
        return
    
    relation_map = paradigm.get("relation_map", {})
    types = set(paradigm.get("types", {}).keys())
    
    # 读取 graph_store 数据
    # 使用 KuzuDB 查询边
    try:
        sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")
        from core.graph_store import GraphStore
        
        store = GraphStore(subject_id)
        conn = store._ensure_db()
        
        # 先列出所有表
        print(f"  检查数据库表...")
        tables_result = store._execute(conn, "CALL show_tables() RETURN *")
        tables = []
        while tables_result.has_next():
            row = tables_result.get_next()
            tables.append(row[0])
        print(f"  数据库中的表: {tables}")
        
        # 确定概念节点表名
        concept_table = None
        for t in ["CanonicalConcept", "Concept", "ExtractedConcept"]:
            if t in tables:
                concept_table = t
                break
        
        if not concept_table:
            print(f"  [WARN] 未找到概念节点表，跳过边检查")
            store.close()
            return
        
        print(f"  使用概念表: {concept_table}")
        
        # 查询概念之间的边
        query = f"""
        MATCH (a:{concept_table})-[r]->(b:{concept_table})
        RETURN a.name AS source_name, a.concept_type AS source_type,
               LABEL(r) AS relation_type,
               b.name AS target_name, b.concept_type AS target_type
        """
        
        result = store._execute(conn, query)
        
        total_edges = 0
        valid_edges = 0
        invalid_edges = []
        
        while result.has_next():
            row = result.get_next()
            total_edges += 1
            
            source_type = row[1]
            relation = row[2]
            target_type = row[4]
            
            # 检查 source_type 和 target_type 是否在定义的 types 中
            if source_type not in types:
                invalid_edges.append({
                    "edge": f"{row[0]}({source_type}) --{relation}--> {row[3]}({target_type})",
                    "reason": f"source_type '{source_type}' 不在范式定义的 types 中"
                })
                continue
            
            if target_type not in types:
                invalid_edges.append({
                    "edge": f"{row[0]}({source_type}) --{relation}--> {row[3]}({target_type})",
                    "reason": f"target_type '{target_type}' 不在范式定义的 types 中"
                })
                continue
            
            # 检查 relation 是否在定义的 relations 中
            allowed_relations = set(paradigm.get("relations", {}).keys())
            if relation not in allowed_relations:
                invalid_edges.append({
                    "edge": f"{row[0]}({source_type}) --{relation}--> {row[3]}({target_type})",
                    "reason": f"relation '{relation}' 不在范式定义的 relations 中"
                })
                continue
            
            # 检查 relation_map 合法性
            type_rel_map = relation_map.get(source_type, {})
            allowed_targets = type_rel_map.get(relation, [])
            
            if target_type not in allowed_targets:
                invalid_edges.append({
                    "edge": f"{row[0]}({source_type}) --{relation}--> {row[3]}({target_type})",
                    "reason": f"根据 relation_map，{source_type} --{relation}--> 的 target 只能是 {allowed_targets}，而非 '{target_type}'"
                })
                continue
            
            valid_edges += 1
        
        print(f"\n{'='*60}")
        print(f"学科: {subject_id} (范式: {paradigm_id})")
        print(f"{'='*60}")
        print(f"  总边数: {total_edges}")
        print(f"  合法边: {valid_edges}")
        print(f"  非法边: {len(invalid_edges)}")
        
        if invalid_edges:
            print(f"\n  非法边详情:")
            for inv in invalid_edges[:20]:  # 最多显示 20 条
                print(f"    - {inv['edge']}")
                print(f"      原因: {inv['reason']}")
            if len(invalid_edges) > 20:
                print(f"    ... 还有 {len(invalid_edges) - 20} 条非法边")
        else:
            print(f"\n  [PASS] 所有边均符合范式配置")
        
        store.close()
        
    except Exception as e:
        print(f"[ERROR] 检查失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    print("="*60)
    print("现有图谱边合法性检查")
    print("="*60)
    
    # 检查 transformer 学科（使用 theory 范式）
    check_graph_edges("transformer", "theory")
    
    # 检查 rag 学科（使用 theory 范式）
    check_graph_edges("rag", "theory")
    
    print("\n" + "="*60)
    print("检查完成")
    print("="*60)


if __name__ == "__main__":
    main()
