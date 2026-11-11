from datetime import date
import io
from types import SimpleNamespace
import pytest
import pymupdf
from PIL import Image, ImageDraw, ImageFont

from app.domain import privacy_gateway as gateway
from app.domain.privacy_gateway import (
    PrivacyViolation,sanitize_text,sanitize_pdf,sanitize_image,final_leak_check,valid_tckn,
)

NAME='Ayşe Yılmazoğlu'

def fake_tckn():
    digits=list(map(int,'123456789'))
    digits.append((sum(digits[::2])*7-sum(digits[1::2]))%10)
    digits.append(sum(digits)%10)
    return ''.join(map(str,digits))


def synthetic_image():
    image=Image.new('RGB',(1000,260),'white')
    try: font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',26)
    except OSError: font=ImageFont.load_default(size=26)
    draw=ImageDraw.Draw(image)
    draw.text((30,30),'Hasta Adi: Ayse Yilmazoglu',fill='black',font=font)
    draw.text((30,120),'Hemoglobin 13.2 g/dL',fill='black',font=font)
    output=io.BytesIO();image.save(output,format='PNG');return output.getvalue()


def synthetic_pdf():
    with pymupdf.open() as document:
        page=document.new_page()
        for y,text in [(30,'Hasta Adi: Ayse Yilmazoglu'),(60,'TCKN: '+fake_tckn()),(90,'Hemoglobin 13.2 g/dL')]:page.insert_text((30,y),text)
        document.set_metadata({'author':NAME,'title':NAME,'subject':'private','keywords':'private'})
        return document.tobytes()


@pytest.mark.parametrize('variant',['Ayşe Yılmazoğlu','AYSE YILMAZOGLU','AYŞE\nYILMAZOĞLU','ayşe yılmazoğlu','Ayse','Yilmazoglu'])
def test_known_identifiers_turkish_case_tokens_and_line_break(variant):
    result=sanitize_text(variant+'\nHemoglobin 13.2 g/dL',known_identifiers=[NAME])
    assert '[HASTA_ADI]' in result.text
    assert 'Hemoglobin 13.2 g/dL' in result.text
    final_leak_check(result.text,[NAME])
    assert all(isinstance(count,int) for count in result.redaction_counts.values())
    assert NAME not in str(result.redaction_counts)


def test_every_text_category_and_non_identifying_lab_number():
    text='\n'.join(['Hasta Adı: '+NAME,'TC Kimlik No: '+fake_tckn(),'+90 555 000 00 00','0555 000 00 00','sentetik@example.invalid',
        'TR00 0000 0000 0000 0000 0000 00','Doğum Tarihi: 01.02.1980','Adres: Sentetik Sokak 12',
        'Protokol No: S-123','Barkod: ABCDEF','Hemoglobin 13.2 g/dL','12345678900'])
    result=sanitize_text(text)
    for category in ('HASTA_ADI','TCKN','TELEFON','EPOSTA','DOGUM_TARIHI','ADRES','KAYIT_NO'):assert f'[{category}]' in result.text
    assert valid_tckn(fake_tckn()) and not valid_tckn('12345678900')
    assert '12345678900' in result.text and 'Hemoglobin 13.2 g/dL' in result.text
    assert '2026-10-20' in sanitize_text('Tetkik tarihi: 2026-10-20').text
    assert fake_tckn() not in result.text


def test_label_without_colon_followed_by_name_line():
    assert NAME not in sanitize_text('Hasta Adı\n'+NAME+'\nHemoglobin 13.2 g/dL').text


def test_final_leak_check_is_independent_and_rejects_canaries():
    for text in (NAME,fake_tckn(),'sentetik@example.invalid'):
        with pytest.raises(PrivacyViolation):final_leak_check(text,[NAME])
    final_leak_check('Hemoglobin 13.2 g/dL')


def test_text_pdf_true_redaction_metadata_and_clinical_values():
    content=sanitize_pdf(synthetic_pdf(),known_identifiers=[NAME])
    final_leak_check(content,[NAME])
    with pymupdf.open(stream=content,filetype='pdf') as document:
        text=''.join(page.get_text() for page in document)
        assert 'Hemoglobin 13.2 g/dL' in text
        assert 'Yilmazoglu' not in text and fake_tckn() not in text
        assert all(not document.metadata[key] for key in ('author','title','subject','keywords','creator','producer'))
        assert not document.get_xml_metadata()


def fake_tokens(image):
    from app.domain.local_ocr_lab_parser import OcrToken
    return [OcrToken('Hasta Adi: Ayse Yilmazoglu',.99,300,50,560,55),OcrToken('Hemoglobin 13.2 g/dL',.99,260,140,480,45)]


def test_image_masks_identifier_pixels_and_removes_exif(monkeypatch):
    original=synthetic_image()
    with Image.open(io.BytesIO(original)) as image:
        exif=Image.Exif();exif[270]=NAME;exif[34853]={1:'N',2:(1,1,1)}
        data=io.BytesIO();image.save(data,format='JPEG',exif=exif)
    calls=0
    def ocr(image, **kwargs):
        nonlocal calls
        calls+=1
        return fake_tokens(image) if calls==1 else fake_tokens(image)[1:]
    monkeypatch.setattr(gateway,'_ocr_tokens',ocr)
    output=sanitize_image(data.getvalue(),'image/jpeg',known_identifiers=[NAME])
    with Image.open(io.BytesIO(output)) as image:
        assert not image.getexif() and not image.info.get('icc_profile')
        assert max(image.getpixel((200,50)))<10
        assert min(image.getpixel((900,200)))>240


