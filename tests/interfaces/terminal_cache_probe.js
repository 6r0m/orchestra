// Real browser/IndexedDB and the shipped xterm, on the acceptance fixture's disposable origin only.
import * as cache from "/terminal-cache.js";

const check = (condition, message) => { if (!condition) throw new Error(message); };
const write = (term, data) => new Promise((resolve) => term.write(data, resolve));
const terms = [];
function terminal() {
  const node = document.createElement("div");
  node.hidden = true;
  document.body.appendChild(node);
  const term = new Terminal({ cols: 160, rows: 48, scrollback: 50 });
  term.open(node);
  terms.push([term, node]);
  return term;
}

function view(term) {
  const core = term._core;
  return JSON.stringify({ rows: term.rows, cols: term.cols, modes: term.modes,
    hidden: core.coreService.isCursorHidden,
    mouse: [core.coreMouseService.activeProtocol, core.coreMouseService.activeEncoding],
    buffers: [term.buffer.normal, term.buffer.alternate].map((buffer) => ({
      x: buffer.cursorX, y: buffer.cursorY, base: buffer.baseY,
      lines: Array.from({ length: buffer.length }, (_, row) => {
        const line = buffer.getLine(row);
        return [line.translateToString(false), line.isWrapped,
          Array.from({ length: line.length }, (_, column) => {
            const cell = line.getCell(column);
            return [cell.getFgColor(), cell.getBgColor(), cell.isBold(), cell.isUnderline()];
          })];
      })
    })) });
}

async function rows() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("orchestra-terminal-screens", 1);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      const db = request.result;
      const transaction = db.transaction("screens", "readonly");
      const all = transaction.objectStore("screens").getAll();
      all.onsuccess = () => resolve(all.result);
      transaction.oncomplete = () => db.close();
    };
  });
}

