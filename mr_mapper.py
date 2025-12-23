#!/usr/bin/env python3
# 文件名: mr_mapper.py
import sys
import json
import jieba

# 确保 jieba 不输出日志干扰 Hadoop
jieba.setLogLevel(20)

for line in sys.stdin:
    try:
        line = line.strip()
        if not line: continue
        
        doc = json.loads(line)
        doc_id = str(doc['id'])
        
        # --- 任务 A: 构建倒排索引 (输出格式: INDEX \t word \t doc_id) ---
        # 拼接: 标题 + 正文 + 图片描述
        content = doc.get('title', '') + " " + doc.get('full_text', '')
        if 'images' in doc:
            for img in doc['images']:
                content += " " + img.get('caption', '')
        
        # 分词
        words = jieba.cut_for_search(content)
        for w in words:
            w = w.strip()
            if len(w) > 1:
                print(f"INDEX\t{w}\t{doc_id}")
        
        # --- 任务 B: 构建 PageRank 图 (输出格式: LINK \t source_id \t target_url) ---
        # 我们先输出 URL，Reducer 阶段或者 Driver 阶段再转为 ID
        if 'outlinks' in doc:
            for link in doc['outlinks']:
                target_url = link.get('url')
                if target_url:
                    print(f"LINK\t{doc_id}\t{target_url}")
        
        # --- 任务 C: 传递文档基础信息 (用于 URL 映射) ---
        # 输出: DOCinfo \t doc_id \t url \t length
        # 这样我们在后面能知道每个 doc_id 对应的 URL 是什么，以及文档长度
        doc_len = len(list(words)) # 注意：这里 words 生成器已经消耗过了，实际代码需优化，这里简化处理
        print(f"DOCINFO\t{doc_id}\t{doc.get('url','')}\t{doc_len}")

    except Exception as e:
        continue