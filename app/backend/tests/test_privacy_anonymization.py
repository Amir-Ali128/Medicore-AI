"""Regression tests for the anonymization review findings (synthetic data only).

1. Archive PDF anonymization (metadata, attachments, annotations, forms,
   hidden/off-page text, scanned pages, phone, known names).
2. Name tokens vs. laboratory words ("Serum Demir") and short record numbers.
3. Missed identifier layouts (single-space labels, Ad/Soyad, TC label with a
   non-checksum number, Tel/GSM/Cep, landlines, tables, DOB formats ...).
4. Known identifiers from the patient context, file names, wrappers.
"""
import asyncio
import io
import json
from datetime import date
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pymupdf
import pytest

from app.domain import privacy_gateway as gateway
from app.domain.pdf_privacy import anonymize_lab_pdf
from app.domain.privacy_gateway import (
    KnownIdentifier as K, PrivacyViolation, final_leak_check, sanitize_text,
)
from app.infrastructure.ai_privacy_client import PrivacyContext, context, privacy_call
from tests.test_privacy_gateway import fake_tckn, synthetic_image

FULL = K('Ahmet Demir', 'HASTA_ADI')
LAB_LINES = (
    'Serum Demir 85 µg/dL',
    'Total Demir Bağlama Kapasitesi 310 µg/dL',
    'Doymamış Demir Bağlama Kapasitesi 225 µg/dL',
    'Demir eksikliği anemisi açısından değerlendiriniz.',
    'DEMİR 85 ug/dL',
)


def _ocr_token(text, y):
    from app.domain.local_ocr_lab_parser import OcrToken
    return OcrToken(text, .99, 300, y, 560, 40)


def _text(text, ids=()):
    return sanitize_text(text, known_identifiers=ids).text


# --------------------------------------------------------------------- 1. archive

def _hostile_pdf(*, scanned=False):
    document = pymupdf.open()
    page = document.new_page()
    if scanned:
        page.insert_image(page.rect, stream=synthetic_image())
    else:
        for y, line in [(40, 'Hasta Adi: Ahmet Yilmaz'), (60, 'Tel: 0532 111 22 33'),
                        (80, 'Hemoglobin 13.2 g/dL'), (100, 'Serum Demir 85 ug/dL')]:
            page.insert_text((40, y), line)
        page.insert_text((40, 120), 'Gizli Ahmet Yilmaz', render_mode=3)
    page.add_text_annot((200, 200), 'Ahmet Yilmaz ' + fake_tckn())
    widget = pymupdf.Widget()
    widget.field_name = 'hasta'
    widget.field_value = 'Ahmet Yilmaz'
    widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    widget.rect = pymupdf.Rect(300, 300, 450, 320)
    page.add_widget(widget)
    document.embfile_add('kimlik.txt', ('Ahmet Yilmaz ' + fake_tckn()).encode())
    document.set_metadata({'title': 'Ahmet Yilmaz ' + fake_tckn(), 'author': 'Ahmet Yilmaz',
                           'subject': 'Ahmet Yilmaz', 'keywords': fake_tckn()})
    data = document.tobytes()
    document.close()
    return data


def test_archive_pdf_drops_metadata_attachments_annotations_forms_and_hidden_text():
    result = anonymize_lab_pdf(_hostile_pdf(), known_identifiers=[K('Ahmet Yilmaz', 'HASTA_ADI')])
    final_leak_check(result.content, ['Ahmet Yilmaz', fake_tckn()])
    with pymupdf.open(stream=result.content, filetype='pdf') as pdf:
        assert all(not pdf.metadata.get(key) for key in ('title', 'author', 'subject', 'keywords', 'creator', 'producer'))
        assert not pdf.get_xml_metadata() and pdf.embfile_count() == 0
        assert not list(pdf[0].annots()) and not list(pdf[0].widgets())
        text = pdf[0].get_text()
        assert 'Yilmaz' not in text and '0532' not in text
        assert 'Hemoglobin 13.2 g/dL' in text and 'Serum Demir 85 ug/dL' in text
    for secret in (b'Yilmaz', fake_tckn().encode(), b'0532 111'):
        assert secret not in result.content
    assert result.redaction_count >= 3


