"""Guest tasks stay in browser session memory, never in SQLite."""
class GuestStore:
    def __init__(self, state):
        self.state = state
        self.state.setdefault("guest_task", None)
        self.state.setdefault("guest_attempts", [])

    def active_session(self):
        return self.state["guest_task"]

    def pause_active(self):
        self.state["guest_task"] = None
        self.state["guest_attempts"] = []

    def start_session(self, problem):
        self.pause_active()
        self.state["guest_counter"] = self.state.get("guest_counter", 0) + 1
        self.state["guest_task"] = {"id": f"guest_{self.state['guest_counter']}", "problem": problem.strip()}

    def attempts(self, session_id):
        return self.state["guest_attempts"]

    def add_step(self, session_id, step, explanation_of=None):
        items = self.attempts(session_id)
        identifier = len(items) + 1
        items.append({"id": identifier, "action_id": explanation_of or identifier,
            "step": step.model_dump(), "result": "pending", "observation": ""})

    def record_result(self, attempt_id, result, observation=""):
        item = self.state["guest_attempts"][attempt_id - 1]
        item.update(result=result, observation=observation.strip())

    def resolve(self, session_id, observation=""):
        self.pause_active()

    def memories(self, **kwargs):
        return []
