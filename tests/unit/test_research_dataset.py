"""Dataset determinism, split integrity, leakage, ground truth, and image transformations."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageChops

from know_your_fan import ocr
from know_your_fan.research import dataset, degradations, preprocessing
from know_your_fan.research.dataset import PARTICLES, SPLITS, DatasetSpec, build_dataset, fold

SIZES = {"dev": 40, "val": 40, "test": 60}


@pytest.fixture(scope="module")
def data() -> dataset.Dataset:
    return build_dataset(DatasetSpec(seed=123, sources_per_split=SIZES))


def test_generation_is_deterministic(data: dataset.Dataset) -> None:
    again = build_dataset(DatasetSpec(seed=123, sources_per_split=SIZES))
    assert again.fingerprint() == data.fingerprint()
    other = build_dataset(DatasetSpec(seed=124, sources_per_split=SIZES))
    assert other.fingerprint() != data.fingerprint()


def test_split_sizes_and_identifiers(data: dataset.Dataset) -> None:
    assert Counter(s.split for s in data.sources) == SIZES
    assert len({s.source_id for s in data.sources}) == len(data.sources)
    assert all(s.source_id.startswith(f"{s.split}-") for s in data.sources)


def test_no_token_leaks_between_splits(data: dataset.Dataset) -> None:
    tokens = {
        split: {t for s in data.sources_in(split) for t in fold(s.name)} - set(PARTICLES)
        for split in SPLITS
    }
    assert not tokens["dev"] & tokens["val"]
    assert not tokens["dev"] & tokens["test"]
    assert not tokens["val"] & tokens["test"]


def test_names_are_unique_and_never_identical_across_splits(data: dataset.Dataset) -> None:
    names = [fold(s.name) for s in data.sources]
    assert len(set(names)) == len(names)


def test_near_duplicate_clusters_stay_in_one_split() -> None:
    for clusters in (dataset.GIVEN_CLUSTERS, dataset.SURNAME_CLUSTERS):
        assignment = dataset.assign_clusters(clusters)
        owners = {w: split for split, cs in assignment.items() for c in cs for w in c}
        for cluster in clusters:
            assert len({owners[w] for w in cluster}) == 1


def test_vocabulary_never_collides_with_fixed_card_text() -> None:
    reserved = dataset._reserved_tokens()
    words = [w for c in (*dataset.GIVEN_CLUSTERS, *dataset.SURNAME_CLUSTERS) for w in c]
    assert not {fold(w)[0] for w in words} & reserved
    assert len({fold(w)[0] for w in words}) == len(words)  # unique after accent folding


def test_dataset_covers_required_name_characteristics(data: dataset.Dataset) -> None:
    patterns = {s.pattern for s in data.sources}
    assert patterns == {"two", "three", "particle", "compound", "repeated"}
    assert any(s.has_accent for s in data.sources)
    assert {s.n_tokens for s in data.sources} >= {2, 3, 4}
    repeated = [s for s in data.sources if s.pattern == "repeated"]
    assert all(len(set(fold(s.name))) < len(fold(s.name)) for s in repeated)


def test_every_name_fits_on_the_card(data: dataset.Dataset) -> None:
    font = ocr.specimen_font(30)
    assert all(
        font.getlength(f"Name: {s.name}") <= dataset.MAX_NAME_LINE_WIDTH_PX for s in data.sources
    )


def test_ground_truth_matches_the_rendered_card_lines(data: dataset.Dataset) -> None:
    source = data.sources[0]
    lines = source.ground_truth()
    assert lines[2] == f"Name: {source.name}"
    assert lines == ocr.specimen_lines(source.profile())


def test_trials_one_positive_three_negatives(data: dataset.Dataset) -> None:
    per_source = Counter(t.source_id for t in data.trials)
    assert set(per_source.values()) == {4}
    kinds = Counter(t.kind for t in data.trials)
    assert kinds == dict.fromkeys(
        ("positive", "easy", "token_swap", "near_miss"), len(data.sources)
    )
    assert data.excluded_trials == {"easy": 0, "token_swap": 0, "near_miss": 0}


def test_negatives_differ_from_the_true_name_and_stay_in_split(data: dataset.Dataset) -> None:
    sources = {s.source_id: s for s in data.sources}
    split_tokens = {
        split: {t for s in data.sources_in(split) for t in fold(s.name)} for split in SPLITS
    }
    for trial in data.trials:
        source = sources[trial.source_id]
        if trial.is_positive:
            assert trial.candidate == source.name
            continue
        assert fold(trial.candidate) != fold(source.name)
        assert set(fold(trial.candidate)) <= split_tokens[trial.split] | {
            fold(t)[0] for t in trial.candidate.split()
        }


def test_easy_negatives_share_no_content_token(data: dataset.Dataset) -> None:
    sources = {s.source_id: s for s in data.sources}
    for trial in (t for t in data.trials if t.kind == "easy"):
        truth = set(fold(sources[trial.source_id].name)) - set(PARTICLES)
        assert not (set(fold(trial.candidate)) - set(PARTICLES)) & truth


def test_token_swap_and_near_miss_change_exactly_one_token(data: dataset.Dataset) -> None:
    sources = {s.source_id: s for s in data.sources}
    for trial in (t for t in data.trials if t.kind in {"token_swap", "near_miss"}):
        truth = sources[trial.source_id].name.split()
        candidate = trial.candidate.split()
        assert len(candidate) == len(truth)
        assert sum(a != b for a, b in zip(truth, candidate, strict=True)) == 1


@pytest.mark.parametrize("sizes", [{"dev": 100_000}, {"dev": -1}, {"holdout": 5}])
def test_out_of_range_split_sizes_are_rejected_up_front(sizes: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="sources_per_split"):
        build_dataset(DatasetSpec(seed=1, sources_per_split=sizes))


def test_exhausted_vocabulary_stops_instead_of_looping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dataset, "MAX_CONSECUTIVE_MISSES", 50)
    monkeypatch.setattr(dataset, "PATTERNS", (("two", 1.0),))  # few possible names
    with pytest.raises(ValueError, match="unique names"):
        build_dataset(DatasetSpec(seed=1, sources_per_split={"dev": 1000, "val": 1, "test": 1}))


def test_manifest_round_trip(tmp_path: Path, data: dataset.Dataset) -> None:
    sources_path, trials_path = dataset.write_manifest(data, tmp_path)
    with sources_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [r["name"] for r in rows] == [s.name for s in data.sources]
    with trials_path.open(encoding="utf-8") as handle:
        assert sum(1 for _ in csv.DictReader(handle)) == len(data.trials)


# ------------------------------------------------------------------ degradations


@pytest.fixture(scope="module")
def card(data: dataset.Dataset) -> Image.Image:
    return ocr.render_specimen(data.sources[0].profile())


@pytest.mark.parametrize("name", list(degradations.CONDITIONS))
def test_degradations_are_deterministic_and_bounded(card: Image.Image, name: str) -> None:
    condition = degradations.CONDITIONS[name]
    first = degradations.apply(card, condition, seed=99)
    second = degradations.apply(card, condition, seed=99)
    assert ImageChops.difference(first, second).getbbox() is None
    assert first.mode == "RGB"
    ocr.check_image(first)  # within the safety limits used by the OCR pipeline


def test_clean_condition_leaves_pixels_unchanged(card: Image.Image) -> None:
    clean = degradations.apply(card, degradations.CONDITIONS["clean"], seed=1)
    assert ImageChops.difference(clean, card.convert("RGB")).getbbox() is None


def test_noise_depends_on_seed_and_is_reproducible(card: Image.Image) -> None:
    noisy = degradations.CONDITIONS["noise_25"]
    a = np.asarray(degradations.apply(card, noisy, seed=1), dtype=float)
    b = np.asarray(degradations.apply(card, noisy, seed=2), dtype=float)
    assert not np.array_equal(a, b)
    residual = a - np.asarray(card.convert("RGB"), dtype=float)
    assert 15 < residual.std() < 30  # roughly sigma=25 before clipping


def test_noise_seed_is_stable_per_sample_and_condition() -> None:
    assert degradations.noise_seed(1, "dev-0001", "noise_10") == degradations.noise_seed(
        1, "dev-0001", "noise_10"
    )
    assert degradations.noise_seed(1, "dev-0001", "noise_10") != degradations.noise_seed(
        1, "dev-0002", "noise_10"
    )


def test_resolution_and_rotation_change_size_as_specified(card: Image.Image) -> None:
    low = degradations.apply(card, degradations.CONDITIONS["res_0.30"], seed=1)
    assert low.size == (round(card.width * 0.3), round(card.height * 0.3))
    rotated = degradations.apply(card, degradations.CONDITIONS["rot_+8"], seed=1)
    assert rotated.width > card.width
    assert rotated.height > card.height


def test_input_image_is_not_modified(card: Image.Image) -> None:
    before = card.copy()
    degradations.apply(card, degradations.CONDITIONS["combo_moderate"], seed=5)
    assert ImageChops.difference(before, card).getbbox() is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"blur_sigma": -1.0},
        {"blur_sigma": 9.0},
        {"rotation_degrees": 20.0},
        {"noise_sigma": 100.0},
        {"scale": 0.1},
        {"scale": 1.5},
        {"blur_sigma": float("nan")},
        {"rotation_degrees": float("inf")},
    ],
)
def test_invalid_degradation_parameters_are_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="bad"):
        degradations.Degradation("bad", **kwargs)


def test_condition_families() -> None:
    families = {name: d.family for name, d in degradations.CONDITIONS.items()}
    assert families["clean"] == "clean"
    assert families["blur_2"] == "blur"
    assert families["res_0.30"] == "resolution"
    assert families["combo_mild"] == "combined"


# ------------------------------------------------------------------ preprocessing


def test_p0_is_exactly_the_application_preprocessing(card: Image.Image) -> None:
    ours = preprocessing.STRATEGIES["P0_baseline"](card)
    assert ImageChops.difference(ours, ocr.preprocess(card)).getbbox() is None


def test_otsu_threshold_separates_two_levels() -> None:
    image = Image.new("L", (10, 10), 40)
    for x in range(5):
        for y in range(10):
            image.putpixel((x, y), 200)
    threshold = preprocessing.otsu_threshold(image)
    assert 40 <= threshold < 200
    assert set(np.unique(np.asarray(preprocessing.binarize(image)))) == {0, 255}


def test_otsu_rejects_non_grayscale() -> None:
    with pytest.raises(ValueError, match="mode 'L'"):
        preprocessing.otsu_threshold(Image.new("RGB", (2, 2)))


@pytest.mark.parametrize("name", list(preprocessing.STRATEGIES))
def test_every_strategy_output_stays_within_ocr_limits(name: str, card: Image.Image) -> None:
    worst = degradations.apply(card, degradations.CONDITIONS["rot_+8"], seed=1)
    out = preprocessing.STRATEGIES[name](worst)
    ocr.check_image(out)


def test_upscale_doubles_dimensions(card: Image.Image) -> None:
    out = preprocessing.STRATEGIES["P5_upscale2"](card)
    assert out.size == (card.width * 2, card.height * 2)
