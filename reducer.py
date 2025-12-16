#!/usr/bin/env python3
import sys
from collections import defaultdict

current_word = None
doc_counts = defaultdict(int)

for line in sys.stdin:
    try:
        word, doc_id = line.strip().split('\t')
        
        if current_word == word:
            doc_counts[doc_id] += 1
        else:
            if current_word:
                # 输出旧词的结果: word \t doc1:3,doc2:1
                postings = ",".join([f"{k}:{v}" for k,v in doc_counts.items()])
                print(f"{current_word}\t{postings}")
            
            current_word = word
            doc_counts = defaultdict(int)
            doc_counts[doc_id] += 1
    except:
        pass

# 输出最后一个词
if current_word:
    postings = ",".join([f"{k}:{v}" for k,v in doc_counts.items()])
    print(f"{current_word}\t{postings}")