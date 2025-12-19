"""
运行脚本
"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from main import main

if __name__ == "__main__":
    print("启动智能ETL系统...")
    main()
    print("程序执行完成！")

