import requests
import os
import json
from urllib.parse import urlparse
import hashlib


class FileDownloader:
    def __init__(self, download_dir):
        self.download_dir = download_dir
        self.url_mapping_file = os.path.join(download_dir, 'url_mapping.json')
        os.makedirs(download_dir, exist_ok=True)

    def _save_url_mapping(self, filepath, url):
        """保存URL映射到文件"""
        mapping = {}
        if os.path.exists(self.url_mapping_file):
            try:
                with open(self.url_mapping_file, 'r', encoding='utf-8') as f:
                    mapping = json.load(f)
            except:
                mapping = {}

        mapping[filepath] = url

        try:
            with open(self.url_mapping_file, 'w', encoding='utf-8') as f:
                json.dump(mapping, f, ensure_ascii=False, indent=2)
        except:
            pass

    def download_file(self, url):
        # 下载文件到本地
        try:
            response = requests.get(url, stream=True, timeout=30)

            if response.status_code == 200:
                url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                filename = urlparse(url).path.split('/')[-1]

                if not filename:
                    filename = f"file_{url_hash}"

                content_type = response.headers.get('content-type', '')
                if 'pdf' in content_type and not filename.lower().endswith('.pdf'):
                    filename += '.pdf'
                elif 'word' in content_type and not filename.lower().endswith('.docx'):
                    filename += '.docx'

                filepath = os.path.join(self.download_dir, filename)

                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                # 下载成功后立即保存URL映射
                self._save_url_mapping(filepath, url)

                return {
                    'success': True,
                    'filepath': filepath,
                    'url': url,
                    'size': os.path.getsize(filepath)
                }
            else:
                return {'success': False, 'error': f'HTTP {response.status_code}'}

        except Exception as e:
            return {'success': False, 'error': str(e)}