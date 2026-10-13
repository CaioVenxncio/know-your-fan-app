"""Deterministic synthetic dataset: fictional names, specimen sources, splits, and trials.

Design (see docs/research/methodology.md):

* The name vocabulary is grouped into *clusters* of near-duplicate tokens
  (e.g. ``Ivo``/``Ivan``). Whole clusters are assigned to exactly one split,
  stratified by token category, so dev/val/test names share no given name or
  surname. Only the Portuguese particles (``da``, ``de``, ``do``, ``dos``,
  ``das``) occur in every split.
* No vocabulary token, after accent folding, equals any token of the fixed
  card text, the fictional cities, or the game titles, so a name can only be
  "found" in a card's name line.
* Every source has known ground-truth text (``ocr.specimen_lines``).
* Each source yields one positive and three negative matching trials
  (``easy``, ``token_swap``, ``near_miss``). Negatives that fold to the same
  tokens as the positive would be ambiguous; they are resampled and, if no
  alternative exists, excluded and counted.
"""

from __future__ import annotations

import csv
import hashlib
import random
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from know_your_fan import ocr
from know_your_fan.models import FanProfile
from know_your_fan.synthetic import (
    _ID_ALPHABET,
    DEMO_ID_PREFIX,
    FICTIONAL_CITIES,
    GAMES,
)
from know_your_fan.text_matching import normalize_tokens

DATASET_VERSION = "kyf-synth-names-v1"
SPLITS = ("dev", "val", "test")
PARTICLES = ("da", "de", "do", "dos", "das")
MAX_NAME_LINE_WIDTH_PX = 820.0  # card is 900 px wide and text starts at x=40
MAX_SOURCES_PER_SPLIT = 1000
MAX_CONSECUTIVE_MISSES = 5000  # vocabulary exhausted: stop instead of looping

# Near-duplicate clusters. Members of a cluster always land in the same split.
GIVEN_CLUSTERS: tuple[tuple[str, ...], ...] = (
    ("Ana", "Ane"),
    ("Lia", "Léa"),
    ("Ivo", "Ivan"),
    ("Davi", "Dani"),
    ("Elisa", "Eliza"),
    ("João", "Joana"),
    ("Otávio", "Otávia"),
    ("Caio", "Kaio"),
    ("Raul", "Saul"),
    ("Bruna", "Bruno"),
    ("Marina", "Mariana"),
    ("Renan", "Renato"),
    ("Tânia", "Tainá"),
    ("Lúcia", "Luciana"),
    ("Iara", "Lara"),
    ("Ilma", "Ilda"),
    ("Érica", "Érika"),
    ("Vítor", "Victor"),
    ("Thaís", "Tais"),
    ("Simone", "Simona"),
    ("Heloísa", "Eloísa"),
    ("Ícaro", "Ítalo"),
    ("Rui", "Ruy"),
    ("Noé", "Noel"),
    ("Isa", "Ísis"),
    ("Guilhermina", "Guilhermino"),
    ("Rosimeire", "Rosemeire"),
    ("Anastácia", "Anastásia"),
    ("Maximiliano",),
    ("Bartolomeu",),
    ("Cristóvão",),
    ("Edu",),
)
SURNAME_CLUSTERS: tuple[tuple[str, ...], ...] = (
    ("Souza", "Sousa"),
    ("Mendes", "Mendez"),
    ("Gonçalves", "Gonçalvez"),
    ("Pereira", "Ferreira"),
    ("Moura", "Mourão"),
    ("Teles", "Telles"),
    ("Melo", "Mello"),
    ("Barros", "Bairros"),
    ("Rocha", "Roche"),
    ("Vasconcelos", "Vasconcellos"),
    ("Bittencourt", "Bitencourt"),
    ("Simões", "Simão"),
    ("Assunção", "Assumpção"),
    ("Leão", "Leal"),
    ("Rios", "Reis"),
    ("Prado", "Pardo"),
    ("Morais", "Moraes"),
    ("Cavalcanti", "Cavalcante"),
    ("Wanderley", "Vanderlei"),
    ("Brandão", "Brandt"),
    ("Albuquerque",),
    ("Quintanilha",),
    ("Magalhães",),
    ("Nogueira",),
    ("Sá",),
    ("Paz",),
    ("Luz",),
    ("Lima",),
    ("Fontes",),
    ("Ximenes",),
)

