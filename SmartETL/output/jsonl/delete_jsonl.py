
import json
import os


def simple_delete(input_file, pattern, max_delete=None):

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    deleted = 0
    new_lines = []
    images_to_delete = []

    for line in lines:
        try:
            data = json.loads(line.strip())
            if pattern.lower() in data.get('url', '').lower():
                if max_delete is None or deleted < max_delete:
                    # 收集图片
                    for img in data.get('images', []):
                        if 'local_path' in img:
                            images_to_delete.append(img['local_path'])
                    deleted += 1
                    continue
            new_lines.append(line)
        except:
            new_lines.append(line)

    with open(input_file, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    for img_path in images_to_delete:
        if os.path.exists(img_path):
            os.remove(img_path)

    print(f"删除了 {deleted} 条记录和 {len(images_to_delete)} 张图片")

def clean_images_simple(jsonl_file):
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        try:
            data = json.loads(line.strip())
            if 'images' in data and isinstance(data['images'], list):
                data['images'] = [
                    img for img in data['images']
                    if 'local_path' not in img or os.path.exists(img['local_path'])
                ]
            new_lines.append(json.dumps(data, ensure_ascii=False) + '\n')
        except:
            new_lines.append(line)

    with open(jsonl_file, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    print("清理完成")

def main():
    #simple_delete("data.jsonl", "oic.ustc.edu.cn", max_delete=1500)
    clean_images_simple("data.jsonl")

if __name__ == "__main__":
    main()