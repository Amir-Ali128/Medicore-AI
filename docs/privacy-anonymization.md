# MediCore AI — zorunlu Privacy Gateway

Bu katman, dış AI sağlayıcısına giden **doğrudan hasta tanımlayıcılarını** yerel olarak ayıklar. `ai_privacy_mode` yalnız `strict` kabul eder; kapatma veya debug bypass seçeneği yoktur. Laboratuvar tutarlılık bayraklarının kapalı olması gizlilik katmanını kapatmaz. Tanı, tedavi, klinik eşik veya referans seçme algoritmaları değiştirilmez.

## Veri akışı

```text
Yetkili kullanıcı + mevcut hasta/vaka seçimi
    → İstek bağlamı: mevcut kaynak/hasta ID'leri
    → İlk gerçek AI denemesinde erişim kontrollerinden sonra DB kimliklerini yükle
    → Metin / PrivateMedia (henüz base64 olmayan yerel dosya)
    → Privacy Gateway
        Metin: DB eşleşmeleri + etiket/regex temizliği
        Metin PDF: gerçek içerik redaksiyonu + temiz yeni PDF
        Tarama/görsel: yerel RapidOCR → siyah piksel maskeleme → yeniden OCR kontrolü
    → Son metin / PDF / taşınacak JSON sızıntı kontrolü
    → Yalnız ortak istemci içinde base64 oluştur
    → Güvenli audit kaydı
    → OpenAI / Anthropic / Gemini SDK
```

Başarısız temizleme yolu SDK'ya ulaşmaz. Her retry, tamamlık geçişi ve bağımsız ikinci/üçüncü okuyucu aynı geçidi kullanır. `PrivacyViolation` genel sağlayıcı hatası, klinik fallback veya daha az güvenli başka bir sağlayıcı çağrısına dönüştürülmez. Kullanıcıya HTTP **422**, `code=PRIVACY_REDACTION_FAILED` ve şu metin döner:

> Belgedeki kişisel bilgiler güvenli biçimde silinemediği için belge yapay zekâya gönderilmedi. Lütfen kimlik bilgilerinin görünmediği bir sürüm yükleyin.

## Neler kaldırılır?

- DB'deki ad/soyad/tam ad; bilinen kimliğin ayrı ad ve soyad parçaları. Türkçe İ/ı, Ş/ş, Ğ/ğ, Ü/ü, Ö/ö, Ç/ç ve büyük/küçük harf farkları dikkate alınır. Bilinen tam isim satır sonundan bölünebilir.
- Bilinen TCKN/ulusal kimlik, telefon, e-posta, adres, doğum tarihi, protokol ve harici hasta referansı. Kategorisi DB alanından gelen tanımlayıcılar doğru yer tutucuyla değiştirilir.
- Resmî sağlama toplamı doğru 11 haneli TCKN; +90/0090 telefon ve 05xx cep numaraları, e-posta ve TR IBAN desenleri.
- Hasta Adı, Ad Soyad, Doğum Tarihi, Adres, Dosya/Protokol/Kayıt/Hasta No, Barkod gibi etiketli değerler. Etiket ile değer aynı satırda veya değer etiketin altındaki satırda olabilir. JSON'daki kimlik/doğum tarihi alanları da işlenir.
- Özgün dosya adları, kişisel veri içerebildiği için sağlayıcıya genel bir dosya adı olarak gider. Kaynak dosyalar ve kullanıcıya ait yerel/vaka kayıt adları gizlilik katmanı tarafından yeniden yazılmaz.

Yer tutucular: `[HASTA_ADI]`, `[TCKN]`, `[TELEFON]`, `[EPOSTA]`, `[ADRES]`, `[DOGUM_TARIHI]`, `[KAYIT_NO]`. Audit sayıları silinen değerleri değil, kategori bazında değiştirme işlemlerini sayar.

**Geçersiz sağlama toplamına sahip etiketsiz 11 haneli sayı** sırf uzunluğu nedeniyle silinmez; laboratuvar/örnek numarası olabilir. Aynı sayı bir kimlik alanıyla etiketlenmişse veya DB'de bilinen kimlikse kaldırılır. Bu davranış testlerde sabittir. JSON sayısı olarak gelen geçerli TCKN de korunmaz.

