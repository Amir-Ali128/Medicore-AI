MediCore: hasta izolasyonu, birleşik sağlık geçmişi ve rapor türü çıkarımı

Hasta verisi mevcut Patient, LabReport, LabResult ve RadiologyReport kayıtları üzerinde tutulur. Yeni görüntüleme sistemi, DB tablosu veya migration eklenmez. Mevcut endpointlerin URL ve payload sözleşmeleri korunur; yeni sağlık geçmişi endpointi ve rapor yanıt alanları eklenir. AI sağlayıcısı, modeli, anahtarı veya laboratuvarın kaynak referansa göre sınıflandırma akışı değiştirilmez.

Hasta izolasyonu:

- Hasta erişimi mevcut rol ve sahiplik kurallarıyla kontrol edilir. Gerçek hastanın arşivlenmiş raporu başka hastaya taşınamaz; geçici yükleme ve referans verdiği geçici kaynaklar yalnız yükleyen kullanıcı tarafından okunup arşivlenebilir. Arşivleme sırasında doğrulanmış staging patient_id markerları seçilen hastaya bağlanır; kaynak metin korunur.
- Explicit patient/source kimlikleri, nested provenance dahil, persistence ve AI çağrısından önce doğrulanır. LabResult ve AnalysisRun için üst LabReport kaydının patient_id değeri de kontrol edilir; diğer kaynak zincirleri aynı hastaya bağlanmalıdır.
- Eski, farklı hastaya işaret eden kaynaklar cevap/timeline projeksiyonuna alınmaz. Kaynaklardan hasta kimliği tahmin edilmez veya kaydı sessizce başka hastaya taşınmaz.
- Ortak geçici yükleme kimliği (DEMO_PATIENT_ID) bir klinik hasta olarak kullanılamaz. Hasta arşivi/CRUD, sağlık geçmişi ve operational timeline bu kimlik için açılmaz; yükleme dosyaları uploader kontrolü olan mevcut endpointler üzerinden okunur.

Frontend izolasyonu:

- Cache anahtarı kullanıcı + patient_id içerir. Legacy ekranların aktif localStorage alanları yalnız seçilen hastanın cache görünümüdür. Hasta değişiminde eski klinik/vital/lab/rapor/AI pointerları temizlenir; sahibi bilinmeyen eski global cache içeriği taşınmaz.
- AbortController, hasta kimliği ve scope generation kontrolü, geç gelen kayıt/yükleme/AI/PDF yanıtlarının yeni hastaya uygulanmasını engeller. A → B → A geçişi eski A isteğini yeniden geçerli yapmaz.
- Layout hasta scope değiştiğinde ilgili ekranı yeniden açar. Timeline komponenti de prop değiştiği ilk render sırasında önceki hastanın verisini saklar ve isteğini iptal eder.
- Hasta okuma fonksiyonu aktif hasta seçimini değiştirmez. Arşivde birden fazla hastanın ayrı kartlarını açık patient_id ile okumak korunur. URL ve navigation state vaka seçiminde dikkate alınır.

Birleşik sağlık geçmişi:

`GET /timeline/patients/{patient_id}/health-history` mevcut kayıtları hasta bazlı sorgulayan backend aggregation/view katmanıdır. Yeni event/snapshot oluşturmaz veya timeline için verileri kopyalayıp DB'ye yazmaz. Dönen her öğe source_type/source_id/source_path ile asıl kaydı işaret eder.

LabResult.measured_at/test_date, raporun report_date/examination_date değeri ve klinik/vital kaydın gerçek muayene/ölçüm tarihi önceliklidir. Tarih yoksa mevcut sabit kayıt tarihi/created_at kullanılır ve UI bunu "Kayıt tarihi" olarak gösterir. Tarihsiz eski kayıtlar en sonda korunur. Saat içeren kayıtlar İstanbul gününe çevrilir; tarih-only değerler kaydırılmaz.