# Name patterns and their sampling weights.
PATTERNS: tuple[tuple[str, float], ...] = (
    ("two", 0.25),  # Given Surname
    ("three", 0.30),  # Given Surname Surname
    ("particle", 0.15),  # Given particle Surname Surname
    ("compound", 0.15),  # Given Given Surname Surname
    ("repeated", 0.15),  # Given Surname Surname (same surname twice)
)

# Visually similar single-letter substitutions for near-miss negatives when a
# token has no cluster partner.
_LOOKALIKE = {
    "a": "o", "o": "a", "e": "c", "c": "e", "i": "l", "l": "i", "n": "m", "m": "n",
    "u": "v", "v": "u", "r": "n", "s": "z", "z": "s", "t": "f", "f": "t", "b": "h", "h": "b",
}  # fmt: skip


def fold(text: str) -> tuple[str, ...]:
    """Accent- and case-folded alphabetic tokens (the app's normalization)."""
    return tuple(normalize_tokens(text))


def _reserved_tokens() -> set[str]:
    profile_free = [ocr.SPECIMEN_TITLE, ocr.SPECIMEN_NOTICE, ocr.SPECIMEN_FOOTER]
    labels = ["Name", "Demo ID", "City", "Favorite game", "KYF", "DEMO"]
    tokens: set[str] = set()
    for text in (*profile_free, *labels, *FICTIONAL_CITIES, *GAMES):
        tokens.update(fold(text))
    return tokens


def _category(cluster: Sequence[str]) -> str:
    word = cluster[0]
    if any(not w.isascii() for w in cluster):
        return "accent"
    if len(word) >= 8:
        return "long"
    if len(word) <= 3:
        return "short"
    return "other"


def assign_clusters(clusters: Sequence[tuple[str, ...]]) -> dict[str, list[tuple[str, ...]]]:
    """Assign whole clusters to splits, round-robin within each token category."""
    result: dict[str, list[tuple[str, ...]]] = {split: [] for split in SPLITS}
    by_category: dict[str, list[tuple[str, ...]]] = {}
    for cluster in sorted(clusters, key=lambda c: fold(c[0])):
        by_category.setdefault(_category(cluster), []).append(cluster)
    offset = 0
    for category in sorted(by_category):
        for index, cluster in enumerate(by_category[category]):
            result[SPLITS[(index + offset) % len(SPLITS)]].append(cluster)
        offset += len(by_category[category])
    return result


@dataclass(frozen=True, slots=True)
class Source:
    """One synthetic specimen with known ground truth."""

    source_id: str
    split: str
    name: str
    pattern: str
    demo_id: str
    city: str
    game: str
    has_accent: bool
    n_tokens: int
    name_length: int

    def profile(self) -> FanProfile:
        """A FanProfile used only for rendering (never stored)."""
        return FanProfile(
            demo_id=self.demo_id,
            name=self.name,
            city=self.city,
            interests=(self.game,),
            activities=(),
            purchases=(),
            social_links=(),
            esports_profiles=(),
        )

    def ground_truth(self) -> list[str]:
        return ocr.specimen_lines(self.profile())


@dataclass(frozen=True, slots=True)
class Trial:
    """A candidate name compared against one source's OCR output."""

    trial_id: str
    source_id: str
    split: str
    kind: str  # positive | easy | token_swap | near_miss
    candidate: str

    @property
    def is_positive(self) -> bool:
        return self.kind == "positive"


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    seed: int
    sources_per_split: dict[str, int] = field(default_factory=dict)
    version: str = DATASET_VERSION


@dataclass(slots=True)
class Dataset:
    spec: DatasetSpec
    sources: list[Source]
    trials: list[Trial]
    excluded_trials: dict[str, int]
    vocabulary: dict[str, dict[str, list[str]]]

    def sources_in(self, split: str) -> list[Source]:
        return [s for s in self.sources if s.split == split]

    def fingerprint(self) -> str:
        """SHA-256 over sources and trials; identical specs must give identical datasets."""
        digest = hashlib.sha256()
        for source in self.sources:
            digest.update(repr(asdict(source)).encode())
        for trial in self.trials:
            digest.update(repr(asdict(trial)).encode())
        return digest.hexdigest()


