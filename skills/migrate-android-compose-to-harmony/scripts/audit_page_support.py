#!/usr/bin/env python3
"""Render the code-owned control/property inventory as human-readable tables."""
from __future__ import annotations

import argparse
import ast
import csv
from functools import lru_cache
from pathlib import Path

from page_component_catalog import CONTROL_FAMILIES, FIELD_AUDIT, FAMILY_BOUNDARIES
from page_snapshot import STYLE_SECTIONS
from generate_arkui_page import target_fact_phase


@lru_cache(maxsize=None)
def function_lines(filename: str) -> dict[str, int]:
    script = Path(__file__).resolve().parent / filename
    tree = ast.parse(script.read_text(encoding='utf-8'))
    return {node.name: node.lineno for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def code_link(filename: str, function: str) -> str:
    line = function_lines(filename).get(function)
    if line is None:
        raise ValueError(f'Missing implementation function: {filename}:{function}')
    return f'[{function}](../scripts/{filename}#L{line})'


def build_report() -> tuple[str, list[list[str]]]:
    expected = {f'{section}.{field}' for section, fields in STYLE_SECTIONS.items() for field in fields}
    if set(FIELD_AUDIT) != expected:
        raise ValueError(f'Unreviewed schema drift: {set(FIELD_AUDIT) ^ expected}')
    internal_count = len(CONTROL_FAMILIES['internal'])
    native_count = sum(len(names) for family, names in CONTROL_FAMILIES.items() if family != 'internal')
    lines = ['# 单输入页面生成器：控件与属性核对表', '',
        f'统计口径：当前入口接纳 **{native_count} 个 Android 控件类型名称 + {internal_count} 个内部类型**，不是 {native_count + internal_count} 个完整框架组件。',
        f'每个节点有 **{len(expected)} 个样式字段槽位 + 4 个结构字段**。槽位允许 null；不代表每个控件适用全部字段，',
        '也不代表 Android SDK 的全部参数、重载、默认主题、修饰符顺序都已经支持。',
        '下表的属性数量按适用顶层字段计算，含条件/证据/未支持项；圆角四角等嵌套字段不重复计数。',
        '项目业务组件保持展开后的独立组件树，不作为固定原生控件种类计数。', '',
        '## 每个控件', '',
        '| 控件 | 适用属性数（含4结构字段） | 已实现 | 条件 | 近似 | 元数据 | 业务边界 | 未支持 | 范围 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    csv_rows = [['control', 'field', 'applicable', 'status', 'source_boundary', 'target_consumer']]
    for family, names in CONTROL_FAMILIES.items():
        applicable = {path: row for path, row in FIELD_AUDIT.items()
                      if row[0] == 'all' or family in row[0].split()}
        counts = {status: sum(row[1] == status for row in applicable.values())
                  for status in ('已实现', '条件', '近似', '证据', '业务边界', '未支持')}
        for name in names:
            lines.append(f'| `{name}` | {len(applicable) + 4} | {counts["已实现"] + 4} | '
                f'{counts["条件"]} | {counts["近似"]} | {counts["证据"]} | {counts["业务边界"]} | '
                f'{counts["未支持"]} | {FAMILY_BOUNDARIES[family]} |')
            for path in ('type', 'parent_id', 'children_ids', 'sibling_index'):
                csv_rows.append([name, 'structure.' + path, 'yes', '已实现', 'SourceTree/lanhu_layer', 'page_snapshot_component_lines'])
            for path, row in FIELD_AUDIT.items():
                applies = path in applicable
                csv_rows.append([name, 'style.' + path, 'yes' if applies else 'no',
                                 row[1] if applies else '不适用', row[2], row[3]])
    lines.extend(['', '## 逐属性核对', '',
        '生成路径：`static_style_for_call` 提取源码，`project_source_page` 解析页面状态，',
        '`lanhu_layer` 保留完整 `migration.style`；不能仅凭原始蓝湖字段中有 frame 就推定全部样式已经消费。',
        '“已实现”限表中明确的值域；“条件”要满足源端与目标端边界；“未支持”非默认值必须失败。',
        '业务点击不属于仅 UI 渲染保证，已明确单列，不能用此表替代 behavior contract。', '',
        '| 字段 | 适用类别 | 首要阶段 | 状态 | 源码生成/支持边界 | 目标消费逻辑 |',
        '| --- | --- | --- | --- | --- | --- |'])
    for path, (families, status, source, target) in FIELD_AUDIT.items():
        links = ' / '.join(code_link('generate_arkui_page.py', fn) for fn in target.split(' / '))
        lines.append(f'| `{path}` | {families} | {target_fact_phase("style." + path)} | {status} | {source} | {links} |')
    lines.extend(['', '## 结构与布局操作', '',
        '| 项目 | 生成逻辑 | 消费逻辑 | 边界 |', '| --- | --- | --- | --- |',
        '| type/parent/children/sibling | SourceTree + lanhu_layer | page_snapshot_component_lines | 对应同一实例；不靠全屏坐标重建父子 |',
        '| fillMaxWidth/Height/Size、matchParentSize、wrapContentWidth/Height/Size | normalized_layout_rules | page_snapshot_dimension_lines | 常量比例；不支持的组合失败 |',
        '| width/height IntrinsicSize | normalized_layout_rules | page_snapshot_dimension_lines | 保留原生内容测量；不估算文字宽度 |',
        '| widthIn/heightIn/sizeIn | normalized_layout_rules | constraintSize | 四个边界逐值使用目标密度取整 |',
        '| weight | normalized_layout_rules | page_snapshot_source_layout_weight | 仅 Row/Column，fill=false 失败 |',
        '| align/constrainAs | normalized_layout_rules + SourceLayout relationships | alignSelf/align/alignRules | 不支持关系失败，不回退绝对布局 |',
        '| offset | normalized_layout_rules | page_snapshot_explicit_offset_line | 常量支持；parent_fraction 当前仍依赖参考父尺寸，不能宣称响应式等价 |',
        '| verticalScroll/horizontalScroll | normalized_layout_rules | Scroll + 原生流式子树 | 不等价于完整 Lazy 虚拟化 |',
        '| zIndex | normalized_layout_rules | zIndex | 数值常量 |',
        '| scale/rotate | static_style_for_call + required facts | scale/rotate | 中心原点常量；graphicsLayer/顺序组合未支持 |',
        '| 重复padding/size与padding顺序 | expand_ordered_layout_modifiers | 原生嵌套 Box + 原组件 | 常量纯布局链；交织绘制/重复同轴尺寸仍 unresolved |', '',
        '## 已补的缺口与未完成边界', '',
        '- 已补：fontStyle、letterSpacing 入口采集、输入 value/placeholder、enabled/visible、contentDescription、scale/rotate/translation、tint。',
        '- 已修：蓝湖 paint.isEnabled 覆盖 Android enabled、TextInput overflow 签名、空 Row/Column 类型、约束像素取整。',
        '- 已阻断：多阴影/非零spread、自定义dash/单边border、选中/checked真值、已识别但无映射的原生参数。',
        '- 本轮补齐：输入单/多行、只读、密码与键盘动作；水平/垂直 Clamp 渐变；绝对四角圆角；纯布局修饰符嵌套。',
        '- 仍有限制：非轴向/径向渐变、复杂输入框装饰、框架默认样式、动态/多重变换、资源像素到逻辑尺寸、locale。',
        '- 阴影近似、文字行高/字体边界仍需真机像素校验，不能因有 emitter 宣称等价。', '',
        '## 代码与验证入口', '',
        '- ' + code_link('real_page_pipeline.py', 'static_style_for_call'),
        '- ' + code_link('generate_lanhu_source_page.py', 'project_source_page'),
        '- ' + code_link('generate_lanhu_source_page.py', 'lanhu_layer'),
        '- ' + code_link('component_required_facts.py', 'build_required_facts'),
        '- ' + code_link('generate_arkui_page.py', 'build_target_phase_consumption_gate'),
        '- `test_page_property_coverage.py`：源值→JSON→生成代码、负路径、25类共享属性、目录与schema闭合。',
        '- `test_layout_mapping_contract.py`：布局/字体/资源/measure与layout关系专项。',
        '- `test_page_input_surface.py` / `test_ordered_layout_wrappers.py`：新增端到端属性、负路径、布局顺序。',
        '- `test_common_page_controls.py`：Kotlin 参数库存、选择状态、离散范围、进度、分隔线、文字、父约束和失败路径。',
        '- 本表不是截图通过证明，必须另外运行同尺寸页面比较。', '',
        '重建表格：`python3 -B scripts/audit_page_support.py --output references/page-support-inventory.md`',
        f'伴随的 CSV 按每个控件×{len(expected) + 4}字段展开，包含不适用项，不把未支持项算作已实现。', ''])
    return '\n'.join(lines), csv_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report, rows = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding='utf-8')
    with args.output.with_suffix('.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        csv.writer(stream).writerows(rows)
    internal = len(CONTROL_FAMILIES['internal'])
    native = sum(len(names) for family, names in CONTROL_FAMILIES.items() if family != 'internal')
    print(f'{native} Android types, {internal} internal types, {len(FIELD_AUDIT)} style fields, 4 structure fields; {len(rows)-1} rows')


if __name__ == '__main__':
    main()
