# MVP architecture

## Static browser demo

`demo/` is a separate HTML/CSS/JavaScript frontend for GitHub Pages or Vercel.
It calls the visitor's selected Ollama directly with browser fetch; it never runs
the Streamlit server or accesses SQLite. Tab-local conversation state avoids
shared profiles and process-global connection state. A clearly labeled scripted
sample works without Ollama. `tools/export_demo_contract.py` exports the existing
public system prompt and Pydantic JSON schema without loading private config.
The browser validates responses, handles retries/cancellation, and applies
liquid-damage safety routing before inference. See [deployment and differences](browser-demo.md).

## Local Python app

The application is a local Streamlit process, a local Ollama process, and a SQLite
file. See the README for setup, environment variables, privacy, and limitations.

`app.py` renders an editable profile, the active session, validated response cards,
feedback buttons, and recent successful fixes. `agent.py` calls `/api/tags` and
`/api/chat` directly with requests; loopback URLs and explicitly configured HTTP/HTTPS servers are allowed and proxy
environment variables and redirects are disabled. `models.py` defines Pydantic
contracts; `prompts.py` supplies explicit behavior and JSON-encoded context.

`database.py` persists feedback before model generation. An unresolved session with
no pending step requests the next step or clarification, making restart and retry
safe. Successful resolution is a transaction spanning attempts, sessions, and
solutions. Clarifications create an explanation linked by `action_id` to the original action.
Saved fixes use the original action and retain user observations and full history.
Demo memories have an explicit fictional marker and seeding is idempotent.

Configuration: `CALL_MAC_MODEL` selects weights, `CALL_MAC_OLLAMA_URL` selects the
local endpoint, and `CALL_MAC_DB` selects the database file. Defaults are Gemma 3
4B, port 11434 on IPv4 loopback, and `data/call_mac.db` next to the source files.

Tests use temporary databases and controlled Ollama replies. Real model quality,
latency, safe instructions, and semantic repetition require manual validation.

The optional repository `.env` supplies `OLLAMA_BASE_URL` and `OLLAMA_SECONDARY_URL`.
No file is needed for local defaults. `.env.example` is the public template;
[the first-time guide](getting-started.md) explains setup and configuration.
Existing process variables win. `CALL_MAC_OLLAMA_URL` overrides the primary.
Requests fall back between servers; successful endpoints are preferred thereafter.
Remote inference sends troubleshooting context to the configured machine; the UI
discloses this. SQLite remains on the machine running Streamlit.

Additive migrations preserve existing SQLite files, adding observation, action_id,
and is_explanation columns. Existing attempts receive their own action identity.
Recent fixes remain visible in the sidebar; prompt retrieval ranks all profile fixes
by keyword overlap and excludes zero-score matches. No embeddings are used.
Model choices live in Streamlit session state and are passed explicitly to generation.
Model discovery lists installed Gemma weights. Server URLs stay in private configuration;
connection controls display only Primary / Secondary labels.

Prompt history uses assistant/user chat turns and highlights the latest nonempty
observation. Clarification addresses the obstacle rather than just restating the
action. Near-identical responses are retried; repeated clarification then becomes
a concrete screen/options question with the previous warning preserved.

`TroubleshootingDecision` replaces keyword routing for ordinary conversation. One
model response contains situation, missing_information, next_move, action_id, and
user-facing step fields. The next move is ask/instruct/explain/change_approach/refer.
Python derives question/action UI behavior, validates explanation identity, and
requires warnings for referrals. New actions receive new database identities;
only explicit explanations attach to the previous action. Legacy stored steps
remain readable. New help task pauses the old session without deleting it.


`safety.py` routes user-reported liquid exposure before model
inference. Exposure remains relevant for the entire task, including later reports.
Safety warnings are preserved independently of previous ordinary-step warnings.

Profile selection is explicit and defaults to Guest. SQLite supports multiple
saved profiles, with all active-session and memory operations scoped by profile ID.
Saving a profile applies it. GuestStore keeps guest task state only in Streamlit
session_state and never writes guest data to SQLite. The top experience selector
sets the profile passed to the model on every generation. Names are used for UI
greetings; empty names get a generic greeting. Existing saved profiles remain intact.

Decision next_move now includes answer and out_of_scope. Both render as answer
cards with Send follow-up and Thanks, that's enough controls. Follow-ups use the
reply result, retain context, and do not trigger the blocked-action restriction.
Out-of-scope decisions render a standard technology help menu. No keyword topic
router was added; the model determines the topic from the conversation.

The top-level Help view renders checked-in Markdown from `docs/` without initializing
the database or calling Ollama. Navigation preserves conversation session state.

`formatting.py` repairs inline numbered sequences and bullet lists when rendering
responses and explanations. Existing Markdown indentation and code stay intact;
stored responses are unchanged. Prompts request one list item per line.

Clarification replies are recorded as `reply` and route through `replan`, including
legacy question replies stored as `unclear`. Driver guidance uses official support
routes; the app has no web-search integration. The opaque header reserves space
for Help and Appearance while conversations scroll.

Question replies and answer follow-ups use native chat inputs (Enter sends,
Shift+Enter inserts a newline). Inference errors are retained in session state
and immediately rerender with a retry control, without duplicating submitted feedback.

Credential handling: the prompt forbids collecting secrets and explains private
entry in trusted settings. A conservative English output guard replaces common
credential requests with safe guidance; it is not a guarantee against every
paraphrase. Hidden Wi-Fi guidance distinguishes SSID, security type, and usernames.
The resolved decision acknowledges explicit user-reported success and offers
Fixed it to complete the task, or a return to troubleshooting. Saved fixes use
prior actions and user observations rather than the acknowledgement itself.

Follow-up reliability: stored assistant turns contain only response fields; action
identities travel in user feedback metadata. General replies use a follow-up prompt
rather than demanding a new troubleshooting action. Derived kind and copied action
metadata are normalized before validation; explanation identities remain strict.
Repair retries include the rejected response and concise validation errors without
input values. ResponseError distinguishes invalid answers from connection failures.
The error UI offers revision of the latest reply and model switching/retry without
resetting the task; revision updates the existing feedback record.
