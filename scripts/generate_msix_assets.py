"""
生成 MSIX 打包所需的图标资源（PNG 格式）

MSIX 需要以下图标尺寸（含高 DPI 缩放版本）：
- Square44x44Logo.png (44x44) 及 scale-125/150/200/400 变体
- Square44x44Logo.targetsize-16/24/32/48/64/256.png (任务栏 targetsize)
- Square44x44Logo.targetsize-24_altform-unplated.png (无背景板任务栏图标)
- Square150x150Logo.png (150x150) 及 scale 变体
- Wide310x150Logo.png (310x150) 及 scale 变体
- StoreLogo.png (50x50) 及 scale 变体
- SplashScreen.png (620x300) 及 scale 变体

使用方法:
    python scripts/generate_msix_assets.py [--source ICON_PATH]

如果没有指定源图标，将使用 src-tauri/icons/icon.png
"""

import argparse
import os
import sys

try:
    from PIL import Image
except ImportError:
    print("需要 Pillow 库，请运行: pip install Pillow")
    sys.exit(1)


def generate_assets(source_path: str, output_dir: str):
    """从源图标生成所有 MSIX 所需的图标资源（含高 DPI 缩放版本）"""

    if not os.path.exists(source_path):
        print(f"[ERROR] 源图标不存在: {source_path}")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    img = Image.open(source_path).convert("RGBA")

    # Windows 支持的 DPI 缩放比例
    scale_factors = [100, 125, 150, 200, 400]

    # 定义基础图标及其基准尺寸
    # key: (文件名模板, 基准尺寸)  尺寸为 int 表示正方形，tuple 表示 (宽, 高)
    base_assets = [
        ("Square44x44Logo", 44),
        ("Square150x150Logo", 150),
        ("StoreLogo", 50),
    ]

    wide_assets = [
        ("Wide310x150Logo", (310, 150)),
    ]

    splash_assets = [
        ("SplashScreen", (620, 300)),
    ]

    # 1) 生成缩放版图标（scale-100, scale-125, scale-150, scale-200, scale-400）
    for name, size in base_assets:
        for scale in scale_factors:
            factor = scale / 100.0
            actual_size = int(size * factor)
            filename = f"{name}.scale-{scale}.png"
            resized = img.resize((actual_size, actual_size), Image.Resampling.LANCZOS)
            resized.save(os.path.join(output_dir, filename), "PNG")
            print(f"  [OK] {filename} ({actual_size}x{actual_size})")

    for name, (w, h) in wide_assets:
        for scale in scale_factors:
            factor = scale / 100.0
            actual_w, actual_h = int(w * factor), int(h * factor)
            filename = f"{name}.scale-{scale}.png"
            canvas = Image.new("RGBA", (actual_w, actual_h), (26, 26, 46, 255))
            icon_size = int(130 * factor)
            icon_resized = img.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
            offset_x = (actual_w - icon_size) // 2
            offset_y = (actual_h - icon_size) // 2
            canvas.paste(icon_resized, (offset_x, offset_y), icon_resized)
            canvas.save(os.path.join(output_dir, filename), "PNG")
            print(f"  [OK] {filename} ({actual_w}x{actual_h})")

    for name, (w, h) in splash_assets:
        for scale in scale_factors:
            factor = scale / 100.0
            actual_w, actual_h = int(w * factor), int(h * factor)
            filename = f"{name}.scale-{scale}.png"
            canvas = Image.new("RGBA", (actual_w, actual_h), (26, 26, 46, 255))
            icon_size = int(180 * factor)
            icon_resized = img.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
            offset_x = (actual_w - icon_size) // 2
            offset_y = (actual_h - icon_size) // 2
            canvas.paste(icon_resized, (offset_x, offset_y), icon_resized)
            canvas.save(os.path.join(output_dir, filename), "PNG")
            print(f"  [OK] {filename} ({actual_w}x{actual_h})")

    # 2) 生成 targetsize 图标（任务栏使用，按像素尺寸而非缩放比例）
    # 这些是任务栏实际使用的图标尺寸，Windows 会根据 DPI 选择最接近的
    target_sizes = [16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 256]
    for ts in target_sizes:
        resized = img.resize((ts, ts), Image.Resampling.LANCZOS)
        filename = f"Square44x44Logo.targetsize-{ts}.png"
        resized.save(os.path.join(output_dir, filename), "PNG")
        print(f"  [OK] {filename} ({ts}x{ts})")

    # 3) 生成 altform-unplated 版本（无系统背景板的任务栏图标）
    for ts in [16, 20, 24, 32, 48, 64, 256]:
        resized = img.resize((ts, ts), Image.Resampling.LANCZOS)
        filename = f"Square44x44Logo.targetsize-{ts}_altform-unplated.png"
        resized.save(os.path.join(output_dir, filename), "PNG")
        print(f"  [OK] {filename} ({ts}x{ts})")

    # 4) 生成基础 1x 版本（兼容旧 manifest 引用）
    for name, size in base_assets:
        resized = img.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(os.path.join(output_dir, f"{name}.png"), "PNG")
        print(f"  [OK] {name}.png ({size}x{size})")

    for name, (w, h) in wide_assets:
        canvas = Image.new("RGBA", (w, h), (26, 26, 46, 255))
        icon_resized = img.resize((130, 130), Image.Resampling.LANCZOS)
        canvas.paste(icon_resized, ((w - 130) // 2, (h - 130) // 2), icon_resized)
        canvas.save(os.path.join(output_dir, f"{name}.png"), "PNG")
        print(f"  [OK] {name}.png ({w}x{h})")

    for name, (w, h) in splash_assets:
        canvas = Image.new("RGBA", (w, h), (26, 26, 46, 255))
        icon_resized = img.resize((180, 180), Image.Resampling.LANCZOS)
        canvas.paste(icon_resized, ((w - 180) // 2, (h - 180) // 2), icon_resized)
        canvas.save(os.path.join(output_dir, f"{name}.png"), "PNG")
        print(f"  [OK] {name}.png ({w}x{h})")

    print(f"\n[DONE] MSIX 图标资源已生成到: {output_dir}")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    parser = argparse.ArgumentParser(description="生成 MSIX 图标资源")
    parser.add_argument(
        "--source",
        default=os.path.join(project_root, "src-tauri", "icons", "icon.png"),
        help="源图标路径",
    )
    parser.add_argument(
        "--output",
        default=os.path.join(project_root, "Assets"),
        help="输出目录",
    )
    args = parser.parse_args()

    print(f"源图标: {args.source}")
    print(f"输出目录: {args.output}")
    print()

    generate_assets(args.source, args.output)


if __name__ == "__main__":
    main()
