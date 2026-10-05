"""Validated local profile and model response contracts."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Profile(BaseModel):
    id: int = 1
    name: str = "Friend"
    operating_system: str = "Not specified"
    computer: str = "Not specified"
    phone: str = "Not specified"
    technical_level: Literal["Beginner", "Comfortable", "Technical"] = "Beginner"
    preferences: str = "Please avoid command-line instructions unless necessary."


class TroubleshootingStep(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    summary: str = Field(min_length=1, max_length=300)
    step: str = Field(min_length=1, max_length=4000)
    why: str = Field(min_length=1, max_length=2000)
    difficulty: Literal["easy", "medium", "advanced"]
    requires_terminal: bool = Field(strict=True)
    warning: str | None = Field(default=None, max_length=2000)
    kind: Literal["action", "question", "answer"] = "action"
    assessment: str = Field(default="", max_length=1200)


class TroubleshootingDecision(TroubleshootingStep):
    situation: str = Field(min_length=1, max_length=1500)
    missing_information: list[str] = Field(max_length=5)
    next_move: Literal["ask", "instruct", "explain", "change_approach", "refer", "answer", "out_of_scope", "resolved"]
    action_id: int | None

    @model_validator(mode="after")
    def decision_contract(self):
        self.kind = "question" if self.next_move in {"ask", "refer"} else "action"
        if self.next_move in {"answer", "out_of_scope", "resolved"}:
            self.kind = "answer"
        if self.next_move == "out_of_scope":
            self.summary = "Ask me about technology"
            self.step = "I can help with technology! Try asking about:\n\n- Programming, code examples, and debugging\n- Apps, software, and operating systems\n- Computers, phones, and other hardware\n- Wi-Fi, printers, and device connections\n- How technology works\n\nWhat would you like help with?"
            self.warning = None
            self.requires_terminal = False
        if self.next_move == "ask" and (not self.missing_information or "?" not in self.step):
            raise ValueError("Ask must name missing information and ask an actual question")
        if self.next_move == "refer" and not self.warning:
            raise ValueError("A referral needs a warning explaining why ordinary troubleshooting should stop")
        if self.next_move == "explain" and self.action_id is None:
            raise ValueError("An explanation must reference the existing action")
        if self.next_move != "explain" and self.action_id is not None:
            raise ValueError("Only an explanation may reuse an action identity")
        return self
