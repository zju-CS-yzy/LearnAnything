#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LA-MEDIA-UNIFY: 统一媒体路径解析模块

解决智能问答和知识图谱中媒体引用路径解析不一致的问题。
所有需要解析媒体路径的代码都应通过此模块，确保路径解析逻辑统一。

设计原则:
1. 单一入口: 所有媒体路径解析走 resolve_media_path()
2. 后端主导: 路径解析逻辑放在后端，前端只负责展示
3. 向后兼容: 支持旧格式的路径（_v1_images、绝对路径等）
4. URL 统一: 所有媒体资源统一使用 /api/media/{path} 访问
"""

from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import json
import os
import re


def resolve_media_path(
    path_input: Union[str, Dict[str, Any], Path],
    subject: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    统一解析媒体路径，返回标准化的媒体引用对象。

    Args:
        path_input: 可以是字符串路径、Path 对象或 media_refs dict
        subject: 学科名称（可选，用于路径推断）
        user_id: 用户ID（可选，用于用户私有目录查找）

    Returns:
        {
            "path": str,        # 原始路径（保留）
            "relative_path": str,  # 相对 KNOWLEDGE_BASE_DIR 的路径
            "url": str,         # 可直接访问的 URL: /api/media/...
            "filename": str,    # 文件名
            "subject": str,     # 推断的学科名
            "resolved": bool,   # 是否成功解析
        }
    """
    from config.settings import KNOWLEDGE_BASE_DIR

    result = {
        "path": "",
        "relative_path": "",
        "url": "",
        "filename": "",
        "subject": subject or "",
        "resolved": False,
    }

    # 1. 提取原始路径
    raw_path = ""
    if isinstance(path_input, dict):
        # 优先顺序: relative_path > path > thumbnail_path
        raw_path = (
            path_input.get("relative_path")
            or path_input.get("path")
            or path_input.get("thumbnail_path")
            or ""
        )
        # 继承 subject 字段
        if not subject and path_input.get("subject"):
            subject = path_input.get("subject")
    elif isinstance(path_input, Path):
        raw_path = str(path_input)
    else:
        raw_path = str(path_input)

    if not raw_path:
        return result

    result["path"] = raw_path

    # 2. 统一路径格式（反斜杠→正斜杠）
    normalized = raw_path.replace("\\", "/")

    # 3. 提取文件名
    filename = normalized.split("/")[-1]
    result["filename"] = filename

    # 4. 只接受知识库中确实存在的文件，禁止把任意文件名伪装成可访问 URL。
    actual_path = _resolve_existing_media_file(normalized, subject=subject, user_id=user_id)
    if actual_path is None:
        return result

    # 5. 构建相对路径（相对于 KNOWLEDGE_BASE_DIR）
    try:
        relative_path = actual_path.resolve().relative_to(KNOWLEDGE_BASE_DIR.resolve()).as_posix()
    except ValueError:
        # 防止绝对路径越过知识库根目录。
        return result
    inferred_subject = _infer_subject(relative_path, subject)
    result["subject"] = inferred_subject
    result["relative_path"] = relative_path
    result["url"] = f"/api/media/{relative_path}"
    result["resolved"] = True

    return result


