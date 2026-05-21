# -*- coding: utf-8 -*-
"""
Tauri 图标生成脚本
从 resources/m.ico 或 resources/img/ 中的图片生成 Tauri 所需的各种尺寸图标

需要安装: pip install Pillow
"""

import os
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("需要安装 Pillow: pip install Pillow")
    sys.exit(1)

# 项目路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TAURI_ICONS_DIR = PROJECT_ROOT / "src-tauri" / "icons"
RESOURCES_DIR = PROJECT_ROOT / "resources"

# Tauri 需要的图标尺寸
ICON_SIZES = {
    "32x32.png": (32, 32),
    "128x128.png": (128, 128),
    "128x128@2x.png": (256, 256),
    "icon.png": (512, 512),
}

# Windows ico 尺寸
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def find_source_image():
    """查找源图片"""
    # 优先使用 ico 文件
    ico_path = RESOURCES_DIR / "m.ico"
    if ico_path.exists():
        return ico_path

    # 从 img 目录查找 png
    img_dir = RESOURCES_DIR / "img"
    if img_dir.exists():
        for pattern in ["*.png", "*.jpg"]:
            files = list(img_dir.glob(pattern))
            if files:
                return files[0]

    print("错误: 未找到源图片，请确保 resources/ 目录中有图片文件")
    sys.exit(1)


def main():
    os.makedirs(TAURI_ICONS_DIR, exist_ok=True)

    source_path = find_source_image()
    print(f"源图片: {source_path}")

    img = Image.open(source_path)
    print(f"原始尺寸: {img.size}, 模式: {img.mode}")

    # 确保 RGBA 模式
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # 生成 PNG 图标
    print("\nGenerating PNG icons...")
    for name, size in ICON_SIZES.items():
        resized = img.resize(size, Image.LANCZOS)
        dest = TAURI_ICONS_DIR / name
        resized.save(dest, "PNG")
        print(f"  [OK] {name} ({size[0]}x{size[1]})")

    # 生成 Windows ico
    print("\nGenerating ICO icon...")
    ico_dest = TAURI_ICONS_DIR / "icon.ico"
    # 使用最大尺寸的图片作为 ico 基础
    ico_base = img.resize((256, 256), Image.LANCZOS)
    ico_base.save(ico_dest, "ICO", sizes=ICO_SIZES)
    print(f"  [OK] icon.ico")

    # 生成 macOS icns (占位符)
    print("\nGenerating ICNS placeholder...")
    icns_dest = TAURI_ICONS_DIR / "icon.icns"
    # 复制最大的 PNG 作为占位（实际应使用 iconutil 生成）
    img_512 = img.resize((512, 512), Image.LANCZOS)
    img_512.save(TAURI_ICONS_DIR / "icon.png", "PNG")
    print(f"  [WARN] icon.icns -- use iconutil for macOS build")

    print(f"\n[DONE] Icons generated: {TAURI_ICONS_DIR}")
    print(f"\nVerify with: cargo tauri icon --help")


if __name__ == "__main__":
    main()
