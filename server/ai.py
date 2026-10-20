"""AI coach: server-side proxy with an honest, clearly labelled demo fallback."""

import json
import os
import re
import urllib.error
import urllib.request

from . import config
from .errors import ApiError


def ai_status():
    cfg = load_ai_config()
    configured = bool(cfg.get("api_key"))
    return {"configured": configured, "mode": "live" if configured else "demo", "model": cfg.get("model", "")}


def load_ai_config():
    cfg = {}
    if config.CONFIG_PATH.exists():
        try:
            cfg = json.loads(config.CONFIG_PATH.read_text(encoding="utf-8")).get("ai", {})
        except Exception:
            cfg = {}
    env_key = os.environ.get("BIZREADY_AI_KEY", "").strip()
    if env_key:
        cfg["api_key"] = env_key
    cfg.setdefault("base_url", os.environ.get("BIZREADY_AI_BASE_URL", "https://api.openai.com/v1"))
    cfg.setdefault("model", os.environ.get("BIZREADY_AI_MODEL", "gpt-4o-mini"))
    cfg.setdefault("provider", "openai")
    return cfg


COACH_SYSTEM = {
    "teach": "You are BizReady's business coach for micro and small businesses. Teach one concept at a time in simple language. Use headings: Simple explanation, Example, What to do, What not to do, Why it matters, Your next step. Use a food, online-selling or service business example. Keep under 280 words and end with one question.",
    "solve": "You are BizReady's business coach. Diagnose the owner's real problem before prescribing. Ask at most two clarifying questions, list likely causes, then give numbered practical steps with the reasoning. Use simple language, reference their business type, and avoid generic advice. Keep under 300 words.",
    "test": "You are BizReady's business coach running a short knowledge check. Ask one multiple-choice question with three options (A, B, C), wait for the answer, then explain why the correct answer is right. Do not reveal the answer before they respond.",
}


