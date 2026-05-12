---
name: ef-restoring-marklion-pages
description: "[快捷命令：/EF-标记狮还原] 当用户需要基于标记狮导出文件进行两阶段页面还原（阶段一公共抽离、阶段二单页面还原）并要求稳定交付与高一致视觉时触发。"
metadata:
  version: "3.6.0"
  slash_command: "/EF-标记狮还原"
  python_version: ">=3.8"
  last_updated: "2026-05-11"
---

# 目标 (Objective)
**将标记狮还原流程固定为“阶段一公共抽离 + 阶段二单页还原”的稳定流水线，优先保障可维护、可复用、可验收，并持续收口到高度还原。**

# 关键结果 (Key Results)
## P0 强制
1. **KR1 (两阶段门禁)**: 必须先完成阶段一共享层抽离并产出共享模块，再允许进入阶段二单页开发。
2. **KR2 (技术栈一致)**: 必须检测并复用项目现有技术栈与依赖，不得引入未使用框架/组件库。
3. **KR3 (数据可用)**: 每次还原前必须完成 `data.js` 解析与清洗，输出 warning/error 分级结果；error 必须阻断。
4. **KR4 (非贴图交付)**: 默认交付必须是图层代码渲染（切片/文本/交互），严禁 `preview.png` 或整图背景冒充还原。
5. **KR5 (局部修复原则)**: 局部问题必须局部修复，禁止通过全局文本/布局样式“一刀切”修复。
6. **KR6 (路由画面一致)**: 必须验证“路由切换 + 页面主视觉变化 + 资源目录正确绑定”三点一致。
7. **KR7 (最小验收闭环)**: 每次交付至少包含一次可运行验证（build/dev 成功）+ 关键区域对齐结果。
8. **KR8 (验收等级先确认)**: 开工前必须先确认验收等级（默认 `1:1 像素级`）；若用户未放宽标准，禁止按“结构占位/大致相似”交付。
9. **KR9 (响应式可用)**: 在保持 1920 设计基准像素对齐的前提下，必须提供响应式适配策略（等比缩放或断点重排）并可在常见分辨率正常使用。
10. **KR10 (宽屏无左右留白)**: 非 F11 宽屏窗口（如 1536x864）默认不得出现两侧大面积空白；需要具备“按宽度铺满 + 顶部对齐”策略。
11. **KR11 (顶部导航公共化)**: 顶部菜单点击区域必须抽为共享层组件并被所有页面复用，禁止在多个页面重复粘贴热区坐标与跳转逻辑。
12. **KR12 (颜色保真)**: 所有文字/填充色必须来自 `data.js` 的 `fill.value` 解码（ARGB 32-bit int → #RRGGBB），禁止凭 preview 目测或想当然写色值。viewport/容器底色必须与设计稿主题（浅/深）一致，交付前要在浏览器中对照 `preview.png` 做主题确认。详见 `references/color-fidelity.md`。

## P1 推荐
13. **KR13 (字体一致)**: 字体映射与 `@font-face` 完整落地，避免 fallback 导致字宽偏差。开工前应预检 `common.scss` / 全局样式里已声明但未提供的字体文件，给用户一次性清单。
14. **KR14 (共享复用)**: 新页面优先复用共享层，避免重复建设导航、菜单、背景。
15. **KR15 (回归稳定)**: 关键交互（展开/收起、入口点击、分页）不回退。

# 最佳实践 (Best Practice)
> Agent 必读：请先阅读《用户使用向导》：`{baseDir}/skills/ef-restoring-marklion-pages/references/usage-guide.md`。
> 若用户首次发起还原，请优先给出向导中的一句话指令模板。

## 阶段一：公共抽离（必须先做）
### 步骤 1: 确认改造边界
- 必问：
  - `A. 新增并行路由`（默认）
  - `B. 替换现有页面`
