"""Call Mac's local Streamlit interface."""
import sqlite3
import re
from functools import partial
from pathlib import Path
from types import SimpleNamespace

from formatting import format_lists
from guest import GuestStore

import streamlit as st

import agent
import database as db
from models import Profile, TroubleshootingStep, TroubleshootingDecision

st.set_page_config(page_title="Call Mac · Local tech support", page_icon="☎️", layout="centered", initial_sidebar_state="collapsed")
st.html("""
<style>
.stApp { background: var(--mac-bg); }
/* Keep the content below Streamlit's fixed toolbar. */
.stMainBlockContainer { max-width: 960px; padding-top: 6rem; padding-bottom: 3rem; }
[data-testid="stSidebar"] { background: var(--mac-surface); border-right: 1px solid var(--mac-border); }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .8rem; }
[data-testid="stSidebar"] h2 { font-size: 1.1rem; }
[data-testid="stSidebar"] h3 { font-size: .9rem; }
h1, h2, h3 { letter-spacing: -.035em; }
[data-testid="stMain"] h3 { font-size: clamp(1.7rem, 3vw, 2.4rem); font-weight: 600; line-height: 1.25; }
[data-testid="stChatMessage"] { background: var(--mac-surface); border-radius: 12px; padding: 1rem 1.2rem; }
.stButton button, .stFormSubmitButton button { min-height: 40px; border-radius: 8px; font-weight: 500; }
.stButton button:focus-visible, .stFormSubmitButton button:focus-visible { outline: 3px solid #2563eb; outline-offset: 3px; }
[data-testid="stExpander"] { border-color: var(--mac-border); border-radius: 8px; }
[data-testid="stChatInput"] { border: 1px solid var(--mac-border); background: var(--mac-surface); border-radius: 14px; box-shadow: 0 4px 20px #0f172a08; }
[data-testid="stBottom"] > div { background: var(--mac-bg); }
.mac-brand { display: flex; align-items: center; gap: 9px; padding: 4px 0; margin-bottom: 2.5rem; color: var(--mac-text); font-size: 17px; font-weight: 650; line-height: 28px; letter-spacing: -.025em; }
.mac-mark { width: 28px; height: 28px; background: #2563eb; border-radius: 8px; color: white; display: grid; place-items: center; }
.mac-examples { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 1.25rem 0 .5rem; }
.mac-example { padding: 16px; border: 1px solid var(--mac-border); border-radius: 12px; background: var(--mac-bg); }
.mac-example strong { display: block; color: var(--mac-text); font-size: 13px; font-weight: 600; margin-bottom: 8px; }
.mac-example p { color: var(--mac-muted); font-size: 13px; line-height: 1.5; margin: 0; }
@media (max-width: 640px) {
 .stMainBlockContainer { padding-top: 5rem; }
 .mac-brand { margin-bottom: 1.5rem; }
 .mac-examples { grid-template-columns: 1fr; gap: 8px; }
 .mac-example { padding: 12px 16px; }
 .mac-example strong { margin-bottom: 4px; }
}
</style>

""")

# This trusted local asset contains the appearance control and browser preference handling.
st.html(Path(__file__).parent / "assets" / "theme.html", unsafe_allow_javascript=True)


def setup_help(message):
    st.warning(message)
    with st.expander("Set up your local AI"):
        st.markdown(
            "1. Install [Ollama](https://ollama.com/download) and open it. "
            "Keep it running while using Call Mac.\n"
            "2. Open a terminal (a window for typing commands) and download the model:"
        )
        st.code(f"ollama pull {agent.MODEL}", language="text")
        st.markdown(
            "3. In the sidebar, open **AI connection** and click **Test connection**.\n\n"
            "On Linux, if Ollama is not running, run `ollama serve` in a separate "
            "terminal and leave it open. For Ollama on this computer, no `.env` file "
            "or server address is needed. If someone manages a separate Ollama server "
            "for you, ask them to check that it is running and has your selected model."
        )


def show_step(data, technical_level="Beginner"):
    step = (TroubleshootingDecision if "next_move" in data else TroubleshootingStep).model_validate(data)
    st.markdown(f"**{step.summary}**")
    if step.warning:
        st.warning(step.warning)
    if step.requires_terminal and technical_level == "Beginner":
        st.info("This step uses a terminal: a window where you type commands. Ask someone you trust for help if you're unsure.")
    if step.assessment:
        st.markdown(step.assessment)
    st.markdown(format_lists(step.step))
    if step.kind == "action":
        st.caption(f"Difficulty: {step.difficulty}")
    with st.expander("Why am I doing this?"):
        st.markdown(format_lists(step.why))


