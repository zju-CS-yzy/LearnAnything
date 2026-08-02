#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PermissionManager - 权限管理器

LA-051: 知识库权限管理核心模块

负责：
  1. 学科权限表管理（subject_permissions）
  2. 待审批变更表管理（subject_pending_changes）
  3. 权限检查与角色判断
  4. 审批流程（submit / review / list_pending）

角色体系：
  - owner:     拥有者（全部权限，可授权）
  - maintainer: 维护者（读写，不可授权）
  - contributor: 贡献者（只读 + 提交变更待审批）
  - reader:    读者（只读）

可见性：
  - public:   公开（任何人可读）
  - private:  私有（仅授权用户可访问）
  - group:    组内（仅指定用户组可访问）
"""

import json
import sqlite3
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any

from config.settings import DATA_ROOT


class Role(Enum):
    """权限角色"""
    OWNER = "owner"
    MAINTAINER = "maintainer"
    CONTRIBUTOR = "contributor"
    READER = "reader"


class Visibility(Enum):
    """学科可见性"""
    PUBLIC = "public"
    PRIVATE = "private"
    GROUP = "group"


class ChangeStatus(Enum):
    """变更状态"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# 角色权限矩阵：角色 → 能力
ROLE_CAPABILITIES = {
    Role.OWNER:     {"read": True, "write": True, "contribute": True, "manage": True, "review": True, "grant": True},
    Role.MAINTAINER:{"read": True, "write": True, "contribute": True, "manage": True, "review": True, "grant": False},
    Role.CONTRIBUTOR:{"read": True, "write": False, "contribute": True, "manage": False, "review": False, "grant": False},
    Role.READER:    {"read": True, "write": False, "contribute": False, "manage": False, "review": False, "grant": False},
}


