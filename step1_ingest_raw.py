# -*- coding: utf-8 -*-
# 文件名: step1_ingest_raw.py
import happybase
import json
import os
import sys

HBASE_HOST = '127.0.0.1'
TABLE_DOCS = 'ustc_docs'
TABLE_INDEX = 'ustc_index'
RAW_FILE = os.path.join('output', 'documents.jsonl')

def connect_hbase():
    return happybase.Connection(HBASE_HOST, port=9090, timeout=20000, autoconnect=True)

def init_tables(connection):
    print(">>> [Step 1] 初始化 HBase 表结构...")
    tables = connection.tables()
    
    # 1. 文档表: info(原始信息), alg(后续计算的算法数据)
    if TABLE_DOCS.encode() in tables:
        print(f"   重建表 {TABLE_DOCS}...")
        connection.disable_table(TABLE_DOCS)
        connection.delete_table(TABLE_DOCS)
    connection.create_table(TABLE_DOCS, {'info': {}, 'alg': {}})
    
    # 2. 索引表: p(倒排表)
    if TABLE_INDEX.encode() in tables:
        print(f"   重建表 {TABLE_INDEX}...")
        connection.disable_table(TABLE_INDEX)
        connection.delete_table(TABLE_INDEX)
    connection.create_table(TABLE_INDEX, {'p': {}})

def import_raw_data(connection):
    print(f">>> [Step 1] 正在将原始数据导入 {TABLE_DOCS}...")
    if not os.path.exists(RAW_FILE):
        print(f"❌ 找不到 {RAW_FILE}")
        return

    table = connection.table(TABLE_DOCS)
    batch = table.batch()
    count = 0
    
    with open(RAW_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                doc = json.loads(line)
                row_key = str(doc['id']).encode('utf-8')
                
                # 只存原始数据，不存向量和PageRank
                data = {
                    b'info:title': doc.get('title', '').encode('utf-8'),
                    b'info:url': doc.get('url', '').encode('utf-8'),
                    # ✅ 修正点 1: 改为 info:year，匹配 app.py
                    b'info:year': str(doc.get('year', '')).encode('utf-8'),
                    # ✅ 修正点 2: 改为 info:source，匹配 app.py
                    b'info:source': doc.get('source', '').encode('utf-8'),
                    
                    b'info:content': doc.get('full_text', '').encode('utf-8'),
                    b'info:images': json.dumps(doc.get('images', [])).encode('utf-8'),
                    # 必须存 outlinks 才能在下一步算 PageRank
                    b'info:outlinks': json.dumps(doc.get('outlinks', [])).encode('utf-8') 
                }
                
                batch.put(row_key, data)
                count += 1
                if count % 1000 == 0: 
                    batch.send()
                    print(f"   已导入 {count} 条...")
            except: continue
            
    batch.send()
    print(f"✅ 原始数据导入完成: {count} 条。")

if __name__ == '__main__':
    conn = connect_hbase()
    init_tables(conn)
    import_raw_data(conn)
    conn.close()