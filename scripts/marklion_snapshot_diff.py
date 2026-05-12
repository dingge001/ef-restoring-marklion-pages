#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""标记狮还原快照与增量差异分析脚本。"""

import argparse
import hashlib
import json
import os
from datetime import datetime
from typing import Any


def read_text(path: str) -> str:
    encodings = ["utf-8", "utf-8-sig", "gbk", "gb18030"]
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="strict") as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def extract_payload(content: str) -> str:
    marker = "marklion_artboard("
    start = content.find(marker)
    if start < 0:
        raise ValueError("未发现 marklion_artboard 调用")
    i = start + len(marker)
    depth = 1
    in_str = False
    quote = ""
    escaped = False
    while i < len(content):
        ch = content[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                in_str = False
        else:
            if ch in ("'", '"'):
                in_str = True
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return content[start + len(marker) : i].strip()
        i += 1
    raise ValueError("marklion_artboard 入参未闭合")


def parse_data(content: str) -> dict[str, Any]:
    payload = extract_payload(content)
    payload = payload.strip()
    payload = payload.replace(",}", "}").replace(",]", "]")
    return json.loads(payload)


def flatten_layers(obj: Any) -> list[dict[str, Any]]:
    layers: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        if isinstance(obj.get("layers"), list):
            for item in obj["layers"]:
                if isinstance(item, dict):
                    layers.append(item)
        for val in obj.values():
            layers.extend(flatten_layers(val))
    elif isinstance(obj, list):
        for item in obj:
            layers.extend(flatten_layers(item))
    return layers


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def layer_signature(layer: dict[str, Any], index: int) -> tuple[str, str]:
    key = str(layer.get("id") or layer.get("name") or f"layer_{index}")
    basis = {
        "name": layer.get("name"),
        "type": layer.get("type"),
        "text": layer.get("text"),
        "x": layer.get("x"),
        "y": layer.get("y"),
        "width": layer.get("width"),
        "height": layer.get("height"),
        "opacity": layer.get("opacity"),
        "exportPath": layer.get("exportPath"),
        "assetId": ((layer.get("fill") or {}).get("assetId") if isinstance(layer.get("fill"), dict) else None),
    }
    return key, stable_hash(basis)


def build_snapshot(data: dict[str, Any], data_path: str) -> dict[str, Any]:
    layers = flatten_layers(data)
    signatures: dict[str, str] = {}
    for idx, layer in enumerate(layers):
        key, sig = layer_signature(layer, idx)
        if key in signatures:
            key = f"{key}__{idx}"
        signatures[key] = sig

    board_name = str(data.get("name") or os.path.basename(os.path.dirname(data_path)) or "board")
    return {
        "board_name": board_name,
        "source_data_path": os.path.abspath(data_path),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "layer_count": len(layers),
        "layers": signatures,
        "snapshot_hash": stable_hash(signatures),
    }


def diff_snapshot(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    old_layers: dict[str, str] = old.get("layers", {})
    new_layers: dict[str, str] = new.get("layers", {})
    old_keys = set(old_layers.keys())
    new_keys = set(new_layers.keys())

    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    common = sorted(old_keys & new_keys)
    modified = [k for k in common if old_layers[k] != new_layers[k]]

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "summary": {
            "added_count": len(added),
            "removed_count": len(removed),
            "modified_count": len(modified),
            "changed": bool(added or removed or modified),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="标记狮快照差异分析")
    parser.add_argument("--data", required=True, help="data.js 绝对路径")
    parser.add_argument("--snapshot-dir", required=True, help="快照目录")
    parser.add_argument("--snapshot-name", help="快照文件名（默认 board 名称）")
    parser.add_argument("--write-snapshot", action="store_true", help="比较后写入当前快照")
    parser.add_argument("--report-json", help="差异报告输出路径")
    args = parser.parse_args()

    data_path = os.path.abspath(args.data)
    if not os.path.exists(data_path):
        print(f"错误：文件不存在 -> {data_path}")
        return 2

    try:
        content = read_text(data_path)
        data = parse_data(content)
        current_snapshot = build_snapshot(data, data_path)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"快照构建失败：{exc}")
        return 1

    snapshot_dir = os.path.abspath(args.snapshot_dir)
    os.makedirs(snapshot_dir, exist_ok=True)
    snapshot_name = args.snapshot_name or f"{current_snapshot['board_name']}.snapshot.json"
    snapshot_path = os.path.join(snapshot_dir, snapshot_name)

    old_snapshot = None
    if os.path.exists(snapshot_path):
        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                old_snapshot = json.load(f)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"历史快照读取失败：{exc}")
            return 1

    if old_snapshot is None:
        diff = {
            "summary": {
                "changed": True,
                "message": "未发现历史快照，当前视为首次全量还原基线。",
            },
            "added": sorted(list(current_snapshot["layers"].keys())),
            "removed": [],
            "modified": [],
        }
    else:
        diff = diff_snapshot(old_snapshot, current_snapshot)

    print("快照差异报告：")
    if "message" in diff["summary"]:
        print(f"- {diff['summary']['message']}")
    else:
        print(f"- 新增图层: {diff['summary']['added_count']}")
        print(f"- 删除图层: {diff['summary']['removed_count']}")
        print(f"- 修改图层: {diff['summary']['modified_count']}")

    report = {
        "snapshot_path": snapshot_path,
        "old_snapshot_exists": old_snapshot is not None,
        "current_snapshot_hash": current_snapshot["snapshot_hash"],
        "diff": diff,
    }

    if args.report_json:
        report_path = os.path.abspath(args.report_json)
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"已输出差异报告：{report_path}")

    if args.write_snapshot:
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(current_snapshot, f, ensure_ascii=False, indent=2)
        print(f"已写入快照：{snapshot_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
