# 标记狮还原进阶能力（附录）

> 本文档为 `ef-restoring-marklion-pages` 的进阶能力补充。  
> 主流程请以 `SKILL.md` 的两阶段硬门禁为准。

## 1. 视觉回归（推荐在收口末期使用）
- 目标：对比基线图与当前截图，输出偏差热点与量化结果。
- 命令：
```bash
python {baseDir}/skills/ef-restoring-marklion-pages/scripts/visual_regression_report.py --baseline "<基线图>" --current "<当前截图>" --threshold 2 --report-json "<输出>/visual-report.json" --heatmap-out "<输出>/visual-heatmap.png"
```

## 2. 增量还原（设计稿频繁变更时使用）
- 目标：通过快照 diff 只处理新增/修改图层，降低重做成本。
- 命令：
```bash
python {baseDir}/skills/ef-restoring-marklion-pages/scripts/marklion_snapshot_diff.py --data "<data.js绝对路径>" --snapshot-dir "<项目目录>/.marklion-snapshots" --report-json "<输出>/snapshot-diff.json" --write-snapshot
```

## 3. 复杂组件还原（按需启用）
- 适用：表格、分页、图表、弹窗、树形、表单等复杂交互区域。
- 原则：
  - 优先使用项目已安装组件库。
  - 先保证结构与交互正确，再做像素收口。
  - 保持 API 分层（页面不直接写请求细节）。

## 4. 性能优化（交付前按需注入）
- 图片懒加载、WebP/srcset、非首屏延迟渲染、长列表优化。
- 优化必须在“不破坏视觉与交互一致性”前提下启用。

## 5. 进阶模式使用建议
- 当用户目标是“稳定交付 + 高度还原”，优先走主流程，不要默认启用全部进阶能力。
- 仅在用户明确要求或主流程无法满足时，再逐项启用本附录能力。
