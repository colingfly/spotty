export type Artist = {
  id: string;
  name: string;
  genres: string[];
  url?: string;
  external_url?: string;
  image?: string | null;
  popularity?: number;
  matchTotal?: number;
  nameSim?: number;
  genreSim?: number;
  fromScan?: boolean;
};

export type TasteProfile = {
  spotify_user_id: string;
  danceability: number;
  energy: number;
  valence: number;
  acousticness: number;
  instrumentalness: number;
  liveness: number;
  speechiness: number;
  tempo: number;
  genres: string[];
  updated_at: string | null;
};

export type Generation = {
  generation_id: number;
  task_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  feature_type: string;
  caption: string | null;
  lyrics: string | null;
  params: Record<string, any> | null;
  audio_url: string | null;
  duration_seconds: number | null;
  title: string | null;
  is_favorite: number;
  created_at: string | null;
  completed_at: string | null;
};

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
