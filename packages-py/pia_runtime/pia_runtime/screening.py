from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .decision_context import content_hash


class Factor(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: Literal["momentum_breadth", "turnover_scaled"]
    weight: float = Field(ge=0, allow_inf_nan=False)


class ScreeningStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1"]
    strategy_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    required_capabilities: list[Literal["market_snapshot"]]
    filters: list[Literal["profile_universe", "eligible_instrument", "rules_liquidity"]]
    factors: list[Factor] = Field(min_length=1)
    missing_policy: Literal["legacy_zero_with_warning", "exclude_with_reason"] = "exclude_with_reason"
    score_round_digits: int = Field(ge=0, le=8)
    sort: list[Literal["score_desc", "input_ordinal_asc", "symbol_asc"]]

    @model_validator(mode="after")
    def validate_policy(self):
        if self.sort != ["score_desc", "input_ordinal_asc", "symbol_asc"]:
            raise ValueError("INVALID_SORT")
        if len({item.id for item in self.factors}) != len(self.factors):
            raise ValueError("DUPLICATE_FACTOR")
        if set(self.filters) != {"profile_universe", "eligible_instrument", "rules_liquidity"}:
            raise ValueError("REQUIRED_FILTER_MISSING")
        if self.required_capabilities != ["market_snapshot"]:
            raise ValueError("REQUIRED_CAPABILITY_MISSING")
        return self


def load_strategies(directory: Path) -> dict[tuple[str, str], dict]:
    result = {}
    for path in sorted(directory.iterdir()):
        if path.suffix not in {".json", ".yaml"}:
            continue
        strategy = ScreeningStrategy.model_validate(json.loads(path.read_text())).model_dump()
        key = strategy["strategy_id"], strategy["version"]
        if key in result and result[key] != strategy:
            raise ValueError("STRATEGY_VERSION_CONFLICT")
        result[key] = strategy
    return result


def execute_scan(manifest: dict, market: dict, profile: dict, rules: dict) -> dict:
    strategy = ScreeningStrategy.model_validate(manifest)
    candidates, excluded = [], []
    allowed_assets = {str(item).lower() for item in profile.get("allowed_asset_types", [])}
    allowed_boards = {str(item).lower() for item in profile.get("universe", [])}
    for ordinal, instrument in enumerate(market.get("instruments", [])):
        reasons, warnings = [], []

        def number(row, key):
            value = row.get(key)
            if value is None:
                warnings.append(f"MISSING_{key.upper()}")
                if strategy.missing_policy == "exclude_with_reason":
                    reasons.append(f"MISSING_{key.upper()}")
                return 0.0
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError(f"INVALID_NUMBER:{key}")
            return float(value)

        turnover, change, breadth = number(instrument, "average_turnover"), number(instrument, "change_pct"), number(market, "breadth")
        listed_days = number(instrument, "listed_days")
        if any(instrument.get(key) for key in ["is_st", "suspended", "is_delisting"]):
            reasons.append("INELIGIBLE_INSTRUMENT")
        if allowed_assets and str(instrument.get("asset_type", "")).lower() not in allowed_assets:
            reasons.append("PROFILE_ASSET_TYPE")
        if allowed_boards and str(instrument.get("board", "")).lower() not in allowed_boards:
            reasons.append("PROFILE_UNIVERSE")
        if listed_days < rules["new_listing_observation_days"]:
            reasons.append("RULE_NEW_LISTING")
        if turnover < rules["min_average_turnover"]:
            reasons.append("RULE_LIQUIDITY")
        if reasons:
            excluded.append({"symbol": instrument.get("symbol"), "reason_codes": sorted(set(reasons)), "input_ordinal": ordinal})
            continue
        values = {"momentum_breadth": change * (1 + breadth), "turnover_scaled": turnover / 100_000_000}
        factors = [
            {"id": item.id, "raw_values": {"change_pct": change, "breadth": breadth} if item.id == "momentum_breadth"
             else {"average_turnover": turnover}, "value": values[item.id],
             "weight": item.weight, "contribution": values[item.id] * item.weight}
            for item in strategy.factors
        ]
        score = round(sum(item["contribution"] for item in factors), strategy.score_round_digits)
        if not math.isfinite(score):
            raise ValueError("INVALID_SCORE")
        candidates.append({
            **{key: instrument.get(key) for key in ["symbol", "name", "asset_type", "board", "change_pct", "average_turnover"]},
            "score": score, "snapshot_id": market["snapshot_id"], "as_of": market["as_of"],
            "source": market["source"], "quality": market.get("quality", "unavailable"),
            "factors": factors, "warnings": warnings, "passed_filters": list(strategy.filters),
            "evidence_refs": [market["snapshot_id"]], "input_ordinal": ordinal,
            "action_eligible": False,
        })
    candidates.sort(key=lambda row: (-row["score"], row["input_ordinal"], str(row["symbol"])))
    return {
        "as_of": market["as_of"], "snapshot_id": market["snapshot_id"],
        "strategy_id": strategy.strategy_id, "strategy_version": strategy.version,
        "strategy_hash": content_hash(strategy.model_dump()),
        "candidates": candidates, "excluded": excluded,
    }
