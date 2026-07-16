#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MessageBus — Agent 间消息总线（P0-INT-6）

简单的内存型发布-订阅消息总线，支持：
- 事件发布/订阅
- 主题过滤
- 消息审计日志（console 输出，便于测试观察）

用法:
    bus = MessageBus()
    bus.subscribe("quiz", "CoachAgent", handler)
    bus.publish("quiz", "QuizAgent", {"event": "quiz_generated", ...})
"""

from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json


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

    轻量级内存实现，每个 Coordinator 实例拥有一个总线。
    """

    def __init__(self, enable_audit: bool = True):
        # topic -> {agent_name: handler}
        self._subscriptions: Dict[str, Dict[str, Callable]] = {}
        # 审计日志（内存中保留最近 100 条）
        self._audit_log: List[Message] = []
        self._max_audit_size = 100
        self._enable_audit = enable_audit
        self._msg_counter = 0

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

        # 记录审计日志
        if self._enable_audit:
            self._audit_log.append(msg)
            if len(self._audit_log) > self._max_audit_size:
                self._audit_log.pop(0)

        # 打印发布日志
        payload_preview = json.dumps(payload, ensure_ascii=False)[:100]
        print(f"[MessageBus] PUBLISH  id={msg.id} topic={topic} event={event} sender={sender} payload={payload_preview}")

        # 投递给订阅者
        recipients = self._subscriptions.get(topic, {})
        if not recipients:
            print(f"[MessageBus] DROP    id={msg.id} reason=no_subscribers")
            msg.dropped = True
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

        return msg

    def get_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取审计日志（用于测试和调试）"""
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
        """获取总线统计信息"""
        return {
            "topics": list(self._subscriptions.keys()),
            "subscribers": {t: list(subs.keys()) for t, subs in self._subscriptions.items()},
            "total_messages": self._msg_counter,
            "audit_log_size": len(self._audit_log),
        }

    def reset(self):
        """重置总线（测试用）"""
        self._subscriptions.clear()
        self._audit_log.clear()
        self._msg_counter = 0
        print("[MessageBus] RESET")
