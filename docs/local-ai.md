# Yerel AI: veriyi dışarı göndermeden klinik yorum

Medicore'un klinik raporu, kendi bilgisayarınızda veya kendi sunucunuzda çalışan bir
dil modeliyle yazılır. **Varsayılan olarak `AI_LOCAL_ONLY=true`'dur**: dış AI servisleri
yalnızca bir operatör açıkça `AI_LOCAL_ONLY=false` verirse kullanılabilir. Bu modda **hiçbir istek dış AI servislerine
(Claude, OpenAI, Gemini) gidemez**: tüm AI çağrılarının geçmek zorunda olduğu tek kapı
(`privacy_call`) yerel model dışındaki her sağlayıcıyı reddeder ve bunu denetim loguna yazar.

## Nasıl çalışır

```
Vaka (kimliksizleştirilmiş) ──▶ privacy_call ──▶ yerel model (LM Studio / Ollama / vLLM)
                                   │
                                   └─ Claude/OpenAI/Gemini istekleri: ENGELLENİR (AI_LOCAL_ONLY)
```

- Yerel modele giden veri de gizlilik katmanından geçer (çift güvenlik).
- Lab sınıflandırması (yüksek/düşük/normal) zaten deterministik ve yereldir; model yalnızca
  metni yazar. Rapor bölümleri, "olabilir / hekim değerlendirmesi gerekir" kuralı ve yarım
  raporun kaydedilmemesi aynen geçerlidir.
- `LOCAL_LLM_BASE_URL` yalnızca yerel/özel bir adres olabilir: `localhost`, `127.0.0.1`,
  iç ağ IP'leri (10.x, 172.16–31.x, 192.168.x), tek kelimelik iç servis adları (`ollama`),
  `.internal` / `.local` adları. Dış bir adres yanlışlıkla yazılırsa reddedilir. Kendi GPU
  sunucunuz genel bir alan adındaysa `LOCAL_LLM_TRUSTED_HOSTS` ile açıkça belirtin.

## Ayarlar (backend)

| Değişken | Örnek | Açıklama |
|---|---|---|
| `AI_LOCAL_ONLY` | `true` | Dış AI servislerini tamamen kapatır |
| `LOCAL_LLM_BASE_URL` | `http://127.0.0.1:1234/v1` | LM Studio (Ollama: `http://127.0.0.1:11434/v1`) |
| `LOCAL_LLM_MODEL` | `qwen2.5-14b-instruct` | Sunucuda yüklü modelin adı |
| `LOCAL_LLM_MAX_TOKENS` | `6000` | Rapor için en fazla çıktı |
| `LOCAL_LLM_TIMEOUT_SECONDS` | `300` | Yavaş donanımda artırın |
| `LOCAL_LLM_TRUSTED_HOSTS` | `gpu.hastanem.com` | Yalnızca kendi sunucunuz genel adlıysa |

`AI_LOCAL_ONLY` kapalı ama `LOCAL_LLM_BASE_URL` + `LOCAL_LLM_MODEL` tanımlıysa klinik rapor
yine yerel modelle yazılır; diğer AI özellikleri (taranmış belge okuma vb.) bulutta çalışır.

## LM Studio ile (Windows/Mac)

1. LM Studio'da bir model indirin (öneri aşağıda) ve **Developer → Start Server** ile sunucuyu açın
   (varsayılan `http://127.0.0.1:1234/v1`).
2. Medicore backend'i aynı bilgisayarda çalıştırın ve ayarları girin.
3. Modelin adını LM Studio'daki "API identifier" ile birebir aynı yazın.

## Ollama ile (Linux sunucu)

```bash
ollama pull qwen2.5:14b
# backend: LOCAL_LLM_BASE_URL=http://127.0.0.1:11434/v1  LOCAL_LLM_MODEL=qwen2.5:14b
```

## Donanım ve model önerisi

| Bellek (GPU VRAM / Mac birleşik bellek) | Model boyutu | Not |
|---|---|---|
| 8–12 GB | 7–8B | Türkçe klinik yorum için genellikle yetersiz |
| 16–24 GB | 14B (4-bit) | **Asgari önerilen** |
| 32–48 GB | 27–32B (4-bit) | Belirgin daha iyi |
| 64 GB+ | 70B (4-bit) | En iyi yerel kalite |

