# Kaynak referans tabloları regresyonu

VAKA01 ZIP incelemesinde hemogram (02) ve biyokimya (03) belgelerindeki
`Test | Sonuç | Referans` tablolarında toplam 12 basılı referans bulundu.
Mevcut yerel okuyucu yalnızca e-Nabız düzenini destekliyordu. Bu tablolar
model okuyucusuna düşüyor, referanslar kaybolabiliyordu. Ayrıca baştaki yüzde
işareti ve `x10^9/L` yazımı ortak sayısal ayrıştırıcıda tanınmıyordu.

Yeni yerel yol açık üç/dört sütunlu kaynak tablolarını geometriyle okur;
ham sonuç, birim ve basılı referansı korur. Desteklenmeyen tarih karşılaştırma
tabloları veya eksik hücreler mevcut okuyucuya bırakılır. Genel belge tarihi
numune/sonuç tarihi olarak kullanılmaz. Klinik metinden referans üretilmez.

| Belge | Doğrulanan sonuçlar |
|---|---|
| Hemogram | WBC HIGH, Nötrofil HIGH, Hb NORMAL, Hct NORMAL, PLT NORMAL |
| Biyokimya | Kreatinin NORMAL, Üre NORMAL, CRP HIGH, Prokalsitonin HIGH, ESR HIGH, AST NORMAL, ALT NORMAL |

Diğer takip/karşılaştırma belgelerinde basılı referans bulunmayan satırlara
önceki belgeden aralık taşınmaz. Kaynaktaki `mm/s`, `mm/h` olarak değiştirilmez.
Önceden referansı eksik kaydedilmiş sonuçlar otomatik değiştirilmez;
kaynak belgenin yeniden okunması gerekir.

Doğrulama: aktif backend CI kapsamı 600 test; yeni 11 regresyon örneği.
Gerçek iki PDF ayrıca dış ağ ve model çağrıları engellenmiş yükleme akışında
12 ham sonuç/referans/durum ve belge tarihi bakımından doğrulandı.
Repository yalnızca sentetik test PDF'leri içerir; yüklenen ZIP eklenmemiştir.
