import json
import csv
import os
import re
from collections import defaultdict
from datetime import datetime


class FileExporter:
    """文件导出类"""

    def __init__(self, output_dir):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def export_jsonl(self, data, filename):
        """导出完整JSONL"""
        path = os.path.join(self.output_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        print(f"    ✓ {filename} ({len(data)}条)")
        return path

    def export_indexing(self, data, filename):
        """导出倒排索引输入"""
        path = os.path.join(self.output_dir, filename)
        max_text_length = 5000

        with open(path, 'w', encoding='utf-8') as f:
            for item in data:
                text_parts = [item['title']]

                text_parts.append(item['full_text'][:max_text_length])

                if 'images' in item and isinstance(item['images'], list):
                    for img in item['images']:
                        if 'caption' in img and img['caption']:
                            text_parts.append(img['caption'])

                text = " ".join(text_parts)
                text = re.sub(r'\s+', ' ', text).strip()
                f.write(f"{item['id']}\t{text}\n")
        print(f"    ✓ {filename}")
        return path

    def export_stats(self, data, filename):
        """导出统计CSV"""
        path = os.path.join(self.output_dir, filename)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'type', 'year', 'source', 'title', 'text_length', 'image_count', 'link_count'])
            for item in data:
                link_count = len(item.get('outlinks', []))

                writer.writerow([
                    item['id'],
                    item['type'],
                    item['year'],
                    item['source'],
                    item['title'][:100],
                    len(item['full_text']),
                    #image_count,
                    link_count
                ])
        print(f"    ✓ {filename}")
        return path

    def export_diff_pairs(self, data, filename):
        """导出版本对比对"""
        groups = defaultdict(list)

        for item in data:
            if item['year']:
                base_title = re.sub(r'\s*\d{4}\s*', '', item['title']).strip()
                if len(base_title) > 2:
                    groups[base_title].append(item)

        path = os.path.join(self.output_dir, filename)
        pairs_count = 0

        with open(path, 'w', encoding='utf-8') as f:
            for base_title, items in groups.items():
                if len(items) >= 2:
                    items.sort(key=lambda x: x['year'])

                    for i in range(len(items) - 1):
                        pair = {
                            'base_title': base_title,
                            'year1': items[i]['year'],
                            'year2': items[i + 1]['year'],
                            'id1': items[i]['id'],
                            'id2': items[i + 1]['id'],
                            'title1': items[i]['title'],
                            'title2': items[i + 1]['title'],
                            'text1': items[i]['full_text'][:1000],
                            'text2': items[i + 1]['full_text'][:1000]
                        }
                        f.write(json.dumps(pair, ensure_ascii=False) + '\n')
                        pairs_count += 1

        print(f"    ✓ {filename} ({pairs_count}个对比对)")
        return path

    def export_stats_json(self, stats, filename):
        """导出统计JSON"""
        path = os.path.join(self.output_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print(f"    ✓ {filename}")
        return path

    def generate_readme(self, stats, data):
        """生成README"""
        path = os.path.join(self.output_dir, "README.md")

        type_dist = "\n".join([f"- {k}: {v} ({v / stats['total'] * 100:.1f}%)"
                               for k, v in sorted(stats['types'].items(), key=lambda x: x[1], reverse=True)])

        year_items = sorted(stats['years'].items(), key=lambda x: x[1], reverse=True)[:10]
        year_dist = "\n".join([f"- {k}: {v}" for k, v in year_items])

        source_items = sorted(stats['websites'].items(), key=lambda x: x[1], reverse=True)[:]
        source_dist = "\n".join([f"- {k}: {v}" for k, v in source_items])

        readme_content = f"""# 第二阶段数据输出

## 数据概览
- **总文档数**: {stats['total']}
- **文本长度**: 平均 {stats.get('avg_text_length', 0):.0f} 字符
- **年份范围**: {stats.get('min_year', 'N/A')} - {stats.get('max_year', 'N/A')}
- **图片统计**: 共 {stats.get('total_images', 0)} 张，{stats.get('has_images', 0)} 篇文档有图片
- **链接统计**: 共 {stats.get('total_links', 0)} 个，{stats.get('has_links', 0)} 篇文档有链接
- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 文件说明

### 1. `documents.jsonl` - 完整数据
所有清洗后的原始数据，每条记录包含：
{{
  "id": "文档唯一ID",
  "title": "文档标题",
  "type": "文档类型（html/pdf/docx）",
  "url": "原始URL",
  "full_text": "完整文本内容",
  "year": "年份",
  "source": "来源网站",
  "images": [  // 新增：图片信息
    {{
      "id": "图片ID",
      "url": "图片原始URL",
      "caption": "图片说明文字",
      "local_path": "本地存储路径"
    }}
  ],
  "outlinks": [  // 新增：出站链接（用于PageRank）
    {{
      "url": "链接URL",
      "text": "链接文本",
      "is_internal": "是否为站内链接"
    }}
  ]
}}

### 2. `for_indexing.txt` - 倒排索引输入
格式：`<文档ID>TAB<文本内容>`
- 用于MapReduce Job A（倒排索引）
- 文本包含：标题、部分正文、图片caption
- 图片caption参与索引，支持图表搜索

### 3. `stats_input.csv` - 统计分析输入
CSV格式，新增字段：
- `image_count`: 图片数量
- `link_count`: 链接数量
- 用于MapReduce Job B（统计）和PageRank分析

### 4. `diff_pairs.jsonl` - 版本对比输入
相同主题不同年份的文档对，用于：
- MapReduce Job C（版本差异）
- 每个对包含两个版本的文本

### 5. `stats_summary.json` - 统计摘要
详细的统计数据JSON，包含图片和链接统计

## 数据分布

### 按文档类型
{type_dist}

### 按年份分布（前10）
{year_dist}

### 按来源网站（前10）
{source_dist}

### 新增统计
- 平均每文档图片数: {stats.get('avg_images_per_doc', 0):.2f}
- 平均每文档链接数: {stats.get('avg_links_per_doc', 0):.2f}
- 有图片的文档比例: {stats.get('doc_with_images_ratio', 0)*100:.1f}%
- 有链接的文档比例: {stats.get('doc_with_links_ratio', 0)*100:.1f}%

## 使用方法

# 倒排索引（包含图片caption）
hadoop jar your-job.jar input=for_indexing.txt output=index_result

# 统计分析（包含图片和链接统计）
hadoop jar your-job.jar input=stats_input.csv output=stats_result

# 版本对比
hadoop jar your-job.jar input=diff_pairs.jsonl output=diff_result

# PageRank计算（使用outlinks字段）
# 邻接表可通过build_adjacency_list.py生成
        """

        with open(path, 'w', encoding='utf-8') as f:
            f.write(readme_content)
