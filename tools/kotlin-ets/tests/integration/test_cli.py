"""Public source-to-target seam; no legacy parser or generated-JS input."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TS = '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js'

class CliTests(unittest.TestCase):
    def test_diagnostic_range_edges_and_unavailable_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            compiler=str(ROOT/'tests/stdlib/compiler.sh')
            jar=root/'diagnostics.jar'
            cp=subprocess.run(['bash',compiler,'--classpath'],text=True,capture_output=True,check=True).stdout.strip()
            compiled=subprocess.run(['bash',compiler,str(ROOT/'src/target/Tree.kt'),str(ROOT/'src/core/SourceDiagnostics.kt'),
                                     str(ROOT/'tests/integration/SourceDiagnostics.kt'),'-d',str(jar)],text=True,capture_output=True)
            self.assertEqual(compiled.returncode,0,compiled.stdout+'\n'+compiled.stderr)
            run=subprocess.run(['java','-cp',str(jar)+':'+cp,'dev.ets.tests.SourceDiagnosticsKt',str(root)],text=True,capture_output=True)
            self.assertEqual(run.returncode,0,run.stdout+'\n'+run.stderr)
            records=[json.loads(line) for line in run.stdout.splitlines()]
            fields=['line','column','endLine','endColumn']
            self.assertEqual(len(records),11)
            for record, expected in zip(records[:4],[(1,1,1,4),(1,4,2,3),(3,1,3,1),(1,1,1,1)]):
                self.assertEqual(tuple(record[field] for field in fields),expected)
            self.assertEqual(records[0]['file'],str(root/'quoted"\t.kt'))
            self.assertEqual([(r['start'],r['end']) for r in records[:7]],[(0,3),(3,6),(7,7),(0,0),(-1,-1),(3,2),(0,8)])
            for record in records[4:10]:
                self.assertTrue(all(record[field] is None for field in fields),record)
            self.assertIsNone(records[9]['file'])
            self.assertEqual(records[10],'error\t\b\x00\r\n"\\')

    def test_unresolved_frontend_never_publishes_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/'Unresolved.kt'
            source.write_text('package other\nfun broken():Int=missingPlatformOperation()\n')
            target=root/'Unresolved.ets'
            run=subprocess.run(['bash',str(ROOT/'kotlin-ets'),'--mode','language','--out',str(target),str(source)],
                               text=True,capture_output=True)
            self.assertEqual(run.returncode,1,run.stdout+'\n'+run.stderr)
            self.assertIn('missingPlatformOperation',run.stderr)
            self.assertIn('Unresolved.kt',run.stderr)
            self.assertEqual(json.loads(run.stdout)['code'],'COMPILATION_REJECTED')
            self.assertFalse(target.exists())

    def test_renamed_methods_and_changed_inputs_execute(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root/'Different.kt'
            source.write_text('package arbitrary\nfun gapFromInputs(base:Int,extra:Int=5):Int=base+extra\n'
                              'fun chooseAction(index:Int):String=if(index==3) "Finish" else "Forward"\n')
            target = root/'Different.ets'
            run = subprocess.run(['bash', str(ROOT/'kotlin-ets'), '--mode','language','--out',str(target),str(source)],
                                 text=True,capture_output=True)
            self.assertEqual(run.returncode,0,run.stdout+'\n'+run.stderr)
            code = ('const ts=require(process.argv[1]);const fs=require("fs");'
                    'const js=ts.transpileModule(fs.readFileSync(process.argv[2],"utf8"),'
                    '{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;'
                    'const m={exports:{}};new Function("exports","module",js)(m.exports,m);'
                    'console.log(JSON.stringify([m.exports.gapFromInputs(17,6),m.exports.gapFromInputs(9),'
                    'm.exports.chooseAction(3),m.exports.chooseAction(2)]));')
            observed = subprocess.run(['node','-e',code,TS,str(target)],text=True,capture_output=True)
            self.assertEqual(observed.returncode,0,observed.stderr)
            self.assertEqual(json.loads(observed.stdout),[23,14,'Finish','Forward'])

    def test_unknown_platform_operation_is_source_linked_and_no_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/'Unknown.kt'
            source.write_text('package other\nfun collectRuntime():Unit=java.lang.System.gc()\n')
            target=root/'Unknown.ets'
            run=subprocess.run(['bash',str(ROOT/'kotlin-ets'),'--mode','language','--out',str(target),str(source)],
                               text=True,capture_output=True)
            self.assertEqual(run.returncode,2,run.stdout+'\n'+run.stderr)
            diagnostic=json.loads(run.stdout)
            self.assertEqual(diagnostic['code'],'UNSUPPORTED')
            self.assertIn('java.lang.System.gc',diagnostic['message'])
            self.assertEqual(Path(diagnostic['source']['file']),source)
            self.assertGreaterEqual(diagnostic['source']['start'],0)
            self.assertEqual(diagnostic['source']['line'],2)
            self.assertEqual(diagnostic['source']['column'],44)
            self.assertEqual(diagnostic['source']['endLine'],2)
            self.assertEqual(diagnostic['source']['endColumn'],48)
            self.assertFalse(target.exists())

    def test_unicode_columns_and_normalized_newlines(self):
        text='// \u4e2d\U0001f600\nfun fail(): Unit = /*\u4e2d\U0001f600*/ java.lang.System.gc()\n'
        for newline, bom in [('LF', False), ('CRLF', False), ('CR', False), ('CRLF', True)]:
            with self.subTest(newline=newline, bom=bom), tempfile.TemporaryDirectory() as temp:
                source=Path(temp)/'Unicode.kt'
                content=text.replace('\n', {'LF':'\n', 'CRLF':'\r\n', 'CR':'\r'}[newline])
                source.write_bytes((('\ufeff' if bom else '')+content).encode('utf-8'))
                target=Path(temp)/'Unicode.ets'
                run=subprocess.run(['bash',str(ROOT/'kotlin-ets'),'--mode','language','--out',str(target),str(source)],
                                   text=True,capture_output=True)
                self.assertEqual(run.returncode,2,run.stdout+'\n'+run.stderr)
                diagnostic=json.loads(run.stdout)
                self.assertEqual(diagnostic['code'],'UNSUPPORTED')
                self.assertEqual(diagnostic['source'],dict(file=str(source),start=51,end=55,
                                                         line=2,column=45,endLine=2,endColumn=49))
                self.assertFalse(target.exists())

    def test_invalid_target_identifies_conflicting_declaration(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            sources=[]
            for name in ['first', 'second']:
                directory=root/name
                directory.mkdir()
                source=directory/'Same.kt'
                source.write_text(f'fun {name}(): Int = 1\n')
                sources.append(str(source))
            target=root/'modules'
            run=subprocess.run(['bash',str(ROOT/'kotlin-ets'),'--mode','language','--out-dir',str(target),*sources],
                               text=True,capture_output=True)
            self.assertEqual(run.returncode,2,run.stdout+'\n'+run.stderr)
            diagnostic=json.loads(run.stdout)
            self.assertEqual(diagnostic['code'],'INVALID_TARGET')
            self.assertEqual(diagnostic['source'],dict(file=sources[1],start=0,end=21,
                                                     line=1,column=1,endLine=1,endColumn=22))
            self.assertFalse(target.exists())

if __name__=='__main__':
    unittest.main(verbosity=2)
