#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""检测项目技术栈并输出还原适配建议。

增强能力:
- 检测框架/样式/路由/构建工具
- 检测默认组件（Element UI/Element Plus、ECharts）实际安装情况
- 检测 ESLint/Prettier 配置
- 检测项目目录结构（src/api/、src/assets/、src/views/ 等）
- 输出代码生成适配建议
"""

import argparse
import json
import os
from typing import Any


def read_package_json(project_root: str) -> dict[str, Any]:
    package_json = os.path.join(project_root, "package.json")
    if not os.path.exists(package_json):
        raise FileNotFoundError(f"未找到 package.json: {package_json}")
    with open(package_json, "r", encoding="utf-8") as f:
        return json.load(f)


def merge_deps(pkg: dict[str, Any]) -> dict[str, str]:
    deps = pkg.get("dependencies", {})
    dev_deps = pkg.get("devDependencies", {})
    merged = {}
    merged.update(deps)
    merged.update(dev_deps)
    return merged


def major_version(version_expr: str) -> int | None:
    chars = "".join(ch for ch in version_expr if ch.isdigit() or ch == ".")
    if not chars:
        return None
    first = chars.split(".", maxsplit=1)[0]
    try:
        return int(first)
    except ValueError:
        return None


def detect_framework(deps: dict[str, Any]) -> dict[str, Any]:
    if "vue" in deps:
        major = major_version(deps["vue"])
        if major and major >= 3:
            return {
                "framework": "vue",
                "version_major": major,
                "restore_template": "vue3-composition-script-setup",
            }
        return {
            "framework": "vue",
            "version_major": major or 2,
            "restore_template": "vue2-options-api",
        }
    if "react" in deps:
        major = major_version(deps["react"]) or 18
        return {
            "framework": "react",
            "version_major": major,
            "restore_template": "react-hooks",
        }
    if "@angular/core" in deps:
        major = major_version(deps["@angular/core"]) or 16
        return {
            "framework": "angular",
            "version_major": major,
            "restore_template": "angular-standalone",
        }
    return {
        "framework": "unknown",
        "version_major": None,
        "restore_template": "generic-html-css",
    }


def detect_styles(deps: dict[str, Any]) -> list[str]:
    styles = []
    if "sass" in deps or "node-sass" in deps:
        styles.append("scss")
    if "less" in deps:
        styles.append("less")
    if "stylus" in deps:
        styles.append("stylus")
    if not styles:
        styles.append("css")
    return styles


def detect_router(deps: dict[str, Any], framework: str) -> str:
    if framework == "vue":
        if "vue-router" in deps:
            major = major_version(deps["vue-router"])
            return f"vue-router@{major}" if major else "vue-router"
        return "manual-router-binding"
    if framework == "react":
        if "react-router-dom" in deps:
            major = major_version(deps["react-router-dom"])
            return f"react-router-dom@{major}" if major else "react-router-dom"
        return "manual-router-binding"
    if framework == "angular":
        return "angular-router"
    return "unknown"


def detect_build_tool(deps: dict[str, Any], scripts: dict[str, str]) -> str:
    script_blob = " ".join(scripts.values())
    if "vite" in deps or "vite" in script_blob:
        return "vite"
    if "@vue/cli-service" in deps:
        return "vue-cli"
    if "react-scripts" in deps:
        return "create-react-app"
    if "webpack" in deps or "webpack" in script_blob:
        return "webpack"
    return "unknown"


def detect_default_components(deps: dict[str, Any]) -> dict[str, str]:
    table_lib = "none"
    chart_lib = "none"

    if "element-plus" in deps:
        table_lib = "element-plus"
    elif "element-ui" in deps:
        table_lib = "element-ui"
    elif "ant-design-vue" in deps:
        table_lib = "ant-design-vue"
    elif "antd" in deps:
        table_lib = "antd"
    elif "@arco-design/web-vue" in deps:
        table_lib = "arco-design"
    elif "naive-ui" in deps:
        table_lib = "naive-ui"

    if "echarts" in deps:
        chart_lib = "echarts"
    elif "highcharts" in deps:
        chart_lib = "highcharts"
    elif "chart.js" in deps:
        chart_lib = "chart.js"
    elif "d3" in deps or "d3-selection" in deps:
        chart_lib = "d3"
    elif "@antv/g2" in deps:
        chart_lib = "antv-g2"
    elif "antv/g6" in deps:
        chart_lib = "antv-g6"

    return {"table": table_lib, "chart": chart_lib}


def detect_lint_config(project_root: str) -> dict[str, Any]:
    lint_files = [
        ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.cjs", ".eslintrc.yaml",
        "eslint.config.js", "eslint.config.mjs",
    ]
    prettier_files = [
        ".prettierrc", ".prettierrc.js", ".prettierrc.json", ".prettierrc.yaml",
        ".prettierrc.cjs", "prettier.config.js",
    ]
    editor_config = os.path.join(project_root, ".editorconfig")

    eslint_found = None
    for name in lint_files:
        if os.path.exists(os.path.join(project_root, name)):
            eslint_found = name
            break

    prettier_found = None
    for name in prettier_files:
        if os.path.exists(os.path.join(project_root, name)):
            prettier_found = name
            break

    return {
        "eslint": eslint_found,
        "prettier": prettier_found,
        "editorconfig": os.path.exists(editor_config),
    }


def detect_project_structure(project_root: str) -> dict[str, Any]:
    src = os.path.join(project_root, "src")
    structure = {
        "src_exists": os.path.isdir(src),
        "views_dir": None,
        "api_dir": None,
        "assets_dir": None,
        "components_dir": None,
        "router_file": None,
        "store_file": None,
        "shared_marklion_dir": None,
    }

    if not structure["src_exists"]:
        return structure

    for views_name in ("views", "pages", "screen"):
        p = os.path.join(src, views_name)
        if os.path.isdir(p):
            structure["views_dir"] = p
            break

    for api_name in ("api", "apis", "services"):
        p = os.path.join(src, api_name)
        if os.path.isdir(p):
            structure["api_dir"] = p
            break

    for assets_name in ("assets", "static", "public"):
        p = os.path.join(src, assets_name)
        if os.path.isdir(p):
            structure["assets_dir"] = p
            break

    for comp_name in ("components", "comp"):
        p = os.path.join(src, comp_name)
        if os.path.isdir(p):
            structure["components_dir"] = p
            break

    for router_name in ("router.js", "router/index.js", "router.ts", "router/index.ts"):
        p = os.path.join(src, router_name)
        if os.path.exists(p):
            structure["router_file"] = p
            break

    for store_name in ("store.js", "store/index.js", "store.ts", "store/index.ts", "vuex/index.js"):
        p = os.path.join(src, store_name)
        if os.path.exists(p):
            structure["store_file"] = p
            break

    shared_dirs = [
        os.path.join(src, "views", "marklion-shared"),
        os.path.join(src, "views", "shared"),
        os.path.join(src, "components", "marklion-shared"),
    ]
    for sd in shared_dirs:
        if os.path.exists(sd):
            structure["shared_marklion_dir"] = sd
            break

    return structure


def generate_code_suggestions(report: dict[str, Any]) -> list[str]:
    suggestions = []
    framework = report["framework"]["framework"]
    major = report["framework"]["version_major"]
    components = report["component_defaults"]
    lint = report["lint_config"]
    structure = report["project_structure"]

    if framework == "vue" and major == 2:
        suggestions.append("使用 Options API（data/methods/computed/watch）编写页面组件。")
        suggestions.append("使用 <style scoped lang=\"scss\"> 隔离样式（项目已安装 sass）。")
    elif framework == "vue" and major >= 3:
        suggestions.append("使用 Composition API + <script setup> 编写页面组件。")
    elif framework == "react":
        suggestions.append("使用函数组件 + Hooks 编写页面。")

    if components["table"] == "element-ui":
        suggestions.append("表格默认使用 Element UI（el-table + el-pagination），保持与项目现有组件一致。")
    elif components["table"] == "element-plus":
        suggestions.append("表格默认使用 Element Plus（el-table + el-pagination）。")
    elif components["table"] == "none":
        suggestions.append("未检测到现有表格组件库，将按 SKILL 默认策略选择（Element UI）。")

    if components["chart"] == "echarts":
        suggestions.append("统计图默认使用 ECharts，保持与项目现有图表库一致。")
    elif components["chart"] == "none":
        suggestions.append("未检测到现有图表库，将按 SKILL 默认策略选择（ECharts）。")

    if lint["eslint"]:
        suggestions.append(f"检测到 ESLint 配置（{lint['eslint']}），生成代码后需执行 lint 校验。")
    if lint["prettier"]:
        suggestions.append(f"检测到 Prettier 配置（{lint['prettier']}），生成代码后需执行格式化。")

    if structure["views_dir"]:
        suggestions.append(f"页面目录应放在 {structure['views_dir']} 下，使用业务语义命名。")
    if structure["api_dir"]:
        suggestions.append(f"API 文件应放在 {structure['api_dir']} 下，与页面模块同名。")
    if structure["shared_marklion_dir"]:
        suggestions.append(f"检测到已有共享层目录 {structure['shared_marklion_dir']}，新页面应优先复用。")

    return suggestions


def main() -> int:
    parser = argparse.ArgumentParser(description="检测项目技术栈并输出适配建议")
    parser.add_argument("--project-root", default=".", help="项目根目录")
    parser.add_argument("--out-json", help="检测结果输出路径（JSON）")
    parser.add_argument("--verbose", action="store_true", help="输出详细建议")
    args = parser.parse_args()

    project_root = os.path.abspath(args.project_root)
    try:
        pkg = read_package_json(project_root)
    except Exception as exc:
        print(f"检测失败：{exc}")
        return 1

    deps = merge_deps(pkg)
    framework_info = detect_framework(deps)
    framework = framework_info["framework"]
    report = {
        "project_root": project_root,
        "framework": framework_info,
        "style_candidates": detect_styles(deps),
        "router": detect_router(deps, framework),
        "build_tool": detect_build_tool(deps, pkg.get("scripts", {})),
        "component_defaults": detect_default_components(deps),
        "lint_config": detect_lint_config(project_root),
        "project_structure": detect_project_structure(project_root),
        "code_suggestions": [],
    }

    report["code_suggestions"] = generate_code_suggestions(report)

    print("技术栈检测结果：")
    print(f"- framework: {report['framework']['framework']} v{report['framework']['version_major']} "
          f"({report['framework']['restore_template']})")
    print(f"- router: {report['router']}")
    print(f"- styles: {', '.join(report['style_candidates'])}")
    print(f"- build_tool: {report['build_tool']}")
    print(f"- table component: {report['component_defaults']['table']}")
    print(f"- chart component: {report['component_defaults']['chart']}")

    lint = report["lint_config"]
    if lint["eslint"]:
        print(f"- eslint: {lint['eslint']}")
    if lint["prettier"]:
        print(f"- prettier: {lint['prettier']}")

    structure = report["project_structure"]
    if structure["views_dir"]:
        print(f"- views dir: {structure['views_dir']}")
    if structure["api_dir"]:
        print(f"- api dir: {structure['api_dir']}")
    if structure["shared_marklion_dir"]:
        print(f"- shared marklion dir: {structure['shared_marklion_dir']}")

    if args.verbose:
        print("\n代码生成建议：")
        for idx, suggestion in enumerate(report["code_suggestions"], 1):
            print(f"  {idx}. {suggestion}")

    if args.out_json:
        out_path = os.path.abspath(args.out_json)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n已输出检测报告：{out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
