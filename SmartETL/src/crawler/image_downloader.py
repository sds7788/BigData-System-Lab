import os
import requests
from urllib.parse import urlparse
import hashlib
from PIL import Image
from io import BytesIO
import time


class ImageDownloader:
    """图片下载器"""

    def __init__(self, download_dir='data/images'):
        self.download_dir = download_dir
        os.makedirs(download_dir, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })


    def download_image(self, img_url, caption=''):
        try:
            parsed_url = urlparse(img_url)
            if not parsed_url.scheme or not parsed_url.netloc:
                return {'success': False, 'error': '无效URL'}

            url_lower = img_url.lower()

            stat_keywords = ['/visitcount?', '/stat.', 'counter?', 'tracking.']
            if any(keyword in url_lower for keyword in stat_keywords):
                return {'success': False, 'error': '统计链接'}

            response = self.session.get(img_url, timeout=10, stream=True)

            content_type = response.headers.get('content-type', '').lower()

            accepted_types = ['image/', 'application/octet-stream', 'binary/octet-stream']
            if not any(atype in content_type for atype in accepted_types):
                if not any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']):
                    return {'success': False, 'error': f'非图片类型: {content_type}'}

            image_content = response.content

            if len(image_content) < 2048:  # 2KB = 2048 bytes
                return {
                    'success': False,
                    'error': '图片小于2KB（可能为占位符/小图标）',
                    'url': img_url
                }
            img_hash = hashlib.md5(img_url.encode()).hexdigest()[:16]

            ext = os.path.splitext(parsed_url.path)[1]
            if not ext or len(ext) > 5:
                ext = '.jpg'

            filename = f"{img_hash}{ext}"
            filepath = os.path.join(self.download_dir, filename)

            with open(filepath, 'wb') as f:
                f.write(image_content)

            return {
                'success': True,
                'filepath': filepath,
                'metadata': {
                    'id': img_hash,
                    'original_url': img_url,
                    'local_path': filepath,
                    'filename': filename,
                    'caption': caption,
                    'size': os.path.getsize(filepath)
                }
            }

        except Exception as e:
            return {'success': False, 'error': str(e)[:50]}