
"""
一键运行脚本
"""

import sys
import os
from config import Config
from processor import DataProcessor
from exporter import FileExporter


def main():
    print("=" * 60)
    print("第二阶段：数据处理与导出")
    print("=" * 60)

    config = Config()
    print(f"[1/4] 加载配置")
    print(f"    输入文件: {config.input_file}")
    print(f"    输出目录: {config.output_dir}")

    print(f"\n[2/4] 处理数据...")
    processor = DataProcessor(config)
    data = processor.load_and_process()

    if not data:
        print("错误：没有数据！请检查输入文件")
        return

    print(f"    加载 {len(data)} 条记录")

    print(f"\n[3/4] 导出文件...")
    exporter = FileExporter(config.output_dir)

    exporter.export_jsonl(data, "documents.jsonl")
    exporter.export_indexing(data, "for_indexing.txt")
    exporter.export_stats(data, "stats_input.csv")
    exporter.export_diff_pairs(data, "diff_pairs.jsonl")

    print(f"\n[4/4] 生成统计信息...")
    stats = processor.calculate_stats(data)
    exporter.export_stats_json(stats, "stats_summary.json")
    exporter.generate_readme(stats, data)

    print("\n输出文件:")
    for root, dirs, files in os.walk(config.output_dir):
        level = root.replace(config.output_dir, '').count(os.sep)
        indent = ' ' * 2 * level
        print(f'{indent}{os.path.basename(root) if level > 0 else "output/"}')
        subindent = ' ' * 2 * (level + 1)
        for file in files:
            if file.endswith('.md') or file.endswith('.json') or file.endswith('.txt') or file.endswith('.csv'):
                print(f'{subindent}{file}')

    print(f"\n数据统计:")
    print(f"   总文档数: {stats['total']}")
    print(f"   文档类型: {', '.join(stats['types'].keys())}")
    print(f"   年份范围: {stats.get('min_year', 'N/A')} - {stats.get('max_year', 'N/A')}")
    print(f"   来源网站: {len(stats['websites'])} 个")


if __name__ == "__main__":
    main()