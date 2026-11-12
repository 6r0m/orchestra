"""The browser terminal's real module with a slow renderer and deterministic transport boundaries."""
import os
import re
from pathlib import Path
import shutil
import subprocess
import unittest


class SnapshotCompatibility(unittest.TestCase):
    def test_native_snapshot_format_matches_both_pinned_vendor_versions(self):
        static = Path(__file__).resolve().parents[2] / "app/interfaces/workbench/static"
        versions = []
        for name in ("xterm", "xterm-serialize"):
            manifest = (static / "vendor" / name / "VERSION").read_text(encoding="utf-8")
            versions.append(re.search(r"@xterm/[\w-]+ (\d+\.\d+\.\d+)", manifest)[1])
        expected = "xterm-%s/serialize-%s/" % tuple(versions)
        source = (static / "terminal-cache.js").read_text(encoding="utf-8")
        self.assertIn('const FORMAT = "' + expected, source,
                      "a native vendor change requires a snapshot-format and continuation-state review")


@unittest.skipUnless(shutil.which("node"), "the browser module requires Node")
class TerminalStream(unittest.TestCase):
    def exercise(self, streaming, recorded=False, cache=False, warm=False):
        path = Path(__file__).resolve().parents[2] / "app/interfaces/workbench/static/terminals.js"
        script = r"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const elements = new Map();
