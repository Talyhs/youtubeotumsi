# Talyhs YouTube Studio — quraşdırma və yoxlama

Bu təlimat veb paneli Render-də işə salmaq və GitHub Actions ilə əlaqələndirmək üçündür.

## 1. Render Web Service

Render-də `talyhs-youtube-studio` adlı Web Service yarat və repository kimi `Talyhs/youtubeotumsi` seç.

- Build Command: `pip install -r requirements.txt`
- Start Command: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
- Health Check Path: `/`

Repository-dəki `render.yaml` bu parametrləri təsvir edir. Deploy etdikdən sonra Render → Environment bölməsində aşağıdakı dəyişənləri əlavə et.

## 2. Məcburi Environment Variables

| Dəyişən | Dəyər |
|---|---|
| `DASHBOARD_PASSWORD` | Panelə giriş üçün özünün yaratdığı güclü şifrə |
| `GH_TOKEN` | GitHub Personal Access Token; heç kimlə paylaşma |
| `GITHUB_REPOSITORY` | `Talyhs/youtubeotumsi` |
| `GITHUB_WORKFLOW_FILE` | `main.yml` |
| `GITHUB_BRANCH` | `main` |

GitHub tokeninə yalnız bu repository üçün lazımi icazələri ver: Actions workflow dispatch üçün **Actions: write**, repository-ni oxumaq üçün **Contents: read**. Tokeni Python koduna, GitHub-a commit edilən fayla və ya ictimai mesaja yazma.

## 3. GitHub Secrets

GitHub repository → Settings → Secrets and variables → Actions bölməsində video istehsalı üçün lazım olan açarları yoxla:
- `GEMINI_API_KEY`
- `PEXELS_API_KEY` və/və ya `PIXABAY_API_KEY`
- `TOKEN_JSON` — yalnız YouTube-a yükləmə üçün; test zamanı `prepare` rejimi seç.

Fitness workflow üçün əlavə olaraq `FITNESS_TOKEN_JSON` və `FITNESS_YOUTUBE_CHANNEL_ID` konfiqurasiyası lazımdır. Token və kanal ID-si düzgün ikinci kanala aid olmalıdır.

## 4. İlk test — təhlükəsiz rejim

1. Render-də Environment dəyişənlərini saxla və servisi yenidən deploy et.
2. Panelə daxil ol.
3. Kanalı seç və **Yalnız hazırla / prepare** rejimini seç.
4. Mövzu, dil, müddət və səs mühərrikini seç.
5. GitHub → Actions bölməsində yeni run-ın başladığını yoxla.
6. Run bitdikdə `youtube-final-video` artifact-ini endir və videonu dinlə/görüntünü yoxla.
7. Yalnız test uğurlu olduqda YouTube upload-u ayrıca təsdiqlə.

**Vacib:** `prepare` rejimi video faylı hazırlayır, amma YouTube-a yayımlamır. Təqvim paneli planı yadda saxlayır və tapşırığı əl ilə başlada bilir; planlaşdırılan saatda avtomatik işləməsi ayrıca scheduler inteqrasiyası tələb edir.

## 5. Problem diaqnostikası

- “DASHBOARD_PASSWORD təyin edilməyib” — Render Environment-də dəyişən yoxdur.
- “GH_TOKEN təyin edilməyib” və ya GitHub API 401/403 — token yoxdur, vaxtı bitib və ya icazələri kifayət etmir.
- Run başlamır — GitHub tokeninin Actions write icazəsini və workflow faylının `main` branch-də mövcudluğunu yoxla.
- Run uğurludur, amma YouTube-a video getmir — bu, `prepare` rejimində gözlənilən davranışdır; artifact-i Actions run-dan götür.
- Render-də dəyişiklik görünmür — deploy logunda son commit-in istifadə edildiyini və servisin uğurla başladığını yoxla.