import json
from datetime import datetime

def generate_jsonl_entry(doc_data):
    #生成JSONL格式的数据条目
    entry = {
        "id": doc_data.get('id', ''),
        "title": doc_data.get('title', '未命名文档'),
        "type": doc_data.get('file_type', 'pdf'),
        "url": doc_data.get('source_website', ''),
        "full_text": doc_data.get('full_text', ''),
    }

    return json.dumps(entry, ensure_ascii=False)