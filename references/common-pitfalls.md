# 常见陷阱清单（基于 v3.5 → v3.6 的真实事故沉淀）

每条都附：**现象 / 根因 / 修复**。在阶段二开工前通读一遍，能省下大部分返工。

---

## 1. data.js 节点坐标系统认知错误

**现象**：summarize 出来的坐标全是大负数（-12009, -13958 之类）。

**根因**：标记狮 `cleaned-data.json` 的 `globalBounds` 是相对于一个任意原点的绝对坐标；artboard 自身的 `globalBounds.{x,y}` 就是这个原点（常见 `-12506, -14181`）。另外节点里确实有 `x/y/width/height` 字段，但等于 `globalBounds`，也是绝对坐标；想要画板内坐标必须减原点。

**修复**：
```python
origin = (artboard['globalBounds']['x'], artboard['globalBounds']['y'])
node_x = node['globalBounds']['x'] - origin[0]
node_y = node['globalBounds']['y'] - origin[1]
```
**不要**用 `boundsInParent` —— 它对嵌套节点是相对父节点的坐标，在扁平化遍历时会累加错位。

---

## 2. 共享层已吃掉 70px 导航偏移，子页坐标需要再减

**现象**：子页还原出来像"整体往下掉了一条导航的高度"，标题被推到屏外。

**根因**：data.js 画板是 1920×1080 且包含顶部导航；但阶段一 `marklion-layout` 的 `<router-view>` 槽位只有 `1920×(1080-navHeight)`，坐标原点在导航下沿。子页直接把 data.js 的 y 喂进 CSS `top` 就会整体下沉。

**修复**：子页组件里定义 `Y_OFFSET = -navHeight`，所有 `posStyle(x, y, w, h)` 里对 y 做一次 `y + Y_OFFSET`。示例：
```js
const Y_OFFSET = -PAGE_DESIGN.navHeight  // -70
posStyle (x, y, w, h) {
  return { position: 'absolute', left: x + 'px', top: (y + Y_OFFSET) + 'px', width: w + 'px', height: h + 'px' }
}
```

---

## 3. exportPath 引用的 png 只有一半真实存在

**现象**：`cp png/32.png` / `cp png/41.png` / `cp png/51.png` 报 "No such file or directory"。

**根因**：标记狮对"视觉相同但 guid 不同"的节点（比如 6 块卡片框都是 464×308 `组 103939`）会给每份分配独立 exportPath（30/31/32/33/34/35），但只实际导出一份（30）或两份（30、31）png。按 exportPath 找资源会丢一半。

**修复**：
- 写资产索引前，先做差集检查：`{exportPath ids} \ {存在的 png 文件 id} = 缺失列表`
- 缺失节点用视觉等价的 id 回落；阶段一就应该记录"卡片框 / 仪表盘 / 告警条 / 计划条"各自的主 png
- 实际回落示例（首页总览-01）：30 → {31,32,33,34,35}；40 → {41}；43 → {45,47}；50 → {51,52,53,54,55}

---

## 4. qiankun 子应用 router base 与主应用激活路径不一致 → 整页空白

**现象**：浏览器访问主应用给的子应用 URL（如 `/web-ui/`），页面结构正常，但 `<router-view>` 输出为空，整页白。

**根因**：
```js
base: window.__POWERED_BY_QIANKUN__ ? process.env.VUE_APP_ROUTER_NAME : process.env.VUE_APP_MODULE_NAME
```
当 `VUE_APP_ROUTER_NAME` 和主应用实际挂载路径不一致时（例如 `/energyfuture-template` vs 主应用实际在 `/web-ui`），router 始终在错误 base 下剥离路径，匹配不到任何路由。

**修复**：
- 开工前必须确认主应用怎么注册子应用；把 `VUE_APP_ROUTER_NAME` 对齐到主应用实际激活路径
- 或更稳：从 qiankun `props.routerBase` 读取（如果主应用透传）
- 验收步骤必须包含"浏览器真正打开一次 qiankun URL"，不能只看 build 通过

---

## 5. `npm run lint` 不可靠，验收用 build

**现象**：`npx vue-cli-service lint` 报 `Error: Invalid Options: Unknown options: cacheStrategy`。

**根因**：`@vue/cli-plugin-eslint` 与新版 `eslint` 选项不兼容（vue-cli 3/4 时代的已知历史问题）。不是代码错，也不是我的编辑错。

**修复**：改用 `npx vue-cli-service build --mode development --no-clean` 作为最低通过门槛，它跑 vue-loader + babel + webpack，能捕获模板语法、import 错误、资源路径错误。dev server 启动也可以但慢。

---

## 6. Vue 模板 `:style.color=` 是无效写法，编译器静默忽略

**现象**：build 通过，运行时颜色没生效。

**根因**：Vue 2 的 `:style` 不接受类似 `:style.color` 的修饰符写法（这是 `:class` 或一些指令的语法，但不在 `:style` 上）。Vue 对未知绑定修饰符是静默丢弃，不报错。

**修复**：所有样式合并进一个对象：
```html
<!-- ✗ -->
<span :style="posStyle(...)" :style.color="t.color">
<!-- ✓ -->
<span :style="{ ...posStyle(...), color: t.color }">
```

---

## 7. Windows bash 下 `cp` 中文路径会乱码

**现象**：`cp "E:/.../标记狮/res/..." "..."` 报 "No such file or directory"，但 `ls` 看得到。

**根因**：Git-Bash 在 Windows 下对命令行参数的 UTF-8 解码在 `cp` 和 `cd` 之间表现不一致，相对路径在 `cd` 之后能找到，绝对路径作为 `cp` 参数就乱码。

**修复**：
```bash
cd "E:/project/标记狮/res/首页总览-01/png" && cp 30.png /target/ && cp 31.png /target/
```
或者在 Powershell 里用 `Copy-Item`，或者用 Python `shutil.copy2` 脚本化。

---

## 8. 164 个文本节点 + 83 个切片，平铺无法读

**现象**：`cleaned-data.json` 近 3MB，`text-layers.json` 1000+ 行，直接逐条看就废了。

**修复**：用 `scripts/summarize_cleaned_data.py` 按 1920 画板做四分桶（top-nav / left-col / middle-col / right-col，按节点中心点归类），每块按 `(y, x)` 排序输出一行一节点的文本摘要，含 `[x,y] WxH text='...' fill=#HEX export=ID`。还原时只看这一份摘要 + 原 preview.png 即可。

---

## 9. 地图省份标签：叠加在 echarts 上还是用 echarts label？

**权衡**：
- echarts `geo.label` 的 position 由真实 geoJSON 几何中心决定，不等于设计稿里设计师手摆的位置
- 要 1:1 还原设计坐标必须用 HTML 绝对定位叠加（`z-index` 高于 echarts canvas）
- 但这样就放弃了地图缩放时 label 跟随的能力

**建议**：像素级还原走 HTML overlay；功能级或需要缩放交互走 echarts label。监测站点同理。

---

## 10. 颜色必须走 `fill.value` ARGB 解码，不能目测

再强调一次（KR12）：ARGB int → `#RRGGBB` 的转换
```python
v = int(fill_value) & 0xFFFFFFFF
r, g, b = (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF
alpha = ((v >> 24) & 0xFF) / 255
```
preview.png 是压缩过的、浏览器渲染的位图，肉眼吸管得到的色值可能差 2-5 位。写色值前看 `data-quality.json` 的 `palette_top`。
