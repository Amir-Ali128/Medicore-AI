from unittest.mock import Mock

import numpy as np
import pytest

from app.infrastructure.bounded_local_ocr import (
    BoundedLocalOCR, MAX_STRIP_PIXELS, MAX_WIDTH, OcrCapacityError,
)


def box(top, bottom, text='Hemoglobin 13.2 g/dL', score=.99):
    return [[[10, top], [200, top], [200, bottom], [10, bottom]], text, score]


def test_large_page_retains_pixels_and_bounds_every_inference():
    # Every source pixel is covered at full resolution, including the last row.
    image=np.zeros((2300,1654,3),dtype=np.uint8)
    indices=np.arange(2300,dtype=np.uint16)[:,None]
    image[:,:,0]=indices%256
    image[:,:,1]=indices//256
    covered=set()
    def read(strip):
        assert strip.shape[0]*strip.shape[1] <= MAX_STRIP_PIXELS
        assert strip.shape[1] == image.shape[1]
        for row in strip:covered.add(int(row[0,0])+256*int(row[0,1]))
        return None,None
    assert BoundedLocalOCR(read)(image)==(None,None)
    assert covered==set(range(2300))


def test_overlap_preserves_global_coordinates_and_deduplicates_same_line():
    image=np.zeros((400,1000,3),dtype=np.uint8)
    # starts: 0,131,138. Same original line y=160..180 seen in each strip.
    starts=iter([0,131,138])
    def read(strip):
        top=next(starts)
        return [box(160-top,180-top)],None
    rows,_=BoundedLocalOCR(read)(image)
    assert len(rows)==1
    assert rows[0][0]==[[10.,160.],[200.,160.],[200.,180.],[10.,180.]]
    assert rows[0][1]=='Hemoglobin 13.2 g/dL'


def test_distinct_recognized_values_are_not_silently_selected():
    starts=iter([0,131,138])
    def read(strip):
        top=next(starts)
        return [box(160-top,180-top,text='13.2' if top==0 else '18.2')],None
    rows,_=BoundedLocalOCR(read)(np.zeros((400,1000,3),dtype=np.uint8))
    assert {row[1] for row in rows}=={'13.2','18.2'}


def test_clipped_boundary_line_requires_complete_counterpart():
    starts=iter([0,131,138])
    def read(strip):
        top=next(starts)
        return [box(max(0,250-top),min(len(strip),275-top),'Hasta Adi: Ayse Yilmazoglu')],None
    rows,_=BoundedLocalOCR(read)(np.zeros((400,1000,3),dtype=np.uint8))
    assert len(rows)==1 and rows[0][1]=='Hasta Adi: Ayse Yilmazoglu'
    assert rows[0][0][2][1]==275


def test_unresolved_boundary_fails_closed():
    read=Mock(side_effect=[([box(250,262,'Hasta Adi: Ayse')],None),(None,None),(None,None)])
    with pytest.raises(OcrCapacityError):
        BoundedLocalOCR(read)(np.zeros((400,1000,3),dtype=np.uint8))


def test_oversize_width_never_reaches_engine():
    read=Mock()
    with pytest.raises(OcrCapacityError):
        BoundedLocalOCR(read)(np.zeros((10,MAX_WIDTH+1,3),dtype=np.uint8))
    read.assert_not_called()


def test_safe_engine_failure_is_privacy_failure(monkeypatch):
    from app.domain import privacy_gateway,local_ocr_lab_parser
    from PIL import Image
    monkeypatch.setattr(local_ocr_lab_parser,'_ocr_engine',lambda:Mock(side_effect=OcrCapacityError()))
    with pytest.raises(privacy_gateway.PrivacyViolation):
        privacy_gateway._ocr_tokens(Image.new('RGB',(100,100)))
