# Medicore'u internetsiz çalıştırma (bilgisayarınızda)

Kurulum **bir kez internetle** yapılır. Ardından Medicore, veritabanı, Sanal HBYS ve AI
raporu dahil **tamamen internetsiz** çalışır; hiçbir veri bilgisayardan çıkmaz.

| Parça | Nerede çalışır |
|---|---|
| Medicore backend + frontend | Docker (bu bilgisayar) |
| PostgreSQL veritabanı | Docker (bu bilgisayar, kalıcı disk) |
| Sanal HBYS | Docker (bu bilgisayar) |
| AI klinik raporu | LM Studio veya Ollama (bu bilgisayar) |
| Türkçe ses tanıma, OCR | Backend içinde, kurulumda pakete gömülür |

## 1. Bir kez, internet varken

1. **Docker Desktop** kurun (Windows: WSL 2 seçeneğiyle) ve açın.
2. **LM Studio**'yu kurun, bir model indirin (16–24 GB ekran kartı belleği için
   *Qwen2.5 14B Instruct* önerilir; bkz. `docs/local-ai.md`), **Developer → Start Server**
   ile sunucuyu açın. Model adını ("API identifier") not edin.
3. Repoyu indirin, kök klasörde `offline.env.example` dosyasını `offline.env` olarak
   kopyalayın ve değerleri doldurun (uzun, rastgele şifreler; `LOCAL_LLM_MODEL` = LM Studio'daki ad).
4. Kök klasörde:

   ```powershell
   docker compose -f docker-compose.offline.yml --env-file offline.env up -d --build
   ```

   Bu adım paketleri, veritabanı imajını ve Türkçe ses modelini indirip doğrular
   (birkaç dakika sürer).

5. Hazır mı kontrol edin:

   ```powershell
   docker compose -f docker-compose.offline.yml --env-file offline.env exec backend python scripts/offline_check.py
   ```

   Sonuç **"HAZIR: internet olmadan çalışabilir."** olmalı.

## 2. Her gün (internet gerekmez)

1. Docker Desktop'ı ve LM Studio sunucusunu açın.
2. `docker compose -f docker-compose.offline.yml --env-file offline.env up -d`
3. Tarayıcı: **http://localhost:8080** (Medicore), **http://localhost:8100** (Sanal HBYS)

Kapatmak için: `docker compose -f docker-compose.offline.yml --env-file offline.env down`
(veriler `medicore_db` diskinde kalır; `down -v` veriyi siler).

## Güvenlik notları

- `AI_LOCAL_ONLY=true` sabittir: Claude/OpenAI/Gemini'ye istek gönderilemez.
- Portlar yalnızca `127.0.0.1`'e açılır; aynı ağdaki başka bir bilgisayar erişemez.
- `offline.env` git'e eklenmez (`.gitignore`). Bu dosyayı paylaşmayın.
- Yerel model adresi yalnızca bu bilgisayar / iç ağ olabilir; dış bir adres reddedilir.

## Sorun giderme

| Belirti | Çözüm |
|---|---|
| "Yerel AI sunucusuna ulaşılamadı" | LM Studio'da sunucu açık mı? Model yüklü mü? |
| "Model bulunamadı" | `LOCAL_LLM_MODEL` LM Studio'daki adla birebir aynı olmalı |
| AI raporu çok yavaş | `LOCAL_LLM_TIMEOUT_SECONDS`'i artırın veya daha küçük/nicemlenmiş model seçin |
| Ses tanıma kapalı | Kurulumu internet varken `--build` ile yeniden yapın |

## Sınırlar

İnternetsiz modda klinik rapor yerel modelle yazılır. Bulut AI gerektiren özellikler
(taranmış belgelerin AI ile okunması, radyoloji AI özeti) kapalıdır ve açık bir mesaj
verir; metin tabanlı PDF'ler, e-Nabız ve yerel OCR çalışır.
