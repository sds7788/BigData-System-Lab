import os
import sys
import json
import hashlib
import yaml
import re
import pdfplumber
import docx
from datetime import datetime
from multiprocessing import Pool
from crawler.website_crawler import WebsiteCrawler
from crawler.file_downloader import FileDownloader
from processors.text_cleaner import clean_text
from utils.data_formatter import generate_jsonl_entry
from processors.document_processor import DocumentProcessor
from crawler.image_downloader import ImageDownloader


def load_config():
    """加载配置文件"""
    with open('config/config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def extract_source_website(original_url):
    """提取来源网站"""
    if not original_url:
        return "unknown"

    try:
        match = re.search(r'https?://([^/]+)', original_url)
        if match:
            domain = match.group(1)
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
    except:
        pass

    return "ustc.edu.cn"


def get_processed_files(output_path):
    """获取已处理的文件列表（从JSONL文件中读取）"""
    processed_files = set()
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        doc = json.loads(line)
                        # 从url字段提取文件路径
                        url = doc.get('url', '')
                        if url.startswith('file://'):
                            file_path = url[7:]  # 去掉'file://'前缀
                            # 使用文件路径的MD5作为唯一标识
                            file_id = hashlib.md5(file_path.encode()).hexdigest()
                            processed_files.add(file_id)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"读取已处理文件列表时出错: {e}")

    return processed_files


def process_documents_in_batches(downloaded_files, file_url_mapping, config,
                                 batch_size=20, resume=False):
    """
    分批处理文档文件，支持断点续传

    Args:
        downloaded_files: 已下载的文件路径列表
        file_url_mapping: 文件路径到原始URL的映射
        config: 配置字典
        batch_size: 每批处理的文件数
        resume: 是否断点续传模式
    """
    output_path = config['output']['jsonl_path']
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    total_files = len(downloaded_files)

    # 断点续传：获取已处理的文件
    processed_file_ids = set()
    if resume:
        processed_file_ids = get_processed_files(output_path)
        print(f"断点续传模式：已处理 {len(processed_file_ids)} 个文件")

    # 计算需要处理的总批次
    total_batches = (total_files + batch_size - 1) // batch_size
    processed_count = 0

    print(f"\n开始分批处理文档...")
    print(f"总文件数: {total_files}")
    print(f"批次大小: {batch_size}")
    print(f"总批次数: {total_batches}")
    print(f"断点续传: {'是' if resume else '否'}")
    print("=" * 60)

    # 以追加模式打开文件（断点续传时追加，否则新建）
    file_mode = 'a' if resume and os.path.exists(output_path) else 'w'

    with open(output_path, file_mode, encoding='utf-8') as f_out:
        for batch_num in range(total_batches):
            # 计算当前批次的文件切片
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, total_files)
            batch_files = downloaded_files[start_idx:end_idx]

            print(f"\n批次 {batch_num + 1}/{total_batches} (文件 {start_idx + 1}-{end_idx})")
            print("-" * 40)

            batch_processed = 0
            batch_skipped = 0

            # 处理当前批次
            for i, file_path in enumerate(batch_files, 1):
                file_index = start_idx + i
                filename = os.path.basename(file_path)

                # 检查是否已处理过（断点续传）
                file_id = hashlib.md5(file_path.encode()).hexdigest()
                if file_id in processed_file_ids:
                    print(f"  [{file_index}/{total_files}] 已跳过: {filename[:40]}")
                    batch_skipped += 1
                    continue

                original_url = file_url_mapping.get(file_path)

                print(f"  [{file_index}/{total_files}] 处理: {filename[:40]}...", end="", flush=True)

                try:
                    # 处理单个文档
                    result = process_single_document_sync(
                        file_path, config, original_url, file_index, total_files
                    )

                    if result:
                        f_out.write(result + '\n')
                        batch_processed += 1
                        processed_count += 1
                        processed_file_ids.add(file_id)  # 记录已处理
                        print(" ✓")
                    else:
                        print(" ✗")

                except Exception as e:
                    print(f" ✗ 错误: {str(e)[:30]}")

            # 批次统计
            print(
                f"  本批次结果: 成功 {batch_processed}, 跳过 {batch_skipped}, 失败 {len(batch_files) - batch_processed - batch_skipped}")

            # 显示总体进度
            current_progress = (batch_num + 1) * 100 // total_batches
            bar_length = 30
            filled = bar_length * (batch_num + 1) // total_batches
            bar = '█' * filled + '░' * (bar_length - filled)
            print(f"  总体进度: [{bar}] {current_progress}% ({processed_count}/{total_files})")

            # 每批处理后强制垃圾回收
            import gc
            gc.collect()

    return processed_count, output_path


