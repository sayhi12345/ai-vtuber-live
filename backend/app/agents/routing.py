from __future__ import annotations

from dataclasses import dataclass
import logging
import re

from app.bazi import is_bazi_query
from app.pipeline import summarize_for_log
from app.tarot import is_tarot_query

logger = logging.getLogger(__name__)

_DIVINATION_KEYWORDS = (
    "tarot",
    "塔羅",
    "塔罗",
    "算命",
    "命理",
    "八字",
    "四柱",
    "紫微",
    "占星",
    "星座",
    "運勢",
    "运势",
)
_DIVINATION_PATTERNS = tuple(
    re.compile(re.escape(keyword), re.IGNORECASE) for keyword in _DIVINATION_KEYWORDS
)


@dataclass(frozen=True, slots=True)
class AgentSkillSpec:
    name: str
    source_path: str
    runtime_instructions: str = ""

    def matches(self, text: str) -> bool:
        if self.name == "tarot":
            return is_tarot_query(text)
        if self.name == "bazi-mingli":
            return is_bazi_query(text)
        return False


@dataclass(frozen=True, slots=True)
class AgentRouteDecision:
    use_agent: bool
    matched_skills: tuple[AgentSkillSpec, ...]

    @property
    def mode(self) -> str:
        if not self.use_agent:
            return "chat"
        if len(self.matched_skills) == 1:
            return self.matched_skills[0].name
        return "agent"

    @property
    def skill_names(self) -> list[str]:
        return [skill.name for skill in self.matched_skills]

    @property
    def skill_sources(self) -> list[str]:
        return [skill.source_path for skill in self.matched_skills]

    @property
    def runtime_instructions(self) -> str:
        instructions = [skill.runtime_instructions.strip() for skill in self.matched_skills]
        return "\n\n".join(item for item in instructions if item)


class SelectiveAgentRouter:
    def __init__(self) -> None:
        self._skills = (
            AgentSkillSpec(
                name="tarot",
                source_path="/skills/tarot",
                runtime_instructions=(
                    "Tarot skill compatibility rules:\n"
                    "- The selected skill lives at /skills/tarot.\n"
                    "- If the skill asks you to run scripts/draw.py, use the tool "
                    "`draw_tarot_cards_tool(question, spread)` instead.\n"
                    "- Treat relative references like `references/cards.md` as files under "
                    "`/skills/tarot/references/`.\n"
                    "- Do not attempt shell execution; use the provided tool and file reads only."
                ),
            ),
            AgentSkillSpec(
                name="bazi-mingli",
                source_path="/skills/bazi-mingli",
                runtime_instructions=(
                    "Bazi skill compatibility rules:\n"
                    "- The selected skill lives at /skills/bazi-mingli.\n"
                    "- If the skill asks you to run scripts/bazi_calc.py, use the tool "
                    "`calculate_bazi_chart_tool(year, month, day, hour, gender)` instead.\n"
                    "- Treat relative references like `references/dayun-liunian.md` as files under "
                    "`/skills/bazi-mingli/references/`.\n"
                    "- Do not attempt shell execution; use the provided tool and file reads only."
                ),
            ),
        )

    def decide(self, text: str) -> AgentRouteDecision:
        matched = tuple(skill for skill in self._skills if skill.matches(text))
        decision = AgentRouteDecision(use_agent=bool(matched), matched_skills=matched)
        if matched or _is_divination_query(text):
            query_summary = _summarize_query(text)
            logger.info(
                "Selective agent router detected divination-related query: mode=%s matched_skills=%s query=%r",
                decision.mode,
                decision.skill_names,
                query_summary,
            )
            if decision.use_agent:
                logger.info(
                    "Selective agent router routing request to agent skills: mode=%s matched_skills=%s query=%r",
                    decision.mode,
                    decision.skill_names,
                    query_summary,
                )
            elif decision.mode == "chat":
                logger.info(
                    "Selective agent router kept divination-related query on standard chat path: matched_skills=%s query=%r",
                    decision.skill_names,
                    query_summary,
                )
        return decision


def _is_divination_query(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return any(pattern.search(stripped) for pattern in _DIVINATION_PATTERNS)


_summarize_query = summarize_for_log
