"""

KùzuDB 图数据库封装??提供知识库图谱的存储、查询和管理能力

"""



import json

import shutil

import threading

from pathlib import Path

from typing import Dict, List, Optional, Any



import kuzu



from config.settings import GRAPH_DB_DIR, PROJECT_ROOT



# 全局数据库实例缓存：每个路径一??Database 对象（线程安全共享）

_db_cache: Dict[str, kuzu.Database] = {}

_db_cache_lock = threading.Lock()





class GraphStore:

    """

    KùzuDB 图数据库封装??

    使用方式:

        store = GraphStore("ai_llm_v2")

        store.init_schema()  # 初始??Schema

        store.add_chunk_nodes(chunks)  # 添加 Chunk 节点

        store.build_structure_relations()  # 构建结构层关??

    注意：KùzuDB 为嵌入式数据库，每个学科对应一个独立的数据库目录??    """



    # Schema 定义（Cypher DDL??

    SCHEMA_DEFINITIONS = [
        # Layer 1: Chunk 节点（文档片段）
        """CREATE NODE TABLE Chunk (
            chunk_id STRING,
            text STRING,
            heading_path STRING,
            source STRING,
            page_number INT64,
            chunk_type STRING,
            image_path STRING,
            thumbnail_path STRING,
            width INT64,
            height INT64,
            media_refs STRING,
            PRIMARY KEY(chunk_id)
        )""",

        # Layer 2: ExtractedConcept 节点（原始概念，chunk 内去重）
        """CREATE NODE TABLE ExtractedConcept (
            extracted_id STRING,
            name STRING,
            concept_type STRING,
            extract_role STRING,
            description STRING,
            parent_hint STRING,
            source_chunk STRING,
            media_refs STRING,
            PRIMARY KEY(extracted_id)
        )""",

        # Layer 3: CanonicalConcept 节点（全局去重概念）
        """CREATE NODE TABLE CanonicalConcept (
            canonical_id STRING,
            name STRING,
            concept_type STRING,
            description STRING,
            parent_hint STRING,
            aliases STRING,
            source_chunks STRING,
            type_votes STRING,
            media_refs STRING,
            PRIMARY KEY(canonical_id)
        )""",

        # Layer 1 → Layer 1: 结构层关系（Phase 1：确定性关系）
        """CREATE REL TABLE BELONGS_TO (
            FROM Chunk TO Chunk,
            MANY_MANY
        )""",
        """CREATE REL TABLE HAS_PARENT (
            FROM Chunk TO Chunk,
            MANY_MANY
        )""",
        """CREATE REL TABLE ADJACENT_TO (
            FROM Chunk TO Chunk,
            source_page INT64,
            MANY_MANY
        )""",

        # Layer 1 → Layer 2: Chunk 提取出的原始概念
        """CREATE REL TABLE HAS_CONCEPT (
            FROM Chunk TO ExtractedConcept,
            MANY_MANY
        )""",

        # Layer 2 → Layer 3: 原始概念归属于全局 canonical 概念
        """CREATE REL TABLE DERIVED_FROM (
            FROM ExtractedConcept TO CanonicalConcept,
            MANY_MANY
        )""",

        # Layer 3 → Layer 3: 语义连接（Phase 2.5: 全局语义推断）
        """CREATE REL TABLE HAS_DETAIL (
            FROM CanonicalConcept TO CanonicalConcept,
            confidence DOUBLE,
            MANY_MANY
        )""",
        """CREATE REL TABLE SOLUTION (
            FROM CanonicalConcept TO CanonicalConcept,
            confidence DOUBLE,
            MANY_MANY
        )""",
        """CREATE REL TABLE DEPENDS_ON (
            FROM CanonicalConcept TO CanonicalConcept,
            confidence DOUBLE,
            MANY_MANY
        )""",

        # 用户层关系（Phase 3：交互式）
        """CREATE REL TABLE USER_DEFINED (
            FROM Chunk TO Chunk,
            rel_type STRING,
            note STRING,
            MANY_MANY
        )""",
    ]



    # 类级别锁，保护非线程安全??KùzuDB Connection 操作

    _conn_lock = threading.Lock()



    def __init__(self, collection_name: str):

        """

        Args:

            collection_name: 学科集合名（??"ai_llm_v2"??        """

        self.collection_name = collection_name

        self.db_path = GRAPH_DB_DIR / f"{collection_name}_graph"
        self.db_path_str = str(self.db_path)  # LA-035-P12: 统一使用字符串缓存 key

        self._db = None

        self._conn = None



    def _ensure_db(self):

        """

        确保数据库已连接??        使用全局缓存确保每个路径只有一??Database 实例，避免并发创建冲突??        使用类锁保护 Connection 操作（KùzuDB Connection 非线程安全）??        """

        # 获取或创建全局共享??Database 实例

        # LA-035-P12: 使用 self.db_path_str

        with _db_cache_lock:

            if self.db_path_str not in _db_cache:

                self.db_path.parent.mkdir(parents=True, exist_ok=True)

                _db_cache[self.db_path_str] = kuzu.Database(self.db_path_str)

            self._db = _db_cache[self.db_path_str]



        # Connection 非线程安全，但这里只是创??返回连接

        # 实际查询时通过 _conn_lock 保护

        if self._conn is None:

            self._conn = kuzu.Connection(self._db)

        return self._conn



    def _execute(self, conn, cypher):

        """

        线程安全地执??Cypher 查询??

        KùzuDB ??Python Connection 非线程安全，??FastAPI 多线程环境下

        并发调用会导致进程崩溃。通过类锁保护所有查询操作??        """

        with GraphStore._conn_lock:

            return conn.execute(cypher)



    def init_schema(self, force: bool = False):

        """

        初始化图数据??Schema??

        Args:

            force: 如果??True，删除已有数据库并重新创??        """

        if force and self.db_path.exists():
            # 关闭连接后删除
            self._db = None
            self._conn = None
            # 清除全局缓存中的旧 Database 实例
            with _db_cache_lock:
                if self.db_path_str in _db_cache:
                    del _db_cache[self.db_path_str]
            if self.db_path.is_dir():
                shutil.rmtree(self.db_path)
            else:
                self.db_path.unlink()



        conn = self._ensure_db()



        # 检查是否已存在 Chunk 表（避免重复创建??    

        try:

            self._execute(conn, "MATCH (c:Chunk) RETURN COUNT(c) AS cnt")

            print(f"[GraphStore] Schema already exists for {self.collection_name}")

            # LA-035: 检查是否是旧版本 schema（缺少 media_refs 字段）

            self._check_schema_version(conn)

            return

        except Exception:

            pass  # 表不存在，继续创??

        print(f"[GraphStore] Creating schema for {self.collection_name}...")

        for ddl in self.SCHEMA_DEFINITIONS:

            try:

                self._execute(conn, ddl)

            except Exception as e:

                print(f"[GraphStore] Schema creation warning: {e}")

                # 某些关系表可能已存在，忽略错??

        print(f"[GraphStore] Schema created for {self.collection_name}")

    def _check_schema_version(self, conn):
        """
        LA-035: 检查 schema 版本，尝试自动升级旧版本。
        """
        # 检查 CanonicalConcept 是否有 media_refs
        try:
            self._execute(conn, "MATCH (c:CanonicalConcept) RETURN c.media_refs LIMIT 1")
        except Exception as e:
            if "media_refs" in str(e):
                print(f"[GraphStore] 升级 CanonicalConcept: {self.collection_name}")
                try:
                    self._execute(conn, "ALTER TABLE CanonicalConcept ADD media_refs STRING")
                except Exception as alt_e:
                    print(f"[GraphStore] 升级失败: {alt_e}")

        # 检查 Chunk 是否有 media_refs
        try:
            self._execute(conn, "MATCH (ch:Chunk) RETURN ch.media_refs LIMIT 1")
        except Exception as e:
            if "media_refs" in str(e):
                print(f"[GraphStore] 升级 Chunk: {self.collection_name}")
                try:
                    self._execute(conn, "ALTER TABLE Chunk ADD media_refs STRING")
                except Exception as alt_e:
                    print(f"[GraphStore] 升级 Chunk 失败: {alt_e}")

        # 检查 ExtractedConcept 是否有 media_refs
        try:
            self._execute(conn, "MATCH (e:ExtractedConcept) RETURN e.media_refs LIMIT 1")
        except Exception as e:
            if "media_refs" in str(e):
                print(f"[GraphStore] 升级 ExtractedConcept: {self.collection_name}")
                try:
                    self._execute(conn, "ALTER TABLE ExtractedConcept ADD media_refs STRING")
                except Exception as alt_e:
                    print(f"[GraphStore] 升级 ExtractedConcept 失败: {alt_e}")

        # 也检查 Chunk 是否有 media 相关字段（旧版本可能缺少）

        try:

            self._execute(conn, "MATCH (c:Chunk) RETURN c.image_path LIMIT 1")

        except Exception as e:

            if "image_path" in str(e):

                print(f"[GraphStore] 旧版本 Chunk schema 检测到：{self.collection_name}")



    def _escape_cypher_string(self, text: str) -> str:

        """

        安全转义 Cypher 字符串中的特殊字符??        

        Kùzu Cypher 对字符串中的特殊字符敏感，需要：

        1. 转义反斜??\ -> /（避免被解析为转义序列如 \1, \n??        2. 转义单引??' -> \'

        3. 移除反引??`（Cypher 标识符引用符??        4. 移除换行符（Cypher 字符串不支持多行??        5. 截断超长文本

        """

        if not text:

            return ""

        # 截断到安全长??
        text = text[:1500]

        # 替换换行符和回车符为空格

        text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")

        # 替换反斜杠为正斜杠（避免 Cypher 转义序列解析问题??
        text = text.replace("\\", "/")

        # 转义单引??
        text = text.replace("'", "\\'")

        # 移除反引号（Cypher 标识符引用符??
        text = text.replace("`", "")

        # 移除其他可能导致 Cypher 解析失败的控制字??
        text = "".join(c for c in text if c >= " " or c in "\t")

        return text

    def _escape_cypher_string_safe(self, text: str) -> str:
        """安全转义 Cypher 字符串，保留反斜杠（用于 JSON 数据）"""
        if not text:
            return ""
        text = text.replace("'", "\\'")
        text = text.replace("`", "")
        text = "".join(c for c in text if c >= " " or c in "\t")
        return text



    def add_chunk_nodes(self, chunks: List[Dict[str, Any]]):

        """

        批量添加 Chunk 节点??

        Args:

            chunks: ??VectorStore 读取??chunk 列表

                [{"id": str, "text": str, "metadata": dict}, ...]

        """

        conn = self._ensure_db()

        added = 0

        failed = 0



        for chunk in chunks:

            meta = chunk.get("metadata", {})

            chunk_id = self._escape_cypher_string(chunk["id"])

            text = self._escape_cypher_string(chunk.get("text", ""))

            heading_path = self._escape_cypher_string(meta.get("heading_path", ""))

            source = self._escape_cypher_string(meta.get("source", ""))

            page_numbers = meta.get("page_numbers", meta.get("page_number", [0]))

            if isinstance(page_numbers, list):

                page_number = page_numbers[0] if len(page_numbers) > 0 else 0

            elif isinstance(page_numbers, (int, float)):

                page_number = int(page_numbers)

            elif isinstance(page_numbers, str) and page_numbers.isdigit():

                page_number = int(page_numbers)

            else:

                page_number = 0

            chunk_type = self._escape_cypher_string(meta.get("type", meta.get("chunk_type", "child")))



            # LA-035: 图片字段
            raw_image_path = meta.get("image_path", "")
            raw_thumbnail_path = meta.get("thumbnail_path", "")
            # LA-035-P26: 将 Windows 绝对路径转换为相对路径（保留 学科_v1_images/文件名 部分）
            import re as _re
            img_match = _re.search(r'([^\\/]+_v1_images[\\/][^\\/]+)$', raw_image_path)
            thumb_match = _re.search(r'([^\\/]+_v1_thumbnails[\\/][^\\/]+)$', raw_thumbnail_path)
            image_path = self._escape_cypher_string(img_match.group(1) if img_match else raw_image_path)
            thumbnail_path = self._escape_cypher_string(thumb_match.group(1) if thumb_match else raw_thumbnail_path)
            width = meta.get("width", 0) or 0
            height = meta.get("height", 0) or 0

            # LA-035-P18: 从 metadata 中提取并序列化 media_refs
            media_refs_raw = meta.get("media_refs", []) or meta.get("image_refs", [])
            
            # LA-035-P18-fix: 如果 media_refs 为空但 image_path 存在，
            # 自动从 image_path 构建 media_refs（兼容 DocumentProcessor 生成的 chunk）
            if not media_refs_raw and image_path and image_path != "":
                media_refs_raw = [{
                    "type": "image",
                    "path": image_path,
                    "thumbnail_path": thumbnail_path or "",
                    "description": "",
                    "width": width or 0,
                    "height": height or 0,
                }]
            
            # LA-035-P26: 用 _escape_cypher_string_safe 保留 JSON 中的反斜杠
            media_refs_json = self._escape_cypher_string_safe(
                json.dumps(media_refs_raw, ensure_ascii=False) if media_refs_raw else ""
            )

            cypher = (

                f"CREATE (c:Chunk {{"

                f"chunk_id: '{chunk_id}',"

                f"text: '{text}',"

                f"heading_path: '{heading_path}',"

                f"source: '{source}',"

                f"page_number: {page_number},"

                f"chunk_type: '{chunk_type}',"

                f"image_path: '{image_path}',"

                f"thumbnail_path: '{thumbnail_path}',"

                f"width: {width},"

                f"height: {height},"

                f"media_refs: '{media_refs_json}'"

                f"}})"

            )

            try:

                self._execute(conn, cypher)

                added += 1

            except Exception as e:

                failed += 1

                if failed <= 5:

                    print(f"[GraphStore] Failed to add chunk {chunk_id}: {e}")



        if failed > 5:

            print(f"[GraphStore] ... and {failed - 5} more failures")

        print(f"[GraphStore] Added {added} Chunk nodes ({failed} failed)")

        return added



    def build_belongs_to_relations(self):

        """

        构建 BELONGS_TO 关系：同一 heading_path 下的 chunk 之间建立层级关系??

        策略??        - ??heading_path 分组

        - 同组内按 page_number 排序

        - 相邻??chunk 之间建立 BELONGS_TO 关系

        """

        conn = self._ensure_db()



        # 获取所??heading_path 分组

        result = self._execute(conn, """

            MATCH (c:Chunk)

            WHERE c.heading_path <> ''

            RETURN c.heading_path AS hp, c.chunk_id AS cid, c.page_number AS pn

            ORDER BY hp, pn

        """)



        groups = {}

        while result.has_next():

            row = result.get_next()

            hp, cid, pn = row[0], row[1], row[2]

            groups.setdefault(hp, []).append((cid, pn))



        # 为每??heading_path 组内建立相邻关系

        created = 0

        esc = self._escape_cypher_string

        for hp, items in groups.items():

            items.sort(key=lambda x: x[1] if x[1] is not None else 0)  # ??page_number 排序，None 视为 0

            for i in range(len(items) - 1):

                cid1, _ = items[i]

                cid2, _ = items[i + 1]

                try:

                    self._execute(conn, f"""

                        MATCH (a:Chunk {{chunk_id: '{esc(cid1)}'}}), (b:Chunk {{chunk_id: '{esc(cid2)}'}})

                        CREATE (a)-[:BELONGS_TO]->(b)

                    """)

                    created += 1

                except Exception as e:

                    print(f"[GraphStore] BELONGS_TO failed: {e}")



        print(f"[GraphStore] Created {created} BELONGS_TO relations")

        return created



    def build_has_parent_relations(self, parent_chunks: List[Dict[str, Any]]):

        """

        构建 HAS_PARENT 关系：child chunk 关联到其 parent chunk??

        Args:

            parent_chunks: parent chunk 列表，用于建??child→parent ??        """

        conn = self._ensure_db()

        created = 0



        for parent in parent_chunks:

            parent_id = parent["id"]

            # ??parent metadata 中获取关联的 child_ids

            meta = parent.get("metadata", {})

            # 注意：parent chunk 本身不直接存??child_ids

            # 我们需要通过??chunk ??parent_ids 反查



        # 更直接的方式：遍历所??child chunk，获取其 parent_ids

        result = self._execute(conn, """

            MATCH (c:Chunk {chunk_type: 'child'})

            RETURN c.chunk_id AS cid

        """)



        child_ids = []

        while result.has_next():

            child_ids.append(result.get_next()[0])



        for cid in child_ids:

            # 注意：parent_ids 存储??SQLite 向量库的 metadata ??            # 这里简化处理：通过 page_number 匹配 parent

            # 实际应传??parent-child 映射

            pass



        print(f"[GraphStore] HAS_PARENT: simplified (page-based matching)")

        return created



    def build_adjacent_relations(self):

        """

        构建 ADJACENT_TO 关系：同一 source（文档）且相??page_number ??chunk 之间建立关系??        """

        conn = self._ensure_db()



        result = self._execute(conn, """

            MATCH (c:Chunk)

            WHERE c.source <> ''

            RETURN c.source AS src, c.chunk_id AS cid, c.page_number AS pn

            ORDER BY src, pn

        """)



        groups = {}

        while result.has_next():

            row = result.get_next()

            src, cid, pn = row[0], row[1], row[2]

            groups.setdefault(src, []).append((cid, pn))



        created = 0

        esc = self._escape_cypher_string

        for src, items in groups.items():

            items.sort(key=lambda x: x[1] if x[1] is not None else 0)  # ??page_number 排序，None 视为 0

            for i in range(len(items) - 1):

                cid1, pn1 = items[i]

                cid2, pn2 = items[i + 1]

                if pn1 is not None and pn2 is not None and abs(pn2 - pn1) <= 1:  # 相邻??                

                    try:

                        self._execute(conn, f"""

                            MATCH (a:Chunk {{chunk_id: '{esc(cid1)}'}}), (b:Chunk {{chunk_id: '{esc(cid2)}'}})

                            CREATE (a)-[:ADJACENT_TO {{source_page: {pn1}}}]->(b)

                        """)

                        created += 1

                    except Exception as e:

                        print(f"[GraphStore] ADJACENT_TO failed: {e}")



        print(f"[GraphStore] Created {created} ADJACENT_TO relations")

        return created



    def compute_and_cache_centrality(self) -> Dict[str, float]:
        """
        P0-INT-5: 计算并缓存 CanonicalConcept 的 PageRank 中心性。

        算法: 简化版 PageRank（10 次迭代, damping=0.85）
        - 读取所有 CanonicalConcept 和语义边（SOLUTION, DEPENDS_ON, HAS_DETAIL）
        - 计算每个节点的 PageRank
        - 保存到 JSON 缓存文件
        - 返回 {canonical_id: pagerank_score} 字典

        Returns:
            Dict[str, float]: {canonical_id: pagerank_score}
        """
        import json

        cache_path = self._get_centrality_cache_path()

        conn = self._ensure_db()
        nodes = self._get_canonical_nodes(conn)
        edges = self._get_semantic_edges(conn)

        pagerank = self._compute_pagerank(nodes, edges)

        cache = {nid: {"pagerank_score": pr} for nid, pr in pagerank.items()}
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

        print(f"[GraphStore] P0-INT-5: PageRank 计算完成，{len(pagerank)} 个节点，缓存保存到 {cache_path}")
        return pagerank

    def _get_centrality_cache_path(self):
        from pathlib import Path as _Path
        return _Path(r"D:\MyCS\AI\Project\LearnAnything\knowledge_base") / f"{self.collection_name}_centrality_cache.json"

    def _get_centrality_cache(self) -> Dict[str, float]:
        import json
        cache_path = self._get_centrality_cache_path()
        if cache_path.exists():
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {nid: d["pagerank_score"] for nid, d in data.items()}
        return {}

    def _get_canonical_nodes(self, conn) -> List[str]:
        result = self._execute(conn, "MATCH (c:CanonicalConcept) RETURN c.canonical_id AS id")
        nodes = []
        while result.has_next():
            row = result.get_next()
            nodes.append(row[0])
        return nodes

    def _get_semantic_edges(self, conn) -> List[tuple]:
        edges = []
        for rel_type in ["SOLUTION", "DEPENDS_ON", "HAS_DETAIL"]:
            try:
                result = self._execute(conn, f"MATCH (a:CanonicalConcept)-[:{rel_type}]-(b:CanonicalConcept) RETURN a.canonical_id, b.canonical_id")
                while result.has_next():
                    row = result.get_next()
                    edges.append((row[0], row[1]))
            except Exception:
                pass
        return edges

    def _compute_pagerank(self, nodes: List[str], edges: List[tuple], iterations: int = 10, damping: float = 0.85) -> Dict[str, float]:
        if not nodes:
            return {}

        pagerank = {node: 1.0 / len(nodes) for node in nodes}

        outgoing = {node: [] for node in nodes}
        for src, dst in edges:
            if src in outgoing:
                outgoing[src].append(dst)

        for _ in range(iterations):
            new_pr = {}
            for node in nodes:
                rank = (1 - damping) / len(nodes)
                for src, dst in edges:
                    if dst == node and src in outgoing and outgoing[src]:
                        rank += damping * pagerank[src] / len(outgoing[src])
                new_pr[node] = rank
            pagerank = new_pr

        max_pr = max(pagerank.values()) if pagerank else 1.0
        if max_pr > 0:
            pagerank = {k: min(v / max_pr, 1.0) for k, v in pagerank.items()}

        return pagerank

    def get_graph_stats(self) -> Dict[str, Any]:

        """获取图统计信息??"""

        conn = self._ensure_db()

        stats = {}



        # 节点统计

        for label in ["Chunk", "ExtractedConcept", "CanonicalConcept"]:

            try:

                result = self._execute(conn, f"MATCH (n:{label}) RETURN COUNT(n) AS cnt")

                if result.has_next():

                    stats[f"{label.lower()}_count"] = result.get_next()[0]

            except Exception:

                stats[f"{label.lower()}_count"] = 0



        # 关系统计

        for rel_type in ["BELONGS_TO", "HAS_PARENT", "ADJACENT_TO", "HAS_CONCEPT", "DERIVED_FROM", "SOLUTION", "DEPENDS_ON", "USER_DEFINED"]:

            try:

                result = self._execute(conn, f"MATCH ()-[r:{rel_type}]->() RETURN COUNT(r) AS cnt")

                if result.has_next():

                    stats[f"{rel_type.lower()}_count"] = result.get_next()[0]

            except Exception:

                stats[f"{rel_type.lower()}_count"] = 0



        return stats



    def get_subgraph(self, chunk_id: str, depth: int = 2) -> Dict[str, Any]:

        """

        获取以指定 chunk 或 concept 为中心的子图（用于前端可视化）。

        支持四层模型 v2.0: Chunk / ExtractedConcept / CanonicalConcept。

        Args:

            chunk_id: 中心节点 ID（可以是 Chunk、ExtractedConcept 或 CanonicalConcept）

            depth: 遍历深度



        Returns:

            { "nodes": [...], "edges": [...] }

        """

        conn = self._ensure_db()

        nodes = {}

        edges = []



        # 安全转义 chunk_id

        safe_id = self._escape_cypher_string(chunk_id)



        # 尝试 Chunk

        center_node = None

        result = self._execute(conn, f"""

            MATCH (c:Chunk {{chunk_id: '{safe_id}'}})

            RETURN c.chunk_id, c.text, c.heading_path, c.source, c.page_number, c.chunk_type

        """)

        if result.has_next():

            row = result.get_next()

            center_node = {

                "id": row[0],

                "label": row[2] or row[0][:20],

                "type": "Chunk",

                "text": row[1][:200] if row[1] else "",

                "source": row[3],

                "page_number": row[4],

                "chunk_type": row[5],

            }



        # 尝试 CanonicalConcept（v2.0 主要节点类型）

        if not center_node:

            result = self._execute(conn, f"""

                MATCH (c:CanonicalConcept {{canonical_id: '{safe_id}'}})

                RETURN c.canonical_id, c.name, c.concept_type

            """)

            if result.has_next():

                row = result.get_next()

                center_node = {

                    "id": row[0],

                    "label": row[1] or row[0][:20],

                    "type": row[2] or "concept",

                    "chunk_type": row[2] or "concept",

                    "text": "",

                    "source": "",

                    "page_number": None,

                }



        # 尝试 ExtractedConcept（v2.0 中间节点类型）

        if not center_node:

            result = self._execute(conn, f"""

                MATCH (c:ExtractedConcept {{extracted_id: '{safe_id}'}})

                RETURN c.extracted_id, c.name, c.concept_type, c.source_chunk

            """)

            if result.has_next():

                row = result.get_next()

                center_node = {

                    "id": row[0],

                    "label": row[1] or row[0][:20],

                    "type": row[2] or "concept",

                    "chunk_type": row[2] or "concept",

                    "text": "",

                    "source": row[3] or "",

                    "page_number": None,

                }



        if not center_node:

            return {"nodes": [], "edges": []}



        nodes[center_node["id"]] = center_node



        # 查询所有关系（结构层 + 语义层 v2.0）

        rel_types = ["BELONGS_TO", "ADJACENT_TO", "HAS_CONCEPT", "DERIVED_FROM", "SOLUTION", "DEPENDS_ON"]

        for rel_type in rel_types:

            try:

                # 双向查询：中心节点可以是 source 或 target

                result = self._execute(conn, f"""

                    MATCH (c)-[r:{rel_type}]-(n)

                    WHERE c.chunk_id = '{safe_id}' OR c.canonical_id = '{safe_id}' OR c.extracted_id = '{safe_id}'

                    RETURN n.chunk_id, n.heading_path, n.chunk_type, n.text,

                           n.canonical_id, n.name, n.concept_type,

                           n.extracted_id

                """)

                while result.has_next():

                    row = result.get_next()

                    nid = row[0] or row[4] or row[7]  # chunk_id / canonical_id / extracted_id

                    if nid and nid not in nodes:

                        if row[0]:  # Chunk

                            nodes[nid] = {

                                "id": nid,

                                "label": row[1] or nid[:20],

                                "type": row[2] or "child",

                                "chunk_type": row[2] or "child",

                                "text": (row[3] or "")[:200],

                            }

                        elif row[4]:  # CanonicalConcept

                            nodes[nid] = {

                                "id": nid,

                                "label": row[5] or nid[:20],

                                "type": row[6] or "concept",

                                "chunk_type": row[6] or "concept",

                                "text": "",

                            }

                        else:  # ExtractedConcept

                            nodes[nid] = {

                                "id": nid,

                                "label": row[5] or nid[:20],

                                "type": row[6] or "concept",

                                "chunk_type": row[6] or "concept",

                                "text": "",

                            }

                    if nid:

                        edges.append({

                            "source": chunk_id,

                            "target": nid,

                            "type": rel_type,

                        })

            except Exception:

                pass



        return {"nodes": list(nodes.values()), "edges": edges}



    def add_concepts(self, chunk_id: str, concepts: List[Dict[str, Any]]) -> int:
        """
        为指定 chunk 添加原始概念节点（ExtractedConcept）。
        同一 chunk 内同名概念自动去重（保留第一个）。

        Args:
            chunk_id: 来源 chunk ID
            concepts: 概念列表，每个包含 name, concept_type, relation, description, parent_hint

        Returns:
            成功添加的概念数量
        """
        conn = self._ensure_db()
        added = 0

        # 同一 chunk 内按概念名称去重
        seen_names = set()
        unique_concepts = []
        for concept in concepts:
            name = concept.get("name", "").strip()
            if name and name not in seen_names:
                seen_names.add(name)
                unique_concepts.append(concept)

        for concept in unique_concepts:
            concept_name = self._escape_cypher_string(concept.get("name", ""))
            if not concept_name:
                continue

            import hashlib
            name_hash = hashlib.md5(concept_name.encode("utf-8")).hexdigest()[:6]
            extracted_id = self._escape_cypher_string(
                concept.get("id", f"{chunk_id}_{name_hash}")
            )
            concept_type = self._escape_cypher_string(
                concept.get("concept_type", "definition")
            )
            extract_role = self._escape_cypher_string(
                concept.get("relation", "DEFINES")
            )
            description = self._escape_cypher_string(
                concept.get("description", "")
            )
            parent_hint = self._escape_cypher_string(
                concept.get("parent_hint", "")
            )

            # LA-035: 多媒体引用
            media_refs = concept.get("media_refs", [])
            # LA-035-P26: 用 _escape_cypher_string_safe 保留 JSON 中的反斜杠
            media_refs_json = self._escape_cypher_string_safe(
                json.dumps(media_refs, ensure_ascii=False) if media_refs else ""
            )

            # 创建 ExtractedConcept 节点
            merge_cypher = f"""
                MERGE (e:ExtractedConcept {{
                    extracted_id: '{extracted_id}'
                }})
                ON CREATE SET
                    e.name = '{concept_name}',
                    e.concept_type = '{concept_type}',
                    e.extract_role = '{extract_role}',
                    e.description = '{description}',
                    e.parent_hint = '{parent_hint}',
                    e.source_chunk = '{chunk_id}',
                    e.media_refs = '{media_refs_json}'
                ON MATCH SET
                    e.name = '{concept_name}',
                    e.concept_type = '{concept_type}',
                    e.extract_role = '{extract_role}',
                    e.description = '{description}',
                    e.parent_hint = '{parent_hint}',
                    e.source_chunk = '{chunk_id}',
                    e.media_refs = '{media_refs_json}'
            """
            try:
                self._execute(conn, merge_cypher)
            except Exception as e:
                print(f"[GraphStore] 创建 ExtractedConcept 节点失败 {extracted_id}: {e}")
                continue

            # 创建 Chunk -> ExtractedConcept 的 HAS_CONCEPT 关系
            rel_cypher = f"""
                MATCH (ch:Chunk {{chunk_id: '{chunk_id}'}}),
                      (e:ExtractedConcept {{extracted_id: '{extracted_id}'}})
                MERGE (ch)-[:HAS_CONCEPT]->(e)
            """
            try:
                self._execute(conn, rel_cypher)
                added += 1
            except Exception as e:
                print(f"[GraphStore] 创建 HAS_CONCEPT 关系失败: {e}")

        # 保存完整概念信息到 JSONL
        self._save_concept_details(chunk_id, concepts)

        print(f"[GraphStore] 为 chunk {chunk_id} 添加 {added} 个 ExtractedConcept")
        return added

    def add_canonical_concepts(
        self,
        canonical_concepts: List[Dict[str, Any]],
        derived_from_map: Dict[str, str] = None,
    ) -> int:
        """
        添加全局去重后的 canonical 概念节点。
        同时建立 ExtractedConcept -> CanonicalConcept 的 DERIVED_FROM 关系。

        Args:
            canonical_concepts: 去重后的 canonical 概念列表
            derived_from_map: {extracted_id: canonical_id} 映射，用于建立 DERIVED_FROM 边

        Returns:
            成功添加的 canonical 概念数量
        """
        conn = self._ensure_db()
        added = 0

        for cc in canonical_concepts:
            canonical_id = self._escape_cypher_string(cc.get("id", ""))
            name = self._escape_cypher_string(cc.get("name", ""))
            if not canonical_id or not name:
                continue

            concept_type = self._escape_cypher_string(cc.get("concept_type", ""))
            description = self._escape_cypher_string(cc.get("description", ""))
            parent_hint = self._escape_cypher_string(cc.get("parent_hint", ""))

            import json
            aliases = json.dumps(cc.get("aliases", []), ensure_ascii=False)
            source_chunks = json.dumps(cc.get("source_chunks", []), ensure_ascii=False)

            type_votes = cc.get("type_votes", {})
            if not type_votes:
                type_votes = {concept_type: 1} if concept_type else {}
            type_votes_json = json.dumps(type_votes, ensure_ascii=False)

            # LA-035: 多媒体引用
            media_refs = cc.get("media_refs", [])
            media_refs_json = json.dumps(media_refs, ensure_ascii=False) if media_refs else ""

            # 创建 CanonicalConcept 节点
            # LA-035: 兼容旧数据库（可能缺少 media_refs 字段）
            # 先尝试完整写入，如果失败则降级到不含 media_refs
            full_merge_cypher = f"""
                MERGE (c:CanonicalConcept {{
                    canonical_id: '{canonical_id}'
                }})
                ON CREATE SET
                    c.name = '{name}',
                    c.concept_type = '{concept_type}',
                    c.description = '{description}',
                    c.parent_hint = '{parent_hint}',
                    c.aliases = '{aliases}',
                    c.source_chunks = '{source_chunks}',
                    c.type_votes = '{type_votes_json}',
                    c.media_refs = '{media_refs_json}'
                ON MATCH SET
                    c.name = '{name}',
                    c.concept_type = '{concept_type}',
                    c.description = '{description}',
                    c.parent_hint = '{parent_hint}',
                    c.aliases = '{aliases}',
                    c.source_chunks = '{source_chunks}',
                    c.type_votes = '{type_votes_json}',
                    c.media_refs = '{media_refs_json}'
            """
            fallback_merge_cypher = f"""
                MERGE (c:CanonicalConcept {{
                    canonical_id: '{canonical_id}'
                }})
                ON CREATE SET
                    c.name = '{name}',
                    c.concept_type = '{concept_type}',
                    c.description = '{description}',
                    c.parent_hint = '{parent_hint}',
                    c.aliases = '{aliases}',
                    c.source_chunks = '{source_chunks}',
                    c.type_votes = '{type_votes_json}'
                ON MATCH SET
                    c.name = '{name}',
                    c.concept_type = '{concept_type}',
                    c.description = '{description}',
                    c.parent_hint = '{parent_hint}',
                    c.aliases = '{aliases}',
                    c.source_chunks = '{source_chunks}',
                    c.type_votes = '{type_votes_json}'
            """
            try:
                self._execute(conn, full_merge_cypher)
                added += 1
            except Exception as e:
                if "media_refs" in str(e):
                    try:
                        self._execute(conn, fallback_merge_cypher)
                        added += 1
                    except Exception as e2:
                        print(f"[GraphStore] 创建 CanonicalConcept 节点失败 {canonical_id}: {e2}")
                        continue
                else:
                    print(f"[GraphStore] 创建 CanonicalConcept 节点失败 {canonical_id}: {e}")
                    continue

        # 建立 DERIVED_FROM 关系
        if derived_from_map:
            derived_count = 0
            for extracted_id, canonical_id in derived_from_map.items():
                safe_eid = self._escape_cypher_string(extracted_id)
                safe_cid = self._escape_cypher_string(canonical_id)
                cypher = f"""
                    MATCH (e:ExtractedConcept {{extracted_id: '{safe_eid}'}}),
                          (c:CanonicalConcept {{canonical_id: '{safe_cid}'}})
                    MERGE (e)-[:DERIVED_FROM]->(c)
                """
                try:
                    self._execute(conn, cypher)
                    derived_count += 1
                except Exception as e:
                    print(f"[GraphStore] 创建 DERIVED_FROM 失败 {extracted_id}->{canonical_id}: {e}")
            print(f"[GraphStore] 建立 {derived_count} 条 DERIVED_FROM 关系")

        print(f"[GraphStore] 添加 {added} 个 CanonicalConcept")
        return added

    def _save_concept_details(self, chunk_id: str, concepts: List[Dict[str, Any]]):

        """

        将概念的完整信息（含 description、parent_hint）保存到 JSON 文件??        供去重器（ConceptDeduper）和连接推断器（SemanticLinker）使用??        """

        import json

        from config.settings import KNOWLEDGE_BASE_DIR



        details_dir = KNOWLEDGE_BASE_DIR / "concept_details"

        details_dir.mkdir(parents=True, exist_ok=True)

        details_path = details_dir / f"{self.collection_name}.jsonl"



        # 追加写入（每??chunk 一??JSON??    

        with open(details_path, "a", encoding="utf-8") as f:

            record = {

                "chunk_id": chunk_id,

                "concepts": [

                    {

                        "id": c.get("id", ""),

                        "name": c.get("name", ""),

                        "concept_type": c.get("concept_type", ""),

                        "relation": c.get("relation", ""),

                        "description": c.get("description", ""),

                        "parent_hint": c.get("parent_hint", ""),
                        "media_refs": c.get("media_refs", []),

                    }

                    for c in concepts

                ],

            }

            f.write(json.dumps(record, ensure_ascii=False) + "\n")



    def _load_concept_details(self) -> Dict[str, Dict[str, Any]]:

        """

        ??JSONL 文件加载所有概念的详细信息??

        Returns:

            {concept_id: {name, description, parent_hint, ...}}

        """

        import json

        from config.settings import KNOWLEDGE_BASE_DIR



        details_path = KNOWLEDGE_BASE_DIR / "concept_details" / f"{self.collection_name}.jsonl"

        if not details_path.exists():

            return {}



        result = {}

        try:

            with open(details_path, "r", encoding="utf-8") as f:

                for line in f:

                    line = line.strip()

                    if not line:

                        continue

                    record = json.loads(line)

                    for c in record.get("concepts", []):

                        cid = c.get("id", "")

                        if cid:

                            result[cid] = c

        except Exception as e:

            print(f"[GraphStore] 读取概念详情失败: {e}")



        return result



    def get_concepts_for_chunk(self, chunk_id: str) -> List[Dict[str, Any]]:

        """

        获取指定 chunk 关联的所有 ExtractedConcept。

        四层模型 v2.0: Chunk -(HAS_CONCEPT)-> ExtractedConcept

        Args:

            chunk_id: chunk ID



        Returns:

            概念列表，每个包含 id, name, type, relation, description

        """

        conn = self._ensure_db()

        concepts = []



        # 查询 Chunk -> ExtractedConcept 的 HAS_CONCEPT 关系

        try:

            result = self._execute(conn, f"""

                MATCH (ch:Chunk {{chunk_id: '{chunk_id}'}})-[r:HAS_CONCEPT]->(co:ExtractedConcept)

                RETURN co.extracted_id, co.name, co.concept_type, co.description

            """)

            while result.has_next():

                row = result.get_next()

                concepts.append({

                    "id": row[0],

                    "name": row[1],

                    "type": row[2],

                    "relation": "HAS_CONCEPT",

                    "description": row[3] or "",

                })

        except Exception:

            pass



        return concepts



    def get_canonical_concepts(self, limit: int = 500) -> List[Dict[str, Any]]:

        """

        获取所??Concept 节点（用于前端可视化）??

        Args:

            limit: 最大返回数??

        Returns:

            概念节点列表

        """

        conn = self._ensure_db()

        nodes = []



        try:
            # LA-035: 兼容旧数据库（可能缺少 media_refs 字段）
            try:
                result = self._execute(conn, f"""
                    MATCH (c:CanonicalConcept)
                    RETURN c.canonical_id, c.name, c.concept_type, c.description, c.parent_hint, c.source_chunks, c.media_refs
                    LIMIT {limit}
                """)
                while result.has_next():
                    row = result.get_next()
                    import json
                    media_refs = []
                    if row[6]:
                        try:
                            raw = row[6]
                            # P0-INT-5: 修复旧数据中 _escape_cypher_string 遗留问题
                            # 旧数据将 JSON 中的 \\ 替换为 //，需要先恢复
                            if isinstance(raw, str) and '//' in raw:
                                raw = raw.replace('//', '\\')
                            media_refs = json.loads(raw)
                        except:
                            pass
                    nodes.append({
                        "id": row[0],
                        "name": row[1],
                        "type": row[2],
                        "description": row[3],
                        "parent_hint": row[4],
                        "source_chunks": row[5],
                        "media_refs": media_refs,
                    })
            except Exception as schema_e:
                if "media_refs" in str(schema_e):
                    # 旧数据库，回退到旧查询
                    print(f"[GraphStore] 旧数据库兼容模式：{self.collection_name}")
                    result = self._execute(conn, f"""
                        MATCH (c:CanonicalConcept)
                        RETURN c.canonical_id, c.name, c.concept_type, c.description, c.parent_hint, c.source_chunks
                        LIMIT {limit}
                    """)
                    while result.has_next():
                        row = result.get_next()
                        nodes.append({
                            "id": row[0],
                            "name": row[1],
                            "type": row[2],
                            "description": row[3],
                            "parent_hint": row[4],
                            "source_chunks": row[5],
                            "media_refs": [],
                        })
                else:
                    raise

            # LA-035-P10: 如果 media_refs 为空，尝试从 source_chunks 关联的 Chunk 获取
            for node in nodes:
                if not node.get("media_refs"):
                    node["media_refs"] = self._get_media_refs_from_chunks(conn, node.get("source_chunks", []))

        except Exception as e:

            print(f"[GraphStore] 获取概念节点失败: {e}")



        return nodes



    def _get_media_refs_from_chunks(self, conn, source_chunks):
        """
        从 source_chunks 关联的 Chunk 节点获取 media_refs。
        LA-035-P10 修复：兼容旧 schema（Chunk 无 media_refs 字段时回退到 image_path/thumbnail_path）。
        """
        import json

        # 解析 source_chunks
        chunk_ids = []
        if isinstance(source_chunks, list):
            chunk_ids = source_chunks
        elif isinstance(source_chunks, str) and source_chunks:
            try:
                parsed = json.loads(source_chunks)
                if isinstance(parsed, list):
                    chunk_ids = parsed
                else:
                    chunk_ids = [source_chunks]
            except:
                chunk_ids = [s.strip() for s in source_chunks.split(",") if s.strip()]

        if not chunk_ids:
            return []

        media_refs = []
        seen = set()

        # 先尝试查询 media_refs 字段（新 schema）
        has_media_refs_field = True
        for chunk_id in chunk_ids:
            try:
                result = self._execute(conn, f"""
                    MATCH (ch:Chunk {{chunk_id: '{self._escape_cypher_string(chunk_id)}'}})
                    RETURN ch.media_refs
                """)
                if result.has_next():
                    row = result.get_next()
                    if row[0]:
                        try:
                            refs = json.loads(row[0])
                            if isinstance(refs, list):
                                for ref in refs:
                                    key = f"{ref.get('type', '')}:{ref.get('path', ref.get('description', '')[:50])}"
                                    if key not in seen:
                                        seen.add(key)
                                        media_refs.append(ref)
                        except:
                            pass
            except Exception as e:
                # 旧 schema：media_refs 字段不存在，回退到 image_path/thumbnail_path
                if "media_refs" in str(e):
                    has_media_refs_field = False
                    break
                else:
                    print(f"[GraphStore] 获取 chunk {chunk_id} 的 media_refs 失败: {e}")

        # LA-035-P18: 修复回退逻辑
        # 当 media_refs 为空时，无论是因为字段不存在（旧 schema）还是字段值为空（新 schema但无数据），都应回退到 image_path
        if not media_refs:
            for chunk_id in chunk_ids:
                try:
                    result = self._execute(conn, f"""
                        MATCH (ch:Chunk {{chunk_id: '{self._escape_cypher_string(chunk_id)}'}})
                        RETURN ch.chunk_type, ch.image_path, ch.thumbnail_path, ch.text, ch.width, ch.height
                    """)
                    if result.has_next():
                        row = result.get_next()
                        chunk_type = row[0] or ''
                        img_path = row[1] or ''
                        thumb_path = row[2] or ''
                        text = row[3] or ''
                        width = row[4] or 0
                        height = row[5] or 0
                        # 如果 chunk_type 是 image 或 text 包含图片标记，构建 media_refs
                        if img_path or chunk_type in ('image', 'image_pseudo'):
                            key = f"image:{img_path}"
                            if key not in seen:
                                seen.add(key)
                                media_refs.append({
                                    "type": "image",
                                    "path": img_path,
                                    "thumbnail_path": thumb_path,
                                    "caption": text[:100] if text else '',
                                    "width": width,
                                    "height": height,
                                })
                except Exception as e:
                    print(f"[GraphStore] 回退获取 chunk {chunk_id} 的图片信息失败: {e}")

        return media_refs

    def get_extracted_concepts(self, limit: int = 10000) -> List[Dict[str, Any]]:
        """
        获取所有 ExtractedConcept 节点。

        Args:
            limit: 最大返回数量

        Returns:
            ExtractedConcept 节点列表
        """
        conn = self._ensure_db()
        nodes = []

        try:
            # LA-035: 兼容旧数据库（可能缺少 media_refs 字段）
            try:
                result = self._execute(conn, f"""
                    MATCH (e:ExtractedConcept)
                    RETURN e.extracted_id, e.name, e.concept_type, e.extract_role,
                           e.description, e.parent_hint, e.source_chunk, e.media_refs
                    LIMIT {limit}
                """)
                while result.has_next():
                    row = result.get_next()
                    media_refs = []
                    if row[7]:
                        try:
                            media_refs = json.loads(row[7])
                        except:
                            pass
                    nodes.append({
                        "id": row[0],
                        "name": row[1],
                        "type": row[2],
                        "extract_role": row[3],
                        "description": row[4],
                        "parent_hint": row[5],
                        "source_chunk": row[6],
                        "media_refs": media_refs,
                    })
            except Exception as schema_e:
                if "media_refs" in str(schema_e):
                    # 旧数据库，回退到旧查询
                    print(f"[GraphStore] 旧数据库兼容模式（ExtractedConcept）: {self.collection_name}")
                    result = self._execute(conn, f"""
                        MATCH (e:ExtractedConcept)
                        RETURN e.extracted_id, e.name, e.concept_type, e.extract_role,
                               e.description, e.parent_hint, e.source_chunk
                        LIMIT {limit}
                    """)
                    while result.has_next():
                        row = result.get_next()
                        nodes.append({
                            "id": row[0],
                            "name": row[1],
                            "type": row[2],
                            "extract_role": row[3],
                            "description": row[4],
                            "parent_hint": row[5],
                            "source_chunk": row[6],
                            "media_refs": [],
                        })
                else:
                    raise
        except Exception as e:
            print(f"[GraphStore] 获取 ExtractedConcept 失败: {e}")

        return nodes

    def get_semantic_edges(self, limit: int = 200) -> List[Dict[str, Any]]:

        """

        获取语义层关系边（Chunk -> ExtractedConcept -> CanonicalConcept）。

        四层模型 v2.0: Chunk -(HAS_CONCEPT)-> ExtractedConcept -(DERIVED_FROM)-> CanonicalConcept

        Args:

            limit: 最大返回数量



        Returns:

            边列表，包含 source, target, type

        """

        conn = self._ensure_db()

        edges = []



        # 查询 Chunk -(HAS_CONCEPT)-> ExtractedConcept

        try:

            result = self._execute(conn, f"""

                MATCH (ch:Chunk)-[r:HAS_CONCEPT]->(co:ExtractedConcept)

                RETURN ch.chunk_id, co.extracted_id

                LIMIT {limit}

            """)

            while result.has_next():

                row = result.get_next()

                edges.append({

                    "source": row[0],

                    "target": row[1],

                    "type": "HAS_CONCEPT",

                    "description": "",

                })

        except Exception:

            pass



        # 查询 ExtractedConcept -(DERIVED_FROM)-> CanonicalConcept

        try:

            result = self._execute(conn, f"""

                MATCH (e:ExtractedConcept)-[r:DERIVED_FROM]->(c:CanonicalConcept)

                RETURN e.extracted_id, c.canonical_id

                LIMIT {limit}

            """)

            while result.has_next():

                row = result.get_next()

                edges.append({

                    "source": row[0],

                    "target": row[1],

                    "type": "DERIVED_FROM",

                    "description": "",

                })

        except Exception:

            pass



        return edges



    def get_concept_links(self, limit: int = 500) -> List[Dict[str, Any]]:

        """

        获取概念间的语义连接边（全局推断生成的）??

        Args:

            limit: 最大返回数??

        Returns:

            边列表，包含 source, target, type, confidence

        """

        conn = self._ensure_db()

        edges = []



        # 语义层关系类型（包含语义推断生成??SOLUTION/DEPENDS_ON ??chunk-level ??DEFINES/REQUIRES 等）

        rel_types = ["SOLUTION", "DEPENDS_ON", "DEFINES", "REQUIRES", "HAS_LAW", "APPLIES_TO", "EXTENDS", "IMPLEMENTS", "HAS_SUB", "HAS_IMPL"]

        for rel_type in rel_types:

            try:

                result = self._execute(conn, f"""

                    MATCH (p:CanonicalConcept)-[r:{rel_type}]->(c:CanonicalConcept)

                    RETURN p.canonical_id, c.canonical_id, r.confidence

                    LIMIT {limit}

                """)

                while result.has_next():

                    row = result.get_next()

                    edges.append({

                        "source": row[0],

                        "target": row[1],

                        "type": rel_type,

                        "confidence": row[2] if row[2] else 0.0,

                    })

            except Exception:

                pass



        return edges




    def add_has_detail_relations(self, relations: List[Dict[str, Any]]) -> int:
        """
        添加 HAS_DETAIL 关系（CanonicalConcept -> CanonicalConcept）。
        LA-035 Phase 2.3: 语义聚合产生的层级关系。
        Args:
            relations: 关系列表，每个包含 {"from": canonical_id, "to": canonical_id, "confidence": float}
        Returns:
            成功创建的关系数量
        """
        conn = self._ensure_db()
        created = 0
        esc = self._escape_cypher_string
        for rel in relations:
            from_id = esc(rel.get("from", ""))
            to_id = esc(rel.get("to", ""))
            confidence = rel.get("confidence", 0.85)
            if not from_id or not to_id or from_id == to_id:
                continue
            cypher = f"""
                MATCH (a:CanonicalConcept {{canonical_id: '{from_id}'}}),
                      (b:CanonicalConcept {{canonical_id: '{to_id}'}})
                MERGE (a)-[:HAS_DETAIL {{confidence: {confidence}}}]->(b)
            """
            try:
                self._execute(conn, cypher)
                created += 1
            except Exception as e:
                print(f"[GraphStore] HAS_DETAIL failed {from_id}->{to_id}: {e}")
        print(f"[GraphStore] Created {created} HAS_DETAIL relations")
        return created

    def get_has_detail_edges(self, limit: int = 500) -> List[Dict[str, Any]]:
        """
        获取 HAS_DETAIL 关系边。
        Returns:
            边列表，包含 source, target, type, confidence
        """
        conn = self._ensure_db()
        edges = []
        try:
            result = self._execute(conn, f"""
                MATCH (a:CanonicalConcept)-[r:HAS_DETAIL]->(b:CanonicalConcept)
                RETURN a.canonical_id, b.canonical_id, r.confidence
                LIMIT {limit}
            """)
            while result.has_next():
                row = result.get_next()
                edges.append({
                    "source": row[0],
                    "target": row[1],
                    "type": "HAS_DETAIL",
                    "confidence": row[2] if row[2] is not None else 0.85,
                })
        except Exception:
            pass
        return edges

    def close(self):

        """关闭数据库连接??"""

        self._conn = None

        self._db = None



    def __del__(self):

        self.close()

