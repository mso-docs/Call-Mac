"""Browser integration checks for the static demo, using fictional Ollama replies.

Run with a separately installed Playwright + Chromium:
    python tests/browser_demo.py
No running Ollama, private .env, or public deployment is required.
"""
import json
import mimetypes
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://demo.example/Call-Mac/"
MODEL = "gemma3:4b"


def decision(move="instruct", text="Open the printer settings and check its status."):
    return {"assessment": "The printer queue may be paused.", "summary": "Check the queue",
            "step": text, "why": "This checks a reversible setting.", "difficulty": "easy",
            "requires_terminal": False, "warning": None,
            "kind": "action", "situation": "The user reports an offline printer.",
            "missing_information": ["operating system"] if move == "ask" else [],
            "next_move": move, "action_id": None}


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        calls, errors = [], []
        responses = []
        tags = {"models": [{"name": MODEL}, {"name": "llama3:latest"}]}

        def static(route):
            relative = route.request.url.removeprefix(SITE).split("?")[0] or "index.html"
            path = ROOT / "demo" / relative
            assert path.is_relative_to(ROOT / "demo") and path.is_file(), relative
            route.fulfill(path=str(path), content_type=mimetypes.guess_type(path)[0] or "text/plain")

        def ollama(route):
            calls.append(route.request)
            if route.request.url.endswith("/api/tags"):
                route.fulfill(json=tags)
            else:
                response = responses.pop(0) if responses else decision()
                if isinstance(response, int):
                    route.fulfill(status=response, json={"error": "grammar unsupported"})
                else:
                    route.fulfill(json={"message": {"content": json.dumps(response)}})

        context.route(SITE + "**", static)
        context.route("http://localhost:11434/**", ollama)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(SITE)
        page.wait_for_function("document.querySelector('#origin-command').textContent.includes('demo.example')")
        assert page.locator("#origin-command").text_content() == 'OLLAMA_ORIGINS="https://demo.example" ollama serve'
        page.locator("#sample").click()
        expect(page.locator("#sample-notice")).to_be_visible()
        expect(page.locator("#reply")).to_be_visible()
        page.locator("#observation").fill("Windows 11")
        page.locator("#reply").click()
        expect(page.locator("#action-buttons")).to_be_visible()
        page.get_by_role("button", name="Still broken", exact=True).click()
        expect(page.locator("#conversation")).to_contain_text("Restart the printer")
        page.get_by_role("button", name="Fixed it", exact=True).click()
        expect(page.locator("#feedback-form")).to_be_hidden()
        assert not calls, "Sample must never call Ollama"

        page.locator("#connect").click()
        expect(page.locator("#connection-status")).to_contain_text("Connected")
        expect(page.locator("#model option")).to_have_count(1)
        expect(page.locator("#sample-notice")).to_be_hidden()
        page.locator("#problem").fill("My printer is offline.")
        page.locator("#send").click()
        expect(page.locator("#action-buttons")).to_be_visible()
        request = calls[-1]
        assert request.method == "POST"
        payload = request.post_data_json
        assert payload["model"] == MODEL and payload["stream"] is False
        assert payload["format"]["additionalProperties"] is False
        assert "cookie" not in request.headers and "referer" not in request.headers
        assert not page.evaluate("localStorage.length || sessionStorage.length")

        # User and model content must stay text, including HTML and fenced code.
        malicious = '<img src=x onerror="window.leaked=true">'
        responses.append(decision("answer", f"{malicious}\n\n```python\nprint('hello')\n```"))
        page.locator("#observation").fill(malicious)
        page.get_by_role("button", name="Still broken", exact=True).click()
        expect(page.locator("#reply")).to_be_visible()
        assert page.locator("#conversation img").count() == 0
        assert not page.evaluate("Boolean(window.leaked)")
        assert page.locator("#conversation pre").inner_text() == "print('hello')\n"
        latest = calls[-1].post_data_json["messages"]
        assert json.loads(latest[-2]["content"])["what_happened"] == malicious

        # A failed call keeps feedback for retry, without duplicate turns.
        responses.append(500)
        page.locator("#observation").fill("Can you explain that?")
        page.locator("#reply").click()
        expect(page.locator("#retry")).to_be_visible()
        count = page.locator(".message.user").count()
        responses.append(decision(text="Open the printer's display and check for a paper jam message."))
        page.locator("#retry").click()
        expect(page.locator("#action-buttons")).to_be_visible()
        assert page.locator(".message.user").count() == count

        # Retry invalid schema output once, then surface a useful error.
        responses.extend([{"step": "invalid"}, {"step": "still invalid"}])
        page.get_by_role("button", name="Still broken", exact=True).click()
        expect(page.locator("#error")).to_contain_text("valid, contextual reply")
        expect(page.locator("#retry")).to_be_visible()

        # Server schema-grammar incompatibility retries with JSON mode.
        responses.extend([400, decision("answer", "A printer queue holds pending jobs.")])
        page.locator("#retry").click()
        expect(page.locator("#reply")).to_be_visible()
        assert calls[-1].post_data_json["format"] == "json"

        # Cancellation returns to a retryable state rather than leaving controls locked.
        held = []
        def hold(route):
            held.append(route)
        context.route("http://localhost:11434/api/chat", hold)
        page.locator("#observation").fill("Please continue")
        page.locator("#reply").click()
        expect(page.locator("#cancel")).to_be_visible()
        page.locator("#cancel").click()
        expect(page.locator("#retry")).to_be_visible()
        expect(page.locator("#error")).to_contain_text("Request stopped")
        context.unroute("http://localhost:11434/api/chat", hold)
        for route in held:
            route.abort()

        # Liquid exposure, including follow-ups, bypasses all model generation.
        page.locator("#new-task").click()
        before = len(calls)
        page.locator("#problem").fill("My laptop fell into a lake.")
        page.locator("#send").click()
        expect(page.locator("#conversation")).to_contain_text("Keep the liquid-damaged device unpowered")
        page.locator("#observation").fill("It's dry now. Should I turn it on?")
        page.locator("#reply").click()
        expect(page.locator("#conversation")).to_contain_text("This needs a repair assessment")
        assert len(calls) == before

        # Model contract and endpoint validation execute in a real JS engine.
        results = page.evaluate("""async () => {
          const core = await import('./core.js');
          const contract = await (await fetch('./contract.json')).json();
          const badURLs = ['javascript:alert(1)', 'http://user:pass@localhost:11434',
            'http://localhost:11434/api/chat', 'http://localhost:11434?token=abc', 'http://localhost:11434/#x'];
          const nativeFetch = window.fetch;
          window.fetch = (_url, options) => new Promise((_resolve, reject) => {
            options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), {once: true});
          });
          let timeout;
          try {timeout = await core.ollamaRequest('https://never.example', '/api/tags', {timeout: 1}).then(() => false, e => e.message.includes('too long'));}
          finally {window.fetch = nativeFetch;}
          return {rejected: badURLs.map(url => {try {core.normalizeEndpoint(url); return false;} catch {return true;}}),
            normalized: core.normalizeEndpoint('http://localhost:11434/'), timeout};
        }""")
        assert all(results["rejected"]) and results["normalized"] == "http://localhost:11434"
        assert results["timeout"]

        good = decision()
        invalid = [{**good, "requires_terminal": "false"}, {**good, "extra": "field"},
                   {**good, "assessment": ""}, {**good, "next_move": "refer"},
                   {**good, "next_move": "explain", "action_id": 7},
                   {**good, "next_move": "ask", "missing_information": []},
                   {**good, "step": "x" * 4001}]
        accepted = page.evaluate("""async values => {
          const core = await import('./core.js');
          const {schema} = await (await fetch('./contract.json')).json();
          return values.map(value => {try {core.validateDecision(value, schema); return true;} catch {return false;}});
        }""", [good, *invalid])
        assert accepted == [True, *([False] * len(invalid))]

        # Empty model lists, malformed URLs, reload isolation, and small screens.
        page.locator("#endpoint").fill("http://localhost:11434/api/chat")
        page.locator("#connect").click()
        expect(page.locator("#error")).to_contain_text("without a username")
        page.locator("#endpoint").fill("http://localhost:11434")
        tags["models"] = []
        page.locator("#connect").click()
        expect(page.locator("#error")).to_contain_text("No Gemma models")
        page.reload()
        expect(page.locator("#connection-status")).to_contain_text("not connected")
        expect(page.locator(".message")).to_have_count(0)
        for width in [1440, 390]:
            page.set_viewport_size({"width": width, "height": 900})
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth"), width
        assert not errors, errors
        page.screenshot(path="/tmp/call-mac-static-mobile.png", full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.screenshot(path="/tmp/call-mac-static-desktop.png", full_page=True)
        browser.close()
        print("Browser demo checks passed: sample, live API flow, validation, retries, privacy, safety, and mobile layout.")


if __name__ == "__main__":
    run()
