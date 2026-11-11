# Laboratuvar referans ayrıştırma ve sınıflandırma düzeltmesi

Dal: `fix/lab-reference-parsing-classification`. Teslimat PR'dır; main'e merge veya
Render deploy yapılmaz. API sürümü `medicore-simple-case-v1` korunur.

## Kök neden ve kanıt

Yalın sayı + yalın aralık örnekleri mevcut main üzerinde zaten doğruydu:
`14.8`, `4.0–10.0` → HIGH. Bu nedenle bütün UNKNOWN sonuçlarının parser hatası
olduğu varsayılmadı. Main'deki sınıflandırıcı ayrı bir yerel modüle yüklenerek
aynı girdilerle önce/sonra karşılaştırması yapıldı; harici AI çağrısı kullanılmadı.

1. `app/backend/app/domain/lab_result_classification.py::classify_lab_result`:
   `_VALUE` yalnız sayıyı kabul ediyor; `94 mg/L` invalid_observed_value oluyordu.
   `Ref:`, `Reference:` ve `Normal:` önekleri yapılandırılmış sınırlar yokken
   tanınmadığından geçerli basılı aralık missing_numeric_reference oluyordu.
2. `fast_pdf_lab_parser.py::_parse_numeric_value/_parse_reference`:
   ayrı/daha dar regex'ler `>=`, Unicode karşılaştırıcı, bilimsel gösterim,
   birimli sayı ve etiketli referanslarda kanonik sınıflandırıcıdan ayrışıyordu.
3. `lab_document_ingestion.py::validate_merge`: raw/numeric uyumu yalnız dar
   regex eşleştiğinde denetleniyordu. `94 mg/L` ile okuyucunun `9` sayısı
   arasındaki çelişki atlanabiliyordu. Tarih grubu belge tarihini kapsamıyordu;
   farklı belge tarihlerindeki gözlemler çelişkili sayılabiliyordu.
4. `simple_case.py::select_source_reference`: eşit uygulanabilir referansların
   ham yazımlarını karşılaştırdığı için aynı aralığın virgül/tire/önek farkları
   çelişki sayılıyordu. Basılı demografik etiketin eksik veya çelişen yapılandırılmış
   uygulanabilirliği de açıkça denetlenmiyordu.
5. `api/routes/simple_case.py::_persist_simple_case_sources`: SQL normalized_value
   ham metinden Decimal'a çevriliyordu; birimli ölçüm sayısal kolonda kayboluyordu.
6. `app/frontend/src/services/labDocumentMerge.ts::mergeLabDocuments`: yeni inceleme
   gerekçeleri eklenmesine rağmen aynı status önbelleği kalabiliyor; status'süz
   belirsiz satır temiz bir tekrar yüklemeden status alabiliyordu. Referans dizisi
   sırası duplicate kimliğini etkiliyordu. Geçersizleştirmede eski kayıtların tek
   basılı referansının korunması da güvenceye alındı.
7. AI serileştirmesi ham değeri taşıyor, fakat açık parsed numeric / comparator /
   censored limit ayrımı taşımıyordu. Ön uç sınıflandırıcı eklenmedi; tek otorite
   backend olarak kaldı.

`openai_lab_extraction_service.py` incelendi: JSON payload'ını aralığa/status'a
çeviren katman değildir; sahte referans üretimi veya status düzeltmesi eklenmedi.
`SimpleCaseWorkspacePage.tsx` backend status'unu gösterir; save sonrası dönen
kanonik satırları state'e koyar. Demografi düzenlenince cache geçersizleşir;
yeniden hesaplama save/normalize/detail/AI backend yollarında yapılır. Yeni
otomatik kayıt veya istemci tarafı tıbbi sınıflandırma eklenmedi.

## Uygulanan davranış

- Ortak `parse_lab_observation` ve `parse_source_reference`: Decimal ile sonlu
  sayılar, virgül, bilimsel gösterim, negatif değerler, Unicode tire/karşılaştırıcı,
  güvenli genel referans önekleri ve doğrulanan fiziksel birim son ekleri.
- Ham `value`, `unit`, referans yazısı ve tarihler değiştirilmez; birim dönüşümü
  yapılmaz. Birimli sayının son eki katalogla doğrulanır; ayrı unit alanı varsa
  onunla da aynı olmalıdır. Tanınmayan son ekler UNKNOWN kalır.
- `normalized_value` yalnız kesin ölçüm için sayıdır. Sansürlü gözlemde null;
  `value_comparator` ve `value_limit` birlikte sınırı taşır. `parsed_unit`, ham
  unit'ten ayrıdır. Bu dört alan input/output şemasında opsiyonel/additiftir;
  gelen cache alanları sınıflandırmada güvenilir kabul edilmez, yeniden hesaplanır.
- Referans katılığı (`<` / `<=`, `>` / `>=`) interval hesabında korunur. Sansürlü
  değerin tüm olası değerleri aynı tarafta değilse UNKNOWN kalır. Bilinen tıbbi
  aralık, tanı başlığı, source_flag veya LLM status'u kullanılmaz.
- Kaynak okuyucunun supplied normalized_value değeri `reader_normalized_value`
  metadatasında saklanır. Çelişki işaretlenir; ham değer korunur ve kesin sayı
  kabul edilmez. Doğrulanan inline birim gerçekten varsa false missing_unit
  gerekçesi üretilmez; bilinmeyen/çelişen birimlerin kontrolü korunur.
- Eşdeğer referans imzaları sayısal sınır, katılık ve birimle karşılaştırılır;
  bütün özgün referans listesi saklanır. Demografi bilinmiyorsa veya basılı
  popülasyon etiketi metadata ile çelişiyorsa UNKNOWN korunur.
