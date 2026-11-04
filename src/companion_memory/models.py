# Generated from Companion Core 30628cff61d6642d6ababf833d6432cd83695c0f; see provenance/upstream.json.
# SPDX-License-Identifier: MIT
# ruff: noqa: E501
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Candidate(StrictModel):
    subject: Literal['user', 'self', 'relationship', 'project']
    kind: Literal['fact', 'preference', 'boundary', 'episode', 'skill']
    fact_key: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=500)
    evidence_event_id: str
    evidence_quote: str = Field(min_length=2, max_length=500)
    evidence_reference_id: str | None = Field(default=None, min_length=1, max_length=128, exclude_if=lambda value: value is None)
    salience: int | None = Field(default=None, ge=1, le=10, strict=True)
    speaker: Literal['owner', 'third_party', 'assistant', 'document'] | None = Field(default=None, exclude_if=lambda value: value is None)
    relayed_by_owner: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    update: Literal['replaces_previous'] | None = Field(default=None, exclude_if=lambda value: value is None)

class EpisodeSummary(StrictModel):
    title: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=600)
    source_event_ids: list[str] = Field(min_length=1, max_length=20)

class InteractionSignal(StrictModel):
    """What the owner's words meant to her; code, not the model, sets the mood change."""
    event_id: str
    reason: Literal['OWNER_AFFECTION', 'OWNER_HURT_BY_REPLY', 'OWNER_DISTRESS', 'OWNER_EXPECTATION', 'OWNER_PLAYFUL']
    quote: str = Field(min_length=2, max_length=200)

class Extraction(StrictModel):
    memories: list[Candidate] = Field(default_factory=list, max_length=20)
    episode_summaries: list[EpisodeSummary] = Field(default_factory=list, max_length=4)
    interaction_signals: list[InteractionSignal] = Field(default_factory=list, max_length=8)

class MemoryRelation(StrictModel):
    supported: bool = Field(strict=True)
    update_authorized: bool = Field(strict=True)
    claims_replacement: bool = Field(strict=True)
    same: str | None = Field(default=None, pattern='^[mc]\\d+$')
    conflicts: list[str] = Field(default_factory=list, max_length=40)
    replaces: list[str] = Field(max_length=40)

class MemoryReview(StrictModel):
    relations: list[MemoryRelation] = Field(max_length=20)

class MemorySelection(StrictModel):
    relevant: list[str] = Field(max_length=10)

class CoreError(Exception):

    def __init__(self, code, status=409):
        self.code = code
        self.status = status
        super().__init__(code)
