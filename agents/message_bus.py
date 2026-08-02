#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MessageBus — Agent 间消息总线（P0-INT-6）

增强版：SQLite 持久化 + 跨会话检索（LA-050-B）

支持：
- 事件发布/订阅
- 主题过滤
- 消息持久化（SQLite）
- 跨会话历史检索
- 消息审计日志

用法:
    bus = MessageBus()
    bus.subscribe("quiz", "CoachAgent", handler)
    bus.publish("quiz", "QuizAgent", {"event": "quiz_generated", ...})
    
    # 查询历史
    history = bus.query_history(topic="quiz", sender="QuizAgent", limit=10)
"""

import sqlite3
import json
import uuid
from pathlib import Path
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime


from config.settings import KNOWLEDGE_BASE_DIR


# 持久化数据库路径（LA-DEPLOY: 使用 KNOWLEDGE_BASE_DIR 替代硬编码路径）
MESSAGE_BUS_DB = KNOWLEDGE_BASE_DIR / "message_bus.db"


@dataclass
class Message:
    """消息结构"""
    id: str
    topic: str
    event: str
    sender: str
    payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    delivered: List[str] = field(default_factory=list)
    dropped: bool = False


class MessageBus:
    """
    Agent 间消息总线。

    LA-050-B 增强：
    - 审计日志持久化到 SQLite（重启不丢失）
    - 支持跨会话消息检索
    - 向后兼容：现有 subscribe/publish API 不变
    """

    def __init__(self, enable_audit: bool = True, persist: bool = True):
        """
        Args:
            enable_audit: 是否启用审计日志
            persist: 是否启用 SQLite 持久化
        """
        # topic -> {agent_name: handler}
        self._subscriptions: Dict[str, Dict[str, Callable]] = {}
        # 内存中保留最近 100 条（快速访问）
        self._audit_log: List[Message] = []
        self._max_audit_size = 100
        self._enable_audit = enable_audit
        self._persist = persist
        self._msg_counter = 0

        # LA-050-B: 初始化持久化
        if self._persist:
            self._init_db()
            self._msg_counter = self._get_max_counter()
            print(f"[MessageBus] LA-050-B: 持久化已启用 | db={MESSAGE_BUS_DB} | last_counter={self._msg_counter}")
        else:
            print("[MessageBus] LA-050-B: 内存模式（无持久化）")

    # ========== LA-050-B: SQLite 持久化 ==========

    def _init_db(self):
        """初始化 SQLite 数据库"""
        MESSAGE_BUS_DB.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(MESSAGE_BUS_DB))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS message_bus_log (
                    msg_id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    event TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    delivered TEXT NOT NULL,
                    dropped INTEGER DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_msg_topic ON message_bus_log(topic)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_msg_sender ON message_bus_log(sender)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_msg_timestamp ON message_bus_log(timestamp)
            """)
            conn.commit()
        finally:
            conn.close()

    def _save_to_db(self, msg: Message):
        """将消息保存到数据库"""
        if not self._persist:
            return
        conn = sqlite3.connect(str(MESSAGE_BUS_DB))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO message_bus_log
                (msg_id, topic, event, sender, payload, timestamp, delivered, dropped)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                msg.id,
                msg.topic,
                msg.event,
                msg.sender,
                json.dumps(msg.payload, ensure_ascii=False),
                msg.timestamp.isoformat(),
                json.dumps(msg.delivered, ensure_ascii=False),
                1 if msg.dropped else 0
            ))
            conn.commit()
        finally:
            conn.close()

    def _get_max_counter(self) -> int:
        """从数据库获取最大消息计数器"""
        if not MESSAGE_BUS_DB.exists():
            return 0
        conn = sqlite3.connect(str(MESSAGE_BUS_DB))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT msg_id FROM message_bus_log ORDER BY msg_id DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                # msg_id 格式: msg_XXXX
                try:
                    return int(row[0].split('_')[1])
                except (ValueError, IndexError):
                    return 0
            return 0
        finally:
            conn.close()

    # ========== 核心 API（向后兼容）==========

    def subscribe(self, topic: str, agent_name: str, handler: Callable[[Message], None]):
        """
        订阅主题。

        Args:
            topic: 主题名（如 "quiz", "user_state", "weak_area"）
            agent_name: 订阅者 Agent 名称
            handler: 回调函数，接收 Message 对象
        """
        if topic not in self._subscriptions:
            self._subscriptions[topic] = {}
        self._subscriptions[topic][agent_name] = handler
        print(f"[MessageBus] SUBSCRIBE topic={topic} agent={agent_name}")

    def unsubscribe(self, topic: str, agent_name: str):
        """取消订阅"""
        if topic in self._subscriptions and agent_name in self._subscriptions[topic]:
            del self._subscriptions[topic][agent_name]
            print(f"[MessageBus] UNSUBSCRIBE topic={topic} agent={agent_name}")

    def publish(self, topic: str, sender: str, event: str, payload: Dict[str, Any]) -> Message:
        """
        发布消息到主题。

        Args:
            topic: 主题名
            sender: 发送者 Agent 名称
            event: 事件类型（如 "quiz_generated", "ability_updated"）
            payload: 消息负载数据

        Returns:
            Message: 消息对象（包含投递状态）
        """
        self._msg_counter += 1
        msg = Message(
            id=f"msg_{self._msg_counter:04d}",
            topic=topic,
            event=event,
            sender=sender,
            payload=payload,
        )

        # 记录审计日志（内存）
        if self._enable_audit:
            self._audit_log.append(msg)
            if len(self._audit_log) > self._max_audit_size:
                self._audit_log.pop(0)

        # LA-050-B: 持久化到 SQLite
        self._save_to_db(msg)

        # 打印发布日志
        payload_preview = json.dumps(payload, ensure_ascii=False)[:100]
        print(f"[MessageBus] PUBLISH  id={msg.id} topic={topic} event={event} sender={sender} payload={payload_preview}")

        # 投递给订阅者
        recipients = self._subscriptions.get(topic, {})
        if not recipients:
            print(f"[MessageBus] DROP    id={msg.id} reason=no_subscribers")
            msg.dropped = True
            # 更新数据库中的 dropped 状态
            self._update_dropped(msg.id, True)
            return msg

        for agent_name, handler in recipients.items():
            if agent_name == sender:
                # 不投递给发送者自己
                continue
            try:
                start = datetime.now()
                handler(msg)
                latency_ms = (datetime.now() - start).total_seconds() * 1000
                msg.delivered.append(agent_name)
                print(f"[MessageBus] DELIVER id={msg.id} topic={topic} recipient={agent_name} latency={latency_ms:.1f}ms")
            except Exception as e:
                print(f"[MessageBus] FAILED  id={msg.id} topic={topic} recipient={agent_name} error={e}")

        # 更新数据库中的 delivered 状态
        if self._persist:
            self._update_delivered(msg.id, msg.delivered)

        return msg

    def _update_dropped(self, msg_id: str, dropped: bool):
        """更新消息 dropped 状态"""
        if not self._persist:
            return
        conn = sqlite3.connect(str(MESSAGE_BUS_DB))
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE message_bus_log SET dropped = ? WHERE msg_id = ?",
                (1 if dropped else 0, msg_id)
            )
            conn.commit()
        finally:
            conn.close()

    def _update_delivered(self, msg_id: str, delivered: List[str]):
        """更新消息 delivered 状态"""
        if not self._persist:
            return
        conn = sqlite3.connect(str(MESSAGE_BUS_DB))
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE message_bus_log SET delivered = ? WHERE msg_id = ?",
                (json.dumps(delivered, ensure_ascii=False), msg_id)
            )
            conn.commit()
        finally:
            conn.close()

    # ========== LA-050-B: 新增查询 API ==========

    def query_history(self, topic: Optional[str] = None,
                      sender: Optional[str] = None,
                      event: Optional[str] = None,
                      start_time: Optional[datetime] = None,
                      end_time: Optional[datetime] = None,
                      limit: int = 50,
                      offset: int = 0) -> List[Dict[str, Any]]:
        """
        查询历史消息（跨会话检索）。

        Args:
            topic: 主题过滤
            sender: 发送者过滤
            event: 事件类型过滤
            start_time: 起始时间
            end_time: 结束时间
            limit: 返回数量
            offset: 分页偏移

        Returns:
            消息列表（字典格式）
        """
        if not self._persist or not MESSAGE_BUS_DB.exists():
            # 内存模式：从 _audit_log 查询
            return self._query_memory(topic, sender, event, limit)

        conn = sqlite3.connect(str(MESSAGE_BUS_DB))
        try:
            cursor = conn.cursor()

            # 构建查询条件
            conditions = []
            params = []
            if topic:
                conditions.append("topic = ?")
                params.append(topic)
            if sender:
                conditions.append("sender = ?")
                params.append(sender)
            if event:
                conditions.append("event = ?")
                params.append(event)
            if start_time:
                conditions.append("timestamp >= ?")
                params.append(start_time.isoformat())
            if end_time:
                conditions.append("timestamp <= ?")
                params.append(end_time.isoformat())

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            sql = f"""
                SELECT msg_id, topic, event, sender, payload, timestamp, delivered, dropped
                FROM message_bus_log
                {where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            results = []
            for row in rows:
                results.append({
                    "id": row[0],
                    "topic": row[1],
                    "event": row[2],
                    "sender": row[3],
                    "payload": json.loads(row[4]) if row[4] else {},
                    "timestamp": row[5],
                    "delivered": json.loads(row[6]) if row[6] else [],
                    "dropped": bool(row[7]),
                })

            print(f"[MessageBus] LA-050-B: query_history 返回 {len(results)} 条记录 | "
                  f"topic={topic}, sender={sender}, event={event}")
            return results
        finally:
            conn.close()

    def _query_memory(self, topic, sender, event, limit) -> List[Dict[str, Any]]:
        """内存模式查询"""
        results = []
        for msg in reversed(self._audit_log):
            if topic and msg.topic != topic:
                continue
            if sender and msg.sender != sender:
                continue
            if event and msg.event != event:
                continue
            results.append({
                "id": msg.id,
                "topic": msg.topic,
                "event": msg.event,
                "sender": msg.sender,
                "payload": msg.payload,
                "timestamp": msg.timestamp.isoformat(),
                "delivered": msg.delivered,
                "dropped": msg.dropped,
            })
            if len(results) >= limit:
                break
        return results

    def get_topic_stats(self, topic: Optional[str] = None) -> Dict[str, Any]:
        """
        获取主题统计信息。

        Args:
            topic: 指定主题，None 则返回全局统计

        Returns:
            统计字典
        """
        if not self._persist or not MESSAGE_BUS_DB.exists():
            return self._get_memory_stats(topic)

        conn = sqlite3.connect(str(MESSAGE_BUS_DB))
        try:
            cursor = conn.cursor()

            # 总消息数
            if topic:
                cursor.execute("SELECT COUNT(*) FROM message_bus_log WHERE topic = ?", (topic,))
            else:
                cursor.execute("SELECT COUNT(*) FROM message_bus_log")
            total = cursor.fetchone()[0]

            # 按事件类型统计
            if topic:
                cursor.execute("""
                    SELECT event, COUNT(*) FROM message_bus_log WHERE topic = ? GROUP BY event
                """, (topic,))
            else:
                cursor.execute("SELECT event, COUNT(*) FROM message_bus_log GROUP BY event")
            event_counts = {row[0]: row[1] for row in cursor.fetchall()}

            # 按发送者统计
            if topic:
                cursor.execute("""
                    SELECT sender, COUNT(*) FROM message_bus_log WHERE topic = ? GROUP BY sender
                """, (topic,))
            else:
                cursor.execute("SELECT sender, COUNT(*) FROM message_bus_log GROUP BY sender")
            sender_counts = {row[0]: row[1] for row in cursor.fetchall()}

            # 丢弃率
            if topic:
                cursor.execute("""
                    SELECT COUNT(*) FROM message_bus_log WHERE topic = ? AND dropped = 1
                """, (topic,))
            else:
                cursor.execute("SELECT COUNT(*) FROM message_bus_log WHERE dropped = 1")
            dropped = cursor.fetchone()[0]
            drop_rate = round(dropped / max(total, 1) * 100, 1)

            return {
                "total_messages": total,
                "event_counts": event_counts,
                "sender_counts": sender_counts,
                "dropped_count": dropped,
                "drop_rate": f"{drop_rate}%",
            }
        finally:
            conn.close()

    def _get_memory_stats(self, topic) -> Dict[str, Any]:
        """内存模式统计"""
        messages = self._audit_log
        if topic:
            messages = [m for m in messages if m.topic == topic]

        total = len(messages)
        event_counts = {}
        sender_counts = {}
        dropped = 0
        for m in messages:
            event_counts[m.event] = event_counts.get(m.event, 0) + 1
            sender_counts[m.sender] = sender_counts.get(m.sender, 0) + 1
            if m.dropped:
                dropped += 1

        return {
            "total_messages": total,
            "event_counts": event_counts,
            "sender_counts": sender_counts,
            "dropped_count": dropped,
            "drop_rate": f"{round(dropped / max(total, 1) * 100, 1)}%",
        }

    # ========== 向后兼容 API ==========

    def get_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取审计日志（向后兼容）"""
        if self._persist:
            return self.query_history(limit=limit)
        # 内存模式
        result = []
        for msg in self._audit_log[-limit:]:
            result.append({
                "id": msg.id,
                "timestamp": msg.timestamp.isoformat(),
                "topic": msg.topic,
                "event": msg.event,
                "sender": msg.sender,
                "delivered": msg.delivered,
                "dropped": msg.dropped,
                "payload_preview": json.dumps(msg.payload, ensure_ascii=False)[:80],
            })
        return result

    def get_stats(self) -> Dict[str, Any]:
        """获取总线统计信息（向后兼容）"""
        stats = {
            "topics": list(self._subscriptions.keys()),
            "subscribers": {t: list(subs.keys()) for t, subs in self._subscriptions.items()},
            "total_messages": self._msg_counter,
            "audit_log_size": len(self._audit_log),
        }
        if self._persist:
            stats["persisted_messages"] = self.get_topic_stats()["total_messages"]
            stats["db_path"] = str(MESSAGE_BUS_DB)
        return stats

    def reset(self):
        """重置总线（测试用）"""
        self._subscriptions.clear()
        self._audit_log.clear()
        self._msg_counter = 0
        if self._persist and MESSAGE_BUS_DB.exists():
            conn = sqlite3.connect(str(MESSAGE_BUS_DB))
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM message_bus_log")
                conn.commit()
            finally:
                conn.close()
        print("[MessageBus] RESET")
