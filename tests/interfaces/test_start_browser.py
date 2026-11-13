"""New-run startup ordering through the actual browser module, without creating a paid run."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'browser module ordering requires Node')
class StartBrowser(unittest.TestCase):
    def test_landing_preview_waits_for_the_initial_repository_list(self):
        source = Path(__file__).resolve().parents[2] / 'app/interfaces/workbench/static/start.js'
        script = r'''
import fs from 'node:fs';
import assert from 'node:assert/strict';
const nodes = new Map();
const get = id => {
  if (!nodes.has(id)) nodes.set(id, {value:'',textContent:'',hidden:false,addEventListener(){},
    replaceChildren(...children){this.children=children;},querySelector(){return {};}});
  return nodes.get(id);
};
let chosen = null, release, calls = 0;
const ready = new Promise(resolve => {release=()=>{chosen='example';resolve();};});
globalThis.fixture = {get, ready, chosen:()=>chosen, api:async path => {
  if(path==='/api/flows') return {default:'engineer-code',flows:[{name:'engineer-code',steps:[]}]};
  assert.ok(path.startsWith('/api/landing?repo=example'),path);
  calls++;
  return {version:1,branch:'main',remote:null,identity_ready:true};
}};
let source = fs.readFileSync(process.argv[1], 'utf8');
source=source.replace(/import \{ api \} from "\.\/api.js";/,
  'const api=globalThis.fixture.api;');
source=source.replace(/import \{[^}]+\} from "\.\/ui.js";/,
  'const $=globalThis.fixture.get, el=()=>({}), report=()=>{},sayRefused=()=>{},score=()=>{},wrote=()=>{};');
source=source.replace(/import \{[^}]+\} from "\.\/picker.js";/,
  'const sourceChoice=()=>globalThis.fixture.chosen,reposRead=()=>globalThis.fixture.ready;');
const module=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const reading=module.reloadFlows();
await Promise.resolve();
assert.equal(calls,0,'preview must not guess while the initial repository is unavailable');
release();
await reading;
assert.equal(calls,1,'the first real repository must refresh its landing without operator interaction');
assert.match(get('start-landing').textContent,/Merge lands on: main \(local; nothing is pushed\)/);
'''
        result = subprocess.run(['node', '--input-type=module', '-e', script, str(source)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
