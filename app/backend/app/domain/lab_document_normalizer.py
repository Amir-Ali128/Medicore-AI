"""Bounded, source-preserving PDF/photo normalization for lab ingestion v2."""
from __future__ import annotations

from dataclasses import dataclass, field
import io
import math
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PAGES = 20
MAX_PIXELS = 24_000_000
MAX_EDGE = 2400
SUPPORTED_IMAGES = {'image/jpeg', 'image/png', 'image/webp'}


@dataclass
class DocumentPage:
    number: int
    image: bytes
    native_pdf: bytes | None = None
    warnings: list[str] = field(default_factory=list)
    operations: list[str] = field(default_factory=list)


def _perspective_crop(image: Image.Image) -> tuple[Image.Image, list[str]]:
    """Rectify a clearly bounded sheet; keep the full frame when uncertain."""
    import cv2
    import numpy as np
    cv2.setNumThreads(1)
    rgb = np.asarray(image)
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(grey, (5, 5), 0), 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = grey.shape
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        if cv2.contourArea(contour) < h * w * 0.60:
            continue
        approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        points = approx.reshape(4, 2).astype('float32')
        ordered = np.array([points[np.argmin(points.sum(1))], points[np.argmin(np.diff(points, axis=1))],
                            points[np.argmax(points.sum(1))], points[np.argmax(np.diff(points, axis=1))]], dtype='float32')
        if len(np.unique(ordered, axis=0)) != 4:
            continue
        # Never crop if apparent text extends beyond the proposed page boundary.
        mask = np.zeros_like(grey)
        cv2.fillConvexPoly(mask, approx, 255)
        outside_ink = (grey < 140) & (mask == 0)
        if outside_ink.sum() > h * w * 0.01:
            continue
        width = int(max(np.linalg.norm(ordered[1]-ordered[0]), np.linalg.norm(ordered[2]-ordered[3])))
        height = int(max(np.linalg.norm(ordered[3]-ordered[0]), np.linalg.norm(ordered[2]-ordered[1])))
        if width < 200 or height < 200:
            continue
        destination = np.array([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]], dtype='float32')
        matrix = cv2.getPerspectiveTransform(ordered, destination)
        corrected = cv2.warpPerspective(rgb, matrix, (width, height), borderValue=(255, 255, 255))
        return Image.fromarray(corrected), ['document_crop', 'perspective_correction']
    return image, []


def process_image(content: bytes, *, number: int = 1, rotation: int = 0) -> DocumentPage:
    if rotation not in {0, 90, 180, 270}:
        raise ValueError('Sayfa dönüşü 0, 90, 180 veya 270 derece olmalı.')
    try:
        with Image.open(io.BytesIO(content)) as source:
            if source.width * source.height > MAX_PIXELS:
                raise ValueError('Görüntü en fazla 24 megapiksel olabilir.')
            if getattr(source, 'n_frames', 1) != 1:
                raise ValueError('Animasyonlu veya çok kareli görüntü desteklenmiyor.')
            operations = ['exif_orientation'] if source.getexif().get(274, 1) != 1 else []
            oriented = ImageOps.exif_transpose(source).convert('RGBA')
            image = Image.new('RGBA', oriented.size, 'white')
            image.alpha_composite(oriented)
            image = image.convert('RGB')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('Görüntü dosyası okunamadı.') from exc
    if rotation:
        image = image.rotate(-rotation, expand=True, fillcolor='white')
        operations.append(f'rotation_{rotation}')
    if max(image.size) > MAX_EDGE:
        image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
        operations.append('bounded_resize')
    image, corrected = _perspective_crop(image)
    operations.extend(corrected)
    import cv2
    import numpy as np
    grey = np.asarray(image.convert('L'))
    warnings = []
    if min(image.size) < 500:
        warnings.append('low_resolution')
    if cv2.Laplacian(grey, cv2.CV_64F).var() < 35:
        warnings.append('blurred_image')
    if float(grey.std()) < 18:
        warnings.append('low_contrast')
    output = io.BytesIO()
    image.save(output, format='PNG')
    return DocumentPage(number, output.getvalue(), warnings=warnings, operations=operations)


def normalize_document(content: bytes, media_type: str, *, rotation: int = 0) -> list[DocumentPage]:
    if not content:
        raise ValueError('Belge boş.')
    if media_type in SUPPORTED_IMAGES:
        return [process_image(content, rotation=rotation)]
    if media_type != 'application/pdf':
        raise ValueError('Belge PDF, JPG, PNG veya WEBP olmalı.')
    import pymupdf
    try:
        document = pymupdf.open(stream=content, filetype='pdf')
    except Exception as exc:
        raise ValueError('PDF dosyası okunamadı.') from exc
    with document:
        if document.needs_pass:
            raise ValueError('Şifreli PDF desteklenmiyor.')
        if not 1 <= document.page_count <= MAX_PAGES:
            raise ValueError(f'Belge 1-{MAX_PAGES} sayfa içermeli; sayfalar sessizce atlanmaz.')
        pages = []
        for index, page in enumerate(document):
            # Limit rendered pixels before allocation, including unusually large PDF pages.
            width, height = page.rect.width, page.rect.height
            if width <= 0 or height <= 0 or not math.isfinite(width * height):
                raise ValueError('PDF sayfa boyutu geçersiz.')
            scale = min(2.0, MAX_EDGE / max(width, height))
            pixels = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            result = process_image(pixels.tobytes('png'), number=index + 1, rotation=rotation)
            with pymupdf.open() as single:
                single.insert_pdf(document, from_page=index, to_page=index)
                result.native_pdf = single.tobytes()
            pages.append(result)
        return pages
