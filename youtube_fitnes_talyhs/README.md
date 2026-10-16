# youtube_fitnes_talyhs — Türkçe Fitness Shorts Otomasyonu

Bu klasör, ana YouTube otomasyonundan ayrı ayarlarla ikinci YouTube kanalına yönelik 30–60 saniyelik Türkçe fitness Shorts videoları üretir.

## Yapılandırılan özellikler
- 1080×1920 dikey MP4 video, varsayılan 45 saniye
- Türkçe fitness senaryosu (Gemini API yoksa yerleşik yedek metin)
- Pexels ve Pixabay stok video araması/indirmesi
- Edge TTS Türkçe kadın sesi: `tr-TR-EmelNeural` (değiştirilebilir)
- FFmpeg montajı ve videoya gömülü altyazılar
- Başlık, açıklama, hashtag ve stok kaynak kredileri
- Yüklemeden önce OAuth hesabında doğru kanal ID'sini doğrulama
- Zamanlanmış görevlerde yalnızca `prepare`; otomatik herkese açık yayın yok

## GitHub Actions
İş akışı: [Turkish Fitness Shorts Bot](../.github/workflows/fitness-shorts.yml)

Türkiye saatiyle (UTC+3) her gün üç video hazırlama denemesi: **07:30, 12:00 ve 18:30**. GitHub zamanlanmış görevleri gecikebilir. Videolar Actions run sayfasındaki `youtube-fitness-shorts` artifact ZIP dosyasında saxlanır.

## GitHub Secrets
Repo → **Settings → Secrets and variables → Actions → Secrets** bölümüne ekle:
- `PEXELS_API_KEY`
- `PIXABAY_API_KEY`
- `GEMINI_API_KEY` (isteğe bağlı)
- `FITNESS_TOKEN_JSON` (ikinci kanal OAuth token JSON-u; kod deposuna qoyma)

Token aşağıdakı OAuth scope-larını ehtiva etməlidir:
- `https://www.googleapis.com/auth/youtube.upload`
- `https://www.googleapis.com/auth/youtube.readonly`

## GitHub Variables
**Settings → Secrets and variables → Actions → Variables** bölməsinə əlavə et:
- `FITNESS_YOUTUBE_CHANNEL_ID` = `UC7_pFbnnuMWT_US47_FD6MDA`
- `FITNESS_ALLOW_PUBLIC_UPLOAD` = əvvəlcə `NO`; yalnız testdən sonra `YES`
- `EDGE_TTS_VOICE` = `tr-TR-EmelNeural` (qadın səsi; kişi üçün `tr-TR-AhmetNeural`)
- `GEMINI_MODEL` = `gemini-2.5-flash`

## İlk sınaq
1. API açarlarını və Variables dəyərlərini əlavə et.
2. GitHub → **Actions → Turkish Fitness Shorts Bot → Run workflow** aç.
3. İlk dəfə `prepare` seç və **Run workflow** bas.
4. Run bitəndə **Artifacts → youtube-fitness-shorts** ZIP faylını endir; videonu, səsi, altyazıları və kreditləri yoxla.
5. OAuth tokeninin ikinci kanala aid olduğunu təsdiqlə. Kod kanal ID-si uyğun gəlmirsə yükləməni bloklayır.
6. Yalnız bütün testlər keçəndən sonra `FITNESS_ALLOW_PUBLIC_UPLOAD=YES` et və əl ilə `upload` seç.

## Lokal Windows quraşdırılması
Python 3.11+ və FFmpeg quraşdırıldıqdan sonra PowerShell-də:
```powershell
cd youtube_fitnes_talyhs
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:PEXELS_API_KEY = "API_AÇARIN"
$env:PIXABAY_API_KEY = "API_AÇARIN"
$env:PUBLISH_MODE = "prepare"
python youtube.py
```

Heç bir real API açarını və ya OAuth tokenini kodda saxlama və GitHub-a yükləmə. Stok kliplərin lisenziyasını və fitness məlumatlarının düzgünlüyünü yayımdan əvvəl yoxla. Bu, ümumi maarifləndirici məzmundur, tibbi məsləhət deyil.
