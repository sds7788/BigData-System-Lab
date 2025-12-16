import json
import difflib
import os
import jieba
import numpy as np
import time
import requests
import happybase  # ✅ 引入 HBase 客户端
from collections import defaultdict

# ==============================================================================
# ⚙️ 配置
# ==============================================================================
ZHIPU_CONFIG = {
    "api_key": "d9e61b3278a64232a29af36a22f627ed.tfHSwHcC0FVZ812A", 
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
    "model": "embedding-3" 
}

# ⚠️ 注意：Diff 数据可能还在本地，如果没入库，这里保持读取本地文件
DIFF_FILE = os.path.join('output', 'diff_pairs.jsonl')
OUTPUT_DIR = './processed_data'

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# --- HBase 连接辅助函数 ---
def get_hbase_connection():
    # 使用 20秒超时，防止网络波动
    return happybase.Connection('127.0.0.1', port=9090, timeout=20000, autoconnect=True)

# --- 辅助函数 ---
def generate_diff_html(text1, text2):
    d = difflib.HtmlDiff(wrapcolumn=80)
    html = d.make_table(text1.splitlines(), text2.splitlines(), context=False, numlines=2)
    return html.replace('nowrap="nowrap"', '')

def get_remote_embedding(text):
    url = f"{ZHIPU_CONFIG['base_url']}/embeddings"
    headers = {"Authorization": f"Bearer {ZHIPU_CONFIG['api_key']}", "Content-Type": "application/json"}
    payload = {"input": text, "model": ZHIPU_CONFIG["model"]}
    try:
        resp = requests.post(url, json=payload, headers=headers, 
                              verify=False, timeout=10)
        if resp.status_code == 200:
            return resp.json()['data'][0]['embedding']
    except: pass
    return None

# ==============================================================================
# Job A: 倒排索引 (✅ 改造：从 HBase 扫描数据)
# ==============================================================================
def run_job_index():
    print(f"[Job A] 正在扫描 HBase 表 'ustc_docs' 构建倒排索引...")
    inverted_index = defaultdict(dict)
    doc_lengths = {}
    total_docs = 0
    
    conn = get_hbase_connection()
    table = conn.table('ustc_docs')
    
    try:
        # scan() 会返回 (row_key, data_dict) 的生成器
        for key, data in table.scan():
            try:
                doc_id = key.decode('utf-8') # RowKey 就是 ID
                total_docs += 1
                
                # 1. 从 HBase 列族中提取数据 (注意解码)
                title = data.get(b'info:title', b'').decode('utf-8')
                full_text = data.get(b'info:content', b'').decode('utf-8')
                
                # 2. 处理图片 Caption (存储的是 JSON 字符串)
                images_json = data.get(b'info:images', b'[]').decode('utf-8')
                images = json.loads(images_json)
                
                content = title + " " + full_text
                for img in images:
                    content += " " + img.get('caption', '')

                # 3. 分词与索引构建
                words = list(jieba.cut_for_search(content))
                doc_lengths[doc_id] = len(words)
                
                term_freq = defaultdict(int)
                for w in words:
                    if len(w.strip()) > 1: term_freq[w.strip()] += 1
                
                for term, count in term_freq.items():
                    inverted_index[term][doc_id] = count
                    
                if total_docs % 100 == 0:
                    print(f"   >> 已处理 {total_docs} 条...")
                    
            except Exception as e:
                print(f"处理行 {key} 出错: {e}")
                continue
        
        # 保存索引到本地文件供 App 读取 (索引文件通常较小，本地读取更快)
        with open(os.path.join(OUTPUT_DIR, 'inverted_index_v2.json'), 'w', encoding='utf-8') as f:
            json.dump(inverted_index, f, ensure_ascii=False)
        with open(os.path.join(OUTPUT_DIR, 'doc_stats.json'), 'w', encoding='utf-8') as f:
            json.dump({"total_docs": total_docs, "doc_lengths": doc_lengths}, f)
        print(f"[Job A] 完成。共索引 {total_docs} 文档。")
        
    finally:
        conn.close()

# ==============================================================================
# Job B: PageRank (✅ 改造：从 HBase 读取 outlinks)
# ==============================================================================
def run_job_pagerank():
    print("[Job B] 正在计算 PageRank (基于 HBase 数据)...")
    
    conn = get_hbase_connection()
    table = conn.table('ustc_docs')
    
    # 1. 构建 ID 映射和链接关系
    # 我们需要扫描全表来获取 url 和 outlinks
    url_to_id = {}
    doc_outlinks = {} # 暂存 ID -> outlinks 列表
    all_ids = []

    print("   >> 阶段1: 扫描链接关系...")
    for key, data in table.scan(columns=[b'info:url', b'info:outlinks']):
        doc_id = key.decode('utf-8')
        all_ids.append(doc_id)
        
        url = data.get(b'info:url', b'').decode('utf-8')
        if url: url_to_id[url] = doc_id
        
        outlinks_json = data.get(b'info:outlinks', b'[]').decode('utf-8')
        try:
            links = json.loads(outlinks_json)
            doc_outlinks[doc_id] = links
        except:
            doc_outlinks[doc_id] = []

    conn.close() # 扫描完可以先关一下，计算是纯内存的
    
    N = len(all_ids)
    if N == 0: return

    # 2. 构建邻接图 (内存计算)
    out_links_map = defaultdict(list)
    in_links_map = defaultdict(list)
    
    for source_id, links in doc_outlinks.items():
        for link_item in links:
            target_url = link_item.get('url')
            if target_url in url_to_id:
                target_id = url_to_id[target_url]
                if source_id != target_id: 
                    out_links_map[source_id].append(target_id)
                    in_links_map[target_id].append(source_id)

    # 3. 迭代计算
    print(f"   >> 阶段2: 迭代计算 ({len(out_links_map)} 关系)...")
    pr = {doc_id: 1.0/N for doc_id in all_ids}
    d = 0.85 
    for i in range(15): 
        new_pr = {}
        for doc_id in all_ids:
            incoming_score = 0
            for link_from_id in in_links_map[doc_id]:
                link_count = len(out_links_map[link_from_id])
                if link_count > 0:
                    incoming_score += pr[link_from_id] / link_count
            new_pr[doc_id] = (1 - d) / N + d * incoming_score
        pr = new_pr

    # 4. 保存
    final_pr = {k: v * 1000 for k, v in pr.items()}
    with open(os.path.join(OUTPUT_DIR, 'pagerank_scores.json'), 'w', encoding='utf-8') as f:
        json.dump(final_pr, f)
    print(f"[Job B] 完成。")

