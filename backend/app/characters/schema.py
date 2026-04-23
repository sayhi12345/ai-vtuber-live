from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class CharacterProfile:
    name: str
    short_description: str
    avatar: str | None = None


@dataclass(slots=True, frozen=True)
class Character:
    id: str
    profile: CharacterProfile
    personality: str
    speaking_style: str
    boundaries: str
    backstory: str

    def to_system_prompt(self) -> str:
        return (
            f"你是 {self.profile.name}，{self.profile.short_description}。\n\n"
            f"【人格設定】\n{self.personality.strip()}\n\n"
            f"【說話風格】\n{self.speaking_style.strip()}\n\n"
            f"【關係邊界】\n{self.boundaries.strip()}\n\n"
            f"【背景故事】\n{self.backstory.strip()}"
        )

    def to_summary(self) -> dict[str, str | None]:
        return {
            "id": self.id,
            "name": self.profile.name,
            "short_description": self.profile.short_description,
            "avatar": self.profile.avatar,
        }
