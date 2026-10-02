MediCore klinik öykü ve vital bulgular değişiklikleri

Kök neden: Yeni vaka klinik veriyi complaints/history/medications/notes alanlarıyla kaydediyordu. Arşiv kartı ise yalnızca eski presenting_complaint/clinical_history_details/physical_exam alanlarını okuyordu. Ayrıca “Klinik bilgiyi kaydet ve devam et” düğmesi yalnızca sekmeyi değiştiriyordu.

Yeni davranış:
- Klinik öykü dört bölümde, tam metin ve satır sonlarıyla gösterilir. Yalnızca öykü ve vital değerlerin ikisi de boş olduğunda boş bilgi mesajı gösterilir.
- Kaydet ve devam et düğmesi mevcut save API üzerinden klinik bilgi ve vital değerleri commit eder.
- VitalSigns dokuz isteğe bağlı sayısal alan içerir: systolic_bp, diastolic_bp, heart_rate, respiratory_rate, temperature, spo2, height_cm, weight_kg, glucose_mg_dl. Birimler sırasıyla mmHg, mmHg, bpm, /dk, °C, %, cm, kg, mg/dL.
- Kaynak klinik vaka JSON verisidir. Vaka özeti önceliklidir; yoksa eski clinical_context okunur. Hasta kartı boy/kiloyu aynı çözümlenmiş vital veriden okur. Eski kök boy/kilo alanları yazma sırasında kanonik veriye taşınır.
- Eksik alanlar null olarak saklanır ve gösterilmez. Sıfır değerleri korunur. Açıkça temizlenen vital değerleri eski metadata'dan geri getirilmez.
- Eski istemciler vital alanını göndermediğinde kayıtlı vital değerler korunur. Eski iç içe klinik form için dönüşüm yapılır; kan şekeri eski formdan geçerken de korunur.
- Kayıt sonrası tarayıcı taslağı güncellenir. Değişmemiş taslak arşive geçişte yeniden yazılmaz. Vital değişiklikleri eski AI raporunu geçersiz kılar; AI girişinde vital veriler nottan ayrı yapılandırılmış alanlardır.
- Mevcut endpointler, AI sağlayıcıları, modeller ve anahtar ayarları korunur. API alanları geriye uyumlu eklenmiştir. Veriler mevcut patients.metadata_json JSONB sütununda tutulduğu için DB migration gerekmez.

Doğrulama:
- Backend: 92 test geçti. Komut: ../../.venv/bin/python -m pytest -q tests/test_patient_clinical_vitals.py tests/test_simple_case.py tests/test_patient_protocol.py tests/test_radiology_report_parser.py (app/backend dizininden).
- Frontend: 26 test geçti; npm run build başarılı (testler + TypeScript + Vite).
- Yeni backend testleri gerçek SQLAlchemy Patient modeliyle SQLite üzerinde commit ve her istekte yeni session kullanarak yeniden okuma yapar. PostgreSQL'e özgü JSON containment filtrelemesi ve üretim dağıtımı bu ortamda çalıştırılmadı. Canlı hasta verisi ya da ücretli AI çağrısı kullanılmadı.

Değişen dosyalar:
- .github/workflows/clinical-quality-ci-v2.yml
- app/backend/app/api/routes/patients.py
- app/backend/app/api/routes/simple_case.py
- app/backend/app/domain/patient_clinical_context.py
- app/backend/app/schemas/patient_record.py
- app/backend/app/schemas/simple_case.py
- app/backend/tests/test_patient_clinical_vitals.py
- app/frontend/src/components/clinical/ClinicalHistorySummary.tsx
- app/frontend/src/components/clinical/ClinicalIntakeForm.tsx
- app/frontend/src/components/clinical/VitalSignsFields.tsx
- app/frontend/src/pages/PatientHistoryPage.tsx
- app/frontend/src/pages/PatientRecordPage.tsx
- app/frontend/src/pages/SimpleCaseWorkspacePage.tsx
- app/frontend/src/services/clinicalBrainClient.ts
- app/frontend/src/services/clinicalRecord.ts
- app/frontend/src/services/labAnalysisClient.ts
- app/frontend/src/services/patientClient.ts
- app/frontend/src/services/simpleCaseClient.ts
- app/frontend/tests/clinicalRecord.test.mjs
- app/frontend/tests/clinicalUI.test.mjs
- docs/clinical-history-vital-signs.md
