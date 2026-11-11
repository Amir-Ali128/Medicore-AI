"""Bound local OCR activations without reducing source image resolution.

Full-width overlapping strips retain horizontal identity/clinical lines. Incomplete
boundary detections must have a complete counterpart, otherwise fail closed.
"""
from __future__ import annotations

import numpy as np

MAX_WIDTH = 3200
MAX_STRIP_PIXELS = 262144
MAX_HEIGHT = 12000
EDGE_MARGIN = 4


class OcrCapacityError(RuntimeError):
    pass


def _bounds(row):
    xs, ys = zip(*row[0])
    return min(xs), min(ys), max(xs), max(ys)


def _same_line(left, right):
    ax, ay, bx, by = _bounds(left)
    cx, cy, dx, dy = _bounds(right)
    overlap = max(0, min(bx, dx)-max(ax, cx))*max(0, min(by, dy)-max(ay, cy))
    return overlap / max(1, min((bx-ax)*(by-ay), (dx-cx)*(dy-cy))) > .65


class BoundedLocalOCR:
    def __init__(self, engine):
        self.engine = engine

    def __call__(self, image):
        height, width = image.shape[:2]
        if not 1 <= width <= MAX_WIDTH or not 1 <= height <= MAX_HEIGHT:
            raise OcrCapacityError('Yerel belge boyutu güvenli işlem sınırını aşıyor.')
        strip_height = min(height, max(64, MAX_STRIP_PIXELS // width))
        step = max(1, strip_height // 2)
        starts = list(range(0, max(1, height-strip_height+1), step))
        if starts[-1] + strip_height < height:
            starts.append(height-strip_height)
        complete, clipped = [], []
        for top in starts:
            bottom = min(height, top+strip_height)
            rows, _timing = self.engine(np.ascontiguousarray(image[top:bottom]))
            for row in rows or []:
                box, text, score = row[:3]
                y_values = [point[1] for point in box]
                boundary = (top > 0 and min(y_values) <= EDGE_MARGIN) or (
                    bottom < height and max(y_values) >= bottom-top-EDGE_MARGIN)
                translated = [[[float(x), float(y)+top] for x,y in box], text, score]
                (clipped if boundary else complete).append(translated)
        # Do not send an image onwards when a cut line could hide an identifier.
        if any(not any(_same_line(row, full) for full in complete) for row in clipped):
            raise OcrCapacityError('Belge satırı güvenli biçimde birleştirilemedi.')
        unique = []
        for row in sorted(complete, key=lambda item: -float(item[2])):
            if not any(_same_line(row, other) and row[1] == other[1] for other in unique):
                unique.append(row)
        unique.sort(key=lambda row: (_bounds(row)[1], _bounds(row)[0]))
        return unique or None, None