def _rng(seed: int, *parts: object) -> random.Random:
    key = "|".join(str(p) for p in (seed, *parts)).encode()
    return random.Random(int.from_bytes(hashlib.sha256(key).digest()[:8], "big"))


def _name_fits(name: str) -> bool:
    return ocr.specimen_font(30).getlength(f"Name: {name}") <= MAX_NAME_LINE_WIDTH_PX


def _make_name(rng: random.Random, given: list[str], surnames: list[str]) -> tuple[str, str]:
    pattern = rng.choices([p for p, _ in PATTERNS], weights=[w for _, w in PATTERNS])[0]
    g1, g2 = rng.sample(given, 2)
    s1, s2 = rng.sample(surnames, 2)
    tokens = {
        "two": [g1, s1],
        "three": [g1, s1, s2],
        "particle": [g1, rng.choice(PARTICLES), s1, s2],
        "compound": [g1, g2, s1, s2],
        "repeated": [g1, s1, s1],
    }[pattern]
    return " ".join(tokens), pattern


def _demo_id(rng: random.Random, forbidden: set[str]) -> str:
    while True:
        chars = "".join(rng.choice(_ID_ALPHABET) for _ in range(8))
        demo_id = f"{DEMO_ID_PREFIX}{chars[:4]}-{chars[4:]}"
        if not set(fold(demo_id)) & forbidden:
            return demo_id


def _lookalike_edit(token: str, rng: random.Random) -> str | None:
    positions = [i for i, ch in enumerate(token) if i > 0 and ch.lower() in _LOOKALIKE]
    if not positions:
        return None
    i = rng.choice(positions)
    replacement = _LOOKALIKE[token[i].lower()]
    return token[:i] + replacement + token[i + 1 :]


