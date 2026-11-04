"""Question types (task 4.7): what each stores as its answer key, how the key is checked, what a student is sent,
and how an answer is graded. The editor, the Excel import, grading and the candidate payload all go through here,
so a type behaves the same everywhere.

    single_choice / multi_choice  options: [text]; correct: text / [text]
    true_false                    options: ["true", "false"]; correct: "true" | "false" (labels are translated on screen)
    fill_blank                    options: None; correct: [[accepted answers for blank 1], [for blank 2], ...]
                                  Blanks are written in the question as ___ (three or more underscores).
    numeric                       options: None; correct: {"value": 9.8, "tolerance": 0.05}
    matching                      options: {"left": [...], "right": [... (may include extras)]}; correct: {left: right}
    ordering                      options: [items in the correct order]; correct: the same list
    text / image_upload           graded by staff; no key

Grading compares values, never positions, and is all or nothing per question (partial marks are task 4.9).
"""
import math
import random
import re
import unicodedata

from . import models

BLANK = re.compile(r"_{3,}")
MAX_ITEMS = models.MAX_OPTIONS  # options, accepted answers per blank, pairs, items to order
MAX_RIGHT = 15  # matching: answers on the right, including ones that match nothing
MAX_TEXT = 1000  # characters in one option, accepted answer or item


def blank_count(title: str | None) -> int:
    """How many blanks a fill-in-the-blank question has: its ___ markers, or one when it has none."""
    return max(1, len(BLANK.findall(title or "")))


# --- what people type

# Digits from other scripts (Bengali, Arabic-Indic, Persian, Devanagari) count as the digits they are
_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹०१२३४५६७८९", "0123456789" * 4)
# "1,000" and "12,34,567" (lakh grouping) group digits; any other lone comma is a decimal comma ("9,81", "0,500")
_GROUPED = re.compile(r"[-+]?[1-9]\d{0,2}(?:(?:,\d{3})+|(?:,\d{2})+,\d{3})")
_PLUS_MINUS = re.compile(r"±|\+/-|\+-")


def normalize_text(value) -> str:
    """A typed answer as it is compared: one Unicode form, case-folded, single spaces, no punctuation around it."""
    text = unicodedata.normalize("NFC", str(value)).casefold().translate(_DIGITS)
    return " ".join(text.split()).strip(" .,;:!?\"'()[]{}")


def parse_number(value) -> float:
    """A typed number. Bengali and other digits, a minus sign, spaces between digit groups and a decimal comma
    ("9,81", "1.000,5") are understood. Raises ValueError for anything that isn't one finite number."""
    if isinstance(value, bool):
        raise ValueError("not a number")
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = unicodedata.normalize("NFKC", str(value)).translate(_DIGITS)
        text = text.replace("٫", ".").replace("٬", ",").replace("−", "-").replace(" ", "").strip()
        if "," in text and "." in text:
            # The later mark is the decimal point: 1,000.5 or 1.000,5
            text = text.replace(",", "") if text.rfind(".") > text.rfind(",") else text.replace(".", "").replace(",", ".")
        elif "," in text:
            text = text.replace(",", "") if _GROUPED.fullmatch(text) else text.replace(",", ".")
        number = float(text)
    if math.isnan(number) or math.isinf(number):
        raise ValueError("not a number")
    return number


def _items(values, plural: str, singular: str, minimum: int = 2, maximum: int = MAX_ITEMS) -> list[str]:
    if not isinstance(values, list):
        raise ValueError(f"Give the {plural} as a list.")
    items = [str(v).strip() for v in values if v is not None]
    if len(items) != len(values) or any(not item for item in items):
        raise ValueError(f"Fill in every {singular} or remove the empty ones.")
    if len(items) < minimum:
        raise ValueError(f"Add at least {minimum} {plural}." if minimum > 1 else f"Add at least one {singular}.")
    if len(items) > maximum:
        raise ValueError(f"Use at most {maximum} {plural}.")
    if any(len(item) > MAX_TEXT for item in items):
        raise ValueError(f"Keep each {singular} under {MAX_TEXT} characters.")
    if len(set(items)) != len(items):
        raise ValueError(f"Two {plural} have the same text.")
    return items


