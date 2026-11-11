"""Canonical lab status regressions; all values/references remain source data."""

from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from app.domain.lab_result_classification import classify_lab_result
from app.domain.simple_case import normalize_simple_case
from app.schemas.simple_case import SimpleCaseRequest


@pytest.mark.parametrize(("value", "reference", "expected"), [
    (445, "250–450", "NORMAL"),
    (450, "250–450", "NORMAL"),
    (451, "250–450", "HIGH"),
    (249, "250–450", "LOW"),
    (250, "250–450", "NORMAL"),
    (5, "15–150", "LOW"),
    (5, "15–45", "LOW"),
    (0, "0-5", "NORMAL"),
    ("4,5", "4,5 – 5,5", "NORMAL"),
    ("5,5", "4,5 — 5,5", "NORMAL"),
    ("5,5001", "4,5 — 5,5", "HIGH"),
    (Decimal("4.5"), "4.5-5.5", "NORMAL"),
    (-3, "-5--1", "NORMAL"),
    ("−3", "−5 – −1", "NORMAL"),
    (1e-6, "0-0.01", "NORMAL"),
])
def test_source_interval_includes_both_boundaries(value, reference, expected):
    result = classify_lab_result(value=value, reference_text=reference)
    assert result.status == expected
    assert result.raw_reference == reference


@pytest.mark.parametrize("dash", ["-", "‐", "‑", "‒", "–", "—", "−"])
def test_unicode_range_separators(dash):
    result = classify_lab_result(value=445, reference_text=f"250 {dash} 450")
    assert (result.status, result.reference_low, result.reference_high) == ("NORMAL", 250, 450)


@pytest.mark.parametrize(("value", "reference", "expected"), [
    (39, "<40", "NORMAL"), (40, "<40", "HIGH"),
    (40, "<=40", "NORMAL"), (41, "≤40", "HIGH"),
    (11, ">10", "NORMAL"), (10, ">10", "LOW"),
    (10, ">=10", "NORMAL"), (9, "≥10", "LOW"),
    ("<5", "15–150", "LOW"),
    (">200", "15–150", "HIGH"),
    ("<15", "15–150", "LOW"),
    ("<=15", "15–150", "UNKNOWN"),
    (">150", "15–150", "HIGH"),
    (">=150", "15–150", "UNKNOWN"),
    ("<40", "<40", "NORMAL"),
    ("<=40", "<40", "UNKNOWN"),
    (">=40", "<40", "HIGH"),
    (">10", ">10", "NORMAL"),
    (">=10", ">10", "UNKNOWN"),
    ("<=10", ">10", "LOW"),
    ("<30", "15–150", "UNKNOWN"),
    (">30", "15–150", "UNKNOWN"),
])
def test_one_sided_references_and_only_provable_censored_values(value, reference, expected):
    assert classify_lab_result(value=value, reference_text=reference).status == expected


@pytest.mark.parametrize("value", [None, "negative", "positive", "iz", "hemolysis", "4.5.6", "4,500.0", True, False, float("nan"), float("inf")])
def test_non_numeric_or_ambiguous_observations_are_unknown(value):
    assert classify_lab_result(value=value, reference_text="2–5").status == "UNKNOWN"


@pytest.mark.parametrize("reference", [None, "negative", "Adult: 2–5", "2–5 or 8–10", "", "5–2"])
def test_unusable_reference_never_invents_range(reference):
    assert classify_lab_result(value=3, reference_text=reference).status == "UNKNOWN"


@pytest.mark.parametrize(("unit", "reference_unit", "text", "expected"), [
    ("µg/dL", None, "250–450", "NORMAL"),
    ("µg/dL", None, "250–450 µg/dL", "NORMAL"),
    ("μg/dL", "ug / dL", "250–450", "NORMAL"),
    ("mg/dL", None, "250–450 µg/dL", "UNKNOWN"),
    ("µg/dL", "mg/dL", "250–450", "UNKNOWN"),
    ("µg/dL", "mg/dL", "250–450 µg/dL", "UNKNOWN"),
    (None, "µg/dL", "250–450", "UNKNOWN"),
    ("10^9 / L", None, "250–450 10^9/L", "NORMAL"),
    ("%", None, "15–45 %", "LOW"),
])
def test_units_are_compared_without_converting_measurements(unit, reference_unit, text, expected):
    value = 5 if text.startswith("15") else 445
    result = classify_lab_result(value=value, unit=unit, reference_text=text, reference_unit=reference_unit)
    assert result.status == expected
    if expected == "UNKNOWN":
        assert result.classification_reason == "reference_unit_mismatch"


