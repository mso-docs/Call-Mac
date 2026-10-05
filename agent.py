"""Direct Ollama API integration with configured server fallback with validated JSON output."""
import ipaddress
import json
import os
import re
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

import requests
from pydantic import ValidationError

from models import TroubleshootingStep, TroubleshootingDecision
from prompts import messages
from safety import safety_response, liquid_exposure, requests_secret, private_credentials_response

def load_env():
    """Load simple KEY=value entries without overriding the process environment."""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.removeprefix("export ").partition("=")
            if separator:
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_env()
MODEL = os.getenv("CALL_MAC_MODEL", "gemma3:4b")
OLLAMA_URL = os.getenv("CALL_MAC_OLLAMA_URL", os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")

SECONDARY_URL = os.getenv("OLLAMA_SECONDARY_URL", "").rstrip("/")
ACTIVE_URL = None


class AgentError(Exception):
    """A message safe to show in the UI."""


class ResponseError(AgentError):
    """A reachable server produced invalid guidance, rather than a connection failure."""
    def __init__(self, message, detail):
        super().__init__(message)
        self.detail = detail


def local_url(url=None):
    url = url or OLLAMA_URL
    parsed = urlparse(url)
    explicitly_configured = url in {
        os.getenv("CALL_MAC_OLLAMA_URL"), os.getenv("OLLAMA_BASE_URL"),
        os.getenv("OLLAMA_SECONDARY_URL"),
    }
    try:
        loopback = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        loopback = False
    if (not (loopback or explicitly_configured) or parsed.scheme not in {"http", "https"}
            or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment):
        raise AgentError("Use a local Ollama address or explicitly configure your server in .env.")
    return url


def inference_location():
    host = urlparse(ACTIVE_URL or OLLAMA_URL).hostname
    try:
        local = host == "localhost" or ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        local = False
    return "this computer" if local else "your configured Ollama server"


def request(path, payload=None, timeout=3, model=None):
    global ACTIVE_URL
    selected_model = model or (payload or {}).get("model", MODEL)
    candidates = list(dict.fromkeys(url for url in [ACTIVE_URL, OLLAMA_URL, SECONDARY_URL] if url))
    error = "Call Mac can't reach an Ollama server. Check that it is running and reachable."
    server_error = None
    for url in candidates:
        try:
            with requests.Session() as client:
                client.trust_env = False
                response = client.request("POST" if payload is not None else "GET", local_url(url) + path,
                                          json=payload, timeout=timeout, allow_redirects=False)
                # Some Ollama-compatible servers reject schema grammars. JSON mode
                # still uses the same response validation before anything is shown.
                if response.status_code == 400 and payload and isinstance(payload.get("format"), dict):
                    try:
                        grammar_error = "grammar" in json.dumps(response.json()).lower()
                    except ValueError:
                        grammar_error = False
                    if grammar_error:
                        json_payload = {**payload, "format": "json"}
                        response = client.request("POST", local_url(url) + path,
                                                  json=json_payload, timeout=timeout, allow_redirects=False)
            if response.status_code == 404:
                error = f"The model isn't available on the configured servers. Install it there with: ollama pull {selected_model}"
                server_error = error
                continue
            if not 200 <= response.status_code < 300:
                error = "Ollama couldn't complete this request. Check server memory and try again."
                server_error = error
                continue
            data = response.json()
            if path == "/api/tags" and model != "*":
                names = {item.get("name") for item in data.get("models", []) if isinstance(item, dict)}
                if selected_model not in names and f"{selected_model}:latest" not in names:
                    error = f"Download the model on an Ollama server first: ollama pull {selected_model}"
                    server_error = error
                    continue
            ACTIVE_URL = url
            return data
        except requests.ConnectTimeout:
            error = "Connection timed out. Check that the configured server is reachable."
        except requests.Timeout:
            error = "The AI took too long. The model may still be loading or the server may be busy; please try again."
            server_error = error
        except requests.RequestException:
            error = "Call Mac can't reach an Ollama server. Check that it is running and reachable."
        except (ValueError, AttributeError, TypeError):
            error = "Ollama returned an unreadable response. Please try again."
            server_error = error
    raise AgentError(server_error or error)


def availability(model=None):
    selected_model = model or MODEL
    data = request("/api/tags", model=selected_model)
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise AgentError("Ollama returned an unreadable model list.")
    names = {item.get("name") for item in data["models"] if isinstance(item, dict)}
    if selected_model not in names and f"{selected_model}:latest" not in names:
        raise AgentError(f"Download the model on your server first: ollama pull {selected_model}")
    return True


def generate_step(profile, problem, history, memory, mode="initial", model=None):
    clarification = safety_response(problem, history)
    if clarification:
        if history and not clarification.warning:
            clarification.warning = history[-1]["step"].get("warning")
        return clarification
    # Older stored question replies may still carry the legacy "unclear" result.
    if history and history[-1]["step"].get("kind") == "question" and history[-1]["result"] in {"reply", "unclear"}:
        mode = "replan"
    elif history and history[-1]["result"] == "reply":
        mode = "followup"
    context = messages(profile, problem, history, memory, mode)
    liquid_warning = None
    if liquid_exposure(problem, history):
        liquid_warning = "Do not turn it on or charge it to test it. Do not use heat or rice, or open the device yourself. Get a professional repair assessment before reuse."
        context.insert(1, {"role": "system", "content":
            "Liquid exposure was reported. The immediate safety warning has already been given. "
            "Answer the latest reply directly using the established details; do not repeat a repair-shop script or ask an already answered question. "
            "Choose answer, ask, or refer. Do not give device testing, powered diagnostics, charging, drying, or disassembly instructions. "
            "Looking dry does not establish safety. Retain this warning: " + liquid_warning})
    final_request = json.loads(context[-1]["content"])
    final_request["response_schema"] = TroubleshootingDecision.model_json_schema()
    context[-1]["content"] = json.dumps(final_request)
    validation_issue = "response did not match the required format"
    for retry in range(2):
        content = None
        data = request("/api/chat", {"model": model or MODEL, "messages": context,
            "stream": False, "format": TroubleshootingDecision.model_json_schema(),
            "options": {"temperature": 0.2, "num_predict": 1200}}, timeout=(5, 180))
        try:
            content = data["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            payload = json.loads(content)
            # kind is derived by Python. Stored IDs belong to history, not output.
            if isinstance(payload, dict):
                payload.pop("stored_action_id", None)
                payload.pop("kind", None)
                if liquid_warning:
                    payload["warning"] = liquid_warning
                if payload.get("next_move") != "explain":
                    payload["action_id"] = None
            step = TroubleshootingDecision.model_validate(payload)
            if liquid_warning and (step.next_move not in {"answer", "ask", "refer"} or step.requires_terminal):
                raise ValueError("Liquid exposure requires an answer, context question, or repair referral without powered diagnostics")
            if requests_secret(step):
                return private_credentials_response()
            if not step.assessment.strip() and step.next_move != "out_of_scope":
                raise ValueError("Include assessment: a brief user-facing explanation of the situation, uncertainty, and why the next move helps. A tool name alone is not helpful guidance")
            if step.step.count("```") % 2:
                step.step += "\n```"
            if mode == "simplify" and history and history[-1]["step"].get("kind") != "question" and step.next_move == "instruct":
                raise ValueError("The last action is blocked or unclear. Choose ask, explain with its existing action_id, change_approach, or refer; do not label a restatement as a new instruction")
            normalized = lambda value: " ".join(re.findall(r"\w+", value.casefold()))
            repeated = lambda a, b: SequenceMatcher(None, normalized(a), normalized(b)).ratio() >= 0.88
            failed_actions = {a.get("action_id") for a in history
                              if a["result"] == "failed" and a.get("action_id") is not None}
            if mode != "simplify" and any(repeated(step.step, a["step"]["step"])
                    for a in history if a["result"] == "failed" or a.get("action_id") in failed_actions):
                raise ValueError("Repeated failed step")
            if step.next_move == "explain":
                if not history or step.action_id != history[-1].get("action_id") or history[-1]["step"].get("kind") == "question":
                    raise ValueError("Explain must reference the latest actual action, not a question")
            if mode == "simplify" and history:
                if any(repeated(step.step, a["step"]["step"]) for a in history):
                    raise ValueError("The explanation repeats instructions the user does not understand")
                previous = (TroubleshootingDecision if "next_move" in history[-1]["step"] else TroubleshootingStep).model_validate(history[-1]["step"])
                if previous.warning:
                    step.warning = previous.warning
                if step.next_move == "explain":
                    step.requires_terminal = previous.requires_terminal
            return step
        except (ValidationError, ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
            if isinstance(exc, ValidationError):
                validation_issue = "; ".join(
                    f"{'.'.join(str(part) for part in error['loc']) or 'decision'}: {error['msg']}"
                    for error in exc.errors(include_input=False, include_url=False)
                )[:600]
            elif isinstance(exc, json.JSONDecodeError):
                validation_issue = "Return a complete JSON object, with no prose outside it."
            else:
                validation_issue = str(exc)[:600]
            if content:
                context.append({"role": "assistant", "content": content})
            context.append({"role": "user", "content": json.dumps({"correction": validation_issue,
                "request": "Return valid schema JSON and address the actual latest request. Use answer for coding samples and technology explanations, ask for genuinely missing context, or change a blocked troubleshooting approach."})})
    if mode == "simplify" and history:
        previous = (TroubleshootingDecision if "next_move" in history[-1]["step"] else TroubleshootingStep).model_validate(history[-1]["step"])
        return TroubleshootingDecision(assessment="I couldn't produce a clear enough response. Let's narrow down the help you need.", situation="The model could not produce a valid contextual response.", missing_information=["the part the user needs help with"], next_move="ask", action_id=None, summary="Let's make this useful", step="Which part would you like help with—an explanation, a code example, or a troubleshooting step? Type your reply below and press Enter.",
            why="I couldn't produce a clear answer. Your reply will help focus the next response.",
            difficulty="easy", requires_terminal=False, warning=previous.warning, kind="question")
    raise ResponseError("The AI server replied, but its answer could not be validated. Your conversation is saved. Retry, revise your follow-up, or select another model.", validation_issue)


def installed_models():
    data = request("/api/tags", model="*")
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise AgentError("Ollama returned an unreadable model list.")
    return sorted({item["name"] for item in data["models"]
                   if isinstance(item, dict) and isinstance(item.get("name"), str)
                   and item["name"].lower().startswith("gemma")})


def server_label():
    return "Secondary server" if SECONDARY_URL and ACTIVE_URL == SECONDARY_URL else "Primary server"