Aynı günün laboratuvar, idrar, rapor, klinik ve vital öğeleri tek gün altında gruplanır; günler en yeniden eskiye sıralanır. İdrar işareti mevcut specimen/parametre bilgisinden alınır. Frontend yanıtın ve her öğenin patient_id değerini tekrar doğrular ve aynı tarih gruplarını birleştirir. Sonuç listesi kırpılmaz; 50 parametrenin tümü "Tüm sonuçları göster" ile erişilebilir. Raporun tam metni "Raporu Gör" altında açılır. Arşiv ve vaka özeti sağlık geçmişine bağlantı içerir.

Eski simple-case kaydetme akışı kaynak LabReport/RadiologyReport kayıtlarını siliyordu. Artık aynı içerik yeniden kaydedildiğinde kaynak fingerprint ile aynı kayıt korunur; farklı tarih/belge/sonuç setleri eklenir. Ağustos/Eylül/Ekim Hb değerleri ayrı satırlarda kalır. Güncel vaka özeti mevcut JSON alanında tutulmaya devam eder.

Rapor türü çıkarımı:

Mevcut generic RadiologyReport modeli kullanılır. Başlık, inceleme/teknik alanı, bulgular, impression ve tam kaynak metin Türkçe/İngilizce işaretlerle değerlendirilir. CT, ULTRASOUND, MRI, X_RAY, PATHOLOGY, ECHOCARDIOGRAPHY, ENDOSCOPY, OTHER ve UNKNOWN desteklenir. Yeni kayıtların metadata_json alanına inferred_report_type, report_type_confidence ve çıkarım sürümü/gerekçesi eklenir; eski kayıtlar okuma sırasında aynı helper ile çözümlenir. API yanıtında derived tür ve confidence alanları bulunur.

Önerilen/geçmiş tetkik, tek başına eski modality kodu veya düşük/çelişkili kanıt tür atamak için yeterli değildir; UNKNOWN kullanılır. Confidence bir kural gücü göstergesidir, kalibre klinik olasılık değildir. Kaynak metin tür çıkarımı için yalnız okunur; birinci kaynaktaki metin korunur. "Patoloji saptanmadı" gibi radyoloji bulguları patoloji raporu olarak yorumlanmaz.

Doğrulama:

- Backend CI seti: 200 test başarılı. Komut (app/backend): `PYTHONPATH=. ../../.venv/bin/python -m pytest -q tests/test_simple_case.py tests/test_patient_clinical_vitals.py tests/test_patient_protocol.py tests/test_radiology_report_parser.py tests/test_patient_isolation.py tests/test_patient_health_timeline.py tests/test_patient_health_timeline_api.py tests/test_report_type_inference.py`.
- Frontend: `npm run build` başarılı; 58 test, TypeScript type-check ve Vite production build geçti.
- Değişen Python dosyalarında Ruff `E9,F63,F7,F82` temel hata kontrolleri ve `git diff --check` başarılı. Repo genelinde ayrıca yapılandırılmış lint komutu bulunmuyor.
- A/B Hb 8.2/15.1 ve CRP 120/2, clinical/vital/report isolation, ham body provenance, geç yanıtlar, geçici upload sahibi, arşivleme, tarih sıralaması, aynı gün gruplanması, Ağustos/Eylül/Ekim sonuçları ve 50 parametrenin tamamı doğrulandı. Gerçek SQLAlchemy model/commit ve her istekte yeni SQLite session kullanıldı; AI çağrıları mock edildi.
- Yeni regression test dosyaları mevcut GitHub CI test setine eklendi.

Kalan sınırlar:

