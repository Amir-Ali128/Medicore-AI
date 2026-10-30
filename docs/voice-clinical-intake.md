# Türkçe sesli klinik taslak

## Kapsam ve veri akışı

Bu özellik `feature/voice-clinical-intake` dalında incelenmek üzere hazırlanmıştır.
PR'ın merge edilmesi, canlıya yayınlanması veya canlı ortamın hazırlanması bu
görevin parçası değildir. Mevcut karar destek/inference algoritmaları, hasta
kimlikleri, veritabanı şeması ve kayıt endpointleri korunur.

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

## Yerel geliştirme için opsiyonel motor

Bu adımlar **canlı ortamda uygulanmadı**. Varsayılan `requirements.txt` ve canlı
ayarlar değiştirilmedi. Motor/model yokken özellik güvenli biçimde kullanılamaz
durumu bildirir; uzaktaki bir sağlayıcıya otomatik geçiş yapmaz.

```sh
cd app/backend
pip install -r requirements.txt -r requirements-voice.txt
```

Operatörün uygun lisansı ve kaynak güvenilirliğini incelemesi sonrasında bir
multilingual CTranslate2 Whisper modelini önceden yerel dizine hazırlaması gerekir.
İngilizceye özel `.en` modeller kullanılmamalıdır. Örneğin testte kullanılan
`Systran/faster-whisper-small` revizyonu
`536b0662742c02347bc0e980a01041f333bce120` şu dosyaları içerir:

```text
/approved/local/whisper-small/
  config.json
  model.bin
  tokenizer.json
  vocabulary.txt  (veya vocabulary.json)
```

Yalnızca kendi geliştirme sürecinde `CLINICAL_VOICE_MODEL_PATH` bu dizine
ayarlanabilir. Bu PR hiçbir Render servisine, ortam değişkenine veya canlı DB'ye
dokunmaz. Model ağırlıkları Git'e eklenmez. Örnek model indirme yalnızca kamuya
açık model dosyalarını taşır; test/üretim hasta verisi içermez. CPU/int8 kullanılır;
sunucu donanımı, eşzamanlı yük ve gecikme ayrıca ölçülmelidir. Her worker en çok
bir ASR işini çalıştırır; dolu olduğunda 429 döner. Varsayılan kurulumun bu
opsiyonel modeli barındıracak belleğe sahip olduğu varsayılmaz.

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

Yerel doğrulama sonucu: mevcut CI kapsamıyla birlikte **363 backend testi** ve
**130 frontend testi** geçti; TypeScript ve production build başarılı. Gerçek
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

Geri alma, feature commit'inin çıkarılmasıyla mümkündür; migration veya hasta
verisi temizleme işlemi gerekmez. İnceleme teslimatında PR açık bırakılır,
`main` değişmez ve deploy yapılmaz.
