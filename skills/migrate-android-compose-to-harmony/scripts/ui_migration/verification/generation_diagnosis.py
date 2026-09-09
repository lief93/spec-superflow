"""Explain existing generation evidence without executing source or guessing visual causes."""
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class Rule:
    code: str
    markers: tuple[str, ...]
    impact: str
    summary: str
    action: str
    owner: str
    confirmed: bool = False


RULES = (
    Rule('target_fact_not_consumed', ('page JSON fact was not consumed by the ArkUI emitter',), 'control',
        '属性已进入页面 JSON，但 ArkUI 生成器没有记录对应消费。',
        '检查该组件的渲染分支与属性消费记录，区分组件未输出、属性未映射和消费记录遗漏；不是直接补默认值。',
        'arkui/renderer.py; component_required_facts.py'),
    Rule('label_slot_unmapped', ('a floating label or composable slot is not a placeholder',), 'content',
        '输入框 label 插槽未完成映射；它不能直接当作 placeholder。',
        '补齐 label 插槽的展开和目标输入框标签布局，保留标签与占位文本的区别。',
        'page_native_controls.py; arkui/renderer.py'),
    Rule('font_asset_unverified', ('has no verified registered asset',), 'style',
        '生成器未找到该字体的已验证注册资源。',
        '核对字体来源及目标资源注册；区分系统字体适配和本地字体文件，不能仅把字体名称当作可用资源。',
        'arkui/renderer.py'),
    Rule('psi_dependency_missing', ('Kotlin PSI dependency missing', 'KOTLIN_PSI_CLASSPATH must contain'),
        'execution', 'PSI 解析器依赖未就绪，源码解析无法启动。',
        '根据原始错误补齐指定 JAR，并配置 KOTLIN_PSI_CLASSPATH；这不是页面布局错误。', 'kotlin_psi.py', True),
    Rule('component_expansion_cycle', ('recursive composable cycle',), 'content',
        '组件展开触发循环保护，该调用的内容无法继续展开。',
        '核对该源码调用的声明身份及调用链；区分真实递归与重载/同名解析错误，不删除循环保护。',
        'frontend/inventory.py'),
    Rule('slot_not_resolved', ('custom component slot invocation was not uniquely resolved',), 'content',
        '内容插槽未绑定到唯一实现，插槽内容没有完整展开。',
        '修复该插槽从调用方、转发参数到实际调用点的绑定；保留业务组件层级。',
        'frontend/inventory.py; frontend/callable_expansion.py'),
    Rule('state_not_selected', ('state selection is unresolved', 'state condition is unresolved'), 'content',
        '分支条件未能求值，当前页面状态的这部分内容没有被选定。',
        '先看下方实际参数绑定：输入缺失时补状态值；已有值时修参数转发或表达式支持，不能改成恒真。',
        'frontend/projection.py; semantics/expressions.py'),
    Rule('modifier_mapping_missing', ('modifier has no declared page-layout mapping',), 'layout',
        '当前 modifier 没有形成可消费的布局映射。',
        '核对该 modifier 的参数求值和生成映射；Insets 类还需明确系统栏数据及消费关系，不能直接忽略。',
        'frontend/values.py; component_required_facts.py; arkui/layout.py'),
    Rule('control_argument_unresolved', ('control argument is not a supported constant',), 'control',
        '控件参数未被当前转换/校验路径识别为支持的值。',
        '检查参数求值结果是否进入控件属性；若已有确定值，修复控件校验/消费路径，而非强制改写源码为字面量。',
        'page_native_controls.py; component_required_facts.py'),
    Rule('control_visual_missing', ('visual semantics require control.',), 'control',
        '控件缺少生成所需的视觉属性。',
        '按下方属性路径补齐显式参数、项目主题或框架默认值的解析及消费；不要任意填色或删控件。',
        'frontend/material_defaults.py; page_native_controls.py'),
    Rule('native_argument_unmapped', ('native argument has no complete single-JSON mapping',), 'control',
        '原生控件参数尚无完整的单 JSON 映射。',
        '补齐该参数的 JSON 表达和 ArkUI 消费；如果确属暂不支持的能力，保留诊断及其他已支持内容。',
        'component_required_facts.py; arkui/renderer.py'),
)


def classify(reason, path):
    for rule in RULES:
        if any(marker in reason for marker in rule.markers):
            return rule
    if path.startswith('style.'):
        return Rule('style_fact_unresolved', (), 'style', '样式属性未获得完整可消费的值或引用。',
            '核对显式项目样式文件、Token 映射和主题选择；已进入 JSON 的引用还须确认该属性有消费支持。',
            'frontend/styles.py; frontend/style_tokens.py; arkui/style_tokens.py')
    return Rule('unclassified', (), 'unknown', '已记录失败项，但当前证据尚不能确定其具体根因。',
        '根据下方源码位置、表达式和原始原因确认缺失环节；不要把未知项当作通过。', 'undetermined')


