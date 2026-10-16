# Türkçe Fitness Shorts Botu

Bu klasör, aynı Gmail hesabındaki ayrı fitness YouTube kanalı için 30–60 saniyelik **Türkçe** dikey videolar hazırlar. Varsayılan ses Türkiye Türkçesi kadın sesi **tr-TR-EmelNeural**; iş akışından kadın veya erkek sesi seçilebilir.

## Özellikler
- 1080×1920 dikey MP4, varsayılan 45 saniye (30/45/60 seçilebilir)
- Türkçe anlatım metni, Gemini kullanılamadığında güvenli yedek metin
- Edge TTS Türkçe sinirsel ses: kadın `tr-TR-EmelNeural`, erkek `tr-TR-AhmetNeural`
- Pexels ve Pixabay'den konuya özel stok görüntüler; yinelenen klipleri ayıklama ve alakasız etiketleri filtreleme
- FFmpeg ile montaj, videoya gömülü Türkçe karaoke altyazı ve ayrıca `output/subtitles.ass`
- İsteğe bağlı Whisper kelime zamanlaması; çalışmazsa tahmini zamanlama yedeği
- Son videoda çözünürlük, ses akışı, dosya boyutu ve süre kontrolü
- Otomatik 1280×720 küçük resim, SEO başlık/açıklama/etiketler, stok görüntü kaynakları ve `output/review_manifest.json`
- Varsayılan güvenli mod: video hazırlanır ama yüklenmez; yayınlama için insan onayı gerekir
- YouTube OAuth hesabının hedef kanal erişimini doğrular; yanlış kanal görünürse yüklemeyi engeller

## GitHub Actions Secrets
**Settings → Secrets and variables → Actions → Secrets** bölümüne ekle:
- `PEXELS_API_KEY` — Pexels API anahtarı
- `PIXABAY_API_KEY` — Pixabay API anahtarı
- `GEMINI_API_KEY` — Gemini API anahtarı
- `FITNESS_TOKEN_JSON` — yalnızca fitness kanalı için OAuth token JSON içeriği

API anahtarlarını veya OAuth token'ını kaynak koda yazma.

## GitHub Actions Variables
**Settings → Secrets and variables → Actions → Variables** bölümünde:
- `FITNESS_YOUTUBE_CHANNEL_ID` = `UC7_pFbnnuMWT_US47_FD6MDA`
- `FITNESS_ALLOW_PUBLIC_UPLOAD` = `NO` (test tamamlanana kadar böyle bırak)
- `EDGE_TTS_VOICE` = `tr-TR-EmelNeural` (isteğe bağlı varsayılan ses)
- `GEMINI_MODEL` = `gemini-2.5-flash` (hesabında kullanılabilen bir model seç)

## İlk test — yayınlama yapmadan
1. Yukarıdaki Secrets ve Variables değerlerini GitHub'da ayarla.
2. **Actions → Turkish Fitness Shorts Bot → Run workflow** sayfasını aç.
3. `mode=prepare`, `duration=45`, `voice=female` seç. Konu alanına örneğin `Şınavda yapılan 3 hata` yaz.
4. **Run workflow** düğmesine bas ve tamamlanmasını bekle.
5. Çalışma sonuçlarındaki **Artifacts → youtube-fitness-shorts** arşivini indir.
6. `fitness_shorts.mp4` dosyasını baştan sona izle/dinle; görüntülerin konuya uyduğunu, Türkçe sesi ve altyazıları, küçük resmi ve kaynakları kontrol et.
7. `output/review_manifest.json` içinde `publish_authorized: false` olduğunu göreceksin. Bu normaldir; dosya inceleme için hazırdır, otomatik onaylanmaz.

## Yayınlama güvenliği
Yalnızca videoyu kendin izleyip onayladıktan sonra:
- `FITNESS_ALLOW_PUBLIC_UPLOAD=YES` ayarla.
- Actions çalıştırırken `mode=upload` seç.
- `confirm_upload` kutusunu özellikle işaretle.
- OAuth token'ın `UC7_pFbnnuMWT_US47_FD6MDA` kanalına ait olduğunu kontrol et.

Zamanlanmış çalıştırmalar yalnızca video hazırlar; otomatik olarak herkese açık yayın yapmaz. İlk gerçek render, stok API anahtarları ve OAuth token'ın bu ortamda doğrulanmış değildir; önce manuel `prepare` çalıştırmasıyla test edilmelidir.

## Yerel Windows kurulumu
Python 3.11+ ve FFmpeg kur. PowerShell'de depo kök klasöründen:
```powershell
python -m pip install -r youtube_fitnes_talyhs/requirements.txt
python youtube_fitnes_talyhs/youtube.py
```
Varsayılan mod `prepare` olduğundan video hazırlanır ama YouTube'a yüklenmez.
