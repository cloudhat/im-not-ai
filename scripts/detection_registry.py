#!/usr/bin/env python3
"""Deterministic detector registry for all humanize-korean taxonomy IDs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import pstdev
from typing import Callable, Iterable


Span = tuple[int, int]


@dataclass(frozen=True)
class DetectionContext:
    genre: str
    translated: bool = False


DetectorFn = Callable[[str, DetectionContext], list[Span]]


@dataclass(frozen=True)
class Detector:
    pattern_id: str
    category: str
    severity: str
    detect: DetectorFn


def _dedupe(spans: Iterable[Span]) -> list[Span]:
    return sorted(set(spans))


def _regex(
    pattern: str,
    *,
    threshold: int = 1,
    flags: int = 0,
) -> DetectorFn:
    compiled = re.compile(pattern, flags)

    def detect(text: str, _context: DetectionContext) -> list[Span]:
        spans = _dedupe(match.span() for match in compiled.finditer(text))
        return spans if len(spans) >= threshold else []

    return detect


def _lexemes(*terms: str, threshold: int = 1) -> DetectorFn:
    return _regex("|".join(re.escape(term) for term in terms), threshold=threshold)


def _regions(text: str, separator: re.Pattern[str]) -> list[tuple[int, int, str]]:
    regions: list[tuple[int, int, str]] = []
    start = 0
    for match in separator.finditer(text):
        end = match.start()
        if text[start:end].strip():
            regions.append((start, end, text[start:end]))
        start = match.end()
    if text[start:].strip():
        regions.append((start, len(text), text[start:]))
    return regions


_PARAGRAPH_SEPARATOR = re.compile(r"\n\s*\n")
_SENTENCE_SEPARATOR = re.compile(r"(?<=[.!?。])(?:[\"'”’)]*)\s+|\n+")


def _paragraph_regex(pattern: str, *, threshold: int) -> DetectorFn:
    compiled = re.compile(pattern)

    def detect(text: str, _context: DetectionContext) -> list[Span]:
        spans: list[Span] = []
        for start, _end, paragraph in _regions(text, _PARAGRAPH_SEPARATOR):
            matches = [
                (start + match.start(), start + match.end())
                for match in compiled.finditer(paragraph)
            ]
            if len(matches) >= threshold:
                spans.extend(matches)
        return _dedupe(spans)

    return detect


def _document(predicate: Callable[[str, DetectionContext], bool]) -> DetectorFn:
    def detect(text: str, context: DetectionContext) -> list[Span]:
        if text and predicate(text, context):
            return [(0, len(text))]
        return []

    return detect


def _sentence_spans(text: str) -> list[tuple[int, int, str]]:
    return _regions(text, _SENTENCE_SEPARATOR)


def _translated_pronouns(text: str, context: DetectionContext) -> list[Span]:
    if not context.translated:
        return []
    compiled = re.compile(
        r"그녀(?:는|가|를|의|에게|와|도|만)?|"
        r"그것(?:은|이|을|의|에|에게)?|"
        r"그들(?:은|이|을|의|에게|과|도)?|"
        r"그(?:는|가|를|의|에게|와|도|만)(?=\s|[.,!?]|$)"
    )
    spans: list[Span] = []
    for start, _end, paragraph in _regions(text, _PARAGRAPH_SEPARATOR):
        matches = [
            (start + match.start(), start + match.end())
            for match in compiled.finditer(paragraph)
        ]
        if len(matches) >= 3:
            spans.extend(matches)
    return _dedupe(spans)


def _bullet_block(text: str, _context: DetectionContext) -> list[Span]:
    line_re = re.compile(r"(?m)^[ \t]*(?:[-*+] |\d+[.)] )[^\n]+$")
    matches = list(line_re.finditer(text))
    spans: list[Span] = []
    block: list[re.Match[str]] = []
    previous_end = -1
    for match in matches:
        if block and text[previous_end:match.start()].count("\n") > 1:
            if len(block) >= 3:
                spans.extend(item.span() for item in block)
            block = []
        block.append(match)
        previous_end = match.end()
    if len(block) >= 3:
        spans.extend(item.span() for item in block)
    return _dedupe(spans)


def _paragraph_opening_formula(text: str, _context: DetectionContext) -> list[Span]:
    groups = (
        re.compile(r"^\s*(먼저|첫째)"),
        re.compile(r"^\s*(반면|둘째)"),
        re.compile(r"^\s*(결국|마지막으로|셋째)"),
    )
    found: list[Span] = []
    for start, _end, paragraph in _regions(text, _PARAGRAPH_SEPARATOR):
        for group in groups:
            match = group.search(paragraph)
            if match:
                found.append((start + match.start(1), start + match.end(1)))
                break
    kinds = {
        index
        for index, group in enumerate(groups)
        if any(group.match(paragraph) for _, _, paragraph in _regions(text, _PARAGRAPH_SEPARATOR))
    }
    return _dedupe(found) if len(kinds) == 3 else []


def _comma_document(text: str, _context: DetectionContext) -> list[Span]:
    sentences = _sentence_spans(text)
    if len(sentences) < 3:
        return []
    with_comma = [(start, end) for start, end, sentence in sentences if "," in sentence]
    return with_comma if len(with_comma) / len(sentences) > 0.5 else []


def _uniform_sentence_length(text: str, _context: DetectionContext) -> list[Span]:
    sentences = _sentence_spans(text)
    lengths = [len(sentence.strip()) for _, _, sentence in sentences]
    if len(lengths) < 4 or max(lengths) >= 100 or pstdev(lengths) >= 10:
        return []
    return [(0, len(text))]


_ENDING_RE = re.compile(
    r"(?:합니다|됩니다|입니다|한다|된다|이다|했다|됐다|였다|해요|돼요|예요|한다네|하오)[.!?。]?\s*$"
)


def _ending_repetition(text: str, _context: DetectionContext) -> list[Span]:
    sentences = _sentence_spans(text)
    endings: list[tuple[int, int, str]] = []
    for start, end, sentence in sentences:
        match = _ENDING_RE.search(sentence.strip())
        if match:
            endings.append((start + match.start(), start + match.end(), match.group().rstrip(".!?。")))
        else:
            endings.append((start, start, ""))
    spans: list[Span] = []
    run: list[tuple[int, int, str]] = []
    for item in endings + [(0, 0, "")]:
        if run and item[2] != run[-1][2]:
            if run[-1][2] and len(run) >= 4:
                spans.extend((start, end) for start, end, _ in run)
            run = []
        run.append(item)
    spans.extend(match.span() for match in re.finditer(r"고\s*있(?:다|었|는|을|던|는다)", text))
    return _dedupe(spans)


def _uniform_paragraphs(text: str, _context: DetectionContext) -> list[Span]:
    paragraphs = _regions(text, _PARAGRAPH_SEPARATOR)
    if len(paragraphs) < 3:
        return []
    selected = [
        (start, end)
        for start, end, paragraph in paragraphs
        if 3 <= len(_sentence_spans(paragraph)) <= 4
    ]
    return selected if len(selected) == len(paragraphs) else []


def _short_sentence_document(text: str, _context: DetectionContext) -> list[Span]:
    sentences = _sentence_spans(text)
    if len(sentences) < 5:
        return []
    simple = [
        (start, end)
        for start, end, sentence in sentences
        if len(sentence.strip()) <= 25
        and not re.search(r"(?:지만|면서|는데|므로|거나|도록|어서|아서)", sentence)
    ]
    return simple if len(simple) / len(sentences) >= 0.8 else []


def _long_comma_segments(text: str, _context: DetectionContext) -> list[Span]:
    segments = [segment.strip() for segment in text.split(",") if segment.strip()]
    if len(segments) < 3:
        return []
    average = sum(len(segment.split()) for segment in segments) / len(segments)
    return [(0, len(text))] if average >= 8 else []


def _comma_boundary_diversity(text: str, context: DetectionContext) -> list[Span]:
    if context.genre not in {"칼럼", "리포트", "블로그", "공적"}:
        return []
    matches = list(re.finditer(r"([^\s,]{1,12}),\s*([^\s,]{1,12})", text))
    if len(matches) < 5:
        return []
    boundary_shapes = {
        (
            "ending" if re.search(r"(?:고|며|지만|면서|어서|아서)$", match.group(1)) else "other",
            "connector" if match.group(2) in {"또한", "따라서", "즉", "그러나", "하지만"} else "other",
        )
        for match in matches
    }
    return [(0, len(text))] if len(boundary_shapes) >= 3 else []


def _speech_level_mixing(text: str, _context: DetectionContext) -> list[Span]:
    styles = {
        "해라": re.compile(r"(?:한다|된다|이다|해라)[.!?。]"),
        "하게": re.compile(r"(?:하네|하게|한다네)[.!?。]"),
        "하오": re.compile(r"(?:하오|되오|이오)[.!?。]"),
        "해요": re.compile(r"(?:해요|돼요|예요|이에요)[.!?。]"),
        "합쇼": re.compile(r"(?:합니다|됩니다|입니다|습니까)[.!?。]"),
    }
    present = [compiled for compiled in styles.values() if compiled.search(text)]
    if len(present) < 2:
        return []
    return _dedupe(match.span() for compiled in present for match in compiled.finditer(text))


def _consecutive_geosida(text: str, _context: DetectionContext) -> list[Span]:
    sentences = _sentence_spans(text)
    flags = [bool(re.search(r"(?:한|할|일|는) 것이다[.!?。]?\s*$", sentence)) for _, _, sentence in sentences]
    spans: list[Span] = []
    start = 0
    while start < len(flags):
        end = start
        while end < len(flags) and flags[end]:
            end += 1
        if end - start >= 3:
            spans.extend((sentences[index][0], sentences[index][1]) for index in range(start, end))
        start = max(end, start + 1)
    return spans


def _deontic_paragraph_endings(text: str, _context: DetectionContext) -> list[Span]:
    compiled = re.compile(r"(?:해야 (?:한다|합니다)|할 필요가 있다|필요합니다)[.!?。]?\s*$")
    matches: list[Span] = []
    for start, _end, paragraph in _regions(text, _PARAGRAPH_SEPARATOR):
        match = compiled.search(paragraph)
        if match:
            matches.append((start + match.start(), start + match.end()))
    return matches[1:] if len(matches) >= 2 else []


def _bold_document(text: str, _context: DetectionContext) -> list[Span]:
    matches = list(re.finditer(r"\*\*[^*\n]+\*\*", text))
    sentences = _sentence_spans(text)
    if len(matches) < 3 or not sentences:
        return []
    touched = sum(1 for start, end, _ in sentences if any(start <= match.start() < end for match in matches))
    return [match.span() for match in matches] if touched / len(sentences) >= 0.5 else []


def _spec(pattern_id: str, severity: str, detect: DetectorFn) -> Detector:
    return Detector(pattern_id, pattern_id[0], severity, detect)


DETECTORS: tuple[Detector, ...] = (
    _spec("A-1", "S1", _regex(r"에\s*대해(?:서)?")),
    _spec("A-2", "S2", _paragraph_regex(r"(?:을|를)\s*통(?:해|하여)", threshold=3)),
    _spec("A-3", "S1", _regex(r"에\s*있어(?:서)?")),
    _spec("A-4", "S2", _regex(r"(?:라는|다는)\s*점에서", threshold=3)),
    _spec("A-5", "S2", _regex(r"(?:와|과)\s*관련(?:하여|된)")),
    _spec("A-6", "S2", _regex(r"(?:에\s*기반(?:하여|한)|(?:을|를)\s*바탕으로)", threshold=2)),
    _spec("A-7", "S1", _regex(r"(?:가지고|갖고)\s*있(?:다|습니다|는|어|었)")),
    _spec("A-8", "S1", _regex(r"(?:되어지|여지|혀지|려지|게\s*된다)")),
    _spec("A-9", "S2", _regex(r"에\s*의(?:해|하여).{0,30}?(?:된|되는|되었|됐다|받은|받는|당한|당하는|진|지는)")),
    _spec("A-10", "S2", _regex(r"[가-힣]+(?:할|될|일|릴|을)\s*수\s*있", threshold=3)),
    _spec("A-11", "S2", _regex(r"(?:을|를)\s*위해", threshold=2)),
    _spec("A-12", "S2", _regex(r"(?:만들어지|이루어지)")),
    _spec("A-13", "S2", _regex(r"(?:[가-힣A-Za-z]+\s+){4,}[가-힣]+화")),
    _spec("A-14", "S2", _regex(r"(?m)^(?:그리고)[, ]", threshold=2)),
    _spec("A-15", "S2", _regex(r"(?:등장|전략|기술|현상|변화|결과|연구|데이터|AI|인공지능)(?:은|는|이|가).{0,50}?(?:보여|제공|가져오|시사)")),
    _spec("A-16", "S1", _translated_pronouns),
    _spec("A-17", "HOLD", _regex(r"(?:기술|정보|사랑|행복|가능성|문제|현상|변화|데이터|경험)들(?:은|이|을|의|과|도)?")),
    _spec("A-18", "S2", _regex(r"(?:\S+(?:는|ㄴ|은|던|을)\s+){3,}\S+")),
    _spec("A-19", "S2", _regex(r"(?:에서의|에로의|으로의|에의|으로부터의|로부터의)")),
    _spec("B-1", "S2", _regex(r"[가-힣]{2,}\s*\([A-Za-z][A-Za-z0-9 ._-]{1,30}\)", threshold=2)),
    _spec("B-2", "S2", _lexemes("seamless", "robust", "leverage", "game changer", "best-in-class")),
    _spec("B-3", "S2", _regex(r"[\"“'][A-Za-z]+(?:\s+[A-Za-z]+){3,}[.!?]?[\"”']")),
    _spec("B-4", "S3", _regex(r"(?:라고\s*알려진|로\s*일컬어지는)")),
    _spec("C-1", "S2", _regex(r"(?:첫째|둘째|셋째|넷째)[, ]", threshold=3)),
    _spec("C-2", "S2", _bullet_block),
    _spec("C-3", "S2", _regex(r"(?m)^#{1,6}\s*(?:도입|서론|본론|결론)\s*$", threshold=2)),
    _spec("C-4", "S2", _regex(r"(?m)^(?:이 문단|이번 (?:장|절)|이 섹션)(?:에서는|은|는).{0,40}(?:다룬다|살펴본다|설명한다)", threshold=2)),
    _spec("C-5", "S1", _regex(r"[✅🚀💡⚠️📊🎯🔥✨📌🔍]")),
    _spec("C-6", "S2", _regex(r"(?m)^#{1,6}[^\n]+\n(?:이 (?:섹션|장)에서는|여기서는)[^\n]+$", threshold=2)),
    _spec("C-7", "S2", _paragraph_opening_formula),
    _spec("C-8", "S1", _regex(r"(?:[^\n.!?]{1,40}인가[, ]+[^\n.!?]{1,40}인가|[가-힣]+가\s*아니라\s*[가-힣]+)", threshold=2)),
    _spec("C-9", "S2", _regex(r"(?<!\d)\d+\)", threshold=3)),
    _spec("C-10", "S1", _regex(r"(?m)^#{1,6}\s+[^\n:]{1,80}:\s*[^\n]+", threshold=2)),
    _spec("C-11", "S1", _regex(r"(?:고|며|지만|면서|아서|어서|는데|자)\s*,")),
    _spec("C-12", "S2", _comma_document),
    _spec("D-1", "S1", _lexemes("결론적으로", "따라서", "이를 통해", "그러므로", "요약하면", "정리하자면", threshold=4)),
    _spec("D-2", "S1", _lexemes("시사하는 바가 크다", "주목할 만하다", "매우 중요하다", "의미가 크다")),
    _spec("D-3", "S1", _lexemes("크게 세 가지로 나눌 수 있다", "다음과 같은")),
    _spec("D-4", "S1", _lexemes("혁신적", "획기적", "압도적", "파격적", "폭발적", "전례 없는", threshold=3)),
    _spec("D-5", "S2", _regex(r"(?:기술|시대|변화|충돌|AI 대전|지능)(?:은|는|이|가).{0,30}?(?:묻|부르|요구|던지|증명)")),
    _spec("D-6", "S2", _regex(r"(?:할|해야 할|나아갈)\s*(?:때|시점|순간)(?:입니다|이다)[.!?。]?\s*$")),
    _spec("D-7", "S2", _regex(r"(?:[^\n.!?]{1,40}에서\s*[^\n.!?]{1,40}로|[^\n.!?]{1,40}(?:을|를)\s*넘어\s*[^\n.!?]{1,40}로)", threshold=2)),
    _spec("E-1", "S2", _uniform_sentence_length),
    _spec("E-2", "S2", _ending_repetition),
    _spec("E-3", "S2", _uniform_paragraphs),
    _spec("E-4", "S2", _short_sentence_document),
    _spec("E-5", "S2", _long_comma_segments),
    _spec("E-6", "S2", _comma_boundary_diversity),
    _spec("E-7", "S2", _speech_level_mixing),
    _spec("F-1", "S2", _lexemes("매우", "아주", "정말", "굉장히", "상당히", "극도로", threshold=4)),
    _spec("F-2", "S2", _regex(r"(?:중요하고\s*핵심적인|신속하고\s*빠른|효율적이고\s*효과적인|새롭고\s*혁신적인)")),
    _spec("F-3", "S2", _regex(r"(?:기능과\s*역할|기능\s*및\s*역할|역할과\s*기능)")),
    _spec("F-4", "S2", _regex(r"\b[가-힣A-Za-z]{2,}(?:성|적|화|tion|ment|ness|ity)(?=[^가-힣A-Za-z]|$)", threshold=13)),
    _spec("F-5", "S2", _regex(r"[가-힣]{2,}적\s+[가-힣]{2,}", threshold=3)),
    _spec("G-1", "S2", _regex(r"(?:로\s*보인다|로\s*판단된다|라고\s*여겨진다|인\s*듯하다)", threshold=3)),
    _spec("G-2", "S2", _regex(r"(?:가능성이\s*있을\s*수\s*있다|보여질\s*수\s*있다|일\s*수도\s*있을\s*것으로\s*보인다)")),
    _spec("G-3", "S2", _lexemes("양쪽 모두", "두 가지 모두", "장점도 있지만", "신중하게", "균형", threshold=4)),
    _spec("H-1", "S1", _regex(r"(?m)^(?:또한|따라서|즉|나아가|아울러|게다가|더욱이)[, ]", threshold=5)),
    _spec("H-2", "S2", _document(lambda text, _ctx: text.count("하지만") + text.count("그러나") >= 4 and "하지만" in text and "그러나" in text)),
    _spec("H-3", "S2", _regex(r"(?m)^(?:이는|이 점에서|이 관점에서|이 말은)(?:\s|,)", threshold=3)),
    _spec("H-4", "S2", _regex(r"(?m)(?:^|[.!?。]\s+)즉[, ]", threshold=3)),
    _spec("I-1", "S1", _consecutive_geosida),
    _spec("I-2", "S2", _regex(r"(?:주목할\s*점은|[가-힣A-Za-z]+은\s*[^.!?]{1,80}라는\s*점에\s*있다)")),
    _spec("I-3", "S2", _regex(r"(?:다는\s*것이다|다는\s*뜻이다)", threshold=3)),
    _spec("I-4", "S2", _deontic_paragraph_endings),
    _spec("I-5", "S2", _regex(r"(?:이|가)\s*필요하다")),
    _spec("I-6", "S2", _regex(r"[가-힣A-Za-z]+\s*능력", threshold=3)),
    _spec("J-1", "S2", _bold_document),
    _spec("J-2", "S1", _regex(r"(?:\"[^\"\n]+\"|'[^'\n]+'|“[^”\n]+”|‘[^’\n]+’)", threshold=5)),
    _spec("J-3", "S2", _regex(r"—", threshold=3)),
    _spec("J-4", "S3", _regex(r"\((?:이는|이는\s|즉|다시 말해)[^)]{3,100}\)", threshold=3)),
)


DETECTOR_BY_ID = {detector.pattern_id: detector for detector in DETECTORS}
CATEGORY_ORDER = tuple("ABCDEFGHIJ")
S1_IDS = frozenset(
    detector.pattern_id for detector in DETECTORS if detector.severity == "S1"
)
S2_IDS = frozenset(
    detector.pattern_id for detector in DETECTORS if detector.severity == "S2"
)


def validate_registry(taxonomy_ids: list[tuple[str, str]]) -> None:
    registry_ids = [(detector.pattern_id, detector.category) for detector in DETECTORS]
    if registry_ids != taxonomy_ids:
        raise ValueError(
            "taxonomy/registry ID·category 불일치: "
            f"taxonomy={taxonomy_ids!r}, registry={registry_ids!r}"
        )
    if len(DETECTOR_BY_ID) != len(DETECTORS):
        raise ValueError("registry에 중복 ID가 있다")


def count_text(text: str, context: DetectionContext) -> dict[str, int]:
    return {
        detector.pattern_id: len(_dedupe(detector.detect(text, context)))
        for detector in DETECTORS
    }
