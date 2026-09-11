"""Loader and schema for the triage knowledge base.

The clinical knowledge lives in ``knowledge/triage_kb.yaml`` as reviewable,
source-tagged data. This module loads it once, validates it against a strict
schema (so a malformed KB fails fast on boot with a clear error instead of
silently mis-triaging), and exposes typed objects to the reasoning layer.

Design goals:
- Explainability: every clinical assertion carries a ``Provenance`` block, so
  a downstream conclusion can be traced to its source and citation.
- Safety: validation rejects references to unknown urgency levels, empty
  keyword lists, etc. — the KB can't ship in a broken state.
- Determinism: topic order is preserved exactly as authored, because the
  reasoning engine relies on a stable sort for tie-breaking.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

KB_PATH = Path(__file__).resolve().parent / "knowledge" / "triage_kb.yaml"


class KnowledgeBaseError(RuntimeError):
    """Raised when the KB file is missing, unparseable, or fails validation."""


class EvidenceLevel(str, Enum):
    provisional = "provisional"  # starter heuristic, not yet grounded in a source
    expert = "expert"            # vetted by a clinician but not a published guideline
    guideline = "guideline"      # traceable to a published triage guideline
    dataset = "dataset"          # derived from a clinical dataset


class ReviewStatus(str, Enum):
    unreviewed = "unreviewed"
    # Cross-checked against the cited source chart, but NOT yet signed off by a
    # licensed clinician. An honest middle ground between the two below.
    chart_verified = "chart-verified"
    clinician_reviewed = "clinician-reviewed"


class Provenance(BaseModel):
    """Where a clinical assertion came from — the backbone of explainability."""

    model_config = ConfigDict(extra="forbid")

    evidence_level: EvidenceLevel = EvidenceLevel.provisional
    review_status: ReviewStatus = ReviewStatus.unreviewed
    mapped_scale: str | None = None
    ref: str
    url: str | None = None


class UrgencyLevel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    rank: int
    label: str
    color: str
    # Human-readable mapping to the WHO IITT three-tier category, surfaced in UI.
    iitt_category: str | None = None


class ReferenceScale(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    url: str | None = None


class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    reference_scales: list[ReferenceScale] = Field(default_factory=list)
    # Licensing note for the source guidelines (surfaced for transparency).
    license: str | None = None


class Fallback(BaseModel):
    """What the engine emits when no topic matches (never guesses a topic)."""

    model_config = ConfigDict(extra="forbid")

    topic: str
    department: str
    urgency: str


class Applicability(BaseModel):
    """Patient conditions under which a discriminator is relevant. Several WHO
    IITT criteria are age- or sex-conditional (e.g. chest/abdominal pain is a
    red criterion only if age > 50; the pregnancy block applies to females).

    Semantics are safety-first: a discriminator is excluded ONLY when the
    patient context is KNOWN to contradict it. Unknown context never excludes,
    so a missing age/sex biases toward over-triage rather than under-triage."""

    model_config = ConfigDict(extra="forbid")

    age_min: float | None = None  # applies when age >= age_min
    age_max: float | None = None  # applies when age <= age_max
    sex: Literal["male", "female"] | None = None
    pregnant: bool | None = None


class Discriminator(BaseModel):
    """An acuity discriminator: a clinical sign that implies a minimum triage
    category. The reasoning engine escalates (never de-escalates) to the most
    acute matched category, citing the specific discriminator responsible."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    category: str  # must reference an urgency_levels id (validated on the KB)
    source: Provenance
    keywords: list[str]
    applies_when: Applicability | None = None

    @field_validator("keywords")
    @classmethod
    def _normalize_keywords(cls, value: list[str]) -> list[str]:
        cleaned = [k.strip().lower() for k in value if k.strip()]
        if not cleaned:
            raise ValueError("a discriminator must define at least one keyword")
        return cleaned

    def applies_to(
        self,
        age: float | None,
        sex: str | None,
        pregnant: bool | None,
    ) -> bool:
        """True unless the (known) patient context contradicts this rule."""
        a = self.applies_when
        if a is None:
            return True
        if a.age_min is not None and age is not None and age < a.age_min:
            return False
        if a.age_max is not None and age is not None and age > a.age_max:
            return False
        if a.sex is not None and sex is not None and sex != a.sex:
            return False
        if a.pregnant is not None and pregnant is not None and pregnant != a.pregnant:
            return False
        return True


class TopicRule(BaseModel):
    """One triage topic: the keywords that trigger it and where it routes."""

    model_config = ConfigDict(extra="forbid")

    id: str
    topic: str
    department: str
    urgency: str
    source: Provenance
    keywords: list[str]
    questions: list[str] = Field(default_factory=list)

    @field_validator("keywords")
    @classmethod
    def _normalize_keywords(cls, value: list[str]) -> list[str]:
        cleaned = [k.strip().lower() for k in value if k.strip()]
        if not cleaned:
            raise ValueError("a topic must define at least one keyword")
        return cleaned


