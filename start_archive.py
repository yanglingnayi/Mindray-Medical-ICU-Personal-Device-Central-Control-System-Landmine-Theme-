"""
监护仪历史档案管理器 - 启动脚本

双击或在命令行运行:
    python start_archive.py

启动图形界面 (GUI) 进行历史数据分析。

其他用法请查看 README.md
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)


def main():
    print("=" * 60)
    print("  监护仪历史档案管理器")
    print("  Mindray Historical Archive Manager")
    print("=" * 60)
    print(f"  项目路径: {PROJECT_ROOT}")
    print(f"  Python: {sys.version.split()[0]}")
    print("-" * 60)
    print("  模式: 图形界面 (GUI)")
    print("  提示: 其他用法见 README.md")
    print("=" * 60)
    print()

    try:
        from app.archive.gui import main as gui_main
        gui_main()
    except Exception as e:
        print(f"\n❌ GUI 启动失败: {e}")
        print("\n如 GUI 不可用时，可尝试命令行模式:")
        print("  python -m app.archive.history_manager")
        import traceback
        traceback.print_exc()
        input("\n按 Enter 退出...")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已取消")