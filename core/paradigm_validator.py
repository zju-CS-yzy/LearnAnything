#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ParadigmValidator — 范式配置校验器

校验规则来源：docs/DESIGN.md 15.3.2
"""

import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """校验结果"""
    valid: bool
    errors: List[str]
    warnings: List[str]
    auto_generated: Dict[str, Any]


class ParadigmValidator:
    """范式配置校验器"""

    # 约束常量
    MIN_TYPES = 2
    MAX_TYPES = 8
    MIN_RELATIONS = 2
    MAX_RELATIONS = 6
    TYPE_KEY_PATTERN = re.compile(r"^[a-z_]+$")
    RELATION_KEY_PATTERN = re.compile(r"^[A-Z_]+$")

    # 默认调色板（为关系分配颜色）
    DEFAULT_PALETTE = [
        "#e67e22", "#9b59b6", "#3498db", "#27ae60",
        "#e74c3c", "#f39c12", "#1abc9c", "#8e44ad"
    ]

    def __init__(self, existing_paradigms: Optional[Dict] = None):
        """
        Args:
            existing_paradigms: 已有范式配置，用于检查 paradigm_id 唯一性
        """
        self.existing_ids = set(existing_paradigms.keys()) if existing_paradigms else set()

    def validate(self, data: Dict) -> ValidationResult:
        """
        完整校验范式配置。
        
        Returns:
            ValidationResult: 包含是否有效、错误列表、警告列表、自动生成字段
        """
        errors = []
        warnings = []
        auto_generated = {}

        # 1. schema 校验（必填字段）
        required = ["paradigm_id", "name", "description", "types", "relations", "relation_map"]
        for field in required:
            if field not in data or data[field] is None:
                errors.append(f"缺少必填字段: {field}")

        if errors:
            return ValidationResult(False, errors, warnings, auto_generated)

        # 2. paradigm_id 校验
        pid = data["paradigm_id"]
        if not isinstance(pid, str):
            errors.append("paradigm_id 必须是字符串")
        elif not self.TYPE_KEY_PATTERN.match(pid):
            errors.append(f"paradigm_id '{pid}' 格式非法，必须匹配 ^[a-z_]+$")
        elif pid in self.existing_ids:
            errors.append(f"paradigm_id '{pid}' 已存在")

        # 3. types 校验
        types = data.get("types", {})
        type_errors = self._validate_types(types)
        errors.extend(type_errors)

        # 4. relations 校验
        relations = data.get("relations", {})
        rel_errors = self._validate_relations(relations)
        errors.extend(rel_errors)

        # 5. relation_map 校验
        relation_map = data.get("relation_map", {})
        if types and relations:
            map_errors = self._validate_relation_map(relation_map, types, relations)
            errors.extend(map_errors)

        # 6. type-level 环检测
        if relation_map and not type_errors and not rel_errors:
            cycle_errors = self._check_type_level_cycles(relation_map)
            errors.extend(cycle_errors)

        # 如果基础校验通过，生成自动字段
        if not errors:
            # 7. 自动生成 parent_rules
            auto_generated["parent_rules"] = self._auto_parent_rules(relation_map, types)

            # 8. 自动生成 styles
            auto_generated["styles"] = self._auto_styles(relations)

            # 9. 自动生成 ideal_chain（如果未提供）
            if "ideal_chain" not in data or not data["ideal_chain"]:
                auto_generated["ideal_chain"] = list(types.keys())
                warnings.append("未提供 ideal_chain，已自动从 types 顺序生成")

            # 10. 自动生成 prompt_addon
            if "prompt_addon" not in data or not data["prompt_addon"]:
                auto_generated["prompt_addon"] = self._auto_prompt_addon(data)
                warnings.append("未提供 prompt_addon，已自动生成基础模板")

            # 11. 检查循环范式配置
            cyclic = data.get("cyclic", False)
            if cyclic and not data.get("cycle_pattern"):
                warnings.append("cyclic=true 但未提供 cycle_pattern")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            auto_generated=auto_generated
        )

    def _validate_types(self, types: Dict) -> List[str]:
        """校验 types 配置"""
        errors = []
        if not isinstance(types, dict):
            return ["types 必须是字典"]

        count = len(types)
        if count < self.MIN_TYPES:
            errors.append(f"types 数量不足: {count} < 最少 {self.MIN_TYPES}")
        if count > self.MAX_TYPES:
            errors.append(f"types 数量过多: {count} > 最多 {self.MAX_TYPES}")

        for key, label in types.items():
            if not isinstance(key, str):
                errors.append(f"type key 必须是字符串: {key}")
            elif not self.TYPE_KEY_PATTERN.match(key):
                errors.append(f"type key '{key}' 格式非法，必须匹配 ^[a-z_]+$")
            if not isinstance(label, str) or not label.strip():
                errors.append(f"type '{key}' 的 label 不能为空")
            if len(label) > 50:
                errors.append(f"type '{key}' 的 label 过长: {len(label)} > 50")

        return errors

    def _validate_relations(self, relations: Dict) -> List[str]:
        """校验 relations 配置"""
        errors = []
        if not isinstance(relations, dict):
            return ["relations 必须是字典"]

        count = len(relations)
        if count < self.MIN_RELATIONS:
            errors.append(f"relations 数量不足: {count} < 最少 {self.MIN_RELATIONS}")
        if count > self.MAX_RELATIONS:
            errors.append(f"relations 数量过多: {count} > 最多 {self.MAX_RELATIONS}")

        for key, label in relations.items():
            if not isinstance(key, str):
                errors.append(f"relation key 必须是字符串: {key}")
            elif not self.RELATION_KEY_PATTERN.match(key):
                errors.append(f"relation key '{key}' 格式非法，必须匹配 ^[A-Z_]+$")
            if not isinstance(label, str) or not label.strip():
                errors.append(f"relation '{key}' 的 label 不能为空")
            if len(label) > 20:
                errors.append(f"relation '{key}' 的 label 过长: {len(label)} > 20")

        return errors

    def _validate_relation_map(self, relation_map: Dict, types: Dict, relations: Dict) -> List[str]:
        """校验 relation_map 合法性"""
        errors = []
        if not isinstance(relation_map, dict):
            return ["relation_map 必须是字典"]

        type_keys = set(types.keys())
        rel_keys = set(relations.keys())

        for source_type, rel_dict in relation_map.items():
            if source_type not in type_keys:
                errors.append(f"relation_map 中 source_type '{source_type}' 未在 types 中定义")
                continue

            if not isinstance(rel_dict, dict):
                errors.append(f"relation_map['{source_type}'] 必须是字典")
                continue

            for rel_type, target_types in rel_dict.items():
                if rel_type not in rel_keys:
                    errors.append(f"relation_map 中 relation '{rel_type}' 未在 relations 中定义")

                if not isinstance(target_types, list):
                    errors.append(f"relation_map['{source_type}']['{rel_type}'] 必须是列表")
                    continue

                for target in target_types:
                    if target not in type_keys:
                        errors.append(f"relation_map 中 target_type '{target}' 未在 types 中定义")

        return errors

    def _check_type_level_cycles(self, relation_map: Dict) -> List[str]:
        """检查 relation_map 在 type 层面是否形成环"""
        # 构建 type 级别的有向图
        adj = {}
        all_types = set()

        for source_type, rel_dict in relation_map.items():
            all_types.add(source_type)
            for rel_type, target_types in rel_dict.items():
                for target in target_types:
                    all_types.add(target)
                    adj.setdefault(source_type, set()).add(target)

        # 使用 DFS 找环
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {t: WHITE for t in all_types}
        path = []

        def dfs(node):
            color[node] = GRAY
            path.append(node)
            for neighbor in adj.get(node, set()):
                if color[neighbor] == GRAY:
                    # 找到环
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    return f"type-level 环 detected: {' -> '.join(cycle)}"
                if color[neighbor] == WHITE:
                    result = dfs(neighbor)
                    if result:
                        return result
            path.pop()
            color[node] = BLACK
            return None

        errors = []
        for t in all_types:
            if color[t] == WHITE:
                result = dfs(t)
                if result:
                    errors.append(result)
                    break  # 找到一个环即可

        return errors

    def _auto_parent_rules(self, relation_map: Dict, types: Dict) -> Dict:
        """从 relation_map 反向推导 parent_rules"""
        parent_rules = {t: [] for t in types.keys()}

        for source_type, rel_dict in relation_map.items():
            for rel_type, target_types in rel_dict.items():
                for target in target_types:
                    if source_type not in parent_rules[target]:
                        parent_rules[target].append(source_type)

        # 按 relation_map 中定义的顺序排序
        return parent_rules

    def _auto_styles(self, relations: Dict) -> Dict:
        """为每个 relation 分配默认样式"""
        styles = {}
        for i, rel_key in enumerate(relations.keys()):
            styles[rel_key] = {
                "color": self.DEFAULT_PALETTE[i % len(self.DEFAULT_PALETTE)],
                "lineStyle": "solid" if i % 2 == 0 else "dashed",
                "width": 2 if i % 2 == 0 else 1.5,
            }
        return styles

    def _auto_prompt_addon(self, data: Dict) -> str:
        """自动生成基础提示词模板"""
        paradigm_id = data.get("paradigm_id", "custom")
        name = data.get("name", "自定义范式")
        types = data.get("types", {})
        relations = data.get("relations", {})

        lines = [
            f"## {name}范式 — 概念类型判断标准（严格遵循）",
            "",
            f"本范式关注知识的内在逻辑结构。",
            "",
        ]

        for type_key, type_label in types.items():
            lines.append(f'**"{type_key}"**: {type_label}')
            lines.append(f"  - 判断标准：...")
            lines.append("")

        lines.append("## 关系类型判断标准")
        lines.append("")

        for rel_key, rel_label in relations.items():
            lines.append(f'**"{rel_key}"**: {rel_label}')
            lines.append(f"  - 语义：...")
            lines.append("")

        lines.append("## parent_hint 填写规则")
        lines.append("")
        lines.append("【理想连接】...")
        lines.append("")
        lines.append("【禁止行为】")
        lines.append("- 不要为了补全链条而编造不存在的概念")

        return "\n".join(lines)


# ========== 单元测试 ==========

def _test():
    """内部测试"""
    print("[ParadigmValidator] 运行测试...")

    # 测试1: 有效配置
    v = ParadigmValidator()
    result = v.validate({
        "paradigm_id": "test_valid",
        "name": "测试范式",
        "description": "用于测试",
        "types": {
            "type_a": "类型A",
            "type_b": "类型B",
        },
        "relations": {
            "REL_A": "关系A",
            "REL_B": "关系B",
        },
        "relation_map": {
            "type_a": {
                "REL_A": ["type_b"]
            }
        }
    })
    assert result.valid, f"有效配置应通过: {result.errors}"
    assert "parent_rules" in result.auto_generated
    assert "styles" in result.auto_generated
    print("  [PASS] 有效配置")

    # 测试2: paradigm_id 已存在
    v2 = ParadigmValidator({"test_valid": {}})
    result2 = v2.validate({
        "paradigm_id": "test_valid",
        "name": "重复",
        "description": "测试",
        "types": {"a": "A", "b": "B"},
        "relations": {"R1": "r1", "R2": "r2"},
        "relation_map": {}
    })
    assert not result2.valid
    assert any("已存在" in e for e in result2.errors)
    print("  [PASS] 重复ID检测")

    # 测试3: type-level 环
    result3 = v.validate({
        "paradigm_id": "test_cycle",
        "name": "环测试",
        "description": "测试环检测",
        "types": {"a": "A", "b": "B"},
        "relations": {"R1": "r1", "R2": "r2"},
        "relation_map": {
            "a": {"R1": ["b"]},
            "b": {"R2": ["a"]}  # 环!
        }
    })
    assert not result3.valid
    assert any("环" in e for e in result3.errors)
    print("  [PASS] 环检测")

    # 测试4: 字段缺失
    result4 = v.validate({"paradigm_id": "incomplete"})
    assert not result4.valid
    assert any("缺少必填字段" in e for e in result4.errors)
    print("  [PASS] 必填字段检测")

    # 测试5: types 数量不足
    result5 = v.validate({
        "paradigm_id": "too_few",
        "name": "太少",
        "description": "测试",
        "types": {"a": "A"},
        "relations": {"R1": "r1", "R2": "r2"},
        "relation_map": {}
    })
    assert not result5.valid
    print("  [PASS] types 数量检测")

    print("[ParadigmValidator] 所有测试通过!")


if __name__ == "__main__":
    _test()