function $(id) {
  if (!elements.has(id)) {
    const handlers={}; let open=false;
    elements.set(id,{textContent:'',classList:{contains:()=>false,toggle:()=>{}},
      addEventListener:(name,fn)=>handlers[name]=fn, replaceChildren:(...nodes)=>{},
      querySelector:()=>null,clientWidth:0,scrollIntoView:()=>{},
      get open(){return open},set open(value){if(value!==open){open=value;handlers.toggle?.()}}});
  }
  return elements.get(id);
}
globalThis.document={body:{classList:{toggle:()=>{}}},createElement:()=>({style:{},remove:()=>{}}),addEventListener:()=>{}};
globalThis.window={addEventListener:()=>{}};
globalThis.ResizeObserver=class{observe(){}};
Object.defineProperty(globalThis,'navigator',{value:{},configurable:true});
const terms=[],sockets=[];
const closedCaches=[];
const streamed=process.env.STREAM==='1';
const recorded=process.env.RECORDED==='1';
const manual=process.env.CACHE==='1'||process.env.WARM==='1';
let reconnectTimers=0;
const nativeTimeout=globalThis.setTimeout;
globalThis.setTimeout=(fn,delay,...args)=>{
  if(delay===3000)reconnectTimers++;
  return nativeTimeout(fn,delay,...args);
};
const history=new Uint8Array(51*1024*1024);
const fragments=new Uint8Array(4096*128);
const live=new TextEncoder().encode('LIVE_ONE\r\n');
const later=new TextEncoder().encode('LIVE_TWO\r\n');
const initial=history.length+fragments.length+live.length;
const replay=new Uint8Array(initial+later.length);
replay.set(history);replay.set(fragments,history.length);
replay.set(live,history.length+fragments.length);replay.set(later,initial);
class Renderer {
  constructor(){terms.push(this);this.options={};this.parser={registerOscHandler:()=>{}};
    this.pending=0;this.maximum=0;this.parsed=0;this.text='';this.calls=0;}
  open(){} attachCustomKeyEventHandler(){} onData(fn){this.input=fn;} dispose(){this.disposed=true;} focus(){}
  scrollToBottom(){this.tailed=true;}
  write(data,done){
    this.calls++;
    if(this.pending>50000000)throw Error('write data discarded');
    this.pending+=data.length;this.maximum=Math.max(this.maximum,this.pending);
    setImmediate(()=>{this.pending-=data.length;this.parsed+=data.length;
      this.text+=new TextDecoder().decode(data.subarray(Math.max(0,data.length-40))).replaceAll('\x00','');done?.();});
  }
}
globalThis.Terminal=Renderer;
globalThis.WebSocket=class {
  static OPEN=1;
  constructor(url){this.url=url;this.protocol=streamed?'workbench.v2':'workbench.v1';this.readyState=1;this.sent=[];
    this.number=sockets.filter(s=>s.url===url).length;sockets.push(this);}
  send(value){this.sent.push(value);if(streamed&&!manual&&typeof value!=='string'){
    const offset=JSON.parse(new TextDecoder().decode(value)).read;
    assert(Number.isSafeInteger(offset));
    if(recorded&&this.number===0&&offset>=2*1024*1024)return;
    const end=this.number===0?initial:replay.length;
    if(offset<end)setImmediate(()=>{if(this.readyState===1)this.onmessage({data:replay.slice(offset,Math.min(end,offset+65536)).buffer})});
    else if(recorded)setImmediate(()=>this.close());
  }}
  close(code=1000){this.readyState=3;this.onclose?.({code});}
};
const module = new vm.SourceTextModule(fs.readFileSync(new URL(process.argv[1]),'utf8'));
await module.link(async name=>{
  const values=name==='./api.js'?{CONFIG:{terminal_size:{cols:160,rows:48},terminal_ports:{windows:1},token:'synthetic'},
    api:async()=>({view:{state:'closed'}})}:
    name==='./terminal-cache.js'?{read:()=>null,save:async()=>false,close:id=>closedCaches.push(id),
      remove:()=>{},issue:()=>'',runs:()=>['offline-run']}:{$};
  return new vm.SyntheticModule(Object.keys(values),function(){for(const [key,value]of Object.entries(values))this.setExport(key,value)});
});
await module.evaluate();
const api=module.namespace;
if(process.env.WARM==='1'){
  api.noteTerminalRuns([]);
  for(let n=0;n<4;n++)await new Promise(r=>setImmediate(r));
  assert(closedCaches.includes('offline-run'),'closed persisted runs absent from the rail need startup reconciliation');
  api.showTerminals('waiting','windows');
  api.updateTerminals({open:true,shown:null,working:null,since:'approval'});
  assert.equal(sockets.length,2,'waiting runs must warm both roles before the operator answers');
  assert.equal($('terminal-architect').open,false);
  api.updateTerminals({open:true,shown:'architect',working:'architect',since:'review'});
  const engineerSocket=sockets.find(s=>s.url.endsWith('/engineer'));
  assert(engineerSocket,'the unopened engineer must start warming during architect review');
  assert.equal($('terminal-engineer').open,false,'warming must leave the operator disclosure alone');
  const engineer=terms[sockets.indexOf(engineerSocket)];
  engineerSocket.onmessage({data:JSON.stringify({live:true,replay:4})});
  engineerSocket.onmessage({data:new TextEncoder().encode('TAIL').buffer});
  for(let n=0;n<4;n++)await new Promise(r=>setImmediate(r));
  assert.equal(engineer.parsed,4,'the closed panel must parse recorded output');
  const count=sockets.length;
  api.updateTerminals({open:true,shown:'engineer',working:'engineer',since:'build'});
  assert.equal(sockets.length,count,'the role switch must keep the warm connection');
  assert(!engineer.disposed);
  assert(engineer.tailed,'the newly active role must show the warm tail');
  api.showTerminals('closed','windows');
  const closedCount=sockets.length;
  api.updateTerminals({open:false,shown:null,working:null,since:'closed'});
  assert.equal(sockets.length,closedCount,'closed runs must not prefetch unopened roles');
  console.log('unopened role warms, parses and switches without replay: PASS');
  process.exit(0);
}
if(process.env.CACHE==='1'){
  async function settle(){for(let n=0;n<4;n++)await new Promise(r=>setImmediate(r));}
  const show=(id,target='windows')=>{
    api.showTerminals(id,target);
    api.updateTerminals({open:true,shown:'engineer',working:'engineer',since:id});
  };
  show('A');
  const a=terms[0], first=sockets[0];
  first.onmessage({data:JSON.stringify({live:true,replay:4})});
  first.onmessage({data:new TextEncoder().encode('ABCD').buffer});
  // Navigate before the parser callback: the confirmed cursor must finish advancing while parked.
  show('B');await settle();
  assert.equal(first.readyState,3);
  assert(!a.disposed,'open runs must retain their parsed emulator');
  api.noteTerminalRuns([]);
  assert(!a.disposed,'an incomplete rail page cannot establish closure');
  assert.equal(a.parsed,4);
  const otherState=$('state-engineer').textContent;
  first.onmessage({data:JSON.stringify({live:true,replay:999999})});
  assert.equal($('state-engineer').textContent,otherState,'parked output must not change another run');
  show('A');await settle();
  assert.equal(terms.length,4,'returning must reuse both role emulators');
  const resumed=sockets.findLast(s=>s.url===first.url);resumed.onopen();
  assert.equal(JSON.parse(new TextDecoder().decode(resumed.sent[0])).read,4);
  resumed.onmessage({data:JSON.stringify({live:true,replay:4})});
  a.input('A input');assert(resumed.sent.includes('A input'));
  assert(a.tailed,'automatic restoration must show the latest screen');
  show('C');show('D');
  assert(terms[2].disposed&&terms[3].disposed,'both least recently used hidden displays must be evicted');
  assert(!a.disposed,'recently used display must survive pressure');
  api.noteTerminalRuns([{run_id:'A',state:'closed'},{run_id:'C',state:'waiting'}]);
  assert(a.disposed,'confirmed closure must release hidden displays');
  show('C','wsl');
  assert.equal(terms.length,10,'another host must never reuse either role emulator');
  const closed=terms.at(-1),closedSocket=sockets.at(-1);
  closedSocket.onmessage({data:JSON.stringify({live:true,replay:0})});
  api.noteTerminalRuns([{run_id:'C',state:'closed'}]);
  api.updateTerminals({open:true,shown:'engineer',working:'engineer',since:'stale'});
  closed.input('must not reach a closed run');
  assert(!closedSocket.sent.includes('must not reach a closed run'),'stale open reads must not undo confirmed closure');
  assert(!closed.disposed,'the currently visible record remains readable');
  show('E');assert(closed.disposed,'closed displays must not survive navigation');
  console.log('cached navigation, confirmed cursor, isolation, bounds and closure: PASS');
  process.exit(0);
}
api.showTerminals('first','windows');
api.updateTerminals({open:!recorded,shown:'engineer',working:recorded?null:'engineer',since:'now'});
const first=sockets[0];first.onopen?.();
first.onmessage({data:JSON.stringify({live:!recorded,size:[160,48],...(streamed?{replay:initial}:{})})});
if(streamed)assert($('state-engineer').textContent.startsWith('catching up'),'replay must not claim to be live');
async function wait(test){const end=Date.now()+20000;while(!test()){if(Date.now()>end)throw Error('renderer did not catch up');await new Promise(r=>setTimeout(r,10));}}
if(streamed)await wait(()=>terms[0].parsed>=(recorded?2*1024*1024:262145));
else {
  first.onmessage({data:history.buffer});
  for(let n=0;n<fragments.length;n+=128)first.onmessage({data:fragments.slice(n,n+128).buffer});
  first.onmessage({data:live.buffer});
}
if(recorded)assert(terms[0].parsed<initial,'the recorded replay must still be incomplete');
first.close(1006);
await wait(()=>sockets.filter(s=>s.url===first.url).length===2);
assert(terms[0].maximum<=1024*1024,'xterm queue must stay bounded');
if(!streamed)assert(terms[0].text.includes('LIVE_ONE'),'live output was lost');
const second=sockets.findLast(s=>s.url===first.url);second.onopen?.();
if(streamed)assert.equal(JSON.parse(new TextDecoder().decode(second.sent[0])).read,terms[0].parsed,
  'reconnect must request the confirmed renderer cursor');