class PermissionManager:
    """
    权限管理器
    
    数据表：
      1. subject_permissions  - 学科权限记录
      2. subject_pending_changes - 待审批变更
    """

    def __init__(self, db_path: Optional[str] = None):
        # LA-051: 权限表存储在全局数据目录
        self.db_path = Path(db_path) if db_path else DATA_ROOT / "permissions.db"
        self._ensure_tables()

    # ── 内部 ──

    def _get_conn(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        """初始化权限相关表"""
        conn = self._get_conn()
        try:
            # 学科权限表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS subject_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'reader',
                    granted_by TEXT,
                    granted_at TEXT,
                    UNIQUE(subject_id, user_id)
                )
            ''')
            # 学科变更审批表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS subject_pending_changes (
                    id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL,
                    submitted_by TEXT NOT NULL,
                    change_type TEXT NOT NULL DEFAULT 'import',
                    description TEXT,
                    file_data BLOB,
                    file_name TEXT,
                    file_size INTEGER DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    reviewed_by TEXT,
                    review_note TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            ''')
            conn.commit()
        finally:
            conn.close()

    def _now(self) -> str:
        return datetime.now().isoformat()

    def _role_from_str(self, s: str) -> Role:
        return Role(s.lower()) if s else Role.READER

    # ── 权限检查 ──

    def get_user_role(self, user_id: str, subject_id: str,
                      subject_owner_id: str = None,
                      subject_visibility: str = None) -> Optional[Role]:
        """
        获取用户在指定学科中的角色。
        
        优先级：
          1. 显式权限记录（subject_permissions 表）
          2. 所有权（user_id == subject_owner_id → owner）
          3. 公开学科（visibility == public → reader）
          4. 无权限 → None
        
        Args:
            user_id: 用户ID
            subject_id: 学科ID
            subject_owner_id: 学科 owner_id（从 subjects 表读取）
            subject_visibility: 学科 visibility（从 subjects 表读取）
        
        Returns:
            Role 枚举或 None（无权限）
        """
        conn = self._get_conn()
        try:
            # 1. 检查显式权限记录
            row = conn.execute(
                "SELECT role FROM subject_permissions WHERE subject_id = ? AND user_id = ?",
                (subject_id, user_id),
            ).fetchone()
            if row:
                return self._role_from_str(row["role"])
            
            # 2. 所有权检查
            if subject_owner_id and user_id == subject_owner_id:
                return Role.OWNER
            
            # 3. 公开学科
            if subject_visibility == Visibility.PUBLIC.value:
                return Role.READER
            
            return None
        finally:
            conn.close()

    def can_read(self, user_id: str, subject_id: str,
                 subject_owner_id: str = None,
                 subject_visibility: str = None) -> bool:
        """是否有读权限"""
        role = self.get_user_role(user_id, subject_id, subject_owner_id, subject_visibility)
        if role is None:
            return False
        return ROLE_CAPABILITIES[role]["read"]

    def can_write(self, user_id: str, subject_id: str,
                  subject_owner_id: str = None) -> bool:
        """是否有直接写权限（跳过审批）"""
        role = self.get_user_role(user_id, subject_id, subject_owner_id)
        if role is None:
            return False
        return ROLE_CAPABILITIES[role]["write"]

    def can_contribute(self, user_id: str, subject_id: str,
                       subject_owner_id: str = None) -> bool:
        """是否可以提交变更（contributor 及以上）"""
        role = self.get_user_role(user_id, subject_id, subject_owner_id)
        if role is None:
            return False
        return ROLE_CAPABILITIES[role]["contribute"]

    def can_manage(self, user_id: str, subject_id: str,
                   subject_owner_id: str = None) -> bool:
        """是否有管理权限（owner/maintainer）"""
        role = self.get_user_role(user_id, subject_id, subject_owner_id)
        if role is None:
            return False
        return ROLE_CAPABILITIES[role]["manage"]

    def can_review(self, user_id: str, subject_id: str,
                   subject_owner_id: str = None) -> bool:
        """是否有审批权限（owner/maintainer）"""
        role = self.get_user_role(user_id, subject_id, subject_owner_id)
        if role is None:
            return False
        return ROLE_CAPABILITIES[role]["review"]

    def can_grant(self, user_id: str, subject_id: str,
                  subject_owner_id: str = None) -> bool:
        """是否有授权权限（仅 owner）"""
        role = self.get_user_role(user_id, subject_id, subject_owner_id)
        if role is None:
            return False
        return ROLE_CAPABILITIES[role]["grant"]

    # ── 权限管理（仅 owner）──

    def grant_permission(self, subject_id: str, user_id: str, role: str,
                         granted_by: str, subject_owner_id: str = None) -> bool:
        """
        授予权限（仅 owner 可调用）
        
        Args:
            subject_id: 学科ID
            user_id: 被授权用户ID
            role: 角色（owner/maintainer/contributor/reader）
            granted_by: 授权者用户ID（必须为 owner）
            subject_owner_id: 学科所有者ID（可选，用于所有权验证）
        
        Returns:
            True: 成功
            False: 失败（授权者不是 owner 或权限不足）
        
        Raises:
            PermissionError: 授权者不是 owner
        """
        if not self.can_grant(granted_by, subject_id, subject_owner_id):
            raise PermissionError("只有学科拥有者(owner)可以授权")
        
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO subject_permissions
                   (subject_id, user_id, role, granted_by, granted_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (subject_id, user_id, role.lower(), granted_by, self._now()),
            )
            conn.commit()
            print(f"[Permission] {granted_by} 授予 {user_id} 在 {subject_id} 的 {role} 权限")
            return True
        finally:
            conn.close()

    def revoke_permission(self, subject_id: str, user_id: str,
                          revoked_by: str, subject_owner_id: str = None) -> bool:
        """
        撤销权限（仅 owner 可调用）
        
        Args:
            subject_id: 学科ID
            user_id: 被撤销权限的用户ID
            revoked_by: 操作者用户ID（必须为 owner）
            subject_owner_id: 学科所有者ID（可选，用于所有权验证）
        
        Raises:
            PermissionError: 操作者不是 owner
        """
        if not self.can_grant(revoked_by, subject_id, subject_owner_id):
            raise PermissionError("只有学科拥有者(owner)可以撤销权限")
        
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM subject_permissions WHERE subject_id = ? AND user_id = ?",
                (subject_id, user_id),
            )
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                print(f"[Permission] {revoked_by} 撤销 {user_id} 在 {subject_id} 的权限")
            return deleted
        finally:
            conn.close()

    def list_permissions(self, subject_id: str) -> List[Dict[str, Any]]:
        """列出学科的所有权限记录"""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM subject_permissions WHERE subject_id = ? ORDER BY granted_at DESC",
                (subject_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── 变更审批（contributor 提交 → owner/maintainer 审批）──

    def submit_change(self, subject_id: str, submitted_by: str,
                      change_type: str = "import",
                      description: str = "",
                      file_data: bytes = None,
                      file_name: str = "",
                      subject_owner_id: str = None) -> str:
        """
        contributor 提交变更。
        
        Args:
            subject_id: 学科ID
            submitted_by: 提交者用户ID
            change_type: 变更类型（import/update/delete）
            description: 变更描述
            file_data: 文件内容（BLOB）
            file_name: 文件名
            subject_owner_id: 学科所有者ID（可选，用于权限验证）
        
        Returns:
            change_id: 变更记录ID
        
        Raises:
            PermissionError: 提交者无 contribute 权限
        """
        if not self.can_contribute(submitted_by, subject_id, subject_owner_id):
            raise PermissionError("您没有权限向此学科提交变更")
        
        change_id = f"chg_{uuid.uuid4().hex[:12]}"
        now = self._now()
        
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO subject_pending_changes
                   (id, subject_id, submitted_by, change_type, description,
                    file_data, file_name, file_size, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (change_id, subject_id, submitted_by, change_type, description,
                 file_data, file_name, len(file_data) if file_data else 0,
                 ChangeStatus.PENDING.value, now, now),
            )
            conn.commit()
            print(f"[Permission] {submitted_by} 提交变更 {change_id} 到 {subject_id}")
            return change_id
        finally:
            conn.close()

    def review_change(self, change_id: str, reviewer: str,
                      approve: bool, note: str = "",
                      subject_owner_id: str = None) -> Dict[str, Any]:
        """
        owner/maintainer 审批变更。
        
        Args:
            change_id: 变更记录ID
            reviewer: 审批者用户ID
            approve: True 批准 / False 拒绝
            note: 审批备注（拒绝时必填）
            subject_owner_id: 学科所有者ID（可选，用于权限验证）
        
        Returns:
            变更记录字典
        
        Raises:
            PermissionError: 审批者无 review 权限
            ValueError: 变更不存在或已处理
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM subject_pending_changes WHERE id = ?",
                (change_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"变更不存在: {change_id}")
            
            change = dict(row)
            subject_id = change["subject_id"]
            
            # 权限检查
            if not self.can_review(reviewer, subject_id, subject_owner_id):
                raise PermissionError("您没有权限审批此变更")
            
            # 检查状态
            if change["status"] != ChangeStatus.PENDING.value:
                raise ValueError(f"变更已处理，当前状态: {change['status']}")
            
            # 更新状态
            status = ChangeStatus.APPROVED.value if approve else ChangeStatus.REJECTED.value
            now = self._now()
            conn.execute(
                """UPDATE subject_pending_changes
                   SET status = ?, reviewed_by = ?, review_note = ?, updated_at = ?
                   WHERE id = ?""",
                (status, reviewer, note, now, change_id),
            )
            conn.commit()
            
            action = "批准" if approve else "拒绝"
            print(f"[Permission] {reviewer} {action} 变更 {change_id}")
            
            # 返回结果时不包含 file_data BLOB（避免 JSON 序列化失败）
            result = dict(change)
            result.pop("file_data", None)
            
            return {
                **result,
                "status": status,
                "reviewed_by": reviewer,
                "review_note": note,
                "updated_at": now,
            }
        finally:
            conn.close()

    def list_pending_changes(self, subject_id: str) -> List[Dict[str, Any]]:
        """列出学科的所有待审批变更。
        
        注意：返回的数据不包含 file_data BLOB（二进制内容），
        避免 JSON 序列化失败。前端如需下载文件，使用专门的下载接口。
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT id, subject_id, submitted_by, change_type, description,
                          file_name, file_size, status, created_at, updated_at, reviewed_by, review_note
                   FROM subject_pending_changes
                   WHERE subject_id = ? AND status = ?
                   ORDER BY created_at DESC""",
                (subject_id, ChangeStatus.PENDING.value),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_change(self, change_id: str) -> Optional[Dict[str, Any]]:
        """获取单个变更记录（不含 file_data BLOB）。"""
        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT id, subject_id, submitted_by, change_type, description,
                          file_name, file_size, status, created_at, updated_at, reviewed_by, review_note
                   FROM subject_pending_changes WHERE id = ?""",
                (change_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_change_with_data(self, change_id: str) -> Optional[Dict[str, Any]]:
        """获取单个变更记录（含 file_data BLOB）。
        
        用于审批通过后自动导入文件的场景，避免单独的查询。
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM subject_pending_changes WHERE id = ?",
                (change_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # ── 学科列表（带权限过滤）──

    def list_accessible_subjects(self, user_id: str, subjects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        根据权限过滤学科列表。
        
        Args:
            user_id: 当前用户ID
            subjects: 学科列表（来自 SubjectManager.list_subjects）
        
        Returns:
            可访问的学科列表（每个学科附加 role 字段）
        """
        result = []
        for subj in subjects:
            subject_id = subj["id"]
            owner_id = subj.get("owner_id", "system")
            visibility = subj.get("visibility", "public")
            
            role = self.get_user_role(user_id, subject_id, owner_id, visibility)
            if role is not None:
                result.append({
                    **subj,
                    "role": role.value,
                    "can_write": ROLE_CAPABILITIES[role]["write"],
                    "can_contribute": ROLE_CAPABILITIES[role]["contribute"],
                    "can_manage": ROLE_CAPABILITIES[role]["manage"],
                    "can_review": ROLE_CAPABILITIES[role]["review"],
                })
        return result


# ==================== 全局实例 ====================
_permission_manager: Optional[PermissionManager] = None


def get_permission_manager() -> PermissionManager:
    """获取全局 PermissionManager 实例（懒加载）"""
    global _permission_manager
    if _permission_manager is None:
        _permission_manager = PermissionManager()
    return _permission_manager
