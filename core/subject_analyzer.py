#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学科自适应分析器 (SubjectAnalyzer)

通过分析用户上传的知识材料样本，自动推断学科特征并生成动态配置：
- 学科类型和领域
- 知识层级结构（从标题提取）
- 题型适配（基于材料中的题目格式检测）
- 难度分布（基于文本复杂度）
- 评分标准（基于材料类型推断）

使用方式:
    analyzer = SubjectAnalyzer()
    config = analyzer.analyze_materials(sample_chunks, subject_name="user_defined")
    # config 包含 question_types, difficulty_levels, knowledge_hierarchy, grading 等

设计原则:
- 以规则启发式为主（零 LLM 依赖）
- 可选 LLM 增强（接入后自动提升精度）
- 所有推断基于材料本身的统计特征，不预定义学科
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from config.settings import SUBJECT_CONFIG_DIR


class SubjectAnalyzer:
    """
    学科自适应分析器。

    分析材料样本，自动生成学科配置。分析过程无需预定义学科知识。
    """

    def __init__(self, use_llm: bool = False):
        self.use_llm = use_llm
        self._llm = None

    # 主分析入口：分析材料样本，生成学科配置
    def analyze_materials(self, chunks: List[Dict[str, Any]], subject_name: str = "auto") -> Dict[str, Any]:
        """
        分析知识材料样本，生成学科配置。

        Args:
            chunks: 分块后的材料样本（每个 chunk 包含 text 和 metadata）
            subject_name: 用户指定的学科名称（可选，默认 auto 由系统推断）

        Returns:
            {
                "subject": str,           # 学科标识
                "name": str,              # 学科显示名称
                "description": str,       # 描述
                "version": "1.0",
                "auto_generated": true,   # 标记为自动生成
                "analysis_basis": {       # 分析依据（透明可审计）
                    "sample_chunks": int,
                    "total_chars": int,
                    "formula_density": float,
                    "code_density": float,
                    "question_format_signals": dict,
                    "header_hierarchy": dict,
                },
                "question_types": {...},  # 检测到的题型
                "difficulty_levels": {...}, # 难度层级
                "knowledge_hierarchy": {...}, # 知识层级（从标题提取）
                "grading": {...},         # 评分标准推断
                "special_features": [...], # 特殊特征（公式、代码、图表等）
            }
        """
        # 合并所有 chunk 文本进行全局分析
        all_text = "\n".join(c.get("text", "") for c in chunks)
        total_chars = len(all_text)

        # 1. 提取标题层级结构（知识层级）
        header_hierarchy = self._extract_header_hierarchy(chunks)

        # 2. 检测题型信号
        question_signals = self._detect_question_formats(all_text)

        # 3. 检测特殊内容密度
        formula_density = self._detect_formula_density(all_text)
        code_density = self._detect_code_density(all_text)
        diagram_density = self._detect_diagram_references(all_text)

        # 4. 推断学科名称（如果未指定）
        inferred_name = subject_name if subject_name != "auto" else self._infer_subject_name(all_text, header_hierarchy)

        # 5. 生成题型配置（基于检测到的信号）
        question_types = self._generate_question_types(question_signals, formula_density, code_density, diagram_density)

        # 6. 生成难度层级（基于文本复杂度）
        difficulty_levels = self._generate_difficulty_levels(all_text)

        # 7. 生成评分标准
        grading = self._generate_grading_rules(question_types, formula_density, code_density)

        # 8. 检测特殊特征
        special_features = self._detect_special_features(formula_density, code_density, diagram_density, question_signals)

        # 9. 可选 LLM 增强分析
        if self.use_llm and self._check_llm():
            llm_enhanced = self._llm_enhance_analysis(all_text, {
                "question_types": question_types,
                "difficulty_levels": difficulty_levels,
                "knowledge_hierarchy": header_hierarchy,
                "grading": grading,
            })
            if llm_enhanced:
                question_types = llm_enhanced.get("question_types", question_types)
                difficulty_levels = llm_enhanced.get("difficulty_levels", difficulty_levels)
                knowledge_hierarchy = llm_enhanced.get("knowledge_hierarchy", header_hierarchy)
                grading = llm_enhanced.get("grading", grading)

        config = {
            "subject": self._slugify(inferred_name),
            "name": inferred_name,
            "description": f"基于 {len(chunks)} 个知识片段自动分析的学科配置",
            "version": "1.0",
            "auto_generated": True,
            "analysis_basis": {
                "sample_chunks": len(chunks),
                "total_chars": total_chars,
                "formula_density": round(formula_density, 4),
                "code_density": round(code_density, 4),
                "question_format_signals": {k: v for k, v in question_signals.items() if v > 0},
                "header_hierarchy": {k: len(v) for k, v in header_hierarchy.items()},
            },
            "question_types": question_types,
            "difficulty_levels": difficulty_levels,
            "knowledge_hierarchy": header_hierarchy,
            "grading": grading,
            "special_features": special_features,
        }

        return config

    # 保存配置到文件
    def save_config(self, config: Dict[str, Any], subject_name: Optional[str] = None) -> Path:
        """保存学科配置到 config/subjects/ 目录"""
        name = subject_name or config.get("subject", "auto")
        config_path = SUBJECT_CONFIG_DIR / f"{name}.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return config_path

    # 加载配置
    @staticmethod
    def load_config(subject_name: str) -> Optional[Dict[str, Any]]:
        """加载学科配置"""
        config_path = SUBJECT_CONFIG_DIR / f"{subject_name}.json"
        if not config_path.exists():
            return None
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    # 获取 generic 回退配置
    @staticmethod
    def get_generic_config() -> Dict[str, Any]:
        """获取通用回退配置"""
        generic_path = SUBJECT_CONFIG_DIR / "generic.json"
        if generic_path.exists():
            with open(generic_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        # 最小回退配置
        return {
            "subject": "generic",
            "name": "通用",
            "version": "1.0",
            "question_types": {
                "single_choice": {"name": "单选题", "description": "从多个选项中选择正确答案", "enabled": True},
                "short_answer": {"name": "简答题", "description": "简述概念或原理", "enabled": True},
            },
            "difficulty_levels": {
                "easy": {"name": "基础", "description": "入门概念"},
                "medium": {"name": "进阶", "description": "综合应用"},
                "hard": {"name": "高级", "description": "深度理解"},
            },
            "grading": {"default": {"method": "keyword_match", "description": "基于关键词匹配"}},
        }

    # ========== 分析子方法 ==========

    def _extract_header_hierarchy(self, chunks: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """从 chunk 元数据中提取标题层级结构"""
        # 收集所有标题路径
        headers_by_level = Counter()
        header_paths = []

        for chunk in chunks:
            meta = chunk.get("metadata", {})
            header_path = meta.get("header_path", "")
            level = meta.get("level", 0)
            if header_path:
                headers_by_level[level] += 1
                header_paths.append(header_path)

        # 按层级分组
        hierarchy = {}
        for level in sorted(headers_by_level.keys()):
            if level == 0:
                continue
            # 提取该层级的所有唯一标题
            level_headers = set()
            for path in header_paths:
                parts = [p.strip() for p in path.split(">") if p.strip()]
                if len(parts) >= level:
                    level_headers.add(parts[level - 1])
            if level_headers:
                hierarchy[f"level_{level}"] = sorted(level_headers)

        # 如果没有标题结构，尝试从文本中提取
        if not hierarchy:
            hierarchy = self._extract_structure_from_text(chunks)

        return hierarchy

    def _extract_structure_from_text(self, chunks: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """从文本内容中提取结构（无标题时的回退）"""
        # 提取前 5 个 chunk 的前 100 字符作为主题线索
        topics = []
        for chunk in chunks[:10]:
            text = chunk.get("text", "")[:200]
            # 找第一个有意义的句子
            sentences = re.split(r'[。！？\.\n]', text)
            for s in sentences:
                s = s.strip()
                if len(s) > 10 and len(s) < 100:
                    topics.append(s)
                    break

        return {"auto_topics": topics[:20]} if topics else {}

    def _detect_question_formats(self, text: str) -> Dict[str, int]:
        """检测材料中隐含的题目格式信号"""
        signals = {
            "single_choice": 0,      # A/B/C/D 选项
            "multiple_choice": 0,    # 多选标记
            "fill_blank": 0,         # 填空标记（____ 或 "填空"）
            "short_answer": 0,       # 简答/论述标记
            "essay": 0,              # 作文/大题标记
            "calculation": 0,        # 计算/求解标记
            "true_false": 0,         # 判断题标记
            "matching": 0,           # 连线/匹配题
        }

        # 单选题信号：A. B. C. D. 模式
        signals["single_choice"] += len(re.findall(r'[（\(][A-D][\)）]', text))
        signals["single_choice"] += len(re.findall(r'\n[A-D][\.．、]', text))

        # 多选题信号
        signals["multiple_choice"] += len(re.findall(r'多选|多项选择|不止一个|至少两个', text))

        # 填空题信号
        signals["fill_blank"] += text.count("____")
        signals["fill_blank"] += text.count("＿＿＿＿")
        signals["fill_blank"] += len(re.findall(r'填空|填写|补全|完成.*空白', text))

        # 简答题信号
        signals["short_answer"] += len(re.findall(r'简答|简述|说明|解释|阐述|分析.*原因', text))

        # 论述/作文题信号
        signals["essay"] += len(re.findall(r'论述|作文|大作文|写作|写一篇', text))

        # 计算题信号
        signals["calculation"] += len(re.findall(r'计算|求解|求.*值|证明|推导|列出.*公式', text))

        # 判断题信号
        signals["true_false"] += len(re.findall(r'判断|正确.*错误|对错|是.*非', text))

        # 匹配题信号
        signals["matching"] += len(re.findall(r'连线|匹配|对应|配对', text))

        return signals

    def _detect_formula_density(self, text: str) -> float:
        """检测公式密度（数学/化学/物理公式）"""
        formula_patterns = [
            r'[\u0370-\u03FF]',           # 希腊字母
            r'\$\$.*?\$\$',              # LaTeX 行间公式
            r'\$.*?\$',                 # LaTeX 行内公式
            r'[\^\_]\{.*?\}',           # 上下标
            r'\\(frac|sum|prod|int|sqrt|alpha|beta|gamma|delta|theta|lambda)',  # LaTeX 命令
            r'[\u2200-\u22FF]',         # 数学符号
            r'\d+\s*[\+\-\*/]\s*\d+',   # 简单算式
            r'[A-Z][a-z]?\d*\s*([\+\-])\s*\d*\s*([A-Z][a-z]?\d*)+\s*(->|→|=)',  # 化学方程式
            r'C\d*H\d*O\d*N\d*',        # 化学分子式
        ]
        total_matches = 0
        for pattern in formula_patterns:
            total_matches += len(re.findall(pattern, text))
        return total_matches / max(len(text), 1) * 1000  # 每千字公式数

    def _detect_code_density(self, text: str) -> float:
        """检测代码密度"""
        code_indicators = [
            r'import\s+\w+',
            r'def\s+\w+\s*\(',
            r'class\s+\w+',
            r'function\s+\w+',
            r'const\s+\w+\s*=',
            r'let\s+\w+\s*=',
            r'var\s+\w+\s*=',
            r'if\s*\(',
            r'for\s*\(',
            r'while\s*\(',
            r'return\s+',
            r'console\.(log|warn|error)',
            r'print\s*\(',
            r'#>\s*\w+',  # R
            r'```\w*',   # Markdown 代码块
        ]
        total_matches = 0
        for pattern in code_indicators:
            total_matches += len(re.findall(pattern, text))
        return total_matches / max(len(text), 1) * 1000

    def _detect_diagram_references(self, text: str) -> float:
        """检测图表引用密度"""
        diagram_patterns = [
            r'图\s*\d+',
            r'Figure\s*\d+',
            r'Fig\.\s*\d+',
            r'表\s*\d+',
            r'Table\s*\d+',
            r'图表|插图|示意图|流程图|架构图|思维导图',
            r'如下.*所示|如图|见.*图',
        ]
        total_matches = 0
        for pattern in diagram_patterns:
            total_matches += len(re.findall(pattern, text, re.IGNORECASE))
        return total_matches / max(len(text), 1) * 1000

    def _infer_subject_name(self, text: str, header_hierarchy: Dict) -> str:
        """基于内容推断学科名称"""
        # 从标题层级提取关键词
        all_headers = []
        for headers in header_hierarchy.values():
            if isinstance(headers, list):
                all_headers.extend(headers)

        # 关键词映射（启发式，不预定义完整列表）
        keyword_subject_map = {
            # 化学
            ("化学", "元素", "原子", "分子", "反应", "方程式", "化学键", "离子", "化合物", "有机", "无机"): "化学",
            # 物理
            ("物理", "力学", "电磁", "光学", "热学", "量子", "相对论", "牛顿", "能量", "动量"): "物理",
            # 数学
            ("数学", "代数", "几何", "微积分", "概率", "统计", "线性代数", "拓扑", "数论"): "数学",
            # 生物
            ("生物", "细胞", "基因", "DNA", "蛋白质", "进化", "生态", "遗传", "代谢"): "生物",
            # 计算机/编程
            ("编程", "算法", "数据结构", "网络", "数据库", "操作系统", "机器学习", "AI", "深度学习", "Python", "Java"): "计算机科学",
            # 语言/文学
            ("语文", "文学", "诗词", "古文", "阅读", "写作", "语法", "修辞"): "语文",
            # 英语
            ("英语", "English", "grammar", "vocabulary", "reading", "listening"): "英语",
            # 历史
            ("历史", "朝代", "战争", "革命", "文明", "古代", "近代"): "历史",
            # 地理
            ("地理", "地形", "气候", "地图", "经纬度", "板块", "洋流"): "地理",
            # 政治/考公
            ("政治", "申论", "行测", "公务员", "政策", "时政", "马克思主义", "法律"): "政治/公务员考试",
            # 经济
            ("经济", "金融", "市场", "供给", "需求", "GDP", "通货膨胀", "微观经济", "宏观经济"): "经济学",
            # 医学
            ("医学", "解剖", "病理", "药理", "诊断", "治疗", "临床", "生理"): "医学",
        }

        # 统计关键词出现
        text_lower = text.lower()
        header_text = " ".join(str(h).lower() for h in all_headers)
        combined = text_lower + " " + header_text

        subject_scores = Counter()
        for keywords, subject in keyword_subject_map.items():
            score = sum(1 for kw in keywords if kw.lower() in combined)
            if score > 0:
                subject_scores[subject] += score

        if subject_scores:
            return subject_scores.most_common(1)[0][0]

        # 无法推断，返回通用名称
        return "自定义学科"

    def _generate_question_types(self, signals: Dict[str, int], formula_density: float,
                                  code_density: float, diagram_density: float) -> Dict[str, Any]:
        """基于检测信号生成题型配置"""
        question_types = {}

        # 阈值：信号出现次数 > 0 即启用该题型
        threshold = 0

        if signals.get("single_choice", 0) > threshold:
            question_types["single_choice"] = {
                "name": "单选题",
                "description": "从多个选项中选择正确答案",
                "enabled": True,
                "detected_signals": signals["single_choice"],
            }

        if signals.get("multiple_choice", 0) > threshold:
            question_types["multiple_choice"] = {
                "name": "多选题",
                "description": "从多个选项中选择所有正确答案",
                "enabled": True,
                "detected_signals": signals["multiple_choice"],
            }

        if signals.get("fill_blank", 0) > threshold:
            question_types["fill_blank"] = {
                "name": "填空题",
                "description": "填写空白处的正确答案",
                "enabled": True,
                "detected_signals": signals["fill_blank"],
            }

        if signals.get("true_false", 0) > threshold:
            question_types["true_false"] = {
                "name": "判断题",
                "description": "判断陈述是否正确",
                "enabled": True,
                "detected_signals": signals["true_false"],
            }

        if signals.get("short_answer", 0) > threshold:
            question_types["short_answer"] = {
                "name": "简答题",
                "description": "简述概念或原理",
                "enabled": True,
                "detected_signals": signals["short_answer"],
            }

        if signals.get("essay", 0) > threshold:
            question_types["essay"] = {
                "name": "论述题/作文",
                "description": "展开论述或写作",
                "enabled": True,
                "detected_signals": signals["essay"],
            }

        if signals.get("calculation", 0) > threshold or formula_density > 1.0:
            question_types["calculation"] = {
                "name": "计算/推导题",
                "description": "进行计算、推导或证明",
                "enabled": True,
                "detected_signals": signals.get("calculation", 0),
                "formula_density": round(formula_density, 2),
            }

        # 代码相关题型
        if code_density > 1.0:
            question_types["coding"] = {
                "name": "编程题",
                "description": "编写或分析代码",
                "enabled": True,
                "code_density": round(code_density, 2),
            }

        # 如果没有检测到任何题型，默认启用单选和简答
        if not question_types:
            question_types["single_choice"] = {
                "name": "单选题", "description": "从多个选项中选择正确答案", "enabled": True,
            }
            question_types["short_answer"] = {
                "name": "简答题", "description": "简述概念或原理", "enabled": True,
            }

        return question_types

    def _generate_difficulty_levels(self, text: str) -> Dict[str, Any]:
        """基于文本复杂度生成难度层级"""
        # 简单启发式：术语密度、句子长度、公式密度
        sentences = re.split(r'[。！？\.\n]', text)
        avg_sentence_len = sum(len(s) for s in sentences) / max(len(sentences), 1)

        # 术语密度（大写字母缩写、专业术语）
        term_count = len(re.findall(r'[A-Z]{2,}', text)) + len(re.findall(r'[\u4e00-\u9fff]{4,8}', text))
        term_density = term_count / max(len(text), 1) * 1000

        return {
            "easy": {
                "name": "基础",
                "description": f"入门概念，平均句长 {avg_sentence_len:.0f} 字符，术语密度低",
            },
            "medium": {
                "name": "进阶",
                "description": f"综合应用，术语密度 {term_density:.1f}/千字",
            },
            "hard": {
                "name": "高级",
                "description": "深度理解，多知识点交叉，复杂推导",
            },
        }

    def _generate_grading_rules(self, question_types: Dict, formula_density: float, code_density: float) -> Dict[str, Any]:
        """基于题型和材料特征生成评分标准"""
        grading = {}

        if "single_choice" in question_types or "multiple_choice" in question_types:
            grading["choice"] = {
                "method": "exact_match",
                "description": "选择题：选项完全匹配即满分",
            }

        if "fill_blank" in question_types:
            grading["fill_blank"] = {
                "method": "keyword_match",
                "description": "填空题：关键词匹配评分，同义词可接受",
            }

        if "short_answer" in question_types:
            grading["short_answer"] = {
                "method": "keyword_match",
                "description": "简答题：基于关键词覆盖度和准确性评分",
            }

        if "essay" in question_types:
            grading["essay"] = {
                "method": "rubric_based",
                "description": "论述题：基于评分表的多维度评分（立意、结构、论证、表达）",
            }

        if "calculation" in question_types or formula_density > 1.0:
            grading["calculation"] = {
                "method": "formula_equivalence",
                "description": "计算/推导题：结果正确且步骤合理即可得分，等价形式接受",
            }

        if "coding" in question_types or code_density > 1.0:
            grading["coding"] = {
                "method": "code_execution",
                "description": "编程题：代码可运行且通过测试用例",
            }

        if not grading:
            grading["default"] = {
                "method": "keyword_match",
                "description": "基于关键词匹配评分",
            }

        return grading

    def _detect_special_features(self, formula_density: float, code_density: float,
                                  diagram_density: float, question_signals: Dict[str, int]) -> List[str]:
        """检测材料的特殊特征"""
        features = []
        if formula_density > 1.0:
            features.append("formula_heavy")
        if code_density > 1.0:
            features.append("code_heavy")
        if diagram_density > 1.0:
            features.append("diagram_references")
        if any(signals > 0 for signals in question_signals.values()):
            features.append("contains_question_formats")
        return features

    def _check_llm(self) -> bool:
        """检查 LLM 是否可用"""
        if not self.use_llm:
            return False
        if self._llm is not None:
            return True
        try:
            from core.llm_client import LLMClient
            self._llm = LLMClient()
            return True
        except Exception:
            return False

    def _llm_enhance_analysis(self, text: str, current_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """使用 LLM 增强分析（可选）"""
        if not self._llm:
            return None
        # 截取样本文本（前 3000 字符）
        sample = text[:3000]
        prompt = f"""你是一位教育内容分析专家。请基于以下知识材料样本，分析并输出 JSON 格式的学科配置建议。

材料样本：
{sample}

当前分析结果：
{json.dumps(current_config, ensure_ascii=False, indent=2)[:1000]}

请输出 JSON：
{{
  "question_types": {{...}},
  "difficulty_levels": {{...}},
  "knowledge_hierarchy": {{...}},
  "grading": {{...}}
}}

只需输出 JSON，不要解释。"""
        try:
            response = self._llm.chat([{"role": "user", "content": prompt}], temperature=0.1, max_tokens=1000)
            # 尝试提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass
        return None

    @staticmethod
    def _slugify(name: str) -> str:
        """将名称转换为标识符"""
        return re.sub(r'[^\w\-]', '_', name.lower())[:50]


# 便捷函数
def analyze_subject(chunks: List[Dict[str, Any]], subject_name: str = "auto") -> Dict[str, Any]:
    """便捷函数：分析学科"""
    analyzer = SubjectAnalyzer()
    return analyzer.analyze_materials(chunks, subject_name)


def save_subject_config(config: Dict[str, Any], subject_name: Optional[str] = None) -> Path:
    """便捷函数：保存学科配置"""
    analyzer = SubjectAnalyzer()
    return analyzer.save_config(config, subject_name)