def build_dataset(spec: DatasetSpec) -> Dataset:
    """Generate sources and trials deterministically from ``spec``."""
    for split, count in spec.sources_per_split.items():
        if split not in SPLITS or not 0 <= count <= MAX_SOURCES_PER_SPLIT:
            raise ValueError(
                f"sources_per_split must map {SPLITS} to 0..{MAX_SOURCES_PER_SPLIT} sources"
            )
    reserved = _reserved_tokens()
    given_split = assign_clusters(GIVEN_CLUSTERS)
    surname_split = assign_clusters(SURNAME_CLUSTERS)
    all_words = [w for c in (*GIVEN_CLUSTERS, *SURNAME_CLUSTERS) for w in c]
    vocab_tokens = {fold(w)[0] for w in all_words}
    sources: list[Source] = []
    trials: list[Trial] = []
    excluded = {"easy": 0, "token_swap": 0, "near_miss": 0}
    vocabulary: dict[str, dict[str, list[str]]] = {}

    for split in SPLITS:
        count = spec.sources_per_split.get(split, 0)
        given = [w for c in given_split[split] for w in c]
        surnames = [w for c in surname_split[split] for w in c]
        partners = {w: [p for p in c if p != w] for c in given_split[split] for w in c}
        partners.update({w: [p for p in c if p != w] for c in surname_split[split] for w in c})
        vocabulary[split] = {"given": given, "surnames": surnames}
        rng = _rng(spec.seed, spec.version, split, "names")
        names: list[tuple[str, str]] = []
        seen: set[tuple[str, ...]] = set()
        misses = 0
        while len(names) < count:
            name, pattern = _make_name(rng, given, surnames)
            key = fold(name)
            if key in seen or not _name_fits(name):
                misses += 1
                if misses > MAX_CONSECUTIVE_MISSES:
                    raise ValueError(f"Could not generate {count} unique names for split {split!r}")
                continue
            misses = 0
            seen.add(key)
            names.append((name, pattern))

        split_sources: list[Source] = []
        for index, (name, pattern) in enumerate(names, start=1):
            srng = _rng(spec.seed, spec.version, split, index, "card")
            source = Source(
                source_id=f"{split}-{index:04d}",
                split=split,
                name=name,
                pattern=pattern,
                demo_id=_demo_id(srng, vocab_tokens),
                city=srng.choice(FICTIONAL_CITIES),
                game=srng.choice(GAMES),
                has_accent=not name.isascii(),
                n_tokens=len(name.split()),
                name_length=len(name),
            )
            split_sources.append(source)
        sources.extend(split_sources)

        for source in split_sources:
            trng = _rng(spec.seed, spec.version, source.source_id, "trials")
            truth = fold(source.name)
            trials.append(
                Trial(
                    f"{source.source_id}/positive", source.source_id, split, "positive", source.name
                )
            )
            words = source.name.split()
            # easy: another name of the split sharing no token and no near-duplicate partner
            related = {fold(w)[0] for w in words if w.lower() not in PARTICLES}
            related |= {fold(p)[0] for w in words for p in partners.get(w, [])}
            others = [
                o.name for o in split_sources
                if o is not source and not (set(fold(o.name)) - set(PARTICLES)) & related
            ]  # fmt: skip
            # token_swap: one token replaced by an unrelated token of the same role and split
            swap_positions = [i for i, w in enumerate(words) if w.lower() not in PARTICLES]
            candidates: dict[str, list[str]] = {"easy": others, "token_swap": [], "near_miss": []}
            for i in swap_positions:
                role_pool = given if words[i] in given else surnames
                pool = [w for w in role_pool if fold(w)[0] not in related]
                for replacement in pool:
                    candidates["token_swap"].append(
                        " ".join([*words[:i], replacement, *words[i + 1 :]])
                    )
                for partner in partners.get(words[i], []):
                    candidates["near_miss"].append(" ".join([*words[:i], partner, *words[i + 1 :]]))
                edited = _lookalike_edit(words[i], trng)
                if edited and not partners.get(words[i]):
                    candidates["near_miss"].append(" ".join([*words[:i], edited, *words[i + 1 :]]))
            for kind in ("easy", "token_swap", "near_miss"):
                valid = sorted({c for c in candidates[kind] if fold(c) != truth})
                if not valid:
                    excluded[kind] += 1
                    continue
                trials.append(
                    Trial(
                        f"{source.source_id}/{kind}",
                        source.source_id,
                        split,
                        kind,
                        trng.choice(valid),
                    )
                )

    _check_invariants(sources, reserved, given_split, surname_split)
    return Dataset(spec, sources, trials, excluded, vocabulary)


def _check_invariants(
    sources: Iterable[Source],
    reserved: set[str],
    given_split: dict[str, list[tuple[str, ...]]],
    surname_split: dict[str, list[tuple[str, ...]]],
) -> None:
    words = [w for c in (*GIVEN_CLUSTERS, *SURNAME_CLUSTERS) for w in c]
    folded = [fold(w) for w in words]
    if any(len(f) != 1 for f in folded) or len({f[0] for f in folded}) != len(words):
        raise ValueError("vocabulary tokens must be single words, unique after accent folding")
    if {f[0] for f in folded} & reserved or set(PARTICLES) & reserved:
        raise ValueError("vocabulary overlaps fixed card text")
    per_split = {
        split: {fold(w)[0] for c in given_split[split] + surname_split[split] for w in c}
        for split in SPLITS
    }
    for a in SPLITS:
        for b in SPLITS:
            if a < b and per_split[a] & per_split[b]:
                raise ValueError(f"vocabulary leaks between {a} and {b}")
    names = [fold(s.name) for s in sources]
    if len(set(names)) != len(names):
        raise ValueError("duplicate names in dataset")


SOURCE_FIELDS = list(Source.__dataclass_fields__)
TRIAL_FIELDS = list(Trial.__dataclass_fields__)


def write_manifest(dataset: Dataset, directory: Path) -> tuple[Path, Path]:
    """Write ``sources.csv`` and ``trials.csv`` (UTF-8) into ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    sources_path = directory / "sources.csv"
    trials_path = directory / "trials.csv"
    with sources_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SOURCE_FIELDS)
        writer.writeheader()
        writer.writerows(asdict(s) for s in dataset.sources)
    with trials_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRIAL_FIELDS)
        writer.writeheader()
        writer.writerows(asdict(t) for t in dataset.trials)
    return sources_path, trials_path
