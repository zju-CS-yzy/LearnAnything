"""
ParadigmLoader: 从 YAML 配置文件加载范式定义

替代 semantic_extractor.py 中硬编码的 PARADIGMS 字典。
"""
import yaml
from pathlib import Path
from typing import Dict, Any, List
from config.settings import BASE_DIR

class ParadigmLoader:
    """
    范式配置加载器。
    
    从 YAML 文件加载范式定义，提供类型、关系、提示词等配置。
    """
    
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self):
        """从 YAML 文件加载配置。"""
        config_path = BASE_DIR / "config" / "paradigms.yaml"
        
        if not config_path.exists():
            raise FileNotFoundError(f"Paradigm config not found: {config_path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f)
    
    def get_paradigm(self, paradigm: str) -> Dict[str, Any]:
        """
        获取指定范式的配置。
        
        Args:
            paradigm: 范式名称（theory/engineering/hierarchical）
            
        Returns:
            范式配置字典，包含 name, description, types, relations, prompt_addon
        """
        if paradigm not in self._config["paradigms"]:
            raise ValueError(f"Unknown paradigm: {paradigm}. Available: {list(self._config['paradigms'].keys())}")
        
        return self._config["paradigms"][paradigm]
    
    def get_all_paradigms(self) -> Dict[str, Dict[str, Any]]:
        """获取所有范式配置。"""
        return self._config["paradigms"]
    
    def get_types(self, paradigm: str) -> Dict[str, str]:
        """获取指定范式的概念类型。"""
        return self.get_paradigm(paradigm)["types"]
    
    def get_relations(self, paradigm: str) -> Dict[str, str]:
        """获取指定范式的关系类型。"""
        return self.get_paradigm(paradigm)["relations"]
    
    def get_prompt_addon(self, paradigm: str) -> str:
        """获取指定范式的提示词附加内容。"""
        return self.get_paradigm(paradigm)["prompt_addon"]
    
    def get_type_list(self, paradigm: str) -> List[str]:
        """获取概念类型列表（用于验证）。"""
        return list(self.get_types(paradigm).keys())
    
    def get_relation_list(self, paradigm: str) -> List[str]:
        """获取关系类型列表（用于验证）。"""
        return list(self.get_relations(paradigm).keys())
    
    def get_default_paradigm(self) -> str:
        """获取默认范式。"""
        return self._config.get("default_paradigm", "theory")
    
    def get_paradigm_metadata(self, paradigm: str) -> Dict[str, Any]:
        """获取范式元数据（图标、颜色等）。"""
        return self._config.get("paradigm_metadata", {}).get(paradigm, {})


# 全局单例
_paradigm_loader = None

def get_paradigm_loader() -> ParadigmLoader:
    """获取范式加载器单例。"""
    global _paradigm_loader
    if _paradigm_loader is None:
        _paradigm_loader = ParadigmLoader()
    return _paradigm_loader
