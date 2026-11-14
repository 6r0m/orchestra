"""A cancelled skill catalog cannot overwrite a subsequently opened instruction picker."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'instruction picker scheduling requires Node')
class InstructionPicker(unittest.TestCase):
    def test_selection_cannot_be_added_after_its_stop_changed(self):
        source = Path(__file__).resolve().parents[2] / 'app/interfaces/workbench/static/skills.js'
        script = r'''
import fs from 'node:fs';
import assert from 'node:assert/strict';
const nodes=new Map();
const node=(tag='',text='')=>({tag,textContent:text,value:'',open:false,children:[],
  replaceChildren(){this.children=[];},append(...x){this.children.push(...x);},
  showModal(){this.open=true;},close(){this.open=false;},focus(){},dispatchEvent(){this.events=(this.events||0)+1;}});
const get=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);};
const catalog={version:1,roles:{engineer:'pi'},stage_skills:{},skills:{pi:[
  {name:'fixture-skill',scope:'global',reference:'/fixture/fixture-skill/SKILL.md'}]}};
globalThis.fixture={get,node,api:async()=>catalog};
const source=fs.readFileSync(process.argv[1],'utf8')
  .replace(/import \{ api \} from "\.\/api.js";/,'const api=globalThis.fixture.api;')
  .replace(/import \{ \$, el \} from "\.\/ui.js";/,'const $=globalThis.fixture.get,el=globalThis.fixture.node;');
const {pickSkills}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
let stop='run:1';const input=node();input.value='Original stop note';
await pickSkills({run:'run',input,isCurrent:()=>stop==='run:1'});
get('instruction-skills-stage').value='This request';
const box=get('instruction-skills-options').children[0].children[0];box.checked=true;box.onchange();
stop='run:2';input.value='New stop note';
get('instruction-skills-add').onclick();
assert.equal(input.value,'New stop note');
assert.equal(input.events||0,0,'refusal must dispatch no draft update');
assert.match(get('instruction-skills-status').textContent,/changed/i);
assert.equal(get('instruction-skills').open,true);
'''
        result = subprocess.run(['node', '--input-type=module', '-e', script, str(source)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_late_cancelled_read_cannot_change_the_new_picker_or_its_input(self):
        source = Path(__file__).resolve().parents[2] / 'app/interfaces/workbench/static/skills.js'
        script = r'''
import fs from 'node:fs';
import assert from 'node:assert/strict';
function node(tag='',text='') {return {tag,textContent:text,value:'',open:false,children:[],
  replaceChildren(){this.children=[];},append(...x){this.children.push(...x);},
  showModal(){this.open=true;},close(){this.open=false;},focus(){},dispatchEvent(){}};}
const nodes=new Map(), pending=[];
const get=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);};
globalThis.fixture={get,node,api:()=>new Promise(resolve=>pending.push(resolve))};
let source=fs.readFileSync(process.argv[1],'utf8')
  .replace(/import \{ api \} from "\.\/api.js";/,'const api=globalThis.fixture.api;')
  .replace(/import \{ \$, el \} from "\.\/ui.js";/,'const $=globalThis.fixture.get,el=globalThis.fixture.node;');
const {pickSkills}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const first=node(),second=node();first.value='Original task';second.value='Original note';
const a=pickSkills({repo:'first',input:first});
get('instruction-skills-cancel').onclick();
const b=pickSkills({repo:'second',input:second});
const catalog=name=>({version:1,roles:{engineer:'pi'},stage_skills:{},
  skills:{pi:[{name,scope:'repository',reference:'/fixture/'+name+'/SKILL.md'}]}});
pending[1](catalog('second-skill'));await b;
pending[0](catalog('first-skill'));await a;
const label=get('instruction-skills-options').children[0];
assert.match(label.children[1].textContent,/second-skill/);
get('instruction-skills-stage').value='This request';
label.children[0].checked=true;label.children[0].onchange();
get('instruction-skills-add').onclick();
assert.equal(first.value,'Original task');
assert.match(second.value,/^Original note/);
assert.match(second.value,/second-skill\/SKILL.md/);
assert.ok(!second.value.includes('first-skill'));
'''
        result = subprocess.run(['node', '--input-type=module', '-e', script, str(source)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
