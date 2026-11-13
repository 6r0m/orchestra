// Disposable browser evidence. IndexedDB transactions coordinate tabs; workers still own every byte.
import { CONFIG } from "./api.js";

const FORMAT = "xterm-5.5.0/serialize-0.13.0/1";
const DATABASE = "orchestra-terminal-screens";
const OPEN_MS = 5000;
export const LIMITS = Object.freeze({ bytes: 32 * 1024 * 1024, frame: 8 * 1024 * 1024,
  screens: 24, closed: 256 });
const { bytes: BYTE_LIMIT, frame: FRAME_LIMIT, screens: SCREEN_LIMIT, closed: CLOSED_LIMIT } = LIMITS;
const frames = new Map();
const activeScreens = new Map();
const closed = new Set();
const serializers = new WeakMap();
const saving = new Set();
let failure = "";
let pending = Promise.resolve();

function report(error) {
  if (!failure) console.warn("Terminal refresh cache unavailable", error);
  failure = "refresh cache unavailable; reloading replays the recording";
}

const database = await new Promise((resolve) => {
  let finished = false;
  const timer = setTimeout(() => finish(null, new Error("browser storage did not become readable within " + OPEN_MS + "ms")), OPEN_MS);
  function finish(db, error) {
    if (finished) { db?.close(); return; }
    finished = true;
    clearTimeout(timer);
    if (error) report(error);
    resolve(db);
  }
  try {
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => request.result.createObjectStore("screens", { keyPath: "id" });
    request.onerror = () => finish(null, request.error);
    request.onblocked = () => finish(null, new Error("browser storage upgrade is blocked"));
    request.onsuccess = () => {
      const db = request.result;
      if (finished) { db.close(); return; }
      db.onversionchange = () => { db.close(); report(new Error("browser cache version changed")); };
      const transaction = db.transaction("screens", "readonly");
      const read = transaction.objectStore("screens").getAll();
      read.onsuccess = () => {
        for (const row of read.result) {
          if (row.kind === "closed") closed.add(row.runId);
          else if (valid(row)) frames.set(row.id, row);
        }
      };
      transaction.oncomplete = () => finish(db);
      transaction.onabort = () => finish(null, transaction.error);
    };
  } catch (error) { finish(null, error); }
});

function key(runId, target, role) { return JSON.stringify([runId, target, role]); }

function valid(row) {
  return row?.kind === "screen" && row.format === FORMAT &&
    typeof row.runId === "string" && typeof row.target === "string" &&
    ["engineer", "architect"].includes(row.role) && row.id === key(row.runId, row.target, row.role) &&
    Number.isSafeInteger(row.cursor) && row.cursor > 0 && row.cols === CONFIG.terminal_size.cols &&
    Number.isInteger(row.rows) && row.rows >= CONFIG.terminal_size.min_rows && row.rows <= CONFIG.terminal_size.max_rows &&
    typeof row.body === "string" && row.body.length <= FRAME_LIMIT &&
    Number.isSafeInteger(row.bytes) && row.bytes > 0 && row.bytes <= FRAME_LIMIT &&
    new TextEncoder().encode(row.body).length === row.bytes &&
    typeof row.digest === "string" && /^[0-9a-f]{64}$/.test(row.digest);
}

function change(edit) {
  const operation = pending.then(() => new Promise((resolve, reject) => {
    if (!database) { resolve(false); return; }
    try {
      const transaction = database.transaction("screens", "readwrite");
      const store = transaction.objectStore("screens");
      const request = store.getAll();
      let changed = true;
      request.onsuccess = () => { changed = edit(store, request.result) !== false; };
      transaction.oncomplete = () => resolve(changed);
      transaction.onabort = () => reject(transaction.error || new Error("browser cache write aborted"));
      transaction.onerror = () => {};
    } catch (error) { reject(error); }
  }));
  pending = operation.catch((error) => { report(error); return false; });
  return pending;
}

export const issue = () => failure;
export const runs = () => [...new Set([...frames.values()].map((row) => row.runId))];
export async function flush() {
  while (saving.size) await Promise.all([...saving]);
  return pending;
}

