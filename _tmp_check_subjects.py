import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")
from core.subject_manager import list_subjects
for s in list_subjects():
    print(f"ID: {s['id']}")
    print(f"Doc count: {s.get('document_count', 0)}")
    print(f"Raw files: {s.get('raw_files_count', 0)}")
    print("---")
