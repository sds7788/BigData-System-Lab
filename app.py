# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify, send_from_directory
import json
import os
import requests
import numpy as np
import math
import urllib3
import happybase # ✅ 引入 HBase
from collections import defaultdict

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# --- 配置 ---
ZHIPU_CONFIG = {
    "enable": True,
    "api_key": "d9e61b3278a64232a29af36a22f627ed.tfHSwHcC0FVZ812A", 
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
    "chat_model": "glm-4.5",
    "embed_model": "embedding-3"
}

@app.route('/images/<path:filename>')
def serve_images(filename):
    return send_from_directory('images', filename)

class DataLayer:
    def __init__(self):
        # 内存里不再存 docs_map，但在启动时我们需要统计信息
        self.stats_cache = {
            "total_data": 0,
            "dept_counts": {},
            "year_counts": {},
            "total_pages": 0,
            "total_files": 0
        }
        
        self.inverted_index = {} 
        self.doc_stats = {}      
        self.pagerank = {}       
        self.diff_storage = {}
        self.vector_ids = []    
        self.vectors = None     
        
        self.real_image_map = {} 
        
        # 1. 扫描本地图片
        self.scan_local_images() 
        # 2. 加载辅助数据
        self.load_aux_data() 
        # 3. ✅ 修复：扫描 HBase 生成统计信息 (恢复前端图表)
        self.build_stats_from_hbase()

    def scan_local_images(self):
        if not os.path.exists('images'): return
        for filename in os.listdir('images'):
            self.real_image_map[filename.lower()] = filename
            name_no_ext = os.path.splitext(filename)[0]
            self.real_image_map[name_no_ext.lower()] = filename

    def load_aux_data(self):
        print(">>> 加载索引与算法数据...")
        if os.path.exists('processed_data/diff_storage.json'):
            with open('processed_data/diff_storage.json', 'r', encoding='utf-8') as f:
                self.diff_storage = json.load(f)

        if os.path.exists('processed_data/inverted_index_v2.json'):
            with open('processed_data/inverted_index_v2.json', 'r', encoding='utf-8') as f:
                self.inverted_index = json.load(f)
        
        if os.path.exists('processed_data/doc_stats.json'):
            with open('processed_data/doc_stats.json', 'r', encoding='utf-8') as f:
                self.doc_stats = json.load(f)
                
        if os.path.exists('processed_data/pagerank_scores.json'):
            with open('processed_data/pagerank_scores.json', 'r', encoding='utf-8') as f:
                self.pagerank = json.load(f)

        if os.path.exists('processed_data/vector_embeddings.npy'):
            self.vectors = np.load('processed_data/vector_embeddings.npy')
            with open('processed_data/vector_ids.json', 'r', encoding='utf-8') as f:
                self.vector_ids = json.load(f)

    # --- ✅ 修复版：根据 URL 后缀正确统计附件数量 ---
    def build_stats_from_hbase(self):
        print(">>> 正在扫描 HBase 生成统计报表 (Dashboard)...")
        dept_counts = defaultdict(int)
        year_counts = defaultdict(int)
        files = 0
        pages = 0
        total = 0

        conn = None
        try:
            conn = happybase.Connection('127.0.0.1', port=9090, timeout=10000)
            table = conn.table('ustc_docs')
            
            # ✅ 修改：多查一个 info:url 列，用来判断文件类型
            for key, data in table.scan(columns=[b'info:source', b'info:year', b'info:url']):
                total += 1
                source = data.get(b'info:source', b'').decode('utf-8')
                year = data.get(b'info:year', b'').decode('utf-8')
                
                # 获取 URL 并转小写，方便判断后缀
                url = data.get(b'info:url', b'').decode('utf-8').lower()
                
                # 统计部门
                dept = self._guess_dept(source)
                dept_counts[dept] += 1
                
                # 统计年份
                year_counts[year] += 1
                
                # ✅ 核心修复：智能判断是“附件”还是“网页”
                # 如果 URL 以常见文档后缀结尾，就算作附件
                if any(url.endswith(ext) for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.rar']):
                    files += 1
                else:
                    pages += 1 

            # 排序部门 (取前10)
            sorted_dept = dict(sorted(dept_counts.items(), key=lambda x: x[1], reverse=True)[:10])
            
            self.stats_cache = {
                "total_data": total,
                "dept_counts": sorted_dept,
                "year_counts": dict(year_counts),
                "total_pages": pages, # 网页数量
                "total_files": files  # 附件数量 (PDF等)
            }
            print(f"✅ 统计完成：共 {total} 条数据 (网页: {pages}, 附件: {files})。")

        except Exception as e:
            print(f"❌ 统计扫描失败: {e}")
        finally:
            if conn: conn.close()

    # --- 核心功能：从 HBase 获取文档详情 ---
    def get_docs_from_hbase(self, doc_ids):
        if not doc_ids: return []
        results = []
        conn = None
        try:
            conn = happybase.Connection('127.0.0.1', port=9090, timeout=5000)
            table = conn.table('ustc_docs')
            
            row_keys = [did.encode('utf-8') for did in doc_ids]
            rows = table.rows(row_keys)
            
            for key, data in rows:
                doc_id = key.decode('utf-8')
                
                title = data.get(b'info:title', b'').decode('utf-8')
                # 🐛 修复：之前写成了 info:date，应该是 info:year
                date = data.get(b'info:year', b'').decode('utf-8') 
                source = data.get(b'info:source', b'').decode('utf-8')
                url = data.get(b'info:url', b'#').decode('utf-8')
                content = data.get(b'info:content', b'').decode('utf-8')
                
                # 图片处理
                raw_images_json = data.get(b'info:images', b'[]').decode('utf-8')
                raw_images = json.loads(raw_images_json)
                clean_images = []
                for img in raw_images:
                    raw_path = img.get('local_path', '')
                    if raw_path:
                        clean_name = raw_path.replace('\\', '/').strip().split('/')[-1]
                        real_filename = self.real_image_map.get(clean_name.lower())
                        if not real_filename:
                            clean_name_no_ext = os.path.splitext(clean_name)[0]
                            real_filename = self.real_image_map.get(clean_name_no_ext.lower())
                        
                        if real_filename:
                            img['filename'] = real_filename
                            clean_images.append(img)

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

    def _get_zhipu_embedding(self, text):
        url = f"{ZHIPU_CONFIG['base_url']}/embeddings"
        headers = {"Authorization": f"Bearer {ZHIPU_CONFIG['api_key']}", "Content-Type": "application/json"}
        try:
            # 打印正在请求，方便调试
            print(f"📡 正在请求 AI 向量接口: {text[:10]}...")
            
            resp = requests.post(url, json={"input": text, "model": ZHIPU_CONFIG["embed_model"]}, 
                                 headers=headers, proxies={"http": None, "https": None}, verify=False, timeout=5)
            
            if resp.status_code == 200:
                print("✅ AI 接口响应成功")
                return resp.json()['data'][0]['embedding']
            else:
                # 打印错误状态码
                print(f"❌ AI 接口报错: {resp.status_code} - {resp.text}")
        except Exception as e:
            # 打印具体异常信息
            print(f"❌ AI 连接失败: {e}")
        return None

    def search_keyword(self, query, top_k=20):
        if not self.inverted_index: return []
        try:
            import jieba
            keywords = list(jieba.cut_for_search(query))
        except: keywords = [query]
        
        scores = {} 
        total_docs = self.doc_stats.get("total_docs", 1)
        
        for term in keywords:
            if term in self.inverted_index:
                posting_list = self.inverted_index[term]
                df = len(posting_list)
                idf = math.log(total_docs / (df + 1))
                for doc_id, tf_count in posting_list.items():
                    doc_len = self.doc_stats.get("doc_lengths", {}).get(doc_id, 100)
                    tf = tf_count / doc_len
                    if doc_id not in scores: scores[doc_id] = 0
                    scores[doc_id] += tf * idf

        if not scores: return []
        
        doc_scores = []
        for doc_id, tfidf_score in scores.items():
            pr_score = self.pagerank.get(doc_id, 0)
            final_score = tfidf_score + (pr_score * 0.05)
            doc_scores.append((doc_id, final_score))
        
        doc_scores.sort(key=lambda x: x[1], reverse=True)
        top_ids_scores = doc_scores[:top_k]
        
        top_ids = [x[0] for x in top_ids_scores]
        final_docs = self.get_docs_from_hbase(top_ids)
        
        score_map = {x[0]: x[1] for x in top_ids_scores}
        for d in final_docs:
            d['score'] = score_map.get(d['id'], 0)
        
        final_docs.sort(key=lambda x: x['score'], reverse=True)
        return final_docs

    def search_vector(self, query, top_k=20):
        # 1. 检查本地向量库是否加载成功
        if self.vectors is None: 
            print("❌ 错误: 内存中没有向量数据。请检查 processed_data/vector_embeddings.npy 是否存在。")
            return []
        
        # 2. 获取用户查询的向量
        query_vec_list = self._get_zhipu_embedding(query)
        if not query_vec_list: 
            print("⚠️ 警告: 无法获取查询词的 Embedding (API 返回为空)。")
            return []
        
        try:
            # 3. 尝试计算相似度
            from sklearn.metrics.pairwise import cosine_similarity
            query_vec = np.array([query_vec_list]) 
            
            # 计算余弦相似度
            similarities = cosine_similarity(query_vec, self.vectors).flatten()
            
            # 取前 K 个
            top_n = np.argsort(similarities)[::-1][:top_k]
            
            top_ids_scores = []
            for idx in top_n:
                # 阈值判断
                if similarities[idx] > 0.2: 
                    doc_id = self.vector_ids[idx]
                    top_ids_scores.append((doc_id, float(similarities[idx])))
            
            if not top_ids_scores:
                print(f"⚠️ 提示: 计算成功，但没有文档相似度 > 0.2 (最高分: {similarities[top_n[0]] if len(top_n)>0 else 0})")
                return []

            top_ids = [x[0] for x in top_ids_scores]
            final_docs = self.get_docs_from_hbase(top_ids)
            
            # 重新根据分数排序
            score_map = {x[0]: x[1] for x in top_ids_scores}
            for d in final_docs:
                d['score'] = score_map.get(d['id'], 0)
            
            final_docs.sort(key=lambda x: x['score'], reverse=True)
            return final_docs

        except ImportError:
            print("❌ 严重错误: 缺少 sklearn 库。请运行 pip install scikit-learn")
            return []
        except Exception as e:
            # 🔥 关键修改：打印出具体的报错信息！
            print(f"❌ search_vector 发生异常: {e}")
            import traceback
            traceback.print_exc()
            return []
        
    # ✅ 恢复：返回完整的统计信息
    def get_stats(self):
        return self.stats_cache

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
    if mode == 'keyword':
        results = db.search_keyword(query)
        search_type_name = "HBase 检索 (TF-IDF + PageRank)" 
    else:
        results = db.search_vector(query)
        search_type_name = "AI 语义检索 (Zhipu Embedding)"
    
    context_text = ""
    for i, doc in enumerate(results[:3]):
        txt = doc.get('content', {}).get('clean_text', '')
        if txt: context_text += f"文档[{i+1}]: {txt[:200]}...\n"
        
    return render_template('results.html', query=query, results=results, mode=mode, 
                           search_type_name=search_type_name, initial_context=context_text)

@app.route('/api/ask', methods=['POST'])
def api_ask():
    data = request.json
    question = data.get('question', '')
    scope = data.get('scope', 'global') 
    provided_context = data.get('context', '') 
    final_context = ""
    if scope == 'global':
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
            system_prompt = "你是一个USTC校园助手。请基于【参考资料】回答问题。"
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
                return jsonify({"answer": f"智谱 API 错误: {response.status_code}"})
        except Exception as e:
            return jsonify({"answer": f"连接超时: {str(e)}"})
    return jsonify({"answer": "AI 未启用"})

if __name__ == '__main__':
    print("🚀 启动 Web 服务 (HBase 驱动版)...")
    app.run(debug=True, port=5000)