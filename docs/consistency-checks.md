# Deterministik veri tutarlılığı — zincir PR'lar

Hiçbir bayrak varsayılan açık değildir. Ortam değişkenleri veya canlı ayarlar bu
çalışmada değiştirilmez. Kural çalıştırmak için örneğin testte Settings örneğinin
ilgili boolean değeri açılır; feature kodu kapalıyken mevcut akış korunur.

## PR 1: rapor ve UI

`consistency_section_enabled=True`: ingestion_reasons ve document_warnings tüm
satırlardan, LLM çağrısından önce derlenir. Parametre/belge, tarih, sayfa ve satır
korunur. Aynı yapı LLM payload'ında `consistency_flags` olarak taşınır. LLM'in
üretmesi gereken sekiz başlık değişmez; backend uyarı bölümünü çıktının başına
kendisi koyar. LLM yanlışlıkla bu bölümü yazarsa kendi bölümü kaldırılır.
Uyarı yoksa "Tespit edilen veri tutarsızlığı yok." yazılır. UI aynı metadata ile
satır bazlı Türkçe panel gösterir. PDF aynı başlığı ve metni korur.

False iken prompt, rapor metni, eski API yanıt alanları ve eski sarı bant korunur;
yeni opsiyonel response alanı serialize edilmez. Eski kayıtlara migration yoktur.
Türkçe kod sözlüğü, eşikler ve listeler `consistency_config.py` içinde tutulur.
Bu PR yeni tutarsızlık bulgusu üretmez; mevcut gerekçeleri deterministik taşır.

Doğrulama: bölüm/payload eşitliği, LLM'in başlığı ele geçirememesi, eksik/verisiz
uyarılar, sayfa/satır bilgisi, default False ve False yanıt/prompt eşitliği; UI
paneli ve üretim build'i. Tam mevcut CI test listesi de çalıştırılır.

## PR 2: laboratuvar kuralları

`lab_consistency_rules_enabled=True`: validate_merge'in çıktısında ek işaretleme
çalışır; validate_merge değiştirilmez. Kaynak H/L yönü, tam beşli diferansiyel
(toplam 100±5), mutlak/yüzde/WBC (>%10), protein toplamı (>0.3 g/dL), basılı
referans/işaret, büyüklük (×10) ve DB referans ayrışması (>×5) denetlenir. Çok
satırlı hesaplar yalnız bilinen aynı klinik tarih ve tekil küratörlü parametre
setinde yapılır. Birim çözülemezse hesap atlanır ve gerekçe eklenir. Türetilmiş
globülin toplam kontrolüne sokulmaz. Sayısal olmayan/kıyaslayıcılı gözlemler için
aritmetik değer uydurulmaz. Yeni anotasyon kodları kanonik durumu değiştirmez;
eski doğrulama/okuma çatışmalarının UNKNOWN davranışı aynen kalır.

Save/detail/AI yolları, yaş/cinsiyet biliniyorsa mevcut ReferenceResolver'ı,
*basılı aralık verilmeden* DB aralığını istemek için kullanır. DB verisi,
demografi veya birim uyumu yoksa karşılaştırma atlanır. Basılı referans asla DB
referansıyla değiştirilmez. Kurallar tekrar çalıştırıldığında kod çoğaltmaz.
Her kuralın pozitif/negatif/eksik veri, kapalı bayrak, tarih/birim/türetilmiş
korumaları ve resolver kontratı test edilir.

## PR 3 — Rapor içi tanımsal kontroller

`report_consistency_enabled=True` bulgu/sonuç kavram polaritesini, aynı organın tarafını, kayıtlı cinsiyete özgü organ terimlerini, gelecekteki rapor tarihini ve tetkik → rapor → yükleme tarih sırasını kontrol eder. Eksik alanlar atlanır. Tarihler İstanbul takvim gününe çevrilir. İki bölümde de aynı organın tarafı açıkça belirtilmedikçe taraf kuralı çalışmaz; iki tarafı da içeren bulgular tek taraflı sonuçla otomatik çelişki sayılmaz.

Kavram yardımcı işlevi mevcut radyoloji okuyucu karşılaştırıcısından çıkarılmıştır. Eski karşılaştırıcı aynı 70 karakterlik pencere/olumsuzluk davranışını korur. Yeni rapor kuralı cümle sınırlarıyla çalışır. Bu sınırlı, küratörlü sözcük taraması klinik doğruluk veya bütün çelişkileri bulma garantisi değildir; teşhis, düzeltme veya tedavi üretmez.

