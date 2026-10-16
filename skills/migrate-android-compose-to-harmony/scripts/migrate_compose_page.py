#!/usr/bin/env python3
"""Prepare one closure-led AI page migration or an explicit deterministic candidate."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from ui_migration.frontend.project_styles import load_style_definitions
from ui_migration.verification.generation_diagnosis import diagnose_run, render_markdown
from ui_migration.progress import Progress, attach_log, checkpoint, phase

SCRIPTS = Path(__file__).parent


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--source', type=Path, help='Original Android project; creates a new safe snapshot and contract.')
    inputs.add_argument('--snapshot', type=Path, help='Existing safe snapshot; requires --contract.')
    parser.add_argument('--contract', type=Path)
    for name in ('style-definitions', 'output-dir', 'target'):
        parser.add_argument('--'+name, required=True, type=Path)
    for name in ('root-source', 'root-composable', 'page-id'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--state-id', default='default')
    parser.add_argument('--state-fixture', type=Path)
    parser.add_argument('--android-page-json', type=Path)
    parser.add_argument('--android-theme-facts', type=Path)
    parser.add_argument('--behavior-contract', type=Path)
    parser.add_argument('--behavior-inventory', type=Path)
    parser.add_argument('--behavior-source-review', type=Path,
                        help='Optional independent review, reported separately from business validation')
    parser.add_argument('--behavior-source-scope', type=Path)
    parser.add_argument('--behavior-scenario-results', type=Path)
    parser.add_argument('--api-adapters', type=Path)
    parser.add_argument('--no-auto-component-reuse', action='store_true',
                        help='Disable same-name/signature discovery in the target module.')
    parser.add_argument('--preserve-component-ui-states', action='store_true',
                        help='Preserve business-component UI branches without migrating their business conditions.')
    parser.add_argument('--module', default='entry')
    parser.add_argument('--component-dir', type=Path, help='Existing component scan directory, absolute or relative to --target, inside the module ETS tree.')
    parser.add_argument('--page-output-dir', type=Path, help='Generated page directory, absolute or relative to --target, inside the module ETS tree.')
    parser.add_argument('--project-name', help='Required for a new target.')
    parser.add_argument('--bundle-name', help='Required for a new target.')
    parser.add_argument('--sdk-version', help='Required for a new target; use an installed SDK version.')
    parser.add_argument('--viewport-width-dp', type=float)
    parser.add_argument('--viewport-height-dp', type=float)
    parser.add_argument('--slice-scale', type=float, default=2)
    parser.add_argument('--deterministic-candidate', action='store_true',
                        help='Explicitly run the legacy fixed-state Lanhu/ArkUI candidate generator.')
    parser.add_argument('--force', action='store_true', help='Regenerate an owned ArkUI page, never replace the project or run directory.')
    from ui_migration.target_access import add_target_arguments
    add_target_arguments(parser)
    return parser.parse_args()


def write_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temporary.replace(path)


class PageRun:
    def __init__(self, args):
        self.args = args
        self.directory = args.output_dir.expanduser().resolve()
        self.target = args.target.expanduser().resolve()
        self.stage = 'preflight'
        self.started = time.monotonic()
        self.report = {'ok':False, 'scope':'page-migration', 'visual_verified':False,
            'build_verified':False, 'business_verified':False, 'stages':[]}
        self.created = False

    def tool(self, stage, script, *arguments):
        self.stage = stage
        command = [sys.executable, str(SCRIPTS/script), *map(str, arguments)]
        started = time.monotonic()
        label = f'{len(self.report["stages"]):02d}-{stage}'
        stdout_path = self.directory/(label+'.stdout.log')
        stderr_path = self.directory/(label+'.stderr.log')
        entry = {'stage':stage, 'command':command, 'exit_code':None, 'status':'running',
            'seconds':0, 'stdout':stdout_path.name, 'stderr':stderr_path.name}
        self.report['stages'].append(entry)
        self.report.update(status='running', current_stage=stage)
        self.save()
        try:
            with phase(stage), stdout_path.open('w') as stdout, stderr_path.open('w') as stderr:
                with stderr_path.open() as live, subprocess.Popen(command, stdout=stdout, stderr=stderr,
                        env={**os.environ, 'PYTHONUNBUFFERED':'1'}) as process:
                    entry['pid'] = process.pid
                    checkpoint(stage, child_pid=process.pid, stdout=str(stdout_path), stderr=str(stderr_path))
                    self.save()
                    try:
                        while process.poll() is None:
                            chunk = live.read()
                            if chunk:
                                sys.stderr.write(chunk)
                                sys.stderr.flush()
                            time.sleep(0.2)
                    except BaseException:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        raise
                    finally:
                        sys.stderr.write(live.read())
                        sys.stderr.flush()
                        entry['exit_code'] = process.returncode
                    checkpoint(stage, child_pid=process.pid, exit_code=process.returncode)
            entry['status'] = 'completed' if entry['exit_code'] == 0 else 'failed'
        except BaseException:
            entry['status'] = 'interrupted' if entry['exit_code'] is not None else 'failed'
            raise
        finally:
            entry['seconds'] = time.monotonic()-started
            self.save()
        output = stdout_path.read_text()
        if entry['exit_code']:
            try:
                detail = json.loads(output).get('error', '')
            except (ValueError, AttributeError):
                detail = ''
            detail = detail or stderr_path.read_text()[-1000:].strip()
            raise ValueError(f'{stage} failed: {detail}; see {self.directory/label}.stdout.log and .stderr.log')
        return json.loads(output)

    def save(self):
        self.report['seconds'] = time.monotonic()-self.started
        if self.created:
            write_json(self.directory/'result.json', self.report)

    def finish_diagnosis(self):
        diagnosis = diagnose_run(self.directory if self.created else None, self.report)
        self.report['diagnosis'] = diagnosis
        if self.created:
            path = self.directory/'diagnosis.md'
            path.write_text(render_markdown(diagnosis), encoding='utf-8')
            self.report['diagnosis_report'] = str(path)

    def run(self):
        a = self.args
        from ui_migration.target_access import metadata_directory
        existing_target = getattr(a, 'existing_target', False)
        metadata_base = getattr(a, 'target_metadata_dir', None)
        metadata = metadata_directory(a.target, a.module, existing_target, metadata_base)
        self.target_options = (['--existing-target', '--target-metadata-dir', metadata_base.expanduser().resolve()]
                               if existing_target else [])
        if not existing_target and self.target.exists():
            from ui_migration.arkui.project import normalize_target
            normalize_target(a.target)
        from ui_migration.target_paths import ets_directory, page_directory
        page_output = None
        component_dir = None
        if a.deterministic_candidate:
            page_output = page_directory(self.target, a.module, getattr(a, 'page_output_dir', None))
            component_dir = getattr(a, 'component_dir', None)
            if component_dir is not None:
                if getattr(a, 'no_auto_component_reuse', False):
                    raise ValueError('--component-dir cannot be used with --no-auto-component-reuse')
                component_dir = ets_directory(self.target, a.module, component_dir, option='--component-dir')
                if not component_dir.is_dir():
                    raise ValueError('--component-dir does not exist: ' + str(component_dir))
            if not getattr(a, 'no_auto_component_reuse', False):
                scan_root = component_dir or ets_directory(self.target, a.module)
                if scan_root.is_relative_to(page_output):
                    raise ValueError('--component-dir must not be inside --page-output-dir')
        if bool(a.snapshot) != bool(a.contract):
            raise ValueError('--snapshot and --contract must be provided together; --source does not accept --contract')
        styles = a.style_definitions.expanduser().resolve()
        load_style_definitions(styles)
        if a.deterministic_candidate and (a.viewport_width_dp is None or a.viewport_height_dp is None):
            raise ValueError('--deterministic-candidate requires --viewport-width-dp and --viewport-height-dp')
        if not a.deterministic_candidate:
            missing = [name for name, path in (
                ('--state-fixture', a.state_fixture),
                ('--android-page-json', a.android_page_json),
                ('--android-theme-facts', a.android_theme_facts),
            ) if path is None]
            if missing:
                raise ValueError('default source-first AI mode requires ' + ', '.join(missing))
        for value in (a.viewport_width_dp, a.viewport_height_dp, a.slice_scale):
            if value is None:
                continue
            if not math.isfinite(value) or value <= 0:
                raise ValueError('Viewport dimensions and slice scale must be finite and positive')
        source = (a.source or a.snapshot).expanduser().resolve()
        if not source.is_dir():
            raise ValueError('Source/snapshot directory does not exist: ' + str(source))
        protected = [source]
        if a.snapshot:
            manifest = json.loads((source/'.android-to-harmony-safe.json').read_text())
            original = manifest.get('source_root') or manifest.get('source', {}).get('root')
            if original:
                protected.append(Path(original).resolve())
            contract = json.loads(a.contract.expanduser().resolve().read_text())
            protected.append(Path(contract['source']['original_root']).resolve())
        for output in (self.directory, self.target):
            for path in protected:
                if output.is_relative_to(path) or path.is_relative_to(output):
                    raise ValueError('Source, target and run directories must be separate')
        if existing_target:
            base = metadata_base.expanduser().resolve()
            for path in [*protected, self.directory]:
                if base.is_relative_to(path) or path.is_relative_to(base):
                    raise ValueError('Target metadata, source and per-run output directories must be separate')
        if self.target.is_relative_to(self.directory) or self.directory.is_relative_to(self.target):
            raise ValueError('--target and --output-dir must be separate directories')
        if self.directory.exists():
            raise ValueError('--output-dir must be new; previous evidence is never overwritten')
        for path in (styles, a.state_fixture, a.android_page_json, a.android_theme_facts,
                     a.behavior_contract, a.behavior_inventory,
                     a.behavior_scenario_results, a.behavior_source_scope, a.api_adapters):
            if path is not None and not path.expanduser().resolve().is_file():
                raise ValueError('Input file does not exist: ' + str(path))
        if not self.target.exists() and (not all((a.project_name, a.bundle_name, a.sdk_version)) or a.module != 'entry'):
            raise ValueError('New target requires --project-name, --bundle-name, --sdk-version and module entry')
        self.directory.mkdir(parents=True)
        self.created = True
        attach_log(self.directory/'progress.jsonl')
        self.report['progress_log'] = str(self.directory/'progress.jsonl')
        self.report['inputs'] = {key:str(value.expanduser().resolve()) if isinstance(value, Path) else value
            for key,value in vars(a).items()}
        self.report['inputs']['page_output_dir'] = str(page_output) if page_output else None
        self.report['inputs']['component_dir'] = str(component_dir) if component_dir else None
        if existing_target:
            self.report['target_metadata_dir'] = str(metadata)
        if a.source:
            snapshot, contract = self.directory/'snapshot', self.directory/'migration-contract.json'
            self.tool('snapshot', 'prepare_safe_snapshot.py', '--source', source, '--snapshot', snapshot)
            self.tool('analysis', 'analyze_compose_project.py', '--snapshot', snapshot, '--output', contract)
        else:
            snapshot, contract = source, a.contract.expanduser().resolve()
            checkpoint('reuse-analysis', snapshot=str(snapshot), contract=str(contract))
        closure_path = self.directory/'effective-page-closure.json'
        closure_options = []
        for name, path in (
            ('--state-fixture', a.state_fixture),
            ('--android-page-json', a.android_page_json),
            ('--android-theme-facts', a.android_theme_facts),
            ('--api-adapters', a.api_adapters),
            ('--behavior-source-scope', a.behavior_source_scope),
        ):
            if path:
                closure_options.extend([name, path.expanduser().resolve()])
        closure = self.tool('effective-page-closure', 'generate_effective_page_closure.py',
            '--contract', contract, '--style-definitions', styles,
            '--root-source', a.root_source, '--root-composable', a.root_composable,
            '--page-id', a.page_id, '--state-id', a.state_id,
            '--output', closure_path, *closure_options)
        self.report['effective_page_closure'] = {
            'path': str(closure_path),
            'sha256': closure['output_sha256'],
            'identity_sha256': closure['identity_sha256'],
            'status': closure['status'],
            'visible_component_count': closure['visible_component_count'],
            'unresolved_branch_component_count': closure['unresolved_branch_component_count'],
            'business_transcription_status': closure['business_transcription_status'],
        }
        closure_document = json.loads(closure_path.read_text(encoding='utf-8'))
        if not a.deterministic_candidate and closure_document.get('status') not in {
            'candidate_complete', 'candidate_ready_for_ai', 'candidate_requires_runtime_facts'
        }:
            raise ValueError(
                'effective page closure is unavailable for source-first implementation; '
                f"status={closure_document.get('status')}"
            )
        if not a.deterministic_candidate:
            source_scope = closure_document['business_transcription'].get('scope')
            source_scope_path = self.directory/'behavior-source-scope.json'
            if not isinstance(source_scope, dict):
                self.stage = 'behavior-source-validation'
                raise ValueError('effective page closure has no page business source scope')
            write_json(source_scope_path, source_scope)
            scoped_source = closure_document['source_scope']
            ai_implementation = {
                'status':'blocked',
                'requires_source_reading':bool(scoped_source.get('reading_required')),
                'source_scope_entry_count':len(scoped_source.get('entry_files', [])),
                'source_scope_sha256':scoped_source['sha256'],
                'runtime_facts_bound':closure_document.get('runtime_facts') is not None,
                'runtime_theme_bound':closure_document.get('runtime_theme') is not None,
                'runtime_state_selection':(
                    'unresolved' if closure_document.get('status') == 'candidate_requires_runtime_facts'
                    else 'resolved'
                ),
                'dynamic_source_obligations':(
                    'required' if closure_document.get('unresolved_branch_components') else 'none'
                ),
                'ui_transcription':'required_from_scoped_source',
                'business_transcription':'specification_required',
                'next_action':(
                    'Author behavior-contract.v2 for this generated page '
                    'source scope, then rerun with the behavior artifacts.'
                ),
            }
            self.report.update(
                scope='source-first-ai-page',
                status='business_specification_required',
                failed_stage='behavior-source-validation',
                implementation_mode='closure-plus-source-first-ai',
                implementation_complete=False,
                migration_complete=False,
                verdict='fail',
                target=str(self.target),
                behavior_source_scope=str(source_scope_path),
                deterministic_generation={'requested':False, 'status':'not_run'},
                ai_implementation=ai_implementation,
            )
            behavior_inputs = (a.behavior_contract, a.behavior_inventory)
            if not all(behavior_inputs):
                self.stage = 'behavior-source-validation'
                raise ValueError(
                    'page behavior specification is required: provide --behavior-contract, '
                    'and --behavior-inventory'
                )
            review_args = (['--source-review', a.behavior_source_review.expanduser().resolve()]
                           if a.behavior_source_review else [])
            source_validation_path = self.directory/'behavior-source-validation.json'
            try:
                source_validation = self.tool(
                    'behavior-source-validation', 'validate_behavior_contract_v2.py',
                    '--phase', 'source', '--contract', a.behavior_contract.expanduser().resolve(),
                    '--inventory', a.behavior_inventory.expanduser().resolve(), '--snapshot', snapshot,
                    '--source-scope', source_scope_path,
                    *review_args,
                    '--output', source_validation_path,
                )
            except ValueError:
                self.report['status'] = 'business_specification_required'
                raise
            self.report['behavior_source_validation'] = {
                'path':str(source_validation_path),
                'verdict':source_validation['verdict'],
                'source_complete':source_validation['source_complete'],
                'semantic_review':source_validation['semantic_review'],
            }
            if not self.target.exists():
                self.tool('target', 'init_harmony_project.py', '--output', self.target, '--contract', contract,
                    '--project-name', a.project_name, '--bundle-name', a.bundle_name, '--sdk-version', a.sdk_version)
            elif not existing_target:
                from attach_contract_to_target import load_target_state
                _, target_state = load_target_state(self.target)
                if target_state.get('contract') is None:
                    self.tool('target-contract', 'attach_contract_to_target.py',
                        '--target', self.target, '--contract', contract)
            if not existing_target:
                from migration_agent import build_run_state, write_json_atomic
                from evidence_runner import load_run_identity, load_ownership_secret
                self.stage = 'evidence-identity'
                self.report['status'] = 'running'
                target_state = json.loads((self.target/'.migration/state.json').read_text())
                manifest = json.loads((snapshot/'.android-to-harmony-safe.json').read_text())
                state = build_run_state(self.directory, Path(manifest['source_root']),
                    snapshot, contract, self.target, {
                        'name':target_state['project_name'],
                        'bundle_name':target_state['bundle_name'],
                        'sdk_version':target_state['sdk_version'],
                    })
                write_json_atomic(self.directory/'agent-state.json', state)
                load_run_identity(self.directory, self.target, load_ownership_secret(self.target))
                self.report['evidence_run_root'] = str(self.directory)
            if a.behavior_scenario_results:
                target_validation_path = self.directory/'behavior-target-validation.json'
                self.report.update(status='business_verification_failed',
                                   failed_stage='behavior-target-validation')
                try:
                    target_validation = self.tool(
                        'behavior-target-validation', 'validate_behavior_contract_v2.py',
                        '--phase', 'target', '--contract', a.behavior_contract.expanduser().resolve(),
                        '--inventory', a.behavior_inventory.expanduser().resolve(), '--snapshot', snapshot,
                        '--source-scope', source_scope_path,
                        *review_args,
                        '--scenario-results', a.behavior_scenario_results.expanduser().resolve(),
                        '--target', self.target, '--output', target_validation_path,
                    )
                except ValueError:
                    self.report['status'] = 'business_verification_failed'
                    raise
                self.report.update(
                    ok=True,
                    status='page_business_verified',
                    failed_stage=None,
                    current_stage=None,
                    verdict='pass',
                    business_verified=True,
                    implementation_complete=False,
                    migration_complete=False,
                    behavior_target_validation={
                        'path':str(target_validation_path),
                        'verdict':target_validation['verdict'],
                        'runtime_complete':target_validation['runtime_complete'],
                        'application_complete':target_validation['application_complete'],
                        'semantic_review':target_validation['semantic_review'],
                    },
                    ai_implementation={**ai_implementation, 'status':'implemented_and_verified',
                        'business_transcription':'verified_from_scoped_source',
                        'next_action':(
                            'Continue the separate build, visual, device, and whole-migration gates; '
                            'page business verification alone is not migration completion.'
                        )},
                )
                self.finish_diagnosis()
                self.save()
                return self.report
            self.report.update(
                ok=True,
                scope='source-first-ai-page',
                status='ready_for_ai_implementation',
                failed_stage=None,
                current_stage=None,
                implementation_mode='closure-plus-source-first-ai',
                implementation_complete=False,
                migration_complete=False,
                verdict='not_evaluated',
                target=str(self.target),
                deterministic_generation={
                    'requested':False,
                    'status':'not_run',
                },
                ai_implementation={**ai_implementation,
                    'status':'pending',
                    'business_transcription':'validated_from_scoped_source',
                    'next_action':(
                        'Read every hash-bound source scope entry and its required project-local helpers, '
                        'then follow references/semantic-transcription.md in this Skill: collect each '
                        'complete UI-to-effect chain, transcribe its source-owned modules and all '
                        'source branches rather than only the captured state, compare '
                        'source/target scenarios, and rerun this command with --behavior-scenario-results. '
                        'This handoff is not completion.'
                    ),
                },
            )
            self.finish_diagnosis()
            self.save()
            return self.report
        source_page = self.directory/'source-page.json'
        self.tool('source-page', 'generate_source_page.py', '--snapshot', snapshot, '--contract', contract,
            '--style-definitions', styles, '--root-source', a.root_source, '--root-composable', a.root_composable,
            '--page-id', a.page_id, '--state-id', a.state_id, '--output', source_page)
        options = []
        inspect_explicit = a.api_adapters and not ets_directory(self.target, a.module).is_relative_to(page_output)
        if not getattr(a, 'no_auto_component_reuse', False) or inspect_explicit:
            options.extend(['--harmony-target', self.target, '--harmony-module', a.module,
                            '--page-output-dir', page_output])
            if getattr(a, 'no_auto_component_reuse', False):
                options.append('--no-auto-component-reuse')
            if component_dir is not None:
                options.extend(['--component-dir', component_dir])
        if getattr(a, 'preserve_component_ui_states', False):
            options.append('--preserve-component-ui-states')
        for name,path in (('--state-fixture', a.state_fixture), ('--api-adapters', a.api_adapters)):
            if path:
                options.extend([name, path.expanduser().resolve()])
        lanhu = self.tool('lanhu', 'generate_lanhu_source_page.py', '--source-page', source_page,
            '--output-dir', self.directory/'lanhu', '--viewport-width-dp', a.viewport_width_dp,
            '--viewport-height-dp', a.viewport_height_dp, '--slice-scale', a.slice_scale, *options)
        version = self.directory/'lanhu/version_json.json'
        if not self.target.exists():
            self.tool('target', 'init_harmony_project.py', '--output', self.target, '--contract', contract,
                '--project-name', a.project_name, '--bundle-name', a.bundle_name, '--sdk-version', a.sdk_version)
        self.tool('theme', 'generate_harmony_theme_resources.py', '--contract', contract,
            '--target', self.target, '--module', a.module, '--force', *self.target_options)
        self.resources(snapshot, version)
        arkui = self.tool('arkui', 'generate_arkui_page.py', '--target', self.target,
            '--module', a.module, '--page-json', version, '--page-output-dir', page_output,
            *(['--force'] if a.force else []), *self.target_options)
        complete = bool(lanhu.get('generation_complete') and arkui.get('generation_complete'))
        candidate = {
            'requested':a.deterministic_candidate,
            'status':'completed',
            'generation_complete':complete,
            'verdict':'pass' if complete else 'fail',
        }
        common = {
            'ok':True,
            'current_stage':None,
            'deterministic_generation':candidate,
            'generation_complete':complete,
            'warnings':arkui.get('warnings', lanhu.get('warnings', [])),
            'source_page':str(source_page),
            'version_json':str(version),
            'arkui':{
                'output':str(self.target/arkui['output']),
                'manifest':str(self.target/arkui['manifest']),
                'input_mode':'page-json-only',
                'unresolved_count':arkui['unresolved_count'],
            },
        }
        self.report.update(
            **common,
            status='generated' if complete else 'partial_generation',
            implementation_mode='deterministic-candidate',
            verdict='pass' if complete else 'fail',
        )
        self.finish_diagnosis()
        self.save()
        return self.report

    def resources(self, snapshot, version):
        from materialize_static_drawables import drawable_candidate

        self.stage = 'resources'
        from ui_migration.contracts.lanhu_storage import unpack_lanhu_document
        document = unpack_lanhu_document(json.loads(version.read_text()))
        manifest = json.loads((snapshot/'.android-to-harmony-safe.json').read_text())
        available = {candidate[1] for asset in manifest['local_only_assets']
                     if (candidate := drawable_candidate(asset)) is not None}
        requested = set(document.get('assets', []))
        names = sorted(requested & available)
        self.report['resources'] = {'requested':sorted(requested),
            'without_local_drawable_candidate':sorted(requested-available)}
        if names:
            self.tool('drawables', 'materialize_static_drawables.py', '--manifest', snapshot/'.android-to-harmony-safe.json',
                '--target', self.target, '--module', self.args.module, '--page-json', version,
                *self.target_options,
                *[arg for name in names for arg in ('--name', name)])
        for resource in sorted({f['resource'] for f in document['meta']['migration'].get('fontFaces', [])}):
            candidates = [asset['path'] for asset in manifest['local_only_assets']
                if Path(asset['path']).suffix.lower() in ('.ttf', '.otf') and Path(asset['path']).stem == resource]
            if len(candidates) == 1:
                destination = self.target/self.args.module/'src/main/resources/rawfile'/Path(candidates[0]).name
                self.tool('font', 'copy_local_asset.py', '--manifest', snapshot/'.android-to-harmony-safe.json',
                    '--asset-path', candidates[0], '--target', self.target, '--destination', destination,
                    *self.target_options)
        # The existing generator rejects missing/ambiguous font dependencies.


def main():
    from validate_business_dossier import requested, main as dossier_main
    if requested(sys.argv[1:]):
        return dossier_main()
    run = PageRun(parse_args())
    try:
        with Progress('page-run'):
            result = run.run()
    except (ValueError, RuntimeError, OSError, KeyError, KeyboardInterrupt) as error:
        run.report.update(ok=False, verdict='fail', failed_stage=run.stage,
                          error=str(error) or type(error).__name__)
        if run.report.get('status') not in {
            'business_specification_required', 'business_verification_failed'
        }:
            run.report['status'] = 'failed'
        run.finish_diagnosis()
        run.save()
        print(json.dumps(run.report, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
