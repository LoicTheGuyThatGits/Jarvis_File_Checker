"""Making new documents: "write a cover letter for a summer job as a Word file", "make 8 slides on the water cycle",
"a budget spreadsheet for my trip to Rome", "write my revision notes on WW1 as a markdown file".

The AI model writes plain Markdown (or CSV for a spreadsheet), which small local models manage far better than JSON;
Jarvis turns that into a real Word, PowerPoint or Excel file with the standard library only.

    request(text)                 {"format": "docx"|"pptx"|"xlsx"|"md"|"txt"|"csv", "slides": n, "topic": text, "pdf": bool} or None
    prompt(req)                   (system, user) for the model
    build(req, model_text)        (file name, bytes)
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import datetime, timezone

LEAD = r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+|s['’]il\s+te\s+pla[iî]t[,]?\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?|(?:peux|pourrais)[- ]tu\s+|i\s+(?:want|need|would\s+like)\s+(?:you\s+to\s+)?|j['’]aimerais\s+(?:que\s+tu\s+)?)?"
VERB = r"(?:write|make|create|draft|generate|prepare|produce|build|put\s+together|do|give\s+me|get\s+me|set\s+up|start|écris|ecris|rédige|redige|fais|crée|cree|prépare|prepare|génère|genere)"
FORMATS = [
    ("pptx", r"\b(?:power\s?point|pptx|slides?|slide\s?show|presentation|deck|diaporama|diapos?(?:itives)?|présentation)\b"),
    ("xlsx", r"\b(?:excel|xlsx|spreadsheet|work\s?book|tableur|feuille\s+de\s+calcul|classeur)\b"),
    ("csv", r"\bcsv\b"),
    ("docx", r"\b(?:word|docx|\.doc)\b(?:\s+(?:file|document|doc|fichier))?|\bdocument\s+word\b|\bfichier\s+word\b"),
    ("pdf", r"\bpdf\b"),
    ("md", r"\b(?:markdown|\.md|md\s+file)\b"),
    ("txt", r"\b(?:text\s+file|\.txt|txt\s+file|plain\s+text\s+file|fichier\s+texte)\b"),
]
NUMBER_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
                "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "douze": 12, "quinze": 15, "vingt": 20}


def request(text: str) -> dict | None:
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(LEAD, "", t, flags=re.I).strip()
    if not t or len(t) > 1500 or not re.match(rf"{VERB}\b", t, re.I):
        return None
    if re.match(rf"{VERB}\s+(?:the|my|it|these|those|this|le|la|les|mon|ma|mes)\b[^.]*?\b(?:shorter|longer|more|less|better|bigger|smaller|simpler|clearer|plus|moins)\b", t, re.I):
        return None                         # "make the slides shorter": a change to an existing document
    fmt = None
    for name, pattern in FORMATS:
        if re.search(pattern, t, re.I):
            fmt = name
            break
    if not fmt:
        return None
    if fmt in ("docx", "xlsx", "pptx") and re.search(r"\b(?:open|launch|start|close)\s+(?:word|excel|power\s?point)\b", t, re.I):
        return None
    if re.search(r"\b(?:\w+\.(?:docx?|pptx|xlsx|pdf|txt|md))\b", t, re.I) and not re.search(r"\b(?:called|named|nommé|appelé)\b", t, re.I):
        return None                         # a file that already exists is mentioned: that is a change, not a new document
    slides = 0
    if fmt == "pptx":
        m = re.search(r"\b(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")[- ](?:\w+[- ]){0,2}?(?:slides?|diapos?(?:itives)?|pages?)\b", t, re.I)
        slides = min(20, max(2, int(m.group(1)) if m and m.group(1).isdigit() else NUMBER_WORDS.get((m.group(1) if m else "").lower(), 6)))
    pdf = fmt == "pdf"
    return {"format": "docx" if pdf else fmt, "slides": slides, "topic": t, "pdf": pdf}


def prompt(req: dict) -> tuple[str, str]:
    base = ("You write documents for the user. Write the complete content now, in the language the user wrote in, unless they ask for another. "
            "Do not ask questions; where you lack a detail (a name, a date, an address), write a short placeholder in square brackets like [Your name]. "
            "Return only the document, with no comments before or after it.")
    fmt = req["format"]
    if fmt == "pptx":
        rules = (f"Write a slide presentation of exactly {req['slides']} slides in Markdown. Start each slide with a line '## ' and its title. "
                 "Under it give 3 to 5 short bullet points starting with '- ' (a few words to one line each, not full paragraphs). "
                 "The first slide is the title slide: its '## ' line is the presentation title and under it one line of subtitle text (no bullet). ")
    elif fmt in ("xlsx", "csv"):
        rules = ("Write the spreadsheet as CSV only: commas between columns, the first row is the column headers, then one row per line. "
                 "Write numbers as plain numbers without currency signs or thousands separators (put the unit in the header, e.g. 'Cost (EUR)'). "
                 "Where a total or a calculation helps, you may write an Excel formula starting with '=' (for example =SUM(B2:B9)); quote any text that contains a comma. ")
    else:
        rules = ("Write it in Markdown: '# ' for the title, '## ' and '### ' for headings, '- ' for bullet points, '1. ' for numbered points, **bold** and *italic*, "
                 "and tables with '|' between cells (header row, then a '|---|' line). Plain paragraphs are separated by a blank line. ")
    return base + " " + rules, "The user asks: " + req["topic"]


# ---------------- reading the model's answer ----------------
def strip_fences(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    m = re.search(r"```(?:[a-z]*)\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def parse_markdown(text: str) -> list[dict]:
    """Blocks: heading (level 0-3), paragraph, bullet, number, table."""
    blocks, para, table = [], [], []

    def flush():
        nonlocal para, table
        if para:
            blocks.append({"type": "paragraph", "text": "\n".join(para)}); para = []
        if table:
            rows = [r for r in table if not re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?", r)]
            cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
            if cells:
                blocks.append({"type": "table", "rows": cells})
            table = []
    for raw in strip_fences(text).splitlines():
        line = raw.rstrip()
        s = line.strip()
        if s.startswith("|") and s.count("|") >= 2:
            if para:
                blocks.append({"type": "paragraph", "text": "\n".join(para)}); para = []
            table.append(s)
            continue
        if table:
            flush()
        if not s:
            flush(); continue
        m = re.match(r"(#{1,4})\s+(.*)", s)
        if m:
            flush(); blocks.append({"type": "heading", "level": len(m.group(1)) - 1, "text": m.group(2).strip().strip("#").strip()}); continue
        m = re.match(r"[-*•]\s+(.*)", s)
        if m and not re.match(r"\*\*[^*]+\*\*$", s):
            flush(); blocks.append({"type": "bullet", "text": m.group(1), "indent": 1 if len(line) - len(line.lstrip()) >= 2 else 0}); continue
        m = re.match(r"(\d{1,3})[.)]\s+(.*)", s)
        if m:
            flush(); blocks.append({"type": "number", "n": int(m.group(1)), "text": m.group(2)}); continue
        if re.fullmatch(r"-{3,}|\*{3,}|_{3,}", s):
            flush(); continue
        para.append(s)
    flush()
    return blocks


def inline_runs(text: str) -> list[tuple[str, bool, bool]]:
    """'a **b** *c*' -> [('a ', False, False), ('b', True, False), (' ', ...), ('c', False, True)]"""
    out = []
    for part in re.split(r"(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|__[^_]+__)", text):
        if not part:
            continue
        if (part.startswith("**") and part.endswith("**")) or (part.startswith("__") and part.endswith("__")):
            out.append((part[2:-2], True, False))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append((part[1:-1], False, True))
        else:
            out.append((part.replace("`", ""), False, False))
    return out


def plain(text: str) -> str:
    return " ".join("".join(r[0] for r in inline_runs(line)) for line in text.split("\n"))


def parse_slides(text: str, count: int) -> list[dict]:
    slides = []
    for block in parse_markdown(text):
        if block["type"] == "heading":
            slides.append({"title": plain(block["text"]), "bullets": [], "subtitle": ""})
        elif slides:
            if block["type"] in ("bullet", "number"):
                slides[-1]["bullets"].append(plain(block["text"]))
            elif block["type"] == "paragraph":
                if len(slides) == 1 and not slides[0]["subtitle"]:
                    slides[0]["subtitle"] = plain(block["text"])
                else:
                    slides[-1]["bullets"].append(plain(block["text"]))
            elif block["type"] == "table":
                slides[-1]["bullets"] += [" · ".join(r) for r in block["rows"]]
    return [s for s in slides if s["title"] or s["bullets"]][: max(count, 1) + 2]


def parse_csv(text: str) -> list[list[str]]:
    body = strip_fences(text)
    lines = [l for l in body.splitlines() if l.strip()]
    if lines and lines[0].count("|") >= 2:                        # the model gave a Markdown table instead
        return next((b["rows"] for b in parse_markdown(body) if b["type"] == "table"), [])
    rows = list(csv.reader(io.StringIO("\n".join(lines))))
    width = max((len(r) for r in rows), default=0)
    return [[c.strip() for c in r] + [""] * (width - len(r)) for r in rows if any(c.strip() for c in r)]


# ---------------- building the files ----------------
def esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def safe_name(title: str, ext: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "", plain(title or "")).strip(" .")[:60] or "Document"
    return f"{name}.{ext}"


def zip_parts(parts: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return buf.getvalue()


CORE = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:title>{title}</dc:title><dc:creator>Jarvis</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created></cp:coreProperties>')
CT_CORE = '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
REL_CORE = '<Relationship Id="rIdCore" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'


def _core(title: str) -> str:
    return CORE.format(title=esc(plain(title)), now=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


# ---- Word ----
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
DOCX_STYLES = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W}>
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Calibri" w:cs="Calibri"/><w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="en-GB"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="240"/></w:pPr><w:rPr><w:rFonts w:ascii="Calibri Light" w:hAnsi="Calibri Light"/><w:sz w:val="52"/><w:szCs w:val="52"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="360" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:color w:val="1F3864"/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:color w:val="2F5496"/><w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="200" w:after="60"/><w:outlineLvl w:val="2"/></w:pPr><w:rPr><w:b/><w:sz w:val="23"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="60"/><w:ind w:left="720" w:hanging="360"/></w:pPr></w:style>
<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:color="A6A6A6"/><w:left w:val="single" w:sz="4" w:color="A6A6A6"/><w:bottom w:val="single" w:sz="4" w:color="A6A6A6"/><w:right w:val="single" w:sz="4" w:color="A6A6A6"/><w:insideH w:val="single" w:sz="4" w:color="A6A6A6"/><w:insideV w:val="single" w:sz="4" w:color="A6A6A6"/></w:tblBorders><w:tblCellMar><w:left w:w="100" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>
</w:styles>'''


def _runs(text: str, bold_all: bool = False) -> str:
    """Runs for one paragraph; a line break inside it (a letter's address, its closing) stays a line break."""
    out = []
    for n, line in enumerate(text.split("\n")):
        if n:
            out.append("<w:r><w:br/></w:r>")
        for t, b, i in inline_runs(line):
            props = ("<w:b/>" if b or bold_all else "") + ("<w:i/>" if i else "")
            out.append(f'<w:r>{"<w:rPr>" + props + "</w:rPr>" if props else ""}<w:t xml:space="preserve">{esc(t)}</w:t></w:r>')
    return "".join(out)


def build_docx(blocks: list[dict]) -> tuple[str, bytes]:
    body, title = [], ""
    for b in blocks:
        if b["type"] == "heading":
            style = ["Title", "Heading1", "Heading2", "Heading3"][min(b["level"], 3)]
            if not title:
                title = b["text"]
            body.append(f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{_runs(b["text"])}</w:p>')
        elif b["type"] == "paragraph":
            body.append(f"<w:p>{_runs(b['text'])}</w:p>")
        elif b["type"] in ("bullet", "number"):
            mark = "•" if b["type"] == "bullet" else f"{b['n']}."
            left = 720 + 360 * b.get("indent", 0)
            body.append(f'<w:p><w:pPr><w:pStyle w:val="ListParagraph"/><w:ind w:left="{left}" w:hanging="360"/></w:pPr>'
                        f'<w:r><w:t xml:space="preserve">{mark}</w:t></w:r><w:r><w:tab/></w:r>{_runs(b["text"])}</w:p>')
        elif b["type"] == "table":
            width = max(len(r) for r in b["rows"])
            col = 9000 // max(1, width)
            rows = []
            for n, r in enumerate(b["rows"]):
                cells = "".join(f'<w:tc><w:tcPr><w:tcW w:w="{col}" w:type="dxa"/>{"<w:shd w:val=\"clear\" w:color=\"auto\" w:fill=\"D9E2F3\"/>" if n == 0 else ""}</w:tcPr>'
                                f'<w:p><w:pPr><w:spacing w:after="0"/></w:pPr>{_runs(c, bold_all=n == 0)}</w:p></w:tc>' for c in r + [""] * (width - len(r)))
                rows.append(f"<w:tr>{cells}</w:tr>")
            grid = "".join(f'<w:gridCol w:w="{col}"/>' for _ in range(width))
            body.append(f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/></w:tblPr><w:tblGrid>{grid}</w:tblGrid>{"".join(rows)}</w:tbl><w:p/>')
    if not body:
        raise ValueError("The AI model gave me nothing to put in the document.")
    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>{"".join(body)}'
           '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1417" w:right="1417" w:bottom="1134" w:left="1417" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>')
    parts = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                               '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                               '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                               '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>' + CT_CORE + '</Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>' + REL_CORE + '</Relationships>',
        "word/_rels/document.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        "word/document.xml": doc, "word/styles.xml": DOCX_STYLES, "docProps/core.xml": _core(title or "Document"),
    }
    return safe_name(title, "docx"), zip_parts(parts)


# ---- Excel ----
def _col(n: int) -> str:
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def build_xlsx(rows: list[list[str]], title: str) -> tuple[str, bytes]:
    if not rows:
        raise ValueError("The AI model gave me no rows for the spreadsheet.")
    width = max(len(r) for r in rows)
    xml_rows = []
    for i, row in enumerate(rows, 1):
        cells = []
        for j, value in enumerate(row):
            ref, v = f"{_col(j)}{i}", value.strip()
            style = ' s="1"' if i == 1 else ""
            if not v:
                continue
            if v.startswith("=") and i > 1 and len(v) > 1:
                cells.append(f'<c r="{ref}"{style}><f>{esc(v[1:])}</f></c>')
            elif re.fullmatch(r"-?\d+(?:\.\d+)?", v.replace(",", "")) and i > 1 and not re.fullmatch(r"0\d+", v):
                cells.append(f'<c r="{ref}"{style}><v>{v.replace(",", "")}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t xml:space="preserve">{esc(v)}</t></is></c>')
        xml_rows.append(f'<row r="{i}">{"".join(cells)}</row>')
    widths = [min(60, max(8, max(len(r[j]) if j < len(r) else 0 for r in rows) + 2)) for j in range(width)]
    cols = "".join(f'<col min="{j + 1}" max="{j + 1}" width="{w}" customWidth="1"/>' for j, w in enumerate(widths))
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
             f'<cols>{cols}</cols><sheetData>{"".join(xml_rows)}</sheetData></worksheet>')
    sheet_name = re.sub(r"[\\/?*\[\]:]", "", plain(title))[:31] or "Sheet1"
    parts = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                               '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                               '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                               '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                               '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' + CT_CORE + '</Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>' + REL_CORE + '</Relationships>',
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                           f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{esc(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
                           '<calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                      '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                                      '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": sheet,
        "xl/styles.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                         '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
                         '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFD9E2F3"/><bgColor indexed="64"/></patternFill></fill></fills>'
                         '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                         '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                         '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
                         '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
        "docProps/core.xml": _core(title),
    }
    return safe_name(title, "xlsx"), zip_parts(parts)


# ---- PowerPoint ----
P = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
     'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
THEME = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Jarvis"><a:themeElements>'
         '<a:clrScheme name="Jarvis"><a:dk1><a:srgbClr val="1F2328"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="1F3864"/></a:dk2><a:lt2><a:srgbClr val="E7E6E6"/></a:lt2>'
         '<a:accent1><a:srgbClr val="2F5496"/></a:accent1><a:accent2><a:srgbClr val="ED7D31"/></a:accent2><a:accent3><a:srgbClr val="A5A5A5"/></a:accent3><a:accent4><a:srgbClr val="FFC000"/></a:accent4>'
         '<a:accent5><a:srgbClr val="5B9BD5"/></a:accent5><a:accent6><a:srgbClr val="70AD47"/></a:accent6><a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme>'
         '<a:fontScheme name="Jarvis"><a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
         '<a:fmtScheme name="Jarvis"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
         '<a:lnStyleLst><a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>'
         '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
         '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme>'
         '</a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>')
