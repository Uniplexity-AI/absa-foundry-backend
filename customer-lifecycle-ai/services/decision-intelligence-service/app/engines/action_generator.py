"""Action Generation Engine — generates ALL possible actions.

Produces every candidate from the YAML action catalog.
Does NOT rank, filter, or prioritize — that happens downstream.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from app.schemas.schemas import CandidateAction

logger = logging.getLogger("decision.action_generator")

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "candidates"


class ActionGenerator:
    """Generates all candidate actions from the YAML catalog."""

    def __init__(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "action_catalog.yaml")
        self._catalog = self._load_catalog(config_path)
        total = sum(len(v) for v in self._catalog.values())
        logger.info("ActionGenerator loaded: %d actions in %d categories",
                     total, len(self._catalog))

    def generate(self) -> list[CandidateAction]:
        """Return ALL possible actions from every category."""
        candidates: list[CandidateAction] = []
        for category, actions in self._catalog.items():
            for action in actions:
                candidates.append(CandidateAction(
                    action=action,
                    category=category,
                ))
        return candidates

    def get_actions_by_category(self, category: str) -> list[str]:
        """Return action names for a specific category."""
        return list(self._catalog.get(category, []))

    @property
    def categories(self) -> list[str]:
        return list(self._catalog.keys())

    def _load_catalog(self, config_path: str) -> dict[str, list[str]]:
        with open(config_path) as f:
            data = yaml.safe_load(f)
        return data.get("actions", {})

    def reload(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "action_catalog.yaml")
        self._catalog = self._load_catalog(config_path)
        logger.info("ActionGenerator reloaded: %d categories", len(self._catalog))
