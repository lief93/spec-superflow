"""Public source-to-target seam; no legacy parser or generated-JS input."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TS = '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js'

class CliTests(unittest.TestCase):
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
            self.assertFalse(target.exists())

if __name__=='__main__':
    unittest.main(verbosity=2)