SLIDE_W, SLIDE_H = 12192000, 6858000


def _sp(sid: int, name: str, ph: str, x: int, y: int, w: int, h: int, paras: str) -> str:
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="{name}"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr>{ph}</p:nvPr></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm></p:spPr><p:txBody><a:bodyPr><a:normAutofit/></a:bodyPr><a:lstStyle/>{paras}</p:txBody></p:sp>')


def _tree(shapes: str) -> str:
    return ('<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>' + shapes + '</p:spTree></p:cSld>')


def _para(text: str, size: int, bold: bool = False, bullet: bool = False, color: str = "1F2328") -> str:
    ppr = ('<a:pPr marL="342900" indent="-342900"><a:buFont typeface="Arial"/><a:buChar char="•"/></a:pPr>' if bullet else '<a:pPr><a:buNone/></a:pPr>')
    return (f'<a:p>{ppr}<a:r><a:rPr lang="en-GB" sz="{size}" b="{1 if bold else 0}" dirty="0"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:rPr>'
            f'<a:t>{esc(text)}</a:t></a:r></a:p>')


def build_pptx(slides: list[dict]) -> tuple[str, bytes]:
    if not slides:
        raise ValueError("The AI model gave me no slides.")
    margin = 609600
    layout = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldLayout {P} type="obj" preserve="1">' + _tree(
        _sp(2, "Title", '<p:ph type="title"/>', margin, 365125, SLIDE_W - 2 * margin, 1325563, '<a:p><a:endParaRPr lang="en-GB"/></a:p>')
        + _sp(3, "Content", '<p:ph idx="1"/>', margin, 1825625, SLIDE_W - 2 * margin, 4351338, '<a:p><a:endParaRPr lang="en-GB"/></a:p>'))
        + '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>')
    master = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldMaster {P}>' .replace("<p:sldMaster", "<p:sldMaster")
              + '<p:cSld><p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>' + _tree(
                  _sp(2, "Title", '<p:ph type="title"/>', margin, 365125, SLIDE_W - 2 * margin, 1325563, '<a:p><a:endParaRPr lang="en-GB"/></a:p>')
                  + _sp(3, "Content", '<p:ph type="body" idx="1"/>', margin, 1825625, SLIDE_W - 2 * margin, 4351338, '<a:p><a:endParaRPr lang="en-GB"/></a:p>'))[len("<p:cSld>"):]
              + '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
              '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
              '<p:txStyles><p:titleStyle><a:lvl1pPr><a:defRPr sz="4000"><a:latin typeface="+mj-lt"/></a:defRPr></a:lvl1pPr></p:titleStyle>'
              '<p:bodyStyle><a:lvl1pPr marL="342900" indent="-342900"><a:buChar char="•"/><a:defRPr sz="2400"><a:latin typeface="+mn-lt"/></a:defRPr></a:lvl1pPr></p:bodyStyle>'
              '<p:otherStyle><a:lvl1pPr><a:defRPr sz="1800"/></a:lvl1pPr></p:otherStyle></p:txStyles></p:sldMaster>')
    rel = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{}</Relationships>'
    R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
    parts = {
        "ppt/slideMasters/slideMaster1.xml": master,
        "ppt/slideMasters/_rels/slideMaster1.xml.rels": rel.format(f'<Relationship Id="rId1" Type="{R}slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="{R}theme" Target="../theme/theme1.xml"/>'),
        "ppt/slideLayouts/slideLayout1.xml": layout,
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels": rel.format(f'<Relationship Id="rId1" Type="{R}slideMaster" Target="../slideMasters/slideMaster1.xml"/>'),
        "ppt/theme/theme1.xml": THEME,
    }
    ids, prels, overrides = [], [f'<Relationship Id="rId1" Type="{R}slideMaster" Target="slideMasters/slideMaster1.xml"/>', f'<Relationship Id="rId2" Type="{R}theme" Target="theme/theme1.xml"/>'], []
    for n, s in enumerate(slides, 1):
        if n == 1:
            shapes = (_sp(2, "Title", '<p:ph type="title"/>', margin, 2130425, SLIDE_W - 2 * margin, 1470025, _para(s["title"], 4400, True, color="1F3864"))
                      + _sp(3, "Subtitle", '<p:ph idx="1"/>', margin, 3886200, SLIDE_W - 2 * margin, 1752600,
                            _para(s.get("subtitle") or (s["bullets"][0] if s["bullets"] else ""), 2400, color="595959")))
        else:
            bullets = "".join(_para(b, 2400 if len(s["bullets"]) <= 5 else 2000, bullet=True) for b in s["bullets"][:8]) or '<a:p><a:endParaRPr lang="en-GB"/></a:p>'
            shapes = (_sp(2, "Title", '<p:ph type="title"/>', margin, 365125, SLIDE_W - 2 * margin, 1325563, _para(s["title"], 3600, True, color="1F3864"))
                      + _sp(3, "Content", '<p:ph idx="1"/>', margin, 1825625, SLIDE_W - 2 * margin, 4351338, bullets))
        parts[f"ppt/slides/slide{n}.xml"] = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sld {P}>' + _tree(shapes) + '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>')
        parts[f"ppt/slides/_rels/slide{n}.xml.rels"] = rel.format(f'<Relationship Id="rId1" Type="{R}slideLayout" Target="../slideLayouts/slideLayout1.xml"/>')
        ids.append(f'<p:sldId id="{255 + n}" r:id="rId{n + 2}"/>')
        prels.append(f'<Relationship Id="rId{n + 2}" Type="{R}slide" Target="slides/slide{n}.xml"/>')
        overrides.append(f'<Override PartName="/ppt/slides/slide{n}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>')
    parts["ppt/presentation.xml"] = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:presentation {P} saveSubsetFonts="1">'
                                     '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
                                     f'<p:sldIdLst>{"".join(ids)}</p:sldIdLst><p:sldSz cx="{SLIDE_W}" cy="{SLIDE_H}"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>')
    parts["ppt/_rels/presentation.xml.rels"] = rel.format("".join(prels))
    parts["[Content_Types].xml"] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                                    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                                    '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
                                    '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
                                    '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
                                    '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>' + "".join(overrides) + CT_CORE + '</Types>')
    parts["_rels/.rels"] = rel.format(f'<Relationship Id="rId1" Type="{R}officeDocument" Target="ppt/presentation.xml"/>' + REL_CORE)
    parts["docProps/core.xml"] = _core(slides[0]["title"])
    order = ["[Content_Types].xml", "_rels/.rels", "docProps/core.xml", "ppt/presentation.xml", "ppt/_rels/presentation.xml.rels"]
    return safe_name(slides[0]["title"], "pptx"), zip_parts({k: parts[k] for k in order + [k for k in parts if k not in order]})


