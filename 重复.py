import json
import os

def normalize_url(url):
    """
    URL 归一化处理：
    1. 忽略 http:// 和 https:// 的区别
    2. 忽略 URL 末尾的斜杠 (例如 example.com/ 和 example.com)
    """
    if not url:
        return ""
    
    # 1. 去除首尾空白
    url = url.strip()
    
    # 2. 统一移除协议头 (只移除开头的，防止误伤 URL 参数里的内容)
    if url.startswith("http://"):
        url = url[7:]
    elif url.startswith("https://"):
        url = url[8:]
        
    # 3. 移除末尾的斜杠 (标准化路径)
    if url.endswith("/"):
        url = url[:-1]
        
    return url

def deduplicate_jsonl_smart(input_file, output_file):
    
    if not os.path.exists(input_file):
        print(f"❌ 错误：找不到输入文件: {input_file}")
        return

    # 使用集合存储"归一化"后的 URL 签名
    seen_signatures = set()
    unique_records = []
    
    duplicates_count = 0
    total_count = 0
    http_https_dupes = 0 # 专门统计因 http/https 差异而被找出的重复
    
    print(f"正在智能去重 {input_file} ...")

    with open(input_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line: continue
            
            try:
                record = json.loads(line)
                raw_url = record.get('url', '')
                
                if not raw_url:
                    continue

                # 获取归一化签名 (例如: www.ustc.edu.cn/index)
                url_signature = normalize_url(raw_url)

                if url_signature in seen_signatures:
                    duplicates_count += 1
                    # 这是一个重复，但我们可以看看是不是仅仅因为 http/https 造成的
                    # (仅做统计用，不影响逻辑)
                    pass 
                else:
                    seen_signatures.add(url_signature)
                    unique_records.append(line)
                    
                total_count += 1
                if total_count % 1000 == 0:
                    print(f"  已扫描 {total_count} 条...")

            except json.JSONDecodeError:
                print(f"  ⚠️ 第 {line_num} 行 JSON 错误，跳过")
                continue

    # 写入结果
    print(f"正在写入输出文件 {output_file} ...")
    with open(output_file, 'w', encoding='utf-8') as f_out:
        for record_line in unique_records:
            f_out.write(record_line + '\n')

    print("=" * 40)
    print(f"✅ 智能去重完成！")
    print(f"原始记录: {total_count}")
    print(f"保留记录: {len(unique_records)}")
    print(f"剔除重复: {duplicates_count}")
    print(f"输出文件: {output_file}")
    print("=" * 40)

if __name__ == "__main__":
    # 配置输入和输出文件名
    input_path = "output\\documents.jsonl"          # 你的原始文件名
    output_path = "output\\documents_dedup.jsonl"   # 去重后的输出文件名
    
    deduplicate_jsonl_smart(input_path, output_path)