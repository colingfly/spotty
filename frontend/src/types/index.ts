// src/types/index.ts

export const AUDIO_FEATURES = [
  "danceability",
  "energy",
  "valence",
  "acousticness",
  "instrumentalness",
  "liveness",
  "speechiness",
  "tempo",
] as const;

export type AudioFeatureKey = (typeof AUDIO_FEATURES)[number];
export type Features = Record<AudioFeatureKey, number>;

export const FEATURE_LABELS: Record<AudioFeatureKey, string> = {
  danceability: "Dance",
  energy: "Energy",
  valence: "Mood",
  acousticness: "Acoustic",
  instrumentalness: "Instrumental",
  liveness: "Live",
  speechiness: "Speech",
  tempo: "Tempo",
};

export const FEATURE_HINTS: Record<AudioFeatureKey, [string, string]> = {
  danceability: ["loose", "groovy"],
  energy: ["calm", "intense"],
  valence: ["dark", "bright"],
  acousticness: ["electronic", "organic"],
  instrumentalness: ["vocal", "instrumental"],
  liveness: ["studio", "live room"],
  speechiness: ["sung", "spoken"],
  tempo: ["slow", "fast"],
};

export type Mode = "taste" | "mood" | "lyrics" | "fusion" | "brief" | "festival";
export const MODES: Mode[] = ["taste", "mood", "lyrics", "fusion", "brief", "festival"];

export const FEATURE_TYPE_TO_MODE: Record<string, Mode> = {
  taste_to_track: "taste",
  mood_slider: "mood",
  lyric_mode: "lyrics",
  artist_fusion: "fusion",
  brief: "brief",
  festival: "festival",
};

export const MODE_META: Record<Mode, { label: string; short: string; blurb: string }> = {
  taste: { label: "Taste to Track", short: "Taste", blurb: "One click. A track that sits in the middle of your library." },
  mood: { label: "Mood Sliders", short: "Mood", blurb: "Bend your profile: more energy, darker, slower, whatever tonight needs." },
  lyrics: { label: "Lyric Mode", short: "Lyrics", blurb: "Bring words, or a theme, and get them sung in your sound." },
  fusion: { label: "Artist Fusion", short: "Fusion", blurb: "Pick two or three of your top artists and blend their worlds." },
  brief: { label: "Creative Brief", short: "Brief", blurb: "Describe a scene or a feeling. Your profile adds the flavor." },
  festival: { label: "Festival Lineup", short: "Festival", blurb: "Feed in a lineup from a poster and capture the night." },
};

export type Artist = {
  id: string;
  name: string;
  genres: string[];
  external_url?: string | null;
  image?: string | null;
  popularity?: number | null;
  followers?: number | null;
};

export type Track = {
  id: string;
  name: string;
  artists: string[];
  album?: string | null;
  image?: string | null;
  external_url?: string | null;
  popularity?: number | null;
  duration_ms?: number | null;
};

export type ScanArtist = Artist & {
  candidate?: string;
  in_library?: boolean;
  matchTotal?: number;
  nameSim?: number;
  genreSim?: number;
};

export type GenreWeight = { genre: string; weight: number };

export type Narrative = {
  headline: string;
  summary: string;
  signature_sounds: string[];
  eras: string[];
  persona: string;
  suggested_modes: string[];
};

export type TasteProfile = Features & {
  spotify_user_id: string;
  genres: string[];
  genre_weights: GenreWeight[];
  top_artists: string[];
  updated_at: string | null;
  narrative: Narrative | null;
};

export type Me = {
  spotify_user_id: string;
  display_name: string;
  avatar_url: string | null;
  country: string | null;
  product: string | null;
  needs_reauth: boolean;
  capabilities: {
    acestep: boolean;
    llm: { enabled: boolean; configured: boolean; model: string | null };
    max_variations: number;
    max_duration_seconds: number;
    default_duration_seconds: number;
  };
};

export type Stats = {
  total: number;
  completed: number;
  favorites: number;
  minutes_generated: number;
  plays: number;
  by_mode: Record<string, number>;
  by_engine: Record<string, number>;
};

export type Preset = { id: string; label: string; emoji: string; tags: string[]; tempo: number };

export type GenerationStatus = "pending" | "processing" | "completed" | "failed";

export type Generation = {
  generation_id: number;
  task_id: string;
  status: GenerationStatus;
  error: string | null;
  feature_type: string;
  mode: Mode | null;
  engine: "llm" | "template" | null;
  batch_id: string | null;
  variation_index: number | null;
  caption: string | null;
  lyrics: string | null;
  params: Record<string, unknown> | null;
  meta: {
    tags?: string[];
    rationale?: string;
    key_scale?: string | null;
    preset?: string | null;
    features?: Partial<Features>;
    fusion_artists?: { name: string; genres: string[]; image?: string | null }[];
    brief?: string | null;
    [k: string]: unknown;
  } | null;
  audio_url: string | null;
  download_url: string | null;
  duration_seconds: number | null;
  waveform: number[] | null;
  title: string | null;
  is_favorite: boolean;
  play_count: number;
  created_at: string | null;
  completed_at: string | null;
};

export type Composed = {
  title: string;
  prompt: string;
  lyrics: string;
  bpm: number;
  duration: number;
  key_scale: string | null;
  tags: string[];
  rationale: string;
  engine: "llm" | "template";
  features: Features;
  mode: Mode;
  preset: string | null;
  acestep_params: Record<string, unknown>;
};

export type GenerateRequest = {
  mode: Mode;
  overrides?: Partial<Features>;
  preset?: string | null;
  brief?: string;
  lyrics?: string;
  lyrics_theme?: string;
  vocals?: boolean;
  duration?: number;
  variations?: number;
  artist_ids?: string[];
  artist_names?: string[];
  use_llm?: boolean;
  edits?: Partial<Pick<Composed, "title" | "prompt" | "lyrics" | "bpm" | "key_scale" | "duration">>;
};

export type Paged<T> = { items: T[]; count: number; total?: number; limit?: number; offset?: number };