# ==============================================================================
# Job C: 版本差异 (✅ 改造：从 HBase 'ustc_diffs' 表读取原始文本)
# ==============================================================================
def run_job_diff():
    print(f"[Job C] 正在扫描 HBase 表 'ustc_diffs' 计算差异...")
    diff_storage = {}
    count = 0
    
    conn = get_hbase_connection()
    try:
        # 检查表是否存在
        if b'ustc_diffs' not in conn.tables():
            print("⚠️ HBase 中没有 'ustc_diffs' 表，跳过 Diff 计算。")
            print("   (请先运行 python3 import_diff_to_hbase.py)")
            return

        table = conn.table('ustc_diffs')
        
        # 扫描全表
        for key, data in table.scan():
            try:
                doc_id = key.decode('utf-8')
                
                # 获取新旧文本
                t1 = data.get(b'data:old', b'').decode('utf-8')
                t2 = data.get(b'data:new', b'').decode('utf-8')
                
                if t1 and t2:
                    # 计算 HTML 差异 (耗时操作，本地 CPU 计算)
                    html = generate_diff_html(t1, t2)
                    
                    diff_storage[doc_id] = {
                        "has_diff": True, 
                        "diff_html": html
                    }
                    count += 1
            except Exception as e:
                continue

        # 将计算好的 HTML 结果存为 JSON 供 App 读取
        # (注：App 启动时会加载这个 JSON 到内存，不需要每次都查 HBase，提高响应速度)
        with open(os.path.join(OUTPUT_DIR, 'diff_storage.json'), 'w', encoding='utf-8') as f:
            json.dump(diff_storage, f, ensure_ascii=False)
            
        print(f"[Job C] 完成。基于 HBase 数据生成了 {count} 组对比结果。")

    except Exception as e:
        print(f"Job C 出错: {e}")
    finally:
        conn.close()

# ==============================================================================
# Job D: 向量化 (✅ 终极稳定版：先扫ID，再逐个处理)
# ==============================================================================
def run_job_vectorize():
    print("[Job D] 检查向量数据...")
    if os.path.exists(os.path.join(OUTPUT_DIR, 'vector_embeddings.npy')):
        print(">> 向量已存在，跳过。")
        return

    import urllib3
    urllib3.disable_warnings()

    doc_ids = []
    vectors = []
    
    conn = get_hbase_connection()
    try:
        table = conn.table('ustc_docs')
        print(f">> [阶段1] 正在扫描 HBase 获取所有文档 ID...")
        
        # 1. 快速扫描：只获取 RowKey (不获取内容，速度极快，防止超时)
        # scan() 返回 (row_key, data) 元组
        all_keys = [key for key, _ in table.scan(columns=[b'info:title'])] 
        print(f">> 扫描完成，共获取 {len(all_keys)} 个文档 ID。")
        print(f">> [阶段2] 开始逐个获取内容并向量化...")

        # 2. 逐个处理
        total = len(all_keys)
        count = 0
        
        for doc_key in all_keys:
            try:
                # 每次只取一行，取完连接就释放，不存在 Scanner 超时问题
                row = table.row(doc_key, columns=[b'info:title', b'info:content'])
                
                doc_id = doc_key.decode('utf-8')
                title = row.get(b'info:title', b'').decode('utf-8')
                content = row.get(b'info:content', b'').decode('utf-8')
                
                text = f"{title}：{content[:600]}".replace("\n", " ")
                vec = get_remote_embedding(text)
                
                if vec:
                    doc_ids.append(doc_id)
                    vectors.append(vec)
                
                count += 1
                if count % 10 == 0: 
                    print(f"   进度: {count}/{total} 已处理")
            except Exception as inner_e:
                print(f"⚠️ 处理文档 {doc_key} 失败: {repr(inner_e)}")
                continue # 跳过错误文档，继续下一个

    except Exception as e:
        # ✅ 修复 print 报错：使用 repr(e) 确保能打印出任何类型的异常
        print(f"❌ 运行中途出错: {repr(e)}")
    finally:
        conn.close()
    
    # 3. 保存结果
    if vectors:
        vectors_np = np.array(vectors, dtype='float32')
        # 确保目录存在
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)
            
        with open(os.path.join(OUTPUT_DIR, 'vector_ids.json'), 'w', encoding='utf-8') as f:
            json.dump(doc_ids, f)
        np.save(os.path.join(OUTPUT_DIR, 'vector_embeddings.npy'), vectors_np)
        print(f"[Job D] 完成。共生成 {len(vectors)} 个向量。")
    else:
        print("[Job D] 未生成任何向量，请检查网络或数据。") 
        
if __name__ == '__main__':
    run_job_index()
    run_job_pagerank()
    run_job_diff()
    run_job_vectorize()
    print("\n✅ 所有离线计算已基于 HBase 数据完成！")