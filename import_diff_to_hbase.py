# -*- coding: utf-8 -*-
import happybase
import json
import os
import sys

# 配置
HBASE_HOST = '127.0.0.1'
TABLE_NAME = 'ustc_diffs'  # 专门存放 Diff 数据的表
JSON_FILE = os.path.join('output', 'diff_pairs.jsonl')

def connect_hbase():
    try:
        connection = happybase.Connection(HBASE_HOST, port=9090, timeout=20000, autoconnect=True)
        return connection
    except Exception as e:
        print(f"❌ 连接 HBase 失败: {e}")
        sys.exit(1)

def init_table(connection):
    try:
        tables = connection.tables()
        if TABLE_NAME.encode() in tables:
            print(f"⚠️ 表 {TABLE_NAME} 已存在，正在删除重建...")
            connection.disable_table(TABLE_NAME)
            connection.delete_table(TABLE_NAME)
        
        # 创建表，列族为 'data'
        connection.create_table(TABLE_NAME, {'data': dict()})
        print(f"✅ 表 {TABLE_NAME} 创建成功")
    except Exception as e:
        print(f"❌ 创建表失败: {e}")
        sys.exit(1)

def import_data(connection):
    if not os.path.exists(JSON_FILE):
        print(f"❌ 找不到数据文件: {JSON_FILE}")
        return

    table = connection.table(TABLE_NAME)
    batch = table.batch()
    count = 0
    
    print(f">>> 开始将 Diff 数据导入 HBase 表 '{TABLE_NAME}'...")
    
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                pair = json.loads(line)
                # 兼容不同字段名
                doc_id = pair.get('id') or pair.get('id2')
                text1 = pair.get('text1') or pair.get('old_text')
                text2 = pair.get('text2') or pair.get('new_text')
                
                if doc_id and text1 and text2:
                    # RowKey 使用文档 ID
                    row_key = str(doc_id).encode('utf-8')
                    
                    # 存入 data 列族
                    data = {
                        b'data:old': text1.encode('utf-8'),
                        b'data:new': text2.encode('utf-8')
                    }
                    batch.put(row_key, data)
                    count += 1
                
                if count % 100 == 0:
                    batch.send()
                    print(f"   已导入 {count} 条...")
                    batch = table.batch()
                    
            except Exception as e:
                continue
                
    batch.send()
    print(f"✅ Diff 数据导入完成！共 {count} 条。")

if __name__ == '__main__':
    conn = connect_hbase()
    init_table(conn)
    import_data(conn)
    conn.close()