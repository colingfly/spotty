# Spotty

AI music generation driven by your Spotify listening DNA.

Spotty analyzes your Spotify listening history to build a multi-dimensional taste profile, then uses that profile to generate original music via [ACE-Step 1.5](https://github.com/ace-step/ACE-Step) — a state-of-the-art AI music generation model running on your local GPU.

## How It Works

```
Spotify API ──▶ Top Artists ──▶ Last.fm Genre Tags ──▶ Genre-to-Audio Inference
                                                              │
                                                    ┌─────────▼──────────┐
                                                    │   Taste Profile    │
                                                    │  8 audio features  │
                                                    │  + genre weights   │
                                                    └─────────┬──────────┘
                                                              │
                                              Caption Engine (taste → prompt)
                                                              │
                                                    ┌─────────▼──────────┐
                                                    │   ACE-Step 1.5     │
                                                    │  Text-to-Music AI  │
                                                    │  (local GPU)       │
                                                    └─────────┬──────────┘
                                                              │
                                                         .mp3 output
```

1. **OAuth** — Connect your Spotify account
2. **Profile** — Spotty fetches your top 50 artists, resolves genres via Last.fm, and infers 8 audio dimensions using a curated genre-to-feature mapping
3. **Caption** — Your taste profile is converted into a natural language prompt (e.g., *"trap, rap, hip hop, rage, plugg track. high-energy, powerful, driving, uplifting..."*)
4. **Generate** — The prompt is sent to ACE-Step 1.5 running locally, which produces an original track in ~20 seconds

## Features

- **Taste-to-Track** — One click: generate a song that matches your Spotify DNA
- **Mood Sliders** — Adjust 8 audio dimensions (energy, danceability, valence, etc.) before generating
- **Lyric Mode** — Write lyrics with `[verse]`/`[chorus]` tags, generate music in your taste profile's style
- **Taste Radar** — Interactive SVG radar chart visualizing your 8-dimension audio profile
- **Library** — Browse, favorite, and replay all generated tracks
- **Poster Scanner** — OCR a concert poster image, find and identify artists

## Architecture

```
┌──────────────────┐     ┌──────────────────────┐     ┌──────────────────┐
│  React Frontend  │────▶│    Flask Backend      │────▶│  ACE-Step 1.5    │
│  Vite + TS       │     │    SQLite + ORM       │     │  Local GPU       │
│  :5180           │     │    :8888              │     │  :8001           │
└──────────────────┘     └──────────┬───────────┘     └──────────────────┘
                                   │
                          ┌────────▼────────┐
                          │  External APIs  │
                          │  Spotify OAuth  │
                          │  Last.fm Tags   │
                          └─────────────────┘
```

### Backend Services

| Service | File | Purpose |
|---------|------|---------|
| `spotify_client.py` | Spotify API wrapper | OAuth token refresh, top artists, search |
| `artist_genre_map.py` | Last.fm integration | Artist → genre tag resolution with in-memory cache |
| `genre_analyzer.py` | Genre inference engine | Maps 100+ genres to 8 audio feature dimensions |
| `taste.py` | Taste profiler | Builds/caches user taste profiles (24hr TTL) |
| `caption_engine.py` | Prompt builder | Converts taste profiles into ACE-Step generation prompts |
| `acestep_client.py` | ACE-Step API client | Task submission, polling, audio download |
| `audio_analyzer.py` | Librosa analysis | Audio feature extraction from preview clips (fallback) |
| `ocr.py` | Tesseract OCR | Concert poster text extraction |

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/login` | Initiate Spotify OAuth flow |
| `GET` | `/callback` | Handle OAuth callback, store tokens |
| `GET` | `/api/me/taste` | Fetch user taste profile |
| `GET` | `/api/me/top-artists` | Get user's top artists with genres |
| `POST` | `/api/generate/taste-to-track` | Generate from taste profile |
| `POST` | `/api/generate/custom` | Generate with mood slider overrides |
| `POST` | `/api/generate/lyric-mode` | Generate with custom lyrics |
| `GET` | `/api/generate/status/:id` | Poll generation status |
| `GET` | `/api/audio/:id` | Stream generated audio |
| `GET` | `/api/generate/history` | List past generations |
| `POST` | `/api/scan` | Upload image for OCR artist detection |
| `GET` | `/api/acestep/health` | Check ACE-Step availability |

## Genre Inference System

Since Spotify deprecated its audio-features API for new apps (Nov 2024), Spotty uses a custom inference pipeline:

1. **Last.fm API** — Fetches top genre tags for each artist (free, no auth restrictions, covers millions of artists)
2. **Genre Profiles** — A curated database of 100+ genre-to-audio-feature mappings based on musicological research
3. **Weighted Aggregation** — Position-based decay weighting across a user's top artists
4. **Keyword Modifiers** — Fuzzy matching for unknown genres (e.g., "dark trap" → trap baseline + dark modifier)

The system maps each genre to 8 dimensions:
- **Danceability** — Beat regularity and rhythmic drive
- **Energy** — Intensity and loudness
- **Valence** — Musical positivity/mood
- **Acousticness** — Acoustic vs. electronic production
- **Instrumentalness** — Vocal presence
- **Liveness** — Live performance qualities
- **Speechiness** — Spoken word / rap density
- **Tempo** — BPM

## Tech Stack

**Backend:** Python 3.11+, Flask, SQLAlchemy, SQLite, librosa, pytesseract, rapidfuzz

**Frontend:** React 18, TypeScript, Vite, React Router v7

**AI:** ACE-Step 1.5 (self-hosted, turbo mode w/ 8 inference steps, 0.6B LM planner)

**External APIs:** Spotify Web API (OAuth + user data), Last.fm API (artist genre tags)

**Deployment:** Docker, Render (backend), Vercel (frontend), Cloudflare Tunnel (GPU bridge)

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- NVIDIA GPU with 8GB+ VRAM
- [ACE-Step 1.5](https://github.com/ace-step/ACE-Step) installed locally
- Spotify Developer App ([create one here](https://developer.spotify.com/dashboard))

### 1. Clone

```bash
git clone https://github.com/colingfly/spotty.git
cd spotty
```

### 2. Backend

```bash
cd backend
cp ../.env.example .env
# Edit .env with your Spotify credentials
pip install -r requirements.txt
python app.py
# Runs on http://127.0.0.1:8888
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:5180
```

### 4. ACE-Step

```bash
# In your ACE-Step 1.5 directory
uv run acestep-api
# Runs on http://127.0.0.1:8001
```

### Environment Variables

```env
# Spotify OAuth (required)
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
SPOTIFY_SCOPE=user-top-read

# Database
DATABASE_URL=sqlite:///spotty.db

# Frontend URL (for CORS + OAuth redirect)
FRONTEND_URL=http://localhost:5180

# ACE-Step API
ACESTEP_API_URL=http://127.0.0.1:8001
```

### Spotify Developer Setup

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Add `http://127.0.0.1:8888/callback` as a Redirect URI
4. Copy Client ID and Client Secret to your `.env`
5. Under **User Management**, add your Spotify account email (required while in Development Mode)

## Deployment

The app can be deployed with the backend on Render and frontend on Vercel:

- **Render:** Docker-based deployment from the `Dockerfile`. Set env vars for Spotify credentials, database URL, and frontend URL.
- **Vercel:** Deploy the `frontend/` directory. Set `VITE_API_BASE` to your Render backend URL.
- **GPU Bridge:** Use [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/) to expose your local ACE-Step server to the deployed backend.

## Project Structure

```
spotty/
├── backend/
│   ├── app.py                  # Flask app factory
│   ├── config.py               # Settings from env vars
│   ├── db.py                   # SQLAlchemy setup
│   ├── models.py               # ORM models
│   ├── requirements.txt
│   ├── routes/
│   │   ├── auth.py             # Spotify OAuth
│   │   ├── spotify.py          # Spotify data endpoints
│   │   ├── generate.py         # Music generation endpoints
│   │   └── scan.py             # Poster OCR endpoints
│   └── services/
│       ├── spotify_client.py   # Spotify API client
│       ├── artist_genre_map.py # Last.fm genre lookup
│       ├── genre_analyzer.py   # Genre → audio features
│       ├── taste.py            # Taste profile builder
│       ├── caption_engine.py   # Taste → ACE-Step prompt
│       ├── acestep_client.py   # ACE-Step API client
│       ├── audio_analyzer.py   # Librosa audio analysis
│       └── ocr.py              # Tesseract OCR
├── frontend/
│   ├── src/
│   │   ├── App.tsx             # Router + layout
│   │   ├── pages/              # Dashboard, Generate, Library, Scan
│   │   ├── components/         # TasteRadar, AudioPlayer, GenerateButton
│   │   ├── hooks/              # useGeneration
│   │   └── config.ts           # API base URL
│   ├── package.json
│   └── vite.config.ts
├── Dockerfile
├── .env.example
└── README.md
```

## License

MIT
