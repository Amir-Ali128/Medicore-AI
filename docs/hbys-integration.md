# HBYS Entegrasyonu ve Sanal HBYS

Medicore, hastane bilgi yönetim sistemlerinden (HBYS) muayene verisini **FHIR R4**
üzerinden alır ve AI ön değerlendirme raporunu yine FHIR ile geri gönderir. Geliştirme
ve demo için repoda gerçek bir HBYS'nin yerine geçen **Sanal HBYS** (`app/hbys_sim`)
servisi bulunur.

## Akış

```
Sanal/gerçek HBYS ──FHIR Bundle──▶ Medicore /hbys/encounters/{id}/case
                                     │  kimlik alanları atılır, serbest metin temizlenir
                                     ▼
                         normal vaka kaydı (/patients + /simple-case/.../save)
                                     ▼
                         AI raporu (mevcut akış, "olabilir; hekim değerlendirmesi gerekir")
                                     ▼
Medicore /hbys/encounters/{id}/report ──FHIR DiagnosticReport (preliminary)──▶ HBYS
```

## Gizlilik

- Medicore'a yalnızca **protokol numarası, yaş, cinsiyet, şikâyet, özgeçmiş, ilaçlar,
  vital bulgular, ICD-10 ön tanı, laboratuvar ve radyoloji** gelir.
- Ad, T.C. kimlik no, telefon, adres ve tam doğum tarihi HBYS'de kalır.
- HBYS kullanıcısı serbest metne kimlik yazmışsa, ziyaretin kendi kimlik bilgileriyle
  yerel gizlilik katmanı (`privacy_gateway`) metni temizler (`[HASTA_ADI]` vb.).
- HBYS'nin H/L bayrakları yalnızca bilgi amaçlı saklanır; Medicore durumu değer ve
  kaynak referansından kendisi hesaplar.
- Geri gönderilen rapor, istemciden gelen metin değil, hastanın kayıtlı AI raporudur ve
  `status: preliminary` + `physician-review-required: true` taşır.
- HBYS uçları admin, doktor ve laboratuvar personeli rolleri içindir. Bireysel hesaplar
  yalnızca `HBYS_INDIVIDUAL_ACCESS=true` iken ve yalnızca Sanal HBYS'ye karşı kullanabilir.

## Sanal HBYS'yi çalıştırma

```bash
cd app
pip install -r hbys_sim/requirements.txt   # backend kuruluysa gerekmez
HBYS_SIM_API_KEY=guclu-bir-anahtar uvicorn hbys_sim.main:app --port 8100
```

- Ekran: <http://localhost:8100/> (muayene listesi, hasta/poliklinik/lab/radyoloji detayı,
  Medicore'dan gelen raporlar)
- FHIR: `GET /fhir/metadata`, `GET /fhir/Encounter?status=in-progress|finished`,
  `GET /fhir/Encounter/{id}/$everything`, `POST /fhir/DiagnosticReport`
- HL7 v2.5: `GET /hl7/oru/{id}` (ORU^R01)
- Ekran HTTP Basic giriş ister: kullanıcı adı herhangi bir şey, şifre `HBYS_SIM_UI_PASSWORD`
  (tanımlı değilse `HBYS_SIM_API_KEY`). Ekrandan **yeni hasta + muayene** eklenebilir
  (şikâyet, vital, ICD-10 ön tanı, `Tetkik | Sonuç | Birim | Referans` satırlarıyla lab,
  isteğe bağlı radyoloji) ve muayene **tamamlandı / devam ediyor** olarak değiştirilebilir.
  T.C. numarası sistem tarafından geçersiz (sentetik) üretilir; gerçek hasta bilgisi girilmez.
- Durum: **Devam ediyor** (FHIR `in-progress`) = hasta hastanede, muayene/tetkik sürüyor;
  **Tamamlandı** (`finished`) = muayene kapandı / taburcu.
- Eklenen hastalar, durum değişiklikleri ve gelen raporlar `HBYS_SIM_DATABASE_URL`
  tanımlıysa PostgreSQL'de (`hbys_sim_records` tablosu) saklanır ve servis uyuyup uyansa da
  kaybolmaz. Tanımlı değilse yalnızca bellekte tutulur.
- API uçları `Authorization: Bearer <HBYS_SIM_API_KEY>` ister. Anahtar tanımlı değilse
  yalnızca `HBYS_SIM_ENV=development` iken `dev-hbys-key` kabul edilir.

Tüm kayıtlar sentetiktir: T.C. numaraları kasıtlı olarak checksum'dan geçmez, telefonlar
`0555 000 xx xx`, adresler hayalidir.

## Medicore ayarları

Backend ortam değişkenleri:

| Değişken | Örnek | Açıklama |
|---|---|---|
| `HBYS_BASE_URL` | `http://localhost:8100` | Boşsa entegrasyon kapalıdır (503) |
| `HBYS_API_KEY` | `guclu-bir-anahtar` | HBYS'ye Bearer olarak gönderilir |
| `HBYS_TIMEOUT_SECONDS` | `10` | İstek zaman aşımı |
| `HBYS_INDIVIDUAL_ACCESS` | `true` | Bireysel hesapların HBYS sayfasını kullanmasına izin verir. **Yalnızca** bağlanılan sistem kendini simülasyon olarak tanıtıyorsa geçerlidir; gerçek bir HBYS'de bireysel hesaplar her zaman reddedilir. Bireysel kullanıcılar yalnızca kendi aktardıkları vakaları görür. |

Arayüzde sol menüde **HBYS** sayfası: muayeneleri listeler, **Aktar** ile vakayı açar.
HBYS'den aktarılan bir vakada AI raporu oluşturulunca rapor **otomatik olarak** (arka planda)
ilgili HBYS muayenesine gönderilir; sonuç (gönderildi / atlandı / hata ve nedeni) HBYS
sayfasındaki **AI raporu** sütununda görünür. **Raporu tekrar gönder** ile elle de gönderilebilir.
Rapor, vaka rapordan sonra değiştiyse gönderilmez (eski rapor HBYS'ye yazılmaz).

## Gerçek bir HBYS'ye bağlanmak

Eşleme standart FHIR R4 kaynaklarını kullanır (Patient, Encounter, Condition,
MedicationStatement, Observation `vital-signs`/`laboratory`, DiagnosticReport). Gerçek
bir HBYS'de farklı olabilecek noktalar `app/backend/app/domain/hbys_integration.py`
içinde toplanmıştır: protokol numarası identifier sistemi, birim ve radyoloji bulgu
uzantıları (`urn:hbys-sim:*`). Canlı hasta verisiyle çalışmadan önce hastanenin bilgi
güvenliği/KVKK onayı ve HBYS firmasının entegrasyon dokümanı gerekir.
