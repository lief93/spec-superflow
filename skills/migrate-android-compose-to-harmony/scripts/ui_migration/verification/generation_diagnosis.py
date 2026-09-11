"""Explain existing generation evidence without executing source or guessing visual causes."""
from dataclasses import dataclass
import json
from pathlib import Path


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
    Rule('component_reuse_parameter', ('component reuse parameter ',), 'control',
        '已复用鸿蒙组件，但部分参数被省略或使用占位值。',
        '核对目标默认值；需要保留源参数语义时配置显式组件 adapter。空回调不代表业务行为已迁移。',
        'frontend/component_arguments.py', True),
    Rule('state_preview_default', ('preview default branch selected',), 'content',
        '条件尚未解析；当前仅展示默认预览分支，其他分支属性已保留，不参与当前布局。',
        '需要真实状态时补充源状态输入并重新生成；预览选择不代表运行时条件或业务逻辑已还原。',
        'frontend/preview.py; frontend/fixed_state.py', True),
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

STATUSES = {
    'pending': '当前 UI 待处理',
    'defaulted': '默认值降级，仍需核对还原',
    'deferred_dynamic': '动态/业务条件暂缓',
    'other_state': '其他组件状态待处理',
    'resolved_reference': '目标引用已消费，不计入未解决',
}


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
    from ui_migration.contracts.source_storage import unpack_source_page
    from ui_migration.contracts.lanhu_storage import unpack_lanhu_document
    source_page = unpack_source_page(source_page)
    version_page = unpack_lanhu_document(version_page or {})
    nodes = {n['id']:n for n in source_page.get('components', [])}
    pending = [(version_page or {}).get('artboard', {})]
    while pending:
        layer = pending.pop()
        migration = layer.get('migration', {})
        if layer.get('id') and migration.get('source'):
            nodes[layer['id']] = {'type':migration.get('componentType'), 'source':migration['source']}
        pending.extend(layer.get('layers', []))
    issues = {}
    consumed = {(c.get('component_id'), c.get('path')) for c in
        manifest.get('target_phase_consumption_gate', {}).get('checks', []) if c.get('status') == 'consumed'}
    target_errors = {(u.get('page_component_id') or u.get('component_id'), u.get('path'))
                     for u in manifest.get('unresolved', [])}
    defaults = {(w.get('component_id'), w.get('path')): w for w in manifest.get('warnings', [])
                if w.get('kind') == 'style_default_applied'}

    def disposition(path, reason, occurrence):
        if occurrence and occurrence.get('component_ui_state'):
            return 'other_state'
        if path.startswith('source.component_reuse.parameters.') and reason.startswith('component reuse parameter '):
            return 'defaulted'
        identity = ((occurrence or {}).get('component_id'), path)
        if identity not in target_errors:
            if identity in defaults:
                return 'defaulted'
            if identity in consumed and path.startswith('style.'):
                from ui_migration.contracts.style_tokens import has_token_reference
                try:
                    if has_token_reference(nodes.get(identity[0], {}), path):
                        return 'resolved_reference'
                except ValueError:
                    pass
        if path == 'source.state_resolution' or classify(reason, path).code == 'state_not_selected':
            return 'deferred_dynamic'
        return 'pending'

    def add(path, expression, reason, occurrence, bindings, evidence, execution=False):
        path, expression, reason = path or '', expression or '', reason or ''
        status = disposition(path, reason, occurrence)
        state = (occurrence or {}).get('component_ui_state')
        if occurrence is not None:
            source = occurrence.get('source') or {}
            occurrence = {key:occurrence.get(key) for key in ('component_id', 'component_type')}
            occurrence.update(path=path, reason=reason,
                source={key:source[key] for key in ('source', 'line', 'composable', 'call_id') if key in source})
            if state:
                occurrence['component_ui_state'] = state
            if status == 'defaulted':
                warning = defaults.get((occurrence['component_id'], path))
                if warning:
                    occurrence['fallback'] = warning.get('fallback')
        rule = classify(reason, path)
        if execution and rule.code == 'unclassified':
            rule = Rule('execution_failed', (), 'execution', '命令在当前阶段停止，未完成后续生成。',
                '处理下方原始错误后使用新的运行目录重试；不要复用上次生成文件冒充本次结果。', failure['stage'])
        key = (status, state, rule.code, expression, reason, json.dumps(bindings, sort_keys=True, ensure_ascii=False))
        issue = issues.setdefault(key, {'code':rule.code, 'summary':rule.summary, 'impact':rule.impact,
            'status':status,
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
            and any(o.get('component_id') == component_id and not o.get('component_ui_state')
                    for o in issue['occurrences'])]
        if len(matches) == 1:
            matches[0]['evidence'] = sorted(set(matches[0]['evidence']) | {'arkui_manifest'})
            continue
        node = nodes.get(component_id, {})
        occurrence = {'component_id':component_id, 'component_type':node.get('type'),
            'source':node.get('source', {}), 'reason':reason}
        add(path, expression, reason, occurrence, {}, 'arkui_manifest')
    for (component_id, path), warning in defaults.items():
        matches = [issue for issue in issues.values() if any(
            o.get('component_id') == component_id and o.get('path') == path and not o.get('component_ui_state')
            for o in issue['occurrences'])]
        if matches:
            for issue in matches:
                issue['evidence'] = sorted(set(issue['evidence']) | {'arkui_default_warning'})
            continue
        node = nodes.get(component_id, {})
        add(path, warning.get('expression'), warning.get('reason'),
            {'component_id':component_id, 'component_type':node.get('type'), 'source':node.get('source', {})},
            {}, 'arkui_default_warning')
    if failure:
        add('', '', failure['error'], None, {}, 'command_error', execution=True)
    priority = {'execution':0, 'content':1, 'layout':2, 'control':3, 'style':4, 'unknown':5}
    ordered = sorted(issues.values(), key=lambda issue:(list(STATUSES).index(issue['status']), priority[issue['impact']]))
    counts = {status:sum(issue['status'] == status for issue in ordered) for status in STATUSES}
    outstanding = len(ordered) - counts['resolved_reference']
    return {'schema':'android-to-harmony.generation-diagnosis.v1', 'issue_count':len(ordered),
        'unresolved_count':outstanding, 'counts':counts,
        'target_evidence_available':bool(manifest),
        'summary':f'尚有 {outstanding} 组未解决事项（含降级、暂缓和其他状态），目标引用已消费 {counts["resolved_reference"]} 组。',
        'scope':'generation-evidence', 'visual_cause_verified':False,
        'priority_note':'按内容、布局、控件、样式排序，不代表已证明整页空白由第一项引起。',
        'issues':ordered}


def render_markdown(diagnosis):
    lines = ['# 页面未解决事项', '', diagnosis['summary'], '',
        '这是本次运行的统一清单；按诊断组计数，不是原始日志条数，也不等于已证实的独立根因数。',
        '默认值降级仍可能影响还原度；暂缓不代表已实现。零未解决项也不代表视觉验收通过。', '',
        '| 分类 | 数量 |', '| --- | ---: |']
    lines.extend(f'| {label} | {diagnosis["counts"][status]} |' for status, label in STATUSES.items())
    lines.extend(['', diagnosis['priority_note'], ''])
    if not diagnosis['target_evidence_available']:
        lines.extend(['尚无最终 ArkUI manifest，当前计数仅基于已收集证据，不能确认目标端已解决。', ''])
    for error in diagnosis.get('collection_errors', []):
        lines.extend([f"证据读取失败：`{error['path']}`：{error['error']}", ''])
    if diagnosis.get('visual_triage'):
        from ui_migration.verification.visual_triage import render_triage
        lines.extend([render_triage(diagnosis['visual_triage']), '', '## 生成问题明细', ''])
    for index, issue in enumerate(diagnosis['issues'], 1):
        lines.extend([f"## {index}. {issue['summary']}", '',
            f"状态：**{STATUSES[issue['status']]}**",
            '根因：' + ('已确认。' if issue['root_cause_confirmed'] else '尚未确定完整上游根因；以下是已定位的失败环节。'),
            f"处理：{issue['action']}", f"对应模块：`{issue['owner']}`",
            f"属性：`{', '.join(issue['paths'])}`", '', '表达式与参数：', '```json',
            json.dumps({'expression':issue['expression'], 'bindings':issue['bindings']}, ensure_ascii=False, indent=2),
            '```', '', '影响位置：'])
        if issue['status'] == 'deferred_dynamic':
            lines.append('暂缓动态/业务实现；该条件未选定的分支可能造成当前页面内容缺失。'
                         '若需还原此状态，应提供真实状态输入或实现等价条件选择，不能改成恒真。')
        for occurrence in issue['occurrences']:
            source = occurrence.get('source') or {}
            lines.append(f"- `{occurrence.get('component_id')}` {occurrence.get('component_type') or ''} "
                f"`{source.get('source', '未绑定源码')}:{source.get('line', '?')}` {source.get('composable', '')} "
                f"属性 `{occurrence.get('path', '')}`")
            if occurrence.get('component_ui_state'):
                lines.append(f"  组件状态：`{occurrence['component_ui_state']}`")
            if 'fallback' in occurrence:
                lines.append('  当前默认值：`' + json.dumps(occurrence['fallback'], ensure_ascii=False) + '`')
        lines.extend(['', '原始原因：', '```text', '\n'.join(issue['reasons']), '```', ''])
    return '\n'.join(lines)+'\n'


def diagnose_run(directory, report, comparison=None):
    """Use the same current-run evidence for command completion and later visual triage."""
    evidence, errors = {}, []
    paths = {}
    if directory is not None:
        directory = Path(directory)
        paths = {'source_page': directory/'source-page.json',
                 'version_page': directory/'lanhu/version_json.json',
                 'worklist': directory/'lanhu/unresolved-worklist.json'}
        if report.get('arkui'):
            paths['manifest'] = Path(report['arkui']['manifest'])
        for name, path in paths.items():
            if path.is_file():
                try:
                    value = json.loads(path.read_text(encoding='utf-8'))
                    if not isinstance(value, dict):
                        raise ValueError('Expected a JSON object')
                    evidence[name] = value
                except (ValueError, OSError) as error:
                    errors.append({'path': str(path), 'error': str(error)})
            elif name == 'manifest':
                errors.append({'path': str(path), 'error': 'Recorded ArkUI manifest is missing'})
    failure = ({'stage': report['failed_stage'], 'error': report['error']}
               if report.get('status') == 'failed' else None)
    diagnosis = diagnose(**evidence, failure=failure)
    if comparison is not None:
        import hashlib
        from ui_migration.contracts.identity import canonical_sha256
        from ui_migration.verification.visual_triage import correlate
        for name in ('source_page', 'version_page'):
            if name not in evidence:
                raise ValueError('Visual triage requires readable ' + name)
        version_sha = hashlib.sha256(paths['version_page'].read_bytes()).hexdigest()
        expected = evidence.get('worklist', {}).get('version_json_sha256')
        if expected and expected != version_sha:
            raise ValueError('Worklist belongs to a different version_json.json; regenerate paired evidence')
        expected = evidence.get('manifest', {}).get('semantic_input_sha256')
        page_sha = canonical_sha256({'version_json_sha256': version_sha})
        if expected and expected != canonical_sha256({'input_mode': 'page-json-only', 'page_json_sha256': page_sha}):
            raise ValueError('ArkUI manifest belongs to a different version_json.json; use the matching run')
        diagnosis['visual_triage'] = correlate(diagnosis, comparison, evidence['source_page'],
            evidence['version_page'], evidence.get('manifest', {}))
    diagnosis['collection_errors'] = errors
    diagnosis['collection_complete'] = not errors
    return diagnosis