def process_single_document_sync(file_path, config, original_url=None,
                                 file_index=0, total_files=0):
    """同步处理单个文档（用于分批处理）"""
    try:
        filename = os.path.basename(file_path)
        if filename in ["80ee4a5453074bddab2bb20afad4bf7c.pdf"]:
            return None
        # 检查文件格式
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext not in ['.pdf', '.docx']:
            return None

        # 处理文档
        processor = DocumentProcessor(file_path, original_url=original_url)
        doc_data = processor.process()

        if not doc_data:
            return None

        # 清洗文本
        doc_data['full_text'] = clean_text(doc_data['full_text'])

        # 检查文本是否有效
        if not doc_data['full_text'] or len(doc_data['full_text'].strip()) < 50:
            return None

        # 添加其他信息
        doc_data.update({
            'source_website': original_url if original_url else "unknown"
        })

        return generate_jsonl_entry(doc_data)

    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        return None


def process_single_document(file_path, config, original_url=None):
    """处理单个文档文件（用于多进程）"""
    try:
        # 检查文件格式
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext not in ['.pdf', '.docx']:
            return None

        # 处理文档
        processor = DocumentProcessor(file_path, original_url=original_url)
        doc_data = processor.process()

        if not doc_data:
            return None

        # 清洗文本
        doc_data['full_text'] = clean_text(doc_data['full_text'])

        # 检查文本是否有效
        if not doc_data['full_text'] or len(doc_data['full_text'].strip()) < 50:
            return None

        # 添加其他信息
        doc_data.update({
            'source_website': original_url if original_url else "unknown"
        })

        return generate_jsonl_entry(doc_data)

    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        return None


def scan_downloaded_files(download_dir, output_path):
    """扫描已下载的文件，构建文件列表和URL映射"""
    downloaded_files = []
    file_url_mapping = {}

    # 从URL映射文件中读取映射
    url_mapping_file = os.path.join(download_dir, 'url_mapping.json')
    url_mapping = {}
    if os.path.exists(url_mapping_file):
        try:
            with open(url_mapping_file, 'r', encoding='utf-8') as f:
                url_mapping = json.load(f)
        except:
            url_mapping = {}

    # 从JSONL中补充URL映射（处理一些历史记录）
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        doc = json.loads(line)
                        url = doc.get('url', '')
                        if url.startswith('file://'):
                            file_path = url[7:]
                            # 尝试从不同字段获取原始URL
                            original_url = doc.get('metadata', {}).get('original_url', '')
                            if not original_url:
                                original_url = doc.get('original_url', '')
                            if not original_url:
                                original_url = doc.get('source_website', '')
                            if original_url and original_url != 'unknown':
                                url_mapping[file_path] = original_url
                    except:
                        continue
        except:
            pass

    # 扫描下载目录中的文件
    for root, dirs, files in os.walk(download_dir):
        for file in files:
            if file.lower().endswith(('.pdf', '.docx')):
                file_path = os.path.join(root, file)
                downloaded_files.append(file_path)

                # 优先从URL映射文件获取URL，否则使用JSONL中的，最后用默认值
                original_url = url_mapping.get(file_path, "unknown")
                file_url_mapping[file_path] = original_url

    return downloaded_files, file_url_mapping


