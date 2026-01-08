import urllib3
# ⬇️ 新增这行代码来屏蔽警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# -*- coding: utf-8 -*-
# 文件名: step2_mr_driver.py
import os
import sys
import subprocess
import json
import numpy as np
import time
import requests
import difflib

# ================= 配置区域 =================
# 请根据你的 Hadoop 安装位置修改这里！！
# 常见路径：
# /usr/local/hadoop/share/hadoop/tools/lib/hadoop-streaming-*.jar
# $HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming-*.jar
HADOOP_STREAMING_JAR = "/usr/local/hadoop/share/hadoop/tools/lib/hadoop-streaming-3.3.6.jar" 

# 如果没有找到，尝试自动寻找
if not os.path.exists(HADOOP_STREAMING_JAR):
    try:
        # 尝试通过环境变量寻找
        hadoop_home = os.environ.get('HADOOP_HOME', '/usr/local/hadoop')
        jar_path = os.path.join(hadoop_home, 'share/hadoop/tools/lib')
        for f in os.listdir(jar_path):
            if f.startswith("hadoop-streaming") and f.endswith(".jar"):
                HADOOP_STREAMING_JAR = os.path.join(jar_path, f)
                break
    except:
        pass

INPUT_LOCAL = "output/documents.jsonl"
INPUT_HDFS = "/input/documents.jsonl"
OUTPUT_HDFS = "/output_step2"
OUTPUT_LOCAL_DIR = "processed_data"

ZHIPU_CONFIG = {
    "api_key": "", 
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
    "model": "embedding-3" 
}

if not os.path.exists(OUTPUT_LOCAL_DIR):
    os.makedirs(OUTPUT_LOCAL_DIR)

# ================= MapReduce 任务提交 =================
def run_mapreduce():
    print(f">>> [Step 2 - MR] 正在准备 MapReduce 任务...")
    
    # 1. 上传数据到 HDFS
    print("   上传数据到 HDFS...")
    os.system(f"hdfs dfs -mkdir -p /input")
    os.system(f"hdfs dfs -rm -f {INPUT_HDFS}")
    if os.system(f"hdfs dfs -put {INPUT_LOCAL} {INPUT_HDFS}") != 0:
        print("❌ HDFS 上传失败，请检查 Hadoop 是否启动。")
        sys.exit(1)
        
    # 2. 清理输出目录
    os.system(f"hdfs dfs -rm -r -f {OUTPUT_HDFS}")
    
    # 3. 提交 Hadoop Streaming 任务
    print("   🚀 提交 Hadoop Streaming 任务...")
    cmd = f"""
    hadoop jar {HADOOP_STREAMING_JAR} \\
        -files mr_mapper.py,mr_reducer.py \\
        -mapper "python3 mr_mapper.py" \\
        -reducer "python3 mr_reducer.py" \\
        -input {INPUT_HDFS} \\
        -output {OUTPUT_HDFS}
    """
    
    # 执行命令
    ret = os.system(cmd)
    if ret != 0:
        print("❌ MapReduce 任务执行失败！")
        sys.exit(1)
    
    print("✅ MapReduce 任务完成！")

# ================= 结果处理 =================
def process_results():
    print(">>> [Step 2 - MR] 正在处理 MapReduce 结果...")
    
    # 1. 读取 MR 结果 (通过 cat 命令直接流式读取，避免保存中间文件)
    process = subprocess.Popen(["hdfs", "dfs", "-cat", f"{OUTPUT_HDFS}/part-*"], stdout=subprocess.PIPE)
    
    inverted_index = {}
    doc_graph = {} # id -> {url, len, outlinks}
    
    for line_bytes in process.stdout:
        line = line_bytes.decode('utf-8').strip()
        parts = line.split('\t')
        tag = parts[0]
        
        if tag == "RESULT_INDEX":
            # word \t json_postings
            word = parts[1]
            postings = json.loads(parts[2])
            inverted_index[word] = postings
            
        elif tag == "RESULT_GRAPH":
            # doc_id \t url \t length \t json_outlinks
            doc_id = parts[1]
            url = parts[2]
            length = int(parts[3])
            outlinks = json.loads(parts[4])
            
            doc_graph[doc_id] = {
                "url": url,
                "len": length,
                "outlinks": outlinks
            }

    # 2. 保存倒排索引
    print(f"   保存倒排索引 (共 {len(inverted_index)} 个词)...")
    with open(os.path.join(OUTPUT_LOCAL_DIR, 'inverted_index_v2.json'), 'w', encoding='utf-8') as f:
        json.dump(inverted_index, f, ensure_ascii=False)
        
    # 3. 保存文档统计
    print(f"   保存文档统计 (共 {len(doc_graph)} 篇)...")
    doc_lengths = {k: v['len'] for k, v in doc_graph.items()}
    with open(os.path.join(OUTPUT_LOCAL_DIR, 'doc_stats.json'), 'w', encoding='utf-8') as f:
        json.dump({"total_docs": len(doc_graph), "doc_lengths": doc_lengths}, f)
        
    return doc_graph

