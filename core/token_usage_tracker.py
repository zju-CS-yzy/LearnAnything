#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token 用量追踪器 (LLM-ROBUST-11)

轻量级本地 SQLite 存储，记录每次 LLM 调用的 token 用量。
支持成本估算、预算告警、按维度统计。

使用方式:
    from core.token_usage_tracker import TokenUsageTracker
    tracker = TokenUsageTracker()
    tracker.log_usage(model="deepseek-v4", prompt_tokens=1000, completion_tokens=500)
    stats = tracker.get_monthly_stats()
"""

import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.settings import DATA_ROOT


# ========== 成本模型（每 1K tokens 的价格，单位：元）==========
# 价格来源：各平台官方定价（2026-08），仅用于估算
COST_PER_1K_TOKENS = {
    # DeepSeek
    "deepseek-v4-pro": {"prompt": 0.002, "completion": 0.008},
    "deepseek-v4-flash": {"prompt": 0.0005, "completion": 0.002},
    "deepseek-chat": {"prompt": 0.001, "completion": 0.002},
    "deepseek-reasoner": {"prompt": 0.001, "completion": 0.004},
    # Kimi
    "kimi-k2.5": {"prompt": 0.002, "completion": 0.006},
    "kimi-k2.6": {"prompt": 0.003, "completion": 0.012},
    "kimi-k2": {"prompt": 0.001, "completion": 0.003},
    "kimi-k2.5-reasoning": {"prompt": 0.002, "completion": 0.008},
    # OpenAI
    "gpt-4o": {"prompt": 0.035, "completion": 0.105},
    "gpt-4o-mini": {"prompt": 0.0015, "completion": 0.006},
    # SiliconFlow (代理价)
    "deepseek-ai/DeepSeek-V3": {"prompt": 0.001, "completion": 0.002},
    "deepseek-ai/DeepSeek-R1": {"prompt": 0.001, "completion": 0.004},
}

# 默认价格（未知模型时使用）
DEFAULT_COST = {"prompt": 0.002, "completion": 0.008}


@dataclass
class UsageRecord:
    """单次用量记录"""
    id: int
    timestamp: str
    model: str
    provider: str
    feature: str  # 'llm', 'vlm', 'embedding' 等
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    request_type: str  # 'chat', 'stream', 'json', 'embedding'
    status: str  # 'success', 'fallback', 'error'
    latency_ms: int
    estimated_cost: float  # 元


@dataclass 
class UsageStats:
    """用量统计聚合"""
    total_requests: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost: float
    avg_latency_ms: float
    fallback_count: int
    error_count: int


class TokenUsageTracker:
    """
    Token 用量追踪器。
    
    线程安全，使用 SQLite 本地存储，支持：
    - 自动记录每次 LLM 调用用量
    - 按时间/模型/功能维度统计
    - 月度预算告警
    - 成本估算
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        Args:
            db_path: 数据库路径，默认 DATA_ROOT/monitor/token_usage.db
        """
        if db_path is None:
            db_path = DATA_ROOT / "monitor" / "token_usage.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 线程锁（SQLite 单写）
        self._lock = threading.Lock()
        
        # 预算配置（可从配置文件读取）
        self._monthly_budget: float = 0.0  # 0 = 无预算限制
        self._budget_warning_threshold: float = 0.8  # 80% 时告警
        
        # 初始化数据库
        self._init_db()
    
    # ========== 数据库操作 ==========
    
    def _init_db(self):
        """初始化数据库表结构"""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS token_usage_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        model TEXT NOT NULL,
                        provider TEXT,
                        feature TEXT NOT NULL DEFAULT 'llm',
                        prompt_tokens INTEGER NOT NULL DEFAULT 0,
                        completion_tokens INTEGER NOT NULL DEFAULT 0,
                        total_tokens INTEGER NOT NULL DEFAULT 0,
                        request_type TEXT NOT NULL DEFAULT 'chat',
                        status TEXT NOT NULL DEFAULT 'success',
                        latency_ms INTEGER DEFAULT 0,
                        estimated_cost REAL DEFAULT 0.0,
                        metadata TEXT  -- JSON 扩展字段
                    )
                """)
                
                # 索引：加速查询
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_usage_time 
                    ON token_usage_logs(timestamp)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_usage_model 
                    ON token_usage_logs(model)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_usage_feature 
                    ON token_usage_logs(feature)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_usage_status 
                    ON token_usage_logs(status)
                """)
                
                # 预算配置表
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS budget_config (
                        id INTEGER PRIMARY KEY,
                        monthly_budget REAL DEFAULT 0.0,
                        warning_threshold REAL DEFAULT 0.8,
                        updated_at TEXT
                    )
                """)
                
                # 插入默认预算配置（如果不存在）
                conn.execute("""
                    INSERT OR IGNORE INTO budget_config (id, monthly_budget, warning_threshold, updated_at)
                    VALUES (1, 0.0, 0.8, ?)
                """, (datetime.now().isoformat(),))
                
                conn.commit()
            finally:
                conn.close()
    
    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return sqlite3.connect(str(self.db_path))
    
    # ========== 核心 API：记录用量 ==========
    
    def log_usage(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        provider: str = "",
        feature: str = "llm",
        request_type: str = "chat",
        status: str = "success",
        latency_ms: int = 0,
        metadata: Optional[Dict] = None,
    ) -> Tuple[int, float, Optional[str]]:
        """
        记录一次 LLM 调用用量。
        
        Args:
            model: 模型名称
            prompt_tokens: 输入 token 数
            completion_tokens: 输出 token 数
            provider: 提供商
            feature: 功能类型 ('llm', 'vlm', 'embedding')
            request_type: 请求类型 ('chat', 'stream', 'json', 'embedding')
            status: 状态 ('success', 'fallback', 'error')
            latency_ms: 请求耗时（毫秒）
            metadata: 额外元数据字典
        
        Returns:
            (record_id, estimated_cost, warning_message)
            - record_id: 记录 ID
            - estimated_cost: 估算成本（元）
            - warning_message: 预算告警消息（未触发则为 None）
        """
        total_tokens = prompt_tokens + completion_tokens
        
        # 计算成本
        cost = self._estimate_cost(model, prompt_tokens, completion_tokens)
        
        # 构建记录
        timestamp = datetime.now().isoformat()
        meta_str = ""
        if metadata:
            import json
            meta_str = json.dumps(metadata, ensure_ascii=False)
        
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO token_usage_logs 
                    (timestamp, model, provider, feature, prompt_tokens, completion_tokens, 
                     total_tokens, request_type, status, latency_ms, estimated_cost, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (timestamp, model, provider, feature, prompt_tokens, completion_tokens,
                     total_tokens, request_type, status, latency_ms, cost, meta_str)
                )
                conn.commit()
                record_id = cursor.lastrowid
            finally:
                conn.close()
        
        # 检查预算告警
        warning = self._check_budget_warning()
        
        return record_id, cost, warning
    
    def log_from_response(
        self,
        model: str,
        response_data: Dict,
        provider: str = "",
        feature: str = "llm",
        request_type: str = "chat",
        latency_ms: int = 0,
    ) -> Tuple[int, float, Optional[str]]:
        """
        从 API 响应数据中自动提取 usage 并记录。
        
        Args:
            response_data: LLM API 返回的 JSON 数据（包含 usage 字段）
            ...其他参数同 log_usage
        
        Returns:
            同 log_usage
        """
        usage = response_data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        
        # 如果 usage 中没有，尝试估算
        if prompt_tokens == 0 and completion_tokens == 0:
            # 从 content 估算（粗略）
            content = ""
            choices = response_data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content", "") or msg.get("reasoning_content", "")
            # 粗略估算：中文约 1.5 tokens/字，英文约 0.25 tokens/char
            prompt_tokens = len(content)  # 简化估算
            completion_tokens = len(content)
        
        return self.log_usage(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            provider=provider,
            feature=feature,
            request_type=request_type,
            latency_ms=latency_ms,
        )
    
    # ========== 成本估算 ==========
    
    def _estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """估算调用成本（元）"""
        cost_cfg = COST_PER_1K_TOKENS.get(model, DEFAULT_COST)
        prompt_cost = (prompt_tokens / 1000) * cost_cfg["prompt"]
        completion_cost = (completion_tokens / 1000) * cost_cfg["completion"]
        return round(prompt_cost + completion_cost, 6)
    
    @classmethod
    def set_model_cost(cls, model: str, prompt_cost: float, completion_cost: float):
        """
        设置/更新模型的成本价格。
        
        Args:
            model: 模型名称
            prompt_cost: 每 1K prompt tokens 价格（元）
            completion_cost: 每 1K completion tokens 价格（元）
        """
        COST_PER_1K_TOKENS[model] = {
            "prompt": prompt_cost,
            "completion": completion_cost,
        }
    
    # ========== 预算管理 ==========
    
    def set_budget(self, monthly_budget: float, warning_threshold: float = 0.8):
        """
        设置月度预算。
        
        Args:
            monthly_budget: 月度预算上限（元），0 表示无限制
            warning_threshold: 告警阈值（0~1），默认 0.8
        """
        self._monthly_budget = monthly_budget
        self._budget_warning_threshold = warning_threshold
        
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    UPDATE budget_config 
                    SET monthly_budget=?, warning_threshold=?, updated_at=?
                    WHERE id=1
                    """,
                    (monthly_budget, warning_threshold, datetime.now().isoformat())
                )
                conn.commit()
            finally:
                conn.close()
    
    def get_budget(self) -> Dict[str, float]:
        """获取当前预算配置"""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT monthly_budget, warning_threshold FROM budget_config WHERE id=1"
                ).fetchone()
                if row:
                    return {
                        "monthly_budget": row[0],
                        "warning_threshold": row[1],
                    }
                return {"monthly_budget": 0.0, "warning_threshold": 0.8}
            finally:
                conn.close()
    
    def _check_budget_warning(self) -> Optional[str]:
        """检查是否触发预算告警，返回告警消息或 None"""
        if self._monthly_budget <= 0:
            return None
        
        # 获取本月已用成本
        monthly_cost = self.get_monthly_stats().total_cost
        
        ratio = monthly_cost / self._monthly_budget
        if ratio >= 1.0:
            return f"⚠️ 月度预算已超支！已用 {monthly_cost:.2f}/{self._monthly_budget:.2f} 元"
        elif ratio >= self._budget_warning_threshold:
            return f"⚠️ 月度预算即将耗尽！已用 {monthly_cost:.2f}/{self._monthly_budget:.2f} 元 ({ratio*100:.0f}%)"
        return None
    
    # ========== 统计查询 ==========
    
    def get_monthly_stats(self, year_month: Optional[str] = None) -> UsageStats:
        """
        获取月度统计。
        
        Args:
            year_month: 年月字符串（如 '2026-08'），None 表示当前月
        """
        if year_month is None:
            year_month = datetime.now().strftime("%Y-%m")
        
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    """
                    SELECT 
                        COUNT(*),
                        COALESCE(SUM(prompt_tokens), 0),
                        COALESCE(SUM(completion_tokens), 0),
                        COALESCE(SUM(total_tokens), 0),
                        COALESCE(SUM(estimated_cost), 0),
                        COALESCE(AVG(latency_ms), 0),
                        COALESCE(SUM(CASE WHEN status='fallback' THEN 1 ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN status='error' THEN 1 ELSE 0 END), 0)
                    FROM token_usage_logs
                    WHERE timestamp LIKE ?
                    """,
                    (f"{year_month}%",)
                ).fetchone()
                
                return UsageStats(
                    total_requests=row[0],
                    total_prompt_tokens=row[1],
                    total_completion_tokens=row[2],
                    total_tokens=row[3],
                    total_cost=round(row[4], 4),
                    avg_latency_ms=round(row[5], 2),
                    fallback_count=row[6],
                    error_count=row[7],
                )
            finally:
                conn.close()
    
    def get_daily_stats(self, days: int = 7) -> List[Dict]:
        """
        获取最近 N 天的每日统计。
        
        Returns:
            每日统计列表，每项包含 date, requests, tokens, cost
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    """
                    SELECT 
                        substr(timestamp, 1, 10) as date,
                        COUNT(*) as requests,
                        COALESCE(SUM(total_tokens), 0) as tokens,
                        COALESCE(SUM(estimated_cost), 0) as cost
                    FROM token_usage_logs
                    WHERE timestamp >= ?
                    GROUP BY date
                    ORDER BY date DESC
                    """,
                    (start_date.isoformat(),)
                )
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        "date": row[0],
                        "requests": row[1],
                        "tokens": row[2],
                        "cost": round(row[3], 4),
                    })
                return results
            finally:
                conn.close()
    
    def get_model_stats(self, days: int = 30) -> List[Dict]:
        """
        按模型分组统计（最近 N 天）。
        
        Returns:
            模型统计列表，每项包含 model, requests, tokens, cost
        """
        start_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    """
                    SELECT 
                        model,
                        COUNT(*) as requests,
                        COALESCE(SUM(total_tokens), 0) as tokens,
                        COALESCE(SUM(estimated_cost), 0) as cost
                    FROM token_usage_logs
                    WHERE timestamp >= ?
                    GROUP BY model
                    ORDER BY cost DESC
                    """,
                    (start_date,)
                )
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        "model": row[0],
                        "requests": row[1],
                        "tokens": row[2],
                        "cost": round(row[3], 4),
                    })
                return results
            finally:
                conn.close()
    
    def get_recent_logs(self, limit: int = 50) -> List[UsageRecord]:
        """获取最近的用量记录"""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    """
                    SELECT id, timestamp, model, provider, feature, prompt_tokens,
                           completion_tokens, total_tokens, request_type, status,
                           latency_ms, estimated_cost
                    FROM token_usage_logs
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit,)
                )
                
                records = []
                for row in cursor.fetchall():
                    records.append(UsageRecord(
                        id=row[0], timestamp=row[1], model=row[2], provider=row[3],
                        feature=row[4], prompt_tokens=row[5], completion_tokens=row[6],
                        total_tokens=row[7], request_type=row[8], status=row[9],
                        latency_ms=row[10], estimated_cost=row[11],
                    ))
                return records
            finally:
                conn.close()
    
    # ========== 数据维护 ==========
    
    def cleanup_old_logs(self, retention_days: int = 90):
        """清理超过保留期的旧记录"""
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "DELETE FROM token_usage_logs WHERE timestamp < ?",
                    (cutoff,)
                )
                conn.commit()
                deleted = cursor.rowcount
                print(f"[TokenUsage] 清理了 {deleted} 条超过 {retention_days} 天的旧记录")
                return deleted
            finally:
                conn.close()
    
    def export_to_csv(self, filepath: str, start_date: Optional[str] = None, end_date: Optional[str] = None):
        """导出记录到 CSV"""
        import csv
        
        query = "SELECT * FROM token_usage_logs WHERE 1=1"
        params = []
        
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date)
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date)
        
        query += " ORDER BY timestamp DESC"
        
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(query, params)
                headers = [desc[0] for desc in cursor.description]
                
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    writer.writerows(cursor.fetchall())
                
                print(f"[TokenUsage] 已导出到 {filepath}")
            finally:
                conn.close()


# ========== 便捷函数：全局单例 ==========

_usage_tracker: Optional[TokenUsageTracker] = None
_usage_tracker_lock = threading.Lock()


def get_usage_tracker() -> TokenUsageTracker:
    """获取全局 TokenUsageTracker 单例"""
    global _usage_tracker
    if _usage_tracker is None:
        with _usage_tracker_lock:
            if _usage_tracker is None:
                _usage_tracker = TokenUsageTracker()
    return _usage_tracker


def log_token_usage(**kwargs) -> Tuple[int, float, Optional[str]]:
    """便捷函数：直接记录用量（使用全局单例）"""
    return get_usage_tracker().log_usage(**kwargs)
