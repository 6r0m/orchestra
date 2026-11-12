"""The actual clipboard reader accepts only complete immutable snapshot pages."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "the browser module requires Node")
class CopyPatch(unittest.TestCase):
    def test_multibyte_pages_labels_and_refusals_preserve_the_clipboard(self):
        path = Path(__file__).resolve().parents[2] / "app/interfaces/workbench/static/diff.js"
        script = r'''
import fs from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';
let copied='original', response, reads=[];
globalThis.window={};globalThis.setTimeout=()=>{};
Object.defineProperty(globalThis,'navigator',{value:{clipboard:{writeText:async text=>{copied=text}}},configurable:true});
const module=new vm.SourceTextModule(fs.readFileSync(new URL(process.argv[1]),'utf8'));
await module.link(async name=>{
 const values=name==='./api.js'?{api:async url=>{reads.push(url);return response}}:{el:()=>{}};
 return new vm.SyntheticModule(Object.keys(values),function(){for(const [k,v]of Object.entries(values))this.setExport(k,v)});
});await module.evaluate();
const {copyPatch}=module.namespace;
const first={base:'base',tree:'tree',patch:'é',next:2,total:6,review_range:{from:1,through:2,current:false}};
response={base:'base',tree:'tree',patch:'🧩',next:6,total:6};
const button={};await copyPatch('run',first,button);
assert(copied.endsWith('é🧩'));assert(copied.startsWith('# Review range:'));
assert.equal(button.textContent,'Copied');assert(reads[0].includes('base=base&tree=tree&offset=2'));
const kept=copied;
for(const invalid of [{...response,tree:'other'},{...response,next:2},{...response,patch:'x'}]){
 response=invalid;await copyPatch('run',first,button);
 assert.equal(button.textContent,'Copy failed');assert.equal(copied,kept);assert.equal(button.disabled,false);
}
await copyPatch('run',{...first,next:NaN},button);assert.equal(copied,kept);assert.equal(button.textContent,'Copy failed');
navigator.clipboard.writeText=async()=>{throw Error('clipboard refused')};
await copyPatch('run',{base:'b',tree:'t',patch:'',next:0,total:0},button);
assert.equal(copied,kept);assert.equal(button.textContent,'Copy failed');
console.log('complete UTF-8 snapshot copy and refusal without mutation: PASS');
'''
        result = subprocess.run([shutil.which("node"), "--experimental-vm-modules", "--input-type=module",
                                 "-e", script, path.as_uri()], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
