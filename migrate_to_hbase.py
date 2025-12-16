# -*- coding: utf-8 -*-
import happybase
import json
import os
import sys

# 配置
HBASE_HOST = '127.0.0.1'
TABLE_NAME = 'ustc_docs'
JSON_FILE = os.path.join('output', 'documents.jsonl')

def connect_hbase():
    try:
        # 使用 20秒超时，防止连接太慢报错
        connection = happybase.Connection(HBASE_HOST, port=9090, timeout=20000, autoconnect=True)
        return connection
    except Exception as e:
        print(f"❌ 连接 HBase 失败: {e}")
        print("💡 请检查: 1. Thrift 是否启动 (hbase-daemon.sh start thrift)")
        print("          2. /etc/hosts 是否修正 (127.0.1.1 注释掉)")
        sys.exit(1)

def init_tables(connection):
    try:
        tables = connection.tables()
        if TABLE_NAME.encode() in tables:
            print(f"⚠️ 表 {TABLE_NAME} 已存在，正在删除重建...")
            connection.disable_table(TABLE_NAME)
            connection.delete_table(TABLE_NAME)
        
        # 创建表，只用一个列族 'info' 即可，简化结构
        connection.create_table(
            TABLE_NAME,
            {'info': dict()} 
        )
        print(f"✅ 创建表 {TABLE_NAME} 成功")
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
    
    print(">>> 开始导入数据到 HBase (包含 outlinks)...")
    
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                doc = json.loads(line)
                row_key = doc.get('id')
                if not row_key: continue
                
                # 准备数据字典
                data = {
                    b'info:url': doc.get('url', '').encode('utf-8'),
                    b'info:title': doc.get('title', '').encode('utf-8'),
                    b'info:content': doc.get('full_text', '').encode('utf-8'),
                    b'info:year': str(doc.get('year', '')).encode('utf-8'),
                    b'info:source': doc.get('source', '').encode('utf-8'),
                    # ✅ 关键修复：必须存 outlinks，否则 PageRank 没法算！
                    b'info:outlinks': json.dumps(doc.get('outlinks', [])).encode('utf-8'),
                    # 存图片信息
                    b'info:images': json.dumps(doc.get('images', [])).encode('utf-8')
                }
                
                batch.put(row_key, data)
                count += 1
                
                if count % 100 == 0:
                    batch.send()
                    print(f"   已导入 {count} 条")
                    batch = table.batch()
                    
            except Exception as e:
                print(f"⚠️ 跳过错误行: {e}")
                continue
                
    batch.send() # 发送最后剩余的
    print(f"✅ 导入完成！共 {count} 条。")

if __name__ == '__main__':
    conn = connect_hbase()
    init_tables(conn)
    import_data(conn)
    conn.close()