# Spotty

AI music generation driven by your Spotify listening DNA.

Spotty connects to your Spotify account, builds a taste profile from your listening history (8 audio dimensions + genres), and uses that profile to generate original music via [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) running on a local GPU.

## Features

- **Taste-to-Track** — One-click: generate a song that matches your Spotify DNA
- **Mood Sliders** — Adjust 8 audio dimensions (energy, danceability, valence, etc.) and hear the result change
- **Lyric Mode** — Write lyrics, app generates music in your taste profile's style
- **Poster Scanner** — OCR a concert poster, find artists that match your taste
- **Library** — Browse, favorite, and replay all your generated tracks
- **Taste Radar** — Interactive SVG visualization of your 8-dimension audio profile

## Architecture

```
[React Frontend :5173]  ──HTTP──▶  [Flask Backend :8888]  ──HTTP──▶  [ACE-Step API :8001]
                                        │                                    │
                                   [PostgreSQL]                         [GPU (RTX 4070+)]
```

## Tech Stack

**Backend:** Flask, SQLAlchemy, PostgreSQL, Pillow + pytesseract (OCR), rapidfuzz

**Frontend:** React 18, TypeScript, Vite, React Router

**AI:** ACE-Step 1.5 (self-hosted, turbo mode, 0.6B LM planner)

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL
- NVIDIA GPU with 8GB+ VRAM (for ACE-Step)
- [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) installed

### Backend

```bash
cd backend
cp ../.env.example .env  # edit with your credentials
pip install -r requirements.txt
python app.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### ACE-Step

```bash
# In the ACE-Step directory
uv run acestep-api  # starts on port 8001
```

### Environment Variables

See `.env.example` for all configuration options.

## License

MIT
