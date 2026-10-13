"""Deterministic generator of fictional fan profiles.

Design constraints:

* Demo identifiers use the form ``KYF-DEMO-XXXX-XXXX`` with letters, so they can
  never be mistaken for an 11-digit CPF or any other government number.
* Links use the reserved ``.example`` top-level domain (RFC 2606), so they never
  point to a real account.
* Cities are fictional. Names are random combinations of common given names and
  surnames; any resemblance to a real person is coincidental.
"""

from __future__ import annotations

import random
import re

from know_your_fan.models import FanProfile

DEMO_ID_PREFIX = "KYF-DEMO-"
# Crockford-style alphabet without easily confused characters.
_ID_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"
DEMO_ID_PATTERN = re.compile(rf"^KYF-DEMO-[{_ID_ALPHABET}]{{4}}-[{_ID_ALPHABET}]{{4}}$")

# Accented names are intentional: they exercise OCR and text normalization.
GIVEN_NAMES = (
    "Ana",
    "Bruno",
    "Camila",
    "Diego",
    "Elisa",
    "Fábio",
    "Gabriela",
    "Heitor",
    "Isabela",
    "João",
    "Larissa",
    "Marcos",
    "Natália",
    "Otávio",
    "Paula",
    "Rafael",
    "Sofia",
    "Tiago",
    "Valéria",
    "Yuri",
)
SURNAMES = (
    "Almeida",
    "Barros",
    "Cardoso",
    "Conceição",
    "Duarte",
    "Esteves",
    "Falcão",
    "Gonçalves",
    "Ishikawa",
    "Lima",
    "Moreira",
    "Nogueira",
    "Prado",
    "Ribeiro",
    "Simões",
    "Teixeira",
    "Vasconcelos",
)
FICTIONAL_CITIES = (
    "Vila Aurora",
    "Porto Celeste",
    "Nova Esmeralda",
    "Serra Dourada",
    "Lago Prateado",
    "Campo Sereno",
)
GAMES = (
    "Counter-Strike 2",
    "Valorant",
    "League of Legends",
    "Rainbow Six Siege",
    "Rocket League",
    "Dota 2",
)
ACTIVITIES = (
    "Watched a regional league final online",
    "Attended a local LAN party",
    "Played in an amateur online cup",
    "Followed a major tournament stream",
    "Joined a community watch party",
    "Organized a casual scrim with friends",
)
PURCHASES = (
    "Team jersey (demo item)",
    "Event ticket (demo item)",
    "Gaming headset (demo item)",
    "Mouse pad (demo item)",
    "In-game cosmetic bundle (demo item)",
)
SOCIAL_NETWORKS = ("social", "video", "stream")
ESPORTS_SITES = ("ladder", "stats", "matches")


def generate_demo_id(rng: random.Random) -> str:
    """Return a fictional identifier such as ``KYF-DEMO-7FQA-91CZ``."""
    chars = [rng.choice(_ID_ALPHABET) for _ in range(8)]
    return f"{DEMO_ID_PREFIX}{''.join(chars[:4])}-{''.join(chars[4:])}"


def _handle(name: str, rng: random.Random) -> str:
    base = re.sub(r"[^a-z]", "", name.split()[0].lower().encode("ascii", "ignore").decode())
    return f"{base}{rng.randint(10, 999)}"


def generate_profile(rng: random.Random) -> FanProfile:
    """Generate one fictional profile using the supplied random generator."""
    name = f"{rng.choice(GIVEN_NAMES)} {rng.choice(SURNAMES)} {rng.choice(SURNAMES)}"
    handle = _handle(name, rng)
    return FanProfile(
        demo_id=generate_demo_id(rng),
        name=name,
        city=rng.choice(FICTIONAL_CITIES),
        interests=tuple(rng.sample(GAMES, k=rng.randint(1, 3))),
        activities=tuple(rng.sample(ACTIVITIES, k=rng.randint(1, 3))),
        purchases=tuple(rng.sample(PURCHASES, k=rng.randint(0, 2))),
        social_links=tuple(
            f"https://{site}.example/@{handle}"
            for site in rng.sample(SOCIAL_NETWORKS, k=rng.randint(1, 2))
        ),
        esports_profiles=tuple(
            f"https://{site}.example/players/{handle}"
            for site in rng.sample(ESPORTS_SITES, k=rng.randint(1, 2))
        ),
    )


def generate_profiles(count: int, seed: int) -> list[FanProfile]:
    """Generate ``count`` profiles reproducibly from ``seed``."""
    if count < 0:
        raise ValueError("count must be non-negative")
    rng = random.Random(seed)
    return [generate_profile(rng) for _ in range(count)]


_SOCIAL_LINK = re.compile(rf"^https://({'|'.join(SOCIAL_NETWORKS)})\.example/@[a-z]+[0-9]{{2,3}}$")
_ESPORTS_LINK = re.compile(
    rf"^https://({'|'.join(ESPORTS_SITES)})\.example/players/[a-z]+[0-9]{{2,3}}$"
)


def synthetic_violations(profile: FanProfile) -> list[str]:
    """Return the reasons ``profile`` could not have come from this generator.

    The check is an allowlist: every value must belong to the generator's own
    vocabulary, so free text (such as a real address or CPF) is rejected.
    An empty list means the profile is acceptable for storage.
    """
    problems: list[str] = []
    if not DEMO_ID_PATTERN.fullmatch(profile.demo_id):
        problems.append("demo_id is not a KYF-DEMO identifier")
    parts = profile.name.split(" ")
    if not (
        len(parts) == 3
        and parts[0] in GIVEN_NAMES
        and parts[1] in SURNAMES
        and parts[2] in SURNAMES
    ):
        problems.append("name is not composed from the synthetic name lists")
    if profile.city not in FICTIONAL_CITIES:
        problems.append("city is not a fictional city")
    for field, vocabulary, minimum in (
        ("interests", GAMES, 1),
        ("activities", ACTIVITIES, 1),
        ("purchases", PURCHASES, 0),
    ):
        values: tuple[str, ...] = getattr(profile, field)
        if (
            len(values) < minimum
            or len(set(values)) != len(values)
            or not set(values) <= set(vocabulary)
        ):
            problems.append(f"{field} contains values outside the synthetic vocabulary")
    for field, pattern in (("social_links", _SOCIAL_LINK), ("esports_profiles", _ESPORTS_LINK)):
        links: tuple[str, ...] = getattr(profile, field)
        if not links or not all(pattern.fullmatch(link) for link in links):
            problems.append(f"{field} must only contain reserved .example links")
    return problems