Kaydetme, normalizasyon, vaka detayını yeniden açma ve AI hazırlama yolları aynı anotasyonu kullanır. `consistency_section_enabled=True` olduğunda PR 1 listesi ve sunucunun ürettiği rapor bölümü bu kodları da içerir. Kapanınca yeni rapor anotasyonu eklenmez.

Doğrulama: yeni 20 test; CI kapsamındaki tüm 419 backend testi geçti. Her beş gerekçe kodu için pozitif/negatif/eksik veri; kapalı bayrak; tekrar çalıştırma; kaynak metinlerin değişmemesi; cümle izolasyonu; saat dilimi; AI'ya tek çağrı ve garanti bölüm test edildi. PR 1 frontend testi/build sonucu da geçerlidir (bu PR frontend değiştirmez).

## PR 4 — Tüm laboratuvar sayfalarında bağımsız çift okuma

`lab_cross_read_enabled=True`: seçilebilir metni bulunan PDF sayfasında yerel parser + Claude; tarama/görüntüde Claude + OpenAI aynı anda başlar. PDF olmak tek başına metinli sayfa sayılmaz. Eski hızlı parser dönüşü bu bayrak açıkken ikinci okumayı atlamaz. Bayrak kapalıyken eski yerel parser → Claude → gerekirse OpenAI yolu aynen çalışır.

Küratörlü alias + semantik tarih alanları eşleştirilir. Küratörlü olmayan adlarda yalnız normalize edilmiş aynı isim kullanılır, fuzzy eşleştirme yapılmaz. Farklı tarihler birleştirilmez; çoklu/tekil olmayan eşleşmeler zorla seçilmez, gözlemler korunur ve eşleştirilemeyen satır işareti alır. Eşleşen satırda A'nın ham değeri gösterilir; iki okuyucunun değer/birim/referansı `reader_values` içinde korunur. B'de bulunan ek satır kaybolmaz. Hiçbir değer ortalanmaz, düzeltilmez veya doğru ilan edilmez. Bir okuyucu satır üretemezse kalan okumanın bütün satırları `cross_read_unavailable` olur. İki okuyucu da başarısızsa eski açık hata akışı korunur.

Her okuyucunun görünür/çıkarılan satır sayısı, hata/uyarısı ve tamamlık durumu ayrı `reader_reports` içindedir. Claude'un mevcut tamamlık geçişi korunur; OpenAI için eksik/belirsiz küçük tabloya en fazla bir ek geçiş yapılır. Bir okuyucunun görmediği satır yokluk oyu değildir. Birleştirilmiş tablo için görünür satır sayısı veya tamlık garantisi uydurulmaz. Bilgi amaçlı `cross_read_agreed`, validate_merge'den **sonra** eklenir, kendi başına `needs_review` değiştirmez. PR 2 kuralları da çapraz okumadan sonra çalışır. `validate_merge` gövdesi değiştirilmez.

### Süre, token ve maliyet analitiği

Her okuyucu/sayfa için süre, gerçek sağlayıcı response usage token'ları ve bilinen fiyat varsa tahmini USD kaydedilir. Tamamlık çağrıları aynı okuyucuya eklenir. ContextVar eşzamanlı okuyucu kayıtlarını ayırır. Yerel parser maliyeti 0; bilinmeyen model/cache fiyatı veya usage bilgisi için maliyet **null** ve açıklayıcı durum kodu kullanılır, sıfır uydurulmaz. Fiyat listesi/eşikler de `consistency_config.py` içindedir. Yeni fiyat doğrulanmadan modele fiyat atanmaz.

Hasta kaydına bağımlı olmayan `lab_reader_events` telemetri tablosu, başarısız/kaydedilmemiş belge okumalarını da tutar. Mevcut startup migration deseninde idempotent tablo/index hazırlığı **yalnız çift okuma bayrağı True ise** yapılır. False iken tablo oluşturulmaz ve telemetri yazılmaz. Bu oturumda canlı DB migration'ı veya ayar değişikliği uygulanmadı. Kayıtlar hasta kimliği, belge görüntüsü, dosya adı veya klinik metin içermez. Aynı event UUID'siyle tekrar sayılmaz. Mevcut admin yetkili `/analytics/ai-costs` endpoint'i bu bayrak açıkken API'ye eklenir ve `lab_readers` toplamını sunar. Klinik özet maliyet alanları korunur. Telemetri yazma hatası belge sonuçlarını düşürmez; güvenli uyarı loglanır. Belge işlemi iptal edilirse başlamış okuyucuların telemetrisi yazılıp iptal yeniden iletilir.

