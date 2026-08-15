"""
MinerU CLI 客户端封装
调用本地 mineru-open-api CLI 工具，将 PDF 解析为结构化 Markdown 和 chunk 列表。

使用方式:
    from core.mineru_client import MinerUClient

    client = MinerUClient()
    chunks = client.parse_pdf_to_chunks(
        pdf_path="path/to/doc.pdf",
        subject="generic",
        metadata={"source": "doc.pdf"}
    )
    # chunks: [{"id": str, "text": str, "metadata": dict, "source": str}, ...]

前置条件:
    - 已安装 mineru-open-api CLI: irm https://cdn-mineru.openxlab.org.cn/open-api-cli/install.ps1 | iex
    - 已配置 Token（环境变量 MINERU_TOKEN 或 API.txt）

参考文档:
    docs/mineru-cli-guide.md
"""

import hashlib
from difflib import SequenceMatcher
import os
import re
import shutil
import subprocess
import tempfile
from urllib.parse import unquote
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config.settings import KNOWLEDGE_BASE_DIR, get_mineru_config, get_subject_images_dir, get_subject_thumbnails_dir, get_user_subject_dir, get_share_subject_dir


# ========== 默认配置 ==========

# CLI 可执行文件名称
CLI_NAME = "mineru-open-api"


def _resolve_mineru_cli_path() -> str:
    """
    跨环境解析 MinerU CLI 路径（支持开发模式 + PyInstaller 打包后）。

    查找顺序：
    1. PyInstaller _MEIPASS (运行时临时目录)
    2. PyInstaller _internal/ (单目录模式)
    3. 开发模式项目目录
    4. 用户目录 ~/.mineru/bin/
    5. 环境变量 MINERU_CLI_PATH
    6. 系统 PATH
    """
    import sys
    import shutil

    candidates = []

    # 1. PyInstaller 运行时目录 (_MEIPASS)
    if hasattr(sys, '_MEIPASS'):
        candidates.append(Path(sys._MEIPASS) / "tools" / "mineru" / f"{CLI_NAME}.exe")

    # 2. PyInstaller 单目录模式：exe 同级 _internal/
    try:
        exe_dir = Path(sys.executable).parent
        candidates.append(exe_dir / "_internal" / "tools" / "mineru" / f"{CLI_NAME}.exe")
    except Exception:
        pass

    # 3. 开发模式：项目根目录 tools/mineru/
    try:
        dev_path = Path(__file__).parent.parent / "tools" / "mineru" / f"{CLI_NAME}.exe"
        candidates.append(dev_path)
    except Exception:
        pass

    # 检查所有候选路径
    for p in candidates:
        if p.exists():
            return str(p)

    # 4. 用户目录（独立安装）
    user_dir = Path.home() / ".mineru" / "bin" / f"{CLI_NAME}.exe"
    if user_dir.exists():
        return str(user_dir)

    # 5. 环境变量
    env_path = os.environ.get("MINERU_CLI_PATH", "")
    if env_path and Path(env_path).exists():
        return env_path

    # 6. 系统 PATH
    path_cmd = shutil.which(CLI_NAME)
    if path_cmd:
        return path_cmd

    return ""


# CLI 默认路径（向后兼容）
DEFAULT_CLI_PATH = _resolve_mineru_cli_path() or r"C:\Users\lenovo\.mineru\bin\mineru-open-api.exe"


