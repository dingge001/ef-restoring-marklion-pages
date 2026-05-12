#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
标记狮共享层提取脚本（CLI 版，可跨项目复用）：
- 遍历指定目录下每个页面 data.js
- 解析并扁平化图层
- 按语义区域识别：背景、顶部导航、左侧菜单
- 按模块前缀聚类，输出跨页面高频共享节点
- 支持 marklion_artboard 的 2 参数与 3 参数（含 document.currentScript）调用

用法：
  python extract_shared_layout.py \
    --res-dir "<项目>/标记狮/res" \
    --out-json "<输出>/semantic-shared-layers.json" \
    --out-report "<输出>/shared-layers-report.md" \
    [--module-separator "-"] \
    [--global-header-min-pages 8]
"""
import argparse
import os
import sys
import json
import re
from collections import Counter, defaultdict
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def read_text(path: str) -> str:
    for enc in ("utf-8", "utf-8-sig", "gbk", "gb18030"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def extract_payload(content: str) -> str | None:
    start = content.find("marklion_artboard(")
    if start < 0:
        return None
    i = start + len("marklion_artboard(")
    depth = 1
    in_str = False
    esc = False
    str_ch = ""
    while i < len(content):
        ch = content[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == str_ch:
                in_str = False
        else:
            if ch in ("'", '"'):
                in_str = True
                str_ch = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return content[start + len("marklion_artboard(") : i]
        i += 1
    return None


def split_top_level_args(payload: str) -> list[str]:
    args = []
    depth = 0
    in_str = False
    esc = False
    str_ch = ""
    start = 0
    for i, ch in enumerate(payload):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == str_ch:
                in_str = False
            continue
        if ch in ("'", '"'):
            in_str = True
            str_ch = ch
            continue
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        elif ch == "," and depth == 0:
            args.append(payload[start:i].strip())
            start = i + 1
    tail = payload[start:].strip()
    if tail:
        args.append(tail)
    return args


def parse_artboard(js_path: str) -> dict | None:
    try:
        content = read_text(js_path)
    except Exception:
        return None
    payload = extract_payload(content)
    if not payload:
        return None
    args = split_top_level_args(payload)
    if not args:
        return None
    # 画板对象：取最后一个 { ... } 参数
    candidates = [args[-1]]
    if "document.currentScript," in payload:
        after = payload.split("document.currentScript,", 1)[1].strip()
        candidates.append(after)
    for raw in candidates:
        for variant in (raw, re.sub(r",\s*([}\]])", r"\1", raw)):
            try:
                obj = json.loads(variant)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


def get_bounds(layer: dict) -> dict:
    b = layer.get("globalBounds") or layer.get("boundsInParent") or {}
    if not isinstance(b, dict):
        b = {}
    return {
        "x": b.get("x", 0) or 0,
        "y": b.get("y", 0) or 0,
        "w": b.get("width", 0) or 0,
        "h": b.get("height", 0) or 0,
    }


def flatten_layers(roots: list) -> list:
    out: list = []

    def rec(node):
        if not isinstance(node, dict):
            return
        out.append(node)
        for k in node.get("children") or node.get("layers") or []:
            rec(k)

    for r in roots or []:
        rec(r)
    return out


def artboard_origin(data: dict) -> tuple[float, float]:
    ab = data.get("boundsInParent") or data.get("globalBounds") or {}
    return ab.get("x", 0) or 0, ab.get("y", 0) or 0


def decode_argb(val) -> tuple[str, float] | None:
    if val is None:
        return None
    try:
        iv = int(val) & 0xFFFFFFFF
    except (TypeError, ValueError):
        return None
    a = (iv >> 24) & 0xFF
    r = (iv >> 16) & 0xFF
    g = (iv >> 8) & 0xFF
    b = iv & 0xFF
    return f"#{r:02X}{g:02X}{b:02X}", round(a / 255, 3)


def layer_signature(layer: dict, ox: float, oy: float) -> str:
    b = get_bounds(layer)
    rx = round((b["x"] - ox) / 2) * 2
    ry = round((b["y"] - oy) / 2) * 2
    rw = round(b["w"] / 2) * 2
    rh = round(b["h"] / 2) * 2
    name = layer.get("name", "") or ""
    ts = layer.get("textStyle") or {}
    text = (ts.get("text") if isinstance(ts, dict) else "") or layer.get("text", "") or ""
    export = layer.get("exportPath") or layer.get("exportName") or ""
    return f"{name}|{rx},{ry},{rw},{rh}|{text[:60]}|{export}"


def module_key(page_name: str, home_prefix: str) -> str:
    if page_name.startswith(home_prefix):
        return home_prefix
    parts = page_name.split("-")
    head = parts[0]
    if len(parts) > 1 and head in ("1集中监测", "2集中监测", "3集中监测", "4集中监测"):
        return f"{head}-{parts[1]}"
    return head


def main() -> int:
    parser = argparse.ArgumentParser(description="标记狮共享层语义识别工具")
    parser.add_argument("--res-dir", required=True, help="标记狮 res 目录绝对路径（含各页面子目录）")
    parser.add_argument("--out-json", required=True, help="输出：共享层 JSON 绝对路径")
    parser.add_argument("--out-report", help="输出：Markdown 报告绝对路径（可选）")
    parser.add_argument("--home-prefix", default="首页总览", help="首页模块前缀（默认：首页总览）")
    parser.add_argument("--global-header-min-pages", type=int, default=8,
                        help="全局顶部节点阈值（出现页数≥该值视为全局共享，默认8）")
    args = parser.parse_args()

    base = os.path.abspath(args.res_dir)
    if not os.path.isdir(base):
        print(f"错误：目录不存在 -> {base}")
        return 2

    page_dirs = sorted([d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))])
    print(f"发现 {len(page_dirs)} 个页面目录")

    modules: dict[str, dict] = defaultdict(lambda: {
        "pages": [],
        "header_sig_counter": Counter(),
        "sidebar_sig_counter": Counter(),
        "bg_sig_counter": Counter(),
        "header_samples": {},
        "sidebar_samples": {},
        "bg_samples": {},
    })
    global_stats = {
        "header_sig_counter": Counter(),
        "header_samples": {},
        "total_pages": 0,
    }

    parsed_ok = 0
    parsed_fail: list[str] = []

    for pd in page_dirs:
        js_path = os.path.join(base, pd, "data.js")
        if not os.path.exists(js_path):
            continue
        data = parse_artboard(js_path)
        if not data:
            parsed_fail.append(pd)
            continue
        parsed_ok += 1
        global_stats["total_pages"] += 1

        ox, oy = artboard_origin(data)
        ab = data.get("boundsInParent") or data.get("globalBounds") or {}
        aw = ab.get("width", 1920) or 1920
        ah = ab.get("height", 1080) or 1080

        flat = flatten_layers(data.get("children") or data.get("layers") or [])
        mod = module_key(pd, args.home_prefix)
        modules[mod]["pages"].append(pd)

        for layer in flat:
            b = get_bounds(layer)
            if b["w"] <= 0 or b["h"] <= 0:
                continue
            rx = b["x"] - ox
            ry = b["y"] - oy
            sig = layer_signature(layer, ox, oy)

            if b["w"] >= aw * 0.9 and b["h"] >= ah * 0.85:
                modules[mod]["bg_sig_counter"][sig] += 1
                modules[mod]["bg_samples"].setdefault(sig, layer)
            elif ry <= 10 and b["h"] <= 120 and b["w"] >= aw * 0.4:
                modules[mod]["header_sig_counter"][sig] += 1
                modules[mod]["header_samples"].setdefault(sig, layer)
                global_stats["header_sig_counter"][sig] += 1
                global_stats["header_samples"].setdefault(sig, layer)
            elif ry <= 80 and b["h"] <= 60 and rx < aw:
                modules[mod]["header_sig_counter"][sig] += 1
                modules[mod]["header_samples"].setdefault(sig, layer)
                global_stats["header_sig_counter"][sig] += 1
                global_stats["header_samples"].setdefault(sig, layer)
            elif rx <= 20 and b["w"] <= 350 and b["h"] >= ah * 0.5:
                modules[mod]["sidebar_sig_counter"][sig] += 1
                modules[mod]["sidebar_samples"].setdefault(sig, layer)

    def sample_payload(layer: dict) -> dict:
        b = get_bounds(layer)
        ts = layer.get("textStyle") or {}
        text_val = ts.get("text") if isinstance(ts, dict) else layer.get("text")
        fill = layer.get("fill") or (ts.get("fill") if isinstance(ts, dict) else None)
        color = None
        if isinstance(fill, dict) and "value" in fill:
            color = decode_argb(fill.get("value"))
        return {
            "name": layer.get("name", ""),
            "bounds": b,
            "exportPath": layer.get("exportPath", ""),
            "text": text_val,
            "fontSize": (ts.get("fontSize") if isinstance(ts, dict) else None),
            "fontFamily": (ts.get("fontFamily") if isinstance(ts, dict) else None),
            "color_rgb": color[0] if color else None,
            "color_alpha": color[1] if color else None,
        }

    module_report: dict[str, dict] = {}
    for mod, info in modules.items():
        n = len(info["pages"])
        threshold = max(2, n // 2)

        def collect(counter: Counter, samples: dict) -> list:
            out = []
            for sig, cnt in counter.most_common():
                if cnt >= threshold:
                    out.append({"sig": sig, "count": cnt, **sample_payload(samples.get(sig, {}))})
            return out

        module_report[mod] = {
            "pages_count": n,
            "threshold": threshold,
            "header_shared": collect(info["header_sig_counter"], info["header_samples"]),
            "sidebar_shared": collect(info["sidebar_sig_counter"], info["sidebar_samples"]),
            "bg_shared": collect(info["bg_sig_counter"], info["bg_samples"]),
            "pages": info["pages"],
        }

    global_threshold = max(args.global_header_min_pages, global_stats["total_pages"] // 8)
    global_header_shared = [
        {"sig": sig, "count": cnt, **sample_payload(global_stats["header_samples"].get(sig, {}))}
        for sig, cnt in global_stats["header_sig_counter"].most_common()
        if cnt >= global_threshold
    ]

    result = {
        "total_pages_parsed": parsed_ok,
        "pages_parse_failed": parsed_fail,
        "modules": module_report,
        "global_header_shared": global_header_shared,
        "global_header_threshold": global_threshold,
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out_json)), exist_ok=True)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    if args.out_report:
        os.makedirs(os.path.dirname(os.path.abspath(args.out_report)), exist_ok=True)
        lines = [
            "# 标记狮共享层识别报告",
            f"- 成功解析页面数：{parsed_ok}",
            f"- 解析失败页面：{len(parsed_fail)}",
        ]
        if parsed_fail:
            lines.append("  - " + ", ".join(parsed_fail[:10]))
        lines.append("")
        lines.append(f"## 全局共享顶部导航（出现页数 >= {global_threshold}，共 {len(global_header_shared)} 项）\n")
        lines.append("| 出现次数 | 名称 | 文本/导出 | 坐标 | 尺寸 | 颜色 |")
        lines.append("|---|---|---|---|---|---|")
        for item in global_header_shared[:30]:
            b = item["bounds"]
            txt = (str(item.get("text") or "") or item.get("exportPath") or "").replace("|", "/").replace("\n", " ")[:30]
            color = item.get("color_rgb") or ""
            lines.append(f"| {item['count']} | {item['name'][:24]} | {txt} | {b['x']},{b['y']} | {b['w']}x{b['h']} | {color} |")
        lines.append("\n## 模块聚类")
        for mod, info in module_report.items():
            lines.append(f"### {mod}  （{info['pages_count']} 页，阈值 {info['threshold']}）")
            lines.append(f"- 共享顶部节点：{len(info['header_shared'])}")
            lines.append(f"- 共享侧栏节点：{len(info['sidebar_shared'])}")
            lines.append(f"- 共享背景节点：{len(info['bg_shared'])}")
            lines.append("")
        with open(args.out_report, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    print(f"输出 JSON：{args.out_json}")
    if args.out_report:
        print(f"输出报告：{args.out_report}")
    print(f"解析成功 {parsed_ok} / 失败 {len(parsed_fail)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
