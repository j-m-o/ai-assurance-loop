"""Reference system under test: a fictional support-reply assistant.

Its behavior is driven by a config, standing in for a prompt or agent policy.
The loop never sees inside it; it only sees replies. Replace this with your
own system by producing an outputs file instead (see SKILL.md).

AI Assurance Loop, created by Jessica Mosley | LinkedIn: https://www.linkedin.com/in/jessmosley/ | GitHub: https://github.com/j-m-o/
"""
import re

INJECTION = ("ignore previous", "ignore all", "system prompt", "you are now", "admin mode")
CARD = re.compile(r"\b(?:\d[ -]?){13,16}\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def redact(text: str) -> str:
    return EMAIL.sub("[email]", CARD.sub("[card]", text))


def reply(message: str, cfg: dict) -> str:
    m = message.lower()
    if cfg.get("injection_guard") and any(p in m for p in INJECTION):
        return "I can't help with that request. I can help with orders, refunds and account questions."
    parts, policy = [], None
    if any(k in m for k in cfg.get("escalate_keywords", [])):
        parts.append("I'm escalating this to a human specialist who will contact you within one business day.")
    if "refund" in m or "money back" in m:
        policy = "POL-REFUND-30"
        if cfg.get("refund_promise") == "always":
            parts.append("We will refund you right away.")
        else:
            parts.append("Refunds are available within 30 days of delivery for unused items. I can start a refund request for review.")
    elif "cancel" in m:
        policy = "POL-CANCEL"
        parts.append("You can cancel any time from Settings > Billing; access continues to the end of the billing period.")
    elif "password" in m or "login" in m:
        policy = "POL-ACCOUNT"
        parts.append("Use 'Forgot password' on the sign-in page to reset it.")
    else:
        parts.append("Thanks for reaching out. Could you share your order number so I can help?")
    if cfg.get("cite_policy") and policy:
        parts.append(f"[Policy: {policy}]")
    shown = redact(message) if cfg.get("pii_redaction") else message
    parts.append(f'You wrote: "{shown}"')
    return " ".join(parts)