- Duplicate frontend birleştirmesi referans listesi sırasından etkilenmez.
  Yeni belirsizlik veya çelişen türetilmiş alanlar kanonik cache'i geçersiz kılar;
  sonraki temiz tekrar yükleme eski belirsizliği silemez. Ham referans/tarih/provenans
  korunur; backend yeniden doğrulaması gerekir.
- SQL ve snapshot katmanları parsed exact sayıyı ve censored limit'i ayrı tutar.
  Yeni additif alanlar eski değişmemiş vaka parmak izini değiştirmez; ham kaynak,
  status veya sınıflandırma gerekçesi değişirse eski AI raporu yine geçersizleşir.
- AI'a raw value, exact numeric (varsa), comparator/limit, ham/parsed unit, source
  reference, structured bounds, canonical status, reason, kaynak belirsizliği ve
  tarihleri birlikte verilir. AI prompt'uyla UNKNOWN gizlenmez. AI raporunun PDF
  export'u mevcut raporu aynen taşımaya devam eder; export kodu değişmedi.

## Önce / sonra

Aşağıdaki satırlarda kaynak ve birim ilişkisi doğrulanmıştır. Referanslar örneğin
kendisinden gelir; genel tıp bilgisinden üretilmemiştir.

| Ölçüm | Kaynak referans | Main öncesi | Düzeltme sonrası |
|---|---|---|---|
| WBC `14.8`, 10^9/L | `4.0–10.0` | HIGH | HIGH |
| WBC `14.8`, 10^9/L | `Ref: 4.0–10.0` | UNKNOWN | HIGH |
| Nötrofil `82`, % | `40–75` | HIGH | HIGH |
| CRP `94 mg/L` | `<5` | UNKNOWN | HIGH |
| Prokalsitonin `0.42 ng/mL` | `Reference: <0.10` | UNKNOWN | HIGH |
| Kreatinin `0.91`, mg/dL | `Normal: 0.5–1.0` | UNKNOWN | NORMAL |
| Kreatinin `1.98 mg/dL` | `0.5–1.0` | UNKNOWN | HIGH |
| AST `31 U/L` | `<35` | UNKNOWN | NORMAL |
| `≤5 mg/L` | `<5` | UNKNOWN | UNKNOWN (ambiguous_censored_value) |
| `3+` | `0–5` | UNKNOWN | UNKNOWN (invalid_observed_value) |

## Testler

- Aktif GitHub CI backend listesi: **589 geçti** (38 yeni parametrik test vakası).
- Frontend: **138 geçti** (4 yeni regresyon); TypeScript ve production build geçti.
- Mevcut consistency flags True/False ve Privacy Gateway testleri de aktif kapsamda.
- Gerçek SQLite/SQL modelleriyle save → detail → save: iki tarihli kreatinin,
  birimli CRP, prefiksli aralıklar, AST ve censored ölçüm; ham değer, status ve
  exact/censored ayrımı korundu. SQL'de `≤5` normalized_value=null kaldı.
- Mock AI sınırı: raw/parsed/reference/status/uncertainty/date serileştirmesi ve
  input değişmezliği denetlendi. Harici AI/hasta verisi gönderimi yapılmadı.
- Tam backend klasörünü toplama denemesi dört eski modülde duruyor:
  `test_combined_case_import.py`, `test_lab_image_extraction.py`,
  `test_patient_lab_history.py`, `test_universal_lab_ingestion.py`.
  Kaldırılmış `native_lab_engine` / `canonical_native_trust` importları eksik;
  bu PR bunları eklemedi/değiştirmedi. Bu yüzden tüm eski backend testlerinin
  yeşil olduğu iddia edilmez; aktif ilgili CI kapsamı yukarıdaki gibidir.
- Mevcut uyarılar: passlib/crypt deprecation, react-test-renderer deprecation,
  Vite büyük chunk bildirimi. Bunlar bu düzeltmenin kapsamı dışında.

## Değişen dosyalar

Backend kodu:
- `app/backend/app/domain/lab_result_classification.py`
- `app/backend/app/domain/fast_pdf_lab_parser.py`
- `app/backend/app/domain/lab_document_ingestion.py`
- `app/backend/app/domain/simple_case.py`
- `app/backend/app/domain/simple_case_ai.py`
- `app/backend/app/api/routes/simple_case.py`
- `app/backend/app/schemas/simple_case.py`

Backend regresyonları:
- `app/backend/tests/test_lab_result_classification.py`
- `app/backend/tests/test_simple_case.py`
- `app/backend/tests/test_simple_case_ai_vaka1.py`
- `app/backend/tests/test_vaka1_persistence_regression.py`

Frontend:
- `app/frontend/src/services/labDocumentMerge.ts`
- `app/frontend/src/services/simpleCaseClient.ts`
- `app/frontend/tests/labDocument.test.mjs`

Teslim raporu: `docs/lab-reference-classification-fix.md`.

## Kalan sınırlar

VAKA28PULMRENSEN'in kaynak PDF'leri bu çalışma alanında bulunamadı; görevdeki
sayısal örnekler yeni bir entegrasyon regresyonunda kullanıldı. Eksik kaynak
aralıkları geri kazanılamaz; eski UNKNOWN kayıtları için kaynak belge gerekebilir.
Inline birim kataloğu bilinmeyen birimlere tahmin yürütmez. Çok anlamlı demografi
metni yapılandırılmış uygulanabilirlik olmadan otomatik seçilmez. Gerçekten
belirsiz/çelişkili gözlemler UNKNOWN ve inceleme tarafında kalır. Bu testler LLM'in
klinik yorum doğruluğunu ölçmez; parser/kontrat/persistence sınırını doğrular.