class MinerUClient:
    """
    MinerU CLI 客户端。

    封装 mineru-open-api 命令行调用，将 PDF 转换为结构化 Markdown chunk 列表。

    与 PyMuPDF 方案的区别:
    - PyMuPDF: 逐页提取纯文本，启发式标题检测，图片孤立提取
    - MinerU: 输出结构化 Markdown（含标题层级、图片引用、公式、表格）
    """

    def __init__(self, cli_path: Optional[str] = None, token: Optional[str] = None):
        """
        初始化 MinerU 客户端。

        Args:
            cli_path: CLI 可执行文件路径，None 则自动查找
            token: API Token，None 则从配置/环境变量读取
        """
        self.cli_path = cli_path or self._find_cli()
        # LA-DEPLOY-FEAT: 优先使用传入 token，其次读取功能配置
        cfg = get_mineru_config()
        self.token = token or cfg.api_key or self._load_token_from_env()
        self._version: Optional[str] = None

    # ========== CLI 查找与验证 ==========

    def _find_cli(self) -> str:
        """
        查找 mineru-open-api CLI 可执行文件。
        统一调用模块级 _resolve_mineru_cli_path()，支持开发模式 + PyInstaller 打包。
        """
        path = _resolve_mineru_cli_path()
        if path:
            return path

        raise FileNotFoundError(
            f"找不到 {CLI_NAME} CLI。\n"
            f"请访问 https://mineru.net/apiManage 下载安装，\n"
            f"或确保 tools/mineru/ 目录下有 CLI 可执行文件。"
        )

    def _load_token_from_env(self) -> str:
        """从环境变量或 API.txt 加载 Token（兼容旧配置）。"""
        token = os.environ.get("MINERU_TOKEN", "")
        if token:
            return token

        # 尝试从项目 API.txt 读取（旧格式兼容）
        api_txt = Path(__file__).parent.parent / "API.txt"
        if api_txt.exists():
            content = api_txt.read_text(encoding="utf-8")
            for line in content.split("\n"):
                if line.strip().startswith("MinerU:"):
                    return line.strip().split(":", 1)[1].strip()

        return ""

    def _run(self, args: List[str]) -> subprocess.CompletedProcess:
        """执行 CLI 命令。"""
        cmd = [self.cli_path] + args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result

    def version(self) -> str:
        """获取 CLI 版本。"""
        if self._version is None:
            result = self._run(["version"])
            self._version = result.stdout.strip() if result.returncode == 0 else "unknown"
        return self._version

    # ========== PDF 解析 ==========

    def parse_pdf(self, pdf_path: str, output_dir: Optional[str] = None, format: str = "md") -> Path:
        """
        调用 MinerU Extract 模式解析 PDF。

        Args:
            pdf_path: PDF 文件路径
            output_dir: 输出目录，None 则使用临时目录
            format: 输出格式，默认 "md"

        Returns:
            输出目录路径（包含 Markdown 文件和 images/ 目录）
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

        if not self.token:
            raise ValueError(
                "MinerU Extract 模式需要 Token。\n"
                "请在首次启动向导中配置 PDF 解析（MinerU）API Key。"
            )

        # 创建输出目录
        if output_dir is None:
            output_dir = Path(tempfile.gettempdir()) / f"mineru_{pdf_path.stem[:20]}_{hashlib.md5(str(pdf_path).encode()).hexdigest()[:8]}"
        else:
            output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 调用 CLI
        args = [
            "extract",
            str(pdf_path),
            "-o", str(output_dir),
            "-f", format,
            "--token", self.token,
        ]

        result = self._run(args)
        if result.returncode != 0:
            raise RuntimeError(
                f"MinerU CLI 执行失败 (exit={result.returncode}):\n"
                f"stderr: {result.stderr[:500]}"
            )

        return output_dir

    def parse_pdf_to_markdown(self, pdf_path: str) -> Tuple[str, Path, List[Path]]:
        """
        解析 PDF 为 Markdown 文本，返回 Markdown 内容 + 输出目录 + 图片路径列表。

        Args:
            pdf_path: PDF 文件路径

        Returns:
            (markdown_text, output_dir, image_paths)
        """
        output_dir = self.parse_pdf(pdf_path)

        # 查找 Markdown 文件（通常以 PDF 文件名命名）
        pdf_name = Path(pdf_path).stem
        md_files = list(output_dir.rglob("*.md"))

        if not md_files:
            raise FileNotFoundError(f"MinerU 输出目录中未找到 Markdown 文件: {output_dir}")

        # 优先选择以 PDF 名命名的文件，否则取第一个
        md_file = None
        for mf in md_files:
            if pdf_name.lower() in mf.stem.lower():
                md_file = mf
                break
        if md_file is None:
            md_file = md_files[0]

        markdown_text = md_file.read_text(encoding="utf-8")

        # 收集图片路径
        images_dir = output_dir / "images"
        image_paths = list(images_dir.rglob("*.jpg")) + list(images_dir.rglob("*.png")) if images_dir.exists() else []

        return markdown_text, output_dir, image_paths

    # ========== Markdown → Chunk 转换 ==========

    def parse_pdf_to_chunks(
        self,
        pdf_path: str,
        subject: str = "generic",
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        将 PDF 解析为 LearnAnything 标准 chunk 列表。

        输出格式:
            [
                {
                    "id": str,
                    "text": str,           # Markdown 文本（含图片引用、公式等）
                    "metadata": dict,      # chunk_type, heading_path, image_refs, etc.
                    "source": str,
                },
                ...
            ]

        Args:
            pdf_path: PDF 文件路径
            subject: 学科名称
            metadata: 基础元数据（source, raw_path, subject 等）

        Returns:
            标准 chunk 列表
        """
        pdf_path = Path(pdf_path)
        metadata = metadata or {}
        source_name = metadata.get("source", pdf_path.name)

        # 1. 解析 PDF 为 Markdown
        markdown_text, output_dir, image_paths = self.parse_pdf_to_markdown(str(pdf_path))

        # 2. 只复制 Markdown 实际引用的内容图片。
        # MinerU 的 images/ 目录还包含公式 OCR 裁剪等中间产物；公式已经以
        # LaTeX 写入 Markdown，再复制并交给 VLM 会造成重复识别、超时和媒体污染。
        referenced_image_paths = self._filter_markdown_referenced_images(
            markdown_text, image_paths
        )
        skipped_count = len(image_paths) - len(referenced_image_paths)
        if skipped_count:
            print(
                f"[MinerUClient] 跳过 {skipped_count} 个 Markdown 未引用的 MinerU 辅助图片，"
                f"保留 {len(referenced_image_paths)} 个内容图片"
            )
        copied_images = self._copy_images_to_kb(
            referenced_image_paths, subject, pdf_path.name, user_id=user_id
        )

        # 3. 将 Markdown 中的图片引用路径替换为本地知识库路径
        markdown_text = self._replace_image_paths(markdown_text, copied_images)

        # 3b. LA-051-DIR: 保存 Markdown 文件到学科 md/ 目录
        # 使用原始文件名（source_name）而非临时 PDF 名
        if user_id:
            md_dir = get_user_subject_dir(user_id, subject) / "md"
        else:
            md_dir = get_share_subject_dir(subject) / "md"
        md_dir.mkdir(parents=True, exist_ok=True)
        orig_name = metadata.get("source", pdf_path.name)
        md_stem = Path(orig_name).stem
        md_name = f"{md_stem}.md"
        md_path = md_dir / md_name
        # 如果文件已存在，添加序号
        counter = 1
        while md_path.exists():
            md_name = f"{md_stem}_{counter}.md"
            md_path = md_dir / md_name
            counter += 1
        self._write_markdown_atomic(md_path, markdown_text)
        print(f"[MinerUClient] Markdown saved: {md_path}")

        # 4. 按标题层级分块（使用 MarkdownChunker v2.0）
        from core.markdown_chunker import MarkdownChunker

        chunker = MarkdownChunker()
        chunks = chunker.chunk_markdown(
            markdown_text=markdown_text,
            source_metadata={**metadata, "subject": subject},
        )

        # LA-035-P21 FIX: 补充图片信息到 heading / document chunks
        # Bug 原因: _replace_image_paths 已替换 Markdown 中的图片路径为知识库路径，
        # 但 copied_images 的 key 是原始文件名（如 xxx.jpg），而 ref["path"] 已是替换后的
        # 知识库路径（如 线性代数_v1_images/xxx.png），两者不匹配导致 image_refs 被清空。
        # 修复: 建立从替换后路径到 copied_images 条目的映射，确保可追溯性。
        # 注意: Windows 路径使用反斜杠，但 Markdown 中的路径使用正斜杠，需要统一。
        path_to_info = {}
        for info in copied_images.values():
            rel_path = info["relative_path"].replace("\\", "/")
            path_to_info[rel_path] = info

        for chunk in chunks:
            if chunk["metadata"]["chunk_type"] in ("heading", "document"):
                new_refs = []
                for ref in chunk["metadata"].get("image_refs", []):
                    ref_path = ref["path"].replace("\\", "/")
                    if ref_path in path_to_info:
                        info = path_to_info[ref_path]
                        new_refs.append({
                            "type": "image",
                            "path": str(info["full_path"]),
                            "relative_path": info["relative_path"].replace("\\", "/"),
                            "thumbnail_path": info["thumbnail_path"].replace("\\", "/"),
                            "width": info["width"],
                            "height": info["height"],
                            "alt": ref.get("alt", ""),
                            "original_name": Path(info["relative_path"]).name,
                        })
                chunk["metadata"]["image_refs"] = new_refs

                # 同步更新 media_refs（供 GraphStore 使用）
                if new_refs:
                    chunk["metadata"]["media_refs"] = new_refs

        # 5. 调用 ImageConceptExtractor 生成图片概念伪文本 chunks
        # LA-035: 对含图片的 heading chunks 调用 VLM 生成描述，生成 image_pseudo chunks
        from core.image_concept_extractor import ImageConceptExtractor
        extractor = ImageConceptExtractor()

        def persist_image_rename(old_relative_path: str, new_relative_path: str) -> None:
            """Keep the saved Markdown valid even if a later VLM request is interrupted."""
            nonlocal markdown_text
            markdown_text = self._apply_image_renames(
                markdown_text,
                {old_relative_path: new_relative_path},
            )
            self._write_markdown_atomic(md_path, markdown_text)

        chunks = extractor.enrich_chunks_with_image_descriptions(
            chunks,
            subject=subject,
            rename_callback=persist_image_rename,
        )

        # LA-035-P21 FIX: 如果 Markdown 中没有图片引用，但 MinerU 提取了图片，
        # 将这些图片作为独立 image_pseudo chunks 添加到 chunks 列表中。
        # 这种情况发生在 MinerU 输出的 Markdown 中不包含图片引用时。
        has_image_refs = any(
            c["metadata"].get("image_refs", [])
            for c in chunks
            if c["metadata"]["chunk_type"] in ("heading", "document", "title")
        )

        if not has_image_refs and copied_images:
            print(f"[MinerUClient] Markdown 中无图片引用，但提取了 {len(copied_images)} 张图片，直接创建 image_pseudo chunks")
            for idx, (orig_name, info) in enumerate(copied_images.items()):
                pseudo_id = f"img_pseudo_{source_name}_{idx}_{hashlib.md5(info['relative_path'].encode()).hexdigest()[:6]}"

                # LA-035-P21: 使用 ImageConceptExtractor 的智能分析（自动检测公式图片）
                img_path = info["full_path"]
                analyze_result = extractor._describe_image_with_context(img_path, context="")

                if analyze_result:
                    text, description_source = analyze_result
                    is_formula = description_source == "vlm_formula"
                else:
                    # 回退到占位符
                    text = f"[图片] {orig_name}"
                    description_source = "placeholder"
                    is_formula = False

                anchor = self._match_image_anchor(
                    text=text,
                    is_formula=is_formula,
                    image_index=idx,
                    image_count=len(copied_images),
                    chunks=chunks,
                )
                anchor_meta = anchor.get("metadata", {}) if anchor else {}

                # 构建 media_refs
                media_refs = [{
                    "type": "image",
                    "path": str(info["full_path"]),
                    "relative_path": info["relative_path"].replace("\\", "/"),
                    "thumbnail_path": info["thumbnail_path"].replace("\\", "/"),
                    "width": info["width"],
                    "height": info["height"],
                    "alt": orig_name,
                }]

                # 如果是公式图片，额外添加 formula media_ref
                if is_formula:
                    media_refs.append({
                        "type": "formula",
                        "latex": text,
                        "display": "block" if "\n" in text else "inline",
                    })

                pseudo_chunk = {
                    "id": pseudo_id,
                    "text": f"[{'公式' if is_formula else '图片'} - {orig_name}]\n{text}",
                    "metadata": {
                        "chunk_type": "image_pseudo",
                        "source_name": source_name,
                        "source": source_name,
                        "subject": subject,
                        "heading_path": anchor_meta.get("heading_path", ""),
                        "heading_level": anchor_meta.get("heading_level", 0),
                        "parent_id": anchor.get("id") if anchor else None,
                        "page_number": anchor_meta.get(
                            "page_number", metadata.get("page_number", 0)
                        ),
                        "media_refs": media_refs,
                        "description_source": description_source,
                        "description_length": len(text),
                        "is_formula_image": is_formula,
                    },
                    "source": source_name,
                }
                chunks.append(pseudo_chunk)

        return chunks

    @staticmethod
    def _markdown_image_names(markdown_text: str) -> set[str]:
        """Return decoded basenames referenced by Markdown image syntax."""
        names: set[str] = set()
        for match in re.finditer(r'!\[[^\]]*\]\(([^)]+)\)', markdown_text):
            raw_path = match.group(1).strip().strip("<>")
            # MinerU emits plain relative paths, but decoding also handles spaces
            # escaped as %20 without changing the stored Markdown.
            path_without_query = unquote(raw_path.split("?", 1)[0].split("#", 1)[0])
            name = Path(path_without_query).name
            if name:
                names.add(name)
        return names

    @classmethod
    def _filter_markdown_referenced_images(
        cls,
        markdown_text: str,
        image_paths: List[Path],
    ) -> List[Path]:
        """Exclude MinerU auxiliary crops that are not part of the document."""
        referenced_names = cls._markdown_image_names(markdown_text)
        return [path for path in image_paths if path.name in referenced_names]

    @staticmethod
    def _apply_image_renames(markdown_text: str, rename_map: Dict[str, str]) -> str:
        """Apply knowledge-base image renames to persisted Markdown references."""
        updated = markdown_text
        for old_path, new_path in rename_map.items():
            updated = updated.replace(
                str(old_path).replace("\\", "/"),
                str(new_path).replace("\\", "/"),
            )
        return updated

    @staticmethod
    def _write_markdown_atomic(md_path: Path, markdown_text: str) -> None:
        """Atomically replace Markdown so an interrupted import cannot truncate it."""
        temp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(md_path.parent),
                prefix=f".{md_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temp_path = Path(stream.name)
                stream.write(markdown_text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, md_path)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    @staticmethod
    def _normalise_formula_text(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", (value or "").lower())

    def _match_image_anchor(
        self,
        *,
        text: str,
        is_formula: bool,
        image_index: int,
        image_count: int,
        chunks: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Find the heading/paragraph that owns an unreferenced MinerU image."""
        candidates = [
            chunk for chunk in chunks
            if chunk.get("metadata", {}).get("chunk_type") in ("heading", "paragraph")
            and chunk.get("metadata", {}).get("heading_path")
        ]
        if not candidates:
            return next(
                (c for c in chunks if c.get("metadata", {}).get("chunk_type") == "document"),
                None,
            )

        if is_formula:
            needle = self._normalise_formula_text(text)
            best = None
            best_score = 0.0
            if needle:
                for candidate in candidates:
                    haystack = self._normalise_formula_text(candidate.get("text", ""))
                    if not haystack:
                        continue
                    score = SequenceMatcher(None, needle, haystack).ratio()
                    if needle in haystack or haystack in needle:
                        score = max(score, 0.95)
                    if score > best_score:
                        best, best_score = candidate, score
            if best is not None and best_score >= 0.25:
                return best

        headings = [
            chunk for chunk in candidates
            if chunk.get("metadata", {}).get("chunk_type") == "heading"
        ]
        ordered = headings or candidates
        position = min(
            len(ordered) - 1,
            int(image_index * len(ordered) / max(image_count, 1)),
        )
        return ordered[position]

    def _copy_images_to_kb(
        self,
        image_paths: List[Path],
        subject: str,
        doc_name: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Path]:
        """
        将 MinerU 提取的图片复制到项目知识库目录。

        Returns:
            {原始文件名: 目标路径} 映射
        """
        # LA-051-DIR: 使用 settings.py 统一路径入口，传入 user_id 确保私有学科路径正确
        img_dir = get_subject_images_dir(subject, user_id)
        thumb_dir = get_subject_thumbnails_dir(subject, user_id)
        
        safe_doc_name = re.sub(r'[^\w\-_.]', '_', Path(doc_name).stem)

        from PIL import Image as PILImage

        mapping = {}
        for idx, img_path in enumerate(image_paths):
            try:
                # 读取图片
                with open(img_path, "rb") as f:
                    img_bytes = f.read()

                # 生成唯一文件名
                img_hash = hashlib.md5(img_bytes).hexdigest()[:8]
                base_name = f"{safe_doc_name}_mineru_{idx}_{img_hash}"

                # 保存为 PNG（统一格式）
                target_path = img_dir / f"{base_name}.png"
                pil_img = PILImage.open(img_path)
                if pil_img.mode in ('CMYK', 'RGBA', 'P'):
                    pil_img = pil_img.convert('RGB')
                pil_img.save(str(target_path), 'PNG')

                # 生成缩略图
                thumb_path = thumb_dir / f"{base_name}.png"
                thumb = pil_img.copy()
                thumb.thumbnail((200, 200), PILImage.LANCZOS)
                thumb.save(str(thumb_path), 'PNG')

                # 记录相对路径映射
                mapping[img_path.name] = {
                    "full_path": target_path,
                    "relative_path": str(target_path.relative_to(KNOWLEDGE_BASE_DIR)),
                    "thumbnail_path": str(thumb_path.relative_to(KNOWLEDGE_BASE_DIR)),
                    "width": pil_img.width,
                    "height": pil_img.height,
                }

            except Exception as e:
                print(f"[MinerUClient] 图片复制失败 {img_path.name}: {e}")
                continue

        return mapping

    def _replace_image_paths(self, markdown_text: str, copied_images: Dict[str, Any]) -> str:
        """
        将 Markdown 中的图片引用路径替换为知识库中的本地路径。

        MinerU 输出格式: ![image](images/xxx.jpg)
        替换为: ![image](relative/path/in/kb.png)
        """
        def replace_ref(match):
            alt_text = match.group(1)
            original_path = match.group(2)
            original_name = Path(original_path).name

            if original_name in copied_images:
                info = copied_images[original_name]
                new_path = info["relative_path"].replace("\\", "/")
                return f"![{alt_text}]({new_path})"

            # 未匹配到，保留原样
            return match.group(0)

        return re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replace_ref, markdown_text)

    def _split_markdown_to_chunks(
        self,
        markdown_text: str,
        source_name: str,
        base_metadata: Dict[str, Any],
        copied_images: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        将 Markdown 文本按标题层级分割为 chunk。

        分块策略:
        - 以 ## 二级标题为 chunk 边界（文档主要章节）
        - 每个 chunk 包含该章节下的文本、图片引用、公式、表格
        - 三级标题 ### 作为 chunk 内的子标题
        - 无标题的前言部分作为单独 chunk

        Returns:
            标准格式 chunk 列表
        """
        chunks = []

        # 按 ## 标题分割（保留标题行）
        # 匹配以 ## 开头的行，但排除 ### 等更深的标题
        pattern = r'^(#{2}\s+.*?)$'
        parts = re.split(pattern, markdown_text, flags=re.MULTILINE)

        # parts 格式: ["前言文本", "## 标题1", "内容1", "## 标题2", "内容2", ...]
        # 合并为 (标题, 内容) 对
        sections = []
        if parts[0].strip():
            sections.append(("前言", parts[0]))

        for i in range(1, len(parts), 2):
            heading = parts[i].strip() if i < len(parts) else ""
            content = parts[i + 1].strip() if i + 1 < len(parts) else ""
            sections.append((heading, content))

        # 生成 chunk
        for idx, (heading, content) in enumerate(sections):
            # 生成 chunk ID
            heading_hash = hashlib.md5(heading.encode()).hexdigest()[:6]
            chunk_id = f"md_{source_name}_{idx}_{heading_hash}"

            # 提取 heading_path（用于溯源）
            heading_path = heading.lstrip("#").strip() if heading.startswith("#") else ""

            # 提取内容中的图片引用
            image_refs = []
            for match in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', content):
                img_rel_path = match.group(2)
                # 查找对应的图片信息
                for orig_name, info in copied_images.items():
                    if info["relative_path"] in img_rel_path or img_rel_path in info["relative_path"]:
                        image_refs.append({
                            "type": "image",
                            "path": info["relative_path"],
                            "thumbnail_path": info["thumbnail_path"],
                            "width": info["width"],
                            "height": info["height"],
                        })
                        break

            # 检测公式
            formula_blocks = re.findall(r'\$\$(.*?)\$\$', content, re.DOTALL)
            inline_formulas = re.findall(r'(?<!\$)\$(?!\$)([^\$]+)\$(?!\$)', content)

            # 检测表格
            table_lines = [line for line in content.split("\n") if line.strip().startswith("|")]
            has_table = len(table_lines) >= 2

            # LA-035-P11: 修复 chunk_type 判断逻辑 - 纯图片行应标记为 image
            # 原逻辑：content.strip().replace("\n", "").replace(" ", "") 对 ![alt](path) 判断为空
            # 修复：移除 Markdown 图片语法后检查是否还有文本
            import re
            text_without_images = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', '', content).strip()
            chunk_type = "text"
            if image_refs and not text_without_images:
                chunk_type = "image"  # 纯图片行（内容只有图片引用）
                print(f"[MinerU] 纯图片 chunk: {chunk_id}, images={len(image_refs)}")
            elif image_refs and text_without_images:
                # 有图片也有文本，标记为 text_image
                chunk_type = "text_image"
                print(f"[MinerU] 图文混合 chunk: {chunk_id}, images={len(image_refs)}, text_len={len(text_without_images)}")
            elif formula_blocks or inline_formulas:
                chunk_type = "text_formula"  # 含公式
            elif has_table:
                chunk_type = "text_table"  # 含表格

            chunk = {
                "id": chunk_id,
                "text": content if content.strip() else heading,
                "metadata": {
                    **base_metadata,
                    "chunk_type": chunk_type,
                    "heading_path": heading_path,
                    "source_name": source_name,
                    "image_refs": image_refs,
                    "formula_count": len(formula_blocks) + len(inline_formulas),
                    "table_lines": len(table_lines),
                },
                "source": source_name,
            }

            # 如果有图片引用，添加图片信息到 metadata
            if image_refs:
                chunk["metadata"]["media_refs"] = image_refs

            chunks.append(chunk)

        # 调试打印 chunk 类型分布
        type_counts = {}
        for c in chunks:
            ct = c.get("metadata", {}).get("chunk_type", "unknown")
            type_counts[ct] = type_counts.get(ct, 0) + 1
        print(f"[MinerU] parse_pdf_to_chunks 返回 {len(chunks)} 个 chunks, 类型分布: {type_counts}")

        return chunks

    # ========== 便捷方法 ==========

    def is_available(self) -> bool:
        """检查 MinerU CLI 是否可用。"""
        try:
            self._find_cli()
            return True
        except FileNotFoundError:
            return False

    def has_token(self) -> bool:
        """检查是否已配置 Token。"""
        return bool(self.token)


# ========== 便捷函数 ==========

def parse_pdf_with_mineru(pdf_path: str, subject: str = "generic", metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    一键解析 PDF 为 chunk 列表（便捷函数）。

    Args:
        pdf_path: PDF 文件路径
        subject: 学科名称
        metadata: 基础元数据

    Returns:
        标准 chunk 列表
    """
    client = MinerUClient()
    return client.parse_pdf_to_chunks(pdf_path, subject=subject, metadata=metadata)
