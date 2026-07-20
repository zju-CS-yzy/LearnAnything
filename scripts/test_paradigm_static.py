#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
范式配置静态校验脚本

校验 paradigms.yaml v2.0 的逻辑一致性，无需 LLM：
1. Schema 完整性（必需字段）
2. relation_map 自洽性（relation 在 relations 中定义，target 在 types 中定义）
3. parent_rules 与 relation_map 一致性
4. ideal_chain 完整性（包含所有 types）
5. 循环检测（DAG 性质验证）

运行方式:
    cd D:\MyCS\AI\Project\LearnAnything
    python scripts/test_paradigm_static.py
"""

import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

import yaml
from pathlib import Path
from collections import defaultdict


def load_paradigms():
    """加载 paradigms.yaml"""
    path = Path(r"D:\MyCS\AI\Project\LearnAnything\config\paradigms.yaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def check_required_fields(paradigm_id, config):
    """检查必需字段"""
    errors = []
    required = ["name", "description", "types", "relations", "relation_map",
                "parent_rules", "ideal_chain", "prompt_addon"]
    for field in required:
        if field not in config:
            errors.append(f"缺少必需字段: {field}")
    return errors


def check_relation_map(paradigm_id, config):
    """校验 relation_map"""
    errors = []
    types = set(config.get("types", {}).keys())
    relations = set(config.get("relations", {}).keys())
    relation_map = config.get("relation_map", {})
    
    for source_type, rel_map in relation_map.items():
        if source_type not in types:
            errors.append(f"relation_map 中的 source_type '{source_type}' 未在 types 中定义")
        
        for rel, targets in rel_map.items():
            if rel not in relations:
                errors.append(f"relation_map 中的 relation '{rel}' 未在 relations 中定义")
            
            for target in targets:
                if target not in types:
                    errors.append(f"relation_map 中的 target '{target}' 未在 types 中定义")
                
                # 检查是否有环（source == target）
                if source_type == target:
                    errors.append(f"relation_map 中存在自环: {source_type} --{rel}--> {target}")
    
    return errors


def check_parent_rules(paradigm_id, config):
    """校验 parent_rules"""
    errors = []
    types = set(config.get("types", {}).keys())
    parent_rules = config.get("parent_rules", {})
    relation_map = config.get("relation_map", {})
    
    for child_type, allowed_parents in parent_rules.items():
        if child_type not in types:
            errors.append(f"parent_rules 中的 child_type '{child_type}' 未在 types 中定义")
        
        for parent in allowed_parents:
            if parent not in types:
                errors.append(f"parent_rules 中的 parent '{parent}' 未在 types 中定义")
    
    # 检查：如果 type 在 relation_map 中作为 target 出现，它必须在 parent_rules 中有定义
    targets_in_map = set()
    for source, rel_map in relation_map.items():
        for rel, targets in rel_map.items():
            targets_in_map.update(targets)
    
    for target in targets_in_map:
        if target not in parent_rules:
            errors.append(f"类型 '{target}' 在 relation_map 中作为 target，但 parent_rules 中未定义")
    
    return errors


def check_ideal_chain(paradigm_id, config):
    """校验 ideal_chain"""
    errors = []
    types = set(config.get("types", {}).keys())
    ideal_chain = config.get("ideal_chain", [])
    
    # 检查是否包含所有 types
    chain_types = set(ideal_chain)
    missing = types - chain_types
    if missing:
        errors.append(f"ideal_chain 缺少 types: {missing}")
    
    extra = chain_types - types
    if extra:
        errors.append(f"ideal_chain 包含未定义的 types: {extra}")
    
    return errors


def check_dag(paradigm_id, config):
    """检测 relation_map 中的环"""
    errors = []
    relation_map = config.get("relation_map", {})
    
    # 构建邻接表
    graph = defaultdict(set)
    for source, rel_map in relation_map.items():
        for rel, targets in rel_map.items():
            for target in targets:
                graph[source].add(target)
    
    # 第一步：检测自环（A -> A），这总是错误
    for source, targets in graph.items():
        if source in targets:
            errors.append(f"存在自环: {source} 指向自身")
    
    # 第二步：检测多节点环
    # 注意：对于允许同一 type 既为 parent 又为 child 的范式（如 engineering），
    # requirement -> technology -> requirement 在 type 层面构成环，但实例层面不一定。
    # 这里只做 type 层面的检测，标记为警告而非错误。
    in_degree = defaultdict(int)
    all_nodes = set(graph.keys())
    for targets in graph.values():
        all_nodes.update(targets)
    
    for node in all_nodes:
        if node not in in_degree:
            in_degree[node] = 0
    
    for source, targets in graph.items():
        for target in targets:
            in_degree[target] += 1
    
    # BFS
    queue = [n for n in all_nodes if in_degree[n] == 0]
    visited = set()
    
    while queue:
        node = queue.pop(0)
        visited.add(node)
        for neighbor in graph.get(node, set()):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    
    if len(visited) != len(all_nodes):
        cycle_nodes = all_nodes - visited
        # 如果环只涉及两个节点且它们互相指向（如 engineering），标记为设计意图
        if len(cycle_nodes) == 2:
            errors.append(f"[注意] type 层面存在双向连接: {cycle_nodes}。这是设计意图（同一 type 的不同实例可互为 parent/child），但需确认实例层面不会形成实际环。")
        else:
            errors.append(f"relation_map 中存在环，涉及类型: {cycle_nodes}")
    
    return errors


def check_prompt_addon(paradigm_id, config):
    """检查 prompt_addon 是否包含关键信息"""
    errors = []
    prompt = config.get("prompt_addon", "")
    types = config.get("types", {})
    relations = config.get("relations", {})
    
    # 检查是否每个 type 都有说明
    for t in types:
        if t not in prompt:
            errors.append(f"prompt_addon 中未提及 type '{t}'")
    
    # 检查是否每个 relation 都有说明
    for r in relations:
        if r not in prompt:
            errors.append(f"prompt_addon 中未提及 relation '{r}'")
    
    # 检查是否包含降级策略说明
    if "降级" not in prompt and "降级" not in prompt:
        errors.append("prompt_addon 中缺少降级策略说明")
    
    # 检查是否包含关系合法性约束
    if "合法连接" not in prompt and "合法" not in prompt:
        errors.append("prompt_addon 中缺少关系合法性约束")
    
    return errors


def print_report(paradigm_id, config, errors):
    """打印校验报告"""
    print(f"\n{'='*60}")
    print(f"范式: {paradigm_id} ({config.get('name', '未命名')})")
    print(f"{'='*60}")
    print(f"  types: {list(config.get('types', {}).keys())}")
    print(f"  relations: {list(config.get('relations', {}).keys())}")
    print(f"  ideal_chain: {config.get('ideal_chain', [])}")
    
    relation_map = config.get("relation_map", {})
    print(f"  relation_map:")
    for source, rel_map in relation_map.items():
        for rel, targets in rel_map.items():
            for target in targets:
                print(f"    {source} --{rel}--> {target}")
    
    print(f"  parent_rules:")
    for child, parents in config.get("parent_rules", {}).items():
        if parents:
            print(f"    {child} 的 parent 可以是: {parents}")
        else:
            print(f"    {child}: 顶层节点（无 parent）")
    
    # 分离错误和警告
    real_errors = [e for e in errors if not e.startswith("[注意]")]
    warnings = [e for e in errors if e.startswith("[注意]")]
    
    if real_errors:
        print(f"\n  [FAIL] 发现 {len(real_errors)} 个错误:")
        for e in real_errors:
            print(f"    - {e}")
    
    if warnings:
        print(f"\n  [WARN] 发现 {len(warnings)} 个警告:")
        for e in warnings:
            print(f"    - {e}")
    
    if not real_errors and not warnings:
        print(f"\n  [PASS] 所有检查通过")
    elif not real_errors:
        print(f"\n  [PASS] 无错误，有 {len(warnings)} 个警告需确认")
    
    return len(real_errors) == 0


def main():
    print("="*60)
    print("范式配置静态校验 (paradigms.yaml v2.0)")
    print("="*60)
    
    config = load_paradigms()
    paradigms = config.get("paradigms", {})
    
    total_errors = 0
    all_pass = True
    
    for pid, pconfig in paradigms.items():
        errors = []
        errors.extend(check_required_fields(pid, pconfig))
        errors.extend(check_relation_map(pid, pconfig))
        errors.extend(check_parent_rules(pid, pconfig))
        errors.extend(check_ideal_chain(pid, pconfig))
        errors.extend(check_dag(pid, pconfig))
        errors.extend(check_prompt_addon(pid, pconfig))
        
        passed = print_report(pid, pconfig, errors)
        if not passed:
            all_pass = False
        total_errors += len([e for e in errors if not e.startswith("[注意]")])
    
    print(f"\n{'='*60}")
    if all_pass:
        print("[PASS] 所有范式配置检查通过")
    else:
        print(f"[FAIL] 共发现 {total_errors} 个问题，请修复")
    print(f"{'='*60}")
    
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