def test_scanned_pdf_rebuilt_without_original_text_layer(monkeypatch):
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=1000,height=260);page.insert_image(page.rect,stream=synthetic_image());original=pdf.tobytes()
    # The synthetic document is enlarged 2.5x by rasterization.
    def ocr(image, **kwargs):
        from app.domain.local_ocr_lab_parser import OcrToken
        scale=image.width/1000
        tokens=[OcrToken(t.text,t.score,t.x*scale,t.y*scale,t.width*scale,t.height*scale) for t in fake_tokens(image)]
        return tokens[1:] if image.getpixel((int(200*scale),int(50*scale)))==(0,0,0) else tokens
    monkeypatch.setattr(gateway,'_ocr_tokens',ocr)
    content=sanitize_pdf(original,known_identifiers=[NAME])
    with pymupdf.open(stream=content,filetype='pdf') as pdf:
        assert not pdf[0].get_text()
        pix=pdf[0].get_pixmap();image=Image.open(io.BytesIO(pix.tobytes('png')))
        assert max(image.getpixel((200,50)))<10


@pytest.mark.parametrize('kind',['image','scanned_pdf'])
def test_ocr_unavailable_is_never_a_fallback(monkeypatch,kind):
    monkeypatch.setattr(gateway,'_ocr_tokens',lambda image:(_ for _ in ()).throw(PrivacyViolation()))
    if kind=='image':operation=lambda:sanitize_image(synthetic_image(),'image/png')
    else:
        with pymupdf.open() as pdf:
            page=pdf.new_page();page.insert_image(page.rect,stream=synthetic_image());content=pdf.tobytes()
        operation=lambda:sanitize_pdf(content)
    with pytest.raises(PrivacyViolation):operation()


def test_dates_and_strict_configuration():
    from app.core.config import Settings
    from pydantic import ValidationError
    assert gateway.age_in_years(date(1980,2,1),today=date(2026,1,1))==45
    assert gateway.relative_day(date(2026,2,12),anchor=date(2026,1,1))=='gün +42'
    assert Settings(_env_file=None).ai_privacy_mode=='strict'
    for mode in ('off','debug','permissive'):
        with pytest.raises(ValidationError):Settings(_env_file=None,ai_privacy_mode=mode)


def test_real_offline_ocr_masks_synthetic_identifier_without_network():
    # RapidOCR loads the bundled ONNX weights; no provider/client is constructed.
    result=sanitize_image(synthetic_image(),'image/png',known_identifiers=[NAME])
    with Image.open(io.BytesIO(result)) as image:
        assert max(image.getpixel((200,50)))<10
        assert not image.getexif()


def test_ambiguous_identity_line_with_lab_value_blocks_instead_of_erasing_clinical_data():
    with pytest.raises(PrivacyViolation):sanitize_text('Hasta Adı: Ayşe Yılmazoğlu Hemoglobin 13.2 g/dL')


def test_text_serology_pdf_reaches_mocked_provider_only_after_native_redaction(monkeypatch):
    import asyncio,base64
    from unittest.mock import AsyncMock
    from app.infrastructure.ai_privacy_client import privacy_call,private_media
    from app.domain.lab_document_normalizer import DocumentPage,provider_document
    with pymupdf.open() as pdf:
        page=pdf.new_page();page.insert_text((40,40),'Hasta Adi: Ayse Yilmazoglu\nPR3-ANCA 42 U/mL\nMPO-ANCA Negative\nAnti-GBM Negative\nANA 1:160\nC3 Normal\nC4 Normal')
        native=pdf.tobytes()
    content,kind=provider_document(DocumentPage(1,b'not-needed',native))
    def reject_ocr(*args,**kwargs):raise AssertionError('Native text privacy must not use raster OCR')
    monkeypatch.setattr(gateway,'_ocr_tokens',reject_ocr)
    sdk=AsyncMock(return_value='read-only response')
    asyncio.run(privacy_call(sdk,provider='test',call_site='synthetic-native-pdf',messages=[{
        'role':'user','content':[{'type':'document','source':{'type':'base64','media_type':kind,'data':private_media(content,kind)}}],
    }]))
    sdk.assert_awaited_once()
    clean=base64.b64decode(sdk.call_args.kwargs['messages'][0]['content'][0]['source']['data'])
    with pymupdf.open(stream=clean,filetype='pdf') as pdf:
        text='\n'.join(page.get_text() for page in pdf)
        assert 'Ayse Yilmazoglu' not in text
        assert all(value in text for value in ('PR3-ANCA 42 U/mL','MPO-ANCA Negative','Anti-GBM Negative','ANA 1:160','C3 Normal','C4 Normal'))
        assert not pdf.metadata.get('author')
