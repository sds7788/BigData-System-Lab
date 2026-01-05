# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify, send_from_directory
import json
import os
import requests
import numpy as np
import math
import urllib3
import happybase
from collections import defaultdict
import time

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==============================================================================
# ⚙️ 配置区域
# ==============================================================================
HBASE_HOST = '127.0.0.1'
TABLE_NAME = 'ustc_docs'

ZHIPU_CONFIG = {
    "enable": True,
    "api_key": "87f1bb35745543f694d23ac62b629ac3.8AtkoIlBl9VOYw3L", 
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
    "chat_model": "glm-4.5",
    "embed_model": "embedding-3"
}

# ==============================================================================
# 🖼️ 路由：图片服务 (保持功能)
# ==============================================================================
@app.route('/images/<path:filename>')
def serve_images(filename):
    return send_from_directory('images', filename)

# ==============================================================================
# 🧠 核心数据层 (Hybrid: HBase Storage + Memory Index)
# ==============================================================================
class DataLayer:
    def __init__(self):
        print(">>> [System] 初始化数据层...")
        
        # 1. 统计信息缓存 (用于首页 Dashboard)
        self.stats_cache = {
            "total_data": 0,
            "dept_counts": {},
            "year_counts": {},
            "total_pages": 0,
            "total_files": 0
        }
        
        # 2. 内存索引与算法数据
        self.inverted_index = {} 
        self.doc_stats = {}      
        self.pagerank = {}       
        self.diff_storage = {}
        self.vector_ids = []    
        self.vectors = None     
        
        # 3. 图片映射表 (处理文件名大小写/后缀问题)
        self.real_image_map = {} 
        
        # --- 初始化流程 ---
        self.scan_local_images()      # A. 扫描本地图片文件
        self.load_aux_data()          # B. 加载倒排索引、向量、PR分数
        self.build_stats_from_hbase() # C. 扫描 HBase 生成统计报表

    # --- A. 图片扫描 (确保能找到图片) ---
    def scan_local_images(self):
        if not os.path.exists('images'): 
            print("⚠️ 警告: images 目录不存在，图片功能将不可用。")
            return
        
        count = 0
        for filename in os.listdir('images'):
            # 建立全小写到真实文件名的映射
            self.real_image_map[filename.lower()] = filename
            # 建立无后缀名到真实文件名的映射
            name_no_ext = os.path.splitext(filename)[0]
            self.real_image_map[name_no_ext.lower()] = filename
            count += 1
        print(f"✅ 图片扫描完成: 索引了 {count} 张本地图片。")

    # --- B. 加载辅助数据 (确保算法有效) ---
    def load_aux_data(self):
        print(">>> 加载算法数据 (Index/Vector/PageRank)...")
        
        # 1. Diff 数据
        if os.path.exists('processed_data/diff_storage.json'):
            with open('processed_data/diff_storage.json', 'r', encoding='utf-8') as f:
                self.diff_storage = json.load(f)

        # 2. 倒排索引
        if os.path.exists('processed_data/inverted_index_v2.json'):
            with open('processed_data/inverted_index_v2.json', 'r', encoding='utf-8') as f:
                self.inverted_index = json.load(f)
        
        # 3. 文档统计 (用于 TF-IDF)
        if os.path.exists('processed_data/doc_stats.json'):
            with open('processed_data/doc_stats.json', 'r', encoding='utf-8') as f:
                self.doc_stats = json.load(f)
                
        # 4. PageRank 分数
        if os.path.exists('processed_data/pagerank_scores.json'):
            with open('processed_data/pagerank_scores.json', 'r', encoding='utf-8') as f:
                self.pagerank = json.load(f)

        # 5. 向量数据
        if os.path.exists('processed_data/vector_embeddings.npy'):
            self.vectors = np.load('processed_data/vector_embeddings.npy')
            with open('processed_data/vector_ids.json', 'r', encoding='utf-8') as f:
                self.vector_ids = json.load(f)
            print("✅ 向量数据加载成功。")

    # --- C. 统计 HBase 数据 (确保首页图表有数据) ---
    def build_stats_from_hbase(self):
        print(">>> 正在扫描 HBase 生成统计报表 (Dashboard)...")
        dept_counts = defaultdict(int)
        year_counts = defaultdict(int)
        files = 0
        pages = 0
        total = 0

        conn = None
        try:
            conn = happybase.Connection(HBASE_HOST, port=9090, timeout=20000, autoconnect=True)
            table = conn.table(TABLE_NAME)
            
            # 只扫描需要的列，减少网络开销
            for key, data in table.scan(columns=[b'info:source', b'info:year', b'info:url']):
                total += 1
                source = data.get(b'info:source', b'').decode('utf-8', errors='ignore')
                year = data.get(b'info:year', b'').decode('utf-8', errors='ignore')
                url = data.get(b'info:url', b'').decode('utf-8', errors='ignore').lower()
                
                # 统计部门
                dept = self._guess_dept(source)
                dept_counts[dept] += 1
                
                # 统计年份
                if year and len(year) == 4:
                    year_counts[year] += 1
                
                # 统计类型 (附件 vs 网页)
                if any(url.endswith(ext) for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.rar']):
                    files += 1
                else:
                    pages += 1

            # 整理数据 (取 Top 10 部门)
            sorted_dept = dict(sorted(dept_counts.items(), key=lambda x: x[1], reverse=True)[:10])
            
            self.stats_cache = {
                "total_data": total,
                "dept_counts": sorted_dept,
                "year_counts": dict(year_counts),
                "total_pages": pages,
                "total_files": files
            }
            print(f"✅ HBase 统计完成: 共 {total} 条数据。")

        except Exception as e:
            print(f"❌ HBase 统计失败: {e}")
            print("💡 提示: 请确保 Hadoop/HBase 已启动，且 thrift 服务运行中 (hbase-daemon.sh start thrift)")
        finally:
            if conn: conn.close()

    # --- 辅助: 部门猜测 ---
    def _guess_dept(self, source):
        if not source: return "科大相关"
        if "gradschool" in source: return "研究生院"
        if "young" in source: return "校团委"
        if "finance" in source: return "财务处"
        if "cs.ustc" in source: return "计算机学院"
        if "ustcnet" in source: return "网络信息中心"
        if "sist.ustc" in source: return "信息学院"
        if "job.ustc" in source: return "就业指导中心"
        if "saids" in source: return "大数据学院"
        if "lib" in source: return "图书馆"
        if "jw" in source or "jiaowu" in source: return "教务处"
        return "科大相关部门"

    # --- 核心: 从 HBase 批量获取文档 (带图片映射) ---
    def get_docs_from_hbase(self, doc_ids):
        if not doc_ids: return []
        results = []
        conn = None
        try:
            conn = happybase.Connection(HBASE_HOST, port=9090, timeout=5000)
            table = conn.table(TABLE_NAME)
            
            # 批量获取 (Row Keys)
            row_keys = [str(did).encode('utf-8') for did in doc_ids]
            rows = table.rows(row_keys)
            
            for key, data in rows:
                doc_id = key.decode('utf-8')
                
                # 解码字段
                title = data.get(b'info:title', b'').decode('utf-8', errors='ignore')
                date = data.get(b'info:year', b'').decode('utf-8', errors='ignore') 
                source = data.get(b'info:source', b'').decode('utf-8', errors='ignore')
                url = data.get(b'info:url', b'#').decode('utf-8', errors='ignore')
                content = data.get(b'info:content', b'').decode('utf-8', errors='ignore')
                
                # --- 图片路径修复逻辑 ---
                raw_images_json = data.get(b'info:images', b'[]').decode('utf-8', errors='ignore')
                clean_images = []
                try:
                    raw_images = json.loads(raw_images_json)
                    for img in raw_images:
                        raw_path = img.get('local_path', '')
                        if raw_path:
                            # 提取文件名
                            clean_name = raw_path.replace('\\', '/').strip().split('/')[-1]
                            
                            # 尝试匹配真实文件
                            real_filename = self.real_image_map.get(clean_name.lower())
                            if not real_filename:
                                clean_name_no_ext = os.path.splitext(clean_name)[0]
                                real_filename = self.real_image_map.get(clean_name_no_ext.lower())
                            
                            if real_filename:
                                img['filename'] = real_filename
                                clean_images.append(img)
                except:
                    pass 
                # -----------------------

                doc_obj = {
                    "id": doc_id,
                    "info": {
                        "title": title, 
                        "date": date, 
                        "dept": self._guess_dept(source),
                        "url": url
                    },
                    "content": {"clean_text": content},
                    "images": clean_images,
                    "diff": self.diff_storage.get(doc_id, {})
                }
                results.append(doc_obj)
        except Exception as e:
            print(f"❌ HBase 查询失败: {e}")
        finally:
            if conn: conn.close()
        
        return results

    # --- 辅助: 智谱 Embedding 调用 ---
    def _get_zhipu_embedding(self, text):
        url = f"{ZHIPU_CONFIG['base_url']}/embeddings"
        headers = {"Authorization": f"Bearer {ZHIPU_CONFIG['api_key']}", "Content-Type": "application/json"}
        try:
            print(f"📡 AI Embedding 请求: {text[:10]}...")
            resp = requests.post(url, json={"input": text, "model": ZHIPU_CONFIG["embed_model"]}, 
                                 headers=headers, proxies={"http": None, "https": None}, verify=False, timeout=5)
            if resp.status_code == 200:
                return resp.json()['data'][0]['embedding']
        except Exception as e:
            print(f"❌ AI 连接失败: {e}")
        return None

    # --- 搜索算法 1: 关键词 (TF-IDF + PageRank + HBase) ---
    def search_keyword(self, query, top_k=20, pr_weight=0.001):
        if not self.inverted_index: return []
        
        # 1. 分词
        try:
            import jieba
            keywords = list(jieba.cut_for_search(query))
        except: keywords = [query]
        
        scores = {} 
        total_docs = self.doc_stats.get("total_docs", 1)
        
        # 2. 计算 TF-IDF
        for term in keywords:
            if term in self.inverted_index:
                posting_list = self.inverted_index[term]
                df = len(posting_list)
                idf = math.log(total_docs / (df + 1))
                for doc_id, tf_count in posting_list.items():
                    # 获取文档长度
                    doc_len = self.doc_stats.get("doc_lengths", {}).get(doc_id, 100)
                    
                    # 🔥 ✅ 修复 ZeroDivisionError：如果长度为 0，强制设为 100
                    if doc_len <= 0: 
                        doc_len = 100
                    
                    tf = tf_count / doc_len
                    if doc_id not in scores: scores[doc_id] = 0
                    scores[doc_id] += tf * idf

        if not scores: return []
        
        # 3. 融合 PageRank (使用传入的 pr_weight)
        doc_scores = []
        for doc_id, tfidf_score in scores.items():
            if tfidf_score <= 1e-6: continue
                
            pr_score = self.pagerank.get(doc_id, 0)
            
            # [修改] 使用 pr_weight 替代原来的 0.001
            final_score = tfidf_score + (pr_score * pr_weight)
            
            doc_scores.append((doc_id, final_score))
            
        # 4. 排序并取 Top K ID
        doc_scores.sort(key=lambda x: x[1], reverse=True)
        top_ids_scores = doc_scores[:top_k]
        top_ids = [x[0] for x in top_ids_scores]
        
        # 5. 去 HBase 查详情
        final_docs = self.get_docs_from_hbase(top_ids)
        
        # 6. 填充分数并保持顺序
        score_map = {x[0]: x[1] for x in top_ids_scores}
        for d in final_docs:
            d['score'] = score_map.get(d['id'], 0)
        
        final_docs.sort(key=lambda x: x['score'], reverse=True)
        return final_docs
    
    # --- 搜索算法 2: 向量 (Cosine + HBase) ---
    def search_vector(self, query, top_k=20):
        if self.vectors is None: 
            print("❌ 错误: 向量库未加载 (vector_embeddings.npy)")
            return []
        
        # 1. 获取 Embedding
        query_vec_list = self._get_zhipu_embedding(query)
        if not query_vec_list: return []
        
        try:
            from sklearn.metrics.pairwise import cosine_similarity
            query_vec = np.array([query_vec_list]) 
            
            # 2. 计算相似度
            similarities = cosine_similarity(query_vec, self.vectors).flatten()
            top_n = np.argsort(similarities)[::-1][:top_k]
            
            top_ids_scores = []
            for idx in top_n:
                if similarities[idx] > 0.15: # 阈值
                    doc_id = self.vector_ids[idx]
                    top_ids_scores.append((doc_id, float(similarities[idx])))
            
            if not top_ids_scores: return []

            # 3. 去 HBase 查详情
            top_ids = [x[0] for x in top_ids_scores]
            final_docs = self.get_docs_from_hbase(top_ids)
            
            # 4. 排序
            score_map = {x[0]: x[1] for x in top_ids_scores}
            for d in final_docs:
                d['score'] = score_map.get(d['id'], 0)
            
            final_docs.sort(key=lambda x: x['score'], reverse=True)
            return final_docs

        except ImportError:
            print("❌ 错误: 缺少 scikit-learn 库")
            return []
        except Exception as e:
            print(f"❌ 向量搜索错误: {e}")
            return []
        
    def get_stats(self):
        return self.stats_cache

# ==============================================================================
# 🚀 Flask 路由
# ==============================================================================
db = DataLayer()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats')
def api_stats():
    return jsonify(db.get_stats())

@app.route('/search')
def search():
    query = request.args.get('q', '')
    mode = request.args.get('mode', 'keyword') 
    
    start_time = time.time()
    
    # [新增] 获取权重参数，默认为 0.001
    try:
        pr_weight = float(request.args.get('pr_weight', 0.001))
    except:
        pr_weight = 0.001
    
    if mode == 'keyword':
        # [修改] 将 pr_weight 传入搜索函数
        results = db.search_keyword(query, pr_weight=pr_weight)
        search_type_name = "HBase 混合检索 (TF-IDF + PageRank)"
    else:
        results = db.search_vector(query)
        search_type_name = "AI 语义检索 (Embedding + HBase)"
    
    print(f"🔍 搜索耗时: {time.time() - start_time:.4f}s")
    
    # 生成 AI 综述所需的上下文
    context_text = ""
    for i, doc in enumerate(results[:3]):
        txt = doc.get('content', {}).get('clean_text', '')
        if txt: context_text += f"文档[{i+1}]: {txt[:200]}...\n"
        
    return render_template('results.html', query=query, results=results, mode=mode, 
                           search_type_name=search_type_name, initial_context=context_text,
                           pr_weight=pr_weight)

@app.route('/api/ask', methods=['POST'])
def api_ask():
    data = request.json
    question = data.get('question', '')
    scope = data.get('scope', 'global') 
    provided_context = data.get('context', '') 
    
    final_context = ""
    if scope == 'global':
        # 全局问答：先用向量搜一下 HBase
        rag_docs = db.search_vector(question, top_k=3)
        if rag_docs:
            for d in rag_docs:
                final_context += f"《{d['info']['title']}》:{d['content']['clean_text'][:300]}\n"
        else:
            final_context = "暂无相关文档。"
    else:
        final_context = provided_context

    if ZHIPU_CONFIG["enable"]:
        try:
            system_prompt = "你是一个USTC校园助手。请基于【参考资料】回答问题。如果资料不足，请诚实回答不知道。"
            user_prompt = f"【参考资料】：\n{final_context}\n\n【用户问题】：{question}"
            headers = {"Authorization": f"Bearer {ZHIPU_CONFIG['api_key']}", "Content-Type": "application/json"}
            payload = {
                "model": ZHIPU_CONFIG["chat_model"],
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                "stream": False
            }
            response = requests.post(f"{ZHIPU_CONFIG['base_url']}/chat/completions", json=payload, headers=headers, verify=False, timeout=30)
            if response.status_code == 200:
                return jsonify({"answer": response.json()['choices'][0]['message']['content']})
            else:
                return jsonify({"answer": f"API Error: {response.status_code}"})
        except Exception as e:
            return jsonify({"answer": f"AI 连接超时: {str(e)}"})
    return jsonify({"answer": "AI 未启用"})

if __name__ == '__main__':
    print("\n🚀 USTC 搜索引擎 (HBase 增强版) 已启动!")
    print("   👉 请访问: http://localhost:5000")
    app.run(debug=True, port=5000)