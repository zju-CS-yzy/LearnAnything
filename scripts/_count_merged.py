import sys, re

path = r'D:\MyCS\AI\Project\LearnAnything\core\graph_store.py'
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

# Count lines with # followed by significant code patterns
code_patterns = [
    r'\s+try:',
    r'\s+except\s',
    r'\s+for\s',
    r'\s+if\s',
    r'\s+elif\s',
    r'\s+else:',
    r'\s+while\s',
    r'\s+def\s',
    r'\s+class\s',
    r'\s+with\s',
    r'\s+return',
    r'\s+"""CREATE',
    r'\s+print\(',
    r'\s+conn\s*=',
    r'\s+self\.',
]

merged = 0
for i, line in enumerate(lines):
    if '#' in line:
        for pat in code_patterns:
            # Find pattern AFTER the #
            comment_pos = line.index('#')
            after_comment = line[comment_pos:]
            if re.search(pat, after_comment):
                print(f'L{i+1}: merged comment+code')
                safe_line = line.strip()[:100].replace('\ufffd', '?').replace('\u56fe', '?')
                print(f'  {safe_line}')
                merged += 1
                break

print(f'\nTotal merged lines: {merged}')