def test_archive_pdf_text_outside_the_page_is_never_kept(monkeypatch):
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((40, 80), 'Hemoglobin 13.2 g/dL')
    page.insert_text((40, -50), 'Ahmet Yilmaz')  # outside the visible box
    data = document.tobytes()
    monkeypatch.setattr(gateway, '_ocr_tokens', lambda image, **kw: [_ocr_token('Hemoglobin 13.2 g/dL', 140)])
    result = anonymize_lab_pdf(data, known_identifiers=[K('Ahmet Yilmaz', 'HASTA_ADI')])
    with pymupdf.open(stream=result.content, filetype='pdf') as pdf:
        assert 'Yilmaz' not in pdf[0].get_text(clip=pymupdf.INFINITE_RECT())
    assert b'Yilmaz' not in result.content


def test_archive_pdf_masks_scanned_pages(monkeypatch):
    def ocr(image, **kwargs):
        scale = image.width / 1000
        tokens = [_ocr_token('Hasta Adi: Ayse Yilmazoglu', 50 * scale), _ocr_token('Hemoglobin 13.2 g/dL', 140 * scale)]
        return tokens[1:] if max(image.getpixel((int(200 * scale), int(50 * scale)))) < 10 else tokens
    monkeypatch.setattr(gateway, '_ocr_tokens', ocr)
    document = pymupdf.open()
    page = document.new_page(width=1000, height=260)
    page.insert_image(page.rect, stream=synthetic_image())
    result = anonymize_lab_pdf(document.tobytes())
    with pymupdf.open(stream=result.content, filetype='pdf') as pdf:
        assert not pdf[0].get_text()  # rebuilt from the masked raster only
        assert pdf.embfile_count() == 0


@pytest.mark.parametrize('content', [b'', b'not a pdf', b'%PDF-1.7 broken'])
def test_archive_pdf_keeps_value_error_contract(content):
    with pytest.raises(ValueError):
        anonymize_lab_pdf(content)


def test_archive_pdf_ocr_failure_is_a_value_error_not_a_raw_archive(monkeypatch):
    monkeypatch.setattr(gateway, '_ocr_tokens', lambda *a, **kw: (_ for _ in ()).throw(PrivacyViolation()))
    with pytest.raises(ValueError) as error:
        anonymize_lab_pdf(_hostile_pdf(scanned=True))
    assert 'Yilmaz' not in str(error.value)


def test_final_leak_check_rejects_pdf_metadata_and_attachments():
    document = pymupdf.open()
    document.new_page().insert_text((40, 40), 'Hemoglobin 13.2 g/dL')
    document.set_metadata({'author': 'Ahmet Yilmaz'})
    with pytest.raises(PrivacyViolation):
        final_leak_check(document.tobytes())
    document.set_metadata({})
    document.embfile_add('x.txt', b'x')
    with pytest.raises(PrivacyViolation):
        final_leak_check(document.tobytes())


def test_archive_route_uses_patient_identifiers_and_neutral_file_name(monkeypatch):
    from fastapi import UploadFile
    from starlette.datastructures import Headers
    from app.api.routes import lab_reports
    patient_id = uuid4()
    patient = NS(date_of_birth=date(1980, 2, 1), protocol_no=None, external_ref=None,
                 metadata_json={'identity': {'full_name': 'Ahmet Demir', 'phone': '05321112233'}})
    report = NS(patient_id=patient_id, file_name=None, metadata_json={})
    session = NS(get=AsyncMock(return_value=patient), execute=AsyncMock(), commit=AsyncMock(), refresh=AsyncMock())
    monkeypatch.setattr(lab_reports, '_ensure_lab_file_columns', AsyncMock())
    monkeypatch.setattr(lab_reports, '_ensure_report_access', AsyncMock())
    document = pymupdf.open()
    page = document.new_page()
    # Unlabelled name: only the patient context can find it.
    for y, line in [(40, 'Sayin Ahmet Demir'), (60, 'Serum Demir 85 ug/dL'), (80, '01.02.1980 dogumlu')]:
        page.insert_text((40, y), line)
    upload = UploadFile(io.BytesIO(document.tobytes()), filename='Ahmet_Demir_tahlil.pdf',
                        headers=Headers({'content-type': 'application/pdf'}))
    asyncio.run(lab_reports.store_lab_report_original_file(
        uuid4(), NS(get_by_id=AsyncMock(return_value=report)), session, NS(), upload))
    stored = session.execute.call_args.args[1]['content']
    with pymupdf.open(stream=stored, filetype='pdf') as pdf:
        text = pdf[0].get_text()
    assert 'Ahmet' not in text and 'Sayin Ahmet' not in text and '1980' not in text
    assert 'Serum Demir 85 ug/dL' in text
    assert report.file_name == 'laboratuvar-raporu.pdf'