def process_html_contents(html_contents, output_path, html_output_path=None, resume=False):
    """处理网页内容，生成JSONL记录"""
    if html_output_path is None:
        html_output_path = output_path

    processed_count = 0
    total_images = 0  # 新增：统计图片数量
    total_links = 0  # 新增：统计链接数量

    # 确保输出目录存在
    os.makedirs(os.path.dirname(html_output_path), exist_ok=True)

    # 获取已处理的网页
    processed_ids = set()
    if resume and os.path.exists(html_output_path):
        try:
            with open(html_output_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        doc = json.loads(line)
                        processed_ids.add(doc.get('id', ''))
                    except:
                        continue
        except:
            pass

    file_mode = 'a' if resume and os.path.exists(html_output_path) else 'w'

    with open(html_output_path, file_mode, encoding='utf-8') as f_out:
        for html_data in html_contents:
            # 跳过已处理的
            if html_data['id'] in processed_ids:
                continue

            # 更新JSONL条目格式
            entry = {
                'id': html_data['id'],
                'title': html_data['title'],
                'type': 'html',
                'url': html_data['url'],
                'full_text': clean_text(html_data['content']),
                #'extract_date': html_data.get('extract_date', ''),
                #'source_website': html_data.get('source_website', ''),
                #'length': html_data.get('length', 0),
                # 新增字段
                'images': html_data.get('images', []),  # 图片数据
                'outlinks': html_data.get('outlinks', []),  # 出链数据（用于PageRank）
                'metadata': {
                    #'has_images': len(html_data.get('images', [])) > 0,
                    'image_count': len(html_data.get('images', [])),
                    'link_count': len(html_data.get('outlinks', [])),
                    'internal_links': len([l for l in html_data.get('outlinks', [])
                                           if l.get('is_internal', False)]),
                    'external_links': len([l for l in html_data.get('outlinks', [])
                                           if not l.get('is_internal', True)])
                }
            }

            # 统计
            total_images += len(entry['images'])
            total_links += len(entry['outlinks'])

            # 写入文件
            json_line = json.dumps(entry, ensure_ascii=False)
            f_out.write(json_line + '\n')
            processed_count += 1

            print(f"  处理网页: {html_data['title'][:40]}...")
            print(f"    图片: {len(entry['images'])} 张, 链接: {len(entry['outlinks'])} 个")

    # 新增：单独保存PageRank所需的图结构
    # 修复：将 _save_pagerank_data 改为独立函数
    # pagerank_file = html_output_path.replace('.jsonl', '_pagerank.json')
    # save_pagerank_data(html_contents, pagerank_file)

    return processed_count, html_output_path, total_images, total_links



def main(resume=False, batch_size=20):
    """主程序入口

    Args:
        resume: 是否断点续传模式
        batch_size: 分批处理的批次大小
    """
    config = load_config()
    output_path = config['output']['jsonl_path']
    download_dir = config['crawler']['download_dir']
    html_output_path = config['output'].get('html_jsonl_path')

    image_download_dir = config['crawler'].get('image_download_dir', 'data/images')

    # 确保下载目录存在
    os.makedirs(download_dir, exist_ok=True)
    os.makedirs(image_download_dir, exist_ok=True)

    # 自动检测是否续传
    if not resume and os.path.exists(output_path):
        # 询问用户
        print("发现已存在的输出文件，是否断点续传？")
        print("1. 是（跳过已处理的文件）")
        print("2. 否（重新开始，覆盖旧文件）")

        choice = input("请选择 (1/2): ").strip()
        resume = (choice == "1")

    if resume:
        print("=" * 60)
        print("断点续传模式：扫描已下载文件...")
        # 直接扫描已下载的文件
        downloaded_files, file_url_mapping = scan_downloaded_files(
            download_dir, output_path
        )

        print(f"找到 {len(downloaded_files)} 个已下载文件")

        # 过滤已处理的文件
        processed_file_ids = get_processed_files(output_path)
        unprocessed_files = []
        unprocessed_mapping = {}

        for file_path in downloaded_files:
            file_id = hashlib.md5(file_path.encode()).hexdigest()
            if file_id not in processed_file_ids:
                unprocessed_files.append(file_path)
                unprocessed_mapping[file_path] = file_url_mapping.get(file_path, "unknown")
            else:
                print(f"跳过已处理文件: {os.path.basename(file_path)}")

        downloaded_files = unprocessed_files
        file_url_mapping = unprocessed_mapping

        if not downloaded_files:
            print("没有需要处理的文件！")
            return

        print(f"准备处理 {len(downloaded_files)} 个未处理文件")

    else:
        print("=" * 60)
        print("全新开始模式：重新爬取和下载...")
        # 1. 爬取网站获取文件链接
        print("开始爬取网站...")
        crawler = WebsiteCrawler(
            config['crawler']['start_urls'],
            config['crawler']['max_depth']
        )
        max_crawl = config['crawler'].get('max_crawl', 100)
        max_html = config['crawler'].get('max_html', 100)
        max_images = config['crawler'].get('max_images', 50)
        crawler.crawl(max_crawl=max_crawl, max_html=max_html)

        results = crawler.get_results()
        file_urls = results['file_urls']
        html_contents = results['html_contents']  # 新增：获取网页内容

        if html_contents and config['crawler'].get('download_images', False):
            print(f"\n开始提取和下载图片...")
            image_downloader = ImageDownloader(image_download_dir)
            downloaded_images = 0

            for html_data in html_contents:
                images = html_data.get('images', [])
                if not images:
                    continue

                print(f"  处理网页 {html_data.get('title', '无标题')[:30]}... 找到 {len(images)} 张图片")

                # 限制每个网页下载的图片数量
                max_per_page = config['crawler'].get('max_images_per_page', 5)
                images_to_download = images[:max_per_page]

                for img_data in images_to_download:
                    if downloaded_images >= max_images:
                        print(f"  已达到最大图片下载限制 ({max_images})")
                        break

                    img_url = img_data.get('url', '')
                    if not img_url:
                        continue

                    # 简化：只保留必要的图片信息，不生成额外JSONL
                    print(f"    下载图片: {img_url[:50]}...", end="", flush=True)
                    result = image_downloader.download_image(img_url, img_data.get('caption', ''))

                    if result['success']:
                        downloaded_images += 1
                        # 只更新必要的字段到HTML数据中
                        img_data['downloaded'] = True
                        img_data['local_path'] = result['metadata']['local_path']
                        img_data['file_size'] = result['metadata']['size']
                        # 保留原有的id、url、alt、title、caption等字段
                        print(" ✓")
                    else:
                        print(f" ✗ ({result.get('error', '未知错误')[:30]})")
                        # 即使下载失败，也保留图片信息，只是不标记为下载
                        img_data['downloaded'] = False

                if downloaded_images >= max_images:
                    break

            print(f"图片下载完成: 成功下载 {downloaded_images} 张图片")
            print(f"图片保存目录: {image_download_dir}")

            # 处理网页内容
        if html_contents:
            print(f"\n开始处理网页内容...")
            processed_html_count, html_output_file, total_images, total_links = process_html_contents(
                html_contents,
                output_path,
                html_output_path=html_output_path,
                resume=resume
            )
            print(f"处理了 {processed_html_count} 个网页内容")
            print(f"总共提取 {total_images} 张图片，{total_links} 个链接")

            # 文件下载处理（原有代码）
        if not crawler.file_urls:
            print("没有找到文件链接！")
            return

        print(f"找到 {len(crawler.file_urls)} 个文件，开始下载...")
        downloader = FileDownloader(download_dir)

        downloaded_files = []
        file_url_mapping = {}

        max_download = config['crawler'].get('max_download', 50)
        urls_to_download = crawler.file_urls[:max_download]

        for i, url in enumerate(urls_to_download):
            print(f"  下载 [{i + 1}/{len(urls_to_download)}]: {url[:60]}...")
            result = downloader.download_file(url)
            if result['success']:
                downloaded_files.append(result['filepath'])
                file_url_mapping[result['filepath']] = url
            else:
                print(f"    ❌ 下载失败: {result.get('error', '未知错误')}")

        if not downloaded_files:
            print("没有成功下载任何文件！")
            return

    # 使用分批处理（不再需要use_batch参数）
    processed_count, final_output_path = process_documents_in_batches(
        downloaded_files, file_url_mapping, config,
        batch_size=batch_size, resume=resume
    )

    # 显示最终统计
    print("\n" + "=" * 60)
    print("处理完成！")
    print(f"✓ 总处理文件数: {len(downloaded_files)}")
    print(f"✓ 成功处理文档数: {processed_count}")
    print(f"✓ 输出文件: {final_output_path}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='文档智能采集系统')
    parser.add_argument('--resume', action='store_true',
                        help='断点续传模式（跳过已处理的文件）')
    parser.add_argument('--batch-size', type=int, default=20,
                        help='分批处理的批次大小（默认20）')

    args = parser.parse_args()

    print("=" * 60)
    print("中国科学技术大学文档智能采集系统")
    print("=" * 60)
    print(f"运行模式: {'断点续传' if args.resume else '全新开始'}")
    print(f"批次大小: {args.batch_size}")
    print("=" * 60)

    # 传递参数到主函数
    main(resume=args.resume, batch_size=args.batch_size)