Doğum tarihi gönderilmez; mevcut yaş korunur veya DOB yerine tamamlanmış yıl olarak yaş hesaplanır. Gerçek klinik olay, numune ve rapor tarihleri trend mantığı için korunur. `relative_day(date, anchor=...)` yardımcı işlevi yalnız mutlak tarihin gereksiz olduğu gelecekteki prompt'lar için hazırdır; mevcut tarih/trend prompt'ları göreli tarihe çevrilmemiştir.

## Dosya temizliği ve hata durumunda gönderimi engelleme

Metin PDF'lerinde PyMuPDF karakter kutularıyla gerçek redaksiyon yapılır; Türkçe harf ve satıra bölünmüş isimler yalnız `search_for` ile aranmaz. `apply_redactions`, yeni belgeye sayfa kopyalama, `garbage=4, clean=True` kullanılır. Belge başlığı/yazarı/konusu/anahtar kelimeleri ve XMP kaldırılır; özgün doküman ekleri, bağlantı ve anotasyon yükleri kopyalanmaz. Son PDF metni yeniden kontrol edilir.

Görsel içeren veya metinsiz PDF sayfaları yerelde rasterize edilir, OCR kutuları piksel olarak siyaha boyanır ve sayfalar yalnız temiz görüntülerden yeniden kurulur. Eski gizli metin katmanı bu sayfalara taşınmaz. Görseller EXIF yönüne çevrilir; RGB piksellerden yeniden kodlanarak EXIF/GPS/XMP/ICC metadata'sı aktarılmaz. Belirtilen JPEG/PNG/WEBP formatı korunur.

OCR, mevcut `local_ocr_lab_parser` motorudur. Eski OCR yardımcısının hata yutup boş liste döndürmesi güvenlik kararı için kullanılmaz. Motor hatası, ilk geçişte boş sonuç veya düşük güvenli metin anonimleştirmeyi durdurur. Yeniden OCR'de boş sonuç yalnız ilk geçişteki bütün metin kutuları maskelenmişse kabul edilir; motor hatasına fallback yapılmaz. Paylaşılan OCR motoru eski yerel parser ile aynı kilidi kullanır; eşzamanlı sayfaların sonuçları karışmaz.

`rapidocr-onnxruntime>=1.4.4,<2.0`, zaten repo'da kullanılan yerel motoru sıkı modda kullanılabilir kılmak için default requirements'a eklendi. Yeni bir harici OCR servisi kullanılmaz. ONNX model dosyaları paketle gelir. OCR kurulumu/modeli bozuksa belge dış sağlayıcıya gönderilmez. DICOM ve desteklenmeyen ham dosya/uzak URL/file-id payload'ları ortak geçitten geçirilmez; **engellenir**. Yalnız yerel ve doğrulanabilir `PrivateMedia` kabul edilir.

Bu katman DB'deki özgün klinik notu veya hasta belgesini kalıcı olarak temizlemeye çalışmaz; görevi dışarıya giden kopyayı temizlemektir. Arşivleme için mevcut `pdf_privacy.py` yolu ve frontend demo/dev maskelemesi ayrı kalır.

## Python çalışma sürümü

Python **3.12.14** repo kökündeki ve Render servis kökü `app/backend` altındaki `.python-version` dosyalarında sabittir. CI da repo kökündeki aynı dosyayı okur ve iki pinin eşitliğini kontrol eder. `rapidocr-onnxruntime` 1.4.x Python `<3.13` gerektirir; Render'ın değişebilen varsayılan 3.14 sürümüyle kurulum başarısız olur. Paketi kaldırmak veya gizlilik denetimini atlamak çözüm değildir.

Render'ın açık `PYTHON_VERSION` ortam değişkeni `.python-version` dosyasından önceliklidir. Bu düzeltmede servis ortam değişkenleri değiştirilmedi; hata logunda kullanılan sürüm zaten `(default)` olarak belirtiliyordu.

