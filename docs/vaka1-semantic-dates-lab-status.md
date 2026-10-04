# Vaka 1: semantic dates and deterministic laboratory status

## Root cause

The timeline selected a single measurement/report/upload date and did not retain
the difference between specimen collection and result release. Imaging could use
the report date before its examination date. Laboratory persistence explicitly
disabled classification and stored UNKNOWN; the frontend trusted a printed
High/Low flag before comparing the numeric interval. The clinical AI was asked
to classify those values again.

## Fix

- `document_dates.resolve_timeline_date` selects dates by record type. Laboratory
  specimen dates precede legacy measurement dates; imaging uses examination/event
  dates; consultations use consultation/document dates. Clinical and vital event
  dates are independently optional. Date-only values stay unchanged; timestamp
  grouping uses the Europe/Istanbul calendar.
- Explicit source dates survive PDF/photo extraction, merge, save and read.
  A printed result/document date is never an upload timestamp. Conflicting or
  unlabelled header dates do not become inferred specimen dates.
- Laboratory records retain their clinical day. A read-only result-availability
  notice on a later release day references existing result IDs, without copying
  DB records or increasing the laboratory-result count.
- One backend classifier returns LOW/NORMAL/HIGH/UNKNOWN from the selected source
  reference. Two-sided endpoints are inclusive. Comma decimals, Unicode dashes,
  one-sided limits and censored observations are supported conservatively.
  Qualitative, conflicting or ambiguous observations remain UNKNOWN. Typography
  aliases for units are compared without converting measurements.
- TIBC 445 and 450 against 250–450 are NORMAL; 451 is HIGH and 249 is LOW.
  A source High flag and stale client status/bounds cannot override this result.
- Save writes existing LabResult status/reference columns. Upload, normalize,
  case detail, timeline and AI use the same deterministic classifier. All original
  demographic reference rows survive the frontend/backend round trip.
- Frontend colors consume canonical status only. Optional clinical/vital date
  inputs support actual observation dates; upload fallbacks are labelled as
  upload/record dates. Late-result notices show sample and result dates separately.
- Clinical AI keeps its existing eight-section plain-text response. The prompt
  preserves canonical status and ranks the main pattern and secondary
  differentials by supporting, contradicting and missing evidence. No new model,
  provider or diagnostic response schema was introduced.

## Validation

- Entire active backend CI suite plus new regressions: **332 passed**.
- Frontend suite: **68 passed**, executed locally with Node test isolation disabled
  so every named test runs in this managed environment.
- TypeScript project build and Vite production build passed.
- Ruff fatal-error checks (E9/F63/F7/F82), compileall and `git diff --check` passed.
- New tests cover the ten requested cases, complete Vaka 1 save/detail/SQL/history
  behavior, all 50 rows reaching AI, patient isolation, legacy read compatibility,
  source deduplication, unit typography, censored values and AI fingerprint safety.
- The five new backend regression files are part of GitHub CI.

## Backward compatibility

No DB migration is needed: optional dates use existing JSON storage and laboratory
status/bounds use existing columns. HTTP routes, the v1 contract version, legacy
`measured_at` and `report_date`, numeric vital fields and existing AI response
format remain available. Old records are classified at read time without bulk
rewrites. Resaving a pre-upgrade source does not duplicate its rows. Explicitly
cleared clinical dates do not revive stale legacy aliases.

An AI report remains visible only when its fingerprint matches the normalized
case. A report tied to old or incorrect status data requires regeneration. Valid
canonical text and timestamp precision are preserved so fresh reports remain
matched.

## Remaining limits

Missing or ambiguous source dates cannot be reconstructed reliably. Existing
documents without labelled specimen/result dates retain their legacy fallback;
they are not silently backdated. Unit conversion is outside classification.
Provider calls were mocked in tests; OCR accuracy and live LLM wording/ranking
were not verified against a production patient or a live paid provider.

## Files changed

- `.github/workflows/clinical-quality-ci-v2.yml`
- `app/backend/app/api/routes/simple_case.py`
- `app/backend/app/domain/document_dates.py`
- `app/backend/app/domain/lab_result_classification.py`
- `app/backend/app/domain/canonical_lab_model.py`
- `app/backend/app/domain/claude_lab_extraction_service.py`
- `app/backend/app/domain/fast_pdf_lab_parser.py`
- `app/backend/app/domain/lab_document_ingestion.py`
- `app/backend/app/domain/openai_case_document_service.py`
- `app/backend/app/domain/openai_lab_extraction_service.py`
- `app/backend/app/domain/patient_clinical_context.py`
- `app/backend/app/domain/patient_health_timeline.py`
- `app/backend/app/domain/simple_case.py`
- `app/backend/app/domain/simple_case_ai.py`
- `app/backend/app/schemas/extraction.py`
- `app/backend/app/schemas/patient_health_timeline.py`
- `app/backend/app/schemas/simple_case.py`
- `app/backend/tests/test_document_dates.py`
- `app/backend/tests/test_lab_document_semantic_dates.py`
- `app/backend/tests/test_lab_result_classification.py`
- `app/backend/tests/test_simple_case_ai_vaka1.py`
- `app/backend/tests/test_vaka1_persistence_regression.py`
- `app/backend/tests/test_patient_clinical_vitals.py`
- `app/backend/tests/test_patient_health_timeline_api.py`
- `app/backend/tests/test_simple_case.py`
- `app/frontend/src/components/patient/PatientTimelinePanel.tsx`
- `app/frontend/src/pages/SimpleCaseWorkspacePage.tsx`
- `app/frontend/src/services/clinicalRecord.ts`
- `app/frontend/src/services/labDisplayClassification.ts`
- `app/frontend/src/services/labDocumentMerge.ts`
- `app/frontend/src/services/patientTimelineGrouping.ts`
- `app/frontend/src/services/simpleCaseClient.ts`
- `app/frontend/tests/clinicalRecord.test.mjs`
- `app/frontend/tests/labDocument.test.mjs`
- `app/frontend/tests/patientTimeline.test.mjs`
- `docs/vaka1-semantic-dates-lab-status.md`
