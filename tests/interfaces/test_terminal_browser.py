"""The browser terminal's real module with a slow renderer and deterministic transport boundaries."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "the browser module requires Node")
class TerminalStream(unittest.TestCase):
    def exercise(self, streaming, recorded=False):
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
      addEventListener:(name,fn)=>handlers[name]=fn, replaceChildren:()=>{},
      querySelector:()=>null,clientWidth:0,scrollIntoView:()=>{},
      get open(){return open},set open(value){if(value!==open){open=value;handlers.toggle?.()}}});
  }
  return elements.get(id);
}
globalThis.document={body:{classList:{toggle:()=>{}}}};
globalThis.window={addEventListener:()=>{}};
globalThis.ResizeObserver=class{observe(){}};
Object.defineProperty(globalThis,'navigator',{value:{},configurable:true});
const terms=[],sockets=[];
const streamed=process.env.STREAM==='1';
const recorded=process.env.RECORDED==='1';
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
  open(){} attachCustomKeyEventHandler(){} onData(fn){this.input=fn;} dispose(){} focus(){}
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
    this.number=sockets.length;sockets.push(this);}
  send(value){this.sent.push(value);if(streamed&&typeof value!=='string'){
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
  const values=name==='./api.js'?{CONFIG:{terminal_size:{cols:160,rows:48},terminal_ports:{windows:1},token:'synthetic'}}:{$};
  return new vm.SyntheticModule(Object.keys(values),function(){for(const [key,value]of Object.entries(values))this.setExport(key,value)});
});
await module.evaluate();
const api=module.namespace;
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
await wait(()=>sockets.length===2);
assert(terms[0].maximum<=1024*1024,'xterm queue must stay bounded');
if(!streamed)assert(terms[0].text.includes('LIVE_ONE'),'live output was lost');
const second=sockets[1];second.onopen?.();
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
  const refused=sockets[2];
  refused.onmessage({data:JSON.stringify({live:false,replay:replay.length})});
  refused.close(1008);
  assert($('state-engineer').textContent.includes('failed'),'cursor refusal must remain visible');
  assert.equal(reconnectTimers,1,'cursor refusal must never retry even with an incomplete replay');
}else{
  terms[0].input('operator-key');
  assert(second.sent.includes('operator-key'),'operator input was lost');
}
api.showTerminals('second','windows');
assert.equal(sockets[1].readyState,3,'switching runs must detach the old socket');
console.log('large replay, live output, confirmed reconnect and input: PASS');
"""
        result = subprocess.run([shutil.which("node"), "--experimental-vm-modules", "--input-type=module",
                                 "-e", script, path.as_uri()], env=dict(os.environ, STREAM="1" if streaming else "0",
                                                                     RECORDED="1" if recorded else "0"),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_large_legacy_replay_live_output_and_reconnect_wait_for_confirmed_parsing(self):
        self.exercise(False)

    def test_pull_stream_acknowledges_parsed_bytes_and_resumes_without_duplicates(self):
        self.exercise(True)

    def test_recorded_partial_replay_reconnects_and_normal_eof_stays_closed(self):
        self.exercise(True, recorded=True)