## Hasta bağlamı ve erişim

`ai_privacy_context.py::load_patient_identifiers` mevcut Patient alanlarını ve kimlik metadata alanlarını kullanır; klinik notu bütünüyle kimlik listesine katmaz. İstek bağımlılığı path/query/form/JSON içindeki mevcut hasta ve kaynak ilişkilerini çözebilir. İlk SDK denemesine kadar DB sorgusu yapmaz; AI kullanmayan ekranların erişim/hata akışı korunur. İki okuyucu aynı istek oturumunda paralel DB sorgusu açmaz; ilk kimlik yüklemesini paylaşır. `ContextVar` farklı kullanıcı/hasta isteklerini ayırır ve istek bitince sıfırlanır.

Vaka ekranındaki dört belge yükleme çağrısı seçili hasta ID'sini isteğe bağlı taşır. Backend bu ID için mevcut hasta erişim kontrolünü uygular. Yeni/kaydedilmemiş vaka ve hasta bağlamı olmayan çağrılar regex/etiket katmanı + son kontrolü kullanır. Sonradan başka bir süreçte doğrudan domain servisi çalıştırılacaksa aynı DB bağlamı açıkça kurulmalıdır; istek bağlamı olmayan iş otomatik olarak bir hastaya bağlanmış sayılmaz.

## Sağlayıcı çağrı envanteri

Aşağıdaki 13 gerçek SDK çağrı noktası `ai_privacy_client.py::privacy_call` üzerinden geçer:

| Modül | Çağrı |
|---|---|
| `claude_lab_extraction_service` | Anthropic laboratuvar ve tamamlık geçişi |
| `openai_lab_extraction_service` | OpenAI laboratuvar PDF/görüntü |
| `openai_case_document_service` | OpenAI birleşik belge |
| `scanned_medical_report_pdf_ai` | OpenAI taranmış rapor; Anthropic sayfa yolu da ortak görüntü okuyucusunu kullanır |
| `report_document_image_ai` | Anthropic rapor/görüntü |
| `radiology_image_ai` | Anthropic radyoloji görüntüsü |
| `openai_radiology_second_reader` | OpenAI bağımsız radyoloji okuması |
| `gemini_radiology_third_reader` | Gemini bağımsız radyoloji okuması |
| `claude_clinical_hypothesis_service` | Anthropic klinik metin |
| `simple_case_ai` | Anthropic vaka raporu ve sınırlı başlık retry'ı |
| `source_only_case_evaluation` | Anthropic kaynak temelli değerlendirme |
| `medical_report_summary_ai` | OpenAI tıbbi rapor metni |
| `openai_lab_clinical_service` | OpenAI laboratuvar klinik sentezi |

`multisource_summary_runtime`, `universal_medical_report_runtime` ve `structured_report_contract_runtime` yeni SDK isteği kurmaz; yukarıdaki korunan metin/medya okuyucularına gider. Bunların gizlilik hatasını yutan handler'ları da düzeltildi. Devre kesici gizlilik engelini sağlayıcı arızası saymaz.

Bilerek ayrı kalan yollar:

- `claude_usage_runtime` saf bir usage proxy'sidir; zaten temizlenmiş `*args/**kwargs` ile SDK'ya iletir, yeni prompt/medya oluşturmaz.
- `claude_sonnet5_compat_runtime` yalnız sampling/thinking uyumluluk parametrelerini düzenler; temizlenmiş isteğe ham klinik veri eklemez.
- `clinical_voice` yerel/offline ASR kullanır, ses veya transkript harici sağlayıcıya gitmez. Sunucu hazırlığında yalnız sabit revizyon/hash ile doğrulanan kamuya açık model yazılımı indirilir; bu işlem hasta girdisi almaz ve transkripsiyon endpointinde çalışmaz.
- `analytics.py` içindeki opt-in IP geolocation HTTP istemcisi AI/patient document transport değildir; değiştirilmedi.
- Yerel deterministik parser, OCR, sınıflama ve arşiv işlemleri dış sağlayıcı çağrısı değildir.