- 未明确前，禁止覆盖旧页面。
- 必问验收等级（默认 `1:1 像素级`）：
  - `A. 像素级（默认）`
  - `B. 高仿级（用户明确同意时）`
  - `C. 功能级（仅演示/临时联调时）`
- 若未获得用户明确降级确认，必须按像素级执行。

### 步骤 2: 技术栈检测（P0）
- 执行：
```bash
python {baseDir}/skills/ef-restoring-marklion-pages/scripts/detect_project_stack.py --project-root "<项目根目录>" --out-json "<输出>/stack-report.json" --verbose
```
- 代码模板必须严格匹配检测结果（Vue2/ Vue3/ React/ Angular）。

### 步骤 3: 共享层识别（P0）
- 跨页面识别并确认：顶部导航、全局背景、左侧菜单、公共容器。
- 对复杂场景优先交互式确认（向用户发选项确认共享模块）。
- 推荐执行：
```bash
python {baseDir}/skills/ef-restoring-marklion-pages/scripts/extract_shared_layout.py \
  --res-dir "<项目>/标记狮/res" \
  --out-json "<输出>/semantic-shared-layers.json" \
  --out-report "<输出>/shared-layers-report.md"
```
- 脚本会按模块前缀聚类，并输出全局高频顶部节点（含颜色 RGB、坐标、尺寸、文本/exportPath）。**所有脚本参数均为 CLI 传入，不写死路径，可跨项目复用。**

### 步骤 4: 产出共享层文件（P0）
- 必须产出（命名可按业务域调整）：
  - `src/views/marklion-shared/<module>-shared-data.js`
  - `src/api/<module>-shared-layout.js` 或 `src/views/<module>/shared-layout.js`
  - `src/views/marklion-shared/<module>-layout.vue`
  - `src/views/marklion-shared/<module>-top-nav-hotspots.vue`（或同等公共顶部导航组件）
- 阶段一交付物缺失时，禁止进入阶段二。

## 阶段二：单页面还原（复用阶段一）

### 起手预检（P0，先做再写代码）
开工前必须逐项确认，跳过任何一项都会直接导致白屏或错位：

1. **坐标系换算** —— data.js 用 1920×1080 画板坐标，但共享层 body 已经占掉顶部 `navHeight`（示例项目 70px）。子页组件容器实际是 `1920×(1080-navHeight)`，**所有子节点 y 都要做 `y - navHeight`**，否则整页下沉一条导航的高度。可在组件里写 `shiftY = y - navHeight` 小工具函数统一处理。
2. **globalBounds 坐标系** —— 标记狮 `cleaned-data.json` 里 `globalBounds.x/y` 是相对于一个任意原点（常见 `-12506, -14181`）的绝对坐标，不是画板内坐标。取坐标时必须减去 `artboard.globalBounds.{x,y}` 才对齐到 0-1920。不要用 `boundsInParent`，它对嵌套节点是相对坐标。
3. **切片资源完整性** —— `exportPath` 里的 id 不等于 png 文件名一定存在。标记狮对视觉相同但 guid 不同的节点（同一 shape 被复用多次）会分配独立 exportPath，但只对其中一份导出 png/svg。写代码前先把 `export-paths.json` 里的所有 id 与磁盘上的 `png/*.png`（不含 `@2x/@3x`）做差集，缺失的用视觉等价的 id 回落（常见：卡片框 30 → 32/33/34/35；仪表盘 40 → 41；告警条 43 → 45/47；计划条 50 → 51-55）。
4. **路由 base 与主应用激活路径一致** —— qiankun 子应用的 `router.base` 必须等于主应用激活该子应用的路径前缀。env 里 `VUE_APP_ROUTER_NAME` 和 `VUE_APP_MODULE_NAME` 对不上时，浏览器 URL 与 router 匹配失败→整页空白。上线前在 dev 打开一次浏览器 URL 验证，不要只靠 build 通过。
5. **验收手段** —— 不要依赖 `npm run lint`（vue-cli-service 3.x 与 eslint 新版本易冲突，报 `Unknown options: cacheStrategy` 之类假错），用 `npx vue-cli-service build --mode development --no-clean` 作为最低通过标准。

