#!/usr/bin/env python3
"""
修复 graph_store.py 中 v2.0 Schema 不兼容的函数
按行号替换，绕过乱码字符问题
"""

filepath = r"D:\MyCS\AI\Project\LearnAnything\core\graph_store.py"

with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 找到关键行号
subgraph_start = None
concepts_start = None
semantic_start = None

for i, line in enumerate(lines):
    if 'def get_subgraph(self, chunk_id: str' in line:
        subgraph_start = i
    elif 'def get_concepts_for_chunk(self, chunk_id: str' in line:
        concepts_start = i
    elif 'def get_semantic_edges(self, limit: int' in line:
        if semantic_start is None:
            semantic_start = i

print(f"get_subgraph at line {subgraph_start}")
print(f"get_concepts_for_chunk at line {concepts_start}")
print(f"get_semantic_edges at line {semantic_start}")

# 找到每个函数的结束行（下一个 def 或类方法的结束）
def find_func_end(start_idx, lines):
    """找到函数在下一个 def/类 之前结束的位置"""
    for i in range(start_idx + 1, len(lines)):
        if lines[i].strip().startswith('def ') or lines[i].strip().startswith('class ') or lines[i].strip() == '#':
            # 回退到上一个非空行
            j = i - 1
            while j > start_idx and lines[j].strip() == '':
                j -= 1
            return j + 1  # 不包含的结束索引
    return len(lines)

subgraph_end = find_func_end(subgraph_start, lines)
concepts_end = find_func_end(concepts_start, lines)
semantic_end = find_func_end(semantic_start, lines)

print(f"get_subgraph lines: {subgraph_start}-{subgraph_end-1}")
print(f"get_concepts_for_chunk lines: {concepts_start}-{concepts_end-1}")
print(f"get_semantic_edges lines: {semantic_start}-{semantic_end-1}")

# 新函数定义
new_subgraph = '''    def get_subgraph(self, chunk_id: str, depth: int = 2) -> Dict[str, Any]:

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

                           n.extracted_id, n.extracted_name

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

                                "label": row[8] or nid[:20],

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
'''

new_concepts = '''    def get_concepts_for_chunk(self, chunk_id: str) -> List[Dict[str, Any]]:

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
'''

new_semantic = '''    def get_semantic_edges(self, limit: int = 200) -> List[Dict[str, Any]]:

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
'''

# 替换：保留 subgraph 之前的所有内容，替换 subgraph，然后保留中间内容，替换 concepts，等等
new_lines = (
    lines[:subgraph_start] + 
    [new_subgraph] + 
    lines[subgraph_end:concepts_start] + 
    [new_concepts] + 
    lines[concepts_end:semantic_start] + 
    [new_semantic] + 
    lines[semantic_end:]
)

with open(filepath, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("All fixes applied by line replacement")