### Test kapsamı

Aynı okuma, değer farkı, birim/referans farkı, tek okuyucu, okuyucu hatası; gerçek paralel başlangıç; ayrı satır sayısı ve tamamlık; iki başarısız okuyucu; tarih/alias/tekrar gözlemler; eksik hücreler; agreement review koruması; gerçek upload yolunda iki bayrak durumu ve PR 2 sıralaması; metinli PDF'de hızlı dönüşün ikinci okuyucuyu atlamaması; sağlayıcı sınırında gerçek usage yakalama (mock response); anonim telemetri, admin maliyet endpoint'i, yazma hatası ve iptal testleri.

Son doğrulama: CI listesindeki **450 backend testi** ve ayrıca mevcut radyoloji ikinci okuyucu/karşılaştırıcı dosyasındaki **5 test** geçti. Frontend'in **15 test dosyası**, TypeScript kontrolü ve Vite production build başarılı. Bunlar gerçek ücretli sağlayıcı veya canlı veritabanı kullanmadan çalıştırıldı; SQL oturumları ve sağlayıcı yanıtları taklit edildi. Bayraklar canlıda açılmadı. `validate_merge` fonksiyon gövdesinin main ile kaynak metni eşitliği de kontrol edildi. Mevcut passlib/crypt kullanım ömrü uyarısı ve frontend paket boyutu uyarısı build'i engellemedi.

## Eklenen 19 gerekçe kodu

| Kod | Türkçe açıklama |
|---|---|
| `source_flag_status_conflict` | Basılı yüksek/düşük işareti ile kanonik durum çelişiyor. |
| `differential_sum_mismatch` | Beş lökosit yüzdesinin toplamı beklenen 100 sınırının dışında. |
| `absolute_percent_mismatch` | Mutlak hücre sayısı ile yüzde × WBC / 100 hesabı uyuşmuyor. |
| `protein_sum_mismatch` | Total protein ile albümin + globülin toplamı uyuşmuyor. |
| `value_outside_reference_no_flag` | Değer basılı referans dışında, ancak kaynak durum işareti yok. |
| `flag_without_reference_breach` | Değer basılı referans içinde, ancak yüksek/düşük işareti var. |
| `magnitude_suspect` | Değer referansa göre büyüklük açısından şüpheli; ondalık, virgül veya birim kontrol edilmeli. |
| `printed_reference_divergence` | Basılı referans ile aynı yaş/cinsiyet için veritabanı referansı belirgin farklı. |
| `consistency_unit_unresolved` | Birim güvenle normalize edilemedi; ilgili sayısal kural atlandı. |
| `report_findings_impression_conflict` | Bulgular ve sonuç bölümlerinde aynı kavram için karşıt ifadeler var. |
| `report_laterality_conflict` | Bulgular ve sonuç bölümlerinde aynı organın tarafı farklı. |
| `report_patient_sex_mismatch` | Rapordaki cinsiyete özgü organ terimi ile kayıtlı cinsiyet uyuşmuyor. |
| `report_date_in_future` | Rapor tarihi gelecekte. |
| `report_date_order_conflict` | Rapordaki tarih alanlarının sırası tutarsız. |
| `cross_read_unavailable` | Bağımsız okuyuculardan biri tamamlanamadı; tek okuma kullanıldı. |
| `cross_read_agreed` | İki bağımsız okuma değer, birim ve referansta aynı; bu, doğruluk garantisi değildir. |
| `cross_read_value_conflict` | İki bağımsız okuyucu farklı değer okudu; her iki okuma saklandı. |
| `cross_read_unit_or_reference_conflict` | İki okuyucunun birim veya referans okuması farklı. |
| `cross_read_single_reader_only` | Satır yalnızca bir okuyucuda bulundu; diğer okuyucunun görmemesi yokluk kanıtı değildir. |