### 步骤 1: 数据解析与清洗（P0）
- 执行：
```bash
python {baseDir}/skills/ef-restoring-marklion-pages/scripts/validate_marklion_data.py --data "<data.js绝对路径>" --report-json "<输出>/data-quality.json" --cleaned-output "<输出>/cleaned-data.json"
```
- Windows 控制台如遇 `UnicodeEncodeError`，在命令前加 `PYTHONIOENCODING=utf-8`。
- **区分两种 data.js**：项目根下 `res/data.js` 是画板索引（含 `__marklionData.artboards`），不要直接校验；必须传入 `res/<页面名>/data.js`。脚本会识别并给出明确指引。
- `error` 直接中止并给修复建议；`warning` 需在汇报中展示。
- 校验报告会输出 `palette_top`（Top 20 调色板），**开工写色值必须以此为准**，不要凭 preview 目测写颜色。

### 步骤 2: 资源入库（P0）
- 禁止运行时代码直接依赖 `标记狮/res/...`。
- 必须复制到项目资产目录（如 `src/assets/marklion/<page>/...`）后再引用。

### 步骤 3: 分层渲染（P0）
- 切片层：按坐标/尺寸/z-index 渲染。
- 文本层：按字体、字号、行高、字距渲染。
- 交互层：热区与状态联动。
- 禁止“整图贴底”替代图层代码。

### 步骤 4: 像素收口（P0）
- 仅允许定点修复：
  - 例：单个标题换行异常 -> 节点白名单或局部 class 修复。
- 禁止全局策略改动误伤全页：
  - 如全局 `white-space`、全局 `line-height`、全局 `letter-spacing`。

### 步骤 5: 响应式适配（P0）
- 必须说明并实现一种策略：
  - `A. 1920 基准等比缩放`（推荐）
  - `B. 断点重排（如 1920/1600/1366）`
- 禁止通过破坏像素基准的全局文本压缩“伪响应式”过验收。
- 响应式仅允许局部适配规则，不得影响 1920 基准稿的像素对齐。
- 若采用 `A. 1920 基准等比缩放`，必须实现以下默认规则（防止非全屏左右留白）：
  - 计算：`xScale = viewportWidth / designWidth`，`yScale = viewportHeight / designHeight`
  - 计算：`viewportRatio = viewportWidth / viewportHeight`，`designRatio = designWidth / designHeight`
  - 当 `viewportWidth <= 1024` 或 `viewportRatio >= designRatio` 时：使用 `scale(xScale)`，容器 `translateX(-50%)` 顶部对齐
  - 其他场景：使用 `scale(min(xScale, yScale))`，容器保持居中
  - 禁止把“是否 mobile”仅等同于“小屏宽度”，应按“是否需要顶部对齐铺满”判定

### 步骤 6: 验收与回归（P0）
- build/dev 至少通过一项。
- 验证“路由-画面-资源”一致。
- 关键区对齐（顶部标题、导航、左侧树/菜单、主容器）至少各抽查 1 项。
- 响应式抽查至少 2 个分辨率（建议：`1920x1080` + `1366x768`）。

