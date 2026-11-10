// Pi owns settlement and the session; this extension only records evidence for the controller.
import fs from "node:fs";
import path from "node:path";
import { VERSION } from "@earendil-works/pi-coding-agent";

export default function (pi) {
  // Older settlement events cannot distinguish an abort during tools or the final boundary from success.
  const version = /^(\d+)\.(\d+)\.(\d+)(?:\+[\w.-]+)?$/.exec(VERSION);
  if (!version || Number(version[1]) < 1 || (Number(version[1]) === 1 && Number(version[2]) < 1)) {
    process.stderr.write("Orchestra requires Pi 1.1.0 or newer for reliable aborted-settlement reporting\n");
    process.exit(1);
  }
  let last = null;
  const promptFile = process.env.ORCHESTRA_PI_PROMPT_FILE;
  const inputToken = process.env.ORCHESTRA_PI_INPUT_TOKEN;
  let controllerPrompt = null;
  let awaitingController = Boolean(inputToken);
  try {
    if (Boolean(promptFile) !== Boolean(inputToken)) throw new Error("incomplete prompt transport");
    if (promptFile) {
      if (!fs.lstatSync(promptFile).isFile()) throw new Error("not a prompt file");
      controllerPrompt = fs.readFileSync(promptFile, "utf8");
      if (!controllerPrompt.trim()) throw new Error("empty prompt");
    }
  } catch {
    process.stderr.write("Pi could not load the controller prompt before work\n");
    process.exit(1);
  }
  pi.registerFlag("orchestra-resume-session", {type: "string", description: "The exact session the controller resumes"});
  function emit(hook, ctx, fields = {}) {
    const file = process.env.ORCHESTRA_TURN_EVENTS;
    if (!file) return;
    const payload = {_hook: hook, _at: Date.now() / 1000,
      session_id: ctx.sessionManager.getSessionId(), session_file: ctx.sessionManager.getSessionFile(), ...fields};
    try {
      fs.appendFileSync(file, JSON.stringify(payload) + "\n", {encoding: "utf8", mode: 0o600});
    } catch {
      process.stderr.write("Pi could not record the controller's turn event\n");
      process.exit(1);
    }
  }
  pi.on("session_start", (_event, ctx) => {
    const expected = pi.getFlag("orchestra-resume-session");
    if (!expected) return;
    try {
      if (!fs.statSync(expected).isFile()) throw new Error("not a file");
    } catch (error) {
      process.stderr.write(error.code === "ENOENT" ? "Pi session not found before work\n"
        : "Pi cannot validate the exact session before work\n");
      process.exit(1);
    }
    try {
      const fd = fs.openSync(expected, "r");
      let head;
      try {
        const data = Buffer.alloc(8192);
        const count = fs.readSync(fd, data, 0, data.length, 0);
        head = JSON.parse(data.subarray(0, count).toString("utf8").split("\n")[0]);
      } finally { fs.closeSync(fd); }
      if (head.type !== "session" || head.id !== ctx.sessionManager.getSessionId()
          || path.resolve(expected) !== path.resolve(ctx.sessionManager.getSessionFile())) throw new Error("session");
      // Pi initializes an empty explicit file; that cannot resume a conversation Orchestra already completed.
      if (!ctx.sessionManager.getEntries().some(entry => entry.type === "message" && entry.message?.role === "assistant"))
        throw new Error("empty conversation");
    } catch {
      process.stderr.write("Pi cannot validate the exact session before work\n");
      process.exit(1);
    }
  });
  pi.on("input", (event, ctx) => {
    let text = event.text;
    if (awaitingController) {
      if (text !== inputToken) {
        process.stderr.write("Pi did not receive the controller input token before work\n");
        process.exit(1);
      }
      awaitingController = false;
      text = controllerPrompt;
    }
    last = null;
    emit("PiInput", ctx, {prompt: text, source: event.source});
    if (text !== event.text) return {action: "transform", text};
  });
  pi.on("message_end", (event, ctx) => {
    if (event.message.role !== "assistant") return;
    last = event.message;
    const answer = (last.content || []).filter(part => part.type === "text").map(part => part.text).join("\n");
    emit("PiGeneration", ctx, {answer, provider: last.provider, model: last.model, api: last.api,
      request_timestamp_ms: last.timestamp, response_id: last.responseId, response_model: last.responseModel,
      usage: last.usage, stop_reason: last.stopReason});
  });
  pi.on("agent_settled", (event, ctx) => {
    if (event.aborted === true || last?.stopReason === "aborted") {
      emit("PiInterrupted", ctx);
      return;
    }
    const answer = (last?.content || []).filter(part => part.type === "text").map(part => part.text).join("\n");
    emit("PiSettled", ctx, {ok: event.aborted === false && last?.stopReason === "stop",
      answer: answer || last?.errorMessage || "", stop_reason: last?.stopReason});
  });
}