def _resolve_existing_media_file(
    normalized_path: str,
    subject: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Optional[Path]:
    """将媒体引用解析为知识库内的真实文件。"""
    from config.settings import KNOWLEDGE_BASE_DIR

    normalized = normalized_path.replace("\\", "/")
    candidates: List[Path] = []

    # 绝对路径（包括 Windows D:/...）或带 knowledge_base 前缀的路径。
    raw_candidate = Path(normalized_path)
    if raw_candidate.is_absolute():
        candidates.append(raw_candidate)
    if "knowledge_base/" in normalized:
        candidates.append(KNOWLEDGE_BASE_DIR / normalized.split("knowledge_base/", 1)[1])

    # 已经是知识库相对路径。
    if normalized.startswith("Share/") or normalized.startswith("Users/"):
        candidates.append(KNOWLEDGE_BASE_DIR / normalized)

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if resolved.is_file() and resolved.is_relative_to(KNOWLEDGE_BASE_DIR.resolve()):
                return resolved
        except (OSError, ValueError):
            continue

    # media_refs 中常见的只有文件名、media/images/... 或 subject/media/...。
    filename = Path(normalized).name
    if not filename:
        return None
    return find_media_file(filename, subject=subject, user_id=user_id)


def _infer_subject(path: str, explicit_subject: Optional[str] = None) -> str:
    """从路径中推断学科名"""
    if explicit_subject:
        return explicit_subject

    # 策略1: 新格式 knowledge_base/Share/<subject>/media/images/
    if "knowledge_base/Share/" in path:
        parts = path.split("knowledge_base/Share/")
        if len(parts) > 1:
            sub_parts = parts[1].split("/")
            if sub_parts:
                return sub_parts[0]

    # 策略2: 新格式 knowledge_base/Users/<user>/<subject>/media/images/
    if "knowledge_base/Users/" in path:
        parts = path.split("knowledge_base/Users/")
        if len(parts) > 1:
            sub_parts = parts[1].split("/")
            if len(sub_parts) > 1:
                return sub_parts[1]  # user 后的第一个目录是学科

    # 策略3: 旧格式 *_v1_images/ 或 *_v1_thumbnails/
    for marker in ["_v1_images", "_v1_thumbnails"]:
        idx = path.find(marker)
        if idx != -1:
            before = path[:idx]
            # 取最后一个 / 后的内容
            parts = before.rstrip("/").split("/")
            if parts:
                return parts[-1].replace(marker, "")

    # 策略4: 从路径中的目录名推断（如 rag_bald/media/images/）
    parts = [p for p in path.split("/") if p]
    for i, part in enumerate(parts):
        if part in ("media", "images", "thumbnails") and i > 0:
            return parts[i - 1]

    return "generic"


def resolve_media_list(
    media_refs: List[Dict[str, Any]],
    subject: Optional[str] = None,
    user_id: Optional[str] = None,
    deduplicate: bool = False,
) -> List[Dict[str, Any]]:
    """
    批量解析 media_refs 列表。

    Args:
        media_refs: media_refs 列表
        subject: 学科名
        user_id: 用户ID

    Returns:
        解析后的 media 列表，每个元素包含 url 字段
    """
    results = []
    seen = set()
    for ref in media_refs:
        if not ref:
            continue
        resolved = resolve_media_path(ref, subject=subject, user_id=user_id)
        # 合并原始字段和解析结果
        merged = dict(ref)
        merged.update(resolved)
        if deduplicate:
            if resolved.get("resolved"):
                identity = ("resolved", resolved.get("relative_path"))
            else:
                identity = (
                    "raw",
                    json.dumps(ref, ensure_ascii=False, sort_keys=True, default=str),
                )
            if identity in seen:
                continue
            seen.add(identity)
        results.append(merged)
    return results


def _lookup_subject_registration(
    subject_id: str,
    user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    MEDIA-P2-1: 在全局 subjects.db 与各用户私有 subjects.db 中查找学科注册信息。

    当前用户 → 全局 → 其他用户。当前用户优先可避免同名私有学科
    被解析成另一个 owner 的注册记录。

    Returns:
        学科字典（含 owner_id / visibility）或 None
    """
    from core.subject_manager import SubjectManager, get_subject as get_global_subject
    from config.settings import USERS_DIR

    # 1. 查指定用户私有，再查全局与其他用户
    user_dbs: List[Path] = []
    if user_id and user_id not in ("default", "anonymous"):
        db = USERS_DIR / user_id / "subjects.db"
        if db.exists():
            user_dbs.append(db)
    for db in user_dbs:
        try:
            sm = SubjectManager(db_path=str(db))
            subj = sm.get_subject(subject_id)
            if subj:
                return subj
        except Exception:
            continue

    try:
        subj = get_global_subject(subject_id)
        if subj:
            return subj
    except Exception:
        pass

    # 2. 遍历其他用户
    user_dbs = []
    try:
        if USERS_DIR.exists():
            for user_dir in sorted(USERS_DIR.iterdir()):
                if not user_dir.is_dir():
                    continue
                db = user_dir / "subjects.db"
                if db.exists() and db not in user_dbs:
                    user_dbs.append(db)
    except Exception:
        pass

    for db in user_dbs:
        try:
            sm = SubjectManager(db_path=str(db))
            subj = sm.get_subject(subject_id)
            if subj:
                return subj
        except Exception:
            continue

    return None


def _find_renamed_hash_match(directory: Path, filename: str) -> Optional[Path]:
    """Resolve an old MinerU filename after VLM title-based renaming.

    Renaming keeps the eight-character content hash suffix, for example
    ``tmp..._d0acf041.png`` -> ``多查询生成-d0acf041.png``.  Only a unique
    match inside the already-authorized subject directory is accepted.
    """
    stem, suffix = Path(filename).stem, Path(filename).suffix
    match = re.search(r"(?:^|[_-])([0-9a-fA-F]{8})$", stem)
    if not match or not directory.is_dir():
        return None
    digest = match.group(1).lower()
    matches = [
        item for item in directory.glob(f"*{digest}{suffix}")
        if item.is_file() and item.stem.lower().endswith(digest)
    ]
    return matches[0] if len(matches) == 1 else None


def _find_in_media_dir(directory: Path, filename: str) -> Optional[Path]:
    exact = directory / filename
    if exact.is_file():
        return exact
    return _find_renamed_hash_match(directory, filename)


def find_media_file(
    filename: str,
    subject: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Optional[Path]:
    """
    在知识库中查找媒体文件的实际路径。

    搜索顺序:
    1. 用户私有目录: Users/<user>/<subject>/media/images/
    1.5. MEDIA-P2-1: 已授权访问的 owner 私有学科目录
    2. 共享目录: Share/<subject>/media/images/
    3. 旧结构: *_v1_images/、*_v1_thumbnails/
    4. 全局遍历

    Args:
        filename: 文件名
        subject: 学科名（可选，优先搜索该学科）
        user_id: 用户ID（可选，优先搜索用户私有目录）

    Returns:
        文件 Path 或 None
    """
    from config.settings import (
        KNOWLEDGE_BASE_DIR,
        SHARE_KB_DIR,
        USERS_KB_DIR,
        get_user_root_dir,
        get_user_subject_dir,
    )

    safe_name = Path(filename).name

    # 1. 用户私有目录
    if user_id and user_id not in ("default", "anonymous"):
        user_root = get_user_root_dir(user_id)
        subject_dirs = []
        if subject:
            subject_dirs.append(get_user_subject_dir(user_id, subject))
        elif user_root.exists():
            subject_dirs.extend(p for p in user_root.iterdir() if p.is_dir())
        for subject_dir in subject_dirs:
            user_img_dir = subject_dir / "media" / "images"
            candidate = _find_in_media_dir(user_img_dir, safe_name)
            if candidate:
                return candidate

            user_thumb_dir = subject_dir / "media" / "thumbnails"
            candidate = _find_in_media_dir(user_thumb_dir, safe_name)
            if candidate:
                return candidate

    # 1.5. MEDIA-P2-1: 私有学科被授权后数据仍在 owner 目录（授权≠公开≠数据迁移）。
    # 当请求者不是 owner 但拥有该学科的读权限时，搜索 owner 的私有目录。
    # 注意：这里直接拼路径而不是调 get_user_subject_dir()，避免为不存在的
    # owner/subject 组合创建空目录的副作用。
    if subject and user_id and user_id not in ("default", "anonymous"):
        try:
            registration = _lookup_subject_registration(subject, user_id)
            if registration:
                owner_id = registration.get("owner_id", "system")
                visibility = registration.get("visibility", "public")
                if visibility == "private" and owner_id != user_id:
                    from core.permission_manager import PermissionManager
                    if PermissionManager().can_read(user_id, subject, owner_id):
                        owner_subject_dir = USERS_KB_DIR / owner_id / subject
                        for sub in ("media/images", "media/thumbnails"):
                            candidate = _find_in_media_dir(owner_subject_dir / sub, safe_name)
                            if candidate:
                                return candidate
        except Exception:
            pass

    # 2. 共享目录
    if subject:
        share_subject_dir = SHARE_KB_DIR / subject
        share_img_dir = share_subject_dir / "media" / "images"
        candidate = _find_in_media_dir(share_img_dir, safe_name)
        if candidate:
            return candidate

        share_thumb_dir = share_subject_dir / "media" / "thumbnails"
        candidate = _find_in_media_dir(share_thumb_dir, safe_name)
        if candidate:
            return candidate

    # 3. 旧结构: *_v1_images/
    for subdir in KNOWLEDGE_BASE_DIR.iterdir():
        if not subdir.is_dir():
            continue
        if subdir.name.endswith("_images") or subdir.name.endswith("_thumbnails"):
            candidate = subdir / safe_name
            if candidate.exists():
                return candidate

    # 4. 全局遍历 Share/
    # MEDIA-P2-2: 已知学科时不做跨学科文件名遍历——同名图片会解析到错误学科。
    # 仅在完全不知道学科上下文时才作为最后手段全局搜索。
    if subject:
        return None
    share_dir = KNOWLEDGE_BASE_DIR / "Share"
    if share_dir.exists():
        for subject_dir in share_dir.iterdir():
            if not subject_dir.is_dir():
                continue
            img_dir = subject_dir / "media" / "images"
            if img_dir.exists():
                candidate = img_dir / safe_name
                if candidate.exists():
                    return candidate
            thumb_dir = subject_dir / "media" / "thumbnails"
            if thumb_dir.exists():
                candidate = thumb_dir / safe_name
                if candidate.exists():
                    return candidate

    return None
