#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""视觉回归报告工具（轻量级像素差异统计）。"""

import argparse
import json
import os
from typing import Any

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit("缺少依赖 Pillow，请先安装：pip install Pillow") from exc


def open_image(path: str) -> Image.Image:
    if not os.path.exists(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    return Image.open(path).convert("RGBA")


def compare_images(
    baseline: Image.Image,
    current: Image.Image,
    threshold: int,
) -> dict[str, Any]:
    if baseline.size != current.size:
        current = current.resize(baseline.size)

    width, height = baseline.size
    base_data = baseline.load()
    curr_data = current.load()

    total = width * height
    changed = 0
    hot_pixels = 0
    max_diff = 0

    # heatmap: 差异像素使用红色显示，未差异使用透明
    heatmap = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    heatmap_data = heatmap.load()

    for y in range(height):
        for x in range(width):
            b = base_data[x, y]
            c = curr_data[x, y]
            diff = max(abs(b[0] - c[0]), abs(b[1] - c[1]), abs(b[2] - c[2]), abs(b[3] - c[3]))
            if diff > 0:
                changed += 1
            if diff > threshold:
                hot_pixels += 1
                # 差异越大，alpha 越高，便于人工定位偏差热点
                alpha = min(255, 64 + diff * 3)
                heatmap_data[x, y] = (255, 0, 0, alpha)
            if diff > max_diff:
                max_diff = diff

    alignment = 100.0 if total == 0 else (1 - changed / total) * 100
    hot_ratio = 0.0 if total == 0 else hot_pixels / total * 100
    return {
        "resolution": {"width": width, "height": height},
        "total_pixels": total,
        "changed_pixels": changed,
        "changed_ratio_percent": round(changed / total * 100, 4) if total else 0.0,
        "hot_pixels_gt_threshold": hot_pixels,
        "hot_ratio_percent": round(hot_ratio, 4),
        "alignment_percent": round(alignment, 4),
        "max_channel_diff": max_diff,
        "heatmap": heatmap,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="视觉回归报告（像素差异）")
    parser.add_argument("--baseline", required=True, help="设计稿基线图路径")
    parser.add_argument("--current", required=True, help="当前页面截图路径")
    parser.add_argument(
        "--threshold",
        type=int,
        default=2,
        help="热点阈值（单通道差异阈值，默认 2）",
    )
    parser.add_argument("--report-json", required=True, help="报告输出路径 JSON")
    parser.add_argument("--heatmap-out", required=True, help="热力图输出路径 PNG")
    args = parser.parse_args()

    try:
        baseline = open_image(os.path.abspath(args.baseline))
        current = open_image(os.path.abspath(args.current))
        result = compare_images(baseline, current, args.threshold)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"视觉回归失败：{exc}")
        return 1

    heatmap_path = os.path.abspath(args.heatmap_out)
    os.makedirs(os.path.dirname(heatmap_path), exist_ok=True)
    result["heatmap"].save(heatmap_path, format="PNG")

    report = {
        "baseline": os.path.abspath(args.baseline),
        "current": os.path.abspath(args.current),
        "threshold": args.threshold,
        "metrics": {k: v for k, v in result.items() if k != "heatmap"},
        "heatmap_path": heatmap_path,
        "suggestions": [
            "若 alignment_percent < 98%，优先检查字体映射、字距换算与文本绝对定位。",
            "若 hot_ratio_percent > 1%，优先检查边框厚度、行高、图标尺寸与分页位置。",
            "若 max_channel_diff > 32，检查色值映射与透明度叠加。",
        ],
    }

    report_path = os.path.abspath(args.report_json)
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("视觉回归完成：")
    print(f"- alignment: {report['metrics']['alignment_percent']}%")
    print(f"- changed_ratio: {report['metrics']['changed_ratio_percent']}%")
    print(f"- hot_ratio(>{args.threshold}): {report['metrics']['hot_ratio_percent']}%")
    print(f"- 报告: {report_path}")
    print(f"- 热力图: {heatmap_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
