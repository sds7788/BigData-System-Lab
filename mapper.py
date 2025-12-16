#!/usr/bin/env python3
import sys
import json
import jieba

# 从标准输入读取 (Hadoop 会把文件行传进来)
for line in sys.stdin:
    try:
        line = line.strip()
        if not line: continue
        
        # 解析 JSONL 中的一行
        doc = json.loads(line)
        doc_id = doc['id']
        text = doc.get('title', '') + " " + doc.get('full_text', '')
        
        # 分词
        words = jieba.cut_for_search(text)
        for w in words:
            if len(w.strip()) > 1:
                # 输出: 关键词 \t 文档ID
                print(f"{w.strip()}\t{doc_id}")
    except:
        pass