def topic_title(topic: str) -> str:
    t = re.sub(rf"^{VERB}\s+(?:me\s+)?(?:a|an|the|my|un|une|des|le|la)?\s*", "", topic, flags=re.I)
    t = re.sub(r"\s+(?:as|in|into|en|sous\s+forme\s+d['’]?)\s+(?:a\s+|an\s+|un\s+|une\s+)?(?:word|excel|power\s?point|markdown|text|csv|pdf|docx|xlsx|pptx)\b.*$", "", t, flags=re.I)
    return t.strip(" .")[:60] or "Document"


def build(req: dict, model_text: str) -> tuple[str, bytes]:
    fmt = req["format"]
    if fmt == "pptx":
        return build_pptx(parse_slides(model_text, req["slides"]))
    if fmt == "xlsx":
        return build_xlsx(parse_csv(model_text), topic_title(req["topic"]))
    if fmt == "csv":
        rows = parse_csv(model_text)
        if not rows:
            raise ValueError("The AI model gave me no rows.")
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\r\n").writerows(rows)
        return safe_name(topic_title(req["topic"]), "csv"), buf.getvalue().encode("utf-8-sig")
    if fmt in ("md", "txt"):
        text = strip_fences(model_text).strip()
        if not text:
            raise ValueError("The AI model gave me nothing to put in the file.")
        first = next((b["text"] for b in parse_markdown(text) if b["type"] == "heading"), topic_title(req["topic"]))
        if fmt == "txt":
            text = re.sub(r"^#{1,4}\s+", "", text, flags=re.M).replace("**", "")
        return safe_name(first, fmt), (text + "\n").replace("\n", "\r\n").encode("utf-8")
    return build_docx(parse_markdown(model_text))
