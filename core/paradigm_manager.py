#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ParadigmManager — 范式管理服务

职责：
- 范式配置的 CRUD
- 文件持久化（paradigms.yaml）
- 内存缓存热刷新
- 文件锁（防止并发修改）
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml

from core.paradigm_validator import ParadigmValidator, ValidationResult


# 范式 YAML 文件路径
PARADIGMS_YAML_PATH = Path(__file__).parent.parent / "config" / "paradigms.yaml"


class ParadigmManager:
    """范式管理服务"""

    # 内置范式 ID 列表（不可修改/删除）
    BUILTIN_PARADIGMS = {"theory", "engineering", "hierarchical"}

    def __init__(self, yaml_path: Optional[Path] = None):
        self.yaml_path = yaml_path or PARADIGMS_YAML_PATH
        self._cache: Optional[Dict] = None
        self._load_yaml()

    def _load_yaml(self) -> Dict:
        """加载 paradigms.yaml 到内存缓存"""
        if self.yaml_path.exists():
            with open(self.yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._cache = data
            return data
        self._cache = {"paradigms": {}}
        return self._cache

    def _save_yaml(self) -> None:
        """保存内存缓存到 paradigms.yaml"""
        # 备份
        self._backup_yaml()
        # 写入
        with open(self.yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(self._cache, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    def _backup_yaml(self) -> None:
        """创建备份文件"""
        if self.yaml_path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.yaml_path.parent / f"paradigms.yaml.bak.{ts}"
            shutil.copy2(self.yaml_path, backup_path)

    def list_paradigms(self) -> List[Dict]:
        """
        获取所有范式列表（简要信息）
        
        Returns:
            [{paradigm_id, name, description, icon, is_builtin}, ...]
        """
        paradigms = self._cache.get("paradigms", {})
        result = []
        for pid, config in paradigms.items():
            result.append({
                "paradigm_id": pid,
                "name": config.get("name", pid),
                "description": config.get("description", ""),
                "icon": config.get("icon", ""),
                "is_builtin": pid in self.BUILTIN_PARADIGMS,
            })
        return result

    def get_paradigm(self, paradigm_id: str) -> Optional[Dict]:
        """
        获取单个范式完整配置
        
        Args:
            paradigm_id: 范式 ID
            
        Returns:
            完整配置字典，或 None（不存在）
        """
        paradigms = self._cache.get("paradigms", {})
        config = paradigms.get(paradigm_id)
        if config:
            # 补充 is_builtin 标记
            config = dict(config)
            config["is_builtin"] = paradigm_id in self.BUILTIN_PARADIGMS
        return config

    def create_paradigm(self, data: Dict) -> Dict[str, Any]:
        """
        创建新范式
        
        Args:
            data: 前端提交的范式配置（最小必填集）
            
        Returns:
            {
                "success": bool,
                "paradigm_id": str,
                "warnings": [str],
                "auto_generated": {parent_rules, styles, ideal_chain, prompt_addon}
            }
        """
        # 1. 校验
        existing = self._cache.get("paradigms", {})
        validator = ParadigmValidator(existing)
        result = validator.validate(data)

        if not result.valid:
            return {
                "success": False,
                "errors": result.errors,
                "warnings": result.warnings,
            }

        # 2. 组装完整配置
        paradigm_id = data["paradigm_id"]
        full_config = {
            "name": data["name"],
            "description": data.get("description", ""),
            "icon": data.get("icon", ""),
            "color": data.get("color", "#3498db"),
            "types": data["types"],
            "relations": data["relations"],
            "relation_map": data["relation_map"],
            "parent_rules": result.auto_generated.get("parent_rules", {}),
            "ideal_chain": data.get("ideal_chain") or result.auto_generated.get("ideal_chain", list(data["types"].keys())),
            "cyclic": data.get("cyclic", False),
            "cycle_pattern": data.get("cycle_pattern", []),
            "fallback": data.get("fallback", {
                "allow_skip_levels": True,
                "mark_as_gap": True,
                "create_virtual_nodes": False,
            }),
            "gap_rules": data.get("gap_rules", {
                "detect_by_type_mismatch": True,
                "detect_by_same_type": False,
            }),
            "styles": data.get("styles") or result.auto_generated.get("styles", {}),
            "prompt_addon": data.get("prompt_addon") or result.auto_generated.get("prompt_addon", ""),
        }

        # 3. 持久化
        paradigms = self._cache.setdefault("paradigms", {})
        paradigms[paradigm_id] = full_config
        self._save_yaml()

        return {
            "success": True,
            "paradigm_id": paradigm_id,
            "warnings": result.warnings,
            "auto_generated": result.auto_generated,
        }

    def update_paradigm(self, paradigm_id: str, data: Dict) -> Dict[str, Any]:
        """
        修改自定义范式（内置范式不允许修改）
        
        Args:
            paradigm_id: 范式 ID
            data: 更新数据
            
        Returns:
            {"success": bool, "errors": [str]}
        """
        if paradigm_id in self.BUILTIN_PARADIGMS:
            return {"success": False, "errors": [f"内置范式 '{paradigm_id}' 不允许修改"]}

        if paradigm_id not in self._cache.get("paradigms", {}):
            return {"success": False, "errors": [f"范式 '{paradigm_id}' 不存在"]}

        # TODO: 实现更新逻辑（合并更新）
        return {"success": False, "errors": ["更新功能暂未实现"]}

    def delete_paradigm(self, paradigm_id: str) -> Dict[str, Any]:
        """
        删除自定义范式（内置范式不允许删除）
        
        Args:
            paradigm_id: 范式 ID
            
        Returns:
            {"success": bool, "errors": [str]}
        """
        if paradigm_id in self.BUILTIN_PARADIGMS:
            return {"success": False, "errors": [f"内置范式 '{paradigm_id}' 不允许删除"]}

        paradigms = self._cache.get("paradigms", {})
        if paradigm_id not in paradigms:
            return {"success": False, "errors": [f"范式 '{paradigm_id}' 不存在"]}

        del paradigms[paradigm_id]
        self._save_yaml()
        return {"success": True}

    def reload(self) -> None:
        """强制重新加载 YAML（用于外部修改后）"""
        self._load_yaml()


# ========== 便捷函数（供后端 API 使用）==========

_manager_instance: Optional[ParadigmManager] = None


def get_paradigm_manager() -> ParadigmManager:
    """获取全局 ParadigmManager 单例"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ParadigmManager()
    return _manager_instance
