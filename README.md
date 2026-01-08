# USTC Data Insight - 智能校园大数据检索系统

<img src="static/logo.png" alt="Logo" width="100" />

> 基于 Hadoop 生态与大模型 RAG 技术的中国科学技术大学校园文档检索引擎。

## 📖 项目简介

本项目是一个完整的大数据系统实验工程，实现了从数据采集、清洗、存储、离线计算到在线检索的全链路流程。系统针对 USTC 校园网内的网页、PDF、DOCX 等多模态数据进行抓取，利用 Hadoop MapReduce 构建倒排索引与计算 PageRank，使用 HBase 进行海量数据存储，并结合智谱 AI (GLM-4) 实现向量检索与 RAG（检索增强生成）问答。

## ✨ 核心特性

* **多源异构数据采集**: 支持 HTML 网页、PDF 文档、DOCX 文档、图片等多格式数据的深度爬取与解析。
* **大数据存储与计算**:
    * **存储**: 使用 **HBase** 存储海量文档正文及元数据。
    * **计算**: 使用 **Hadoop MapReduce** 构建倒排索引与文档图结构。
    * **算法**: 实现了 **PageRank** 网页排名算法与 **TF-IDF** 关键词权重计算。
* **混合检索架构**:
    * **关键词检索**: 传统的倒排索引 + TF-IDF + PageRank 加权排序。
    * **语义检索**: 基于 Embedding 向量相似度（Cosine Similarity）的语义匹配。
* **AI 智能问答 (RAG)**: 集成智谱 AI 大模型，支持基于检索结果的智能综述与问答。
* **数据可视化**: 包含文档年份分布、部门来源统计等 ECharts 交互式图表。

## 🏗️ 系统架构

1.  **数据层 (SmartETL)**: `Scrapy` 思想的自定义爬虫，负责抓取 USTC 各大门户，清洗并输出 JSONL 格式数据。
2.  **存储层 (HBase)**: 将清洗后的非结构化数据导入 HBase 表 (`ustc_docs`)。
3.  **计算层 (MapReduce & Spark idea)**:
    * MR Job: 生成倒排索引 (`INDEX`) 和 链接图 (`GRAPH`)。
    * Local Driver: 基于 MR 结果迭代计算 PageRank，调用 API 生成向量 Embedding。
4.  **应用层 (Flask)**: 提供 Web 界面，集成搜索、高亮、快照预览及 AI 对话功能。

## 📂 项目结构

```text
Project_Root
├── SmartETL/                  # [模块1] 智能爬虫与ETL
│   ├── config/                # 爬虫配置文件
│   ├── src/
│   │   ├── crawler/           # 网页/图片/文件下载器
│   │   ├── processors/        # PDF/DOCX 解析与文本清洗
│   │   └── main.py            # ETL 入口
│   └── run.py                 # 启动脚本
├── SchemaDesign/              # [模块2] 数据预处理与导出工具
│   ├── config.py
│   ├── exporter.py            # 导出为 MR 输入格式
│   └── run.py                 # 处理入口
├── static/                    # 前端静态资源 (Logo等)
├── templates/                 # Flask HTML 模板
│   ├── index.html             # 首页 (仪表盘)
│   └── results.html           # 搜索结果页 (含 AI 对话)
├── app.py                     # [模块4] Web 搜索应用入口 (Flask)
├── mr_mapper.py               # MapReduce Mapper 脚本
├── mr_reducer.py              # MapReduce Reducer 脚本
├── step1_ingest_raw.py        # [模块3-1] 数据导入 HBase
├── step2_mr_driver.py         # [模块3-2] MapReduce 驱动与算法计算
├── requirements.txt           # 项目依赖
└── README.md                  # 项目说明
```

## 🚀 快速开始

### 1. 环境准备

确保你的环境已安装以下组件：

- Python 3.8+
- Hadoop 3.x (HDFS, MapReduce)
- HBase 2.x (需开启 Thrift 服务: `hbase-daemon.sh start thrift`)
- Java JDK 8+

安装 Python 依赖：

```bash
pip install -r requirements.txt
```

### 2. 数据采集 (SmartETL)

运行爬虫抓取数据，数据将保存在 `output/` 目录下。

```bash
python SmartETL/run.py
```

*配置文件位于 `SmartETL/config/config.yaml`，可调整目标 URL 和抓取深度。*

### 3. 数据导入 HBase

将采集到的 `jsonl` 数据导入 HBase 表中。

```bash
python step1_ingest_raw.py
```

### 4. 离线计算 (MapReduce & PageRank)

提交 Hadoop 任务构建索引，并在本地计算 PageRank 和向量向量化。 *注意：需在脚本中配置 `HADOOP_STREAMING_JAR` 的路径。*

```bash
python step2_mr_driver.py
```

该步骤会生成：

- `inverted_index_v2.json`: 倒排索引
- `pagerank_scores.json`: 网页排名分数
- `vector_embeddings.npy`: 向量库

### 5. 启动搜索引擎

启动 Flask Web 应用。

```bash
python app.py
```

访问浏览器：`http://localhost:5000`

## ⚙️ 配置说明

- **API Key 配置**: 若要使用 AI 功能，请在 `app.py` 和 `step2_mr_driver.py` 中修改 `ZHIPU_CONFIG`：

  Python

  ```
  ZHIPU_CONFIG = {
      "api_key": "YOUR_API_KEY",
      ...
  }
  ```

- **Hadoop 配置**: 在 `step2_mr_driver.py` 中修改 Hadoop Streaming Jar 包路径和 HDFS 路径。

## 📊 功能展示

1. **首页仪表盘**: 展示数据总量、部门分布、年份趋势。
2. **混合搜索**: 支持关键词搜索（可调整 PageRank 权重）和 AI 语义模式切换。
3. **文档详情**: 支持下载原文件（PDF/Word），查看文档快照。
4. **智能综述**: 搜索结果页右侧自动生成 Top 文档的 AI 摘要。

## 🛠️ 技术栈

- **语言**: Python, HTML/JS
- **Web 框架**: Flask, Bootstrap 5
- **大数据组件**: Hadoop HDFS, MapReduce, HBase (Thrift)
- **NLP & AI**: Jieba (分词), ZhipuAI GLM-4 (大模型), Scikit-learn (余弦相似度)
- **爬虫**: Requests, BeautifulSoup4, PDFPlumber, Python-docx

## 📝 License

This project is for educational purposes (Big Data System Lab).
