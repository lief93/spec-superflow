"""Join measured differences to generation evidence; never infer causes from pixels."""
from ui_migration.contracts.source_storage import unpack_source_page
from ui_migration.contracts.lanhu_storage import unpack_lanhu_document


def _index(nodes):
    result = {}
    for node in nodes:
        key = node.get('semantic_key')
        if key:
            result.setdefault(key, []).append(node)
    return result


def _value(node, path):
    value = node
    for part in path.split('.'):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _covers(owner, path):
    return owner == path or (owner.startswith('style.') and owner.count('.') >= 2 and path.startswith(owner + '.'))


def correlate(diagnosis, comparison, source_page, version_page, manifest):
    if comparison.get('schema') != 'android-to-harmony.local-image-comparison.v1':
        raise ValueError('Expected compare_local_screenshots.py comparison.json')
    source_page = unpack_source_page(source_page)
    version_page = unpack_lanhu_document(version_page)
    expected = version_page.get('meta', {}).get('migration', {}).get('page')
    records = {r.get('side'): r for r in comparison.get('component_inventories', [])}
    source_identity = {k: source_page.get('page', {}).get(k) for k in ('id', 'state')}
    page_matches = bool(expected) and source_identity == expected and all(
        records.get(side, {}).get('page') == expected and
        records.get(side, {}).get('schema') == 'android-to-harmony.page-snapshot.v2'
        for side in ('left', 'right'))
    viewport_matches = comparison.get('viewport_compatibility', {}).get('pixel_comparison_compatible') is True
    findings = []
    result = {'comparable': page_matches and viewport_matches, 'findings': findings,
        'limitations': ['仅核对已记录的页面/状态及视口；主题、语言、动态数据和实际安装版本仍需核实。',
            '关联表示同一组件/属性的证据相关，不代表根因已证明；不解析或修改生成的 ETS。',
            '最后匹配/首次不同仅指已记录的属性值；产物中存在组件不等于该阶段完全正确。'],
        'ordering': 'P0 对比前提；P1 缺失/层级/布局；P2 资源/文字/样式；P3 证据不足。同级按实测影响排序。'}
    if not result['comparable']:
        findings.append({'kind': 'comparison_prerequisite', 'priority': 'P0',
            'summary': '页面/状态或视口证据不一致，先修正采集对，再定位 UI 原因。',
            'evidence': {'page_matches': page_matches, 'viewport_matches': viewport_matches},
            'related_issue_indexes': [], 'root_cause_confirmed': False,
            'owners': ['runtime capture / comparison inputs'],
            'verification': '重新采集同页同状态的两端截图与 page.json，重跑比较。'})
        result['finding_count'] = 1
        return result
    source_index = _index(source_page.get('components', []))
    nodes = []
    pending = [version_page.get('artboard', {})]
    while pending:
        layer = pending.pop()
        migration = layer.get('migration') or {}
        if migration:
            nodes.append({'id': layer.get('id'), 'semantic_key': migration.get('semanticKey'),
                          'source': migration.get('source', {}), 'style': migration.get('style', {})})
        pending.extend(layer.get('layers', []))
    version_index = _index(nodes)
    analysis = comparison.get('difference_analysis', {})
    rankings = {r['semantic_key']: r for r in analysis.get('business_component_ssim_rankings', [])}
    consumption = {(c.get('component_id'), c.get('path')): c.get('status')
                   for c in manifest.get('target_phase_consumption_gate', {}).get('checks', [])}
    issues_by_component = {}
    for index, issue in enumerate(diagnosis.get('issues', []), 1):
        for occurrence in issue['occurrences']:
            if not occurrence.get('component_ui_state'):
                issues_by_component.setdefault(occurrence.get('component_id'), []).append((index, occurrence))

    def add(kind, key, path, evidence, priority, summary):
        source_matches, version_matches = source_index.get(key, []), version_index.get(key, [])
        ambiguous = len(source_matches) > 1 or len(version_matches) > 1
        source = source_matches[0] if len(source_matches) == 1 and not ambiguous else {}
        version = version_matches[0] if len(version_matches) == 1 and not ambiguous else {}
        ids = {n['id'] for n in (source, version) if n.get('id')}
        related, contextual = set(), set()
        for component_id in ids:
            for index, occurrence in issues_by_component.get(component_id, []):
                if not path or _covers(occurrence.get('path', ''), path):
                    related.add(index)
                else:
                    contextual.add(index)
        related, contextual = sorted(related), sorted(contextual - related)
        trace = {'last_matching_artifact': None, 'first_differing_artifact': None,
            'source_present': bool(source), 'version_present': bool(version),
            'target_consumption': consumption.get((version.get('id'), path)),
            'source_value': _value(source, path) if path else None,
            'version_value': _value(version, path) if path else None}
        if trace['target_consumption'] is None and path:
            parents = [(p, status) for (component_id, p), status in consumption.items()
                       if component_id == version.get('id') and _covers(p, path)]
            if parents:
                parent, status = max(parents, key=lambda item: len(item[0]))
                trace.update(target_consumption=status, target_consumption_path=parent)
        # Literal equality is evidence at this property, not evaluation of a target call.
        expected_value = evidence.get('left')
        if kind == 'style' and expected_value is not None and not isinstance(expected_value, (dict, list)):
            for artifact, value in [('source-page.json', trace['source_value']),
                                    ('version_json.json', trace['version_value'])]:
                if value is not None and not isinstance(value, (dict, list)):
                    if value == expected_value and trace['first_differing_artifact'] is None:
                        trace['last_matching_artifact'] = artifact
                    elif value != expected_value and trace['first_differing_artifact'] is None:
                        trace['first_differing_artifact'] = artifact
            if not trace['first_differing_artifact']:
                trace['first_differing_artifact'] = 'harmony runtime'
        owners = sorted({diagnosis['issues'][i-1]['owner'] for i in related})
        if not owners:
            owners = (['frontend/projection.py; frontend/style_tokens.py']
                      if trace['first_differing_artifact'] == 'version_json.json' else
                      ['arkui/renderer.py; native layout/resources; project adapter'])
        score = rankings.get(key, {}).get('impact_score') or 0
        findings.append({'kind': kind, 'semantic_key': key, 'path': path, 'priority': priority,
            'summary': summary, 'source_binding': 'ambiguous' if ambiguous else 'unique' if ids else 'unmapped',
            'source_component_ids': sorted(ids), 'source': source.get('source') or version.get('source', {}),
            'trace': trace, 'evidence': evidence, 'related_issue_indexes': related,
            'component_context_issue_indexes': contextual, 'owners': owners,
            'root_cause_confirmed': False, 'impact_score': score,
            'verification': '在首个有证据的差异阶段补回归，重新生成并采集同状态，对比本组件该项差值；不改最终 ETS。'})

    presence = analysis.get('component_presence', {})
    for field, summary in [('missing_in_right', '鸿蒙侧未匹配到组件，核对缺失或运行时映射缺口。'),
                           ('missing_in_left', '仅鸿蒙侧匹配到组件，核对额外内容或 Android 映射缺口。')]:
        for key in presence.get(field, []):
            add('missing_component', key, '', {'presence': field}, 'P1', summary)
    for field in ('ambiguous_in_left', 'ambiguous_in_right'):
        for key in presence.get(field, []):
            add('mapping', key, '', {'presence': field}, 'P3', '运行时组件身份重复，不能据此确认具体实例。')
    for item in analysis.get('component_hierarchy_deltas', []):
        if item.get('status') == 'fail':
            add('hierarchy', item['semantic_key'], 'structure.parent_id', item, 'P1', '父子层级或兄弟顺序不同。')
    for item in analysis.get('component_geometry_deltas', []):
        if item.get('over_1dp'):
            add('geometry', item['semantic_key'], '', item, 'P1', '实测位置或尺寸差异超过 1dp。')
    for item in analysis.get('component_style_deltas', []):
        for prop in item.get('comparisons', []):
            if prop.get('over_tolerance'):
                add('style', item['semantic_key'], prop['path'], prop, 'P2', '实测属性值超出比较容差。')
        for side in ('left', 'right'):
            for path in item.get(side + '_only_proven_paths', []):
                add('style_evidence', item['semantic_key'], path, {'only_proven_in': side}, 'P3',
                    '仅一侧有已验证属性值，尚不能证明另一侧样式错误。')
            for error in item.get(side + '_unresolved', []):
                add('runtime_evidence', item['semantic_key'], error.get('path', ''),
                    {'side': side, 'diagnostic': error}, 'P3', '运行时属性证据未解析，需要补采集或绑定。')
    for key, item in rankings.items():
        score = item.get('aligned_appearance_ssim_score')
        if score is not None and score < comparison.get('verdict', {}).get('minimum_ssim', 0.95):
            add('appearance', key, '', {'aligned_appearance_ssim_score': score,
                'bounds_comparability': item.get('bounds_comparability')}, 'P2',
                '组件内部像素外观存在差异；该分数不能直接证明颜色、字体或资源根因。')
    if not findings and comparison.get('verdict', {}).get('status') == 'fail':
        add('unlocalized', '', '', {'failure_reasons': comparison['verdict'].get('failure_reasons', [])},
            'P3', '比较未通过，但当前证据无法定位到唯一组件；先补运行时映射或采集证据。')
    findings.sort(key=lambda item: (item['priority'], -item.get('impact_score', 0), item.get('semantic_key', ''), item.get('path', '')))
    result['finding_count'] = len(findings)
    return result


def render_triage(triage):
    import json
    lines = ['## 实测异常与生成诊断关联', '',
        f"实测/采集异常 {triage['finding_count']} 项。与生成问题有关联，数量不能直接相加。", triage['ordering'], '']
    for index, finding in enumerate(triage['findings'], 1):
        lines.extend([f"### {finding['priority']} / {index}. {finding['summary']}",
            f"组件：`{finding.get('semantic_key', '')}` 属性：`{finding.get('path', '')}`",
            '关联生成问题编号：' + (', '.join(map(str, finding['related_issue_indexes'])) or '无直接关联'),
            '同组件其他诊断（不是属性因果证据）：' + (', '.join(map(str, finding.get('component_context_issue_indexes', []))) or '无'),
            '待查模块：' + '; '.join(finding['owners']),
            '根因未确认。最后正确/首次错误仅能按下列已有证据判断，null 表示尚不可确定。',
            '```json', json.dumps({'trace': finding.get('trace'), 'evidence': finding['evidence'],
                'source_binding': finding.get('source_binding'), 'source': finding.get('source')}, ensure_ascii=False, indent=2),
            '```', '修复验证：' + finding['verification'], ''])
    lines.extend(triage['limitations'])
    return '\n'.join(lines)