# ================= 辅助算法 (本地/混合) =================
def run_pagerank(doc_graph):
    print("\n>>> [Step 2 - Algo] 正在计算 PageRank (基于 MR 构建的图)...")
    
    # 1. 构建 ID 映射
    url_to_id = {v['url']: k for k, v in doc_graph.items() if v['url']}
    all_ids = list(doc_graph.keys())
    N = len(all_ids)
    
    # 2. 构建邻接表
    out_links_map = {}
    in_links_map = {uid: [] for uid in all_ids}
    
    for src_id, info in doc_graph.items():
        targets = []
        for url in info['outlinks']:
            if url in url_to_id:
                tgt_id = url_to_id[url]
                if tgt_id != src_id:
                    targets.append(tgt_id)
                    in_links_map[tgt_id].append(src_id)
        out_links_map[src_id] = targets

    # 3. 迭代计算
    pr = {doc_id: 1.0/N for doc_id in all_ids}
    d = 0.85 
    for _ in range(15): 
        new_pr = {}
        for doc_id in all_ids:
            incoming = 0
            for from_id in in_links_map[doc_id]:
                out_degree = len(out_links_map[from_id])
                if out_degree > 0:
                    incoming += pr[from_id] / out_degree
            new_pr[doc_id] = (1 - d)/N + d * incoming
        pr = new_pr

    # 4. 保存
    final_pr = {k: v * 1000 for k, v in pr.items()}
    with open(os.path.join(OUTPUT_LOCAL_DIR, 'pagerank_scores.json'), 'w', encoding='utf-8') as f:
        json.dump(final_pr, f)
    print("✅ PageRank 计算完成。")

def run_diff_local():
    # Diff 处理逻辑简单且 IO 密集，保持本地处理即可，MapReduce 优势不明显
    print("\n>>> [Step 2 - Algo] 处理 Diff 数据...")
    import difflib
    diff_storage = {}
    count = 0
    diff_file = "output/diff_pairs.jsonl"
    if os.path.exists(diff_file):
        with open(diff_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    p = json.loads(line)
                    tid = p.get('id') or p.get('id2')
                    t1, t2 = p.get('text1', ''), p.get('text2', '')
                    if tid and t1 and t2:
                        d = difflib.HtmlDiff(wrapcolumn=80)
                        html = d.make_table(t1.splitlines(), t2.splitlines(), context=False, numlines=2)
                        html = html.replace('nowrap="nowrap"', '')
                        diff_storage[tid] = {"has_diff": True, "diff_html": html}
                        count += 1
                except: continue
        with open(os.path.join(OUTPUT_LOCAL_DIR, 'diff_storage.json'), 'w', encoding='utf-8') as f:
            json.dump(diff_storage, f, ensure_ascii=False)
    print(f"✅ Diff 处理完成: {count} 条。")

def get_remote_embedding(text):
    # 智谱 AI 调用
    url = f"{ZHIPU_CONFIG['base_url']}/embeddings"
    headers = {"Authorization": f"Bearer {ZHIPU_CONFIG['api_key']}", "Content-Type": "application/json"}
    try:
        resp = requests.post(url, json={"input": text, "model": ZHIPU_CONFIG["model"]}, 
                             headers=headers, verify=False, timeout=10)
        if resp.status_code == 200: return resp.json()['data'][0]['embedding']
    except: pass
    return None

def run_vector_local():
    print("\n>>> [Step 2 - Algo] 计算向量 Embedding (本地线程池)...")
    # ⚠️ 警告：绝对不要在 MapReduce 中调用 API，否则 Key 必封无疑。
    # 保持本地计算，带有断点续传功能。
    
    vec_path = os.path.join(OUTPUT_LOCAL_DIR, 'vector_embeddings.npy')
    id_path = os.path.join(OUTPUT_LOCAL_DIR, 'vector_ids.json')
    
    processed_ids = set()
    existing_vecs = []
    existing_ids = []
    
    if os.path.exists(vec_path) and os.path.exists(id_path):
        existing_vecs = list(np.load(vec_path))
        with open(id_path, 'r', encoding='utf-8') as f:
            existing_ids = json.load(f)
        processed_ids = set(existing_ids)
        print(f"   发现已有向量: {len(processed_ids)} 条，执行增量更新...")
    
    new_vecs = []
    new_ids = []
    
    # 读取原始数据
    docs = []
    with open(INPUT_LOCAL, 'r', encoding='utf-8') as f:
        for line in f: docs.append(json.loads(line))
        
    to_proc = [d for d in docs if str(d['id']) not in processed_ids]
    print(f"   待处理: {len(to_proc)} 条...")
    
    for i, d in enumerate(to_proc):
        text = f"{d.get('title','')} {d.get('full_text','')[:500]}".replace("\n", " ")
        vec = get_remote_embedding(text)
        if vec:
            new_vecs.append(vec)
            new_ids.append(str(d['id']))
            print(f"   向量化进度: {i+1}/{len(to_proc)}", end='\r')
            time.sleep(0.1) # 频控
            
    if new_vecs:
        final_vecs = existing_vecs + new_vecs
        final_ids = existing_ids + new_ids
        np.save(vec_path, np.array(final_vecs, dtype='float32'))
        with open(id_path, 'w', encoding='utf-8') as f:
            json.dump(final_ids, f)
        print(f"\n✅ 向量库更新完成。")
    else:
        print("\n✅ 无需更新向量。")

if __name__ == '__main__':
    # 1. 运行 MapReduce (倒排索引 + 图构建)
    run_mapreduce()
    
    # 2. 处理 MR 结果
    graph_data = process_results()
    
    # 3. 运行 PageRank (基于 MR 结果)
    run_pagerank(graph_data)
    
    # 4. 运行其他组件
    run_diff_local()
    run_vector_local()
    

    print("\n🎉 全部处理完成！请运行 python app.py 启动搜索引擎。")
