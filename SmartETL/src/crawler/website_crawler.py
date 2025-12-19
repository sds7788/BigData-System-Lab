import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from .html_extractor import HTMLExtractor
from collections import deque
import time
import warnings
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=UserWarning, module='bs4')


class WebsiteCrawler:
    def __init__(self, start_urls, max_depth=3):
        self.start_urls = start_urls
        self.max_depth = max_depth
        self.visited_urls = set()
        self.file_urls = []
        self.html_contents = []
        self.html_extractor = HTMLExtractor()
        self.allowed_domains = set()
        for url in start_urls:
            try:
                domain = urlparse(url).netloc
                if domain:
                    self.allowed_domains.add(domain)
            except:
                continue

        print(f"允许的域名: {list(self.allowed_domains)}")

    def is_allowed_domain(self, url):
        try:
            domain = urlparse(url).netloc
            return domain in self.allowed_domains
        except:
            return False

    def crawl(self, max_crawl, max_html):
        queue = deque([(url, 0) for url in self.start_urls])

        while queue and len(self.file_urls) < max_crawl and len(self.html_contents) < max_html:
            current_url, depth = queue.popleft()

            if depth > self.max_depth:
                continue

            if current_url in self.visited_urls:
                continue

            if not self.is_allowed_domain(current_url):
                print(f"跳过非允许域名的URL: {current_url}")
                continue

            try:
                parsed_url = urlparse(current_url)
                if not parsed_url.scheme or not parsed_url.netloc:
                    print(f"跳过无效URL: {current_url}")
                    continue

                print(f"深度{depth}: 爬取 {current_url}")

                response = requests.get(
                    current_url,
                    timeout=15,
                    verify=False,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                )

                self.visited_urls.add(current_url)

                if response.status_code == 200:
                    content_type = response.headers.get('content-type', '').lower()

                    if 'text/html' in content_type or 'html' in content_type:
                        html_data = self.html_extractor.extract_from_html(response.text, current_url)
                        if html_data and len(html_data['content']) > 200:  # 过滤太短的内容
                            self.html_contents.append(html_data)
                            print(
                                f"  📄 提取网页内容: {html_data.get('title', '无标题')[:50]}... ({len(html_data['content'])} 字符)")

                        #提取文件链接
                        # file_links = self.extract_file_links(current_url, response.text)
                        # if file_links:
                        #
                        #     remaining_slots = max_crawl - len(self.file_urls)
                        #     if remaining_slots > 0:
                        #         file_links_to_add = file_links[:min(len(file_links), remaining_slots)]
                        #         self.file_urls.extend(file_links_to_add)
                        #         print(f"  找到 {len(file_links)} 个文件链接，添加 {len(file_links_to_add)} 个")

                        if depth < self.max_depth and len(self.file_urls) < max_crawl:
                            page_links = self.extract_page_links(current_url, response.text)

                            allowed_page_links = []
                            for link in page_links:
                                if self.is_allowed_domain(link) and link not in self.visited_urls:
                                    allowed_page_links.append(link)

                            for link in allowed_page_links:
                                queue.append((link, depth + 1))
                    else:
                        print(f"  非HTML页面，跳过")

                else:
                    print(f"  HTTP {response.status_code}")

                time.sleep(0.5)

            except Exception as e:
                print(f"  错误: {type(e).__name__}: {str(e)[:50]}")
                continue

        print(f"\n爬取完成，总共找到 {len(self.file_urls)} 个文件链接")
        print(f"访问过的URL数: {len(self.visited_urls)}")
        print(f"提取的网页内容数: {len(self.html_contents)}")  # 新增统计

    def extract_file_links(self, base_url, html_content):
        """提取文件下载链接 - 只爬取PDF和DOCX"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            file_links = []

            for link in soup.find_all('a', href=True):
                href = link['href']
                full_url = urljoin(base_url, href)

                # 只添加PDF和DOCX链接
                url_lower = full_url.lower()
                if url_lower.endswith('.pdf') or url_lower.endswith('.docx'):
                    file_links.append(full_url)

            return list(set(file_links))
        except:
            return []

    def extract_page_links(self, base_url, html_content):
        # 提取页面链接
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            page_links = []

            for link in soup.find_all('a', href=True):
                href = link['href']
                if not href or href.startswith(('#', 'javascript:', 'mailto:')):
                    continue

                try:
                    full_url = urljoin(base_url, href)

                    parsed = urlparse(full_url)
                    if not parsed.scheme or not parsed.netloc:
                        continue

                    url_lower = full_url.lower()
                    if any(url_lower.endswith(ext) for ext in
                           ['.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.zip', '.rar', '.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mp3']):
                        continue

                    if self.is_allowed_domain(full_url) and full_url not in self.visited_urls:
                        page_links.append(full_url)

                except Exception as e:
                    continue

            return list(set(page_links))

        except Exception as e:
            print(f"提取页面链接出错: {e}")
            return []

    def get_results(self):
        return {
            'file_urls': self.file_urls,
            'html_contents': self.html_contents,
            'visited_urls': self.visited_urls
        }