- Eski sürümde silinmiş laboratuvar/rapor kayıtları veya overwrite edilmiş klinik/vital sürümleri DB'den geri üretilemez. Timeline yalnız mevcut gerçek kayıtları ve mevcut rapor içi klinik/vital bağlamları gösterir; Patient JSON alanında ayrıca kaydedilmemiş geçmiş klinik/vital sürümler için yeni bir arşiv modeli icat edilmez.
- Gerçek klinik tarihi olmayan kayıtların günü kayıt tarihidir. Belirsiz raporlar UNKNOWN kalabilir; tür hekim doğrulamasının yerini almaz.
- Başka hastaya veya eksik/geçersiz kaynağa explicit referans taşıyan eski kayıtlar güvenli okumada dışlanabilir; mevcut veriye destructive düzeltme uygulanmaz.
- Kaynak fingerprint seri kayıtlarda idempotence sağlar; eşzamanlı aynı hasta/kaynak save için DB seviyesinde unique constraint/row lock eklenmedi.
- Aggregation tüm sonuçları getirir. Çok büyük hasta geçmişleri için ileride tarih bazlı sayfalama gerekebilir.
- SQLite üzerinde gerçek model/commit/fresh-session testleri yapılır; üretim PostgreSQL'i veya canlı hasta verisi kullanılmaz. İki eski, aktif router'a bağlı olmayan ingestion test dosyası mevcut main'de de eksik canonical_native_trust/native_lab_engine modülleri nedeniyle collect edilemez. Ek eski `test_lab_pdf_system_extract_runtime.py` dosyasında referanssız satır regex grubu ve telefon footer filtresi için iki başarısız assertion vardır. Bu üç eski test dosyasındaki sorunlar pristine main (574f039) kopyasında da yeniden doğrulanmıştır; aktif simplified router test seti başarılıdır.

Değişen dosyalar:

- .github/workflows/clinical-quality-ci-v2.yml
- app/backend/app/api/routes/lab_reports.py
- app/backend/app/api/routes/patient_timeline.py
- app/backend/app/api/routes/patients.py
- app/backend/app/api/routes/radiology_reports.py
- app/backend/app/api/routes/simple_case.py
- app/backend/app/domain/clinical_record_dates.py
- app/backend/app/domain/patient_health_timeline.py
- app/backend/app/domain/patient_scope.py
- app/backend/app/domain/report_type_inference.py
- app/backend/app/schemas/patient_health_timeline.py
- app/backend/app/schemas/patient_record.py
- app/backend/app/schemas/radiology_report.py
- app/backend/tests/test_patient_health_timeline.py
- app/backend/tests/test_patient_health_timeline_api.py
- app/backend/tests/test_patient_isolation.py
- app/backend/tests/test_report_type_inference.py
- app/backend/tests/test_simple_case.py
- app/frontend/src/components/PatientPersistenceBridge.tsx
- app/frontend/src/components/clinical/ClinicalIntakeForm.tsx
- app/frontend/src/components/patient/PatientTimelinePanel.tsx
- app/frontend/src/layout/AppLayout.tsx
- app/frontend/src/pages/PatientHistoryPage.tsx
- app/frontend/src/pages/PatientTimelinePage.tsx
- app/frontend/src/pages/SimpleCaseWorkspacePage.tsx
- app/frontend/src/router.tsx
- app/frontend/src/services/apiClient.ts
- app/frontend/src/services/claudeReviewClient.ts
- app/frontend/src/services/clinicalBrainClient.ts
- app/frontend/src/services/combinedCaseClient.ts
- app/frontend/src/services/labAnalysisClient.ts
- app/frontend/src/services/labArchiveClient.ts
- app/frontend/src/services/patientClient.ts
- app/frontend/src/services/patientScope.ts
- app/frontend/src/services/patientSessionStore.ts
- app/frontend/src/services/patientTimelineClient.ts
- app/frontend/src/services/patientTimelineGrouping.ts
- app/frontend/src/services/radiologyClient.ts
- app/frontend/src/services/simpleCaseClient.ts
- app/frontend/tests/patientIsolation.test.mjs
- app/frontend/tests/patientTimeline.test.mjs
- docs/patient-isolation-timeline-report-types.md
