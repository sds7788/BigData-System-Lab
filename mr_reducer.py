#!/usr/bin/env python3
# 文件名: mr_reducer.py
import sys
from collections import defaultdict

# 缓存数据
index_map = defaultdict(lambda: defaultdict(int)) # word -> {doc_id: count}
link_map = defaultdict(list)    # doc_id -> [target_urls]
doc_info_map = {}               # doc_id -> url

for line in sys.stdin:
    try:
        parts = line.strip().split('\t')
        tag = parts[0]
        
        if tag == 'INDEX':
            # INDEX \t word \t doc_id
            if len(parts) < 3: continue
            word, doc_id = parts[1], parts[2]
            index_map[word][doc_id] += 1
            
        elif tag == 'LINK':
            # LINK \t src_id \t target_url
            if len(parts) < 3: continue
            src_id, target_url = parts[1], parts[2]
            link_map[src_id].append(target_url)
            
        elif tag == 'DOCINFO':
            # DOCINFO \t doc_id \t url \t length
            if len(parts) < 3: continue
            doc_id, url = parts[1], parts[2]
            length = int(parts[3]) if len(parts) > 3 else 0
            doc_info_map[doc_id] = {"url": url, "len": length}
            
    except: continue

# --- 输出阶段 ---

# 1. 输出倒排索引 (JSON 格式化字符串，方便 Driver 解析)
# 输出格式: RESULT_INDEX \t word \t {"doc1": 2, "doc2": 1}
for word, postings in index_map.items():
    # 简单的 JSON 序列化
    postings_str = "{" + ",".join([f'"{k}":{v}' for k,v in postings.items()]) + "}"
    print(f"RESULT_INDEX\t{word}\t{postings_str}")

# 2. 输出图结构和文档信息
# 输出格式: RESULT_GRAPH \t doc_id \t url \t length \t [target_url1, target_url2...]
for doc_id, info in doc_info_map.items():
    url = info['url']
    length = info['len']
    outlinks = link_map.get(doc_id, [])
    # 简单的列表序列化
    outlinks_str = "[" + ",".join([f'"{lnk}"' for lnk in outlinks]) + "]"
    print(f"RESULT_GRAPH\t{doc_id}\t{url}\t{length}\t{outlinks_str}")