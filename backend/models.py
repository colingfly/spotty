# backend/models.py
from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class SpotifyAccount(Base):
    __tablename__ = "spotify_accounts"

    id = Column(Integer, primary_key=True)
    spotify_user_id = Column(String, index=True, nullable=False)
    app_user_id = Column(String, nullable=True)

    display_name = Column(String, nullable=True)
    avatar_url = Column(Text, nullable=True)
    country = Column(String, nullable=True)
    product = Column(String, nullable=True)  # free / premium

    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    expires_at = Column(BigInteger, nullable=False)

    scope = Column(Text, nullable=True)
    token_type = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<SpotifyAccount user={self.spotify_user_id}>"


class UserTaste(Base):
    __tablename__ = "user_taste"

    id = Column(Integer, primary_key=True)
    spotify_user_id = Column(String, index=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    danceability = Column(Float, nullable=False, default=0.0)
    energy = Column(Float, nullable=False, default=0.0)
    valence = Column(Float, nullable=False, default=0.0)
    acousticness = Column(Float, nullable=False, default=0.0)
    instrumentalness = Column(Float, nullable=False, default=0.0)
    liveness = Column(Float, nullable=False, default=0.0)
    speechiness = Column(Float, nullable=False, default=0.0)
    tempo = Column(Float, nullable=False, default=0.0)

    genres = Column(JSON, nullable=False, default=list)
    # Weighted genre list [{"genre": str, "weight": float}] for richer prompts
    genre_weights = Column(JSON, nullable=True)
    # Top artist names captured at profile time (so the composer can reference them)
    top_artists = Column(JSON, nullable=True)

    # Claude-written "Sound DNA" narrative, cached
    narrative_json = Column(JSON, nullable=True)
    narrative_updated_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<UserTaste user={self.spotify_user_id}>"

    def as_features(self) -> dict:
        return {
            "danceability": self.danceability,
            "energy": self.energy,
            "valence": self.valence,
            "acousticness": self.acousticness,
            "instrumentalness": self.instrumentalness,
            "liveness": self.liveness,
            "speechiness": self.speechiness,
            "tempo": self.tempo,
        }


class PosterScan(Base):
    __tablename__ = "poster_scan"

    id = Column(Integer, primary_key=True)
    spotify_user_id = Column(String, index=True, nullable=False)
    scan_ts = Column(BigInteger, nullable=False)
    artists_csv = Column(Text, nullable=True)


class ArtistEdge(Base):
    __tablename__ = "artist_edge"

    id = Column(Integer, primary_key=True)
    a = Column(String, nullable=False)
    b = Column(String, nullable=False)
    weight = Column(Float, nullable=False, default=0.0)
    last_seen = Column(BigInteger, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("a", "b", name="uq_artist_edge_pair"),
        Index("ix_artist_edge_a", "a"),
        Index("ix_artist_edge_b", "b"),
    )


class Generation(Base):
    __tablename__ = "generations"

    id = Column(Integer, primary_key=True)
    spotify_user_id = Column(String, index=True, nullable=False)

    task_id = Column(String, unique=True, nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending|processing|completed|failed
    error_message = Column(Text, nullable=True)

    # taste_to_track | mood_slider | lyric_mode | artist_fusion | brief | festival
    feature_type = Column(String, nullable=False)
    # llm | template
    engine = Column(String, nullable=True)
    # groups N variations submitted together
    batch_id = Column(String, nullable=True, index=True)
    variation_index = Column(Integer, nullable=True)

    caption_used = Column(Text, nullable=True)
    lyrics_used = Column(Text, nullable=True)
    params_json = Column(JSON, nullable=True)
    # Mode-specific inputs: overrides, preset, brief text, fused artists, rationale
    meta_json = Column(JSON, nullable=True)

    audio_path = Column(Text, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    waveform_json = Column(JSON, nullable=True)  # ~96 normalized peaks for the player

    title = Column(String, nullable=True)
    is_favorite = Column(Integer, nullable=False, default=0)
    play_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Generation id={self.id} type={self.feature_type} status={self.status}>"