@pytest.mark.parametrize(("kwargs", "reason"), [
    ({"reference_low": 1, "reference_high": 4, "reference_text": "2–5"}, "reference_bounds_conflict"),
    ({"reference_low": 2, "reference_high": 5, "reference_text": "<5"}, "reference_bounds_conflict"),
    ({"reference_low": "broken", "reference_high": 5}, "invalid_reference_bounds"),
    ({"reference_low": float("inf"), "reference_high": 5}, "invalid_reference_bounds"),
    ({"reference_low": 5, "reference_high": 2}, "invalid_reference_bounds"),
])
def test_conflicting_or_invalid_structured_bounds_are_unknown(kwargs, reason):
    result = classify_lab_result(value=3, **kwargs)
    assert result.status == "UNKNOWN"
    assert result.classification_reason == reason


def test_explicit_structured_bounds_and_selected_demographic_label_are_supported():
    result = classify_lab_result(value=210, unit="U/L", reference_text="Age 10-17: 80-350 U/L",
                                 reference_low=80, reference_high=350, reference_unit="U/L")
    assert result.status == "NORMAL"
    assert classify_lab_result(value="4,5", reference_low="4,5", reference_high="5,5").status == "NORMAL"


@pytest.mark.parametrize("reason", ["numeric_value_conflict", "invalid_reference_bounds", "reference_unit_mismatch", "low_input_confidence", "conflicting_or_repeated_observation"])
def test_transcription_uncertainty_is_not_promoted_to_fact(reason):
    result = classify_lab_result(value=3, reference_text="2–5", ingestion_reasons=[reason])
    assert result.status == "UNKNOWN"
    assert result.classification_reason == "ingestion_review_required"


def test_normalization_recomputes_tibc_status_without_trusting_flag_or_incoming_status():
    payload = SimpleCaseRequest.model_validate({"labs": [{
        "test_name": "TIBC", "value": 445, "unit": "µg/dL", "source_reference": "250–450",
        "status": "HIGH", "source_metadata": {"source_flag": "High", "display_status": "high"},
        "specimen_date": "2026-10-02", "result_date": "2026-10-04", "uploaded_at": "2026-10-04",
    }]})
    before = deepcopy(payload.model_dump())
    output = normalize_simple_case(payload).labs[0]
    assert (output.status, output.reference_low, output.reference_high) == ("NORMAL", 250, 450)
    assert output.raw_reference == "250–450"
    assert output.source_metadata["source_flag"] == "High"
    assert output.specimen_date == date(2026, 10, 2)
    assert output.result_date == output.uploaded_at == date(2026, 10, 4)
    assert payload.model_dump() == before


def test_missing_demographics_never_reuses_unselected_context_specific_reference():
    payload = SimpleCaseRequest.model_validate({"labs": [{
        "test_name": "ALP", "value": 210, "source_reference": "80–350", "reference_low": 80,
        "reference_high": 350, "source_references": [{"text": "80–350", "minimum": 80,
            "maximum": 350, "age_min": 10, "age_max": 17}],
    }]})
    output = normalize_simple_case(payload).labs[0]
    assert output.status == "UNKNOWN"
    assert output.reference_source == "missing"


def test_equally_applicable_conflicting_reference_rows_stay_unknown():
    payload = SimpleCaseRequest.model_validate({"labs": [{"test_name": "test", "value": 3,
        "source_references": [{"text": "2–5", "minimum": 2, "maximum": 5},
                              {"text": "4–8", "minimum": 4, "maximum": 8}]}]})
    assert normalize_simple_case(payload).labs[0].status == "UNKNOWN"


def test_equal_numeric_bounds_do_not_hide_conflicting_strict_comparators():
    payload = SimpleCaseRequest.model_validate({"labs": [{"test_name": "test", "value": 40,
        "source_references": [{"text": "<40", "maximum": 40},
                              {"text": "<=40", "maximum": 40}]}]})
    assert normalize_simple_case(payload).labs[0].status == "UNKNOWN"


@pytest.mark.parametrize(("reference", "status"), [("Adult: <40", "HIGH"), ("Adult: <=40", "NORMAL")])
def test_selected_demographic_labels_preserve_one_sided_boundary_semantics(reference, status):
    result = classify_lab_result(value=40, reference_text=reference, reference_high=40)
    assert result.status == status


def test_source_flag_without_numeric_reference_never_creates_numeric_status():
    payload = SimpleCaseRequest.model_validate({"labs": [{"test_name": "test", "value": 3,
        "source_metadata": {"source_flag": "High"}}]})
    assert normalize_simple_case(payload).labs[0].status == "UNKNOWN"


