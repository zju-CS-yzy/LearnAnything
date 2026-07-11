#!/usr/bin/env python3
"""
检查 cardLabel 中的特殊字符
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")
from fastapi.testclient import TestClient
from app.backend_api import app

client = TestClient(app)
resp = client.get('/api/knowledge-graph/generic/concepts?limit=2000')
concepts = resp.json().get('concepts', [])

def get_type_label(t):
    mapping = {
        'requirement': '【需求】', 'sub_requirement': '【子需求】',
        'technology': '【技术】', 'sub_technology': '【子技术】',
        'concept': '【概念】',
    }
    return mapping.get(t, '【概念】')

def build_uml_card_label(name, ctype, description):
    type_label = get_type_label(ctype)
    title = name[:12]
    desc = description or ''
    desc_lines = [desc[i:i+15] for i in range(0, len(desc), 15)]
    desc_text = '\n'.join(desc_lines)
    card_label = f"{title}\n━━━━━━\n{type_label}\n━━━━━━\n{desc_text}"
    return card_label

# 检查特殊字符
special_chars_found = []
for c in concepts:
    card_label = build_uml_card_label(c['name'], c['type'], c['description'])
    
    # 检查是否有非 BMP 字符、控制字符等
    for ch in card_label:
        code = ord(ch)
        if code > 0xFFFF:  # 非 BMP
            special_chars_found.append((c['id'], c['name'], ch, f'U+{code:04X}'))
        elif code < 0x20 and code not in (0x09, 0x0A, 0x0D):  # 控制字符
            special_chars_found.append((c['id'], c['name'], ch, f'U+{code:04X}'))

print(f"总概念数: {len(concepts)}")
print(f"含特殊字符数: {len(special_chars_found)}")

# 检查分隔线字符
separator = '━'
for c in concepts[:5]:
    card_label = build_uml_card_label(c['name'], c['type'], c['description'])
    has_sep = separator in card_label
    print(f"  {c['name']}: has_separator={has_sep}, card_label_lines={card_label.count(chr(10))}")

# 输出几个 cardLabel 样本到文件
with open(r"D:\MyCS\AI\Project\LearnAnything\scripts\cardlabel_samples.txt", "w", encoding="utf-8") as f:
    for c in concepts[:10]:
        card_label = build_uml_card_label(c['name'], c['type'], c['description'])
        f.write(f"=== {c['name']} ===\n")
        f.write(card_label)
        f.write("\n\n")
print("Samples written to cardlabel_samples.txt")
