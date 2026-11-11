# Türkçe sesli klinik taslak

## Kapsam ve veri akışı

Mevcut karar destek/inference algoritmaları, hasta kimlikleri, veritabanı şeması
ve kayıt endpointleri korunur. Ses yalnız sunucuda işlenir; sonuç bir taslaktır.

1. Hasta/Klinik adımındaki **Konuşmaya başla** önce kimlik doğrulamalı
   `GET /clinical-voice/capabilities` ile yerel motorun hazır olduğunu doğrular.
2. Tarayıcı kullanıcıdan mikrofon izni ister; MediaRecorder bağımsız altı
   saniyelik parçalar üretir. En çok üç dakika kayıt yapılır. Sıra sınırlıdır;
   işlem yetişmezse kayıt durur ve okunamayan bölümün tekrarı istenir.
3. Ses yalnızca mevcut `API_BASE_URL` üzerindeki
   `POST /clinical-voice/transcribe` endpointine, mevcut oturum yetkisiyle gider.
   OpenAI/Anthropic, bulut Web Speech veya başka bir ses sağlayıcısına gönderilmez.
4. Sunucu bellekte, en fazla 2 MiB / 15 saniyelik sesi çözer. Yerel
   faster-whisper/CTranslate2 modeli Türkçe (`tr`) transkripsiyon üretir.
   Model/Tokenizer dosyaları önceden mevcut olmalıdır; istek sırasında model
   indirilmez. ONNX Runtime telemetrisi kapatılır. Ham ses/transkript dosyaya,
   hasta kaydına, analitiğe veya uygulama loguna yazılmaz. Yanıt `no-store` taşır.
5. Tarayıcıdaki kural tabanlı çıkarıcı sayıları, yaş/cinsiyeti, açık bölüm
   başlıklarını ve vital etiketlerini mevcut form alanlarına eşler. Yeni tanı,
   klinik öneri veya özet üretmez. Muayene metni mevcut Ek klinik not alanına gider.
6. Kaynak metin, çelişkiler, belirsizlikler, birimler ve eşleşmeyen ifadeler
   önizlemede gösterilir. Hiçbir alan varsayılan olarak seçili değildir.
7. Doktor alanları seçer ve taslağı onaylar. Mevcut sayısal değer/yerine yazılacak
   metin için ayrıca alan bazında izin; işaretli belirsizlik için ayrıca doğrulama
   gerekir. Metin alanlarına ekleme desteklenir. Önizleme sırasında elle değişen
   alan eski taslakla ezilmez; güncelleme istenir.
8. **Seçili alanları forma aktar** yalnızca React form state'ini değiştirir.
   Kalıcı kayıt için mevcut **Vakayı kaydet** veya klinik kaydetme düğmesine
   doktorun ayrıca basması gerekir. Transkript ve ses tarayıcı storage'ına yazılmaz.

Vaka/hesap değişimi, bileşenin kapanması veya iptal mikrofonu kapatır; önceki
vakanın geç gelen yanıtları uygulanmaz. Durdur, son parçanın okunması bitene kadar
taslak onayını açmaz. Mikrofon izni reddedilirse veya hizmet hazır değilse metin
elle girilebilir. Yerel önizleme HTTPS veya localhost gerektirir.

## Yerel motorun hazırlanması

`requirements.txt`, sabitlenmiş `faster-whisper==1.2.1` bağımlılığını içerir.
Sunucu istek kabul etmeden önce `offline_turkish_voice` hazırlık adımı çalışır.
Operatör `CLINICAL_VOICE_MODEL_PATH` tanımlamışsa yalnız bu yerel dizin kullanılır;
hatalı bir override otomatik olarak değiştirilmez.

Override yoksa MIT lisanslı `Systran/faster-whisper-tiny` multilingual modelinin
`d90ca5fe260221311c53c58e660288d3deb8d356` revizyonu hazırlanır. Dört dosyanın
sabit SHA256 ve byte uzunluğu `voice_model_assets.py` içinde kayıtlıdır.
Yalnız sabit HTTPS yazılım URL'leri kullanılır; indirme girdilerinde ses, transkript,
hasta veya istek verisi bulunmaz. İndirme süre/boyut sınırlarıyla yapılır.
Hash ve Türkçe destekli CPU/int8 yükleme başarılı olmadan hazır işareti yazılmaz.
Ağırlıklar `.voice_models/` altındadır ve Git'e girmez. Mevcut doğrulanmış
dosyalar tekrar indirilmez. Ephemeral sunucu yeniden başladığında indirme
tekrarlanabilir; soğuk açılış süresi uzar.

Hazırlık başarısızsa uygulama açılır, runtime health bileşeni degraded olur ve
ses özelliği kapalı kalır. İstek sırasında indirme veya uzak ASR fallback yoktur.
`GET /health/ready` içindeki runtime bileşenleri hazırlık durumunu gösterir.
İsteğe bağlı ön hazırlık komutu:

