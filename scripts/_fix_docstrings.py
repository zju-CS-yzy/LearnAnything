import re

path = r'D:\MyCS\AI\Project\LearnAnything\core\graph_store.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find all docstrings that might have missing closing quote
# Pattern: """..."" (only 2 closing quotes instead of 3)
# Look for lines with """ start and "" end
lines = content.split('\r\n')

fixed = 0
for i, line in enumerate(lines):
    # Check if line starts with spaces + """ and ends with "" (not """)
    stripped = line.lstrip()
    if stripped.startswith('"""') and not stripped.endswith('"""') and stripped.endswith('""'):
        # Check if it's likely a docstring (has Chinese chars or ASCII text inside)
        inner = stripped[3:-2]  # Content between """ and ""
        if len(inner) > 0 and not inner.startswith('CREATE') and not inner.startswith('MATCH'):
            lines[i] = line + '"'
            print(f'L{i+1}: fixed docstring: {lines[i]!r}')
            fixed += 1

print(f'Fixed {fixed} docstrings')

new_content = '\r\n'.join(lines)
with open(path, 'w', encoding='utf-8') as f:
    f.write(new_content)
