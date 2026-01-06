#!/usr/bin/env python3
# 文件名: mr_mapper.py
import sys
import json
import jieba

jieba.setLogLevel(20)

for line in sys.stdin:
    try:
        line = line.strip()
        if not line: continue
        
        doc = json.loads(line)
        doc_id = str(doc['id'])
        
        content = doc.get('title', '') + " " + doc.get('full_text', '')
        if 'images' in doc:
            for img in doc['images']:
                content += " " + img.get('caption', '')
        
        # ✅ 【修复点】立即转为 list，防止生成器耗尽
        words = list(jieba.cut_for_search(content)) 
        
        # 任务 A: 构建倒排索引
        for w in words:
            w = w.strip()
            if len(w) > 1:
                print(f"INDEX\t{w}\t{doc_id}")
        
        # 任务 B: 构建 PageRank 图
        if 'outlinks' in doc:
            for link in doc['outlinks']:
                target_url = link.get('url')
                if target_url:
                    print(f"LINK\t{doc_id}\t{target_url}")
        
        # 任务 C: 传递文档基础信息
        # ✅ 【修复点】现在 len(words) 能取到正确长度了
        doc_len = len(words) 
        print(f"DOCINFO\t{doc_id}\t{doc.get('url','')}\t{doc_len}")

    except Exception as e:
        continue