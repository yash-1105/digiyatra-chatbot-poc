"""Deterministic extraction of official HTML / feeds (no browser, no LLM).

Collapsed accordion answers are present in the delivered DOM (hidden by CSS / ``hidden``)
and are read from the DOM, never inferred from question headings. Pages whose answers are
only fetched by JavaScript yield questions without answers, which the validator rejects as
partial instead of reporting success.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date

import lxml.etree as etree
import lxml.html as lh

BLOCK_TAGS = {"p", "div", "section", "article", "li", "ul", "ol", "table", "tr", "td", "th", "h1", "h2", "h3",
              "h4", "h5", "h6", "br", "dd", "dt", "blockquote", "summary", "details"}
# <form> is NOT dropped: ASP.NET pages (PIB) wrap the whole document in one.
DROP_TAGS = ("script", "style", "noscript", "template", "svg", "iframe", "button[not(@aria-controls)]",
             "select", "input", "textarea", "nav", "footer")
BOILERPLATE_TOKENS = {"menu", "navbar", "nav", "navigation", "footer", "site-footer", "site-header", "breadcrumb",
                      "breadcrumbs", "social", "share", "sharing", "social-share", "cookie", "cookies", "sidebar",
                      "skip-link", "region-header", "region-footer", "header-top", "top-bar", "mega-menu",
                      "screen-reader-text", "visually-hidden", "sr-only", "back-to-top"}
BLOCKED_PAGE = re.compile(
    r"request could not be satisfied|request blocked|access denied|attention required|verify you are human|"
    r"captcha|just a moment\.\.\.|enable javascript and cookies|you don't have permission to access",
    re.I,
)
# Embedded social posts (Task 2 handles social sources); share buttons do not count.
SOCIAL_EMBED = re.compile(r"class=[\"'][^\"']*\b(?:twitter-tweet|instagram-media|fb-post|tiktok-embed)\b", re.I)

EN_MONTHS = {m: i for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
HI_MONTHS = {"जनवरी": 1, "फरवरी": 2, "फ़रवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6, "जुलाई": 7,
             "अगस्त": 8, "सितंबर": 9, "सितम्बर": 9, "अक्टूबर": 10, "अक्तूबर": 10, "नवंबर": 11, "नवम्बर": 11,
             "दिसंबर": 12, "दिसम्बर": 12}
POSTED = re.compile(r"(?:posted\s+on|पोस्ट\s+किया\s+गया|प्रविष्टि\s+तिथि)\s*:?\s*(\d{1,2})\s+([^\s\d,]+)\s*,?\s*(\d{4})", re.I)


@dataclass
class FAQ:
    question: str
    answer: str
    category: str | None
    anchor: str | None


@dataclass
class Section:
    heading: str
    text: str
    anchor: str | None


@dataclass
class Extraction:
    title: str = ""
    language: str = "en"
    published_on: str | None = None
    updated_on: str | None = None
    faqs: list[FAQ] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)
    blocked: bool = False
    social_embed: bool = False
    unanswered_questions: int = 0
    text_chars: int = 0


def clean(text: str) -> str:
    text = text.replace(" ", " ").replace("​", "")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def node_text(el) -> str:
    parts: list[str] = []

    def walk(node, root=False):
        if not isinstance(node.tag, str):
            if node.tail and not root:
                parts.append(node.tail)
            return
        block = node.tag.lower() in BLOCK_TAGS
        if block:
            parts.append("\n")
        if node.tag.lower() == "li":
            parts.append("• ")
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
        if block:
            parts.append("\n")
        if node.tail and not root:
            parts.append(node.tail)

    walk(el, root=True)
    return clean("".join(parts))


def language_of(text: str) -> str:
    letters = re.findall(r"[A-Za-zऀ-ॿ]", text)
    deva = sum(1 for c in letters if "ऀ" <= c <= "ॿ")
    return "hi" if letters and deva / len(letters) > 0.3 else "en"


def parse_date(day: str, month: str, year: str) -> str | None:
    m = month.strip(".").lower()
    num = EN_MONTHS.get(m[:3]) if re.fullmatch(r"[a-z]+", m) else HI_MONTHS.get(month.strip("."))
    try:
        return date(int(year), num, int(day)).isoformat() if num else None
    except ValueError:
        return None


def _tokens(el) -> set[str]:
    return set((el.get("class") or "").lower().split()) | {(el.get("id") or "").lower()}


def _strip_boilerplate(root) -> None:
    for xpath in DROP_TAGS:
        for el in root.xpath(f"//{xpath}"):
            el.drop_tree()
    for el in list(root.iter()):
        if not isinstance(el.tag, str) or el.getparent() is None:
            continue
        role = (el.get("role") or "").lower()
        if role in {"navigation", "banner", "contentinfo", "search"} or (
            el.tag.lower() == "header" and el.getparent() is not None and el.getparent().tag.lower() == "body"
        ) or _tokens(el) & BOILERPLATE_TOKENS:
            el.drop_tree()


def _main(root):
    for xpath in ("//main", "//*[@role='main']", "//*[@id='main-content']", "//article", "//*[contains(@class,'region-content')]"):
        found = root.xpath(xpath)
        if found:
            return found[0]
    body = root.xpath("//body")
    return body[0] if body else root


def _heading_before(el) -> str | None:
    for prev in el.itersiblings(preceding=True):
        if isinstance(prev.tag, str) and re.fullmatch(r"h[1-4]", prev.tag.lower()):
            return clean(prev.text_content())
        found = prev.xpath(".//h2|.//h3") if isinstance(prev.tag, str) else []
        if found:
            return clean(found[-1].text_content())
    parent = el.getparent()
    return _heading_before(parent) if parent is not None and parent.tag.lower() not in {"body", "main"} else None


def _category(el, root) -> str | None:
    # Tab panels: <div role="tabpanel" aria-labelledby="tab-x"> … <button id="tab-x">Category</button>
    for anc in el.iterancestors():
        if (anc.get("role") or "").lower() == "tabpanel":
            label = anc.get("aria-labelledby")
            tabs = root.xpath(f"//*[@id={json.dumps(label)}]") if label else []
            if tabs:
                return clean(tabs[0].text_content())
            if anc.get("aria-label"):
                return clean(anc.get("aria-label"))
        if _tokens(anc) & {"faq-category", "accordion-group", "faq-section"}:
            heading = anc.xpath(".//h2|.//h3")
            if heading:
                return clean(heading[0].text_content())
    return _heading_before(el)


def _jsonld_faqs(root) -> list[FAQ]:
    out: list[FAQ] = []
    for script in root.xpath("//script[@type='application/ld+json']"):
        raw = (script.text or "")[:500_000]
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop(0)
            if not isinstance(item, dict):
                continue
            stack.extend(item.get("@graph", []) if isinstance(item.get("@graph"), list) else [])
            if item.get("@type") == "FAQPage":
                for q in item.get("mainEntity", []) or []:
                    if not isinstance(q, dict):
                        continue
                    answer = (q.get("acceptedAnswer") or {}).get("text", "") if isinstance(q.get("acceptedAnswer"), dict) else ""
                    ans = clean(lh.fromstring(f"<div>{answer}</div>").text_content()) if answer else ""
                    out.append(FAQ(clean(str(q.get("name", ""))), ans, None, None))
    return out


def _dom_faqs(root) -> tuple[list[FAQ], int]:
    faqs: list[FAQ] = []
    unanswered = 0
    seen: set[str] = set()

    def add(question_el, answer_el, anchor):
        nonlocal unanswered
        q = clean(question_el.text_content()) if question_el is not None else ""
        a = node_text(answer_el) if answer_el is not None else ""
        if not q or len(q) > 600 or q.lower() in seen:
            return
        seen.add(q.lower())
        if a.startswith(q):
            a = a[len(q):].strip()
        if not a:
            unanswered += 1
        faqs.append(FAQ(q, a, _category(question_el, root), anchor))

    # 1) <details><summary>Q</summary>A…</details>
    for det in root.xpath("//details[summary]"):
        summary = det.xpath("./summary")[0]
        body = lh.fromstring("<div></div>")
        for child in det:
            if child is not summary:
                body.append(child.__copy__())
        add(summary, body, det.get("id"))
    # 2) ARIA disclosure: trigger[aria-controls=ID] -> panel#ID (works for collapsed panels)
    for trig in root.xpath("//*[@aria-controls]"):
        panel_id = trig.get("aria-controls")
        panel = root.xpath(f"//*[@id={json.dumps(panel_id)}]")
        if panel and (trig.get("aria-expanded") is not None or "accordion" in " ".join(_tokens(trig) | _tokens(panel[0]))
                      or (panel[0].get("role") or "") == "region"):
            add(trig, panel[0], panel_id)
    # 3) Common accordion widgets (Bootstrap / Elementor / WordPress blocks)
    for item in root.xpath("//*[contains(concat(' ',normalize-space(@class),' '),' accordion-item ') or "
                           "contains(@class,'elementor-accordion-item') or contains(@class,'elementor-toggle-item') or "
                           "contains(@class,'faq-item') or contains(@class,'schema-faq-section')]"):
        q = item.xpath(".//*[contains(@class,'accordion-header') or contains(@class,'accordion-button') or "
                       "contains(@class,'elementor-tab-title') or contains(@class,'faq-question') or contains(@class,'schema-faq-question')]")
        a = item.xpath(".//*[contains(@class,'accordion-body') or contains(@class,'accordion-collapse') or "
                       "contains(@class,'elementor-tab-content') or contains(@class,'faq-answer') or contains(@class,'schema-faq-answer')]")
        if q:
            add(q[0], a[0] if a else None, item.get("id"))
    # 4) Definition lists
    for dt in root.xpath("//dl/dt"):
        dd = dt.getnext()
        add(dt, dd if dd is not None and dd.tag == "dd" else None, dt.get("id"))
    return faqs, unanswered


def _sections(main, section_filter: str | None) -> list[Section]:
    sections: list[Section] = []
    heading, anchor, buf = "", None, []

    def flush():
        text = clean("\n".join(buf))
        if text and (not section_filter or re.search(section_filter, heading + " " + text[:200], re.I)):
            sections.append(Section(heading or "", text, anchor))

    for el in main.iter():
        if not isinstance(el.tag, str):
            continue
        tag = el.tag.lower()
        if re.fullmatch(r"h[1-4]", tag):
            flush()
            heading, anchor, buf = clean(el.text_content()), el.get("id"), []
        elif tag in {"p", "li", "td", "blockquote", "dd"} and not any(
            isinstance(a.tag, str) and a.tag.lower() in {"p", "li", "td", "blockquote", "dd"} for a in el.iterancestors()
        ):
            text = node_text(el)
            if text:
                buf.append(("• " if tag == "li" and not text.startswith("•") else "") + text)
        elif tag == "div" and not len(el) and el.text and el.text.strip():
            buf.append(clean(el.text))
    flush()
    return sections


def extract_html(html: str, section_filter: str | None = None) -> Extraction:
    ex = Extraction()
    if BLOCKED_PAGE.search(html[:20_000]) and len(html) < 20_000:
        ex.blocked = True
        return ex
    root = lh.document_fromstring(html)
    ex.social_embed = bool(SOCIAL_EMBED.search(html))
    for attr, target in (("article:published_time", "published_on"), ("article:modified_time", "updated_on")):
        val = root.xpath(f"//meta[@property='{attr}']/@content")
        if val and re.match(r"\d{4}-\d{2}-\d{2}", val[0]):
            setattr(ex, target, val[0][:10])
    text_all = root.text_content()
    if m := POSTED.search(" ".join(text_all.split())):
        ex.published_on = parse_date(*m.groups()) or ex.published_on
    ex.links = [(h, clean(a.text_content())) for a in root.xpath("//a[@href]") if (h := a.get("href"))]
    ex.faqs = _jsonld_faqs(root)
    _strip_boilerplate(root)
    main = _main(root)
    og = root.xpath("//meta[@property='og:title']/@content")
    headings = [clean(h.text_content()) for h in main.xpath(".//h1|.//h2")]
    page_title = root.xpath("//title/text()")
    ex.title = (og[0] if og else next((h for h in headings if h and h.lower() not in {
        "press information bureau", "ministry of civil aviation", "पत्र सूचना कार्यालय"}), "")
        or (clean(page_title[0]).split("|")[0] if page_title else ""))[:300].strip()
    dom_faqs, ex.unanswered_questions = _dom_faqs(main)
    known = {f.question.lower() for f in ex.faqs}
    ex.faqs += [f for f in dom_faqs if f.question.lower() not in known]
    ex.sections = _sections(main, section_filter)
    body = "\n".join(s.text for s in ex.sections) + "\n".join(f.question + f.answer for f in ex.faqs)
    ex.text_chars = len(body)
    ex.language = language_of(body or ex.title)
    return ex


def _first(item, *names) -> str:
    for n in names:
        el = item.find(n)
        if el is not None:
            return (el.get("href") or el.text or "").strip()
    return ""


def parse_feed(xml: bytes) -> list[tuple[str, str, str | None]]:
    """RSS/Atom items -> (link, title+description, None). Entities/network access disabled."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, recover=True)
    root = etree.fromstring(xml, parser=parser)
    items: list[tuple[str, str, str | None]] = []
    if root is None:
        return items
    atom = "{http://www.w3.org/2005/Atom}"
    for item in root.iter("item", f"{atom}entry"):
        link = _first(item, "link", f"{atom}link", "guid")
        summary = _first(item, "description", f"{atom}summary") or " "
        text = clean(_first(item, "title", f"{atom}title") + " " + lh.fromstring(f"<div>{summary}</div>").text_content())
        items.append((link, text, None))
    return items


def parse_sitemap(xml: bytes) -> list[str]:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, recover=True)
    root = etree.fromstring(xml, parser=parser)
    if root is None:
        return []
    return [el.text.strip() for el in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc", "loc") if el.text]