AST testi domain/API altında doğrudan `messages/responses/interactions/completions.create`, `generate_content` çağrılarını ve `b64encode` kullanımını reddeder. Yeni ham HTTP istemcileri de allowlist dışında reddedilir. Bu test dinamik çalışma zamanı kod enjeksiyonuna karşı bir sandbox değildir; yeni entegrasyonlar yine kod incelemesi gerektirir.

## Audit

`medicore.privacy.audit` logger'ına yapılandırılmış JSON yazılır: UTC timestamp, provider, modül/call site, yalnız iç hasta UUID'si (bağlam yoksa null), kategori sayıları ve `blocked` boolean. Silinen değerler, dosya adı, görüntü, prompt, kimlik eşleme tablosu veya ham payload loglanmaz. Her gerçek SDK denemesi/retry ayrı kayıt üretir. Yeni DB tablosu/migration gerekmez; operasyonel log saklama/erişim politikası ayrıca yönetilmelidir.

## Kalan sınırlar ve sonraki adımlar

Bu mekanizma her sağlık kaydını hukuken tamamen anonim hale getirdiği veya KVKK aktarım şartlarının tamamını sağladığı iddiasında değildir. Özellikle:

- DB bağlamında bilinmeyen, etiketsiz serbest metin isimleri/akraba ve hekim adları için Türkçe NER henüz yoktur.
- OCR yanlış okuyabilir veya bir metin bölgesini hiç algılamayabilir. Yeniden OCR ve düşük güven engeli bu riski azaltır; sıfırlamaz. Kimlik ile sayısal klinik birimi aynı ayrıştırılamayan etiket/OCR kutusunda olan satır, laboratuvar değerini silmek yerine engellenir. Bu koruma bütün klinik ifade çeşitlerini tanıyan bir model değildir; sayısal/birim deseni dışındaki yakındaki metin de maskelenebilir. Yoğun/alışılmadık belgelerde kullanıcı kimliksiz bir kaynak hazırlamalıdır.
- Etiketsiz QR/lineer barkod, el yazısı ve metin dışı/varyant yazı biçimleri eksiksiz çözümlenmez. PDF/görüntü ayrıştırıcısının göremediği içerikler ve dolaylı yeniden kimliklendirme riski ayrıca değerlendirilmelidir.
- DICOM gateway tarafından desteklenmez ve ham DICOM gönderimi engellenir; bir DICOM anonimleştirme standardı uygulandığı iddia edilmez.
- Yaş/cinsiyet/tarih/çok nadir bulgu birleşimi dolaylı tanımlayıcı olabilir; klinik trend işlevi korunurken bunların bütünüyle anonim olduğu varsayılmaz.

Sonraki adımlar: yerel Türkçe NER ve alan/kurum bazlı doğrulanmış maskeleme; ayrı şifreli kimlik tablosu ve dar erişim; belge/görüntü için ölçülmüş OCR recall veri kümesi; DICOM/QR-barkod politikası; sağlayıcı ZDR/DPA sözleşmeleri; KVKK yurt dışına aktarım için uygun standart sözleşme ve diğer hukuki/operasyonel yükümlülükler.

## Doğrulama

Yalnız sentetik isim, testte üretilen sağlama toplamı geçerli TCKN ve uydurma iletişim verileri kullanılır. Metin kategorileri, Türkçe harfler, ayrık isim parçaları; gerçek PDF redaksiyonu ve metadata; EXIF/GPS; tarama görüntüsü kutuları; OCR yokluğu; gerçek paket içi offline OCR; 13 çağrı noktasındaki yakalanan SDK payload'ları; 8 medya yolunda sıfır SDK çağrısıyla engelleme; audit; DB kimlik bağlamı; eşzamanlı izolasyon; HTTP 422; DOB→yaş ve klinik tarih/değer koruması; JSON anahtarı/sayısal TCKN, JSON-prefix retry, karışık kimlik/laboratuvar satırını engelleme ve AST sınırı sınanır.

