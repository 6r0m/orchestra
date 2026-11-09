// Pi owns settlement and the session; this extension only records evidence for the controller.
import fs from "node:fs";
import path from "node:path";

export default function (pi) {
  let last = null;
  let outcome = "completed";
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
    last = null;
    outcome = "completed";
    emit("PiInput", ctx, {prompt: event.text, source: event.source});
  });
  pi.on("message_end", (event, ctx) => {
    if (event.message.role !== "assistant") return;
    last = event.message;
    const answer = (last.content || []).filter(part => part.type === "text").map(part => part.text).join("\n");
    emit("PiGeneration", ctx, {answer, provider: last.provider, model: last.model, api: last.api,
      usage: last.usage, stop_reason: last.stopReason});
  });
  pi.on("agent_before_settle", (event) => { outcome = event.outcome; });
  pi.on("agent_settled", (_event, ctx) => {
    if (outcome === "aborted" || last?.stopReason === "aborted") {
      emit("PiInterrupted", ctx);
      return;
    }
    const answer = (last?.content || []).filter(part => part.type === "text").map(part => part.text).join("\n");
    emit("PiSettled", ctx, {ok: Boolean(last) && outcome !== "error" && !["error", "length"].includes(last.stopReason),
      answer: answer || last?.errorMessage || "", stop_reason: last?.stopReason});
  });
}