# ---------------------------------------------- 2. name tokens vs. lab vocabulary

@pytest.mark.parametrize('line', LAB_LINES)
def test_surname_token_never_wipes_laboratory_names(line):
    result = _text('Hasta Adı: Ahmet Demir\n' + line, [FULL])
    assert result.startswith('Hasta Adı: [HASTA_ADI]')
    assert result.endswith(line)
    final_leak_check(result, [FULL])  # must not raise on "Serum Demir"


@pytest.mark.parametrize('text', ['Sayın Demir kontrole gelmeli.', 'Demir 45 yaşında', 'DEMIR, Ahmet',
                                  'Ahmet Bey', "Ahmet'in şikayetleri", 'Hasta: Demir'])
def test_name_tokens_outside_clinical_context_are_redacted(text):
    result = _text(text, [FULL])
    assert 'Ahmet' not in result and 'Demir' not in result.replace('[HASTA_ADI]', '')
    with pytest.raises(PrivacyViolation):
        final_leak_check(text, [FULL])


def test_surname_only_identifier_is_treated_as_a_token():
    ids = [K('Demir', 'HASTA_ADI')]
    assert _text('Serum Demir 85 µg/dL', ids) == 'Serum Demir 85 µg/dL'
    assert _text('Sayın Demir', ids) == 'Sayın [HASTA_ADI]'
    assert _text('Hasta Adı: Demir', ids) == 'Hasta Adı: [HASTA_ADI]'


def test_ocr_image_with_lab_homograph_is_not_blocked(monkeypatch):
    calls = []
    def ocr(image, **kwargs):
        calls.append(1)
        tokens = [_ocr_token('Hasta Adi: Ahmet Demir', 50), _ocr_token('Serum Demir 85 ug/dL', 140)]
        return tokens if len(calls) == 1 else tokens[1:]
    monkeypatch.setattr(gateway, '_ocr_tokens', ocr)
    gateway.sanitize_image(synthetic_image(), 'image/png', known_identifiers=[FULL])


def test_short_numeric_record_number_does_not_redact_lab_values():
    ids = [K('145', 'KAYIT_NO'), K('SYN-145', 'KAYIT_NO'), K('5551234', 'KAYIT_NO')]
    result = _text('Glukoz 145 mg/dL\nProtokol No: 145\nKayıt SYN-145\nArşiv 5551234\nLDL 145', ids)
    assert 'Glukoz 145 mg/dL' in result and 'LDL 145' in result
    assert 'Protokol No: [KAYIT_NO]' in result
    assert 'SYN-145' not in result and '5551234' not in result
    final_leak_check('Glukoz 145 mg/dL', ids)


# ------------------------------------------------------ 3. missed identifiers

