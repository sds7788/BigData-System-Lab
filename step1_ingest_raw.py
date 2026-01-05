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
    # 保持 2分钟超时，防止连接中断
    return happybase.Connection(HBASE_HOST, port=9090, timeout=120000, autoconnect=True)

def init_tables(connection):
    print(">>> [Step 1] 初始化 HBase 表结构...")
    try:
        tables = connection.tables()
        if TABLE_DOCS.encode() in tables:
            print(f"   重建表 {TABLE_DOCS}...")
            connection.disable_table(TABLE_DOCS)
            connection.delete_table(TABLE_DOCS)
        connection.create_table(TABLE_DOCS, {'info': {}, 'alg': {}})
        
        if TABLE_INDEX.encode() in tables:
            print(f"   重建表 {TABLE_INDEX}...")
            connection.disable_table(TABLE_INDEX)
            connection.delete_table(TABLE_INDEX)
        connection.create_table(TABLE_INDEX, {'p': {}})
    except Exception as e:
        print(f"⚠️ 初始化表结构警告: {e}")

def import_raw_data(connection):
    print(f">>> [Step 1] 正在将原始数据导入 {TABLE_DOCS}...")
    if not os.path.exists(RAW_FILE):
        print(f"❌ 找不到 {RAW_FILE}")
        return

    table = connection.table(TABLE_DOCS)
    batch = table.batch()
    count = 0
    success_count = 0
    
    with open(RAW_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                doc = json.loads(line)
                row_key = str(doc['id']).encode('utf-8')
                
                # --- 🛡️ 1. 严格截断正文 (限制 30万字符) ---
                content = doc.get('full_text', '')
                if content and len(content) > 2000000:
                    content = content[:2000000] + "...(truncated)"

                # --- 🛡️ 2. 检查 JSON 字段大小 (限制 50万字符) ---
                # 如果图片列表或链接列表太大，直接丢弃，防止报错
                images_json = json.dumps(doc.get('images', []))
                if len(images_json) > 2000000: 
                    images_json = "[]" 
                
                outlinks_json = json.dumps(doc.get('outlinks', []))
                if len(outlinks_json) > 2000000:
                    outlinks_json = "[]"

                data = {
                    b'info:title': doc.get('title', '').encode('utf-8'),
                    b'info:url': doc.get('url', '').encode('utf-8'),
                    b'info:year': str(doc.get('year', '')).encode('utf-8'),
                    b'info:source': doc.get('source', '').encode('utf-8'),
                    b'info:content': content.encode('utf-8'),
                    b'info:images': images_json.encode('utf-8'),
                    b'info:outlinks': outlinks_json.encode('utf-8') 
                }
                
                batch.put(row_key, data)
                count += 1
                
                if count % 1000 == 0: 
                    batch.send() # 发送一批
                    batch = table.batch() # 重置 batch
                    print(f"   已处理 {count} 条...")
                    success_count = count

            except Exception as e: 
                # 捕获单行处理错误或 batch.send() 错误
                print(f"⚠️ 警告: 第 {count} 行附近发生错误，已跳过。原因: {str(e)[:100]}")
                # 发生错误后，最好重置 batch，防止坏数据卡在缓冲区
                try: batch = table.batch() 
                except: pass
                continue
            
    # --- 🛡️ 3. 给最后一次提交加保险 ---
    try:
        batch.send()
        print(f"✅ 原始数据导入完成。")
    except Exception as e:
        print(f"⚠️ 最后这批数据提交失败 (可能包含超大文档)，已跳过。错误: {str(e)[:100]}")

if __name__ == '__main__':
    conn = connect_hbase()
    init_tables(conn)
    import_raw_data(conn)
    conn.close()