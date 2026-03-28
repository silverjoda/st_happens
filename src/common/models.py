"""Database models for Ship Happens."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.common.db import Base


class Card(Base):
    __tablename__ = "cards"
    __table_args__ = (
        CheckConstraint(
            "status IN ('extracted', 'reviewed', 'approved', 'needs_fix', 'rejected')",
            name="ck_cards_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_image_path: Mapped[str] = mapped_column(Text, nullable=False)
    description_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    official_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocr_confidence_desc: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocr_confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="extracted")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    left_comparisons: Mapped[list[Comparison]] = relationship(
        back_populates="left_card", foreign_keys="Comparison.left_card_id"
    )
    right_comparisons: Mapped[list[Comparison]] = relationship(
        back_populates="right_card", foreign_keys="Comparison.right_card_id"
    )
    chosen_comparisons: Mapped[list[Comparison]] = relationship(
        back_populates="chosen_card", foreign_keys="Comparison.chosen_card_id"
    )
    ranking_results: Mapped[list[RankingResult]] = relationship(back_populates="card")


class SessionRecord(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("actor_type IN ('human', 'ai')", name="ck_sessions_actor_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pair_target_count: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    comparisons: Mapped[list[Comparison]] = relationship(back_populates="session")


class Comparison(Base):
    __tablename__ = "comparisons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    left_card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), nullable=False)
    right_card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), nullable=False)
    chosen_card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), nullable=False)
    presented_order: Mapped[int] = mapped_column(Integer, nullable=False)
    response_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    session: Mapped[SessionRecord] = relationship(back_populates="comparisons")
    left_card: Mapped[Card] = relationship(
        back_populates="left_comparisons", foreign_keys=[left_card_id]
    )
    right_card: Mapped[Card] = relationship(
        back_populates="right_comparisons", foreign_keys=[right_card_id]
    )
    chosen_card: Mapped[Card] = relationship(
        back_populates="chosen_comparisons", foreign_keys=[chosen_card_id]
    )


class RankingRun(Base):
    __tablename__ = "ranking_runs"
    __table_args__ = (
        CheckConstraint(
            "population IN ('human', 'ai', 'combined')", name="ck_ranking_runs_population"
        ),
        CheckConstraint("algorithm IN ('bradley_terry', 'elo')", name="ck_ranking_runs_algorithm"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    population: Mapped[str] = mapped_column(String(16), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(32), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    results: Mapped[list[RankingResult]] = relationship(back_populates="ranking_run")


class RankingResult(Base):
    __tablename__ = "ranking_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ranking_run_id: Mapped[int] = mapped_column(ForeignKey("ranking_runs.id"), nullable=False)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), nullable=False)
    raw_score: Mapped[float] = mapped_column(Float, nullable=False)
    normalized_score_1_100: Mapped[float] = mapped_column(Float, nullable=False)
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)

    ranking_run: Mapped[RankingRun] = relationship(back_populates="results")
    card: Mapped[Card] = relationship(back_populates="ranking_results")