Yerel modeller büyük bulut modellerinden daha zayıftır ve daha sık uydurabilir; rapor
her zaman hekim onayı bekleyen ön değerlendirmedir.

## Render notu

Render'ın ücretsiz/standart servislerinde GPU yoktur; büyük bir modeli orada çalıştırmak
pratik değildir. Seçenekler: backend'i modelin çalıştığı makinede (hastane sunucusu, GPU'lu
bulut sunucusu) çalıştırmak veya modeli aynı özel ağdaki bir sunucuda barındırıp
`LOCAL_LLM_BASE_URL`'yi o iç adrese vermek.

## Yalnızca yerel modda sınırlar

Bugün yalnızca **klinik rapor** yerel modelle yazılır. `AI_LOCAL_ONLY=true` iken şu bulut
özellikleri bilinçli olarak kapanır ve açık bir hata mesajı verir (veri dışarı gitmez):
taranmış/fotoğraf lab belgelerinin AI ile okunması (metin tabanlı PDF'ler ve e-Nabız yerel
okunur), radyoloji görüntüsü/raporu AI özeti, ikinci/üçüncü okuyucu.

## Kendi ince ayarlı (fine-tune) modelinizi kullanmak

Medicore modelden yalnızca OpenAI uyumlu bir sohbet API'si bekler; ince ayar yaptığınız
model LM Studio, Ollama, vLLM veya llama.cpp ile sunulduğu anda `LOCAL_LLM_MODEL` ile
kullanılabilir.

**Modelin öğrenmesi gerekenler** (sistem istemi zaten bunları ister, ince ayar pekiştirir):
- Türkçe ve şu 8 başlık, bu sırayla: KLİNİK ÖZET · ÖNE ÇIKAN LABORATUVAR BULGULARI ·
  TETKİK / RAPOR BULGULARI · ENTEGRE KLİNİK DEĞERLENDİRME · OLASI KLİNİK DURUMLAR / AYIRICI TANI ·
  ÖNERİLEN İLERİ TETKİK / İZLEM · SONUÇ / KANAAT · HEKİM NOTU
- Kesin tanı yerine olasılık dili ("… ile uyumlu olabilir"), her zaman hekim değerlendirmesi.
- Tedavi/ilaç talimatı vermemek; raporda olmayan referans aralığı veya değer uydurmamak.
- Girdideki yüksek/düşük laboratuvar sonuçlarının hepsini anmak (durum Medicore tarafından
  deterministik hesaplanır; model yalnızca yorumlar).

**Veri:** Gerçek hasta verisiyle eğitim KVKK açısından açık rıza/anonimleştirme ve etik kurul
onayı gerektirir. Öneri: sentetik vakalar, kamuya açık ve anonim Türkçe tıbbi metinler ve
hekimlerin düzelttiği örnek raporlar. Eğitim verisine kimlik bilgisi girmemeli.

**Yöntem (tek GPU):** Türkçe'yi iyi bilen bir instruct taban modeli (lisansının tıbbi kullanıma
izin verdiğini kontrol edin) üzerinde QLoRA/LoRA (ör. Unsloth, LLaMA-Factory, Axolotl).
Sonrasında: birleştir → GGUF'a dönüştür (llama.cpp) → LM Studio/Ollama'ya yükle; veya vLLM ile
LoRA adaptörünü doğrudan sunun.

**Ölçmeden geçmeyin:** Her yeni modeli taban modelle karşılaştırın:

```bash
LOCAL_LLM_BASE_URL=http://127.0.0.1:1234/v1 LOCAL_LLM_MODEL=benim-tip-modelim \
  python scripts/evaluate_local_model.py --out degerlendirme.md
```

Betik Sanal HBYS'deki sentetik vakaları gerçek rapor hattından (gizlilik katmanı + yerel model)
geçirir ve her vakayı puanlar: zorunlu bölümler (30), anormal lab kapsamı (30), olasılık dili ve
hekim notu (20), yasaklı ifade yokluğu (20), ayrıca süre. Ortalama puanı ve tablo halinde rapor
üretir. Gerçek hasta verisi kullanılmaz.
