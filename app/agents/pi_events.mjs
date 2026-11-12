// Pi owns settlement and the session; this extension delivers the controller contract and records evidence.
import fs from "node:fs";
import path from "node:path";
import { VERSION } from "@earendil-works/pi-coding-agent";

export default function (pi) {
  // The native structured system-prompt projection is part of the turn contract.
  const version = /^(\d+)\.(\d+)\.(\d+)(?:\+[\w.-]+)?$/.exec(VERSION);
  if (!version || Number(version[1]) < 1 || (Number(version[1]) === 1 && Number(version[2]) < 5)) {
    process.stderr.write("Orchestra requires Pi 1.5.0 or newer for the native turn-contract system section\n");
    process.exit(1);
  }
  let last = null;
  const promptFile = process.env.ORCHESTRA_PI_PROMPT_FILE;
  const inputToken = process.env.ORCHESTRA_PI_INPUT_TOKEN;
  const partsFile = process.env.ORCHESTRA_PI_PARTS_FILE;
  let controllerPrompt = null;
  let contract = null;
  let requestParts = [];
  let awaitingController = Boolean(inputToken);
  try {
    if (Boolean(promptFile) !== Boolean(inputToken) || Boolean(promptFile) !== Boolean(partsFile))
      throw new Error("incomplete prompt transport");
    if (promptFile) {
      if (!fs.lstatSync(promptFile).isFile()) throw new Error("not a prompt file");
      controllerPrompt = fs.readFileSync(promptFile, "utf8");
      if (!controllerPrompt.trim()) throw new Error("empty prompt");
      if (!fs.lstatSync(partsFile).isFile()) throw new Error("not a parts file");
      const parts = JSON.parse(fs.readFileSync(partsFile, "utf8"));
      if (!Array.isArray(parts) || parts.some(part => !part || typeof part.part !== "string"
        || typeof part.text !== "string") || parts.map(part => part.text).join("\n") + "\n" !== controllerPrompt)
        throw new Error("mismatched prompt parts");
      for (const name of ["task", "persona", "instructions"]) {
        const matches = parts.filter(part => part.part === name);
        if (matches.length !== 1 || !matches[0].text.trim()) throw new Error("missing turn contract");
      }
      const systemParts = ["skill", "authority", "persona", "instructions", "recheck", "reflection", "handoff"];
      contract = "Use this current Orchestra contract rather than an earlier stage. If context is missing after "
        + "compaction, re-read the full controller prompt and its referenced instructions: " + promptFile + "\n\n"
        + parts.filter(part => systemParts.includes(part.part))
          .map(part => part.text).join("\n");
      requestParts = parts.filter(part => !systemParts.includes(part.part)).map(part => part.text);
    }
  } catch {
    process.stderr.write("Pi could not load the controller prompt and matching turn contract before work\n");
    process.exit(1);
  }
  pi.on("before_agent_start", event => {
    if (!contract) return;
    if (!event.systemPromptOptions?.sections) {
      process.stderr.write("Pi cannot project the controller contract into its native system prompt before work\n");
      process.exit(1);
    }
    event.systemPromptOptions.sections.orchestra_turn = contract;
  });
  pi.on("context", event => {
    if (!requestParts.length) return;
    const messages = event.messages.filter(message => message.role !== "custom"
      || message.customType !== "orchestra_request_context");
    const userText = messages.filter(message => message.role === "user").map(message =>
      typeof message.content === "string" ? message.content : message.content
        .filter(block => block.type === "text").map(block => block.text).join("\n")).join("\n");
    const missing = requestParts.filter(text => !userText.includes(text));
    if (!missing.length) return {messages};
    // Request-only context survives compaction without putting free-form evidence in the system prompt.
    return {messages: [{role: "custom", customType: "orchestra_request_context", display: false,
      content: missing.join("\n"), timestamp: 0}, ...messages]};
  });
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
