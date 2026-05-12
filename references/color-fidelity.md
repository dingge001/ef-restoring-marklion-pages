# 颜色保真参考（Color Fidelity）

标记狮 `data.js` 里每个填充色都是 ARGB 32-bit 整数（可能以 signed int 存），Agent 必须按此解码落地，不能目测/估色。

## 1. 解码规则

标记狮 `data.js` 中颜色的存储形式统一为：

```json
{"fill": {"value": 4281545523}}
```

该整数是 `0xAARRGGBB` 的无符号 32-bit 表示。部分旧导出可能出现负数（signed int），需先 `& 0xFFFFFFFF`。

**Python 解码示例：**
```python
def decode_argb(val):
    iv = int(val) & 0xFFFFFFFF
    a = (iv >> 24) & 0xFF
    r = (iv >> 16) & 0xFF
    g = (iv >> 8) & 0xFF
    b = iv & 0xFF
    return f"#{r:02X}{g:02X}{b:02X}", round(a / 255, 3)
```

**JS 解码示例：**
```js
function decodeArgb(val) {
  const iv = (val >>> 0) // 转为 uint32
  const a = (iv >>> 24) & 0xFF
  const r = (iv >>> 16) & 0xFF
  const g = (iv >>> 8) & 0xFF
  const b = iv & 0xFF
  return { rgb: `#${[r,g,b].map(x => x.toString(16).padStart(2,'0').toUpperCase()).join('')}`, alpha: a/255 }
}
```

## 2. 常见坑

| 坑 | 现象 | 处理 |
|---|---|---|
| 目测取色 | 写成 `#7DB6E9` 其实是 `#00377B` | 必须走解码脚本，禁止凭 preview 取色 |
| 按 signed 解读 | 负数 `fill.value` 丢位 | 先 `& 0xFFFFFFFF` 再分段 |
| alpha 忽略 | 色值对了但透明度掉了 | 半透明节点要把 alpha 同步落到 CSS `rgba()` 或 `opacity` |
| 主题反转 | viewport 底色跟设计稿相反（浅色稿写成深底） | 阶段一结束前必须对照 `preview.png` 主题 |
| 全局背景无填充 | 1920×1080 背景图层没有 fill.value（靠图片或外层色） | 从 preview 采样 + 对照其他全屏图层 |

## 3. 取主题底色的正规流程（阶段一必做）

1. 打开 `标记狮/res/<代表页>/preview.png` 或 `preview.mini.png`。
2. 用取色工具（或 Python PIL）采样设计稿 4 个角的像素：
   ```python
   from PIL import Image
   im = Image.open('preview.png').convert('RGB')
   w, h = im.size
   corners = [im.getpixel((0, 0)), im.getpixel((w-1, 0)), im.getpixel((0, h-1)), im.getpixel((w-1, h-1))]
   print(corners)
   ```
3. 取 4 个角中出现次数最多的颜色作为 viewport / stage 底色。
4. 同步到：
   - `marklion-layout.vue` 的 `.marklion-viewport { background: <RGB>; }`
   - `.marklion-stage { background: <RGB>; }`
5. 在浏览器里把视口宽度开到 >1920，看四周色块是否跟 preview 一致。

## 4. 与 validate_marklion_data.py 集成

`validate_marklion_data.py` 已在 3.5.0 起自动输出 `palette_top` —— 即 `data.js` 中出现次数最多的填充色 Top 20。写 CSS 前**先查这张表**：出现次数 ≥ 2 的颜色都应该进入设计 token，一次性写在 `marklion-shared-data.js` 或 CSS variable 里，阶段二复用。

```bash
python validate_marklion_data.py --data "<page>/data.js" --report-json "quality.json"
# 然后读 quality.json.palette_top
```

## 5. 反例回顾

本技能 3.4.0 版本在首页总览 01 还原中：
- `marklion-viewport` 写了 `#051225`（深蓝）—— 设计稿实际是浅色 `#E8EEF5`
- 菜单文字写了 `#7DB6E9`（浅蓝）—— 设计稿实际是 `#00377B`（深蓝）
- 原因：没走 ARGB 解码，按"深色仪表盘"的惯性色板写码。

预防：把 "KR12 颜色保真" 纳入 P0 并加到交付验收清单。