def test_normalized_roundtrip_preserves_all_demographic_references():
    references = [
        {"text": "80–350", "minimum": 80, "maximum": 350, "age_min": 10, "age_max": 17},
        {"text": "40–130", "minimum": 40, "maximum": 130, "age_min": 18, "age_max": 65},
    ]
    first = normalize_simple_case(SimpleCaseRequest.model_validate({
        "clinical": {"age": 15}, "labs": [{"test_name": "ALP", "value": 210,
        "source_reference": None, "source_references": references}],
    })).labs[0]
    assert first.status == "NORMAL"
    assert first.source_reference is None
    assert first.source_references == SimpleCaseRequest.model_validate({
        "labs": [{"test_name": "ALP", "source_references": references}],
    }).labs[0].source_references
    updated = normalize_simple_case(SimpleCaseRequest.model_validate({
        "clinical": {"age": 44}, "labs": [first.model_dump(mode="json")],
    })).labs[0]
    assert updated.status == "HIGH"
    assert updated.raw_reference == "40–130"


def test_boolean_observation_does_not_coerce_into_numeric_value():
    payload = SimpleCaseRequest.model_validate({"labs": [{"test_name": "test", "value": True,
        "source_reference": "0–2"}]})
    output = normalize_simple_case(payload).labs[0]
    assert output.value == "True"
    assert output.status == "UNKNOWN"


@pytest.mark.parametrize(('value','unit','reference','status','numeric'),[
    ('14.8','10^9/L','Ref: 4.0–10.0','HIGH',14.8),
    ('82','%','40–75','HIGH',82),
    ('94 mg/L','mg/L','Reference: <5','HIGH',94),
    ('0.42 ng/mL','ng/mL','<0.10','HIGH',.42),
    ('0.91','mg/dL','Normal: 0.5-1.0','NORMAL',.91),
    ('1,98 mg/dL','mg/dL','0,5–1,0','HIGH',1.98),
    ('31 U/L','U/L','<35','NORMAL',31),
    ('-3 mmol/L','mmol/L','-5–-1','NORMAL',-3),
    ('1.48e1 10^9/L','10^9/L','4e0–1e1','HIGH',14.8),
])
def test_verified_numeric_formats_and_source_labels(value,unit,reference,status,numeric):
    c=classify_lab_result(value=value,unit=unit,reference_text=reference)
    assert (c.status,c.normalized_value,c.parsed_unit)==(status,numeric,unit)
    assert c.raw_reference==reference


@pytest.mark.parametrize(('value','reference','expected','operator','limit'),[
    ('>100 mg/L','<5','HIGH','>',100),
    ('<0.10 mg/L','<0.10','NORMAL','<',.10),
    ('≥90 mg/L','>90','UNKNOWN','>=',90),
    ('≤5 mg/L','<5','UNKNOWN','<=',5),
    ('≤5 mg/L','<=5','NORMAL','<=',5),
])
def test_inline_units_and_comparators_never_become_exact_measurements(value,reference,expected,operator,limit):
    c=classify_lab_result(value=value,unit='mg/L',reference_text=reference)
    assert (c.status,c.value_comparator,c.value_limit)==(expected,operator,limit)
    assert c.normalized_value is None


@pytest.mark.parametrize('value',['Positive','Negative','Normal','2+','3+','94 mg/L elevated','94 mystery'])
def test_qualitative_or_unvalidated_suffix_cannot_be_numeric(value):
    c=classify_lab_result(value=value,unit='mg/L',reference_text='<5')
    assert c.status=='UNKNOWN' and c.normalized_value is None


def test_observed_unit_conflict_and_unparseable_reference_are_not_ignored():
    assert classify_lab_result(value='94 mg/dL',unit='mg/L',reference_text='<5').classification_reason=='observed_unit_mismatch'
    c=classify_lab_result(value=3,reference_text='2–5 or 8–10',reference_low=2,reference_high=5)
    assert c.status=='UNKNOWN'
    assert classify_lab_result(value=3,reference_text='Negative',reference_low=2,reference_high=5).status=='UNKNOWN'


def test_equivalent_reference_typography_is_not_a_conflict_but_strictness_still_is():
    case={'labs':[{'test_name':'Creatinine','value':.91,'unit':'mg/dL','source_references':[
        {'text':'Ref: 0.5–1.0','minimum':.5,'maximum':1,'unit':'mg/dL'},
        {'text':'0,5-1,0','minimum':.5,'maximum':1,'unit':'mg/dL'}]}]}
    assert normalize_simple_case(SimpleCaseRequest.model_validate(case)).labs[0].status=='NORMAL'


@pytest.mark.parametrize('label',['Female: 0.5–1.0','Adult: 0.5–1.0','Age 10-17: 0.5–1.0'])
def test_demographic_label_without_structured_applicability_stays_unknown(label):
    payload=SimpleCaseRequest.model_validate({'clinical':{'sex':'male','age':40},'labs':[{
        'test_name':'test','value':.91,'source_references':[{'text':label,'minimum':.5,'maximum':1}]}]})
    assert normalize_simple_case(payload).labs[0].status=='UNKNOWN'


