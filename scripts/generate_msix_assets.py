"""
生成 MSIX 打包所需的图标资源（PNG 格式）

MSIX 需要以下图标尺寸（含高 DPI 缩放版本）：
- Square44x44Logo.png (44x44) 及 scale-125/150/200/400 变体
- Square44x44Logo.targetsize-*.png (任务栏 targetsize)
- 每个 targetsize 对应的 _altform-unplated.png（无背景板任务栏图标）
- Square150x150Logo.png (150x150) 及 scale 变体
- Wide310x150Logo.png (310x150) 及 scale 变体
- StoreLogo.png (50x50) 及 scale 变体
- SplashScreen.png (620x300) 及 scale 变体

使用方法:
    python scripts/generate_msix_assets.py [--source ICON_PATH]

如果没有指定源图标，将使用 src-tauri/icons/icon.png。
所有输出都保留源图 Alpha 通道，不会合成背景色或阴影。
"""

import argparse
import os
import sys

try:
    from PIL import Image
except ImportError:
    print("需要 Pillow 库，请运行: pip install Pillow")
    sys.exit(1)


TRANSPARENT = (0, 0, 0, 0)
TARGET_SIZES = [16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 256]


def resize_icon(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """使用预乘 Alpha 缩放图标，避免透明边缘出现暗色光晕。"""

    return (
        img.convert("RGBa")
        .resize(size, Image.Resampling.LANCZOS)
        .convert("RGBA")
    )


def place_on_transparent_canvas(
    img: Image.Image,
    canvas_size: tuple[int, int],
    icon_size: tuple[int, int],
) -> Image.Image:
    """将图标居中放到透明画布，并完整保留 Alpha 通道。"""

    canvas = Image.new("RGBA", canvas_size, TRANSPARENT)
    icon = resize_icon(img, icon_size)
    offset = (
        (canvas_size[0] - icon_size[0]) // 2,
        (canvas_size[1] - icon_size[1]) // 2,
    )
    canvas.alpha_composite(icon, dest=offset)
    return canvas


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
            resized = resize_icon(img, (actual_size, actual_size))
            resized.save(os.path.join(output_dir, filename), "PNG")
            print(f"  [OK] {filename} ({actual_size}x{actual_size})")

    for name, (w, h) in wide_assets:
        for scale in scale_factors:
            factor = scale / 100.0
            actual_w, actual_h = int(w * factor), int(h * factor)
            filename = f"{name}.scale-{scale}.png"
            icon_size = int(130 * factor)
            canvas = place_on_transparent_canvas(
                img,
                (actual_w, actual_h),
                (icon_size, icon_size),
            )
            canvas.save(os.path.join(output_dir, filename), "PNG")
            print(f"  [OK] {filename} ({actual_w}x{actual_h})")

    for name, (w, h) in splash_assets:
        for scale in scale_factors:
            factor = scale / 100.0
            actual_w, actual_h = int(w * factor), int(h * factor)
            filename = f"{name}.scale-{scale}.png"
            icon_size = int(180 * factor)
            canvas = place_on_transparent_canvas(
                img,
                (actual_w, actual_h),
                (icon_size, icon_size),
            )
            canvas.save(os.path.join(output_dir, filename), "PNG")
            print(f"  [OK] {filename} ({actual_w}x{actual_h})")

    # 2) 生成 targetsize 图标（任务栏使用，按像素尺寸而非缩放比例）。
    # 普通版和无背景板版必须使用同一份缩放结果、覆盖相同尺寸集合，
    # 避免 Windows 在不同 DPI/显示入口选择资源后出现样式差异。
    for ts in TARGET_SIZES:
        resized = resize_icon(img, (ts, ts))
        for suffix in ("", "_altform-unplated"):
            filename = f"Square44x44Logo.targetsize-{ts}{suffix}.png"
            resized.save(os.path.join(output_dir, filename), "PNG")
            print(f"  [OK] {filename} ({ts}x{ts})")

    # 3) 生成基础 1x 版本（兼容旧 manifest 引用）
    for name, size in base_assets:
        resized = resize_icon(img, (size, size))
        resized.save(os.path.join(output_dir, f"{name}.png"), "PNG")
        print(f"  [OK] {name}.png ({size}x{size})")

    for name, (w, h) in wide_assets:
        canvas = place_on_transparent_canvas(img, (w, h), (130, 130))
        canvas.save(os.path.join(output_dir, f"{name}.png"), "PNG")
        print(f"  [OK] {name}.png ({w}x{h})")

    for name, (w, h) in splash_assets:
        canvas = place_on_transparent_canvas(img, (w, h), (180, 180))
        canvas.save(os.path.join(output_dir, f"{name}.png"), "PNG")
        print(f"  [OK] {name}.png ({w}x{h})")

    print(f"\n[DONE] MSIX 图标资源已生成到: {output_dir}")


def main():
    # 确保 stdout 使用 UTF-8 编码（修复 Windows cp1252 下的 UnicodeEncodeError）
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

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
