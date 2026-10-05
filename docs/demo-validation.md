# Demo validation

## Static browser demo

On October 4, 2026, `tests/browser_demo.py` passed in headless Chromium using a
simulated HTTPS site under `/Call-Mac/` and fictional Ollama responses. Checks cover
the no-inference sample, model discovery, direct request context, malformed schema
retries, JSON grammar fallback, API errors, retry without duplicate feedback,
cancellation, timeouts, endpoint validation, HTML escaping, liquid safety across
follow-ups, reload isolation, and desktop/mobile overflow. The exported prompt and
schema match the Python source. Gitleaks found no secrets in `demo/`.

All 39 existing Python tests also passed. These results do not validate real
Ollama inference, public hosting, CORS configuration, or local-network browser
permissions. Before presenting, test the published origin with a real installed
Gemma model. See [browser demo instructions](browser-demo.md).

## Earlier local-app validation

Validated on October 4, 2026 with Python 3.14 and Streamlit 1.65.

- Thirty automated tests pass, covering persistence, old database upgrades,
  explanations linked to original actions, observations, keyword memory matching,
  model selection, malformed output, server fallback, and friendly errors.
- The browser walkthrough passed initial advice, observations, failed feedback,
  simplification, success storage, model discovery, and connection testing. It uses an isolated temporary SQLite file, fictional
  profile, and controlled responses. Screenshots illustrate the UI; they are not
  evidence of live Gemma generation.
- A live Gemma 2 2B check against the privately configured server timed out at
  connection. Server hardware and generation latency are unverified. No private
  endpoint values are recorded in this document or other repository files.
- Git ignores private environment files. A source audit checked for configured
  endpoint values without printing them and found none in publishable files.

Before presenting with live inference:

1. Restart Streamlit after changing private `.env` configuration.
2. Find installed Gemma models and test the connection.
3. Submit a fictional printer problem, record what happened, and click Still broken.
4. Ask for a simpler explanation, then confirm success only if it actually worked.
5. Start a related problem and verify memory appears in context.
6. Restart to verify persistence and disconnect the server to verify recovery.

Use a model your server can run comfortably. Connection testing verifies model
availability, not inference speed. Time the real walkthrough on your hardware;
the example screenshots do not establish model quality or performance.

Follow-up: normal Gemma 2 2B chat succeeded on the privately configured primary.
Structured requests exposed a server-side schema grammar error (HTTP 400). Call Mac
now retries that specific failure using JSON mode, retaining Pydantic validation.


## Structured decision evaluation

The ordinary keyword router has been removed. New responses validate a factual
situation summary, missing information, next move, action reference, and displayed
step. Thirty automated tests pass with legacy history, decision validation,
question UI, fix storage, and a narrow liquid-damage safety override.

The revised Gemma 2 9B live run completed five fictional scenarios without a generic
fallback. It asked for phone type, asked about missing menu options, changed the
printer diagnostic, and respected the liquid safety override. These are move-level
smoke checks, not proof of sound advice: the printer response combined power and
network checks despite a USB context. Review response meaning and action count
before presenting. Timing in this shared-server test is not a controlled benchmark.

Reproduce with `python evals/run.py --model gemma2:9b` and compare with 2B. The runner
prints fictional responses and does not record private server configuration.

In the corrected 2B run, three of five move checks passed, including the deterministic
safety override; missing-menu and already-in-Settings cases used generic fallbacks.
The private model configuration now selects 9B. No server details are stored here.

Technology-scope follow-up: Gemma 2 9B returned a linked-list code example and a
RAM-versus-SSD explanation using the answer decision. Automated tests cover answer
follow-ups and verify that closing an informational task creates no successful fix.

An unrelated cooking request initially escaped the model scope instruction. After
adding a concrete redirection example, a different dinner request returned the
standard technology help menu. Scope remains a model decision and is not a hard
security boundary; more varied evaluation is needed for general reliability.