def test_changed_demographics_reclassify_verified_source_intervals_and_ignore_cached_numbers():
    refs=[{'text':'Female: 0.5–1.0','minimum':.5,'maximum':1,'sex':'female'},
          {'text':'Male: 0.5–1.2','minimum':.5,'maximum':1.2,'sex':'male'}]
    first=normalize_simple_case(SimpleCaseRequest.model_validate({'clinical':{'sex':'female'},'labs':[{
        'test_name':'Creatinine','value':'1.1 mg/dL','unit':'mg/dL','source_references':refs,
        'status':'NORMAL','normalized_value':99}]}))
    assert first.labs[0].status=='HIGH' and first.labs[0].normalized_value==1.1
    snapshot=first.model_dump(mode='json');snapshot['clinical']['sex']='male'
    second=normalize_simple_case(SimpleCaseRequest.model_validate(snapshot))
    assert second.labs[0].status=='NORMAL' and second.labs[0].value=='1.1 mg/dL'


def test_validated_inline_unit_can_supply_a_missing_unit_without_overwriting_source():
    for missing in (None,'   '):
        output=normalize_simple_case(SimpleCaseRequest.model_validate({'labs':[{
            'test_name':'CRP','value':'94 mg/L','unit':missing,'source_reference':'Reference: <5 mg/L'}]})).labs[0]
        assert output.status=='HIGH' and output.parsed_unit=='mg/L'
        assert output.unit==missing and output.value=='94 mg/L'


def test_additive_parsed_fields_preserve_legacy_fingerprint_but_status_and_sources_do_not():
    from app.domain.simple_case import case_fingerprint
    from copy import deepcopy
    old={'labs':[{'test_name':'CRP','value':94,'unit':'mg/L','status':'HIGH','raw_reference':'<5'}]}
    richer=deepcopy(old);richer['labs'][0].update(normalized_value=94,value_comparator=None,value_limit=None,parsed_unit='mg/L')
    assert case_fingerprint(old)==case_fingerprint(richer)
    richer['labs'][0]['status']='UNKNOWN'
    assert case_fingerprint(old)!=case_fingerprint(richer)
    richer=deepcopy(old);richer['labs'][0]['value']='>94'
    assert case_fingerprint(old)!=case_fingerprint(richer)


def test_reference_unit_can_be_printed_in_either_verified_reference_field():
    payload=SimpleCaseRequest.model_validate({'labs':[{'test_name':'Test','value':3,'unit':'mg/L','source_references':[
        {'text':'Ref: 2–5 mg/L'}, {'text':'2-5','unit':'mg/L','minimum':2,'maximum':5},
    ]}]})
    assert normalize_simple_case(payload).labs[0].status=='NORMAL'


@pytest.mark.parametrize('reference',[
    {'text':'Female: 0.5–1.0','minimum':.5,'maximum':1,'sex':'male'},
    {'text':'Age 10-17: 0.5–1.0','minimum':.5,'maximum':1,'age_min':18,'age_max':65},
])
def test_printed_population_label_cannot_be_overridden_by_conflicting_structured_applicability(reference):
    case=SimpleCaseRequest.model_validate({'clinical':{'age':40,'sex':'male'},'labs':[{
        'test_name':'Test','value':.91,'source_references':[reference]}]})
    assert normalize_simple_case(case).labs[0].status=='UNKNOWN'


@pytest.mark.parametrize(('value','unit','reference','expected','numeric'),[
    ('%82','%','40–75','HIGH',82),
    ('%37.1','%','36–46','NORMAL',37.1),
    ('14.8 x10^9/L','10^9/L','4–10','HIGH',14.8),
    ('282 ×10⁹/L','10^9/L','150–400','NORMAL',282),
    ('68 mm/s','mm/s','<20','HIGH',68),
])
def test_source_percent_prefix_and_count_unit_typography_preserve_raw_scale(value,unit,reference,expected,numeric):
    c=classify_lab_result(value=value,unit=unit,reference_text=reference)
    assert c.status==expected and c.normalized_value==numeric
    assert c.parsed_unit==unit


def test_percent_prefix_cannot_override_a_conflicting_unit_or_mixed_value():
    assert classify_lab_result(value='%82',unit='g/dL',reference_text='40–75').status=='UNKNOWN'
    assert classify_lab_result(value='%95, 2 L/dk O2',unit='%',reference_text='90–100').status=='UNKNOWN'
    assert classify_lab_result(value='68 mm/s',unit='mm/h',reference_text='<20').status=='UNKNOWN'
