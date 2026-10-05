# Browser demo: GitHub Pages or Vercel

The `demo/` folder is a standalone static website. It needs no build, backend,
hosting secrets, account, or hosted model. It uses relative asset paths, so it
works under GitHub Pages' repository path as well as a Vercel domain.

Visitors can choose **Try a sample walkthrough** to explore a fictional printer
scenario with scripted responses. The sample makes no Ollama requests. For real
questions, visitors connect their own Ollama. Requests go directly from their
browser to that address, never through GitHub or Vercel's servers.

## Publish with GitHub Pages (recommended)

1. Commit and push the demo, `tools/export_demo_contract.py`, current `models.py`
   and `prompts.py`, and `.github/workflows/demo-pages.yml` to `main`.
2. In the repository, open **Settings → Pages → Build and deployment → Source**
   and choose **GitHub Actions**.
3. Open **Actions → Deploy browser demo to GitHub Pages → Run workflow**.
   Future pushes affecting the demo or its contract also deploy automatically.
4. Open the deployed URL shown by the workflow. For this repository, the standard
   URL is `https://mso-docs.github.io/Call-Mac/`, unless you configure a custom domain.

The workflow runs the browser checks, verifies that the exported prompt/schema matches the Python app, and
uploads **only `demo/`**. It does not publish `.env`, SQLite, or the repository root.
Repository/environment deployment permissions may need to be enabled by an owner.
See [GitHub's custom workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

## Publish with Vercel

1. Import this GitHub repository in Vercel.
2. Set **Root Directory** to **`demo`**.
3. Choose the **Other** framework preset. Leave the overridden Build Command empty
   and use the root of `demo` as the output (no custom output directory).
4. Deploy. No environment variables or AI API keys are required.

`demo/vercel.json` skips install/build steps and adds security headers. Keep the
Root Directory set to `demo`; serving the repository root is unnecessary and could
expose files included in a deployment. Preview domains each have their own origin;
use a stable production domain when configuring Ollama.
See [Vercel's static build and root-directory instructions](https://vercel.com/docs/builds/configure-a-build).

## Connect a visitor's Ollama

1. Install and start Ollama on the visitor's computer.
2. Download a model: `ollama pull gemma3:4b` (or another installed Gemma model).
3. Set **`OLLAMA_ORIGINS` on that computer** to the exact website origin. The site
   displays the correct value for wherever it is hosted. The origin is protocol
   plus host plus port; it excludes paths. For GitHub Pages, that means
   `https://mso-docs.github.io`, not the `/Call-Mac/` suffix.
4. Restart Ollama, open the demo, enter `http://localhost:11434`, and click
   **Connect to Ollama**. Select one of the discovered Gemma models.
5. Allow browser access to local devices if prompted, then submit a fictional
   problem for your first test.

For a terminal-managed Ollama process, stop any existing process and run:

```bash
OLLAMA_ORIGINS="https://mso-docs.github.io" ollama serve
```

For the macOS desktop app:

```bash
launchctl setenv OLLAMA_ORIGINS "https://mso-docs.github.io"
```

Then quit and reopen Ollama. On Windows, set `OLLAMA_ORIGINS` in your user's
environment variables, then quit and reopen Ollama. For Linux systemd, add
`Environment="OLLAMA_ORIGINS=https://mso-docs.github.io"` under `[Service]` in
`sudo systemctl edit ollama.service`, then reload systemd and restart the service.
Follow [Ollama's OS-specific configuration guide](https://docs.ollama.com/faq#how-do-i-configure-ollama-server).

Use the exact site origin rather than `*`. Ollama can remain bound to loopback;
no port forwarding, public tunnel, or `OLLAMA_HOST=0.0.0.0` is needed for a visitor
using Ollama on the same computer as their browser. Origin permissions apply to
the whole origin: GitHub Pages sites under the same username share that origin.
A dedicated domain provides a narrower boundary. CORS is not authentication.

### If the connection fails

- Check that Ollama is running and the address includes the right port.
- Confirm you restarted Ollama after setting `OLLAMA_ORIGINS`.
- Allow local-network access in your browser's site permissions if requested.
- Browser support varies. Try a current desktop Chrome/Edge browser. An HTTPS
  website accessing an HTTP server elsewhere on the LAN can also hit mixed-content
  restrictions; use an appropriately secured HTTPS endpoint or run this demo locally.
- A phone's `localhost` points to the phone, not your laptop. Prefer a desktop
  browser with Ollama installed on the same computer for presentations.
- Do not expose an unauthenticated Ollama server to the public internet just to
  make the demo connect. This demo does not support credential-bearing URLs or
  authentication tokens; privately secured remote endpoints need their own access setup.

[Chrome's local-network access documentation](https://developer.chrome.com/blog/local-network-access)
explains the additional browser permission. CORS permission and local-network
permission are separate checks.

## Preview locally

From the repository root:

```bash
python -m http.server 8000 --bind 127.0.0.1 --directory demo
```

Open `http://localhost:8000`. The sample works immediately. For real inference,
allow `http://localhost:8000` through `OLLAMA_ORIGINS` and restart Ollama. Serve
only the demo directory; don't open `index.html` as a `file://` URL.

## Privacy and differences from the local app

The static demo has no shared profiles, SQLite, remembered fixes, proxy, analytics,
or persistent browser storage. Connection settings and conversation live in the
open tab's memory and are cleared on reload. Switching to a newly connected server
clears the current task. Normal hosting access logs may still record page visits.

The Ollama server receives the problem, history, observations, and experience level.
Remote endpoints receive that same information. Users should enter only fictional
or non-sensitive data for demonstrations. Generated HTML is never executed; replies
and code are rendered as text. Redirects and cookies are disabled for API requests.

The demo reuses the Python system prompt and response schema via `contract.json`.
Browser code validates field types/limits and decision references, rejects exact
repeated failed instructions, and retries invalid output once. It also preserves
liquid-exposure safety routing across follow-ups, before model requests. Unlike the
Python app, it does not perform fuzzy repetition checks. Neither version can prove
advice is correct. Requests can be stopped or retried without duplicating feedback;
tasks are limited to 24 replies to bound context size.

## Maintain and verify

After changing `prompts.py` or `models.py`, regenerate the public contract:

```bash
python tools/export_demo_contract.py
python tools/export_demo_contract.py --check
```

This script imports only public prompt and schema modules, never the Ollama agent
or `.env`. Commit the generated `demo/contract.json` with those changes. Vercel
serves it directly; GitHub Pages checks for stale exports before publishing.

Optional browser checks (Playwright is a development tool, not an app dependency):

```bash
python -m pip install playwright
python -m playwright install chromium
python tests/browser_demo.py
```

These checks use mocked Ollama responses at a simulated HTTPS site under a
repository path. They verify sample flow, API payloads, schema retries, errors,
liquid safety, output escaping, isolation, and mobile layout. They do **not** prove
real Ollama connectivity or browser permission behavior. Before presenting, test
your actual published origin against real Ollama and the selected model.