export function read(runId, target, role) {
  return closed.has(runId) ? null : frames.get(key(runId, target, role)) || null;
}

export function remove(runId, target, role) {
  const id = key(runId, target, role);
  const screen = activeScreens.get(id);
  if (screen) screen.generation++;
  frames.delete(id);
  return change((store) => store.delete(id));
}

export function close(runId) {
  if (closed.has(runId)) return pending;
  closed.add(runId);
  for (const [id, row] of frames) if (row.runId === runId) frames.delete(id);
  return change((store, rows) => {
    for (const row of rows) if (row.runId === runId) store.delete(row.id);
    const markers = rows.filter((row) => row.kind === "closed" && row.runId !== runId)
      .sort((a, b) => b.at - a.at);
    for (const row of markers.slice(CLOSED_LIMIT - 1)) store.delete(row.id);
    store.put({ id: JSON.stringify(["closed", runId]), kind: "closed", runId, at: Date.now() });
  });
}

function attributes(value) {
  return { fg: value.fg, bg: value.bg, ext: value.extended.ext, color: value.extended.underlineColor };
}

function setAttributes(target, value) {
  for (const field of ["fg", "bg", "ext", "color"]) if (!Number.isInteger(value[field]))
    throw new Error("invalid cached terminal attributes");
  target.fg = value.fg;
  target.bg = value.bg;
  target.extended.ext = value.ext;
  target.extended.underlineColor = value.color;
}

// The version-pinned addon omits parser fragments and some continuation state. Keep the native
// buffer/mode fields beside its VT output; never checkpoint halfway through an escape or UTF-8 codepoint.
function capture(term) {
  const core = term._core, input = core._inputHandler;
  if (input._parser.currentState !== 0 || input._parser._parseStack.state !== 0 ||
      input._utf8Decoder.interim[0] !== 0) return null;
  let addon = serializers.get(term);
  if (!addon) {
    addon = new SerializeAddon.SerializeAddon();
    term.loadAddon(addon);
    serializers.set(term, addon);
  }
  const buffers = {};
  for (const name of ["normal", "alt"]) {
    const buffer = core._bufferService.buffers[name];
    buffers[name] = { x: buffer.x, y: buffer.y, savedX: buffer.savedX, savedY: buffer.savedY,
      scrollTop: buffer.scrollTop, scrollBottom: buffer.scrollBottom, tabs: { ...buffer.tabs },
      savedCharset: buffer.savedCharset, attributes: attributes(buffer.savedCurAttrData) };
  }
  return { vt: addon.serialize({ scrollback: term.options.scrollback }), buffers,
    attributes: attributes(input._curAttrData), erase: attributes(input._eraseAttrDataInternal),
    charset: { level: core._charsetService.glevel, tables: core._charsetService._charsets },
    hidden: core.coreService.isCursorHidden, initialized: core.coreService.isCursorInitialized,
    modes: { ...core.coreService.modes }, privateModes: { ...core.coreService.decPrivateModes },
    mouse: [core.coreMouseService.activeProtocol, core.coreMouseService.activeEncoding],
    cursorStyle: term.options.cursorStyle, cursorBlink: term.options.cursorBlink };
}

async function digest(body) {
  const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(body));
  return Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function save(runId, target, role, cursor, term) {
  const id = key(runId, target, role);
  let screen = activeScreens.get(id);
  if (!screen) {
    screen = { generation: 0, count: 0 };
    activeScreens.set(id, screen);
  }
  screen.count++;
  const operation = saveScreen(runId, target, role, cursor, term, screen, screen.generation);
  saving.add(operation);
  operation.finally(() => {
    saving.delete(operation);
    // Other saves may still be hashing or waiting for the write transaction.
    if (--screen.count === 0) activeScreens.delete(id);
  });
  return operation;
}

