from __future__ import annotations

import base64
import json
import math
from datetime import datetime
from typing import Any

from .db import Database


class DecisionJournal:
    """Read-only cross-task projection for decisions and observed outcomes."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def list(
        self,
        *,
        user_id: str = "default",
        symbol: str | None = None,
        intent: str | None = None,
        outcome_status: str | None = None,
        rule_snapshot_id: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        normalized_limit = max(1, min(int(limit), 100))
        normalized_symbol = symbol.strip().upper() if symbol else None
        normalized_intent = intent.strip().upper() if intent else None
        normalized_outcome = outcome_status.strip().lower() if outcome_status else None
        normalized_rule = rule_snapshot_id.strip() if rule_snapshot_id else None
        cursor_key = self._decode_cursor(cursor)

        items = self._collect(
            user_id=user_id,
            symbol=normalized_symbol,
            intent=normalized_intent,
            outcome_status=normalized_outcome,
            rule_snapshot_id=normalized_rule,
            from_date=from_date,
            to_date=to_date,
            cursor_key=cursor_key,
            limit=normalized_limit,
        )
        next_cursor = None
        if len(items) == normalized_limit:
            last_task = items[-1]["decision_record"]["task"]
            next_cursor = self._encode_cursor(
                (str(last_task.get("created_at", "")), str(last_task.get("id", "")))
            )
        return {"items": items, "next_cursor": next_cursor}

    def summary(
        self,
        *,
        user_id: str = "default",
        symbol: str | None = None,
        intent: str | None = None,
        outcome_status: str | None = None,
        rule_snapshot_id: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        items = self._collect(
            user_id=user_id,
            symbol=self._normalize_symbol(symbol),
            intent=self._normalize_intent(intent),
            outcome_status=self._normalize_outcome(outcome_status),
            rule_snapshot_id=rule_snapshot_id.strip() if rule_snapshot_id else None,
            from_date=from_date,
            to_date=to_date,
            limit=None,
        )
        retrospectives = [
            retrospective
            for item in items
            for retrospective in item["retrospectives"]
        ]
        returns = [
            value
            for retrospective in retrospectives
            if (value := self._return_pct(retrospective)) is not None
        ]
        benchmark_returns = [
            value
            for retrospective in retrospectives
            if (value := self._benchmark_return_pct(retrospective)) is not None
        ]
        excess_returns = [
            value
            for retrospective in retrospectives
            if (value := self._excess_return_pct(retrospective)) is not None
        ]
        action_counts: dict[str, int] = {}
        outcome_status_counts: dict[str, int] = {}
        horizon_counts: dict[str, int] = {}
        for retrospective in retrospectives:
            action = self._action_category(retrospective)
            action_counts[action] = action_counts.get(action, 0) + 1
            status = str(retrospective.get("outcome_status") or "unknown")
            outcome_status_counts[status] = outcome_status_counts.get(status, 0) + 1
            outcome = retrospective.get("outcome")
            horizon = str(
                outcome.get("horizon")
                if isinstance(outcome, dict) else "USER_RECORDED"
            ).upper()
            horizon_counts[horizon] = horizon_counts.get(horizon, 0) + 1

        intent_counts: dict[str, int] = {}
        rule_snapshot_counts: dict[str, int] = {}
        for item in items:
            record = item["decision_record"]
            decision_intent = str(record.get("intent") or "UNKNOWN")
            intent_counts[decision_intent] = intent_counts.get(decision_intent, 0) + 1
            rule_id = str(record.get("rule_snapshot_id") or "UNKNOWN")
            rule_snapshot_counts[rule_id] = rule_snapshot_counts.get(rule_id, 0) + 1

        warnings: list[str] = []
        if len(items) < 3:
            warnings.append("样本量少于 3，只适合观察，不形成稳定模式。")
        if len(retrospectives) < len(items):
            warnings.append("部分决策还没有后续结果记录，未计入结果统计。")
        return {
            "decision_count": len(items),
            "retrospective_count": len(retrospectives),
            "intent_counts": intent_counts,
            "action_counts": action_counts,
            "outcome_status_counts": outcome_status_counts,
            "comparable_outcome_count": len(returns),
            "average_return_pct": round(sum(returns) / len(returns), 4) if returns else None,
            "benchmark_outcome_count": len(benchmark_returns),
            "average_benchmark_return_pct": (
                round(sum(benchmark_returns) / len(benchmark_returns), 4)
                if benchmark_returns else None
            ),
            "average_excess_return_pct": (
                round(sum(excess_returns) / len(excess_returns), 4)
                if excess_returns else None
            ),
            "horizon_counts": horizon_counts,
            "rule_snapshot_counts": rule_snapshot_counts,
            "warnings": warnings,
        }

    def patterns(
        self,
        *,
        user_id: str = "default",
        symbol: str | None = None,
        intent: str | None = None,
        outcome_status: str | None = None,
        rule_snapshot_id: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        items = self._collect(
            user_id=user_id,
            symbol=self._normalize_symbol(symbol),
            intent=self._normalize_intent(intent),
            outcome_status=self._normalize_outcome(outcome_status),
            rule_snapshot_id=rule_snapshot_id.strip() if rule_snapshot_id else None,
            from_date=from_date,
            to_date=to_date,
            limit=None,
        )
        intent_groups = self._group_patterns(items, "intent")
        rule_groups = self._group_patterns(items, "rule_snapshot_id")
        candidates = [
            {
                "candidate_key": f"RETROSPECTIVE_PATTERN:{group['key']}",
                "kind": "RETROSPECTIVE_PATTERN",
                "intent": group["key"],
                "title": f"{group['key']} 后续记录模式",
                "eligible": group["sample_size"] >= 3 and group["comparable_outcome_count"] >= 3,
                "sample_size": group["sample_size"],
                "comparable_outcome_count": group["comparable_outcome_count"],
                "average_return_pct": group["average_return_pct"],
                "average_benchmark_return_pct": group["average_benchmark_return_pct"],
                "average_excess_return_pct": group["average_excess_return_pct"],
                "horizon_counts": group["horizon_counts"],
                "source_task_ids": group["source_task_ids"],
                "source_rule_snapshot_ids": group["source_rule_snapshot_ids"],
                "as_of": group["as_of"],
                "observed_at": group["observed_at"],
                "usage_count": 0,
                "latest_usage_id": None,
                "usage_task_ids": [],
                "usage_outcome_count": 0,
                "usage_average_return_pct": None,
                "usage_outcome_status_counts": {},
                "feedback_count": 0,
                "helpful_count": 0,
                "not_helpful_count": 0,
                "uncertain_count": 0,
                "feedback_recommendation": "NO_FEEDBACK",
                "reason": (
                    "样本量和可比较结果达到最低门槛。"
                    if group["sample_size"] >= 3 and group["comparable_outcome_count"] >= 3
                    else "需要至少 3 条决策和 3 条可比较结果。"
                ),
            }
            for group in intent_groups
        ]
        persisted = {
            str(row["candidate_key"]): row
            for row in self.db.list_memory_candidates(user_id=user_id)
        }
        for candidate in candidates:
            stored = persisted.get(str(candidate["candidate_key"]))
            candidate["status"] = str(stored["status"]) if stored else "UNSAVED"
            if stored:
                candidate["memory_candidate_id"] = stored["id"]
                candidate["updated_at"] = stored["updated_at"]
                candidate["title"] = stored["title"]
                candidate["content"] = stored["content"]
                candidate["reviewed_at"] = stored.get("reviewed_at")
                candidate["reviewed_by"] = stored.get("reviewed_by")
                candidate["review_action"] = stored.get("review_action")
                candidate["review_notes"] = stored.get("review_notes", "")
                usages = self.db.list_memory_candidate_usages(
                    str(stored["id"]),
                    user_id=user_id,
                )
                usage_returns: list[float] = []
                usage_status_counts: dict[str, int] = {}
                for usage in usages:
                    detail = self.db.get_task_detail(
                        str(usage["task_id"]),
                        user_id,
                    )
                    for retrospective in (detail or {}).get("retrospectives", []):
                        status = str(retrospective.get("outcome_status") or "unknown")
                        usage_status_counts[status] = usage_status_counts.get(status, 0) + 1
                        return_pct = self._return_pct(retrospective)
                        if return_pct is not None:
                            usage_returns.append(return_pct)
                candidate["usage_count"] = len(usages)
                candidate["latest_usage_id"] = str(usages[0]["id"]) if usages else None
                candidate["usage_task_ids"] = [
                    str(usage["task_id"]) for usage in usages
                ]
                candidate["usage_outcome_count"] = len(usage_returns)
                candidate["usage_average_return_pct"] = (
                    round(sum(usage_returns) / len(usage_returns), 4)
                    if usage_returns else None
                )
                candidate["usage_outcome_status_counts"] = usage_status_counts
                candidate.update(self.feedback_summary(
                    str(stored["id"]),
                    user_id=user_id,
                ))
            candidate["content"] = json.dumps(
                {
                    "description": candidate["reason"],
                    "intent": candidate["intent"],
                    "sample_size": candidate["sample_size"],
                    "comparable_outcome_count": candidate["comparable_outcome_count"],
                    "average_return_pct": candidate["average_return_pct"],
                    "average_benchmark_return_pct": candidate["average_benchmark_return_pct"],
                    "average_excess_return_pct": candidate["average_excess_return_pct"],
                    "horizon_counts": candidate["horizon_counts"],
                    "source_task_ids": candidate["source_task_ids"],
                    "source_rule_snapshot_ids": candidate["source_rule_snapshot_ids"],
                },
                ensure_ascii=False,
                sort_keys=True,
            ) if not stored else str(stored["content"])
        return {
            "intent_patterns": intent_groups,
            "rule_patterns": rule_groups,
            "memory_candidates": candidates,
            "warnings": [
                "Patterns 是确定性统计，不代表预测正确率。",
                "不同规则快照分开统计，避免版本变化造成伪规律。",
            ],
        }

    def feedback_summary(
        self,
        candidate_id: str,
        *,
        user_id: str = "default",
    ) -> dict[str, Any]:
        feedback = self.db.list_memory_candidate_feedback(
            candidate_id,
            user_id=user_id,
        )
        counts = {
            "HELPFUL": 0,
            "NOT_HELPFUL": 0,
            "UNCERTAIN": 0,
        }
        for row in feedback:
            rating = str(row.get("rating") or "").upper()
            if rating in counts:
                counts[rating] += 1
        if not feedback:
            recommendation = "NO_FEEDBACK"
        elif counts["NOT_HELPFUL"] >= 2 and counts["HELPFUL"] == 0:
            recommendation = "ARCHIVE_SUGGESTED"
        elif counts["NOT_HELPFUL"] > counts["HELPFUL"]:
            recommendation = "REVIEW_SUGGESTED"
        elif counts["HELPFUL"] > counts["NOT_HELPFUL"]:
            recommendation = "KEEP"
        else:
            recommendation = "REVIEW_SUGGESTED"
        return {
            "feedback_count": len(feedback),
            "helpful_count": counts["HELPFUL"],
            "not_helpful_count": counts["NOT_HELPFUL"],
            "uncertain_count": counts["UNCERTAIN"],
            "feedback_recommendation": recommendation,
        }

    def materialize_memory_candidate(
        self,
        candidate_key: str,
        *,
        user_id: str = "default",
        symbol: str | None = None,
        intent: str | None = None,
        outcome_status: str | None = None,
        rule_snapshot_id: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        report = self.patterns(
            user_id=user_id,
            symbol=symbol,
            intent=intent,
            outcome_status=outcome_status,
            rule_snapshot_id=rule_snapshot_id,
            from_date=from_date,
            to_date=to_date,
        )
        candidate = next(
            (
                row for row in report["memory_candidates"]
                if str(row.get("candidate_key")) == candidate_key
            ),
            None,
        )
        if not candidate:
            raise KeyError(candidate_key)
        if not candidate.get("eligible"):
            raise ValueError("memory candidate does not meet the minimum threshold")
        return self.db.save_memory_candidate(candidate, user_id=user_id)

    def review_memory_candidate(
        self,
        candidate_id: str,
        *,
        action: str,
        user_id: str = "default",
        title: str | None = None,
        content: str | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        return self.db.review_memory_candidate(
            candidate_id,
            action=action,
            user_id=user_id,
            title=title,
            content=content,
            notes=notes,
        )

    def _collect(
        self,
        *,
        user_id: str,
        symbol: str | None = None,
        intent: str | None = None,
        outcome_status: str | None = None,
        rule_snapshot_id: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        cursor_key: tuple[str, str] | None = None,
        limit: int | None = 100,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for task in self.db.list_tasks(user_id):
            if cursor_key and (task.created_at, task.id) >= cursor_key:
                continue
            if from_date and task.created_at < from_date:
                continue
            if to_date and task.created_at > to_date:
                continue

            detail = self.db.get_task_detail(task.id, user_id)
            if not detail:
                continue
            decision = detail.get("decision")
            if not decision:
                continue

            target = task.target if isinstance(task.target, dict) else {}
            symbols = self._symbols_from_target(target)
            if symbol and symbol not in symbols:
                continue
            if intent and str(decision.get("status", "")).upper() != intent:
                continue

            decision_rule_snapshot_id = (
                task.rule_snapshot_id
                or self._decision_rule_snapshot_id(decision)
            )
            if rule_snapshot_id and decision_rule_snapshot_id != rule_snapshot_id:
                continue

            retrospectives = list(detail.get("retrospectives") or [])
            if outcome_status and not any(
                self._outcome_status(item) == outcome_status
                for item in retrospectives
            ):
                continue

            item = self._item(task.to_dict(), target, decision, detail, decision_rule_snapshot_id, symbols)
            items.append(item)
            if limit is not None and len(items) >= limit:
                break
        return items

    @staticmethod
    def _normalize_symbol(value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @staticmethod
    def _normalize_intent(value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @staticmethod
    def _normalize_outcome(value: str | None) -> str | None:
        return value.strip().lower() if value else None

    @classmethod
    def _group_patterns(cls, items: list[dict[str, Any]], group_by: str) -> list[dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        for item in items:
            record = item["decision_record"]
            key = (
                str(record.get("intent") or "UNKNOWN")
                if group_by == "intent"
                else str(record.get("rule_snapshot_id") or "UNKNOWN")
            )
            group = groups.setdefault(key, {
                "key": key,
                "sample_size": 0,
                "retrospective_count": 0,
                "comparable_outcome_count": 0,
                "positive_outcome_count": 0,
                "negative_outcome_count": 0,
                "action_counts": {},
                "horizon_counts": {},
                "average_return_pct": None,
                "average_benchmark_return_pct": None,
                "average_excess_return_pct": None,
                "source_task_ids": [],
                "source_rule_snapshot_ids": [],
                "_created_at_values": [],
                "_observed_at_values": [],
                "rule_violation_count": 0,
                "rule_warning_count": 0,
            })
            group["sample_size"] += 1
            task_id = str(record["task"].get("id"))
            group["source_task_ids"].append(task_id)
            created_at = str(record.get("created_at") or record["task"].get("created_at") or "")
            if created_at:
                group["_created_at_values"].append(created_at)
            rule_snapshot_id = str(record.get("rule_snapshot_id") or "").strip()
            if rule_snapshot_id and rule_snapshot_id not in group["source_rule_snapshot_ids"]:
                group["source_rule_snapshot_ids"].append(rule_snapshot_id)
            rationale = record.get("rationale")
            rules = rationale.get("rules") if isinstance(rationale, dict) else {}
            if isinstance(rules, dict):
                group["rule_violation_count"] += len(rules.get("reasons") or [])
                group["rule_warning_count"] += len(rules.get("warnings") or [])
            returns: list[float] = []
            benchmark_returns: list[float] = []
            excess_returns: list[float] = []
            for retrospective in item["retrospectives"]:
                group["retrospective_count"] += 1
                observed_at = str(retrospective.get("observed_at") or "").strip()
                if observed_at:
                    group["_observed_at_values"].append(observed_at)
                action = cls._action_category(retrospective)
                action_counts = group["action_counts"]
                action_counts[action] = action_counts.get(action, 0) + 1
                horizon = str(
                    (retrospective.get("outcome") or {}).get("horizon")
                    or "USER_RECORDED"
                ).upper()
                horizon_counts = group["horizon_counts"]
                horizon_counts[horizon] = horizon_counts.get(horizon, 0) + 1
                return_pct = cls._return_pct(retrospective)
                if return_pct is None:
                    continue
                group["comparable_outcome_count"] += 1
                returns.append(return_pct)
                if return_pct > 0:
                    group["positive_outcome_count"] += 1
                elif return_pct < 0:
                    group["negative_outcome_count"] += 1
                benchmark = cls._benchmark_return_pct(retrospective)
                if benchmark is not None:
                    benchmark_returns.append(benchmark)
                excess = cls._excess_return_pct(retrospective)
                if excess is not None:
                    excess_returns.append(excess)
            if returns:
                existing = group.get("_returns", [])
                existing.extend(returns)
                group["_returns"] = existing
            if benchmark_returns:
                group.setdefault("_benchmark_returns", []).extend(benchmark_returns)
            if excess_returns:
                group.setdefault("_excess_returns", []).extend(excess_returns)
        for group in groups.values():
            returns = group.pop("_returns", [])
            benchmark_returns = group.pop("_benchmark_returns", [])
            excess_returns = group.pop("_excess_returns", [])
            created_at_values = group.pop("_created_at_values", [])
            observed_at_values = group.pop("_observed_at_values", [])
            group["as_of"] = max(created_at_values)[:10] if created_at_values else None
            group["observed_at"] = max(observed_at_values) if observed_at_values else None
            group["average_return_pct"] = round(sum(returns) / len(returns), 4) if returns else None
            group["average_benchmark_return_pct"] = (
                round(sum(benchmark_returns) / len(benchmark_returns), 4)
                if benchmark_returns else None
            )
            group["average_excess_return_pct"] = (
                round(sum(excess_returns) / len(excess_returns), 4)
                if excess_returns else None
            )
        return list(groups.values())

    @staticmethod
    def _action_category(retrospective: dict[str, Any]) -> str:
        action = str(retrospective.get("action_taken") or "OTHER").upper()
        if action == "APPROVE":
            return "TAKEN"
        if action in {"REJECT", "NOT_TAKEN", "NO_ACTION"}:
            return "NOT_TAKEN"
        return "OTHER"

    @staticmethod
    def _return_pct(retrospective: dict[str, Any]) -> float | None:
        outcome = retrospective.get("outcome")
        if not isinstance(outcome, dict):
            return None
        try:
            value = float(outcome.get("return_pct"))
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) else None

    @staticmethod
    def _benchmark_return_pct(retrospective: dict[str, Any]) -> float | None:
        outcome = retrospective.get("outcome")
        if not isinstance(outcome, dict):
            return None
        try:
            value = float(outcome.get("benchmark_return_pct"))
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) else None

    @classmethod
    def _excess_return_pct(cls, retrospective: dict[str, Any]) -> float | None:
        outcome = retrospective.get("outcome")
        if not isinstance(outcome, dict):
            return None
        try:
            value = float(outcome.get("excess_return_pct"))
        except (TypeError, ValueError):
            value = None
        if value is not None and math.isfinite(value):
            return value
        return_pct = cls._return_pct(retrospective)
        benchmark = cls._benchmark_return_pct(retrospective)
        return round(return_pct - benchmark, 6) if return_pct is not None and benchmark is not None else None

    @staticmethod
    def _item(
        task: dict[str, Any],
        target: dict[str, Any],
        decision: dict[str, Any],
        detail: dict[str, Any],
        rule_snapshot_id: str | None,
        symbols: list[str],
    ) -> dict[str, Any]:
        evidence = list(detail.get("evidence") or [])
        qualities = sorted({
            str(row.get("quality"))
            for row in evidence
            if row.get("quality")
        })
        as_of_values = sorted({
            str(row.get("as_of"))
            for row in evidence
            if row.get("as_of")
        })
        retrospective_rows = [
            {
                **row,
                "outcome_status": DecisionJournal._outcome_status(row),
            }
            for row in (detail.get("retrospectives") or [])
        ]
        decision_record = {
            "result_metadata": detail.get("result_metadata"),
            "task": task,
            "subject": {
                "symbols": symbols,
                "symbol": symbols[0] if len(symbols) == 1 else None,
                "target": target,
            },
            "intent": decision.get("status"),
            "rationale": decision.get("rationale"),
            "confidence": decision.get("confidence"),
            "risk_level": decision.get("risk_level"),
            "next_action": decision.get("next_action"),
            "created_at": decision.get("created_at") or task.get("created_at"),
            "rule_snapshot_id": rule_snapshot_id,
            "data_snapshot_id": task.get("data_snapshot_id"),
        }
        return {
            "decision_record": decision_record,
            "retrospectives": retrospective_rows,
            "evidence_summary": {
                "count": len(evidence),
                "qualities": qualities,
                "latest_as_of": as_of_values[-1] if as_of_values else None,
                "ids": [str(row.get("id")) for row in evidence if row.get("id")],
            },
            "approvals": detail.get("approvals") or [],
            "replay_refs": {
                "task_id": task.get("id"),
                "data_snapshot_id": task.get("data_snapshot_id"),
                "rule_snapshot_id": rule_snapshot_id,
            },
        }

    @staticmethod
    def _symbols_from_target(target: dict[str, Any]) -> list[str]:
        values: list[Any] = []
        if target.get("symbol"):
            values.append(target["symbol"])
        if isinstance(target.get("symbols"), list):
            values.extend(target["symbols"])
        return sorted({
            str(value).strip().upper()
            for value in values
            if str(value).strip()
        })

    @staticmethod
    def _decision_rule_snapshot_id(decision: dict[str, Any]) -> str | None:
        rationale = decision.get("rationale")
        rules = rationale.get("rules") if isinstance(rationale, dict) else None
        value = rules.get("rule_snapshot_id") if isinstance(rules, dict) else None
        return str(value) if value else None

    @staticmethod
    def _outcome_status(retrospective: dict[str, Any]) -> str:
        outcome = retrospective.get("outcome")
        if isinstance(outcome, dict):
            status = outcome.get("status")
            if status:
                return str(status).strip().lower()
        return "unknown"

    @staticmethod
    def _encode_cursor(value: tuple[str, str]) -> str:
        raw = f"{value[0]}|{value[1]}".encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(value: str | None) -> tuple[str, str] | None:
        if not value:
            return None
        try:
            padded = value + "=" * (-len(value) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode()).decode()
            created_at, task_id = decoded.split("|", 1)
            datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            return created_at, task_id
        except (ValueError, UnicodeDecodeError):
            raise ValueError("cursor must be a valid journal cursor")
