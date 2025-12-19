import json
import re
from collections import defaultdict


class DataProcessor:
    """数据处理类"""

    def __init__(self, config):
        self.config = config

    def load_and_process(self):
        data = []

        try:
            with open(self.config.input_file, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f, 1):
                    if not line.strip():
                        continue

                    try:
                        item = json.loads(line)

                        cleaned = self._clean_item(item)
                        if cleaned:
                            data.append(cleaned)

                    except json.JSONDecodeError:
                        print(f"警告：第 {i} 行JSON格式错误")

                    if i % 100 == 0:
                        print(f"    已处理 {i} 行...")

        except FileNotFoundError:
            print(f"错误：找不到文件 {self.config.input_file}")
            return []

        return data

    def _clean_item(self, item):
        """清理单个数据项"""
        if 'id' not in item or 'full_text' not in item:
            return None

        if len(item['full_text'].strip()) < self.config.min_text_length:
            return None

        cleaned = {
            'id': item['id'],
            'title': item.get('title', '无标题').strip(),
            'type': item.get('type', 'unknown'),
            'url': item.get('url', ''),
            'full_text': item['full_text'].strip(),
            'year': self._extract_year(item),
            'source': self._extract_source(item.get('url', ''))
        }

        if 'images' in item:
            cleaned_images = []
            for img in item['images']:
                cleaned_img = {
                    'id': img.get('id'),
                    'url': img.get('url')
                }
                if 'caption' in img and img['caption']:
                    cleaned_img['caption'] = img['caption']
                if 'local_path' in img:
                    cleaned_img['local_path'] = img['local_path']
                cleaned_images.append(cleaned_img)
            cleaned['images'] = cleaned_images

        if 'outlinks' in item:
            cleaned_outlinks = []
            for link in item['outlinks']:
                cleaned_link = {
                    'url': link.get('url'),
                    'text': link.get('text', ''),
                    'is_internal': link.get('is_internal', False)
                }
                cleaned_outlinks.append(cleaned_link)
            cleaned['outlinks'] = cleaned_outlinks

        return cleaned

    def _extract_year(self, item):
        """提取年份"""
        if 'year' in item and item['year']:
            year_str = str(item['year'])
            match = re.search(self.config.year_pattern, year_str)
            if match:
                return match.group()

        title = item.get('title', '')
        match = re.search(self.config.year_pattern, title)
        if match:
            return match.group()

        text = item.get('full_text', '')[:500]
        match = re.search(self.config.year_pattern, text)
        if match:
            return match.group()

        return ''

    def _extract_source(self, url):
        """从URL提取来源网站"""
        if not url:
            return 'unknown'

        url = url.replace('http://', '').replace('https://', '')
        domain = url.split('/')[0]
        if domain.startswith('www.'):
            domain = domain[4:]

        return domain

    def calculate_stats(self, data):
        """计算统计数据"""
        stats = {
            'total': len(data),
            'types': defaultdict(int),
            'years': defaultdict(int),
            'websites': defaultdict(int),
            'text_lengths': [],
            'min_year': None,
            'max_year': None,
            'total_images': 0,
            'total_links': 0,
            'has_images': 0,
            'has_links': 0
        }

        for item in data:
            stats['types'][item['type']] += 1

            if item['year']:
                stats['years'][item['year']] += 1

                year_int = int(item['year'])
                if stats['min_year'] is None or year_int < stats['min_year']:
                    stats['min_year'] = year_int
                if stats['max_year'] is None or year_int > stats['max_year']:
                    stats['max_year'] = year_int

            stats['websites'][item['source']] += 1

            stats['text_lengths'].append(len(item['full_text']))

            image_count = len(item.get('images', []))
            if image_count > 0:
                stats['has_images'] += 1
                stats['total_images'] += image_count

            link_count = len(item.get('outlinks', []))
            if link_count > 0:
                stats['has_links'] += 1
                stats['total_links'] += link_count

        if stats['text_lengths']:
            stats['avg_text_length'] = sum(stats['text_lengths']) / len(stats['text_lengths'])
            stats['max_text_length'] = max(stats['text_lengths'])
            stats['min_text_length'] = min(stats['text_lengths'])

        if stats['total'] > 0:
            stats['avg_images_per_doc'] = stats['total_images'] / stats['total']
            stats['avg_links_per_doc'] = stats['total_links'] / stats['total']
            stats['doc_with_images_ratio'] = stats['has_images'] / stats['total']
            stats['doc_with_links_ratio'] = stats['has_links'] / stats['total']

        return stats