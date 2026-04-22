from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml

from app.characters.schema import Character, CharacterProfile

_REQUIRED_TOP_LEVEL = ("id", "profile", "personality", "speaking_style", "boundaries", "backstory")
_REQUIRED_PROFILE = ("name", "short_description")


class CharacterLoadError(ValueError):
    pass


class CharacterRegistry:
    def __init__(self, characters: Iterable[Character]) -> None:
        self._by_id: dict[str, Character] = {}
        for character in characters:
            if character.id in self._by_id:
                raise CharacterLoadError(f"Duplicate character id: {character.id}")
            self._by_id[character.id] = character
        if not self._by_id:
            raise CharacterLoadError("No characters loaded — at least one is required.")

    def get(self, character_id: str) -> Character:
        if character_id not in self._by_id:
            raise KeyError(character_id)
        return self._by_id[character_id]

    def has(self, character_id: str) -> bool:
        return character_id in self._by_id

    def list_summaries(self) -> list[dict[str, str | None]]:
        return [c.to_summary() for c in self._by_id.values()]


def _parse_character(path: Path) -> Character:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CharacterLoadError(f"{path.name}: invalid YAML — {exc}") from exc

    if not isinstance(raw, dict):
        raise CharacterLoadError(f"{path.name}: root must be a mapping.")

    for key in _REQUIRED_TOP_LEVEL:
        if key not in raw or raw[key] in (None, ""):
            raise CharacterLoadError(f"{path.name}: missing required field '{key}'.")

    expected_id = path.stem
    if raw["id"] != expected_id:
        raise CharacterLoadError(
            f"{path.name}: id '{raw['id']}' does not match filename stem '{expected_id}'."
        )

    profile_raw = raw["profile"]
    if not isinstance(profile_raw, dict):
        raise CharacterLoadError(f"{path.name}: 'profile' must be a mapping.")
    for key in _REQUIRED_PROFILE:
        if key not in profile_raw or not profile_raw[key]:
            raise CharacterLoadError(f"{path.name}: profile.{key} is required.")

    profile = CharacterProfile(
        name=str(profile_raw["name"]),
        short_description=str(profile_raw["short_description"]),
        avatar=profile_raw.get("avatar") or None,
    )

    return Character(
        id=str(raw["id"]),
        profile=profile,
        personality=str(raw["personality"]),
        speaking_style=str(raw["speaking_style"]),
        boundaries=str(raw["boundaries"]),
        backstory=str(raw["backstory"]),
    )


def load_registry_from_directory(directory: Path) -> CharacterRegistry:
    if not directory.is_dir():
        raise CharacterLoadError(f"Character directory not found: {directory}")

    files = sorted(directory.glob("*.yaml"))
    if not files:
        raise CharacterLoadError(f"No *.yaml character files found in {directory}")

    return CharacterRegistry(_parse_character(path) for path in files)


def load_default_registry() -> CharacterRegistry:
    directory = Path(__file__).resolve().parent / "definitions"
    return load_registry_from_directory(directory)