second.onmessage({data:JSON.stringify({live:!recorded,size:[160,48],...(streamed?{replay:replay.length}:{})})});
if(!streamed)second.onmessage({data:replay.buffer});
await wait(()=>terms[0].text.includes('LIVE_TWO'));
assert.equal(terms[0].parsed,replay.length,'reconnect duplicated or skipped bytes');
assert($('state-engineer').textContent.startsWith(recorded?'recorded':'live:'),'caught-up output must identify its actual state');
assert(terms[0].calls<1000,'small redraw frames must share bounded renderer writes');
if(recorded){
  await wait(()=>second.readyState===3);
  assert.equal(reconnectTimers,1,'EOF after complete replay must not schedule another reconnect');
  api.showTerminals('refused','windows');
  api.updateTerminals({open:false,shown:'engineer',working:null,since:'refused'});
  const refused=sockets.find(s=>s.url.includes('/refused/'));
  refused.onmessage({data:JSON.stringify({live:false,replay:replay.length})});
  refused.close(1008);
  assert($('state-engineer').textContent.includes('failed'),'cursor refusal must remain visible');
  assert.equal(reconnectTimers,1,'cursor refusal must never retry even with an incomplete replay');
}else{
  terms[0].input('operator-key');
  assert(second.sent.includes('operator-key'),'operator input was lost');
}
api.showTerminals('second','windows');
assert.equal(second.readyState,3,'switching runs must detach the old socket');
console.log('large replay, live output, confirmed reconnect and input: PASS');
"""
        result = subprocess.run([shutil.which("node"), "--experimental-vm-modules", "--input-type=module",
                                 "-e", script, path.as_uri()], env=dict(os.environ, STREAM="1" if streaming else "0",
                                                                     RECORDED="1" if recorded else "0",
                                                                     CACHE="1" if cache else "0",
                                                                     WARM="1" if warm else "0"),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_large_legacy_replay_live_output_and_reconnect_wait_for_confirmed_parsing(self):
        self.exercise(False)

    def test_pull_stream_acknowledges_parsed_bytes_and_resumes_without_duplicates(self):
        self.exercise(True)

    def test_recorded_partial_replay_reconnects_and_normal_eof_stays_closed(self):
        self.exercise(True, recorded=True)

    def test_navigation_reuses_bounded_open_run_displays_and_evicts_only_confirmed_closed_runs(self):
        self.exercise(True, cache=True)

    def test_unopened_role_is_already_parsed_when_the_workflow_switches_roles(self):
        self.exercise(True, warm=True)
