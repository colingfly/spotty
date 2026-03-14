# backend/models.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    Float,
    DateTime,
    JSON,
    func,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# -------------------------
# spotify_accounts
# -------------------------
class SpotifyAccount(Base):
    __tablename__ = "spotify_accounts"

    id = Column(Integer, primary_key=True)
    spotify_user_id = Column(String, index=True, nullable=False)
    app_user_id = Column(String, nullable=True)

    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    expires_at = Column(BigInteger, nullable=False)

    scope = Column(Text, nullable=True)
    token_type = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<SpotifyAccount user={self.spotify_user_id} expires_at={self.expires_at}>"


# -------------------------
# user_taste
# -------------------------
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

    def __repr__(self) -> str:
        return f"<UserTaste user={self.spotify_user_id} updated_at={self.updated_at}>"


# -------------------------
# poster_scan
# -------------------------
class PosterScan(Base):
    __tablename__ = "poster_scan"

    id = Column(Integer, primary_key=True)
    spotify_user_id = Column(String, index=True, nullable=False)
    scan_ts = Column(BigInteger, nullable=False)
    artists_csv = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<PosterScan user={self.spotify_user_id} ts={self.scan_ts}>"


# -------------------------
# artist_edge (co-occurrence graph)
# -------------------------
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

    def __repr__(self) -> str:
        return f"<ArtistEdge {self.a}—{self.b} w={self.weight}>"


# -------------------------
# generations (AI music)
# -------------------------
class Generation(Base):
    __tablename__ = "generations"

    id = Column(Integer, primary_key=True)
    spotify_user_id = Column(String, index=True, nullable=False)

    task_id = Column(String, unique=True, nullable=False)
    status = Column(String, nullable=False, default="pending")

    feature_type = Column(String, nullable=False)

    caption_used = Column(Text, nullable=True)
    lyrics_used = Column(Text, nullable=True)
    params_json = Column(JSON, nullable=True)

    audio_path = Column(Text, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    title = Column(String, nullable=True)
    is_favorite = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Generation id={self.id} type={self.feature_type} status={self.status}>"