# --- checking an answer key

_TRUE = {"true", "t", "yes", "সত্য", "ঠিক"}
_FALSE = {"false", "f", "no", "মিথ্যা", "ভুল"}


def clean(qtype: str, title: str | None, options, correct):
    """Check an answer key for its type and return it tidied as (options, correct_answers).
    Raises ValueError with a message for the teacher."""
    if qtype in models.MANUAL_TYPES:
        return None, None

    if qtype in models.CHOICE_TYPES:
        items = _items(options or [], "options", "option")
        marked = correct if isinstance(correct, list) else ([] if correct in (None, "") else [correct])
        marked = list(dict.fromkeys(str(c).strip() for c in marked))
        if not marked:
            raise ValueError("Mark the correct answer.")
        if any(c not in items for c in marked):
            raise ValueError("The correct answer must be one of the options.")
        if qtype == "single_choice" and len(marked) != 1:
            raise ValueError("A single-choice question has exactly one correct answer.")
        # Stored the way older imports stored them: one value for single choice, a list for multiple
        return items, marked[0] if qtype == "single_choice" else marked

    if qtype == "true_false":
        if isinstance(correct, list) and len(correct) == 1:
            correct = correct[0]
        if isinstance(correct, bool):
            value = "true" if correct else "false"
        else:
            word = str(correct or "").strip().casefold()
            value = "true" if word in _TRUE else "false" if word in _FALSE else None
        if value is None:
            raise ValueError("Mark whether the statement is true or false.")
        return ["true", "false"], value

    if qtype == "fill_blank":
        blanks = blank_count(title)
        if isinstance(correct, (str, int, float)) and not isinstance(correct, bool) and str(correct).strip():
            correct = [[str(correct)]]
        elif isinstance(correct, list) and correct and not any(isinstance(c, list) for c in correct):
            # A flat list: the accepted answers of a one-blank question, or one answer per blank
            correct = [correct] if blanks == 1 else [[c] for c in correct]
        if not isinstance(correct, list) or not correct or not all(isinstance(c, list) for c in correct):
            raise ValueError("Give the accepted answers for each blank.")
        if len(correct) != blanks:
            raise ValueError(f"The question has {blanks} blank{'s' if blanks != 1 else ''} (___) but answers for {len(correct)}.")
        accepted = [_items(c, "accepted answers", "accepted answer", minimum=1) for c in correct]
        if any(not normalize_text(a) for answers in accepted for a in answers):
            raise ValueError("An accepted answer needs at least one letter or number.")
        return None, accepted

    if qtype == "numeric":
        raw_tolerance = 0
        if isinstance(correct, dict):
            correct, raw_tolerance = correct.get("value"), correct.get("tolerance")
        elif isinstance(correct, str) and _PLUS_MINUS.search(correct):
            correct, raw_tolerance = _PLUS_MINUS.split(correct, maxsplit=1)  # "9.8 ± 0.1" from a spreadsheet
        try:
            value = parse_number(correct)
        except (TypeError, ValueError):
            raise ValueError("Give the correct answer as a number.") from None
        try:
            tolerance = parse_number(raw_tolerance) if raw_tolerance not in (None, "") else 0.0
        except (TypeError, ValueError):
            raise ValueError("Give the margin as a number, or 0 for an exact answer.") from None
        if tolerance < 0:
            raise ValueError("The margin can't be negative.")
        return None, {"value": value, "tolerance": tolerance}

    if qtype == "matching":
        if isinstance(options, list) and all(isinstance(p, list) and len(p) == 2 for p in options):
            # Written as pairs, [[item, its match], ...]: the pairs are the key
            correct = {str(left).strip(): str(right).strip() for left, right in options}
            options = {"left": [p[0] for p in options], "right": [p[1] for p in options]}
        if not isinstance(options, dict):
            raise ValueError("Give the items and their matches as two lists.")
        left = _items(options.get("left"), "items to match", "item")
        right = _items(options.get("right"), "matches", "match", minimum=len(left), maximum=MAX_RIGHT)
        if not isinstance(correct, dict):
            raise ValueError("Pick the match for every item.")
        key = {str(k).strip(): str(v).strip() for k, v in correct.items()}
        if set(key) != set(left):
            raise ValueError("Pick the match for every item.")
        if any(v not in right for v in key.values()):
            raise ValueError("Every match must be one of the answers on the right.")
        if len(set(key.values())) != len(key):
            raise ValueError("Two items have the same match. Each match can be used once.")
        return {"left": left, "right": right}, {item: key[item] for item in left}

    if qtype == "ordering":
        items = _items(options if options not in (None, "", []) else correct, "items to put in order", "item")
        if correct not in (None, "", []):
            if not isinstance(correct, list):
                raise ValueError("Give the correct order as a list.")
            order = [str(c).strip() for c in correct]
            if sorted(order) != sorted(items):
                raise ValueError("The correct order must use the same items.")
            items = order
        return items, items

    raise ValueError(f"Type must be one of: {', '.join(models.QUESTION_TYPES)}")