export async function run() {
  const cleanup = new Set();
  try {
    for (const alternate of [false, true]) {
      const original = terminal(), restored = terminal();
      if (alternate) original.resize(160, 138);
      const id = "probe-native-" + alternate;
      cleanup.add(id);
      const normal = "\x1b[31mRED\x1b[0m\r\n" + "a wrapped native line ".repeat(20) + "\r\n";
      const prefix = normal + (alternate ? "\x1b[?1049h" : "") +
        "\x1b[2;40r\x1b[?6h\x1b[5;7H\x1b[33m\x1b7\x1b[?25l\x1b[3;4H" +
        "\x1b[?1006h\x1b[?1002h\x1b(0qq\x1b(B";
      await write(original, new TextEncoder().encode(prefix));
      const cursor = new TextEncoder().encode(prefix).length;
      check(await cache.save(id, "windows", "engineer", cursor, original), "native screen was not saved");
      const saved = cache.read(id, "windows", "engineer");
      await cache.restore(restored, saved);
      check(view(original) === view(restored), "native screen or modes changed on restoration: " + alternate);
      const suffix = "\x1b8X\tY\x1b[?6l\x1b[48;5;23m\x1b[2K\r\nAFTER" +
        (alternate ? "\x1b[?1049l\x1b8NORMAL_AFTER_ALT" : "");
      await Promise.all([write(original, suffix), write(restored, suffix)]);
      check(view(original) === view(restored), "continuation differs after restored native modes: " + alternate);
      const before = view(restored);
      let refused = false;
      try { await cache.restore(restored, { ...saved, cursor: saved.cursor + 1 }); } catch { refused = true; }
      check(refused && view(restored) === before, "corrupt identity must fail before touching the terminal");
    }

    const stream = terminal(), id = "probe-fragments";
    cleanup.add(id);
    await write(stream, new TextEncoder().encode("SAFE"));
    await cache.save(id, "windows", "engineer", 4, stream);
    await write(stream, new Uint8Array([0xf0, 0x9f]));
    check(!await cache.save(id, "windows", "engineer", 6, stream), "partial UTF-8 was checkpointed");
    check(cache.read(id, "windows", "engineer").cursor === 4, "partial UTF-8 advanced persisted cursor");
    await write(stream, new Uint8Array([0xa7, 0xa9]));
    check(await cache.save(id, "windows", "engineer", 8, stream), "complete UTF-8 could not be saved");
    await write(stream, "\x1b[3");
    check(!await cache.save(id, "windows", "engineer", 11, stream), "partial escape sequence was checkpointed");
    await write(stream, "1mCOMPLETE");
    check(await cache.save(id, "windows", "engineer", 21, stream), "complete escape sequence could not be saved");
    let release;
    stream.parser.registerOscHandler(777, () => new Promise((resolve) => { release = resolve; }));
    const held = write(stream, "\x1b]777;held\x07LATER");
    const deadline = Date.now() + 2000;
    while (!release && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 1));
    check(release, "the asynchronous parser control did not begin");
    check(!await cache.save(id, "windows", "engineer", 40, stream), "an unfinished parser callback was checkpointed");
    release(true);
    await held;

    for (const phase of ["hash", "transaction"]) {
      const invalidated = "probe-invalidated-" + phase;
      cleanup.add(invalidated);
      await cache.save(invalidated, "windows", "engineer", 100, stream);
      let pendingSave, removal, releaseHash;
      const nativeDigest = crypto.subtle.digest, nativeRead = IDBObjectStore.prototype.getAll;
      try {
        if (phase === "hash") {
          crypto.subtle.digest = function (...args) {
            const computed = nativeDigest.apply(this, args);
            return new Promise((resolve) => { releaseHash = () => resolve(computed); });
          };
          pendingSave = cache.save(invalidated, "windows", "engineer", 500, stream);
          check(releaseHash, "save did not reach the delayed hash");
          await cache.remove(invalidated, "windows", "engineer");
          releaseHash();
        } else {
          let armed = true;
          IDBObjectStore.prototype.getAll = function (...args) {
            const request = nativeRead.apply(this, args);
            if (armed && this.transaction.mode === "readwrite") {
              armed = false;
              // Run before the cache's write callback, while the real transaction is active.
              request.addEventListener("success", () => {
                removal = cache.remove(invalidated, "windows", "engineer");
              }, { once: true });
            }
            return request;
          };
          pendingSave = cache.save(invalidated, "windows", "engineer", 500, stream);
        }
        const accepted = await pendingSave;
        await removal;
        check(!cache.read(invalidated, "windows", "engineer") &&
          !(await rows()).some((row) => row.runId === invalidated),
          "an invalidated screen reappeared after " + phase);
        check(!accepted, "an invalidated save was accepted after " + phase);
      } finally {
        crypto.subtle.digest = nativeDigest;
        IDBObjectStore.prototype.getAll = nativeRead;
        releaseHash?.();
        await pendingSave;
        await removal;
      }
      check(await cache.save(invalidated, "windows", "engineer", 10, stream),
        "invalidation prevented a fresh screen at its reset cursor after " + phase);
    }

    const peer = await import("/terminal-cache.js?peer");
    const race = "probe-race";
    cleanup.add(race);
    await Promise.all([cache.save(race, "windows", "engineer", 200, stream),
      peer.save(race, "windows", "engineer", 100, stream)]);
    check((await rows()).find((row) => row.runId === race && row.kind === "screen").cursor === 200,
      "another tab rolled the persisted cursor backwards");
    await cache.save(race, "wsl", "engineer", 300, stream);
    await cache.save(race, "windows", "architect", 400, stream);
    check((await rows()).filter((row) => row.runId === race && row.kind === "screen").length === 3,
      "host or role identity collided");
    const late = peer.save(race, "windows", "engineer", 500, stream);
    await cache.close(race);
    await late;
    check(!(await rows()).some((row) => row.runId === race && row.kind === "screen"),
      "a pending write recreated a closed run's cache");

    for (let n = 0; n <= cache.LIMITS.screens; n++) {
      const run = "probe-bound-" + n;
      cleanup.add(run);
      await cache.save(run, "windows", "engineer", n + 1, stream);
    }
    const stored = (await rows()).filter((row) => row.kind === "screen");
    check(stored.length <= cache.LIMITS.screens && stored.reduce((n, row) => n + row.bytes, 0) <= cache.LIMITS.bytes,
      "persistent screen retention exceeded its global bounds");
    check(!stored.some((row) => row.runId === "probe-bound-0"), "old screen was not evicted under pressure");
    for (const run of cleanup) await cache.close(run);

    const dense = terminal();
    dense.options.scrollback = 2500;
    await write(dense, ("\x1b[31mA\x1b[32mB".repeat(79) + "\x1b[0m\r\n").repeat(2000));
    cleanup.add("probe-byte-0");
    check(await cache.save("probe-byte-0", "windows", "engineer", 1, dense), "dense native screen could not be cached");
    const size = cache.read("probe-byte-0", "windows", "engineer").bytes;
    check(size > cache.LIMITS.bytes / cache.LIMITS.screens, "byte-pressure fixture cannot distinguish the byte bound");
    const copies = Math.floor(cache.LIMITS.bytes / size) + 1;
    for (let n = 1; n < copies; n++) {
      const run = "probe-byte-" + n;
      cleanup.add(run);
      check(await cache.save(run, "windows", "engineer", n + 1, dense), "dense screen save failed");
    }
    const bounded = (await rows()).filter((row) => row.kind === "screen");
    check(bounded.length < copies && bounded.reduce((n, row) => n + row.bytes, 0) <= cache.LIMITS.bytes,
      "byte pressure retained too much even below the screen-count bound");

    const quota = await import("/terminal-cache.js?quota");
    const beforeQuota = JSON.stringify((await rows()).map((row) => [row.id, row.cursor]).sort());
    const nativePut = IDBObjectStore.prototype.put;
    try {
      IDBObjectStore.prototype.put = function () { throw new DOMException("disposable quota refusal", "QuotaExceededError"); };
      check(!await quota.save("probe-quota", "windows", "engineer", 999, stream) && quota.issue(),
        "quota refusal must remain observable and disable persistence");
    } finally { IDBObjectStore.prototype.put = nativePut; }
    check(JSON.stringify((await rows()).map((row) => [row.id, row.cursor]).sort()) === beforeQuota,
      "a refused cache transaction changed earlier snapshots");

    const nativeStorage = window.indexedDB;
    try {
      Object.defineProperty(window, "indexedDB", { configurable: true,
        value: { open() { throw new DOMException("disposable denial", "SecurityError"); } } });
      const denied = await import("/terminal-cache.js?denied");
      check(denied.issue() && denied.read("any", "windows", "engineer") === null,
        "storage denial must be observable without breaking the page");
      Object.defineProperty(window, "indexedDB", { configurable: true, value: { open() { return {}; } } });
      const hung = await Promise.race([import("/terminal-cache.js?hung"), new Promise((_, reject) =>
        setTimeout(() => reject(new Error("a hung storage open blocked page startup")), 10000))]);
      check(hung.issue(), "an unreadable cache was reported ready");
    } finally {
      Object.defineProperty(window, "indexedDB", { configurable: true, value: nativeStorage });
    }
    return true;
  } finally {
    for (const run of cleanup) await cache.close(run);
    for (const [term, node] of terms) { term.dispose(); node.remove(); }
    await cache.flush();
  }
}
