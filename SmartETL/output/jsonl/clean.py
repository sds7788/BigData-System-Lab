
import os

def process_jsonl1(input_file, output_file):
    """
    处理JSONL文件：
    1. 删除title不含中文的记录
    2. 按full_text长度排序
    3. 输出为新的JSONL文件
    """

    if not os.path.exists(input_file):
        print(f"错误：输入文件 '{input_file}' 不存在")
        return False

    try:
        records = []

        with open(input_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)

                    if 'title' not in record or 'full_text' not in record:
                        print(f"警告：第{line_num}行缺少必需字段，跳过")
                        continue

                    title = record.get('title', '')
                    full_text = record.get('full_text', '')

                    has_chinese = any('\u4e00' <= char <= '\u9fff' for char in title)

                    if has_chinese:
                        text_length = len(str(full_text))
                        record['_full_text_length'] = text_length
                        records.append(record)

                except json.JSONDecodeError as e:
                    print(f"警告：第{line_num}行JSON解析错误: {e}，跳过")
                    continue

        if not records:
            print("没有符合条件的记录")
            return False

        #records.sort(key=lambda x: x['_full_text_length'])
        records.sort(key=lambda x: x.get('url', ''))

        with open(output_file, 'w', encoding='utf-8') as f:
            for record in records:
                if '_full_text_length' in record:
                    del record['_full_text_length']

                f.write(json.dumps(record, ensure_ascii=False) + '\n')

        print(f"处理完成！")
        print(f"输入文件: {input_file}")
        print(f"输出文件: {output_file}")
        print(f"总记录数: {len(records)}")

        return True

    except Exception as e:
        print(f"处理过程中发生错误: {e}")
        return False

import re

def extract_year_from_text(text):
    """从文本中提取年份"""

    year_patterns = [
        r'(?:19|20)\d{2}',  # 1900-2099
        r'[一二三四五六七八九零〇]{4}年'
    ]

    years = []
    for pattern in year_patterns:
        matches = re.findall(pattern, text)
        years.extend(matches)

    if years:
        from collections import Counter
        year_counts = Counter(years)
        most_common = year_counts.most_common(1)[0][0]

        if '年' in most_common:
            chinese_to_num = {'〇': '0', '一': '1', '二': '2', '三': '3',
                              '四': '4', '五': '5', '六': '6', '七': '7',
                              '八': '8', '九': '9', '零': '0'}
            chinese_year = most_common.replace('年', '')
            num_year = ''.join(chinese_to_num.get(c, c) for c in chinese_year)
            return num_year if len(num_year) == 4 else None

        return most_common if 1900 <= int(most_common) <= 2100 else None

    return None


def add_year_field(input_file, output_file):
    """为JSONL文件添加year字段"""
    updated_count = 0
    total_count = 0

    with open(input_file, 'r', encoding='utf-8') as f_in, \
            open(output_file, 'w', encoding='utf-8') as f_out:

        for line in f_in:
            if not line.strip():
                continue

            total_count += 1
            data = json.loads(line)

            title = data.get('title', '')
            full_text = data.get('full_text', '')

            year = extract_year_from_text(title) or extract_year_from_text(full_text[:1000])  # 只检查前1000字符

            if year:
                data['year'] = int(year)
                updated_count += 1
            else:
                data['year'] = None

            f_out.write(json.dumps(data, ensure_ascii=False) + '\n')

    print(f"处理完成: {total_count} 条记录，{updated_count} 条添加了year字段")
    return output_file

def process_image(input_file, output_file):
    """
    处理HTML JSONL文件中的图片信息

    功能：
    1. 删除下载失败的图片（downloaded为false或不存在）
    2. 删除downloaded字段
    3. 删除file_size字段

    Args:
        input_file: 输入的JSONL文件路径
        output_file: 输出的JSONL文件路径
    """

    processed_count = 0
    image_removed_count = 0

    with open(input_file, 'r', encoding='utf-8') as f_in, \
            open(output_file, 'w', encoding='utf-8') as f_out:

        for line_num, line in enumerate(f_in, 1):
            try:
                data = json.loads(line.strip())

                if 'images' in data and isinstance(data['images'], list):
                    original_count = len(data['images'])

                    filtered_images = []
                    for img in data['images']:
                        downloaded = img.get('downloaded', False)

                        if downloaded:
                            new_img = {
                                'id': img.get('id'),
                                'url': img.get('url')
                            }

                            if 'caption' in img and img['caption']:
                                new_img['caption'] = img['caption'][:10]

                            if 'local_path' in img:
                                new_img['local_path'] = img['local_path'][5:]

                            filtered_images.append(new_img)

                    data['images'] = filtered_images
                    removed = original_count - len(filtered_images)
                    image_removed_count += removed

                    if removed > 0:
                        print(f"第{line_num}行：删除了{removed}张下载失败的图片")

                f_out.write(json.dumps(data, ensure_ascii=False) + '\n')
                processed_count += 1

            except json.JSONDecodeError as e:
                print(f"第{line_num}行JSON解析错误：{e}")
                continue
            except Exception as e:
                print(f"第{line_num}行处理错误：{e}")
                continue

    print(f"\n处理完成！")
    print(f"总处理记录数：{processed_count}")
    print(f"删除的失败图片数：{image_removed_count}")
    print(f"输出文件：{output_file}")


import json
from urllib.parse import urlparse

def build_adjacency_list(input_file, output_file):
    """
    从HTML JSONL文件构建邻接表数据结构

    输出格式：每一行是一个JSON对象，包含source_url和target_urls
    target_urls只包含站内链接（is_internal=True）
    """

    adjacency_data = []
    internal_link_count = 0
    external_link_count = 0

    with open(input_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            try:
                data = json.loads(line.strip())
                source_url = data.get('url', '')

                if not source_url:
                    continue

                target_urls = []
                if 'outlinks' in data and isinstance(data['outlinks'], list):
                    for link in data['outlinks']:
                        if link.get('is_internal', False):
                            target_url = link.get('url', '')
                            if target_url:
                                parsed = urlparse(target_url)
                                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                                if clean_url.endswith('/') and len(clean_url) > len(
                                        f"{parsed.scheme}://{parsed.netloc}"):
                                    clean_url = clean_url[:-1]
                                target_urls.append(clean_url)
                                internal_link_count += 1
                        else:
                            external_link_count += 1

                target_urls = list(set(target_urls))

                if target_urls:
                    adjacency_data.append({
                        'id' : data.get('id', ''),
                        'url': source_url,
                        'target_urls': target_urls,
                        'target_count': len(target_urls)
                    })

            except json.JSONDecodeError:
                print(f"第{line_num}行JSON格式错误，跳过")
                continue
            except Exception as e:
                print(f"第{line_num}行处理错误：{e}")
                continue

    with open(output_file, 'w', encoding='utf-8') as f_out:
        for item in adjacency_data:
            f_out.write(json.dumps(item, ensure_ascii=False) + '\n')

    print(f"邻接表构建完成！")
    print(f"总节点数：{len(adjacency_data)}")
    print(f"内部链接数：{internal_link_count}")
    print(f"外部链接数：{external_link_count}")
    print(f"输出文件：{output_file}")

    return output_file


def main():
    input_file = "html_contents.jsonl"
    output_file = "data.jsonl"
    process_jsonl1(input_file, output_file)
    add_year_field(output_file, input_file)
    process_image(input_file, output_file)
    build_adjacency_list(output_file, "html_contents_pagerank.jsonl")

if __name__ == "__main__":
    main()