async function saveScreen(runId, target, role, cursor, term, screen, generation) {
  if (!database || failure || closed.has(runId) || !cursor) return false;
  // A legacy page configuration cannot validate persisted geometry; its ordinary replay still works.
  if (!Number.isInteger(CONFIG.terminal_size.min_rows) || !Number.isInteger(CONFIG.terminal_size.max_rows)) return false;
  const id = key(runId, target, role);
  try {
    const snapshot = capture(term);
    if (!snapshot) return false;
    // Freeze the complete native state before hashing or waiting for another tab's transaction.
    const body = JSON.stringify({ format: FORMAT, runId, target, role, cursor, scrollback: term.options.scrollback,
      cols: term.cols, rows: term.rows, snapshot });
    const bytes = new TextEncoder().encode(body).length;
    if (bytes > FRAME_LIMIT) throw new Error("terminal screen exceeds the refresh-cache allowance");
    const row = { id: id, kind: "screen", format: FORMAT,
      runId, target, role, cursor, cols: term.cols, rows: term.rows, body,
      bytes, digest: await digest(body), at: Date.now() };
    if (closed.has(runId) || screen.generation !== generation) return false;
    frames.set(row.id, row);
    return await change((store, rows) => {
      if (closed.has(runId) || screen.generation !== generation) return false;
      if (rows.some((item) => item.kind === "closed" && item.runId === runId)) {
        closed.add(runId);
        for (const [id, frame] of frames) if (frame.runId === runId) frames.delete(id);
        return false;
      }
      const old = rows.find((item) => item.id === row.id);
      if (valid(old) && old.cursor > cursor) { frames.set(row.id, old); return false; }
      const others = rows.filter((item) => item.kind === "screen" && item.id !== row.id)
        .sort((a, b) => b.at - a.at);
      let total = bytes, count = 1;
      for (const item of others) {
        total += item.bytes || FRAME_LIMIT;
        if (!valid(item) || ++count > SCREEN_LIMIT || total > BYTE_LIMIT) {
          store.delete(item.id);
          frames.delete(item.id);
        }
      }
      store.put(row);
    });
  } catch (error) { report(error); return false; }
}

export async function restore(term, row) {
  if (!valid(row) || await digest(row.body) !== row.digest) throw new Error("terminal snapshot is corrupt or incompatible");
  const data = JSON.parse(row.body);
  for (const field of ["format", "runId", "target", "role", "cursor", "cols", "rows"])
    if (data[field] !== row[field]) throw new Error("terminal snapshot identity does not match");
  if (data.scrollback !== term.options.scrollback) throw new Error("terminal scrollback configuration changed");
  const state = data.snapshot;
  if (typeof state?.vt !== "string") throw new Error("terminal snapshot has no native screen");
  term.resize(row.cols, row.rows);
  await new Promise((resolve) => term.write(state.vt, resolve));
  const core = term._core, input = core._inputHandler;
  for (const name of ["normal", "alt"]) {
    const buffer = core._bufferService.buffers[name], saved = state.buffers[name];
    for (const field of ["x", "y", "savedX", "savedY", "scrollTop", "scrollBottom"]) {
      if (!Number.isInteger(saved[field]) || saved[field] < 0) throw new Error("invalid cached terminal position");
      buffer[field] = saved[field];
    }
    buffer.tabs = saved.tabs;
    buffer.savedCharset = saved.savedCharset;
    setAttributes(buffer.savedCurAttrData, saved.attributes);
  }
  setAttributes(input._curAttrData, state.attributes);
  setAttributes(input._eraseAttrDataInternal, state.erase);
  core._charsetService._charsets = state.charset.tables.map((table) => table ?? undefined);
  core._charsetService.setgLevel(state.charset.level);
  for (const [target, saved] of [[core.coreService.modes, state.modes],
    [core.coreService.decPrivateModes, state.privateModes]]) {
    for (const field of Object.keys(target)) {
      if (typeof saved[field] !== "boolean") throw new Error("invalid cached terminal mode");
      target[field] = saved[field];
    }
  }
  core.coreService.isCursorHidden = state.hidden;
  core.coreService.isCursorInitialized = state.initialized;
  [core.coreMouseService.activeProtocol, core.coreMouseService.activeEncoding] = state.mouse;
  term.options.cursorStyle = state.cursorStyle;
  term.options.cursorBlink = state.cursorBlink;
  term.refresh(0, term.rows - 1);
  term.scrollToBottom();
  return row.cursor;
}