def ai_chat(mode, messages):
    cfg = load_ai_config()
    key = (cfg.get("api_key") or "").strip()
    if not key:
        return None, "not_configured"
    base = (cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    payload = {
        "model": cfg.get("model", "gpt-4o-mini"),
        "temperature": 0.4,
        "max_tokens": 650,
        "messages": [{"role": "system", "content": COACH_SYSTEM[mode]}]
        + [{"role": m["role"], "content": m["content"]} for m in messages[-8:]],
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"].strip()
        return text, None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:
        return None, str(exc)[:200]


COACH_TOPICS = {
    "pricing": {
        "keys": ["price", "pricing", "discount", "cheap", "margin", "cost", "raise price", "profit", "revenue"],
        "simple": "Price is not a number you copy from competitors. It is a decision about which customers you want, what you promise them, and what margin you need to keep the business healthy.",
        "example": "A home baker sells 60 cakes at RM45 with RM22 direct cost. Contribution is RM23. A café offers to buy 40 at RM32 — contribution falls to RM10, and the extra volume uses her only oven. The order looks big but leaves less money per hour of work.",
        "do": ["Calculate contribution per sale before and after any price change.", "Know your break-even volume.", "Test a new price with a small group or one product first.", "Explain the value, not just the number, when you raise a price."],
        "dont": ["Do not discount to win a customer you cannot serve profitably.", "Do not match a competitor without knowing their cost base.", "Do not raise prices and quietly reduce quality."],
        "why": "Small businesses usually have less room for error than large ones. A 10% price cut can require 50% more volume to stand still; knowing that prevents a slow, invisible loss.",
        "next": "Calculate contribution for your best-selling offer, then tell me the price, direct cost and monthly fixed costs — I will help you find your break-even.",
    },
    "cash": {
        "keys": ["cash", "cashflow", "cash flow", "late payment", "supplier", "owe", "loan", "run out"],
        "simple": "Profit is what is left after costs. Cash is what is in the bank today. You can be profitable and still unable to pay wages next Friday if customers pay late or you hold too much stock.",
        "example": "A caterer wins a RM24,000 contract, buys RM9,000 of stock, and is paid 45 days later. The job is profitable, but for six weeks the business is funding the client. Two late invoices at once can stop the whole operation.",
        "do": ["Forecast cash weekly for the next 13 weeks.", "Invoice immediately and state payment terms clearly.", "Collect deposits for large or custom orders.", "Negotiate supplier terms before you need them."],
        "dont": ["Do not use next month's customer deposits for this month's costs.", "Do not assume a signed contract means money is available.", "Do not hide a shortfall from yourself or your suppliers."],
        "why": "Cash problems close businesses faster than bad ideas. A short, honest forecast gives you time to act while options still exist.",
        "next": "List money coming in and going out for the next four weeks. If there is a gap, tell me the amounts and I will help you sequence the options.",
    },
    "customers": {
        "keys": ["customer", "marketing", "sales", "social media", "advert", "promote", "enquir", "audience"],
        "simple": "Marketing works when a specific person recognises a specific problem in your message. A clear customer, a clear offer and one channel you can measure beats being everywhere.",
        "example": "A tuition centre posts general 'enrol now' flyers with no response. It switches to a two-week 'exam readiness check' for parents of Form 5 students, promoted in two parent groups and followed by a WhatsApp call. Ten bookings come from 30 enquiries.",
        "do": ["Choose one primary customer group and one problem.", "Make one clear offer with a next step.", "Use one or two channels you can measure.", "Follow up within 24 hours."],
        "dont": ["Do not target everyone.", "Do not count likes as sales.", "Do not run several offers at once with no way to compare them."],
        "why": "Small budgets cannot afford vague marketing. Specific offers produce measurable responses, which let you improve instead of guessing.",
        "next": "Tell me your best-selling offer and who buys it most often. I will help you write one offer and choose a channel to test for two weeks.",
    },
    "staff": {
        "keys": ["staff", "employee", "team", "hire", "worker", "roster", "salary", "people"],
        "simple": "Most small-team problems are clarity problems before they are attitude problems. People need to know what good looks like, what they can decide, and what happens when something goes wrong.",
        "example": "A café owner complains that staff are 'not proactive'. The real issue: nobody has written down the opening checklist. A one-page checklist and a 15-minute handover cut missed tasks within a week.",
        "do": ["Write one page per role: tasks, standards, decisions.", "Train once, then observe and coach.", "Give feedback close to the event, in private.", "Review workload before assuming low effort."],
        "dont": ["Do not rely on hints or hope.", "Do not apply rules differently to different people.", "Do not add tasks without removing something."],
        "why": "Consistency protects quality and fairness. Clear standards also make it easier to reward good work and address poor work without guesswork.",
        "next": "Pick your most repeated task and write the steps someone else would need. Send them here and I will help you tighten the checklist.",
    },
    "operations": {
        "keys": ["operation", "process", "quality", "queue", "delay", "waste", "mistake", "stock", "inventory", "supplier"],
        "simple": "Operations is the repeatable path from customer request to delivery. When something goes wrong repeatedly, look for a missing standard, a missing check, or a capacity mismatch — not a person to blame.",
        "example": "A laundry service loses garments during pickup. Mapping the flow shows three handover points with no count. Adding a counted handover at each point removes almost all losses without new staff.",
        "do": ["Map the process on one page.", "Find the two points where errors occur.", "Add a simple check or count at those points.", "Measure the error rate for two weeks."],
        "dont": ["Do not add staff to fix a process problem.", "Do not write a 30-page manual nobody uses.", "Do not hide errors — log them so you can fix causes."],
        "why": "Reliable delivery protects repeat business and reduces costly rework. Simple checks are usually more effective than more people or more software.",
        "next": "Describe the step where mistakes happen most often, and what happens just before and after it. I will help you design one check.",
    },
    "online": {
        "keys": ["online", "website", "shopee", "tiktok", "ecommerce", "delivery app", "digital", "whatsapp"],
        "simple": "Selling online adds a channel, not a new business. The test is whether each order contributes after platform fees, delivery, packaging and returns — and whether customers come back.",
        "example": "An online seller makes RM28 revenue per order. Platform fee RM4, delivery RM6, packaging RM1.50, product RM9 → contribution RM7.50. Ads cost RM9 per order, so growth is losing money until repeat orders improve.",
        "do": ["Start with one channel.", "Track contribution after all fees.", "Measure repeat orders and cost per order.", "Use simple tools you will actually maintain."],
        "dont": ["Do not build an app before proving demand.", "Do not scale ads on a negative contribution.", "Do not store customer details in unsafe spreadsheets."],
        "why": "Digital channels make costs visible and comparable. That is their real advantage — not novelty.",
        "next": "Tell me your average order value and the fees you pay per order. I will help you calculate real online contribution.",
    },
    "growth": {
        "keys": ["grow", "growth", "expand", "second branch", "scale", "new product", "invest"],
        "simple": "Growth is a set of tested bets, not one big leap. The safest next step is the one that uses existing customers, existing skills and a measurable amount of money.",
        "example": "A florist wants a second outlet. Before signing a lease, she tests corporate weekly flowers for nearby offices. Three accounts cover 40% of the new rent, which lowers the risk of the larger commitment.",
        "do": ["Test demand before committing fixed costs.", "Use existing customers first.", "Set a stop rule before you start.", "Protect core service quality while testing."],
        "dont": ["Do not grow a model that is not profitable yet.", "Do not add fixed costs on optimism.", "Do not chase every opportunity that appears."],
        "why": "Fixed costs are hard to reverse. Small tests give you evidence at a fraction of the risk.",
        "next": "Tell me the growth idea and the fixed cost it requires. We will design a 30-day test with a clear stop rule.",
    },
    "general": {
        "keys": [],
        "simple": "Most business problems become manageable when you separate three things: the customer and promise, the numbers, and the process that delivers it. Fix the area with the clearest evidence first.",
        "example": "A small catering business feels 'busy but broke'. Sales are up 20%, but two large clients pay in 60 days and the menu added six low-margin items. Trimming the menu and invoicing earlier fixes more than another marketing push.",
        "do": ["Describe the problem in one sentence with numbers.", "Identify which of the three areas it sits in.", "Choose one small change and a way to measure it.", "Review after two weeks."],
        "dont": ["Do not change five things at once.", "Do not treat a cash problem as a sales problem by default.", "Do not skip the measurement step."],
        "why": "A structured diagnosis prevents expensive guessing and makes each decision a little more evidence-based than the last.",
        "next": "Tell me what is happening, what you have tried, and one number involved. I will help you narrow it down.",
    },
}


def detect_topic(text):
    low = text.lower()
    best = ("general", 0)
    for name, data in COACH_TOPICS.items():
        hits = sum(1 for k in data["keys"] if k in low)
        if hits > best[1]:
            best = (name, hits)
    return best[0]


TEST_BANK = [
    {"q": "A business sells 200 units at RM25. Variable cost is RM15 per unit and fixed costs are RM1,200. What is its profit?",
     "options": ["RM800", "RM2,000", "RM1,200"], "correct": 0,
     "explain": "Contribution is RM10 × 200 = RM2,000, minus RM1,200 fixed costs = RM800 profit."},
    {"q": "Which of these is a leading indicator for a small café?",
     "options": ["Monthly profit", "Repeat customers per week", "Last year's revenue"], "correct": 1,
     "explain": "Repeat customers per week moves early enough to act on. Profit and last year's revenue arrive too late."},
    {"q": "A supplier offers a 60-day payment term you cannot meet. What is the best response?",
     "options": ["Sign and pay late quietly", "Negotiate the term before signing", "Ignore the contract"], "correct": 1,
     "explain": "Negotiating before signing protects the relationship and avoids a cash crisis later."},
]


def demo_coach(mode, messages):
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    prefix = "**Demo mode** — scripted guidance, not a live AI. Connect an API key on the server for personalised coaching.\n\n"

    if mode == "test":
        prior_assistant = [m["content"] for m in messages if m["role"] == "assistant"]
        if prior_assistant:
            last = prior_assistant[-1]
            match = re.search(r"\[Q(\d+)\]", last)
            if match:
                idx = int(match.group(1)) - 1
                if 0 <= idx < len(TEST_BANK):
                    item = TEST_BANK[idx]
                    ans = last_user.strip().upper()
                    letter = re.match(r"^\(?([ABC])", ans)
                    picked = "ABC".index(letter.group(1)) if letter else None
                    if picked is None:
                        for i, opt in enumerate(item["options"]):
                            if opt.lower() in last_user.lower():
                                picked = i
                    if picked is None:
                        return prefix + "I did not catch which option you chose. Reply with **A**, **B** or **C**."
                    if picked == item["correct"]:
                        return prefix + f"**Correct.** {item['explain']}\n\nThat is the kind of reasoning the scenario test checks. Want another question, or shall we apply it to your business?"
                    return prefix + f"**Not quite.** The best answer is **{'ABC'[item['correct']]}** — {item['options'][item['correct']]}.\n\n{item['explain']}\n\nWant to try another one?"
        item_idx = len([m for m in messages if m["role"] == "assistant"]) % len(TEST_BANK)
        item = TEST_BANK[item_idx]
        opts = "\n".join(f"**{'ABC'[i]}.** {o}" for i, o in enumerate(item["options"]))
        return prefix + f"[Q{item_idx + 1}] {item['q']}\n\n{opts}\n\nReply with A, B or C and I will explain."

    topic = detect_topic(last_user)
    data = COACH_TOPICS[topic]
    if mode == "teach":
        reply = (
            f"**Simple explanation**\n{data['simple']}\n\n"
            f"**Example**\n{data['example']}\n\n"
            f"**What to do**\n" + "\n".join(f"• {x}" for x in data["do"]) + "\n\n"
            f"**What not to do**\n" + "\n".join(f"• {x}" for x in data["dont"]) + "\n\n"
            f"**Why it matters**\n{data['why']}\n\n"
            f"**Your next step**\n{data['next']}"
        )
    else:
        reply = (
            "**Let's diagnose it before prescribing**\n"
            "To give you something useful rather than generic advice, I need two details:\n"
            "1. What exactly happens, and when?\n"
            "2. What one number is involved (sales, cost, margin, hours, customers)?\n\n"
            f"**Likely causes**\n{data['simple']}\n\n"
            f"**What I would check, in order**\n" + "\n".join(f"{i+1}. {x}" for i, x in enumerate(data["do"])) + "\n\n"
            f"**What to avoid**\n" + "\n".join(f"• {x}" for x in data["dont"]) + "\n\n"
            f"**Why this order**\n{data['why']}\n\n"
            f"**Do this next**\n{data['next']}"
        )
    return prefix + reply


def coach_endpoint(messages, mode):
    if mode not in ("teach", "solve", "test"):
        raise ApiError(400, "Unknown coach mode.", "invalid_input")
    cleaned = []
    for m in messages[-12:]:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            continue
        text = m.get("content")
        if not isinstance(text, str) or not text.strip():
            continue
        cleaned.append({"role": m["role"], "content": text.strip()[:4000]})
    if not cleaned or cleaned[-1]["role"] != "user":
        raise ApiError(400, "Send a message to the coach.", "invalid_input")

    text, err = ai_chat(mode, cleaned)
    if text:
        return {"reply": text, "demo": False, "ai_error": None}
    if err == "not_configured":
        return {"reply": demo_coach(mode, cleaned), "demo": True, "ai_error": None}
    fallback = "The live AI request failed, so this is demo guidance instead.\n\n" + demo_coach(mode, cleaned)
    return {"reply": fallback, "demo": True, "ai_error": err}
