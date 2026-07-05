import json, os, glob, requests

text_dir = r"D:\MyCS\AI\Project\IWork\yuque_download\pdf_texts"
os.chdir(text_dir)
json_files = [f for f in glob.glob("*.json") if f not in ["all_pdf_texts.json", "analyze_pdf_quality.py", "identify_garbled_pdfs.py"]]
print(f"Found {len(json_files)} text JSON files")

url = "http://127.0.0.1:5001/api/import/text"
total_chunks = 0

# Upload first 5 files
for json_file in json_files[:5]:
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        chunks = data.get("text_chunks", [])
        if not chunks:
            print(f"[{json_file}] No chunks, skipping")
            continue
            
        # Combine all chunks into one text
        full_text = "\n\n".join([c.get("text", "") for c in chunks])
        source_name = data.get("original_name", json_file.replace(".json", ".pdf"))
        
        body = {
            "subject": "generic",
            "text": full_text,
            "source_name": source_name
        }
        
        resp = requests.post(url, json=body, timeout=300)
        result = resp.json()
        
        added = result.get("chunks_added", 0)
        total_chunks += added
        print(f"[{source_name}] Added {added} chunks (status: {resp.status_code})")
        
    except Exception as e:
        print(f"[{json_file}] Error: {e}")

print(f"\nTotal chunks added: {total_chunks}")
