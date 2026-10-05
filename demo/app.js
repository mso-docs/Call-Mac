import {normalizeEndpoint, validateDecision, safetyResponse, buildMessages, sampleResponse, ollamaRequest} from "./core.js";

const $ = id => document.getElementById(id);
let contract, connection = null, sample = false, task = null, busy = false, controller = null, pendingMode = null;
const origin = location.origin;
const mobile = matchMedia("(max-width: 620px)");
const updateWorkspace = () => { $("workspace").open = !mobile.matches; };
mobile.addEventListener("change", updateWorkspace);
updateWorkspace();
$("site-origin").textContent = origin;
$("origin-command").textContent = `OLLAMA_ORIGINS="${origin}" ollama serve`;

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = !message;
}

function renderText(container, text) {
  // Never interpret model/user output as HTML. Render fenced code as plain text.
  const pieces = text.split(/```[^\n]*\n([\s\S]*?)```/g);
  pieces.forEach((piece, index) => {
    if (!piece.trim()) return;
    const element = document.createElement(index % 2 ? "pre" : "p");
    element.textContent = piece;
    container.append(element);
  });
}

function message(role, text, step) {
  const card = document.createElement("article");
  card.className = `message ${role}`;
  const speaker = document.createElement("div");
  speaker.className = "speaker";
  speaker.textContent = role === "user" ? "You" : sample ? "Call Mac · Sample reply" : "Call Mac";
  card.append(speaker);
  if (!step) renderText(card, text);
  else {
    if (step.assessment) {
      const assessment = document.createElement("p");
      assessment.className = "assessment";
      assessment.textContent = step.assessment;
      card.append(assessment);
    }
    const title = document.createElement("h3");
    title.textContent = step.summary;
    card.append(title);
    renderText(card, step.step);
    if (step.warning) {
      const warning = document.createElement("p");
      warning.className = "warning";
      warning.textContent = step.warning;
      card.append(warning);
    }
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Why am I doing this?";
    details.append(summary);
    renderText(details, step.why);
    card.append(details);
  }
  $("conversation").append(card);
}

function updateControls() {
  document.querySelectorAll("input, textarea, select, button").forEach(element => {
    element.disabled = busy && element.id !== "cancel";
  });
  $("model").disabled = busy || !connection || sample;
  $("problem-form").hidden = !!task;
  $("welcome").hidden = !!task;
  $("feedback-form").hidden = !task || task.solved || !task.attempts.length || !!pendingMode;
  $("retry").hidden = !pendingMode || busy;
  $("working").hidden = !busy;
  $("sample-notice").hidden = !sample;
  $("mode-label").textContent = sample ? "FICTIONAL SAMPLE WALKTHROUGH" : "BRING YOUR OWN OLLAMA";
  const last = task?.attempts.at(-1)?.step;
  const isAction = last?.kind === "action";
  $("action-buttons").hidden = !isAction;
  $("reply").hidden = isAction;
  $("observation").required = !isAction;
  $("observation-label").textContent = isAction ? "What happened? (optional)" : "Your reply or follow-up";
}

function resetTask() {
  task = null;
  pendingMode = null;
  $("conversation").replaceChildren();
  $("observation").value = "";
  $("problem").value = "";
  showError("");
  updateControls();
}

async function generate(mode) {
  pendingMode = mode;
  busy = true;
  controller = new AbortController();
  showError("");
  updateControls();
  try {
    if (task.attempts.length >= 24) throw new Error("This task has reached the demo's conversation limit. Start a new help task to continue.");
    let step = safetyResponse(task.problem, task.attempts);
    if (!step && sample) step = sampleResponse(task.attempts, mode);
    if (!step) {
      if (!connection) throw new Error("Connect to Ollama first, or choose the sample walkthrough.");
      if (!contract) throw new Error("The demo couldn't load its response instructions. Reload the page and try again.");
      const messages = buildMessages(contract, task, $("experience").value, mode);
      for (let attempt = 0; attempt < 2; attempt++) {
        const data = await ollamaRequest(connection.endpoint, "/api/chat", {
          signal: controller.signal, timeout: 180000,
          payload: {model: $("model").value, messages, stream: false, format: contract.schema,
            options: {temperature: 0.2, num_predict: 1200}},
        });
        try {
          if (typeof data?.message?.content !== "string") throw new Error("Missing model response.");
          const content = data.message.content.trim().replace(/^```(?:json)?\s*\n?/, "").replace(/\s*```$/, "");
          step = validateDecision(JSON.parse(content), contract.schema, task.attempts);
          if (mode === "simplify" && step.next_move === "instruct") throw new Error("Choose explain, ask, change_approach, or refer for an unclear action.");
          const previous = task.attempts.at(-1)?.step;
          if (mode === "simplify" && previous?.warning) step.warning = previous.warning;
          break;
        } catch {
          if (attempt === 1) throw new Error("The model couldn't produce a valid, contextual reply. Try again or select a larger Gemma model.");
          messages.push({role: "user", content: "Return valid JSON matching every schema field, including assessment and a valid next_move/action_id. Do not repeat failed advice. For unclear actions choose explain, ask, change_approach, or refer."});
        }
      }
    }
    task.attempts.push({step, action_id: step.action_id ?? task.attempts.length + 1, result: "pending", observation: ""});
    pendingMode = null;
    message("assistant", "", step);
    $("observation").value = "";
  } catch (error) {
    showError(error.message);
  } finally {
    busy = false;
    controller = null;
    updateControls();
  }
}

