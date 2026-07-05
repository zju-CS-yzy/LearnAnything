path = r'D:\MyCS\AI\Project\LearnAnything\core\graph_store.py'
with open(path, 'rb') as f:
    raw = f.read()

crlf = raw.count(b'\r\n')
lf = raw.count(b'\n') - crlf
print(f'CRLF: {crlf}')
print(f'LF: {lf}')

# If mixed, standardize to CRLF
if crlf > 0 and lf > 0:
    print('Mixed newlines detected! Standardizing to CRLF...')
    # Replace standalone LF with CRLF, but avoid double CRLF
    raw = raw.replace(b'\r\n', b'\n')  # First normalize to LF
    raw = raw.replace(b'\n', b'\r\n')  # Then convert to CRLF
    with open(path, 'wb') as f:
        f.write(raw)
    print('Standardized to CRLF')
