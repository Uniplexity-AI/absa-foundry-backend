"""Campaign Mapper — maps product recommendations to active marketing campaigns.

Loads campaign catalog from config/products/campaign_catalog.yaml.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from app.schemas.schemas import DecisionContext

logger = logging.getLogger("decision.recommendation.campaigns")

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "config" / "products"


class CampaignMapper:
    """Maps NBO recommendations to active campaigns."""

    def __init__(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "campaign_catalog.yaml")
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        self._campaigns = cfg["campaigns"]
        logger.info("CampaignMapper: %d campaigns loaded", len(self._campaigns))

    def map_recommendations(
        self, recommendations: list[dict], ctx: DecisionContext
    ) -> list[dict]:
        """Attach campaign info to each recommendation.

        Returns enriched recommendations with campaign_id, campaign_name, channel.
        """
        seg = ctx.segment or "MASS_MARKET"
        results = []

        for rec in recommendations:
            enriched = dict(rec)
            campaign = self._find_campaign(rec["product_id"], seg)
            if campaign:
                enriched["campaign_id"] = campaign["id"]
                enriched["campaign_name"] = campaign["name"]
                enriched["channel"] = campaign["channel"]
                enriched["priority"] = campaign["priority"]
            else:
                enriched["campaign_id"] = None
                enriched["campaign_name"] = None
                enriched["channel"] = None
                enriched["priority"] = None
            results.append(enriched)

        return results

    def get_campaign_target_list(
        self, segment: str | None = None, limit: int = 1000
    ) -> list[dict]:
        """Get active campaigns with target audience sizing.

        Returns list of {campaign_id, campaign_name, product, target_segments,
                         channel, priority, audience_size}
        """
        active = [c for c in self._campaigns if c.get("active", True)]
        if segment:
            active = [c for c in active if segment in c.get("target_segments", [])]

        return [
            {
                "campaign_id": c["id"],
                "campaign_name": c["name"],
                "product": c["product"],
                "target_segments": c.get("target_segments", []),
                "channel": c["channel"],
                "priority": c["priority"],
                "audience_size": 0,  # Stub — needs DB query
            }
            for c in active[:limit]
        ]

    def _find_campaign(self, product_id: str, segment: str) -> dict | None:
        """Find the best matching active campaign for a product + segment."""
        matches = [
            c for c in self._campaigns
            if c.get("active", True)
            and c["product"] == product_id
            and segment in c.get("target_segments", [])
        ]
        if not matches:
            return None
        # Return highest priority campaign
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        matches.sort(key=lambda c: priority_order.get(c.get("priority", "LOW"), 2))
        return matches[0]

    def reload(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "campaign_catalog.yaml")
        with open(config_path) as f:
            self._campaigns = yaml.safe_load(f)["campaigns"]
        logger.info("CampaignMapper reloaded")
