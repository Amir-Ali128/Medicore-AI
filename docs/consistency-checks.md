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
