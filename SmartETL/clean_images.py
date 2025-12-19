import json
import os
import shutil


def clean_images_simple(jsonl_file, image_dir):
    """
    简单清理：将需要的图片移动到新目录
    """

    needed_filenames = set()

    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                if 'images' in data:
                    for img in data['images']:
                        if 'local_path' in img:
                            filename = os.path.basename(img['local_path'])
                            needed_filenames.add(filename)
            except:
                continue

    print(f"需要保留 {len(needed_filenames)} 张图片")

    clean_dir = os.path.join(image_dir, "clean")
    os.makedirs(clean_dir, exist_ok=True)

    moved = 0
    for filename in os.listdir(image_dir):
        filepath = os.path.join(image_dir, filename)

        if os.path.isdir(filepath) or not filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
            continue

        if filename in needed_filenames:
            shutil.move(filepath, os.path.join(clean_dir, filename))
            moved += 1

    print(f"已移动 {moved} 张图片到 {clean_dir}/")
    print(f"剩余 {len(os.listdir(image_dir)) - 1} 个文件/目录（可删除）")

    return moved

def main():
    clean_images_simple("output/jsonl/data.jsonl", "data/images")

if __name__ == "__main__":
    main()