```sh
cd app/backend
pip install -r requirements.txt
python -m app.infrastructure.voice_model_provisioning
```

ASR ve OCR ortak işlem kilidiyle çalışır. Motor değiştiğinde diğerinin önbelleği
boşaltılır; ses isteği OCR çalışırken 429 alır. Böylece iki motor aynı anda
çıkarım yapmaz. Bu, tek başına sunucu kapasite garantisi değildir: yerel sentetik
ölçümde uygulama+ASR yaklaşık 392 MiB tepe RSS, ASR→OCR→ASR yaklaşık 714 MiB;
OCR tek başına da yaklaşık 679 MiB oldu. OCR sonrası anlık RSS yaklaşık 316 MiB
idi. **512 MiB ücretsiz plan için bu belge iş yükü doğrulanmış değildir.**
Plan/ortam değişkeni/Render ayarı bu değişiklikle değiştirilmez.

## Ayrıştırma örneği ve sınırlar

```text
Altmış beş yaşında erkek.
Şikayetler: iki gündür kusma, ağız kuruluğu.
Anamnez: hipertansiyon.
İlaçlar: amlodipin 5 mg/gün.
Vital bulgular: tansiyon 145/90, nabız 108, solunum 18,
ateş 37,2, SpO2 yüzde 97, boy 178, kilo 82, kan şekeri 108.
Muayenede ağız mukozası kuru, cilt turgoru azalmış.
```

Bu bir genel tıbbi NER/LLM sistemi değildir. Açık başlıklar ve alan etiketleri
tercih edilir. Desteklenmeyen dil, tarihsel/aile bağlamı, bitişik yazılmış sayı
sözcükleri, bilinmeyen birimler ve çelişen sayılar tahmin edilmez; elle doğrulama
veya düzeltme gerekir. `14/9` dönüşümü özellikle işaretlenir. Olumsuz bulgular
metin olarak aynen korunur. Konuşma parçası sınırında sözcük kaybı olabilir;
transkript mutlaka okunup düzeltilmelidir.

## Test ve bilinen eksikler

Bu düzeltmede aktif CI kapsamındaki **527 backend testi**, **16 frontend test
dosyası**, TypeScript ve production build geçti. Model hazırlama, bütünlük,
hata/timeout, override ve yerel motor kaynak yönetimi için 17 test eklendi. Gerçek
Chromium mikrofonu (yalnız sentetik ses), gerçek yerel ASR ve izole SQLite test
API'siyle kayıt öncesi değişmezlik, ayrı alan onayı, açık kaydetme sonrası aynı
UUID/lab/rapor korunması, refresh ve vaka değiştirme kontrolleri geçti. Alan
eşleme/kaydetme kontrolünde hekim düzeltmesini temsil eden açık örnek metin
kullanıldı; bu kontrol ASR'nin her sözcüğü doğru okuduğu anlamına gelmez.

- Backend testleri: authentication, boyut/süre sınırı, gerçek ses çözme, sessizlik,
  model yokluğu, kapasite, hata/log gizliliği, yerel dosya zorunluluğu, sabit Türkçe,
  model cache'i, İngilizceye özel modelin reddi, uzak playlist/protokol engeli ve
  ağ erişimi olmadan ASR çağrısı.
- Frontend testleri: çok alanlı çıkarım, Türkçe sayılar, birimler, negatif/familial
  bulgular, belirsizlik/çelişki, alan bazında overwrite izni, eşzamanlı düzenleme,
  hasta değişimi, mikrofon izni, geç yanıt, son parçayı bekleme, backpressure,
  taslakların kayıt/AI isteği oluşturmaması.
- Tam mevcut CI listesi, TypeScript ve production build çalıştırılır.
- Yerel smoke: yalnızca sentetik Türkçe TTS sesi; model dosyaları hazırlandıktan
  sonra dış ağ kapalı ve Python socket bağlantıları engellenmiş halde ASR denendi.
  Small model yaş/cinsiyet ifadesini okuyabildi; robotik TTS'deki vital ifadelerini
  tam doğru okuyamadı. Tiny model de hatalar yaptı. Bu, klinik doğruluk kanıtı
  değildir; düşük akustik belirsizlik puanı bile doğruluk garantisi sağlamaz.
- Gerçek hekim sesi, aksan/gürültü, özel tıbbi terim, farklı cihaz/tarayıcı ve
  hastane iş akışı değerlendirmesi henüz yapılmadı. Klinik kullanımdan önce bu
  değerlendirme, sunucu kapasitesi ve kurumun ses/veri işleme politikası gerekir.

Geri alma, düzeltme commit'inin çıkarılmasıyla mümkündür; migration veya hasta
verisi temizleme işlemi gerekmez. İnceleme teslimatında PR açık bırakılır,
`main` değişmez ve deploy yapılmaz.