CI listesine iki gizlilik dosyası ve ilgili eski sağlayıcı regresyonları eklendi. Eski SDK testlerindeki geçersiz `b'image'`/sahte PDF baytları gerçek sentetik dosyalarla değiştirildi; OCR taklidi yalnız açıkça işaretlenen eski test fixture'larında kullanılır, üretim kodunda bypass yoktur. Gerçek offline OCR ayrıca otomatik test edilir.

Tüm eski testleri birlikte toplama denemesinde önceden bulunan dört collection hatası vardır: `test_combined_case_import.py`, `test_lab_image_extraction.py`, `test_patient_lab_history.py`, `test_universal_lab_ingestion.py`. Başlangıç commit'i `1f96eb1` de `native_lab_engine` / `canonical_native_trust` modüllerini içermez. Bu dört dosya ayrıldığında altı eski hata kalır: `test_claude_possibility_review_runtime`, `test_clinical_ai_performance`, `test_lab_pdf_system_extract_runtime` (iki test), `test_radiology_report_safety`, `test_report_type_inference`. Aynı altı hata temiz başlangıç checkout'ında da tekrarlandı (**580 passed / 6 failed**); gizlilik öncesi mevcut duruma aitler. Kaldırılmış native pipeline bu görev için geri getirilmedi ve klinik çıktılar bu testleri yeşile çevirmek amacıyla değiştirilmedi.

Son yerel doğrulama (9 Kasım 2026): genişletilmiş aktif CI listesindeki **510 backend testi** başarılı; bunun **46** tanesi gizlilik/gateway canary testidir. Frontend'de **132 test**, TypeScript kontrolü ve Vite production build başarılı. Mevcut passlib/crypt ve frontend paket boyutu uyarıları kontrolü engellemedi. Sağlayıcı istemcileri ve DB oturumları taklit edildi; gerçek yerel OCR modeli yalnız sentetik görüntüde çalıştırıldı. Ücretli AI çağrısı, canlı veritabanı sorgusu/migration, ortam değişkeni değişikliği veya deploy yapılmadı.

## OCR bellek sınırlandırması (2026-11-11)

PDF yüklemelerinden hemen sonra canlı süreç iki kez yeniden başladı (11:53:45
ve 11:55:24 Türkiye saati). 30 saniyelik metrikler kısa tepeyi yakalamadı;
bellek taşması olasılığı yerel yeniden üretimdeki yüksek OCR belleğiyle tutarlı.
RapidOCR'nin varsayılan `min` ölçeklemesi dar görselleri büyütüyor, büyük sayfaları
ise tam boyutta tek çıkarımda işliyordu.

Yerel OCR artık kaynak çözünürlüğünü düşürmeden tam genişlikte, yarı örtüşen
şeritler kullanır. Her çağrı en çok 262144 kaynak piksel içerir; otomatik büyütme
ve geniş şeritlere boşluk ekleme kapalıdır. Algılama/okuma aynı yerel modelleri
kullanır; okuma batch'i 1'dir. Koordinatlar özgün sayfaya taşınır, aynı metnin
örtüşen kutuları tekilleştirilir. Farklı okunan değerler sessizce seçilmez.
Kesilmiş satırın tam karşılığı yoksa veya genişlik 3200 pikseli aşıyorsa güvenli
hata verilir; Privacy Gateway geçilemez. PDF raster kopyaları azaltıldı;
maskeleme sonrası tam çözünürlükte yeniden oluşturma ve ikinci OCR kontrolü sürer.

Doğrulama: 534 aktif backend testi geçti. Gerçek yerel modelle sentetik A4 tarama
maskelendi ve klinik satırlar korundu; tepe RSS yaklaşık 469 MiB oldu. Önceki
ses→OCR→ses denemesi yaklaşık 714 MiB iken sınırlı OCR ile yaklaşık 444 MiB oldu.
Bu sayılar belirli sentetik girdilerdir; tüm belgeler/eşzamanlı yük için 512 MiB
kapasite garantisi değildir. Ücretli plan veya ortam değişkeni değiştirilmedi.
