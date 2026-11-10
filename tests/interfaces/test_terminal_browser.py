"""The browser terminal's real module with a slow renderer and deterministic transport boundaries."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "the browser module requires Node")
class TerminalStream(unittest.TestCase):
    def exercise(self, streaming):
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
    const end=this.number===0?initial:replay.length;
    if(offset<end)setImmediate(()=>{if(this.readyState===1)this.onmessage({data:replay.slice(offset,Math.min(end,offset+65536)).buffer})});
  }}
  close(){this.readyState=3;this.onclose?.({code:1000});}
};
const module = new vm.SourceTextModule(fs.readFileSync(new URL(process.argv[1]),'utf8'));
await module.link(async name=>{
  const values=name==='./api.js'?{CONFIG:{terminal_size:{cols:160,rows:48},terminal_ports:{windows:1},token:'synthetic'}}:{$};
  return new vm.SyntheticModule(Object.keys(values),function(){for(const [key,value]of Object.entries(values))this.setExport(key,value)});
});
await module.evaluate();
const api=module.namespace;
api.showTerminals('first','windows');
api.updateTerminals({open:true,shown:'engineer',working:'engineer',since:'now'});
const first=sockets[0];first.onopen?.();
first.onmessage({data:JSON.stringify({live:true,size:[160,48],...(streamed?{replay:initial}:{})})});
if(streamed)assert($('state-engineer').textContent.startsWith('catching up'),'replay must not claim to be live');
async function wait(test){const end=Date.now()+20000;while(!test()){if(Date.now()>end)throw Error('renderer did not catch up');await new Promise(r=>setTimeout(r,10));}}
if(streamed)await wait(()=>terms[0].parsed>262144);
else {
  first.onmessage({data:history.buffer});
  for(let n=0;n<fragments.length;n+=128)first.onmessage({data:fragments.slice(n,n+128).buffer});
  first.onmessage({data:live.buffer});
}
first.close();
await wait(()=>sockets.length===2);
assert(terms[0].maximum<=1024*1024,'xterm queue must stay bounded');
if(!streamed)assert(terms[0].text.includes('LIVE_ONE'),'live output was lost');
const second=sockets[1];second.onopen?.();
second.onmessage({data:JSON.stringify({live:true,size:[160,48],...(streamed?{replay:replay.length}:{})})});
if(!streamed)second.onmessage({data:replay.buffer});
await wait(()=>terms[0].text.includes('LIVE_TWO'));
assert.equal(terms[0].parsed,replay.length,'reconnect duplicated or skipped bytes');
assert($('state-engineer').textContent.startsWith('live:'),'caught-up output must be identified as live');
assert(terms[0].calls<1000,'small redraw frames must share bounded renderer writes');
terms[0].input('operator-key');
assert(second.sent.includes('operator-key'),'operator input was lost');
api.showTerminals('second','windows');
assert.equal(sockets[1].readyState,3,'switching runs must detach the old socket');
console.log('large replay, live output, confirmed reconnect and input: PASS');
"""
        result = subprocess.run([shutil.which("node"), "--experimental-vm-modules", "--input-type=module",
                                 "-e", script, path.as_uri()], env=dict(os.environ, STREAM="1" if streaming else "0"),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_large_legacy_replay_live_output_and_reconnect_wait_for_confirmed_parsing(self):
        self.exercise(False)

    def test_pull_stream_acknowledges_parsed_bytes_and_resumes_without_duplicates(self):
        self.exercise(True)