# --- grading

def is_blank(answer) -> bool:
    """Whether a saved answer says nothing: no text, no choice, no photo. A blank answer earns nothing and
    needs no grading."""
    if answer is None:
        return True
    if isinstance(answer, str):
        return not answer.strip()
    if isinstance(answer, (list, tuple)):
        return all(is_blank(a) for a in answer)
    if isinstance(answer, dict):
        return all(is_blank(v) for v in answer.values())
    return False


def is_correct(qtype: str, correct, answer) -> bool | None:
    """Whether an answer matches the key; None for types staff grade."""
    if qtype in models.MANUAL_TYPES:
        return None
    if answer is None or correct is None:
        return False
    try:
        if qtype in models.CHOICE_TYPES:
            def norm(value):
                return sorted(str(v) for v in value) if isinstance(value, list) else [str(value)]
            return norm(correct) == norm(answer)
        if qtype == "true_false":
            return str(answer).strip().casefold() == correct
        if qtype == "fill_blank":
            given = answer if isinstance(answer, list) else [answer]
            return len(given) == len(correct) and all(
                g is not None and normalize_text(g) != "" and normalize_text(g) in {normalize_text(a) for a in accepted}
                for g, accepted in zip(given, correct)
            )
        if qtype == "numeric":
            # A hair of slack, so 0.1 + 0.2 counts as 0.3
            return abs(parse_number(answer) - float(correct["value"])) <= float(correct.get("tolerance") or 0) + 1e-9
        if qtype == "matching":
            return isinstance(answer, dict) and {str(k): str(v) for k, v in answer.items()} == correct
        if qtype == "ordering":
            return isinstance(answer, list) and [str(a) for a in answer] == list(correct)
    except (TypeError, ValueError, KeyError, AttributeError):
        return False
    return False


def points(question: models.Question, answer, worth: float) -> float | None:
    """What an answer earns: all of the question's marks or none. None for questions staff grade."""
    if question.type in models.MANUAL_TYPES:
        return None
    if answer is None:
        return 0.0
    return float(worth) if is_correct(question.type, question.correct_answers, answer) else 0.0


# --- what a student is sent (never the key)

def student_options(question: models.Question, seed: str, shuffle: bool):
    """The question's options as one student sees them, in an order seeded per attempt and question, so a reload
    keeps it. Ordering items and matching answers are always shuffled: their stored order is the answer."""
    options = question.options
    if question.type in models.CHOICE_TYPES and isinstance(options, list):
        items = list(options)
        if shuffle:
            random.Random(seed).shuffle(items)
        return items
    if question.type == "true_false":
        return ["true", "false"]
    if question.type == "fill_blank":
        return {"blanks": blank_count(question.title)}
    if question.type == "matching" and isinstance(options, dict):
        left, right = list(options.get("left") or []), list(options.get("right") or [])
        if shuffle:
            random.Random(f"{seed}:left").shuffle(left)
        random.Random(f"{seed}:right").shuffle(right)
        return {"left": left, "right": right}
    if question.type == "ordering" and isinstance(options, list):
        items = list(options)
        random.Random(seed).shuffle(items)
        if items == list(options) and len(items) > 1:
            items = items[1:] + items[:1]  # never hand anyone the answer by chance
        return items
    return None