@pytest.mark.parametrize('text,secret,category', [
    ('Adı Soyadı AHMET YILMAZ', 'AHMET', 'HASTA_ADI'),
    ('Hasta Adı Soyadı Ahmet Yılmaz', 'Yılmaz', 'HASTA_ADI'),
    ('Adı: Ahmet', 'Ahmet', 'HASTA_ADI'),
    ('Soyadı: Yılmaz', 'Yılmaz', 'HASTA_ADI'),
    ('Ad: Ahmet', 'Ahmet', 'HASTA_ADI'),
    ('Soyad: Yılmaz', 'Yılmaz', 'HASTA_ADI'),
    ('Baba Adı: Veli', 'Veli', 'HASTA_ADI'),
    ('Anne Adı: Fatma', 'Fatma', 'HASTA_ADI'),
    ('Hasta: Ahmet Yılmaz', 'Ahmet', 'HASTA_ADI'),
    ('T.C. Kimlik Numarası: 12345678900', '12345678900', 'TCKN'),
    ('TC Kimlik No 12345678900', '12345678900', 'TCKN'),
    ('T.C. No: 123 456 789 00', '789', 'TCKN'),
    ('Tel: 0532 111 22 33', '111 22 33', 'TELEFON'),
    ('Tel No 0312 444 55 66', '444 55 66', 'TELEFON'),
    ('GSM 05321112233', '05321112233', 'TELEFON'),
    ('Cep: 0 (532) 111 22 33', '111 22 33', 'TELEFON'),
    ('İletişim 0312 444 55 66', '444 55 66', 'TELEFON'),
    ('Telefon (0312) 444 55 66', '444 55 66', 'TELEFON'),
    ('Ev 0 (212) 555 66 77', '555 66 77', 'TELEFON'),
    ('Doğum Yeri: Ankara', 'Ankara', 'ADRES'),
    ('SGK No: 12345', '12345', 'KAYIT_NO'),
    ('Sigorta No 99887766', '99887766', 'KAYIT_NO'),
    ('Pasaport No: U1234567', 'U1234567', 'KAYIT_NO'),
    ('Barkod 998877', '998877', 'KAYIT_NO'),
    ('Doğum Tarihi: 1.2.1980', '1980', 'DOGUM_TARIHI'),
    ('Doğum Tarihi 01-02-1980', '1980', 'DOGUM_TARIHI'),
    ('D.Tarihi: 1/2/1980', '1980', 'DOGUM_TARIHI'),
    ('E-posta ahmet@example.invalid', 'ahmet@', 'EPOSTA'),
])
def test_labelled_identifiers_without_patient_context(text, secret, category):
    result = _text(text + '\nHemoglobin 13.2 g/dL')
    assert secret not in result, result
    assert f'[{category}]' in result and result.endswith('Hemoglobin 13.2 g/dL')


def test_birth_date_label_does_not_swallow_following_fields():
    assert _text('Doğum Tarihi: 1.2.1980 Cinsiyet: K') == 'Doğum Tarihi: [DOGUM_TARIHI] Cinsiyet: K'


def test_labelled_tc_number_is_redacted_even_without_valid_checksum_and_final_check_catches_it():
    assert not gateway.valid_tckn('12345678900')
    assert '12345678900' not in _text('T.C. Kimlik Numarası: 12345678900')
    with pytest.raises(PrivacyViolation):
        final_leak_check('T.C. Kimlik Numarası: 12345678900')
    final_leak_check('Referans 12345678900')  # unlabelled lab/accession numbers stay allowed


def test_doctor_names_and_clinical_text_are_kept():
    text = 'İsteyen Dr: Ali Veli\nOnaylayan: Uzm. Dr. Zeynep Kaya\nHasta: 45 yaşında erkek, ateş yüksek'
    assert _text(text) == text


@pytest.mark.parametrize('text', [
    'Hasta Adı\nProtokol No\nAHMET YILMAZ\n55555\nHemoglobin 13.2 g/dL',
    'Hasta Adı\nProtokol No\n55555\nAHMET YILMAZ\nHemoglobin 13.2 g/dL',
    'Hasta Adı        Protokol No\nAHMET YILMAZ      55555\nHemoglobin 13.2 g/dL',
    'Hasta Adı\tProtokol No\nAHMET YILMAZ\t55555\nHemoglobin 13.2 g/dL',
    'Adı Soyadı :\nAHMET YILMAZ\nProtokol No :\n55555\nHemoglobin 13.2 g/dL',
])
def test_table_and_next_line_layouts_pair_labels_with_values(text):
    result = sanitize_text(text)
    assert 'AHMET' not in result.text and '55555' not in result.text
    assert result.redaction_counts == {'HASTA_ADI': 1, 'KAYIT_NO': 1}
    assert result.text.endswith('Hemoglobin 13.2 g/dL')


def test_labels_followed_directly_by_clinical_value_fail_closed():
    with pytest.raises(PrivacyViolation):
        sanitize_text('Adı Soyadı AHMET YILMAZ Hemoglobin 13.2 g/dL')
    with pytest.raises(PrivacyViolation):
        sanitize_text('Hasta Adı\nHemoglobin 13.2 g/dL')


@pytest.mark.parametrize('text', [
    'Trombosit 250 10^3/uL 150 - 400',
    'Tetkik tarihi: 2026-10-20',
    'Numune 0 200 100 10 10',
    'Referans 0.312 - 0.444',
    'TSH 2.5 mIU/L',
    '{"labs":[{"name":"Hemoglobin","value":13.2,"unit":"g/dL"}]}',
])
def test_non_identifying_clinical_text_is_untouched(text):
    assert _text(text) == text
    final_leak_check(text)


