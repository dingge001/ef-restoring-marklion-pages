#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对标记狮 validate_marklion_data.py 产出的 cleaned-data.json 做分区摘要，
便于 LLM 阅读而不直接读 3MB json。

分区规则（以节点中心点归类，1920×1080 画板）：
  top-nav    : center_y < NAV_HEIGHT（默认 70）
  left-col   : center_x < LEFT_CUT（默认 468）
  middle-col : LEFT_CUT <= center_x < RIGHT_CUT（默认 1450）
  right-col  : center_x >= RIGHT_CUT

输出：
  <out-dir>/layout-summary.txt    文本版分桶摘要
  <out-dir>/text-layers.json      仅文本层（含坐标、颜色、字体）
  <out-dir>/export-paths.json     仅切片层（含 exportPath）

用法：
  python summarize_cleaned_data.py \
    --cleaned  .../out/home-overview-01/cleaned-data.json \
    --out-dir  .../out/home-overview-01 \
    [--nav-height 70] [--left-cut 468] [--right-cut 1450]

坐标换算：globalBounds 相对某个负原点，这里减去 artboard.globalBounds 得到画板内坐标。
"""
import argparse
import json
import os
import sys


def argb_to_hex(val):
    if val is None:
        return ''
    try:
        v = int(val)
    except Exception:
        return ''
    if v < 0:
        v = v & 0xFFFFFFFF
    a = (v >> 24) & 0xFF
    r = (v >> 16) & 0xFF
    g = (v >> 8) & 0xFF
    b = v & 0xFF
    return f'#{r:02X}{g:02X}{b:02X}(a={a/255:.2f})'


def flatten(nodes, out, parent_path=''):
    for n in nodes:
        if not isinstance(n, dict):
            continue
        name = n.get('name') or ''
        path = f'{parent_path}/{name}' if parent_path else name
        out.append((path, n))
        children = n.get('children') or []
        if isinstance(children, list):
            flatten(children, out, path)


def get_xywh(node, origin):
    b = node.get('globalBounds') or {}
    if not b:
        return 0.0, 0.0, 0.0, 0.0
    try:
        return (
            float(b.get('x', 0)) - origin[0],
            float(b.get('y', 0)) - origin[1],
            float(b.get('width', 0)),
            float(b.get('height', 0)),
        )
    except Exception:
        return 0.0, 0.0, 0.0, 0.0


def extract_fill(node):
    text = node.get('text') or ''
    fill_val = None
    fo = node.get('fill')
    if isinstance(fo, dict):
        fill_val = fo.get('value')
    if text and not fill_val:
        sr = node.get('styleRanges') or []
        if sr and isinstance(sr[0], dict):
            fo2 = sr[0].get('fill')
            if isinstance(fo2, dict):
                fill_val = fo2.get('value')
    return fill_val


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cleaned', required=True, help='cleaned-data.json 路径')
    ap.add_argument('--out-dir', required=True, help='输出目录')
    ap.add_argument('--nav-height', type=int, default=70)
    ap.add_argument('--left-cut', type=int, default=468)
    ap.add_argument('--right-cut', type=int, default=1450)
    ap.add_argument('--per-region-limit', type=int, default=500,
                    help='每个分桶最多输出多少条，避免超大页面爆文本')
    args = ap.parse_args()

    with open(args.cleaned, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if isinstance(data, list):
        artboards = data
    elif isinstance(data, dict):
        if 'artboards' in data:
            artboards = data['artboards']
        else:
            artboards = [data]
    else:
        print('cleaned-data.json 格式不识别', file=sys.stderr)
        sys.exit(1)

    artboard = artboards[0] if artboards else {}
    gb = artboard.get('globalBounds') or {'x': 0, 'y': 0}
    origin = (float(gb.get('x', 0)), float(gb.get('y', 0)))

    all_nodes = []
    for ab in artboards:
        children = ab.get('children') or ab.get('layers') or []
        flatten(children, all_nodes)

    text_layers = []
    export_layers = []
    regions = {
        'top-nav':    [],
        'left-col':   [],
        'middle-col': [],
        'right-col':  []
    }

    for path, n in all_nodes:
        x, y, w, h = get_xywh(n, origin)
        text = n.get('text') or ''
        if not isinstance(text, str):
            text = ''
        export_path = n.get('exportPath')
        fill_val = extract_fill(n)
        hex_c = argb_to_hex(fill_val) if fill_val is not None else ''

        entry = {
            'path': path,
            'name': n.get('name', ''),
            'x': round(x, 1), 'y': round(y, 1), 'w': round(w, 1), 'h': round(h, 1),
            'text': text,
            'export': export_path,
            'fill': hex_c,
            'font': n.get('fontFamily', ''),
            'fontSize': n.get('fontSize', ''),
        }

        if text:
            text_layers.append(entry)
        if export_path:
            export_layers.append(entry)

        cx = x + w / 2
        cy = y + h / 2
        if cy < args.nav_height:
            regions['top-nav'].append(entry)
        elif cx < args.left_cut:
            regions['left-col'].append(entry)
        elif cx < args.right_cut:
            regions['middle-col'].append(entry)
        else:
            regions['right-col'].append(entry)

    os.makedirs(args.out_dir, exist_ok=True)
    text_path = os.path.join(args.out_dir, 'text-layers.json')
    export_path = os.path.join(args.out_dir, 'export-paths.json')
    summary_path = os.path.join(args.out_dir, 'layout-summary.txt')

    with open(text_path, 'w', encoding='utf-8') as f:
        json.dump(text_layers, f, ensure_ascii=False, indent=2)
    with open(export_path, 'w', encoding='utf-8') as f:
        json.dump(export_layers, f, ensure_ascii=False, indent=2)

    lines = []
    lines.append(f'artboard origin: {origin}')
    lines.append(f'节点总数：{len(all_nodes)}')
    lines.append(f'文本节点数：{len(text_layers)}')
    lines.append(f'切片节点数：{len(export_layers)}')
    lines.append('')
    for region, items in regions.items():
        lines.append(f'=== {region} ({len(items)} items) ===')
        items_sorted = sorted(items, key=lambda e: (e['y'], e['x']))
        for it in items_sorted[:args.per_region_limit]:
            t = it['text'][:40].replace('\n', ' ')
            lines.append(
                f"  [{int(it['x']):4d},{int(it['y']):4d}] "
                f"{int(it['w']):4d}x{int(it['h']):4d} "
                f"text='{t}' fill={it['fill']} "
                f"font={it['fontSize']} export={it['export'] or ''}"
            )
        if len(items_sorted) > args.per_region_limit:
            lines.append(f"  ... 截断 {len(items_sorted) - args.per_region_limit} 条 ...")
        lines.append('')

    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f'wrote {summary_path}')
    print(f'wrote {text_path}')
    print(f'wrote {export_path}')


if __name__ == '__main__':
    main()
