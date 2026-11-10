"""Model software provisioning is separate from patient audio inference."""
import asyncio
import hashlib
from io import BytesIO
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core import config
from app.domain import voice_model_assets as assets
from app.domain import clinical_voice
from app.infrastructure import voice_model_provisioning as provision


@pytest.fixture
def fake_assets(monkeypatch,tmp_path):
    files={'config.json':b'{"multilingual":true}','model.bin':b'synthetic model bytes',
           'tokenizer.json':b'{}','vocabulary.txt':b'test vocabulary'}
    manifest={name:(len(data),hashlib.sha256(data).hexdigest()) for name,data in files.items()}
    monkeypatch.setattr(provision,'MODEL_FILES',manifest)
    monkeypatch.setattr(assets,'MODEL_FILES',manifest)
    monkeypatch.setattr(assets,'BUNDLED_MODEL_DIR',tmp_path)
    prepare=Mock()
    monkeypatch.setattr(clinical_voice.recognizer,'prepare',prepare)
    urls=[]
    class Response(BytesIO):
        def geturl(self):return 'https://public-model.invalid/immutable-file'
    def open_url(url,**kwargs):
        urls.append(url)
        return Response(files[url.rsplit('/',1)[-1]])
    monkeypatch.setattr(provision,'urlopen',open_url)
    return SimpleNamespace(root=tmp_path,files=files,urls=urls,prepare=prepare,response=Response)


def test_verified_immutable_model_becomes_available_without_environment_override(fake_assets):
    fixture=fake_assets
    assert assets.effective_voice_model_path(None) is None
    assert provision.prepare_bundled_voice_model(fixture.root)==str(fixture.root)
    assert assets.effective_voice_model_path(None)==str(fixture.root)
    assert len(fixture.urls)==4
    assert all(assets.MODEL_REVISION in url and url.startswith('https://huggingface.co/') for url in fixture.urls)
    assert all('audio' not in url and 'patient' not in url for url in fixture.urls)
    fixture.prepare.assert_called_once_with(str(fixture.root))
    assert json.loads((fixture.root/assets.READY_FILE).read_text())=={'revision':assets.MODEL_REVISION,'language':'tr'}


def test_valid_cached_assets_are_reused_without_network(fake_assets,monkeypatch):
    provision.prepare_bundled_voice_model(fake_assets.root)
    monkeypatch.setattr(provision,'urlopen',Mock(side_effect=AssertionError('cache must be offline')))
    assert provision.prepare_bundled_voice_model(fake_assets.root)==str(fake_assets.root)
    assert assets.bundled_model_available(fake_assets.root)


@pytest.mark.parametrize('failure',['oversize','short','wrong_hash','timeout','insecure_redirect'])
def test_failed_asset_never_enables_voice_or_loads_model(fake_assets,monkeypatch,failure):
    f=fake_assets
    def failed(url,**kwargs):
        if failure=='timeout':raise TimeoutError('do not log raw response or URLs')
        payload=f.files['config.json']
        if failure=='oversize':payload+=b'oversize'
        if failure=='short':payload=payload[:-1]
        if failure=='wrong_hash':payload=b'X'*len(payload)
        response=f.response(payload)
        if failure=='insecure_redirect':response.geturl=lambda:'http://unsafe.invalid/file'
        return response
    monkeypatch.setattr(provision,'urlopen',failed)
    with pytest.raises(provision.VoicePreparationError) as error:provision.prepare_bundled_voice_model(f.root)
    assert 'unsafe' not in str(error.value) and 'raw response' not in str(error.value)
    assert not assets.bundled_model_available(f.root)
    assert not (f.root/assets.READY_FILE).exists()
    assert not list(f.root.glob('*.part'))
    f.prepare.assert_not_called()


def test_multilingual_model_validation_must_pass_before_ready(fake_assets):
    fake_assets.prepare.side_effect=clinical_voice.VoiceUnavailable()
    with pytest.raises(provision.VoicePreparationError):provision.prepare_bundled_voice_model(fake_assets.root)
    assert not assets.bundled_model_available(fake_assets.root)


def test_corrupt_existing_asset_is_repaired_before_readiness(fake_assets):
    provision.prepare_bundled_voice_model(fake_assets.root)
    (fake_assets.root/'model.bin').write_bytes(b'broken')
    assert not assets.bundled_model_available(fake_assets.root)
    old=len(fake_assets.urls)
    provision.prepare_bundled_voice_model(fake_assets.root)
    assert len(fake_assets.urls)==old+1
    assert assets.bundled_model_available(fake_assets.root)


def test_partial_files_and_wrong_revision_are_not_ready(fake_assets):
    for name,data in fake_assets.files.items():(fake_assets.root/name).write_bytes(data)
    assert assets.effective_voice_model_path(None) is None
    (fake_assets.root/assets.READY_FILE).write_text(json.dumps({'revision':'wrong','language':'tr'}))
    assert assets.effective_voice_model_path(None) is None


def test_explicit_operator_override_is_not_silently_replaced(fake_assets):
    provision.prepare_bundled_voice_model(fake_assets.root)
    assert assets.effective_voice_model_path('/operator/model')=='/operator/model'
    assert assets.effective_voice_model_path('')==''


def test_startup_uses_explicit_model_without_software_download(fake_assets,monkeypatch):
    monkeypatch.setattr(config,'get_settings',lambda:SimpleNamespace(clinical_voice_model_path='/operator/model'))
    download=Mock(side_effect=AssertionError('override must never trigger download'))
    monkeypatch.setattr(provision,'prepare_bundled_voice_model',download)
    assert asyncio.run(provision.prepare_offline_voice())=='operator-local-model'
    download.assert_not_called()
    fake_assets.prepare.assert_called_once_with('/operator/model')


def test_default_startup_prepares_once_before_requests(fake_assets,monkeypatch):
    monkeypatch.setattr(config,'get_settings',lambda:SimpleNamespace(clinical_voice_model_path=None))
    prepare=Mock(return_value=str(fake_assets.root))
    monkeypatch.setattr(provision,'prepare_bundled_voice_model',prepare)
    assert asyncio.run(provision.prepare_offline_voice())=='bundled-multilingual-tiny'
    prepare.assert_called_once_with()
