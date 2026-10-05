"""Safety routing takes priority over normal troubleshooting and model advice."""
import re

from models import TroubleshootingStep


def liquid_exposure(problem, history):
    # Only user reports establish exposure, never the assistant's own instructions.
    reports = [problem, *[a.get("observation", "") for a in history]]
    pattern = r"\b(lake|submerged|soaked|water damage|liquid damage|liquid detected)\b|\b(?:dropped|fell|fall|spilled|spill)\b.{0,80}\b(?:water|lake|pool|sea|ocean|toilet|bath|bathtub|coffee|tea|juice|liquid)\b|\b(?:water|liquid|coffee)\b.{0,60}\b(?:spilled|spill|inside|into|on my)\b|\b(?:mac|laptop|computer|phone|device|keyboard)\b.{0,40}\b(?:wet|soaked)\b"
    return any(re.search(pattern, text.casefold()) for text in reports)


def safety_response(problem, history):
    if not liquid_exposure(problem, history):
        return None
    already_warned = any(a["step"].get("summary") == "Keep the liquid-damaged device unpowered" for a in history)
    if already_warned:
        return None
    return TroubleshootingStep(summary="Keep the liquid-damaged device unpowered",
        step="Not necessarily beyond repair, but water inside can cause damage even if the outside looks dry. Do not turn the device on or plug it in to test it. If it is connected to power, disconnect the charger only if you can do so safely with dry hands, without touching wet electrical equipment. If it's already off, leave it off. Is it still connected to power?",
        why="Liquid exposure changes the first step: protect the device from further powered use before trying any normal troubleshooting. Manufacturer guidance: https://support.apple.com/en-us/120854",
        difficulty="easy", requires_terminal=False, kind="question",
        warning="A device submerged in water needs professional assessment before reuse. Do not use heat or rice to dry it, or open it yourself. If it is hot, smoking, or sparking, do not handle it; move away and seek emergency help.")


def requests_secret(step):
    """Block common credential solicitations; private-entry guidance is allowed.

    This is a conservative guard, not a detector for all languages/paraphrases.
    """
    secret = r"(?:password|passphrase|pin|one[- ]time code|verification code|recovery code|api key|access token|secret)"
    if any(re.fullmatch(r"(?:the |your |network |wi-fi )*" + secret, item.casefold().strip())
           for item in getattr(step, "missing_information", [])):
        return True
    for field in (step.summary, step.assessment, step.step, step.why, step.warning or "", *getattr(step, "missing_information", [])):
        for sentence in re.split(r"[.!\n]+", field.casefold()):
            if re.search(r"\b(?:never|don't|do not)\b", sentence):
                continue
            if re.search(r"\b(?:what(?:'s| is)|tell me|share|send|paste|provide|give me|type here)\b[^?]{0,120}\b" + secret + r"\b", sentence):
                return True
            if re.search(r"\b(?:enter|type)\b.{0,80}\b" + secret + r"\b.{0,60}\b(?:here|chat|reply|message)\b", sentence):
                return True
            if "?" in sentence and re.search(r"\b" + secret + r"\b", sentence):
                if not re.search(r"\b(?:have|know|forgot|forgotten|reset|change|enter|entered)\b", sentence):
                    return True
    return False


def private_credentials_response():
    from models import TroubleshootingDecision
    return TroubleshootingDecision(
        assessment="Keep your sign-in details private. You can troubleshoot without sharing any secrets here.",
        situation="The generated guidance requested secret credentials and was replaced.",
        missing_information=["connection result or error message"], next_move="ask", action_id=None,
        summary="Enter credentials privately",
        step="If the device or service asks for credentials, enter them only in its trusted settings or sign-in dialog, never in this chat. If you don't have them, contact the network owner or service administrator. Did you connect successfully, or what error appeared? Share only the error text, with any private details removed.",
        why="Only the connection result is needed to choose the next step.",
        difficulty="easy", requires_terminal=False)