class ConditionFinding(BaseModel):
    """A finding that shifts the odds of a condition. ``lr`` is the likelihood
    ratio applied when ``match`` appears in the conversation text (>1 raises the
    probability, <1 lowers it)."""

    model_config = ConfigDict(extra="forbid")

    match: str
    lr: float = Field(gt=0)

    @field_validator("match")
    @classmethod
    def _lower(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("a finding must have a non-empty match")
        return v


class Condition(BaseModel):
    """A candidate diagnosis for the probabilistic differential. The engine
    updates ``prior`` odds by each present finding's likelihood ratio (naive
    Bayes) to rank a cited differential. Age/sex-conditional conditions are
    gated by ``applies_when``."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    prior: float = Field(ge=0, le=1)
    department: str | None = None
    applies_when: "Applicability | None" = None
    findings: list[ConditionFinding]
    source: Provenance

    def applies_to(self, age: float | None, sex: str | None, pregnant: bool | None) -> bool:
        a = self.applies_when
        if a is None:
            return True
        if a.age_min is not None and age is not None and age < a.age_min:
            return False
        if a.age_max is not None and age is not None and age > a.age_max:
            return False
        if a.sex is not None and sex is not None and sex != a.sex:
            return False
        if a.pregnant is not None and pregnant is not None and pregnant != a.pregnant:
            return False
        return True


class AgeBand(BaseModel):
    """An age band for vital-sign thresholds. Bounds are in years; min is
    inclusive, max is exclusive. A missing bound means open-ended."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    min_age: float | None = None
    max_age: float | None = None


class VitalBand(BaseModel):
    """A [low, high] normal range. A reading below `low` or above `high` is
    abnormal. A null bound means that side is not checked."""

    model_config = ConfigDict(extra="forbid")

    low: float | None = None
    high: float | None = None


class VitalThreshold(BaseModel):
    """One measurable vital. `kind=numeric` compares against age-banded ranges;
    `kind=avpu` is abnormal when the reading is anything other than 'A' (alert)."""

    model_config = ConfigDict(extra="forbid")

    id: str  # heart_rate | resp_rate | temperature | spo2 | avpu
    label: str
    unit: str | None = None
    category: str
    kind: Literal["numeric", "avpu"] = "numeric"
    # Keyed by age-band id, or "all" for age-independent thresholds.
    bands: dict[str, VitalBand] = Field(default_factory=dict)


class VitalSigns(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Provenance
    age_bands: list[AgeBand]
    thresholds: list[VitalThreshold]

    def band_for(self, age: float | None) -> str:
        """Age-band id for an age; defaults to the last band (adult) when the
        age is unknown, so age-independent vitals still evaluate sensibly."""
        if age is not None:
            for band in self.age_bands:
                lo_ok = band.min_age is None or age >= band.min_age
                hi_ok = band.max_age is None or age < band.max_age
                if lo_ok and hi_ok:
                    return band.id
        return self.age_bands[-1].id if self.age_bands else "adult"


class KnowledgeBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    meta: Meta
    urgency_levels: list[UrgencyLevel]
    fallback: Fallback
    default_questions: list[str]
    discriminators: list[Discriminator]
    topics: list[TopicRule]
    vital_signs: VitalSigns | None = None
    conditions: list[Condition] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_integrity(self) -> "KnowledgeBase":
        levels = {u.id for u in self.urgency_levels}
        if not levels:
            raise ValueError("at least one urgency_level is required")

        ranks = [u.rank for u in self.urgency_levels]
        if len(set(ranks)) != len(ranks):
            raise ValueError("urgency_level ranks must be unique")

        # Every urgency referenced by a topic, the fallback, or a discriminator
        # must exist — a typo can't silently mis-triage.
        for topic in self.topics:
            if topic.urgency not in levels:
                raise ValueError(
                    f"topic {topic.id!r} references unknown urgency {topic.urgency!r}"
                )
        if self.fallback.urgency not in levels:
            raise ValueError(
                f"fallback references unknown urgency {self.fallback.urgency!r}"
            )
        for disc in self.discriminators:
            if disc.category not in levels:
                raise ValueError(
                    f"discriminator {disc.id!r} references unknown category {disc.category!r}"
                )
        if self.vital_signs is not None:
            for th in self.vital_signs.thresholds:
                if th.category not in levels:
                    raise ValueError(
                        f"vital threshold {th.id!r} references unknown category {th.category!r}"
                    )

        # Ids must be unique (they anchor provenance and graph nodes).
        topic_ids = [t.id for t in self.topics]
        if len(set(topic_ids)) != len(topic_ids):
            raise ValueError("topic ids must be unique")
        disc_ids = [d.id for d in self.discriminators]
        if len(set(disc_ids)) != len(disc_ids):
            raise ValueError("discriminator ids must be unique")
        cond_ids = [c.id for c in self.conditions]
        if len(set(cond_ids)) != len(cond_ids):
            raise ValueError("condition ids must be unique")

        return self

    @property
    def urgency_rank(self) -> dict[str, int]:
        """Map urgency id -> severity rank (0 = most acute) for tie-breaking."""
        return {u.id: u.rank for u in self.urgency_levels}

    @property
    def most_acute_urgency(self) -> str:
        """The urgency id with the lowest rank — used by the red-flag safety net."""
        return min(self.urgency_levels, key=lambda u: u.rank).id


@lru_cache(maxsize=1)
def load_kb() -> KnowledgeBase:
    """Load and validate the KB. Cached: the file is read once per process.

    Raises ``KnowledgeBaseError`` (never a bare parse/validation error) so the
    caller gets a clear, actionable message on boot.
    """
    if not KB_PATH.exists():
        raise KnowledgeBaseError(f"Knowledge base file not found: {KB_PATH}")

    try:
        raw = yaml.safe_load(KB_PATH.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise KnowledgeBaseError(f"Could not parse {KB_PATH.name}: {exc}") from exc

    if not isinstance(raw, dict):
        raise KnowledgeBaseError(f"{KB_PATH.name} must be a YAML mapping at the top level.")

    try:
        return KnowledgeBase.model_validate(raw)
    except ValidationError as exc:
        raise KnowledgeBaseError(
            f"Knowledge base {KB_PATH.name} failed validation:\n{exc}"
        ) from exc
