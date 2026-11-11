"""Local, mandatory identifier redaction. No provider or network access here.

Unlabelled unknown names require a future Turkish NER layer. Unknown eleven-digit
numbers are preserved unless labelled/known; only checksum-valid TCKNs are detected.
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


LABELS = {
    'HASTA_ADI': r'hastanin\s+adi(?:\s+soyadi)?|hasta\s+adi(?:\s+soyadi)?|adi\s+soyadi|ad\s+soyad|patient[_ ]name|full[_ ]name|first[_ ]name|last[_ ]name|surname',
    'TCKN': r't\.?\s*c\.?\s*(?:kimlik(?:\s+no)?|no)|tckn|kimlik\s+no|national[_ ]id',
    'TELEFON': r'telefon|cep\s+telefonu|phone',
    'EPOSTA': r'e[ -]?posta|e[ -]?mail',
    'DOGUM_TARIHI': r'dogum\s+tarihi|dogum[_ ]tarihi|date[_ ]of[_ ]birth|birth[_ ]date|dob',
    'ADRES': r'adres|address',
    'KAYIT_NO': r'dosya\s+(?:no|numarasi)|protokol\s+(?:no|numarasi)|kayit\s+(?:no|numarasi)|hasta\s+(?:no|numarasi)|barkod|barcode|filename|file_name|source_file_name',
}
_LABEL = re.compile(r'(?<!\w)(?P<label>' + '|'.join(f'(?:{p})' for p in LABELS.values()) + r')(?!\w)(?:["\']?\s*[:=]\s*["\']?|[ \t]{2,}|[ \t]*\r?\n)',re.I)
_TCKN = re.compile(r'(?<!\d)[1-9]\d{10}(?!\d)')
_PHONE = re.compile(r'(?<!\d)(?:(?:\+90|0090)[ (.-]*[2-5]\d{2}|0[ (]*5\d{2})[ ) .-]*\d{3}[ .-]*\d{2}[ .-]*\d{2}(?!\d)')
_EMAIL = re.compile(r'(?<![\w.+-])[\w.+-]+@[\w.-]+\.[a-z]{2,}',re.I)
_CLINICAL_VALUE = re.compile(r'\d+(?:[.,]\d+)?\s*(?:mg/dl|g/dl|mmol/l|mmhg|bpm|g/l|ng/ml|cm|kg)\b',re.I)
_IBAN = re.compile(r'(?<!\w)TR(?:\s*\d){24}(?!\d)',re.I)


def _fold_map(text: str) -> tuple[str, list[int]]:
    folded, positions = [], []
    for index, char in enumerate(text):
        char = char.translate(str.maketrans('ıİ','ii'))
        for unit in unicodedata.normalize('NFKD',char).casefold():
            if not unicodedata.combining(unit):
                folded.append(unit); positions.append(index)
    return ''.join(folded), positions


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
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}|\d{2}[./-]\d{2}[./-]\d{4}',value): return 'DOGUM_TARIHI'
    folded,_ = _fold_map(value)
    if re.search(r'\b(?:sokak|sok|cadde|caddesi|mahalle|mahallesi|adres|address)\b',folded): return 'ADRES'
    if any(ch.isdigit() for ch in value): return 'KAYIT_NO'
    return 'HASTA_ADI'


def _spans(text: str, known_identifiers: Sequence[str]) -> list[_Span]:
    folded, positions = _fold_map(text)
    spans: list[_Span] = []
    for category, regex in (('TCKN',_TCKN),('TELEFON',_PHONE),('EPOSTA',_EMAIL),('KAYIT_NO',_IBAN)):
        for match in regex.finditer(text):
            if category != 'TCKN' or valid_tckn(match.group()): spans.append(_Span(*match.span(),category))
    identifiers: dict[str,str] = {}
    for identifier in known_identifiers:
        value = str(identifier or '').strip()
        if not value: continue
        category = getattr(identifier,'category',None) or _identifier_category(value)
        identifiers[value] = category
        if category == 'HASTA_ADI':
            for token in value.split():
                if len(token) >= 2: identifiers[token] = category
    for identifier, category in identifiers.items():
        key,_ = _fold_map(identifier)
        pattern = r'(?<!\w)' + r'\s+'.join(re.escape(part) for part in key.split()) + r'(?!\w)'
        for match in re.finditer(pattern,folded):
            spans.append(_Span(positions[match.start()],positions[match.end()-1]+1,category))
    labels = list(_LABEL.finditer(folded))
    for index, match in enumerate(labels):
        category = next(key for key, pattern in LABELS.items() if re.fullmatch(pattern,match['label'],re.I))
        start = match.end()
        # A value may be on the next line. Do not consume subsequent clinical lines.
        while start < len(folded) and folded[start] in ' \t': start += 1
        if start < len(folded) and folded[start] in '\r\n':
            start += 1
            while start < len(folded) and folded[start] in '\r\n \t': start += 1
        end = start
        while end < len(folded) and folded[end] not in '\r\n"\'': end += 1
        if index+1 < len(labels): end = min(end,labels[index+1].start())
        # Structured identifiers have an exact end even when a prompt flattens
        # source newlines; never absorb the following clinical observation.
        bounded={'EPOSTA':_EMAIL,'TELEFON':_PHONE,'TCKN':_TCKN}.get(category)
        typed=re.match(r'\[(?:HASTA_ADI|TCKN|TELEFON|EPOSTA|ADRES|DOGUM_TARIHI|KAYIT_NO)\]',text[positions[start]:]) if start<len(positions) else None
        if typed:
            end=min(end,start+typed.end())
        elif bounded:
            exact=bounded.match(text,positions[start]) if start<len(positions) else None
            if exact:
                # ASCII phone/e-mail/TCKN match positions are mapped back safely.
                end=min(end,next((i for i in range(start,len(positions)) if positions[i]>=exact.end()),len(positions)))
        while end > start and folded[end-1] in ' \t,;': end -= 1
        if end > start:
            if _CLINICAL_VALUE.search(folded[start:end]): raise PrivacyViolation()
            spans.append(_Span(positions[start],positions[end-1]+1,category))
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


def final_leak_check(payload_text_or_bytes: str | bytes, known_identifiers: Sequence[str] = ()) -> None:
    if isinstance(payload_text_or_bytes,bytes):
        if not payload_text_or_bytes.startswith(b'%PDF'): raise PrivacyViolation()
        import pymupdf
        try:
            with pymupdf.open(stream=payload_text_or_bytes,filetype='pdf') as document:
                text='\n'.join(page.get_text() for page in document)
        except Exception as exc: raise PrivacyViolation() from None
    else: text=payload_text_or_bytes
    # Labels remain useful; only their values are placeholders now.
    residual = re.sub(r'\[(?:HASTA_ADI|TCKN|TELEFON|EPOSTA|ADRES|DOGUM_TARIHI|KAYIT_NO)\]','',text)
    folded,_ = _fold_map(residual)
    for identifier in known_identifiers:
        value=str(identifier or '').strip()
        if not value: continue
        variants=value.split() if (getattr(identifier,'category',None) or _identifier_category(value))=='HASTA_ADI' else []
        for variant in [value,*variants]:
            key,_=_fold_map(variant)
            if key and re.search(r'(?<!\w)'+r'\s+'.join(map(re.escape,key.split()))+r'(?!\w)',folded): raise PrivacyViolation()
    if any(valid_tckn(match.group()) for match in _TCKN.finditer(residual)) or _EMAIL.search(residual) or _PHONE.search(residual) or _IBAN.search(residual):
        raise PrivacyViolation()


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
            oriented=ImageOps.exif_transpose(original).convert('RGBA')
            image=Image.new('RGBA',oriented.size,'white');image.alpha_composite(oriented)
            image=image.convert('RGB')
        image,counts=_mask_image(image,known_identifiers)
        output=io.BytesIO()
        # Preserve declared format, but never copy original info/EXIF/ICC metadata.
        clean=Image.frombytes('RGB',image.size,image.tobytes())
        clean.save(output,format={'image/png':'PNG','image/jpeg':'JPEG','image/webp':'WEBP'}[media_type])
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
                if page.get_images(full=True) or not page.get_text().strip():
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
