#!/usr/bin/env python3
"""
测试 buildUMLCardLabel 对各种输入的输出
模拟前端 JavaScript 逻辑
"""
import json
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from fastapi.testclient import TestClient
from app.backend_api import app

client = TestClient(app)

# 获取所有概念
resp = client.get('/api/knowledge-graph/generic/concepts?limit=2000')
concepts = resp.json().get('concepts', [])

# 模拟 buildUMLCardLabel
def get_type_label(t):
    mapping = {
        'requirement': '【需求】',
        'sub_requirement': '【子需求】',
        'technology': '【技术】',
        'sub_technology': '【子技术】',
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
    
    fixed_lines = 5
    desc_line_count = max(len(desc_lines), 1)
    total_lines = fixed_lines + desc_line_count - 1
    line_height = 16
    padding = 36
    card_height = max(80, total_lines * line_height + padding)
    
    return card_label, card_height

# 分析每个概念的 cardLabel
issues = []
for c in concepts:
    name = c.get('name', '')
    ctype = c.get('type', 'concept')
    desc = c.get('description', '')
    
    card_label, card_height = build_uml_card_label(name, ctype, desc)
    
    # 检查潜在问题
    problems = []
    if not name.strip():
        problems.append("name为空")
    if len(name) > 12:
        problems.append(f"name被截断({len(name)}->12)")
    if not desc.strip():
        problems.append("desc为空")
    if '【概念】' in card_label and ctype not in ['concept', '']:
        problems.append(f"类型'{ctype}'被映射为【概念】")
    if '\n' not in card_label:
        problems.append("无换行符")
    
    if problems:
        issues.append({
            'id': c['id'],
            'name': name,
            'type': ctype,
            'problems': problems,
            'card_label_preview': card_label[:100].replace('\n', '\\n'),
            'card_height': card_height,
        })

print(f"总概念数: {len(concepts)}")
print(f"有问题概念数: {len(issues)}")

if issues:
    print("\n问题详情 (前20个):")
    for issue in issues[:20]:
        print(f"  {issue['id']}: name='{issue['name']}' type='{issue['type']}'")
        print(f"    问题: {', '.join(issue['problems'])}")
        print(f"    cardLabel: {issue['card_label_preview']}")
else:
    print("\n未发现明显问题!")
    # 打印一些样本看看cardLabel长什么样
    print("\n样本cardLabel (前3个):")
    for c in concepts[:3]:
        card_label, _ = build_uml_card_label(c['name'], c['type'], c['description'])
        print(f"  {c['name']}:")
        for line in card_label.split('\n'):
            print(f"    | {line}")
