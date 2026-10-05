// Browser-only logic. No proxy, credentials, persistent storage, or server state.
export function normalizeEndpoint(value) {
  let url;
  try { url = new URL(value.trim()); } catch { throw new Error("Enter a complete Ollama address, such as http://localhost:11434."); }
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password ||
      url.search || url.hash || !["", "/"].includes(url.pathname)) {
    throw new Error("Use an HTTP or HTTPS server address without a username, password, path, query, or fragment.");
  }
  return url.origin;
}

export function validateDecision(value, schema, history = []) {
  function check(item, rule) {
    if (rule.anyOf) {
      if (!rule.anyOf.some(option => { try { check(item, option); return true; } catch { return false; } })) throw new Error("Invalid response field.");
      return;
    }
    const type = rule.type;
    if (type === "null" && item !== null || type === "string" && typeof item !== "string" ||
        type === "boolean" && typeof item !== "boolean" || type === "integer" && !Number.isInteger(item) ||
        type === "array" && !Array.isArray(item) ||
        type === "object" && (item === null || typeof item !== "object" || Array.isArray(item))) throw new Error("Invalid response field.");
    if (rule.enum && !rule.enum.includes(item)) throw new Error("Invalid response choice.");
    if (typeof item === "string" && (item.trim().length < (rule.minLength ?? 0) || item.length > (rule.maxLength ?? Infinity))) throw new Error("Invalid response length.");
    if (type === "array") {
      if (item.length > (rule.maxItems ?? Infinity)) throw new Error("Too many response items.");
      item.forEach(entry => check(entry, rule.items));
    }
    if (type === "object") {
      for (const key of rule.required ?? []) if (!(key in item)) throw new Error("Missing response field.");
      for (const [key, entry] of Object.entries(item)) {
        if (!rule.properties[key]) {
          if (rule.additionalProperties === false) throw new Error("Unexpected response field.");
        } else check(entry, rule.properties[key]);
      }
    }
  }
  check(value, schema);
  const decision = Object.fromEntries(Object.entries(value).map(([key, entry]) => [key, typeof entry === "string" ? entry.trim() : entry]));
  decision.warning ??= null;
  if (!decision.assessment && decision.next_move !== "out_of_scope") throw new Error("Missing assessment.");
  if (decision.next_move === "ask" && (!decision.missing_information.length || !decision.step.includes("?"))) throw new Error("Missing context question.");
  if (decision.next_move === "refer" && !decision.warning) throw new Error("Missing referral warning.");
  if (decision.next_move === "explain") {
    const last = history.at(-1);
    if (!last || last.step.kind !== "action" || decision.action_id !== last.action_id) throw new Error("Invalid explanation reference.");
  } else if (decision.action_id !== null) throw new Error("Invalid action reference.");
  decision.kind = ["ask", "refer"].includes(decision.next_move) ? "question" :
    ["answer", "out_of_scope"].includes(decision.next_move) ? "answer" : "action";
  if (decision.next_move === "out_of_scope") {
    decision.summary = "Ask me about technology";
    decision.step = "I can help with programming, software, hardware, devices, and networking. What technology question can I help with?";
    decision.warning = null;
    decision.requires_terminal = false;
  }
  const normalized = text => text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  if (history.some(attempt => attempt.result === "failed" && normalized(attempt.step.step) === normalized(decision.step))) throw new Error("Repeated failed action.");
  if ((decision.step.match(/```/g) ?? []).length % 2) decision.step += "\n```";
  return decision;
}

export function safetyResponse(problem, history) {
  const pattern = /\b(lake|submerged|soaked|water damage|liquid damage|liquid detected)\b|\b(?:dropped|fell|fall|spilled|spill)\b.{0,80}\b(?:water|lake|pool|sea|ocean|toilet|bath|bathtub|coffee|tea|juice|liquid)\b|\b(?:water|liquid|coffee)\b.{0,60}\b(?:spilled|spill|inside|into|on my)\b|\b(?:mac|laptop|computer|phone|device|keyboard)\b.{0,40}\b(?:wet|soaked)\b/i;
  if (![problem, ...history.map(attempt => attempt.observation)].some(text => pattern.test(text ?? ""))) return null;
  const warned = history.some(attempt => attempt.step.summary === "Keep the liquid-damaged device unpowered");
  return {
    assessment: "Liquid inside a device can cause damage even when the outside looks dry. A repair assessment is the safest next step.",
    summary: warned ? "This needs a repair assessment" : "Keep the liquid-damaged device unpowered",
    step: warned ? "It may still be repairable. Tell a repair shop: ‘My device got wet. Can you check for liquid damage and explain my repair options? Please ask before erasing anything—I may need my files.’ Tell them when it happened and whether you've turned it on or charged it since. Have you found a repair shop to contact?" : "Do not turn the device on or plug it in to test it. If connected to power, disconnect the charger only if you can do so safely with dry hands, without touching wet electrical equipment. If it's already off, leave it off. Is it still connected to power?",
    why: "Looking dry does not establish that internal parts are electrically safe. Ordinary software troubleshooting cannot check liquid damage.",
    warning: "Do not power on or charge it to test it, use heat or rice, or open it yourself. If it is hot, smoking, or sparking, do not handle it; move away and seek emergency help.",
    kind: "question", next_move: "refer", action_id: null, difficulty: "easy", requires_terminal: false,
  };
}

export function buildMessages(contract, task, experience, mode) {
  const instruction = {
    initial: "Give the first safe action or one necessary clarifying question.",
    next: "Give the NEXT action. Do not repeat any failed action.",
    simplify: "Use the latest observation to explain an available action, ask for missing context, change a blocked approach, or refer. Preserve warnings. Do not repeat unclear advice.",
    replan: "Use the latest answer or follow-up to choose an appropriate next move. Do not treat an answer to a question as a failed action.",
  }[mode];
  const messages = [{role: "system", content: contract.system}, {role: "user", content: JSON.stringify({
    profile: {id: 0, name: "", operating_system: "Not specified", computer: "Not specified", phone: "Not specified", technical_level: experience,
      preferences: experience === "Beginner" ? "Please avoid command-line instructions unless necessary." : ""},
    current_problem: task.problem, previous_successful_fixes: [],
  })}];
  for (const attempt of task.attempts) {
    messages.push({role: "assistant", content: JSON.stringify({...attempt.step, stored_action_id: attempt.action_id})});
    const feedback = {failed: "Still broken", unclear: "I don't understand", reply: "Answer or follow-up", pending: "Awaiting feedback"}[attempt.result];
    messages.push({role: "user", content: JSON.stringify({feedback, what_happened: attempt.observation})});
  }
  messages.push({role: "user", content: JSON.stringify({request: instruction,
    latest_observation: task.attempts.at(-1)?.observation ?? "", response_schema: contract.schema})});
  return messages;
}

export function sampleResponse(history, mode) {
  const common = {assessment: "Let's narrow this down one step at a time.", why: "This is a fictional example of Call Mac's troubleshooting flow.", warning: null, requires_terminal: false, difficulty: "easy", action_id: null};
  if (!history.length) return {...common, summary: "Which computer are you printing from?", step: "Are you using Windows or a Mac? For this sample, we'll walk through a Windows 11 printer problem.", kind: "question", next_move: "ask"};
  if (mode === "simplify" && history.at(-1).step.kind === "action") return {...common, summary: "Let's find the setting together", step: "Click the Start button at the bottom of the screen, then type ‘Printers & scanners’ into search. Open the matching settings result and click your printer. Can you see ‘Open print queue’ there?", kind: "question", next_move: "ask"};
  if (history.some(attempt => attempt.result === "failed")) return {...common, summary: "Restart the printer", step: "If the printer is idle, turn it off with its power button, wait 30 seconds, then turn it back on. Wait until it is ready, then try printing a test page. What happened?", warning: "Wait for any current print job to finish before restarting the printer.", kind: "action", next_move: "change_approach"};
  return {...common, assessment: "In this Windows 11 example, an offline queue setting can stop an otherwise connected printer.", summary: "Check the printer queue", step: "Open Start → Settings → Bluetooth & devices → Printers & scanners. Choose your printer and open its print queue. If ‘Use Printer Offline’ is checked in the queue's Printer menu, uncheck it. Try a test page and tell me what happens.", kind: "action", next_move: "instruct"};
}

export async function ollamaRequest(endpoint, path, {payload, signal, timeout = 12000} = {}) {
  const controller = new AbortController();
  const forwardAbort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener("abort", forwardAbort, {once: true});
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeout);
  try {
    const options = {
      method: payload ? "POST" : "GET", headers: payload ? {"Content-Type": "application/json"} : {},
      body: payload ? JSON.stringify(payload) : undefined,
      signal: controller.signal, credentials: "omit", redirect: "error", referrerPolicy: "no-referrer",
    };
    let response = await fetch(endpoint + path, options);
    if (response.status === 400 && payload && typeof payload.format === "object") {
      const detail = await response.clone().text();
      if (/grammar/i.test(detail)) {
        response = await fetch(endpoint + path, {...options, body: JSON.stringify({...payload, format: "json"})});
      }
    }
    if (!response.ok) {
      if (response.status === 404) throw new Error("The model or API route isn't available. Refresh the connection and check that the selected model is installed.");
      throw new Error(`Ollama returned HTTP ${response.status}. Check its available memory and server logs.`);
    }
    return await response.json();
  } catch (error) {
    if (timedOut) throw new Error("Ollama took too long. It may still be loading the model. Check that it is running and try again.");
    if (signal?.aborted) throw new Error("Request stopped. You can retry without losing this conversation.");
    if (error instanceof TypeError) throw new Error("Couldn't reach Ollama. Check its address, OLLAMA_ORIGINS, and your browser's local-network permission. For remote servers, check HTTPS and connectivity. Open ‘Connect your Ollama’ for help.");
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", forwardAbort);
  }
}