# ------------------------------------- 4. patient context, file names, wrappers

@pytest.mark.parametrize('variant', ['01.02.1980', '1.2.1980', '01-02-1980', '1980-02-01', '1/2/1980'])
def test_known_birth_date_any_format(variant):
    ids = [K('1980-02-01', 'DOGUM_TARIHI')]
    assert '1980' not in _text('Kayıt ' + variant, ids)
    with pytest.raises(PrivacyViolation):
        final_leak_check(variant, ids)


def test_db_loader_includes_birth_date_variants_and_identity_fields():
    from app.infrastructure.ai_privacy_context import load_patient_identifiers
    patient = NS(date_of_birth=date(1980, 2, 1), protocol_no='145', external_ref=None,
                 metadata_json={'identity': {'full_name': 'Ahmet Demir', 'phone': '05321112233'}})
    privacy = asyncio.run(load_patient_identifiers(NS(get=AsyncMock(return_value=patient)), uuid4()))
    text = 'Sayın Ahmet Demir, 1.2.1980\nSerum Demir 85 µg/dL\nGlukoz 145 mg/dL\nProtokol No: 145\n0532 111 22 33'
    result = _text(text, privacy.known_identifiers)
    assert 'Ahmet' not in result and '1980' not in result and '0532' not in result
    assert 'Serum Demir 85 µg/dL' in result and 'Glukoz 145 mg/dL' in result
    assert 'Protokol No: [KAYIT_NO]' in result


def test_file_names_are_redacted_without_patient_context():
    sdk = AsyncMock()
    asyncio.run(privacy_call(sdk, provider='test', call_site='synthetic', input=[
        {'type': 'input_text', 'text': 'SOURCE 1 filename: ahmet_yilmaz_hemogram.pdf'},
        {'type': 'input_file', 'filename': 'Ahmet Yılmaz.pdf'},
    ]))
    sent = json.dumps(sdk.call_args.kwargs, ensure_ascii=False).casefold()
    assert 'ahmet' not in sent and 'yılmaz' not in sent and 'yilmaz' not in sent


def test_usage_proxy_and_compat_wrapper_only_receive_sanitized_kwargs():
    from app.domain import claude_usage_runtime
    received = []
    async def create(**kwargs):
        received.append(kwargs)
        return NS(usage=None)
    owner = NS(_last_claude_usage=None)
    proxy = claude_usage_runtime._MessagesUsageProxy(owner, NS(create=create))
    async def scenario():
        token = context.set(PrivacyContext(None, (FULL,)))
        try:
            await privacy_call(proxy.create, provider='test', call_site='proxy',
                               messages=[{'role': 'user', 'content': 'Sayın Ahmet Demir. Serum Demir 85 µg/dL'}])
        finally:
            context.reset(token)
    asyncio.run(scenario())
    assert received[0]['messages'][0]['content'] == 'Sayın [HASTA_ADI]. Serum Demir 85 µg/dL'


def test_privacy_errors_never_carry_document_content():
    with pytest.raises(PrivacyViolation) as error:
        sanitize_text('Hasta Adı: Ahmet Yılmaz Hemoglobin 13.2 g/dL')
    assert 'Ahmet' not in str(error.value) and error.value.__cause__ is None


def test_prose_ending_in_a_label_word_does_not_swallow_the_next_line():
    text = 'Ad, soyad, telefon ve doğum tarihi\ngibi doğrudan tanımlayıcıları hiçbir çıktı alanına yazma.'
    assert _text(text) == text


def test_static_provider_prompts_are_not_altered_by_label_rules():
    import ast
    from pathlib import Path
    from tests.test_privacy_canaries import SITES
    changed = []
    for site in SITES:
        tree = ast.parse((Path(__file__).parents[1] / 'app' / 'domain' / f'{site}.py').read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 30:
                # Schema field descriptions such as '"source_file_name": string' are
                # intentionally treated like data by the KAYIT_NO label.
                if 'source_file_name' in node.value:
                    continue
                if sanitize_text(node.value).text != node.value:
                    changed.append((site, node.value[:80]))
    assert not changed, changed