def diagnose(worklist=None, manifest=None, source_page=None, failure=None, version_page=None):
    worklist, manifest, source_page = worklist or {}, manifest or {}, source_page or {}
    nodes = {n['id']:n for n in source_page.get('components', [])}
    pending = [(version_page or {}).get('artboard', {})]
    while pending:
        layer = pending.pop()
        migration = layer.get('migration', {})
        if layer.get('id') and migration.get('source'):
            nodes[layer['id']] = {'type':migration.get('componentType'), 'source':migration['source']}
        pending.extend(layer.get('layers', []))
    issues = {}

    def add(path, expression, reason, occurrence, bindings, evidence, execution=False):
        path, expression, reason = path or '', expression or '', reason or ''
        if occurrence is not None:
            source = occurrence.get('source') or {}
            occurrence = {key:occurrence.get(key) for key in ('component_id', 'component_type')}
            occurrence.update(path=path, reason=reason,
                source={key:source[key] for key in ('source', 'line', 'composable', 'call_id') if key in source})
        rule = classify(reason, path)
        if execution and rule.code == 'unclassified':
            rule = Rule('execution_failed', (), 'execution', '命令在当前阶段停止，未完成后续生成。',
                '处理下方原始错误后使用新的运行目录重试；不要复用上次生成文件冒充本次结果。', failure['stage'])
        key = (rule.code, expression, reason, json.dumps(bindings, sort_keys=True, ensure_ascii=False))
        issue = issues.setdefault(key, {'code':rule.code, 'summary':rule.summary, 'impact':rule.impact,
            'root_cause_confirmed':rule.confirmed, 'action':rule.action, 'owner':rule.owner,
            'expression':expression, 'bindings':bindings, 'paths':[], 'reasons':[reason],
            'occurrences':[], 'evidence':[]})
        if path not in issue['paths']:
            issue['paths'].append(path)
        if occurrence is not None and occurrence not in issue['occurrences']:
            issue['occurrences'].append(occurrence)
        issue['evidence'] = sorted(set(issue['evidence']) | {evidence})

    for task in worklist.get('tasks', []):
        for occurrence in task.get('occurrences', []):
            add(task.get('path', ''), task.get('expression', ''), occurrence.get('reason', ''),
                occurrence, task.get('context', {}).get('bindings', {}), 'unresolved_worklist')
    for item in manifest.get('unresolved', []):
        component_id = item.get('page_component_id') or item.get('component_id')
        path, expression = item.get('path', ''), item.get('expression', '')
        reason = item.get('page_reason') or item.get('reason', '')
        matches = [issue for issue in issues.values() if issue['expression'] == expression
            and reason in issue['reasons'] and path in issue['paths']
            and any(o.get('component_id') == component_id for o in issue['occurrences'])]
        if len(matches) == 1:
            matches[0]['evidence'] = sorted(set(matches[0]['evidence']) | {'arkui_manifest'})
            continue
        node = nodes.get(component_id, {})
        occurrence = {'component_id':component_id, 'component_type':node.get('type'),
            'source':node.get('source', {}), 'reason':reason}
        add(path, expression, reason, occurrence, {}, 'arkui_manifest')
    if failure:
        add('', '', failure['error'], None, {}, 'command_error', execution=True)
    priority = {'execution':0, 'content':1, 'layout':2, 'control':3, 'style':4, 'unknown':5}
    ordered = sorted(issues.values(), key=lambda issue:priority[issue['impact']])
    return {'schema':'android-to-harmony.generation-diagnosis.v1', 'issue_count':len(ordered),
        'summary':f'发现 {len(ordered)} 组生成问题，已合并重复证据。' if ordered else '未收集到具体失败项；这不等于视觉验收通过。',
        'scope':'generation-evidence', 'visual_cause_verified':False,
        'priority_note':'按内容、布局、控件、样式排序，不代表已证明整页空白由第一项引起。',
        'issues':ordered}


def render_markdown(diagnosis):
    lines = ['# 页面生成诊断', '', diagnosis['summary'], '', diagnosis['priority_note'], '']
    for error in diagnosis.get('collection_errors', []):
        lines.extend([f"证据读取失败：`{error['path']}`：{error['error']}", ''])
    for index, issue in enumerate(diagnosis['issues'], 1):
        lines.extend([f"## {index}. {issue['summary']}", '',
            '根因：' + ('已确认。' if issue['root_cause_confirmed'] else '尚未确定完整上游根因；以下是已定位的失败环节。'),
            f"处理：{issue['action']}", f"对应模块：`{issue['owner']}`",
            f"属性：`{', '.join(issue['paths'])}`", '', '表达式与参数：', '```json',
            json.dumps({'expression':issue['expression'], 'bindings':issue['bindings']}, ensure_ascii=False, indent=2),
            '```', '', '影响位置：'])
        for occurrence in issue['occurrences']:
            source = occurrence.get('source') or {}
            lines.append(f"- `{occurrence.get('component_id')}` {occurrence.get('component_type') or ''} "
                f"`{source.get('source', '未绑定源码')}:{source.get('line', '?')}` {source.get('composable', '')} "
                f"属性 `{occurrence.get('path', '')}`")
        lines.extend(['', '原始原因：', '```text', '\n'.join(issue['reasons']), '```', ''])
    return '\n'.join(lines)+'\n'