def show_help():
    st.title("Help")
    st.write("Get started, learn how to use Call Mac, or find setup help.")
    documents = {
        "First-time setup": "docs/getting-started.md",
        "Using Call Mac": "docs/using-call-mac.md",
        "Technical details": "docs/architecture.md",
        "Demo and validation": "docs/demo-validation.md",
    }
    topic = st.selectbox("Help topic", list(documents), key="help_topic")
    path = Path(__file__).parent / documents[topic]
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        st.error("This help document is unavailable. Check that the docs folder is included with Call Mac.")
        return
    # Relative file links do not resolve in Streamlit. Link public files to the repo.
    def resolve_link(match):
        label, target = match.groups()
        if target.startswith(("https://", "http://", "#")):
            return match.group(0)
        relative = (path.parent / target).resolve().relative_to(Path(__file__).parent.resolve())
        return f"[{label}](https://github.com/mso-docs/Call-Mac/blob/main/{relative.as_posix()})"
    content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", resolve_link, content)
    st.markdown(content)
    st.download_button("Download this guide", path.read_text(encoding="utf-8"),
        file_name=path.name, mime="text/markdown")


def run():
    if st.button("Call Mac", icon=":material/north_east:", type="tertiary",
                 key="brand_home"):
        current_id = st.session_state.get("active_user", 0)
        if current_id:
            db.initialize()
            db.pause_active(current_id)
        else:
            GuestStore(st.session_state).pause_active()
        st.session_state.pop("solved", None)
        st.session_state["app_page"] = "Get help"
        st.rerun()
    page = st.session_state.get("app_page", "Get help")
    with st.container(key="app_navigation"):
        if st.button("Back to conversation" if page == "Help" else "Help",
                     type="tertiary", key="help_navigation"):
            st.session_state["app_page"] = "Get help" if page == "Help" else "Help"
            st.rerun()
    if page == "Help":
        show_help()
        return
    db.initialize()
    profiles = db.list_profiles()
    options = [0] + [p.id for p in profiles]
    labels = {0: "Guest", **{p.id: p.name or f"Profile {p.id}" for p in profiles}}
    current_id = st.session_state.get("active_user", 0)
    with st.sidebar:
        st.header("Workspace")
        candidate = st.selectbox("Use Call Mac as", options, format_func=lambda pid: labels[pid],
            index=options.index(current_id) if current_id in options else 0)
        if st.button("Apply user", use_container_width=True):
            st.session_state["active_user"] = candidate
            st.session_state.pop("solved", None)
            st.rerun()
        profile = db.load_profile(current_id) if current_id else Profile(id=0, name="", preferences="")
        levels = ["Beginner", "Comfortable", "Technical"]
        level_key = f"experience_{current_id}"
        profile.technical_level = st.selectbox("Experience with tech", levels,
            index=levels.index(profile.technical_level), key=level_key)
        st.divider()
    st.subheader(f"Hi, {profile.name}! What can I help with?" if profile.name and profile.name != "Friend" else "Hi there! What can I help with?")
    with st.sidebar:
        st.caption("Guest tasks aren't saved." if current_id == 0 else "Profile and fixes saved locally.")
    if current_id:
        store = SimpleNamespace(active_session=partial(db.active_session, current_id),
            pause_active=partial(db.pause_active, current_id), start_session=partial(db.start_session, profile_id=current_id),
            attempts=db.attempts, add_step=db.add_step, record_result=db.record_result, resolve=db.resolve,
            memories=partial(db.memories, profile_id=current_id))
    else:
        store = GuestStore(st.session_state)
    session = store.active_session()
    if session:
        title, control, exit_control = st.columns([3, 1, 1])
        title.caption("Current help task: " + session["problem"][:100])
        if control.button("＋ New help task", type="primary", use_container_width=True):
            store.pause_active()
            st.session_state.pop("solved", None)
            st.rerun()
        if exit_control.button("End chat", use_container_width=True):
            store.pause_active()
            st.session_state.pop("solved", None)
            st.rerun()
    selected_model = st.session_state.get("selected_model", agent.MODEL)
    with st.sidebar:
        with st.expander("AI connection"):
            st.caption("Server addresses stay private. Only Primary / Secondary labels are shown.")
            if st.button("Find installed Gemma models"):
                try:
                    st.session_state["model_choices"] = agent.installed_models()
                except agent.AgentError as exc:
                    st.warning(str(exc))
            choices = list(dict.fromkeys([selected_model] + st.session_state.get("model_choices", [])))
            selected_model = st.selectbox("Gemma model", choices, key="selected_model")
            if st.button("Test connection"):
                try:
                    agent.availability(selected_model)
                    st.success(f"{agent.server_label()} is reachable and has {selected_model}.")
                except agent.AgentError as exc:
                    st.warning(str(exc))
        with st.expander("Saved profiles"):
            edit_options = [p.id for p in profiles] + [0]
            edit_id = st.selectbox("Profile to edit", edit_options,
                format_func=lambda pid: "Create a new profile" if pid == 0 else labels[pid],
                index=edit_options.index(current_id) if current_id else len(edit_options)-1)
            edit_profile = db.load_profile(edit_id) if edit_id else Profile(id=0, name="", preferences="")
            with st.form(f"profile_{edit_id}"):
                name = st.text_input("Name", edit_profile.name, max_chars=100)
                operating_system = st.text_input("Operating system", edit_profile.operating_system, max_chars=150)
                computer = st.text_input("Computer / device", edit_profile.computer, max_chars=200)
                phone = st.text_input("Phone", edit_profile.phone, max_chars=200)
                levels = ["Beginner", "Comfortable", "Technical"]
                technical_level = st.selectbox("Technical comfort", levels, index=levels.index(edit_profile.technical_level))
                preferences = st.text_area("Additional preferences", edit_profile.preferences, max_chars=2000)
                if st.form_submit_button("Save profile", use_container_width=True):
                    saved = Profile(id=edit_id, name=name.strip() or "Friend", operating_system=operating_system.strip() or "Not specified",
                        computer=computer.strip() or "Not specified", phone=phone.strip() or "Not specified",
                        technical_level=technical_level, preferences=preferences.strip())
                    saved_id = db.save_profile(saved)
                    st.session_state["active_user"] = saved_id
                    st.session_state.pop(f"experience_{saved_id}", None)
                    st.rerun()
        st.divider()
        with st.expander("Remembered fixes"):
            memory = store.memories()
            if not memory:
                st.caption("Successful fixes will appear here.")
            for fix in memory:
                with st.expander(("Demo · " if fix["is_demo"] else "") + fix["problem"]):
                    st.write(fix["solution"])
            with st.expander("Demo tools"):
                st.caption("Adds a fictional Windows printer fix for trying out memory.")
                if st.button("Add demo printer fix", disabled=not current_id):
                    db.seed_demo(current_id)
                    st.success("Demo memory added.")
        if st.button("Start a new problem", use_container_width=True):
            store.pause_active()
            st.session_state.pop("solved", None)
            st.rerun()

    try:
        agent.availability(selected_model)
        with st.sidebar:
            st.divider()
            st.caption(f"● AI ready · {selected_model} · {agent.server_label()}")
            st.caption(f"Inference: {agent.inference_location()}")
    except agent.AgentError as exc:
        setup_help(str(exc))

    with st.sidebar:
        st.caption("Your profile and saved fixes stay on this computer. Troubleshooting context is sent to your configured Ollama server, which may be on another computer.")

    if st.session_state.pop("solved", False):
        st.toast("Glad that worked. Saved the fix for next time." if current_id else "Glad that worked.", icon="✅")
    session = store.active_session()
    if session is None:
        st.caption("Clear answers to tech questions. One step at a time.")
        # A nested chat input stays inline, beside the welcome content rather than
        # covering it in Streamlit's fixed bottom composer.
        with st.container():
            problem = st.chat_input("Describe a problem or ask a question…", max_chars=4000)
        st.html("""
        <div class="mac-examples">
          <div class="mac-example"><strong>Devices</strong><p>My printer is on, but shows as offline.</p></div>
          <div class="mac-example"><strong>Apps &amp; Wi-Fi</strong><p>I'm connected, but websites won't load.</p></div>
          <div class="mac-example"><strong>Code &amp; concepts</strong><p>Explain Python linked lists to me.</p></div>
        </div>
        """)
        if problem is not None:
            if not problem.strip():
                st.info("Please describe what's going wrong first.")
            else:
                store.start_session(problem)
                st.rerun()
        return

    with st.chat_message("user"):
        st.write(session["problem"])
    history = store.attempts(session["id"])
    for attempt in history:
        with st.chat_message("assistant", avatar="☎️"):
            show_step(attempt["step"], profile.technical_level)
        if attempt["result"] != "pending":
            with st.chat_message("user"):
                st.write({"failed": "❌ Still broken", "unclear": "🤷 I don't understand", "fixed": "✅ Fixed it", "reply": "Your reply"}[attempt["result"]])
                if attempt.get("observation"):
                    st.write(attempt["observation"])

    pending = history and history[-1]["result"] == "pending"
    action = None
    if pending:
        if history[-1]["step"].get("next_move") == "resolved":
            st.success("You reported that it worked.")
            if st.button("✅ Fixed it", type="primary", use_container_width=True):
                store.resolve(session["id"])
                st.session_state["solved"] = True
                st.rerun()
            if st.button("Actually, I still need help", use_container_width=True):
                store.record_result(history[-1]["id"], "reply", "The issue is not fully resolved; I still need help.")
                st.rerun()
            return
        if history[-1]["step"].get("kind") == "answer":
            with st.container():
                reply = st.chat_input("Ask a follow-up", max_chars=4000,
                    key=f"reply_{current_id}_{session['id']}_{history[-1]['id']}")
            st.caption("Enter to send · Shift+Enter for a new line")
            if reply and reply.strip():
                store.record_result(history[-1]["id"], "reply", reply)
                st.rerun()
            if st.button("Thanks, that's enough", use_container_width=True):
                store.pause_active()
                st.rerun()
            return
        if history[-1]["step"].get("kind") == "question":
            with st.container():
                reply = st.chat_input("Type your reply", max_chars=2000,
                    key=f"question_reply_{current_id}_{session['id']}_{history[-1]['id']}")
            st.caption("Enter to send · Shift+Enter for a new line")
            if reply and reply.strip():
                store.record_result(history[-1]["id"], "reply", reply)
                st.rerun()
            return
        st.markdown("**How did that go?**")
        observation = st.text_area("What happened? (optional)",
            placeholder="For example: The printer isn't listed, or I see an error message.",
            max_chars=2000, key=f"observation_{current_id}_{session['id']}_{history[-1]['id']}")
        left, middle, right = st.columns(3)
        if left.button("✅ Fixed it", type="primary", use_container_width=True):
            store.resolve(session["id"], observation)
            st.session_state["solved"] = True
            st.rerun()
        if middle.button("❌ Still broken", use_container_width=True):
            action = "failed"
        if right.button("🤷 I don't understand", use_container_width=True):
            action = "unclear"
        if action:
            store.record_result(history[-1]["id"], action, observation)
            st.rerun()
    else:
        # Feedback is committed before inference. A failure/restart can safely retry.
        mode = "initial" if not history else ("simplify" if history[-1]["result"] == "unclear" else "next")
        retry_key = f"blocked_{current_id}_{session['id']}_{len(history)}"
        error = st.session_state.get(retry_key)
        if error:
            if st.session_state.get(retry_key + "_detail"):
                st.warning(error)
                with st.expander("Response validation details"):
                    st.text(st.session_state[retry_key + "_detail"])
            else:
                setup_help(error)
            if history:
                revised = st.chat_input("Revise your follow-up", max_chars=2000,
                    key=f"recover_{current_id}_{session['id']}_{len(history)}")
                if revised and revised.strip():
                    store.record_result(history[-1]["id"], "reply", revised)
                    st.session_state.pop(retry_key, None)
                    st.session_state.pop(retry_key + "_detail", None)
                    st.rerun()
            st.caption("Your message is still here. Retry to request a response again.")
        retry = st.button("Try again", type="primary") if error else True
        if retry:
            try:
                with st.spinner("Thinking through one helpful step…"):
                    step = agent.generate_step(profile, session["problem"], history, store.memories(problem=session["problem"]), mode, model=selected_model)
                store.add_step(session["id"], step, explanation_of=getattr(step, "action_id", None) if getattr(step, "next_move", None) == "explain" else None)
                st.session_state.pop(retry_key, None)
                st.session_state.pop(retry_key + "_detail", None)
                st.rerun()
            except agent.AgentError as exc:
                st.session_state[retry_key] = str(exc)
                detail = getattr(exc, "detail", None)
                if detail:
                    st.session_state[retry_key + "_detail"] = detail
                st.rerun()


try:
    run()
except (sqlite3.Error, OSError):
    st.error("Call Mac couldn't open or save its local memory. Check that the data folder is writable and has free space, then refresh. Your existing files have not been deleted.")
