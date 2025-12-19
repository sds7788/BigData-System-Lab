import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime
import hashlib
from urllib.parse import urlparse, urljoin


class HTMLExtractor:
    """HTML网页内容提取器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def extract_from_url(self, url):
        """从URL提取网页内容"""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return self.extract_from_html(response.text, url)
        except Exception as e:
            print(f"提取网页内容失败 {url}: {e}")
            return None

    def extract_from_html(self, html_content, url):
        """从HTML文本提取内容"""
        try:
            if isinstance(html_content, bytes):
                import chardet
                result = chardet.detect(html_content)
                encoding = result['encoding'] if result['confidence'] > 0.7 else 'utf-8'
                html_content = html_content.decode(encoding, errors='ignore')

            soup = BeautifulSoup(html_content, 'html.parser', from_encoding='utf-8')

            for script in soup(["script", "style", "header", "footer", "nav", "iframe"]):
                script.decompose()

            title = ""
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
                title = re.sub(r'[^\u4e00-\u9fff\w\s\-\.\(\)\[\]]', '', title)

            chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', title))
            total_chars = len(title)
            if total_chars > 0:
                chinese_ratio = chinese_chars / total_chars
                if total_chars > 5 and chinese_ratio < 0.2:
                    return None
            content = self._extract_main_content(soup)

            content = self._clean_text(content)

            if len(content) < 100:
                print(f"内容太短，跳过: {url}")
                return None

            paragraphs = content.split('\n')
            if len(paragraphs) > 10:
                unique_rate = len(set(paragraphs)) / len(paragraphs)
                if unique_rate < 0.3:
                    print(f"内容重复率过高 ({unique_rate:.1%})，跳过: {url}")
                    return None

            images_data = self._extract_images(soup, url)

            return {
                'id': f"html_{hashlib.md5(url.encode()).hexdigest()[:16]}",
                'url': url,
                'title': title,
                'content': content,
                'extract_date': datetime.now().isoformat(),
                'source_website': self._extract_domain(url),
                'length': len(content),

                'images': images_data,
                'outlinks': self._extract_outlinks(soup, url)
            }

        except Exception as e:
            print(f"解析HTML失败 {url}: {e}")
            return None

    def _extract_main_content(self, soup):
        """智能提取正文内容，避免重复"""
        selectors = ['main', 'article', '.content', '.main-content',
                     '#content', '.article', '.post-content']

        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                main_element = max(elements, key=lambda x: len(x.get_text()))
                text = main_element.get_text(separator='\n', strip=True)
                if len(text) > 200:
                    return text

        paragraphs = soup.find_all(['p', 'div'])
        texts = []
        seen_texts = set()

        for p in paragraphs:
            text = p.get_text(strip=True)
            if len(text) > 20:
                if text not in seen_texts:
                    seen_texts.add(text)
                    texts.append(text)

        return '\n'.join(texts)

    def _clean_text(self, text):
        """清理文本"""
        text = re.sub(r'\s+', ' ', text)

        patterns = [
            r'版权所有.*',
            r'Copyright.*',
            r'地址：.*',
            r'邮政编码：.*',
            r'联系电话：.*',
            r'邮箱：.*',
            r'©.*',
        ]

        for pattern in patterns:
            text = re.sub(pattern, '', text)

        paragraphs = text.split('\n')
        unique_paragraphs = []
        seen = set()

        for para in paragraphs:
            para = para.strip()
            if para and para not in seen:
                seen.add(para)
                unique_paragraphs.append(para)

        return '\n'.join(unique_paragraphs)

    def _extract_domain(self, url):
        """提取域名"""
        try:
            domain = urlparse(url).netloc
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except:
            return "unknown"

    def _extract_images(self, soup, base_url):
        """提取图片及其caption"""
        images = []

        for img in soup.find_all('img'):
            try:
                img_data = {}

                src = img.get('src', '')
                if not src:
                    continue

                img_url = urljoin(base_url, src)
                img_data['url'] = img_url

                alt = img.get('alt', '').strip()
                if alt:
                    img_data['alt'] = alt

                title = img.get('title', '').strip()
                if title:
                    img_data['title'] = title

                caption = self._extract_image_caption(img)
                if caption:
                    img_data['caption'] = caption

                if self._is_non_image_url(img_url):
                    continue

                if img_data.get('url'):
                    img_data['id'] = hashlib.md5(img_url.encode()).hexdigest()[:8]
                    images.append(img_data)

            except Exception as e:
                continue

        return images

    def _extract_image_caption(self, img_tag):
        """智能提取图片caption"""
        caption = ""

        parent = img_tag.parent
        if parent and parent.name == 'figure':
            figcaption = parent.find('figcaption')
            if figcaption:
                caption = figcaption.get_text(strip=True)
                if caption:
                    return caption

        if not caption:
            current = img_tag
            for _ in range(3):
                if current.parent:
                    current = current.parent
                    all_text = current.get_text(strip=True)
                    img_text = img_tag.get_text(strip=True)
                    if all_text and all_text != img_text:
                        if 10 < len(all_text) < 300:
                            text_lines = all_text.split('\n')
                            for line in text_lines:
                                line = line.strip()
                                if line and len(line) > 10 and len(line) < 200:
                                    caption = line
                                    break

        if not caption:
            next_sib = img_tag.find_next_sibling(['p', 'div', 'span'])
            if next_sib:
                text = next_sib.get_text(strip=True)
                if 10 < len(text) < 200:
                    caption = text
            elif img_tag.previous_sibling:
                prev_sib = img_tag.find_previous_sibling(['p', 'div', 'span'])
                if prev_sib:
                    text = prev_sib.get_text(strip=True)
                    if 10 < len(text) < 200:
                        caption = text

        return caption

    def _is_non_image_url(self, url):
        """判断是否为非图片URL（如访问统计）"""
        url_lower = url.lower()
        non_image_keywords = [
            'visitcount', 'counter', 'stat.', 'track', 'pixel',
            'beacon', 'analytics', 'monitor'
        ]

        for keyword in non_image_keywords:
            if keyword in url_lower:
                return True

        if '?' in url_lower:
            query_part = url_lower.split('?')[1]
            if any(keyword in query_part for keyword in ['count', 'visit', 'id=', 'type=']):
                # 但也要确保它确实是图片URL（排除误判）
                if not any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                    return True

        return False

    def _extract_outlinks(self, soup, base_url):
        """提取出站链接（用于PageRank）"""
        outlinks = []

        for link in soup.find_all('a', href=True):
            try:
                href = link.get('href', '').strip()
                if not href:
                    continue

                full_url = urljoin(base_url, href)

                normalized_url = self._normalize_url(full_url)

                if normalized_url:
                    link_text = link.get_text(strip=True)

                    outlinks.append({
                        'url': normalized_url,
                        'text': link_text[:100] if link_text else '',
                        'is_internal': self._is_internal_link(normalized_url, base_url)
                    })

            except Exception:
                continue

        unique_outlinks = []
        seen = set()
        for link in outlinks:
            if link['url'] not in seen:
                seen.add(link['url'])
                unique_outlinks.append(link)

        return unique_outlinks

    def _normalize_url(self, url):
        """规范化URL（用于PageRank）"""
        try:
            from urllib.parse import urlparse, urlunparse

            parsed = urlparse(url)

            clean_url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                '',
                '',
                ''
            ))

            if not clean_url.startswith(('http://', 'https://')):
                return None

            clean_url = clean_url.replace('http://', 'https://')

            if clean_url.endswith('/') and len(clean_url) > 8:
                clean_url = clean_url[:-1]

            return clean_url

        except Exception:
            return None

    def _is_internal_link(self, url, base_url):
        """判断是否是内部链接"""
        try:
            from urllib.parse import urlparse

            base_domain = urlparse(base_url).netloc
            target_domain = urlparse(url).netloc

            if not target_domain:
                return True

            base_main = base_domain.replace('www.', '')
            target_main = target_domain.replace('www.', '')

            return base_main == target_main

        except Exception:
            return False