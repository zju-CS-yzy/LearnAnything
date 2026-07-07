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

        self._db = None

        self._conn = None



    def _ensure_db(self):

        """

        确保数据库已连接??        使用全局缓存确保每个路径只有一??Database 实例，避免并发创建冲突??        使用类锁保护 Connection 操作（KùzuDB Connection 非线程安全）??        """

        # 获取或创建全局共享??Database 实例

        db_path_str = str(self.db_path)

        with _db_cache_lock:

            if db_path_str not in _db_cache:

                self.db_path.parent.mkdir(parents=True, exist_ok=True)

                _db_cache[db_path_str] = kuzu.Database(db_path_str)

            self._db = _db_cache[db_path_str]



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

            # 关闭连接后删??            self._db = None

            self._conn = None

            if self.db_path.is_dir():

                shutil.rmtree(self.db_path)

            else:

                self.db_path.unlink()



        conn = self._ensure_db()



        # 检查是否已存在 Chunk 表（避免重复创建??    

        try:

            self._execute(conn, "MATCH (c:Chunk) RETURN COUNT(c) AS cnt")

            print(f"[GraphStore] Schema already exists for {self.collection_name}")

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



            cypher = (

                f"CREATE (c:Chunk {{"

                f"chunk_id: '{chunk_id}',"

                f"text: '{text}',"

                f"heading_path: '{heading_path}',"

                f"source: '{source}',"

                f"page_number: {page_number},"

                f"chunk_type: '{chunk_type}'"

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

        获取以指??chunk ??concept 为中心的子图（用于前端可视化）??

        Args:

            chunk_id: 中心节点 ID（可以是 Chunk ??Concept??            depth: 遍历深度



        Returns:

            { "nodes": [...], "edges": [...] }

        """

        conn = self._ensure_db()

        nodes = {}

        edges = []



        # 安全转义 chunk_id

        safe_id = self._escape_cypher_string(chunk_id)



        # 先尝试作??Chunk 查询，如果没有结果则作为 Concept 查询

        center_node = None



        # 尝试 Chunk

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



        # 如果未找到，尝试 Concept

        if not center_node:

            result = self._execute(conn, f"""

                MATCH (c:Concept {{concept_id: '{safe_id}'}})

                RETURN c.concept_id, c.name, c.concept_type, c.source_chunk

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



        # 查询所有结构层关系（BELONGS_TO, ADJACENT_TO）和语义层关系（DEFINES, REQUIRES 等）

        rel_types = ["BELONGS_TO", "ADJACENT_TO", "DEFINES", "REQUIRES", "HAS_LAW", "APPLIES_TO", "EXTENDS", "IMPLEMENTS", "HAS_SUB", "HAS_IMPL"]

        for rel_type in rel_types:

            try:

                result = self._execute(conn, f"""

                    MATCH (c)-[r:{rel_type}]-(n)

                    WHERE c.chunk_id = '{safe_id}' OR c.concept_id = '{safe_id}'

                    RETURN n.chunk_id, n.heading_path, n.chunk_type, n.text, n.concept_id, n.name, n.concept_type

                """)

                while result.has_next():

                    row = result.get_next()

                    nid = row[0] or row[4]  # chunk_id ??concept_id

                    if nid and nid not in nodes:

                        if row[0]:  # Chunk

                            nodes[nid] = {

                                "id": nid,

                                "label": row[1] or nid[:20],

                                "type": row[2] or "child",

                                "chunk_type": row[2] or "child",

                                "text": (row[3] or "")[:200],

                            }

                        else:  # Concept

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



    # ========== Phase 2: 语义????概念操作 ==========



    def add_concepts(self, chunk_id: str, concepts: List[Dict[str, Any]]) -> int:

        """

        为指??chunk 添加概念节点和语义关系??        同一 chunk 内同名概念自动去重（保留第一个）??

        Args:

            chunk_id: 来源 chunk ID

            concepts: 概念列表，每个包??name, concept_type, relation, description



        Returns:

            成功添加的概念数??        """

        conn = self._ensure_db()

        added = 0



        # 同一 chunk 内按概念名称去重（保留第一个出现的??
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



            concept_id = self._escape_cypher_string(concept.get("id", f"concept_{chunk_id}_{concept_name}"))

            concept_type = self._escape_cypher_string(concept.get("concept_type", "definition"))

            relation = self._escape_cypher_string(concept.get("relation", "DEFINES"))

            description = self._escape_cypher_string(concept.get("description", ""))



            # 1. 创建或合??Concept 节点

            merge_cypher = f"""

                MERGE (c:Concept {{

                    concept_id: '{concept_id}',

                    name: '{concept_name}',

                    concept_type: '{concept_type}',

                    source_chunk: '{chunk_id}'

                }})

            """

            try:

                self._execute(conn, merge_cypher)

            except Exception as e:

                print(f"[GraphStore] 创建概念节点失败 {concept_id}: {e}")

                continue



            # 2. 创建 Chunk -> Concept 的语义关??
            rel_cypher = f"""

                MATCH (ch:Chunk {{chunk_id: '{chunk_id}'}}), (co:Concept {{concept_id: '{concept_id}'}})

                CREATE (ch)-[:{relation}]->(co)

            """

            try:

                self._execute(conn, rel_cypher)

                added += 1

            except Exception as e:

                print(f"[GraphStore] 创建关系失败 {relation}: {e}")



        # 3. 将完整概念信息保存到 JSON（供去重器和连接器使用）

        self._save_concept_details(chunk_id, concepts)



        print(f"[GraphStore] ??chunk {chunk_id} 添加 {added} 个概??")

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

        获取指定 chunk 关联的所有概念??

        Args:

            chunk_id: chunk ID



        Returns:

            概念列表，每个包??id, name, type, relation, description

        """

        conn = self._ensure_db()

        concepts = []



        # 查询所有语义层关系（DEFINES, HAS_LAW, APPLIES_TO, EXTENDS??
        rel_types = ["DEFINES", "HAS_LAW", "APPLIES_TO", "EXTENDS", "REQUIRES", "IMPLEMENTS", "HAS_SUB", "HAS_IMPL"]

        for rel_type in rel_types:

            try:

                result = self._execute(conn, f"""

                    MATCH (ch:Chunk {{chunk_id: '{chunk_id}'}})-[r:{rel_type}]->(co:Concept)

                    RETURN co.concept_id, co.name, co.concept_type, co.description

                """)

                while result.has_next():

                    row = result.get_next()

                    concepts.append({

                        "id": row[0],

                        "name": row[1],

                        "type": row[2],

                        "relation": rel_type,

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

            result = self._execute(conn, f"""

                MATCH (c:CanonicalConcept)

                RETURN c.canonical_id, c.name, c.concept_type, c.source_chunks

                LIMIT {limit}

            """)

            while result.has_next():

                row = result.get_next()

                nodes.append({

                    "id": row[0],

                    "name": row[1],

                    "type": row[2],

                    "source_chunk": row[3],

                })

        except Exception as e:

            print(f"[GraphStore] 获取概念节点失败: {e}")



        return nodes



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
                })
        except Exception as e:
            print(f"[GraphStore] 获取 ExtractedConcept 失败: {e}")

        return nodes

    def get_semantic_edges(self, limit: int = 200) -> List[Dict[str, Any]]:

        """

        获取语义层关系边（Chunk -> Concept）??

        Args:

            limit: 最大返回数??

        Returns:

            边列表，包含 source, target, type

        """

        conn = self._ensure_db()

        edges = []



        rel_types = ["DEFINES", "HAS_LAW", "APPLIES_TO", "EXTENDS"]

        for rel_type in rel_types:

            try:

                result = self._execute(conn, f"""

                    MATCH (ch:Chunk)-[r:{rel_type}]->(co:Concept)

                    RETURN ch.chunk_id, co.concept_id, r.description

                    LIMIT {limit}

                """)

                while result.has_next():

                    row = result.get_next()

                    edges.append({

                        "source": row[0],

                        "target": row[1],

                        "type": rel_type,

                        "description": row[2] if row[2] else "",

                    })

            except Exception:

                pass



        return edges



    def get_semantic_edges(self, limit: int = 200) -> List[Dict[str, Any]]:

        """

        获取语义层关系边（Chunk -> Concept）??

        Args:

            limit: 最大返回数??

        Returns:

            边列表，包含 source, target, type

        """

        conn = self._ensure_db()

        edges = []



        rel_types = ["DEFINES", "HAS_LAW", "APPLIES_TO", "EXTENDS"]

        for rel_type in rel_types:

            try:

                result = self._execute(conn, f"""

                    MATCH (ch:Chunk)-[r:{rel_type}]->(co:Concept)

                    RETURN ch.chunk_id, co.concept_id, r.description

                    LIMIT {limit}

                """)

                while result.has_next():

                    row = result.get_next()

                    edges.append({

                        "source": row[0],

                        "target": row[1],

                        "type": rel_type,

                        "description": row[2] if row[2] else "",

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

                    RETURN p.concept_id, c.concept_id, r.confidence

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



    def close(self):

        """关闭数据库连接??"""

        self._conn = None

        self._db = None



    def __del__(self):

        self.close()

