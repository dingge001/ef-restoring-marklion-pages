#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""标记狮 data.js 生产级校验与数据清洗脚本。

能力:
- 校验 data.js 是否可解析、是否包含 marklion_artboard
- 区分"画板索引 data.js"与"页面级 data.js"，并给出正确指引
- 执行基础数据清洗（重复 ID、缺失字段、无效图层过滤）
- 输出分级异常（warning/error）与数据质量报告
- 可选输出清洗后的 JSON，供后续还原流程直接消费
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from copy import deepcopy
from datetime import datetime
from typing import Any

# Windows GBK 控制台兼容：强制 UTF-8 输出，避免中文/符号打印崩溃
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def read_text_file(path: str) -> str:
    """安全读取文本文件，按常见编码降级尝试。"""
    encodings = ["utf-8", "utf-8-sig", "gbk", "gb18030"]
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="strict") as f:
                return f.read()
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            raise RuntimeError(f"读取文件失败：{exc}") from exc
    # 最终兜底：忽略非法字符，确保脚本不崩溃
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def extract_marklion_payload(content: str) -> str:
    """从 marklion_artboard(...) 中提取入参 payload。"""
    marker = "marklion_artboard("
    start = content.find(marker)
    if start < 0:
        # 检测是否是 "画板索引 data.js"（__marklionData = {...artboards:[]...}）
        if "__marklionData" in content and "artboards" in content:
            raise ValueError(
                "当前 data.js 是画板索引文件（含 __marklionData.artboards 列表），不是单页画板数据。\n"
                "请传入某个页面目录下的 data.js，例如：标记狮/res/<页面名>/data.js"
            )
        raise ValueError("文件中未发现 marklion_artboard 调用，可能不是标记狮画板数据。")

    i = start + len(marker)
    depth = 1
    in_str = False
    str_char = ""
    escaped = False

    while i < len(content):
        ch = content[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == str_char:
                in_str = False
        else:
            if ch in ("'", '"'):
                in_str = True
                str_char = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return content[start + len(marker) : i].strip()
        i += 1

    raise ValueError("marklion_artboard 调用不完整，括号未闭合。")


def split_top_level_args(payload: str) -> list[str]:
    """按顶层逗号切分 marklion_artboard(...) 的参数列表，兼容 2/3 参数调用。"""
    args: list[str] = []
    depth = 0
    in_str = False
    str_char = ""
    escaped = False
    start = 0
    for i, ch in enumerate(payload):
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == str_char:
                in_str = False
            continue
        if ch in ("'", '"'):
            in_str = True
            str_char = ch
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


def sanitize_json_like(payload: str) -> str:
    """对常见 JSON-like 格式做最小清洗。"""
    normalized = payload.strip()
    normalized = re.sub(r",\s*([}\]])", r"\1", normalized)
    return normalized


def parse_data(content: str) -> dict[str, Any]:
    payload = extract_marklion_payload(content)

    # 兼容 2 参数 / 3 参数调用：marklion_artboard(resMap, artboardObj)
    # 或 marklion_artboard(resMap, document.currentScript, artboardObj)
    # 画板对象一般是"最后一个"顶层参数
    args = split_top_level_args(payload)
    candidates_raw: list[str] = []
    if args:
        # 优先最后一个参数作为画板对象
        candidates_raw.append(args[-1])
        # 兼容旧脚本：若 payload 含 "document.currentScript," 也按其分割
        if "document.currentScript," in payload:
            after = payload.split("document.currentScript,", 1)[1].strip()
            candidates_raw.append(after)
    candidates_raw.append(payload)

    seen = set()
    for item in candidates_raw:
        if item in seen:
            continue
        seen.add(item)
        for variant in (item, sanitize_json_like(item)):
            try:
                result = json.loads(variant)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                continue
    raise ValueError("data.js payload 解析失败，疑似格式损坏（建议检查是否存在非法逗号/注释/未闭合结构）。")


def normalize_number(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(fallback)
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def extract_layers(obj: Any) -> list[dict[str, Any]]:
    layers: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        if isinstance(obj.get("layers"), list):
            for item in obj["layers"]:
                if isinstance(item, dict):
                    layers.append(item)
        if isinstance(obj.get("children"), list): # 兼容 MarkLion 新版的 children 结构
            for item in obj["children"]:
                if isinstance(item, dict):
                    layers.append(item)
        for val in obj.values():
            layers.extend(extract_layers(val))
    elif isinstance(obj, list):
        for item in obj:
            layers.extend(extract_layers(item))
    return layers


def clean_tree(obj: Any, issue_acc: dict[str, int], id_seen: dict[str, int], path: str = "root") -> Any:
    """递归清洗树结构，并保持原始层级。"""
    if isinstance(obj, dict):
        cleaned: dict[str, Any] = {}
        for key, val in obj.items():
            if (key == "layers" or key == "children") and isinstance(val, list):
                cleaned_layers = []
                for idx, layer in enumerate(val):
                    if not isinstance(layer, dict):
                        issue_acc["invalid_layer_type"] += 1
                        continue

                    layer_item = deepcopy(layer)
                    layer_id = str(layer_item.get("id", "")).strip()
                    if not layer_id:
                        layer_id = str(layer_item.get("guid", "")).strip() # 兼容 guid
                        
                    if not layer_id:
                        layer_id = f"auto_layer_{issue_acc['auto_id_count']}"
                        layer_item["id"] = layer_id
                        issue_acc["auto_id_count"] += 1
                    else:
                        layer_item["id"] = layer_id

                    id_seen[layer_id] = id_seen.get(layer_id, 0) + 1
                    if id_seen[layer_id] > 1:
                        new_id = f"{layer_id}__dup{id_seen[layer_id] - 1}"
                        layer_item["id"] = new_id
                        issue_acc["duplicate_id_rewritten"] += 1
                        id_seen[new_id] = 1

                    # 兼容 globalBounds 或 boundsInParent
                    bounds = layer_item.get("globalBounds", {}) or layer_item.get("boundsInParent", {})
                    if not isinstance(bounds, dict): bounds = {}
                    
                    for field in ("x", "y", "width", "height"):
                        if field not in layer_item or layer_item.get(field) in ("", None):
                            # fallback to bounds
                            if field in bounds and bounds.get(field) not in ("", None):
                                layer_item[field] = bounds.get(field)
                            else:
                                layer_item[field] = 0
                                issue_acc["missing_coordinate_filled"] += 1
                        else:
                            layer_item[field] = normalize_number(layer_item.get(field), 0)

                    width = normalize_number(layer_item.get("width"), 0)
                    height = normalize_number(layer_item.get("height"), 0)
                    is_text_layer = "text" in layer_item or "Text" in layer_item.get("types", {})
                    if width <= 0 or height < 0:
                        if not is_text_layer:
                            issue_acc["invalid_layer_filtered"] += 1
                            continue

                    layer_path = f"{path}.{key}[{idx}]"
                    cleaned_layers.append(clean_tree(layer_item, issue_acc, id_seen, layer_path))
                cleaned[key] = cleaned_layers
            else:
                cleaned[key] = clean_tree(val, issue_acc, id_seen, f"{path}.{key}")
        return cleaned
    if isinstance(obj, list):
        return [clean_tree(item, issue_acc, id_seen, f"{path}[]") for item in obj]
    return obj


def validate_and_clean(raw_data: dict[str, Any], raw_content: str) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []

    if not isinstance(raw_data, dict):
        raise ValueError("解析结果不是对象结构，无法执行清洗。")

    cleaned = deepcopy(raw_data)
    issue_acc = {
        "auto_id_count": 0,
        "duplicate_id_rewritten": 0,
        "missing_coordinate_filled": 0,
        "invalid_layer_filtered": 0,
        "invalid_layer_type": 0,
    }
    id_seen: dict[str, int] = {}
    cleaned = clean_tree(cleaned, issue_acc, id_seen)

    all_layers = extract_layers(cleaned)
    font_families = re.findall(r'"fontFamily"\s*:\s*"([^"]+)"', raw_content)
    font_sizes = re.findall(r'"fontSize"\s*:\s*([0-9]+(?:\.[0-9]+)?)', raw_content)
    text_nodes = re.findall(r'"text"\s*:\s*"([^"]*)"', raw_content)
    export_paths = re.findall(r'"exportPath"\s*:\s*"([^"]+)"', raw_content)

    # 颜色保真：解码所有 "fill":{"value":<ARGB int>} 出现的填充色
    # 标记狮把 ARGB 打包成 32-bit 整数（signed 或 unsigned 都可能出现），需要按 unsigned 还原
    color_raw_vals = re.findall(r'"value"\s*:\s*(-?\d+)', raw_content)
    palette_counter: Counter = Counter()
    for v in color_raw_vals:
        try:
            iv = int(v) & 0xFFFFFFFF
            a = (iv >> 24) & 0xFF
            r = (iv >> 16) & 0xFF
            g = (iv >> 8) & 0xFF
            b = iv & 0xFF
            hex_rgb = f"#{r:02X}{g:02X}{b:02X}"
            palette_counter[(hex_rgb, a)] += 1
        except (TypeError, ValueError):
            continue

    if len(all_layers) == 0:
        errors.append("画板图层为空（阻断级）。请检查 data.js 是否导出完整。")
    if len(text_nodes) == 0 and len(export_paths) == 0:
        errors.append("未检测到文本与切片节点（阻断级）。疑似空画板或导出异常。")
    if not any(str(item).strip() for item in font_families):
        warnings.append("未检测到有效字体声明，后续可能触发字体 fallback。")
    if issue_acc["duplicate_id_rewritten"] > 0:
        warnings.append(f"检测到重复图层 ID，已自动重写 {issue_acc['duplicate_id_rewritten']} 项。")
    if issue_acc["invalid_layer_filtered"] > 0:
        warnings.append(f"检测到无效图层，已过滤 {issue_acc['invalid_layer_filtered']} 项。")
    if issue_acc["missing_coordinate_filled"] > 0:
        warnings.append(f"检测到坐标缺失，已补全 {issue_acc['missing_coordinate_filled']} 项字段。")
    if issue_acc["auto_id_count"] > 0:
        warnings.append(f"检测到缺失 ID 图层，已自动补 ID {issue_acc['auto_id_count']} 项。")
    if issue_acc["invalid_layer_type"] > 0:
        warnings.append(f"检测到非对象图层条目，已忽略 {issue_acc['invalid_layer_type']} 项。")

    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "quality": "error" if errors else ("warning" if warnings else "ok"),
        "summary": {
            "layer_count": len(all_layers),
            "text_count": len(text_nodes),
            "export_path_count": len(export_paths),
            "font_count": len(font_families),
            "color_count": sum(palette_counter.values()),
        },
        "font_counter": Counter(font_families),
        "font_size_counter": Counter(font_sizes),
        "palette_top": [
            {"rgb": rgb, "alpha": round(a / 255, 3), "count": cnt}
            for (rgb, a), cnt in palette_counter.most_common(20)
        ],
        "issues": {
            "warnings": warnings,
            "errors": errors,
            "stats": issue_acc,
        },
    }
    return {"cleaned_data": cleaned, "report": report}


def main() -> int:
    parser = argparse.ArgumentParser(description="标记狮 data.js 校验与数据清洗工具")
    parser.add_argument("--data", required=True, help="data.js 的绝对路径")
    parser.add_argument("--report-json", help="数据质量报告输出路径（JSON）")
    parser.add_argument("--cleaned-output", help="清洗后数据输出路径（JSON）")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式：出现 warning 也返回非 0（用于 CI）",
    )
    args = parser.parse_args()

    data_path = os.path.abspath(args.data)
    if not os.path.exists(data_path):
        print(f"错误：文件不存在 -> {data_path}")
        return 2
    if not os.path.isfile(data_path):
        print(f"错误：路径不是文件 -> {data_path}")
        return 2

    try:
        content = read_text_file(data_path)
        parsed_data = parse_data(content)
        result = validate_and_clean(parsed_data, content)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"校验失败：{exc}")
        return 1

    report = result["report"]
    print("校验完成：检测到标记狮画板数据。")
    print(f"质量等级：{report['quality']}")
    print(f"图层数量：{report['summary']['layer_count']}")
    print(f"文本节点数量：{report['summary']['text_count']}")
    print(f"切片节点数量（exportPath）：{report['summary']['export_path_count']}")

    print("字体家族统计（Top 10）：")
    for family, count in report["font_counter"].most_common(10):
        print(f"- {family}: {count}")

    print("字号统计（Top 10）：")
    for size, count in report["font_size_counter"].most_common(10):
        print(f"- {size}: {count}")

    print("调色板（Top 10 出现次数最多的填充色）：")
    for entry in report["palette_top"][:10]:
        print(f"- {entry['rgb']} (alpha={entry['alpha']}) x{entry['count']}")

    if report["issues"]["warnings"]:
        print("警告项：")
        for item in report["issues"]["warnings"]:
            print(f"- [warn] {item}")
    if report["issues"]["errors"]:
        print("错误项：")
        for item in report["issues"]["errors"]:
            print(f"- [error] {item}")

    if args.report_json:
        report_path = os.path.abspath(args.report_json)
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"已输出数据质量报告：{report_path}")

    if args.cleaned_output:
        cleaned_path = os.path.abspath(args.cleaned_output)
        os.makedirs(os.path.dirname(cleaned_path), exist_ok=True)
        with open(cleaned_path, "w", encoding="utf-8") as f:
            json.dump(result["cleaned_data"], f, ensure_ascii=False, indent=2)
        print(f"已输出清洗数据：{cleaned_path}")

    if report["issues"]["errors"]:
        return 1
    if args.strict and report["issues"]["warnings"]:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