# 强门禁清单 (Hard Gates)
1. **禁止贴图交付**：发现 `preview.png/preview.mini.png` 作为主渲染即判失败。
2. **禁止跳过共享层复用确认**：进入单页编码前必须完成以下其一：`A. 新项目完成阶段一共享层抽离`；`B. 旧项目已确认并复用现有公共层（导航/背景/菜单等）`。两者都未满足时判失败。
3. **禁止全局误伤**：局部问题使用全局样式修复且未做影响面回归，判失败。
4. **禁止技术栈漂移**：与项目既有依赖不一致（如 Vue2 写 `<script setup>`），判失败。
5. **禁止骨架占位冒充还原**：仅完成头部/侧栏框架但未按设计图层坐标渲染公共层，判失败。
6. **禁止伪响应式**：通过全局改字距/行高/缩字体等方式“挤压适配”且未做分辨率回归，判失败。
7. **禁止顶部导航重复实现**：发现顶部导航热区/跳转在多个页面各自实现且未抽公共组件，判失败。
8. **禁止目测配色**：视觉稿文字/填充色未来自 `data.js` 的 `fill.value` 解码；或 viewport/容器底色与设计稿主题（浅/深）明显不一致，判失败。

# 异常处理手册
## E1: data.js 无法解析
- 现象：payload 解析失败/画板为空。
- 处理：校验导出完整性 -> 修复格式 -> 重新导出。

## E2: 资源存在但页面不显示
- 现象：图层有数据但页面缺图。
- 处理：按“数据存在 -> 资源存在 -> 映射逻辑”三步排查。

## E3: 局部文本修复后全页错位
- 现象：修好两处标题，其他文本全乱。
- 处理：回退全局样式改动，改为节点白名单，并做分区回归。

## E4: 被质疑“贴图糊弄”
- 现象：视觉很像但不可交互不可维护。
- 处理：立即撤销整图方案，恢复图层代码渲染并补充可验证说明。

# 交付验收 (Verification)
## P0 必检
- [ ] 已明确本次是新增并行路由还是替换旧页。
- [ ] 已确认验收等级；如未明确降级，按 `1:1 像素级`执行。
- [ ] 已完成阶段一共享层产物，且阶段二已复用。
- [ ] 已执行 data.js 校验与清洗，error 已阻断；Windows 下已加 `PYTHONIOENCODING=utf-8`。
- [ ] 已完成技术栈检测并按检测结果编码。
- [ ] 页面主体未使用 `preview.png` / 整图背景冒充还原。
- [ ] 公共层（至少顶部/背景/侧栏）已按图层坐标渲染，不是结构占位近似样式。
- [ ] 顶部导航热区已公共化（单一组件/共享层），并在所有页面可点击生效。
- [ ] 所有文字/填充色来自 `data.js` 的 `fill.value` 解码（非目测）；viewport/stage 底色与设计稿主题（浅/深）一致。
- [ ] 已实现响应式策略，并完成至少 2 个分辨率可用性验证（含 1920 基准）。
- [ ] 已验证“非全屏宽屏无左右留白”（建议抽查：`1536x864` 或 `1600x900`）。
- [ ] 局部问题采用局部修复，未误改全局策略。
- [ ] 已通过 build/dev 验证，并完成关键区域对齐抽查。
- [ ] 已验证“路由-画面-资源”一致。

## P1 建议
- [ ] 字体映射完成，文本无明显 fallback 偏差。
- [ ] 关键交互无回归（展开/收起、入口点击、分页）。
- [ ] 汇报包含：修复节点、影响范围、回归结果。

# 进阶能力入口
- 快照 diff / 视觉回归 / 复杂组件 / 性能优化等进阶内容见：
  - `{baseDir}/skills/ef-restoring-marklion-pages/references/advanced.md`
- 颜色保真（ARGB 解码、主题取色、调色板沉淀）详见：
  - `{baseDir}/skills/ef-restoring-marklion-pages/references/color-fidelity.md`
- 常见陷阱清单（坐标/切片/路由/验收，每项附实际事故）：
  - `{baseDir}/skills/ef-restoring-marklion-pages/references/common-pitfalls.md`
- 阶段二分区摘要脚本（对 cleaned-data.json 做 top-nav / left / middle / right 分桶，生成易读文本）：
  - `{baseDir}/skills/ef-restoring-marklion-pages/scripts/summarize_cleaned_data.py`
