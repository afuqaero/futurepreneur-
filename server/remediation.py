"""Map a missed question back to the lesson that teaches it.

Questions carry no lesson column yet; this explicit map is the authored
link between each seeded question and one of its module's four lessons.
Admin-created questions fall back to a keyword match against lesson text,
so a remediation link is never invented when no sensible match exists.
"""

import re

# question id -> lesson number (1-based) within the module
LESSON_BY_QUESTION = {
    # Strategy (legacy seed)
    "q-str-1": 1, "q-str-2": 3, "q-str-3": 2, "q-str-4": 4, "q-str-5": 2,
    "q-str-6": 3, "q-str-7": 3, "q-str-8": 1, "q-str-9": 4, "q-str-10": 4,
    "s-str-1": 3, "s-str-2": 3, "s-str-3": 2, "s-str-4": 3, "s-str-5": 2,
    # Marketing
    "mk-q1": 1, "mk-q2": 2, "mk-q3": 2, "mk-q4": 3, "mk-q5": 3,
    "mk-q6": 3, "mk-q7": 4, "mk-q8": 2, "mk-q9": 3, "mk-q10": 3,
    "mk-s1": 3, "mk-s2": 3, "mk-s3": 2, "mk-s4": 4, "mk-s5": 4,
    # Operations
    "op-q1": 1, "op-q2": 1, "op-q3": 2, "op-q4": 2, "op-q5": 3,
    "op-q6": 3, "op-q7": 4, "op-q8": 4, "op-q9": 4, "op-q10": 4,
    "op-s1": 1, "op-s2": 4, "op-s3": 3, "op-s4": 4, "op-s5": 2,
    # Finance
    "fn-q1": 1, "fn-q2": 1, "fn-q3": 2, "fn-q4": 2, "fn-q5": 3,
    "fn-q6": 3, "fn-q7": 3, "fn-q8": 4, "fn-q9": 4, "fn-q10": 4,
    "fn-s1": 2, "fn-s2": 3, "fn-s3": 2, "fn-s4": 4, "fn-s5": 4,
    # People
    "pp-q1": 1, "pp-q2": 1, "pp-q3": 2, "pp-q4": 2, "pp-q5": 3,
    "pp-q6": 3, "pp-q7": 3, "pp-q8": 4, "pp-q9": 4, "pp-q10": 4,
    "pp-s1": 2, "pp-s2": 3, "pp-s3": 1, "pp-s4": 4, "pp-s5": 2,
    # Systems
    "sy-q1": 1, "sy-q2": 1, "sy-q3": 2, "sy-q4": 2, "sy-q5": 2,
    "sy-q6": 3, "sy-q7": 3, "sy-q8": 4, "sy-q9": 4, "sy-q10": 4,
    "sy-s1": 1, "sy-s2": 2, "sy-s3": 3, "sy-s4": 2, "sy-s5": 1,
    # Legal
    "lg-q1": 1, "lg-q2": 1, "lg-q3": 1, "lg-q4": 4, "lg-q5": 2,
    "lg-q6": 2, "lg-q7": 3, "lg-q8": 3, "lg-q9": 4, "lg-q10": 4,
    "lg-s1": 1, "lg-s2": 2, "lg-s3": 3, "lg-s4": 4, "lg-s5": 4,
    # Digital
    "dg-q1": 1, "dg-q2": 2, "dg-q3": 2, "dg-q4": 2, "dg-q5": 2,
    "dg-q6": 3, "dg-q7": 3, "dg-q8": 4, "dg-q9": 4, "dg-q10": 4,
    "dg-s1": 1, "dg-s2": 2, "dg-s3": 3, "dg-s4": 3, "dg-s5": 4,
}

STOP = set(
    "the a an and or of to in for on with your you is are it this that be as at by from "
    "not do does what which who how when why if than then them their our we can could "
    "should would may might will just about into out more most less only also very much "
    "many few one two three".split()
)


def _tokens(text):
    return {w for w in re.findall(r"[a-z]+", (text or "").lower()) if w not in STOP and len(w) > 2}


def lesson_for(module, question_id, topic="", prompt=""):
    """Return {id,number,title} for the lesson that should be revisited."""
    lessons = (module or {}).get("lessons") or []
    if not lessons:
        return None
    position = LESSON_BY_QUESTION.get(question_id)
    if position and 1 <= position <= len(lessons):
        chosen = lessons[position - 1]
        return {"id": chosen["id"], "number": chosen["number"], "title": chosen["title"]}

    wanted = _tokens(f"{topic} {prompt}")
    best, best_score = None, 0
    for lesson in lessons:
        body = " ".join(
            [lesson.get("title", ""), lesson.get("summary", "")]
            + list(lesson.get("explanation") or [])
            + list(lesson.get("do") or [])
        )
        score = len(wanted & _tokens(body))
        if score > best_score:
            best, best_score = lesson, score
    if best is None or best_score < 1:
        return None
    return {"id": best["id"], "number": best["number"], "title": best["title"]}
