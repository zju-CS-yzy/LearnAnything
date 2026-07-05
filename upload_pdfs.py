import requests, os, glob, json

pdf_dir = r"D:\MyCS\AI\Project\IWork\yuque_download\pdfs"
os.chdir(pdf_dir)
pdf_files = glob.glob("*.pdf")
print(f"Found {len(pdf_files)} PDF files")

# Upload first 3 small PDFs (< 5MB)
small_pdfs = [f for f in pdf_files if os.path.getsize(f) < 5*1024*1024][:3]
print(f"Uploading {len(small_pdfs)} small PDFs:")
for f in small_pdfs:
    print(f"  - {f} ({os.path.getsize(f)//1024}KB)")

url = "http://127.0.0.1:5001/api/import/file"
for pdf_file in small_pdfs:
    file_path = os.path.join(pdf_dir, pdf_file)
    try:
        with open(file_path, 'rb') as f:
            files = {'files': (pdf_file, f, 'application/pdf')}
            data = {'subject': 'generic'}
            resp = requests.post(url, data=data, files=files, timeout=300)
        print(f"[{pdf_file}] Status: {resp.status_code}")
        result = resp.json()
        if result.get('success_count', 0) > 0:
            print(f"  OK: {result['results'][0].get('message', '')}")
        else:
            print(f"  FAIL: {result['results'][0].get('message', '')}")
    except Exception as e:
        print(f"  ERROR: {e}")
