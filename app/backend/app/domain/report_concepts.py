"""Shared deterministic concept polarity; legacy comparator keeps its old window."""
import re
import unicodedata
from app.domain import consistency_config as cfg


def fold_text(text):
    value = unicodedata.normalize('NFKD', str(text or '')).lower()
    return ' '.join(''.join(ch for ch in value if not unicodedata.combining(ch)).split())


def concept_polarities_text(text, *, clause_scoped=False):
    transform = lambda value: str(value or '').translate(str.maketrans('ıİ', 'ii')) if clause_scoped else str(value or '')
    segments = re.split(cfg.POLARITY_CLAUSE_SPLIT, transform(text)) if clause_scoped else [text]
    polarities = {}
    for segment in segments:
        folded = fold_text(segment)
        for concept, markers in cfg.RADIOLOGY_CONCEPT_MARKERS.items():
            for raw_marker in markers:
                marker = fold_text(transform(raw_marker)); start = 0
                while True:
                    index = folded.find(marker,start)
                    if index < 0: break
                    window = ' '+folded[max(0,index-cfg.CONCEPT_WINDOW):index+len(marker)+cfg.CONCEPT_WINDOW]+' '
                    polarity = 'negative' if any(transform(neg) in window for neg in cfg.RADIOLOGY_NEGATION_MARKERS) else 'positive_or_uncertain'
                    polarities.setdefault(concept,set()).add(polarity)
                    start = index+max(1,len(marker))
    return polarities
