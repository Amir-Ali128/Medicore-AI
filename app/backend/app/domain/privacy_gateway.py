"""Local, mandatory identifier redaction. No provider or network access here.

Unlabelled unknown names require a future Turkish NER layer. Unknown eleven-digit
numbers are preserved unless labelled/known; only checksum-valid TCKNs are detected
without a label (any 11 digits after a T.C./kimlik label are redacted).

Known (DB) identifiers: multi-word names, phones, e-mails, TCKNs and long record
numbers are redacted everywhere. A single name token that is also a laboratory
word (surname "Demir" vs. "Serum Demir") is kept only in clinical context, and
short purely numeric record numbers ("145") only next to a label, so lab names
and values are never wiped. ``final_leak_check`` applies the same rules.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
import io
import re
import unicodedata

PRIVACY_ERROR_CODE = 'PRIVACY_REDACTION_FAILED'
PRIVACY_MESSAGE = ('Belgedeki kişisel bilgiler güvenli biçimde silinemediği için belge yapay zekâya gönderilmedi. '
                   'Lütfen kimlik bilgilerinin görünmediği bir sürüm yükleyin.')
MAX_PAGES = 20
MAX_PIXELS = 24_000_000
MIN_OCR_CONFIDENCE = 0.60


class PrivacyViolation(Exception):
    """Safe public message; never attach input/identifiers to the exception."""
    def __init__(self) -> None:
        super().__init__(PRIVACY_MESSAGE)


class KnownIdentifier(str):
    """A DB field supplies a category without ever putting its value in logs."""
    category: str

    def __new__(cls, value: str, category: str):
        instance=super().__new__(cls,value)
        instance.category=category
        return instance


@dataclass(frozen=True)
class SanitizedText:
    text: str
    redaction_counts: dict[str, int]


@dataclass(frozen=True)
class _Span:
    start: int
    end: int
    category: str


# --------------------------------------------------------------------------
# Labels. Each entry: (category, folded regex, kind)
#   strong: also accepted with a single space before the value, but then only a
#           value of the category's exact shape is redacted ("Adı Soyadı AHMET").
#   weak:   needs ':'/'=', 2+ spaces, or a label-only line (table/next line).
# Order matters inside the alternation: longer phrases first.
# --------------------------------------------------------------------------
_LABEL_SPECS: tuple[tuple[str, str, str], ...] = (
    ('HASTA_ADI', r'hastanin\s+adi(?:\s*,?\s*soyadi)?|hasta\s+adi(?:\s*,?\s*soyadi)?|hasta\s+ad\s*,?\s*soyad|'
                  r'adi\s*,?\s*soyadi|ad\s*,?\s*soyad|ad\s+ve\s+soyadi?|isim\s+soyisim|anne\s+adi|ana\s+adi|baba\s+adi|'
                  r'patient[_ ]name|full[_ ]name|first[_ ]name|last[_ ]name|given[_ ]name|family[_ ]name', 'strong'),
    ('TCKN', r't\.?\s*c\.?\s*kimlik\s*(?:no|numarasi|numara)?\.?|t\.?\s*c\.?\s*(?:no|numarasi)\.?|tc\s*kn|tckn|'
             r'kimlik\s+(?:no|numarasi)\.?|national[_ ]id(?:entity)?(?:[_ ]number)?', 'strong'),
    ('TELEFON', r'(?:cep|ev|is|gsm|mobil)\s+tel(?:efon(?:u)?)?\.?(?:\s+(?:no|numarasi))?\.?|telefon(?:u)?(?:\s+(?:no|numarasi))?\.?|'
                r'tel\.?\s*no\.?|gsm(?:\s+no)?|tel\.?|cep|mobile|phone(?:[_ ]number)?|telephone', 'strong'),
    ('EPOSTA', r'e[ -]?posta(?:\s+adresi)?|e[ -]?mail', 'strong'),
    ('DOGUM_TARIHI', r'dogum\s+tarihi|dogum\s+t\.|d\.\s*tarihi|d\.tarihi|dogum[_ ]tarihi|date[_ ]of[_ ]birth|birth[_ ]?date|dob', 'strong'),
    ('KAYIT_NO', r'(?:dosya|protokol|kayit|hasta|basvuru|sicil|sigorta|sgk|ssk|bagkur|pasaport|passport|provizyon|takip|arsiv|barkod|barcode)'
                 r'\s*(?:no|numarasi|number|nr)\.?|sgk\s+sicil\s+no\.?|barkod|barcode|pasaport|passport', 'strong'),
    ('ADRES', r'ev\s+adresi|ikamet(?:gah)?(?:\s+adresi)?|adresi?|address|dogum\s+yeri', 'weak'),
    ('KAYIT_NO', r'filename|file_name|source_file_name|protokol', 'weak'),
    ('HASTA_ADI', r'soyadi|soyad|soyisim|adi|ad|isim|surname|hasta', 'weak'),
)
# Backwards-compatible view for callers that inspect the label table.
LABELS: dict[str, str] = {}
for _category, _pattern, _kind in _LABEL_SPECS:
    LABELS[_category] = f'{LABELS[_category]}|{_pattern}' if _category in LABELS else _pattern
_LABEL_KIND: list[tuple[re.Pattern, str, str]] = [(re.compile(p), c, k) for c, p, k in _LABEL_SPECS]
_LABEL_WORD = re.compile(r'(?<![\w\[])(?P<label>' + '|'.join(f'(?:{p})' for _, p, _ in _LABEL_SPECS) + r')(?!\w)')
_PLACEHOLDER = re.compile(r'\[(?:HASTA_ADI|TCKN|TELEFON|EPOSTA|ADRES|DOGUM_TARIHI|KAYIT_NO)\]')

_TCKN = re.compile(r'(?<!\d)[1-9]\d{10}(?!\d)')
_LABELLED_TCKN_VALUE = re.compile(r'\d{3}[ ]?\d{3}[ ]?\d{3}[ ]?\d{2}(?!\d)')
_PHONE = re.compile(
    r'(?<![\d.,])(?:'
    r'(?:\+90|0090)[ (.-]*[2-5]\d{2}'                 # international
    r'|0[ (]*5\d{2}'                                  # mobile 05xx / 0 (5xx)
    r'|0[2-4]\d{2}|\(0[2-4]\d{2}\)|0[ ]?\([2-4]\d{2}\)'  # landline 0312 / (0312) / 0 (212)
    r')[ ) .-]*\d{3}[ .-]?\d{2}[ .-]?\d{2}(?!\d)')
_EMAIL = re.compile(r'(?<![\w.+-])[\w.+-]+@[\w.-]+\.[a-z]{2,}',re.I)
_DATE = re.compile(r'(?<!\d)(?:\d{1,2}[./-]\d{1,2}[./-](?:19|20)\d{2}|(?:19|20)\d{2}[./-]\d{1,2}[./-]\d{1,2})(?!\d)')
_CLINICAL_VALUE = re.compile(r'\d+(?:[.,]\d+)?\s*(?:mg/dl|g/dl|mmol/l|mmhg|bpm|g/l|ng/ml|cm|kg)\b',re.I)
_LAB_RESULT = re.compile(
    r'\d+(?:[.,]\d+)?\s*(?:mg/dl|g/dl|mmol/l|meq/l|µg/dl|ug/dl|mcg/dl|μg/dl|ng/ml|ng/dl|pg/ml|pg|fl|iu/l|u/l|miu/ml|'
    r'uiu/ml|µiu/ml|mmhg|g/l|mg/l|µmol/l|umol/l|%|10\^\d+/[µu]l|x?10e\d+/l|/mm3|/µl|/ul)'
    r'|\b(?:normal|negatif|pozitif|reaktif|non-reaktif|yuksek|dusuk|negative|positive|high|low)\b',re.I)
_IBAN = re.compile(r'(?<!\w)TR(?:\s*\d){24}(?!\d)',re.I)
_NAME_VALUE = re.compile(r"[^\W\d_]+(?:[-'.][^\W\d_]+)*\.?(?:[ \t]+[^\W\d_]+(?:[-'.][^\W\d_]+)*\.?){0,3}")
_ID_VALUE = re.compile(r'[\w./-]*\d[\w./-]*')
_VALUE_SHAPE = {
    'HASTA_ADI': _NAME_VALUE, 'TCKN': _LABELLED_TCKN_VALUE, 'TELEFON': _PHONE,
    'EPOSTA': _EMAIL, 'DOGUM_TARIHI': _DATE, 'KAYIT_NO': _ID_VALUE,
}
_BOUNDED = {'EPOSTA': _EMAIL, 'TELEFON': _PHONE, 'TCKN': _LABELLED_TCKN_VALUE, 'DOGUM_TARIHI': _DATE}

# Medical/laboratory words that are also Turkish given names or surnames
# (Demir = iron, Taş = stone, Şeker = sugar, Kan = blood ...). A *single* known
# name token equal to one of these is kept only in clinical context. Full names,
# labelled values and every other token are always redacted.
_BUILTIN_LAB_VOCABULARY = frozenset('''
serum plazma plasma kan tam total direkt indirekt serbest free demir demiri iron baglama kapasitesi doymamis
ferritin transferrin saturasyon satürasyon tdbk uibc tibc eksikligi eksiklik anemisi anemi yuklenmesi
tedavisi destegi takviyesi profili emilimi depolari depo seker sekeri glukoz aclik tokluk sodyum potasyum
kalsiyum magnezyum fosfor cinko bakir kursun civa altin gumus selenyum protein albumin globulin hemoglobin
ure kreatinin vitamin folik asit kolesterol bilirubin hormon antikor idrar tahlili testi degeri duzeyi
seviyesi orani sayimi hemogram bobrek tasi tas safra kesesi karaciger mesane akciger kalp hastaligi
yetmezligi yuksekligi dusuklugu acil kontrol
'''.split())


def _fold_map(text: str) -> tuple[str, list[int]]:
    folded, positions = [], []
    for index, char in enumerate(text):
        if char in 'ıİ': char = 'i'
        for unit in unicodedata.normalize('NFKD',char).casefold():
            if not unicodedata.combining(unit):
                folded.append(unit); positions.append(index)
    return ''.join(folded), positions


def _fold(text: str) -> str:
    return _fold_map(text)[0]


_vocabulary_cache: tuple[int, frozenset[str]] | None = None


def _lab_vocabulary() -> frozenset[str]:
    """Builtin words + curated lab aliases already loaded by the application.

    Route modules are never imported from here; when they are loaded their alias
    table is merged. A missing table only makes redaction stricter.
    """
    global _vocabulary_cache
    import sys
    sources: list[str] = []
    try:
        from app.domain.alias_engine import _CURATED_ALIAS_TARGETS_RAW
        for canonical, aliases in _CURATED_ALIAS_TARGETS_RAW.items(): sources.extend((canonical, *aliases))
    except Exception: pass
    routes = sys.modules.get('app.api.routes.lab_analysis')
    for canonical, config in dict(getattr(routes,'LAB_PARAMETER_ALIASES',{}) or {}).items():
        sources.append(canonical)
        if isinstance(config,dict): sources.extend(str(alias) for alias in config.get('aliases',()) or ())
    if _vocabulary_cache is not None and _vocabulary_cache[0] == len(sources): return _vocabulary_cache[1]
    words = set(_BUILTIN_LAB_VOCABULARY)
    for source in sources:
        words.update(word for word in re.findall(r'[^\W\d_]{3,}',_fold(source)))
    _vocabulary_cache = (len(sources), frozenset(words))
    return _vocabulary_cache[1]


def valid_tckn(value: str) -> bool:
    if not re.fullmatch(r'[1-9]\d{10}',value): return False
    digits = list(map(int,value))
    return ((sum(digits[:9:2])*7-sum(digits[1:8:2])) % 10 == digits[9]
            and sum(digits[:10]) % 10 == digits[10])


def _identifier_category(value: str) -> str:
    if _TCKN.fullmatch(value): return 'TCKN'
    if _PHONE.fullmatch(value): return 'TELEFON'
    if _EMAIL.fullmatch(value): return 'EPOSTA'
    if _IBAN.fullmatch(value): return 'KAYIT_NO'
    if _DATE.fullmatch(value): return 'DOGUM_TARIHI'
    folded,_ = _fold_map(value)
    if re.search(r'\b(?:sokak|sok|cadde|caddesi|mahalle|mahallesi|adres|address)\b',folded): return 'ADRES'
    if any(ch.isdigit() for ch in value): return 'KAYIT_NO'
    return 'HASTA_ADI'


def _date_pattern(value: str) -> str | None:
    """Any separator/zero-padding variant of a known birth date."""
    match = re.fullmatch(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})',value) or None
    if match: year,month,day = match.groups()
    else:
        match = re.fullmatch(r'(\d{1,2})[./ -](\d{1,2})[./ -](\d{4})',value)
        if not match: return None
        day,month,year = match.groups()
    d, m = rf'0?{int(day)}', rf'0?{int(month)}'
    sep = r'\s*[./-]\s*'
    return rf'(?<!\d)(?:{d}{sep}{m}{sep}{year}|{year}{sep}{m}{sep}{d})(?!\d)'


def _line_bounds(folded: str, index: int) -> tuple[int, int]:
    start = folded.rfind('\n',0,index)+1
    end = folded.find('\n',index)
    return start, len(folded) if end < 0 else end


def _protected_name_token(folded: str, start: int, end: int, name_tokens: set[str]) -> bool:
    """A single name token that is also a lab word, used clinically ("Serum Demir")."""
    vocabulary = _lab_vocabulary()
    if folded[start:end] not in vocabulary: return False
    line_start, line_end = _line_bounds(folded,start)
    line = folded[line_start:line_end]
    for label in _LABEL_WORD.finditer(line):
        if _label_category(label)[1] == 'strong' or re.match(r'["\']?[ \t]*[:=]',line[label.end():]): return False
    before = re.findall(r'[^\W\d_]+',folded[line_start:start])
    after = re.findall(r'[^\W\d_]+',folded[end:line_end])
    neighbours = before[-1:] + after[:1]
    if any(word in name_tokens for word in neighbours): return False
    return any(word in vocabulary for word in neighbours) or bool(_LAB_RESULT.search(line))


def _known_spans(folded: str, known_identifiers: Sequence[str]) -> list[tuple[int, int, str]]:
    """Spans (in folded coordinates) of DB-known identifiers.

    * multi-word names, e-mail, phone, TCKN, addresses: everywhere;
    * single name tokens: everywhere except a lab homograph in clinical context;
    * short purely numeric record numbers (< 6 digits): only via labels, because
      "145" is also a glucose value;
    * birth dates: any separator/zero-padding variant.
    """
    full: dict[str,str] = {}
    tokens: dict[str,str] = {}
    for identifier in known_identifiers:
        value = str(identifier or '').strip()
        if not value: continue
        category = getattr(identifier,'category',None) or _identifier_category(value)
        key = ' '.join(_fold(value).split())
        if not key: continue
        if category == 'HASTA_ADI':
            parts = [part for part in re.split(r"[\s,]+",key) if len(part) >= 2]
            if len(parts) > 1: full[key] = category
            for part in parts: tokens[part] = category
            continue
        if re.fullmatch(r'\d+',key) and len(key) < 6: continue
        full[key] = category
    spans: list[tuple[int,int,str]] = []
    for key, category in full.items():
        pattern = (_date_pattern(key) if category == 'DOGUM_TARIHI' else None) or \
            (r'(?<![\w.,])' if key[:1].isdigit() else r'(?<!\w)') + r'\s+'.join(map(re.escape,key.split())) + r'(?!\w|[.,]\d)'
        spans.extend((m.start(),m.end(),category) for m in re.finditer(pattern,folded))
    name_tokens = set(tokens)
    for key, category in tokens.items():
        for m in re.finditer(r'(?<!\w)' + re.escape(key) + r'(?!\w)',folded):
            if not _protected_name_token(folded,m.start(),m.end(),name_tokens):
                spans.append((m.start(),m.end(),category))
    return spans


def _label_category(match: re.Match) -> tuple[str, str]:
    label = match['label']
    for regex, category, kind in _LABEL_KIND:
        if regex.fullmatch(label): return category, kind
    raise PrivacyViolation()  # pragma: no cover - table is static


def _value_fits(category: str, value: str) -> bool:
    shape = _VALUE_SHAPE.get(category)
    if shape is None: return True
    if category == 'HASTA_ADI': return bool(shape.fullmatch(value.strip(' \t.,;:')))
    return bool(shape.search(value))


_FOLDED_PLACEHOLDER = re.compile(r'\[(?:hasta_adi|tckn|telefon|eposta|adres|dogum_tarihi|kayit_no)\]')
_CELL = re.compile(r'\S+(?:[ ]\S+)*')


def _shaped_value(body: str, category: str, start: int, stop: int) -> tuple[int, int] | None:
    shape = _VALUE_SHAPE.get(category)
    exact = shape.match(body,start,stop) if shape else None
    if not exact: return None
    end = exact.end()
    while end > start and body[end-1] in ' \t.': end -= 1
    return (start,end) if end > start else None


def _label_spans(folded: str) -> list[tuple[int,int,str]]:
    """Label -> value pairs on folded text: inline, next line and table layouts.

    "Hasta Adi\nProtokol No\nAHMET YILMAZ\n55555" and column headers followed by
    a row of cells are paired in order; a value that clearly has another label's
    shape (digits vs. a name) is given to that label instead.
    """
    spans: list[tuple[int,int,str]] = []
    pending: list[str] = []
    offset = 0
    for raw_line in folded.split('\n'):
        line_start, offset = offset, offset+len(raw_line)+1
        body = raw_line.rstrip('\r')
        labels = list(_LABEL_WORD.finditer(body))
        header_row = bool(labels) and re.fullmatch(r'[\s:=.|/-]*',_LABEL_WORD.sub('',body)) is not None
        values: list[tuple[int,int,str]] = []   # inline (start, end, category)
        label_only: list[str] = []
        for index, match in enumerate(labels):
            category, kind = _label_category(match)
            rest = match.end()
            stop = labels[index+1].start() if index+1 < len(labels) else len(body)
            separator = re.match(r'["\']?[ \t]*[:=][ \t]*["\']?|[ \t]{2,}|\t',body[rest:stop])
            if match['label'] == 'hasta':
                # "Hasta:" also introduces clinical notes; take only a name-shaped value.
                if separator:
                    value = _shaped_value(body,'HASTA_ADI',rest+separator.end(),stop)
                    if value:
                        if _CLINICAL_VALUE.search(body[value[0]:]): raise PrivacyViolation()
                        values.append((*value,category))
                continue
            if separator:
                start = rest+separator.end()
            elif re.fullmatch(r'[ \t.:-]*',body[rest:stop]):
                start = stop
            elif kind == 'strong' and re.match(r'[ \t]\S',body[rest:stop]):
                value = _shaped_value(body,category,rest+1,stop)
                if value:
                    if category == 'HASTA_ADI' and _CLINICAL_VALUE.search(body[value[0]:]): raise PrivacyViolation()
                    values.append((*value,category))
                continue
            else:
                continue
            while start < stop and body[start] in ' \t': start += 1
            end = stop
            quote = re.search(r'["\']',body[start:end])
            if quote: end = start+quote.start()
            typed = _FOLDED_PLACEHOLDER.match(body,start,end)
            if typed: end = typed.end()
            elif category in _BOUNDED:
                exact = _BOUNDED[category].match(body,start,end)
                if exact: end = exact.end()
            while end > start and body[end-1] in ' \t,;': end -= 1
            if end <= start:
                # Only a real label row may claim the next line: "Hasta Adi:" or a
                # header made of labels only. Prose that happens to end in a label
                # word ("... dogum tarihi gibi") must not swallow the next sentence.
                if separator and re.search(r'[:=]',separator.group()) or header_row:
                    label_only.append(category)
                continue
            if _CLINICAL_VALUE.search(body[start:end]): raise PrivacyViolation()
            values.append((start,end,category))
        if values or label_only:
            spans.extend((line_start+s,line_start+e,c) for s,e,c in values)
            pending.extend(label_only)
            continue
        if not pending or not body.strip() or _FOLDED_PLACEHOLDER.fullmatch(body.strip()):
            if pending and body.strip(): pending.pop(0)
            continue
        if _CLINICAL_VALUE.search(body): raise PrivacyViolation()
        cells = list(_CELL.finditer(body))
        if len(pending) > 1 and len(cells) == len(pending) and re.search(r'\t|[ ]{2,}',body.strip()):
            spans.extend((line_start+cell.start(),line_start+cell.end(),category) for cell,category in zip(cells,pending))
            pending = []
            continue
        content = body.strip()
        choice = next((c for c in pending if _value_fits(c,content)),pending[0])
        pending.remove(choice)
        left = len(body)-len(body.lstrip())
        spans.append((line_start+left,line_start+len(body.rstrip()),choice))
    return spans


def _spans(text: str, known_identifiers: Sequence[str]) -> list[_Span]:
    folded, positions = _fold_map(text)
    spans: list[_Span] = []
    for category, regex in (('TCKN',_TCKN),('TELEFON',_PHONE),('EPOSTA',_EMAIL),('KAYIT_NO',_IBAN)):
        for match in regex.finditer(text):
            if category != 'TCKN' or valid_tckn(match.group()): spans.append(_Span(*match.span(),category))
    for start, end, category in [*_known_spans(folded,known_identifiers),*_label_spans(folded)]:
        if end > start: spans.append(_Span(positions[start],positions[end-1]+1,category))
    # Prefer the complete labelled value/full identifier, avoiding overlapping replacements.
    selected: list[_Span] = []
    for span in sorted(spans,key=lambda value:(value.start,-(value.end-value.start))):
        if selected and span.start < selected[-1].end:
            previous=selected[-1]
            selected[-1]=_Span(previous.start,max(previous.end,span.end),previous.category)
        else: selected.append(span)
    return selected


def sanitize_text(text: str, *, known_identifiers: Sequence[str] = ()) -> SanitizedText:
    if not isinstance(text,str): raise PrivacyViolation()
    spans = _spans(text,known_identifiers)
    counts = Counter(span.category for span in spans)
    for span in reversed(spans): text = text[:span.start]+f'[{span.category}]'+text[span.end:]
    return SanitizedText(text,dict(counts))


_LABELLED_TCKN_RESIDUE = re.compile(r'(?<!\w)(?:t\.?\s*c\.?\s*kimlik|tckn|tc\s*kn|kimlik\s+n)[\w.]*[^\w\n]{0,6}\d{3}[ ]?\d{3}[ ]?\d{3}[ ]?\d{2}(?!\d)')


def _pdf_text(document) -> str:
    import pymupdf
    parts = []
    for page in document:
        # Text outside the visible page box is still in the file: extract it too.
        try: parts.append(page.get_text(clip=pymupdf.INFINITE_RECT()))
        except TypeError: parts.append(page.get_text())
    return '\n'.join(parts)


def _pdf_text_outside(page) -> bool:
    import pymupdf
    try: everything=page.get_text('words',clip=pymupdf.INFINITE_RECT())
    except TypeError: return False
    area=page.rect
    return any(not area.intersects(pymupdf.Rect(word[:4])) for word in everything)


def final_leak_check(payload_text_or_bytes: str | bytes, known_identifiers: Sequence[str] = ()) -> None:
    if isinstance(payload_text_or_bytes,bytes):
        if not payload_text_or_bytes.startswith(b'%PDF'): raise PrivacyViolation()
        import pymupdf
        try:
            with pymupdf.open(stream=payload_text_or_bytes,filetype='pdf') as document:
                if document.metadata and any(document.metadata.get(key) for key in ('title','author','subject','keywords')): raise PrivacyViolation()
                if document.embfile_count() or document.get_xml_metadata(): raise PrivacyViolation()
                text=_pdf_text(document)
        except PrivacyViolation: raise
        except Exception: raise PrivacyViolation() from None
    else: text=payload_text_or_bytes
    # Labels remain useful; only their values are placeholders now.
    residual = _PLACEHOLDER.sub('',text)
    folded,_ = _fold_map(residual)
    if _known_spans(folded,known_identifiers): raise PrivacyViolation()
    if any(valid_tckn(match.group()) for match in _TCKN.finditer(residual)) or _EMAIL.search(residual) or _PHONE.search(residual) or _IBAN.search(residual):
        raise PrivacyViolation()
    if _LABELLED_TCKN_RESIDUE.search(folded): raise PrivacyViolation()


def _ocr_tokens(image, *, allow_empty: bool = False):
    """Call the existing local engine directly; its legacy helper swallows errors."""
    import numpy as np
    from app.domain.local_ocr_lab_parser import _ocr_engine, _tokens_from_result, _ocr_engine_lock
    from app.infrastructure.local_model_resources import model_lock, activate_model
    try:
        with model_lock, _ocr_engine_lock:
            activate_model("ocr")
            tokens = _tokens_from_result(_ocr_engine()(np.array(image)))
    except Exception: raise PrivacyViolation() from None
    if (not tokens and not allow_empty) or any(token.score < MIN_OCR_CONFIDENCE for token in tokens): raise PrivacyViolation()
    return tokens


def _mask_image(image, known_identifiers: Sequence[str]):
    from PIL import ImageDraw
    tokens=_ocr_tokens(image)
    # OCR returns line boxes. Join lines to detect a name wrapped across two boxes.
    ordered=sorted(tokens,key=lambda token:(round(token.y/max(token.height,1)),token.x))
    text=''; locations=[]
    for token in ordered:
        start=len(text);text+=token.text+'\n';locations.append((start,len(text)-1,token))
    spans=_spans(text,known_identifiers)
    draw=ImageDraw.Draw(image)
    counts=Counter();masked=set()
    for span in spans:
        counts[span.category]+=1
        for index,(start,end,token) in enumerate(locations):
            if span.start < end and span.end > start:
                # An OCR line box may combine identity and clinical values.
                # Never black out a lab value just to remove the adjacent name.
                local_start=max(0,span.start-start);local_end=min(len(token.text),span.end-start)
                remainder=token.text[:local_start]+token.text[local_end:]
                if _CLINICAL_VALUE.search(remainder): raise PrivacyViolation()
                masked.add(index)
                box=(max(0,token.x-token.width/2-3),max(0,token.y-token.height/2-3),
                     min(image.width,token.x+token.width/2+3),min(image.height,token.y+token.height/2+3))
                draw.rectangle(box,fill='black')
    # A second local OCR pass must not expose surviving identifiers. Empty OCR on
    # an all-redacted page is valid only after the successful initial OCR pass.
    if spans:
        remaining=_ocr_tokens(image,allow_empty=len(masked)==len(tokens))
        final_leak_check('\n'.join(token.text for token in remaining),known_identifiers)
    else: final_leak_check(text,known_identifiers)
    return image,dict(counts)


def _sanitize_image(content: bytes, media_type: str, known_identifiers: Sequence[str]):
    from PIL import Image, ImageOps
    if media_type not in ('image/png','image/jpeg','image/webp'): raise PrivacyViolation()
    try:
        with Image.open(io.BytesIO(content)) as original:
            if original.width*original.height > MAX_PIXELS or getattr(original,'n_frames',1)!=1: raise PrivacyViolation()
            oriented=ImageOps.exif_transpose(original)
            if oriented.mode in ('RGBA','LA') or 'transparency' in oriented.info:
                rgba=oriented.convert('RGBA')
                image=Image.new('RGB',rgba.size,'white')
                image.paste(rgba,mask=rgba.getchannel('A'))
                del rgba
            else:
                image=oriented.convert('RGB')
            del oriented
        image,counts=_mask_image(image,known_identifiers)
        output=io.BytesIO()
        # Preserve declared format, but never copy original info/EXIF/ICC metadata.
        image.info.clear()
        image.save(output,format={'image/png':'PNG','image/jpeg':'JPEG','image/webp':'WEBP'}[media_type])
        return output.getvalue(),counts
    except PrivacyViolation: raise
    except Exception: raise PrivacyViolation() from None


def sanitize_image(content: bytes, media_type: str, *, known_identifiers: Sequence[str] = ()) -> bytes:
    return _sanitize_image(content,media_type,known_identifiers)[0]


def _sanitize_pdf(content: bytes, known_identifiers: Sequence[str]):
    import pymupdf as fitz
    from PIL import Image
    counts=Counter()
    try:
        with fitz.open(stream=content,filetype='pdf') as document, fitz.open() as output:
            if document.needs_pass or not 1 <= len(document) <= MAX_PAGES: raise PrivacyViolation()
            for page in document:
                # Text placed outside the visible page box cannot be redacted by
                # geometry; rasterizing keeps only what is visible, then OCR-masks it.
                visible=page.get_text().strip()
                hidden=_pdf_text_outside(page)
                if page.get_images(full=True) or not visible or hidden:
                    scale=min(2.5,3200/max(page.rect.width,page.rect.height))
                    pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False)
                    image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
                    del pix
                    image,redactions=_mask_image(image,known_identifiers);counts.update(redactions)
                    buffer=io.BytesIO();image.info.clear();image.save(buffer,format='PNG')
                    rebuilt=output.new_page(width=page.rect.width,height=page.rect.height)
                    rebuilt.insert_image(rebuilt.rect,stream=buffer.getvalue())
                    continue
                # Work on character positions, not search_for: PyMuPDF's search is
                # not Turkish-diacritic insensitive and names can span visual lines.
                text=''; boxes=[]
                for block in page.get_text('rawdict')['blocks']:
                    for line in block.get('lines',[]):
                        for span in line.get('spans',[]):
                            for char in span.get('chars',[]):
                                text+=char['c'];boxes.append(char['bbox'])
                        text+='\n';boxes.append(None)
                for span in _spans(text,known_identifiers):
                    counts[span.category]+=1
                    for box in boxes[span.start:span.end]:
                        if box: page.add_redact_annot(fitz.Rect(box),fill=(0,0,0))
                page.apply_redactions()
                # Copy page content only: no document attachments, forms, links,
                # source metadata, XMP or hidden annotation payloads are retained.
                for annotation in list(page.annots() or []): page.delete_annot(annotation)
                output.insert_pdf(document,from_page=page.number,to_page=page.number,links=False,annots=False,widgets=False)
            output.set_metadata({});output.del_xml_metadata()
            sanitized=output.tobytes(garbage=4,clean=True,deflate=True)
        final_leak_check(sanitized,known_identifiers)
        return sanitized,dict(counts)
    except PrivacyViolation: raise
    except Exception: raise PrivacyViolation() from None


def sanitize_pdf(content: bytes, *, known_identifiers: Sequence[str] = ()) -> bytes:
    return _sanitize_pdf(content,known_identifiers)[0]


def age_in_years(born: date, *, today: date | None = None) -> int:
    today=today or date.today()
    if born > today: raise PrivacyViolation()
    return today.year-born.year-((today.month,today.day)<(born.month,born.day))


def relative_day(value: date, *, anchor: date) -> str:
    """Opt-in only. Existing absolute-date trend prompts are deliberately unchanged."""
    return f'gün {(value-anchor).days:+d}'