async function begin(problem) {
  if (busy) return;
  if (!connection && !sample) {
    showError("Connect to your Ollama in the workspace, or choose ‘Try a sample walkthrough’.");
    $("setup").open = true;
    $("workspace").open = true;
    $("endpoint").focus();
    return;
  }
  task = {problem, attempts: [], solved: false};
  message("user", problem);
  await generate("initial");
}

$("connection-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (busy) return;
  busy = true;
  controller = new AbortController();
  showError("");
  updateControls();
  try {
    const endpoint = normalizeEndpoint($("endpoint").value);
    const data = await ollamaRequest(endpoint, "/api/tags", {signal: controller.signal});
    if (!Array.isArray(data.models)) throw new Error("Ollama returned an unreadable model list.");
    const models = [...new Set(data.models.map(item => item?.name).filter(name => typeof name === "string" && /^gemma/i.test(name)))].sort();
    if (!models.length) throw new Error("No Gemma models found. Run ‘ollama pull gemma3:4b’ on that server, then reconnect.");
    connection = {endpoint};
    sample = false;
    $("model").replaceChildren(...models.map(name => new Option(name, name)));
    if (models.includes("gemma3:4b")) $("model").value = "gemma3:4b";
    $("connection-status").textContent = "Connected · Requests go directly to your selected Ollama server.";
    $("connection-status").dataset.state = "ready";
    resetTask();
  } catch (error) {
    connection = null;
    $("connection-status").textContent = "Ollama is not connected.";
    $("connection-status").dataset.state = "";
    showError(error.message);
    $("setup").open = true;
  } finally {
    busy = false;
    controller = null;
    updateControls();
  }
});

$("endpoint").addEventListener("input", () => {
  connection = null;
  $("connection-status").textContent = "Address changed. Connect to confirm it.";
  $("connection-status").dataset.state = "";
  updateControls();
});
function startSample() {
  sample = true;
  resetTask();
  begin("My printer says offline even though it's turned on.");
  if (mobile.matches) { $("workspace").open = false; $("sample-notice").scrollIntoView({behavior: "smooth", block: "start"}); }
}
$("sample").addEventListener("click", startSample);
$("sample-start").addEventListener("click", startSample);
$("setup-link").addEventListener("click", () => { $("workspace").open = true; $("setup").open = true; });
$("new-task").addEventListener("click", () => {
  resetTask();
  if (sample) begin("My printer says offline even though it's turned on.");
});
$("cancel").addEventListener("click", () => controller?.abort());
$("retry").addEventListener("click", () => { if (pendingMode) generate(pendingMode); });
$("problem-form").addEventListener("submit", event => {
  event.preventDefault();
  const problem = $("problem").value.trim();
  if (problem) begin(problem);
});
document.querySelectorAll(".example").forEach(button => button.addEventListener("click", () => {
  $("problem").value = button.dataset.problem;
  $("problem").focus();
}));

async function feedback(result) {
  if (busy || !task || task.solved) return;
  const last = task.attempts.at(-1);
  const observation = $("observation").value.trim();
  if (!last || last.result !== "pending") return;
  if (result === "reply" && !observation) { $("observation").reportValidity(); return; }
  last.result = result;
  last.observation = observation;
  message("user", `${{fixed: "Fixed it", failed: "Still broken", unclear: "I don't understand", reply: "Reply"}[result]}${observation ? "\n\n" + observation : ""}`);
  if (result === "fixed") {
    task.solved = true;
    message("assistant", sample ? "That's the sample walkthrough! Connect your Ollama to try a real tech question, or start another sample task." : "Glad that helped! Start a new help task whenever you need a hand. This browser demo doesn't save fixes.");
    updateControls();
    return;
  }
  await generate(result === "failed" ? "next" : result === "unclear" ? "simplify" : "replan");
}
$("feedback-form").addEventListener("submit", event => { event.preventDefault(); feedback("reply"); });
document.querySelectorAll("[data-feedback]").forEach(button => button.addEventListener("click", () => feedback(button.dataset.feedback)));
$("copy-origin").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(origin); $("copy-origin").textContent = "Copied"; }
  catch { $("copy-origin").textContent = "Select the origin above to copy"; }
});

updateControls();
try {
  const response = await fetch("./contract.json", {credentials: "omit"});
  if (!response.ok) throw new Error("Contract unavailable.");
  contract = await response.json();
} catch { showError("Couldn't load the demo instructions. Reload the page. The sample walkthrough is still available."); }
