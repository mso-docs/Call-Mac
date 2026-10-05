import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import requests
from streamlit.testing.v1 import AppTest

import agent
import database as db
from models import Profile, TroubleshootingStep, TroubleshootingDecision


def step(text="Open Settings and check the printer's status.", warning=None):
    return TroubleshootingDecision(assessment="Your computer may not be able to see the printer. This check helps narrow down the connection problem.", situation="The user reports a printer problem.", missing_information=[], next_move="instruct", action_id=None, summary="Check your printer", step=text,
        why="This tells us whether your computer can see it.", difficulty="easy",
        requires_terminal=False, warning=warning)


class MVPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(db, "DB_PATH", Path(self.temp.name) / "memory.db")
        self.db_patch.start()
        self.server_patch = patch.multiple(agent, OLLAMA_URL="http://127.0.0.1:11434", SECONDARY_URL="", ACTIVE_URL=None)
        self.server_patch.start()
        db.initialize()
        db.save_profile(Profile())

    def tearDown(self):
        self.server_patch.stop()
        self.db_patch.stop()
        self.temp.cleanup()

    def test_secret_requests_are_replaced_and_private_entry_is_allowed(self):
        for text in ["What's the password for the hidden Wi-Fi network?",
                     "Please paste your API key here.", "Tell me your verification code."]:
            with patch.object(agent, "request", return_value={"message": {"content": step(text).model_dump_json()}}):
                actual = agent.generate_step(Profile(), "Hidden Wi-Fi", [], [])
            self.assertIn("never in this chat", actual.step)
            self.assertEqual(actual.next_move, "ask")
        safe = step("Enter the password privately in your device's Wi-Fi settings. Did it connect?")
        with patch.object(agent, "request", return_value={"message": {"content": safe.model_dump_json()}}):
            self.assertEqual(agent.generate_step(Profile(), "Hidden Wi-Fi", [], []).step, safe.step)

    def test_hidden_wifi_success_reply_and_completion_ui(self):
        question = TroubleshootingDecision.model_validate({**step("Which device are you connecting?").model_dump(),
            "next_move": "ask", "missing_information": ["device"]})
        resolved = TroubleshootingDecision.model_validate({**step("Glad you connected! Keep your password private.").model_dump(),
            "next_move": "resolved", "summary": "You're connected"})
        history = [{"step": question.model_dump(), "result": "reply", "observation": "It worked! Thank you!"}]
        with patch.object(agent, "request", return_value={"message": {"content": resolved.model_dump_json()}}):
            self.assertEqual(agent.generate_step(Profile(), "Hidden Wi-Fi", history, []).next_move, "resolved")
        with patch.object(agent, "availability", return_value=True), patch.object(agent, "generate_step", side_effect=[question, resolved]):
            app = self.make_app()
            app.chat_input[0].set_value("Hidden Wi-Fi").run()
            app.chat_input[0].set_value("It worked! Thank you!").run()
            self.assertFalse(app.exception)
            self.assertTrue(any("You reported" in item.value for item in app.success))
            self.button(app, "✅ Fixed it").click().run()
            self.assertIsNone(db.active_session())
            self.assertNotIn("Glad you", db.memories()[0]["solution"])

    def test_followup_history_matches_schema_and_copied_metadata_is_normalized(self):
        from prompts import messages
        history = [{"step": step().model_dump(), "result": "reply", "observation": "What does that mean?", "action_id": 4}]
        context = messages(Profile(), "Printer offline", history, [], "followup")
        TroubleshootingDecision.model_validate_json(context[2]["content"])
        payload = {**step("It means the printer is disconnected.").model_dump(),
                   "next_move": "answer", "action_id": 4, "stored_action_id": 4, "kind": "explanation"}
        with patch.object(agent, "request", return_value={"message": {"content": json.dumps(payload)}}) as request:
            actual = agent.generate_step(Profile(), "Printer offline", history, [])
        self.assertEqual(actual.kind, "answer")
        self.assertIsNone(actual.action_id)
        self.assertIn("latest follow-up", request.call_args.args[1]["messages"][-1]["content"])

    def test_repair_sees_invalid_response_and_safe_validation_details(self):
        invalid = {**step().model_dump(), "difficulty": "secret-value"}
        captured = []
        def respond(path, payload, **kwargs):
            captured.append(json.loads(json.dumps(payload)))
            content = json.dumps(invalid) if len(captured) == 1 else step().model_dump_json()
            return {"message": {"content": content}}
        with patch.object(agent, "request", side_effect=respond):
            agent.generate_step(Profile(), "Printer offline", [], [])
        self.assertEqual(captured[1]["messages"][-2]["content"], json.dumps(invalid))
        correction = json.loads(captured[1]["messages"][-1]["content"])["correction"]
        self.assertIn("difficulty", correction)
        self.assertNotIn("secret-value", correction)

    def test_invalid_followup_can_be_revised_in_ui(self):
        question = TroubleshootingDecision.model_validate({**step("Which Linux distribution are you using?").model_dump(),
            "next_move": "ask", "missing_information": ["distribution"]})
        with patch.object(agent, "availability", return_value=True), patch.object(agent, "generate_step", side_effect=[
            question, agent.ResponseError("The AI server replied, but its answer could not be validated.", "difficulty: invalid value"), step("Open Ubuntu Wi-Fi settings.")]) as generate:
            app = self.make_app()
            app.chat_input[0].set_value("Hidden Wi-Fi on Linux").run()
            app.chat_input[0].set_value("Ubuntu").run()
            self.assertFalse(app.exception)
            self.assertTrue(any(item.placeholder == "Revise your follow-up" for item in app.chat_input))
            self.assertFalse(any(item.label == "Set up your local AI" for item in app.expander))
            app.chat_input[0].set_value("Ubuntu 24.04, GNOME desktop").run()
            self.assertFalse(app.exception)
            self.assertEqual(generate.call_args.args[2][-1]["observation"], "Ubuntu 24.04, GNOME desktop")
            self.assertEqual(len(db.attempts(db.active_session()["id"])), 2)

    def test_persistence_and_success_transaction(self):
        db.save_profile(Profile(name="Mom", operating_system="Windows 11"))
        sid = db.start_session("Printer offline")
        db.add_step(sid, step())
        db.record_result(db.attempts(sid)[-1]["id"], "failed")
        db.add_step(sid, step("Reconnect the printer cable."))
        db.resolve(sid)
        db.initialize()
        self.assertEqual(db.load_profile().name, "Mom")
        self.assertIsNone(db.active_session())
        self.assertEqual(db.memories()[0]["solution"], "Reconnect the printer cable.")
        with db.connection() as conn:
            history = json.loads(conn.execute("SELECT history FROM solutions").fetchone()[0])
        self.assertEqual([a["result"] for a in history], ["failed", "fixed"])

    def test_seed_empty_problem_and_resume(self):
        db.seed_demo()
        db.seed_demo()
        self.assertEqual(len(db.memories()), 1)
        self.assertEqual(db.memories()[0]["is_demo"], 1)
        with self.assertRaises(ValueError):
            db.start_session("  ")
        sid = db.start_session("Wi-Fi lost")
        db.initialize()
        self.assertEqual(db.active_session()["id"], sid)

    def test_structured_output_retry_and_repetition(self):
        profile = db.load_profile()
        reply = {"message": {"content": step().model_dump_json()}}
        with patch.object(agent, "request", side_effect=[{"message": {"content": "oops"}}, reply]) as call:
            result = agent.generate_step(profile, "Printer offline", [], [])
            self.assertEqual(result.step, step().step)
            self.assertEqual(call.call_count, 2)
            payload = call.call_args.args[1]
            self.assertIn("properties", payload["format"])
            self.assertFalse(payload["stream"])
        history = [{"step": step().model_dump(), "result": "failed"}]
        with patch.object(agent, "request", return_value=reply):
            with self.assertRaises(agent.AgentError):
                agent.generate_step(profile, "Printer offline", history, [], "next")

    def test_clarification_preserves_warning_and_context(self):
        previous = step(warning="Save your work first.")
        history = [{"step": previous.model_dump(), "result": "unclear"}]
        with patch.object(agent, "request", return_value={"message": {"content": TroubleshootingDecision.model_validate({**step("Click the gear icon.").model_dump(), "next_move":"change_approach"}).model_dump_json()}}) as call:
            result = agent.generate_step(Profile(name="Mom"), "Printer offline", history, db.memories(), "simplify")
            self.assertEqual(result.warning, previous.warning)
            context = json.loads(call.call_args.args[1]["messages"][1]["content"])
            self.assertEqual(context["profile"]["name"], "Mom")
            self.assertIn("change a blocked approach", json.loads(call.call_args.args[1]["messages"][-1]["content"])["request"])

    def test_local_only_and_network_failures(self):
        for url in ["https://example.com", "http://192.168.1.2:11434", "http://127.0.0.1/path"]:
            with patch.object(agent, "OLLAMA_URL", url), self.assertRaises(agent.AgentError):
                agent.local_url()
        with patch("requests.Session.request", side_effect=requests.ConnectionError):
            with self.assertRaisesRegex(agent.AgentError, "can't reach"):
                agent.availability()
        with patch.object(agent, "request", return_value={"models": []}):
            with self.assertRaisesRegex(agent.AgentError, "pull"):
                agent.availability()

    def make_app(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
        app.session_state["active_user"] = 1
        return app.run()

    def button(self, app, label):
        return next(button for button in app.button if button.label == label)

    def test_logo_starts_fresh_chat_from_help_for_guest_and_profile(self):
        with patch.object(agent, "availability", return_value=None):
            for profile_id in (0, 1):
                app = self.make_app()
                app.session_state["active_user"] = profile_id
                if profile_id:
                    db.start_session("Printer offline", profile_id=profile_id)
                else:
                    app.session_state["guest_task"] = {"id": "guest_1", "problem": "Printer offline"}
                    app.session_state["guest_attempts"] = []
                app.session_state["app_page"] = "Help"
                app.run()
                self.button(app, "Call Mac").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state["app_page"], "Get help")
                self.assertEqual(app.session_state["active_user"], profile_id)
                self.assertEqual(len(app.chat_input), 1)
                if profile_id:
                    self.assertIsNone(db.active_session(profile_id))
                else:
                    self.assertIsNone(app.session_state["guest_task"])

    def test_http_transport_payload_and_errors(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"message": {"content": step().model_dump_json()}}
        with patch("requests.Session.request", return_value=response) as transport:
            actual = agent.generate_step(Profile(), "Printer offline", [], [])
            self.assertEqual(actual.step, step().step)
            self.assertEqual(transport.call_args.args[0], "POST")
            self.assertTrue(transport.call_args.args[1].endswith("/api/chat"))
            self.assertFalse(transport.call_args.kwargs["allow_redirects"])
        for status in [302, 404, 500]:
            response.status_code = status
            with patch("requests.Session.request", return_value=response), self.assertRaises(agent.AgentError):
                agent.request("/api/chat", {})
        with patch("requests.Session.request", side_effect=requests.Timeout), self.assertRaisesRegex(agent.AgentError, "too long"):
            agent.request("/api/chat", {})

    def test_ui_database_failure(self):
        with patch.object(db, "initialize", side_effect=OSError("read only")):
            app = self.make_app()
            self.assertFalse(app.exception)
            self.assertTrue(app.error)

    def test_secondary_server_fallback(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"models": [{"name": agent.MODEL}]}
        with patch.object(agent, "SECONDARY_URL", "http://127.0.0.1:11435"), patch("requests.Session.request", side_effect=[requests.ConnectionError, response]) as transport:
            self.assertTrue(agent.availability())
            self.assertEqual(transport.call_count, 2)
            self.assertEqual(agent.ACTIVE_URL, "http://127.0.0.1:11435")

    def test_explanation_remembers_original_action_and_observations(self):
        sid = db.start_session("Printer offline")
        original = step("Reconnect the printer cable.")
        db.add_step(sid, original)
        first = db.attempts(sid)[0]
        db.record_result(first["id"], "unclear", "Which cable?")
        db.add_step(sid, step("Find the cable at the back."), explanation_of=first["action_id"])
        db.resolve(sid, "The printer is online now.")
        saved = db.memories()[0]["solution"]
        self.assertTrue(saved.startswith(original.step))
        self.assertIn("online now", saved)
        self.assertEqual(db.attempts(sid)[1]["action_id"], first["id"])
        self.assertTrue(db.attempts(sid)[1]["is_explanation"])

    def test_relevant_memory_beats_newer_unrelated_fixes(self):
        db.seed_demo()
        with db.connection() as conn:
            for _ in range(8):
                conn.execute("INSERT INTO solutions (profile_id, problem, solution) VALUES (1, 'Headphones Bluetooth', 'Pair the headphones')")
        self.assertEqual(len(db.memories(problem="Printer offline")), 1)
        self.assertEqual(db.memories(problem="Printer offline")[0]["is_demo"], 1)
        self.assertEqual(db.memories(problem="Screen flickers"), [])

    def test_help_navigation_preserves_guest_task(self):
        with patch.object(agent, "generate_step", return_value=step()) as generate:
            app = self.make_app()
            app.chat_input[0].set_value("Printer offline").run()
            calls = generate.call_count
            self.button(app, "Help").click().run()
            self.assertFalse(app.exception)
            with patch.object(db, "initialize", side_effect=AssertionError("Help should not need SQLite")):
                for topic in ["First-time setup", "Using Call Mac", "Technical details", "Demo and validation"]:
                    next(field for field in app.selectbox if field.label == "Help topic").set_value(topic).run()
                    self.assertFalse(app.exception)
                    self.assertTrue(any("# " in item.value for item in app.markdown))
            self.assertEqual(generate.call_count, calls)
            self.button(app, "Back to conversation").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Printer offline" in item.value for item in app.caption))
            self.assertEqual(generate.call_count, calls)

    def test_question_reply_replans_instead_of_simplifying(self):
        question = step("What is your printer model?")
        question.next_move = "ask"
        question.kind = "question"
        question.missing_information = ["printer model"]
        history = [{"step": question.model_dump(), "result": "unclear",
                    "observation": "Brother MFC-J1260W", "action_id": 1}]
        response = step("Open Brother's official support website and select Downloads.")
        with patch.object(agent, "request", return_value={"message": {"content": response.model_dump_json()}}) as request:
            actual = agent.generate_step(Profile(), "Download printer drivers", history, [], "simplify")
        self.assertEqual(actual.step, response.step)
        context = request.call_args.args[1]["messages"]
        self.assertIn("answered a context question", context[-1]["content"])

    def test_model_discovery_and_selection(self):
        response = {"models": [{"name": "gemma2:2b"}, {"name": "other:4b"}]}
        with patch.object(agent, "request", return_value=response):
            self.assertEqual(agent.installed_models(), ["gemma2:2b"])
        with patch.object(agent, "availability", return_value=True), patch.object(agent, "installed_models", return_value=["gemma2:2b"]), patch.object(agent, "generate_step", return_value=step()) as generate:
            app = self.make_app()
            self.button(app, "Find installed Gemma models").click().run()
            next(field for field in app.selectbox if field.label == "Gemma model").set_value("gemma2:2b").run()
            self.button(app, "Test connection").click().run()
            app.chat_input[0].set_value("Printer offline").run()
            self.assertEqual(generate.call_args.kwargs["model"], "gemma2:2b")
            next(field for field in app.text_area if field.label == "What happened? (optional)").set_value("Printer isn't listed")
            self.button(app, "❌ Still broken").click().run()
            self.assertEqual(generate.call_args.args[2][0]["observation"], "Printer isn't listed")

    def test_existing_database_upgrade(self):
        with db.connection() as conn:
            conn.execute("DROP TABLE attempts")
            conn.execute("CREATE TABLE attempts (id INTEGER PRIMARY KEY, session_id INTEGER, step TEXT, result TEXT, created_at TEXT)")
            conn.execute("INSERT INTO attempts VALUES (7, 1, ?, 'unclear', CURRENT_TIMESTAMP)", (step().model_dump_json(),))
        db.initialize()
        upgraded = db.attempts(1)[0]
        self.assertEqual(upgraded["action_id"], 7)
        self.assertEqual(upgraded["observation"], "")
        self.assertEqual(upgraded["is_explanation"], 0)

    def test_failed_explanation_also_blocks_original_action(self):
        original = step("Reconnect the printer cable.")
        history = [
            {"step": original.model_dump(), "result": "unclear", "action_id": 1},
            {"step": step("Push the cable plug in.").model_dump(), "result": "failed", "action_id": 1},
        ]
        with patch.object(agent, "request", return_value={"message": {"content": original.model_dump_json()}}):
            with self.assertRaises(agent.AgentError):
                agent.generate_step(Profile(), "Printer offline", history, [], "next")

    def test_fallback_does_not_hide_primary_generation_timeout(self):
        with patch.object(agent, "SECONDARY_URL", "http://127.0.0.1:11435"), patch("requests.Session.request", side_effect=[requests.ReadTimeout, requests.ConnectTimeout]):
            with self.assertRaisesRegex(agent.AgentError, "model may still be loading"):
                agent.request("/api/chat", {"model": agent.MODEL})

    def test_schema_grammar_failure_uses_validated_json_fallback(self):
        rejected = MagicMock(status_code=400)
        rejected.json.return_value = {"error": "Failed to parse grammar"}
        accepted = MagicMock(status_code=200)
        accepted.json.return_value = {"message": {"content": step().model_dump_json()}}
        with patch("requests.Session.request", side_effect=[rejected, accepted]) as transport:
            result = agent.generate_step(Profile(), "Printer offline", [], [])
            self.assertEqual(result.step, step().step)
            self.assertEqual(transport.call_args.kwargs["json"]["format"], "json")

    def test_near_duplicate_clarification_retries_with_obstacle(self):
        original = step("Open Settings and tap Sounds and Haptics.")
        history = [{"step": original.model_dump(), "result": "unclear", "observation": "Please explain the instruction more simply"}]
        repeated = step("Open Settings, and tap Sounds & Haptics.")
        better = TroubleshootingDecision.model_validate({**step("Are you using an iPhone or an Android phone?").model_dump(), "next_move":"ask", "missing_information":["phone type"]})
        with patch.object(agent, "request", side_effect=[{"message": {"content": repeated.model_dump_json()}}, {"message": {"content": better.model_dump_json()}}]) as request:
            actual = agent.generate_step(Profile(), "No sound", history, [], "simplify")
            self.assertEqual(request.call_count, 2)
            self.assertEqual(actual.step, better.step)

    def test_liquid_damage_overrides_model_and_device_questions(self):
        for problem in ["I dropped my Mac in a lake", "I dropped my Mac in the bathtub. Am I cooked?", "My phone is wet", "I spilled coffee on my laptop"]:
            with patch.object(agent, "request") as request:
                actual = agent.generate_step(Profile(), problem, [], [])
                self.assertIn("Do not turn", actual.step)
                self.assertTrue(actual.warning)
                self.assertEqual(actual.kind, "question")
                request.assert_not_called()

    def test_liquid_damage_stays_safe_after_followup(self):
        first = agent.generate_step(Profile(), "I dropped my Mac in a lake", [], [])
        history = [{"step": first.model_dump(), "result": "reply", "observation": "It looks dry now. What should I tell the repair shop?"}]
        response = TroubleshootingDecision.model_validate({**step("Tell the repair shop it fell into a lake and now looks dry. Ask for a repair assessment before using it.").model_dump(), "next_move": "answer"})
        with patch.object(agent, "request", return_value={"message": {"content": response.model_dump_json()}}) as request:
            actual = agent.generate_step(Profile(), "I dropped my Mac in a lake", history, [], "simplify")
            self.assertEqual(actual.step, response.step)
            self.assertIn("Do not turn it on", actual.warning)
            request.assert_called_once()
            self.assertIn(history[-1]["observation"], str(request.call_args.args[1]["messages"]))

    def test_liquid_followup_rejects_powered_diagnostics(self):
        first = agent.generate_step(Profile(), "My laptop is wet", [], [])
        history = [{"step": first.model_dump(), "result": "reply", "observation": "It's unplugged now"}]
        with patch.object(agent, "request", return_value={"message": {"content": step("Turn it on and check Settings.").model_dump_json()}}):
            with self.assertRaises(agent.ResponseError):
                agent.generate_step(Profile(), "My laptop is wet", history, [])

    def test_legacy_agent_error_and_exit_after_failed_followup(self):
        with patch.object(agent, "availability", return_value=True), patch.object(agent, "generate_step", return_value=step()):
            app = self.make_app()
            app.chat_input[0].set_value("Printer offline").run()
        with patch.object(agent, "availability", return_value=True), patch.object(agent, "generate_step", side_effect=agent.AgentError("Invalid response")), patch.object(agent, "ResponseError", create=True):
            del agent.ResponseError
            self.button(app, "❌ Still broken").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any(b.label == "Try again" for b in app.button))
            self.button(app, "End chat").click().run()
            self.assertFalse(app.exception)
            self.assertIsNone(db.active_session())
            self.assertTrue(app.chat_input)

    def test_later_liquid_report_overrides_normal_troubleshooting(self):
        history = [{"step": step().model_dump(), "result": "failed", "observation": "Actually I spilled water on it"}]
        with patch.object(agent, "request") as request:
            actual = agent.generate_step(Profile(), "Computer won't start", history, [], "next")
            self.assertIn("Do not turn", actual.step)
            request.assert_not_called()

    def test_decision_contract_and_explanation_identity(self):
        from pydantic import ValidationError
        payload = step().model_dump()
        with self.assertRaises(ValidationError):
            TroubleshootingDecision.model_validate({**payload, "next_move":"explain"})
        with self.assertRaises(ValidationError):
            TroubleshootingDecision.model_validate({**payload, "next_move":"refer", "warning":None})
        explanation = TroubleshootingDecision.model_validate({**payload,
            "next_move":"explain", "action_id":7, "step":"Push the cable plug gently until it is firmly seated."})
        history = [{"step":step().model_dump(),"result":"unclear","action_id":7}]
        with patch.object(agent, "request", return_value={"message":{"content":explanation.model_dump_json()}}):
            actual = agent.generate_step(Profile(), "Printer offline", history, [], "simplify")
            self.assertEqual(actual.action_id, 7)

    def test_model_can_change_blocked_approach(self):
        response = TroubleshootingDecision.model_validate({**step("Which options are visible in Settings?").model_dump(),
            "situation":"The user cannot locate the suggested menu.", "missing_information":["visible settings"], "next_move":"ask"})
        history = [{"step":step().model_dump(),"result":"unclear","observation":"I cannot find that menu", "action_id":1}]
        with patch.object(agent, "request", return_value={"message":{"content":response.model_dump_json()}}) as request:
            actual = agent.generate_step(Profile(), "Phone has no sound", history, [], "simplify")
            request.assert_called_once()
            self.assertEqual(actual.kind, "question")
            self.assertIsNone(actual.action_id)

    def test_saved_profile_identity_and_memory_isolation(self):
        technical_id = db.save_profile(Profile(id=0, name="Alex", technical_level="Technical", preferences=""))
        db.seed_demo(1)
        self.assertEqual(db.memories(technical_id), [])
        db.start_session("Printer offline", 1)
        db.start_session("Network issue", technical_id)
        self.assertEqual(db.active_session(1)["problem"], "Printer offline")
        self.assertEqual(db.active_session(technical_id)["problem"], "Network issue")
        self.assertEqual(db.load_profile(technical_id).technical_level, "Technical")

    def test_guest_and_applied_profile_context(self):
        technical_id = db.save_profile(Profile(id=0, name="Alex", technical_level="Technical", preferences=""))
        with patch.object(agent, "availability", return_value=True), patch.object(agent, "generate_step", return_value=step()) as generate:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
            self.assertTrue(any("Hi there!" in item.value for item in app.subheader))
            next(field for field in app.selectbox if field.label == "Experience with tech").set_value("Technical").run()
            app.chat_input[0].set_value("Guest network issue").run()
            self.assertEqual(generate.call_args.args[0].technical_level, "Technical")
            self.assertEqual(generate.call_args.args[0].name, "")
            self.assertIsNone(db.active_session())
            next(field for field in app.selectbox if field.label == "Use Call Mac as").set_value(technical_id)
            self.button(app, "Apply user").click().run()
            self.assertTrue(any("Hi, Alex!" in item.value for item in app.subheader))
            app.chat_input[0].set_value("Saved network issue").run()
            self.assertEqual(generate.call_args.args[0].name, "Alex")
            self.assertEqual(generate.call_args.args[0].technical_level, "Technical")
            self.assertEqual(generate.call_args.args[2], [])
            self.assertEqual(db.active_session(technical_id)["problem"], "Saved network issue")
            self.assertFalse(app.exception)

    def test_technology_answer_and_followup_ui(self):
        answer = TroubleshootingDecision.model_validate({**step("```python\nclass Node:\n    def __init__(self, value, next=None):\n        self.value = value\n        self.next = next\n```\nEach node points to the next one.").model_dump(),
            "next_move":"answer", "situation":"The user wants Python code."})
        with patch.object(agent, "availability", return_value=True), patch.object(agent, "generate_step", return_value=answer) as generate:
            app = self.make_app()
            app.chat_input[0].set_value("How do I write a Python linked list?").run()
            self.assertTrue(any(item.placeholder == "Ask a follow-up" for item in app.chat_input))
            self.assertFalse(any(b.label == "✅ Fixed it" for b in app.button))
            app.chat_input[0].set_value("Show me how to append a node").run()
            self.assertEqual(generate.call_args.args[2][-1]["result"], "reply")
            self.assertIn("append", generate.call_args.args[2][-1]["observation"])
            self.button(app, "Thanks, that's enough").click().run()
            self.assertIsNone(db.active_session())
            self.assertEqual(db.memories(), [])
            self.assertFalse(app.exception)

    def test_out_of_scope_menu(self):
        answer = TroubleshootingDecision.model_validate({**step().model_dump(), "next_move":"out_of_scope"})
        self.assertEqual(answer.kind, "answer")
        self.assertIn("Programming", answer.step)
        self.assertIn("hardware", answer.step)

    def test_context_visible_and_terminal_hint_matches_experience(self):
        db.save_profile(Profile(name="Alex", technical_level="Technical", preferences=""))
        response = step("Run a read-only diagnostic and share the output.")
        response.requires_terminal = True
        with patch.object(agent, "availability", return_value=True), patch.object(agent, "generate_step", return_value=response):
            app = self.make_app()
            app.chat_input[0].set_value("Network issue").run()
            self.assertTrue(any(response.assessment == item.value for item in app.markdown))
            self.assertFalse(any("window where you type" in item.value for item in app.info))
            self.assertFalse(app.exception)

    def test_generated_response_without_context_is_retried(self):
        thin = step("Try a diagnostic tool.")
        thin.assessment = ""
        with patch.object(agent, "request", side_effect=[{"message":{"content":thin.model_dump_json()}}, {"message":{"content":step().model_dump_json()}}]) as request:
            response = agent.generate_step(Profile(), "Printer offline", [], [])
            self.assertTrue(response.assessment)
            self.assertEqual(request.call_count, 2)

    def test_new_help_task_and_question_reply_in_ui(self):
        with patch.object(agent, "availability", return_value=True), patch.object(agent, "generate_step", return_value=TroubleshootingDecision(assessment="Phone menus differ, so we need the device type.", situation="Unknown phone type", missing_information=["phone type"], next_move="ask", action_id=None, summary="Which phone?", step="Which phone are you using?", why="Menus differ", difficulty="easy", requires_terminal=False)):
            app = self.make_app()
            app.chat_input[0].set_value("My phone has no sound").run()
            self.assertTrue(any(item.placeholder == "Type your reply" for item in app.chat_input))
            self.assertFalse(any(b.label == "✅ Fixed it" for b in app.button))
            previous = db.active_session()["id"]
            self.button(app, "＋ New help task").click().run()
            self.assertIsNone(db.active_session())
            self.assertTrue(app.chat_input)
            with db.connection() as conn:
                self.assertEqual(conn.execute("SELECT status FROM sessions WHERE id=?", (previous,)).fetchone()[0], "paused")
            with patch.object(agent, "generate_step", return_value=step()) as generate:
                app.chat_input[0].set_value("Printer offline").run()
                self.assertEqual(generate.call_args.args[2], [])
            self.assertFalse(app.exception)

    def test_streamlit_full_workflow_and_restart(self):
        responses = [step(), step("Reconnect the printer cable."), step("Unplug the printer cable, then plug that same cable back in.")]
        with patch.object(agent, "availability", return_value=True), patch.object(agent, "generate_step", side_effect=responses) as generate:
            app = self.make_app()
            self.assertFalse(app.exception)
            app.text_input[0].set_value("Mom")
            self.button(app, "Save profile").click().run()
            app.chat_input[0].set_value("Printer offline").run()
            self.assertFalse(app.exception)
            self.button(app, "❌ Still broken").click().run()
            self.button(app, "🤷 I don't understand").click().run()
            self.assertEqual(generate.call_args.args[-1], "simplify")
            self.button(app, "✅ Fixed it").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Saved the fix for next time." in item.value for item in app.get("toast")))
            self.assertFalse(any("Glad that worked" in item.value for item in app.success))
            self.assertEqual(len(db.memories()), 1)
            restarted = self.make_app()
            self.assertEqual(restarted.text_input[0].value, "Mom")
            self.assertFalse(restarted.exception)
        with patch.object(agent, "availability", return_value=True), patch.object(agent, "generate_step", return_value=step()) as generate:
            restarted.chat_input[0].set_value("Printer offline again").run()
            self.assertEqual(len(generate.call_args.args[3]), 1)

    def test_ui_ollama_failure_retry(self):
        with patch.object(agent, "availability", side_effect=agent.AgentError("Call Mac can't reach the local AI model.")), patch.object(agent, "generate_step", side_effect=agent.AgentError("Call Mac can't reach the local AI model.")):
            app = self.make_app()
            app.chat_input[0].set_value("Printer offline").run()
            self.assertFalse(app.exception)
            self.assertTrue(app.warning)
            self.assertTrue(any(button.label == "Try again" for button in app.button))
        with patch.object(agent, "availability", return_value=True), patch.object(agent, "generate_step", return_value=step()):
            self.button(app, "Try again").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(db.attempts(db.active_session()["id"])), 1)


if __name__ == "__main__":
    unittest.main()
