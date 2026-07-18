"""Case source. Fixtures today, Person 1's engine tomorrow.

Integration day is: set ENGINE_API_URL=http://localhost:8001 and restart.
Nothing else changes because both sides speak shared_contracts.Case.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

import requests

from config import ENGINE_API_URL, MOCK_CASES_PATH, RED_THRESHOLD, YELLOW_THRESHOLD
from shared_contracts import Case, CaseSummary


class CaseStore:
    def __init__(self):
        self._fixture_cases: Dict[str, Case] = {}
        with open(MOCK_CASES_PATH, encoding="utf-8") as f:
            for raw in json.load(f):
                case = Case.model_validate(raw)
                self._fixture_cases[case.case_id] = case

    @property
    def source(self) -> str:
        return "engine" if ENGINE_API_URL else "fixtures"

    def get_case(self, case_id: str) -> Optional[Case]:
        if ENGINE_API_URL:
            r = requests.get(f"{ENGINE_API_URL}/cases/{case_id}", timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return Case.model_validate(r.json())
        return self._fixture_cases.get(case_id)

    def list_summaries(self, threshold: Optional[float] = None) -> List[CaseSummary]:
        if ENGINE_API_URL:
            r = requests.get(f"{ENGINE_API_URL}/cases", timeout=30)
            r.raise_for_status()
            return [CaseSummary.model_validate(c) for c in r.json()]
        red = threshold if threshold is not None else RED_THRESHOLD
        yellow = red - (RED_THRESHOLD - YELLOW_THRESHOLD)
        out = []
        for c in self._fixture_cases.values():
            band = "RED" if c.risk.p >= red else "YELLOW" if c.risk.p >= yellow else "GREEN"
            out.append(
                CaseSummary(
                    case_id=c.case_id,
                    risk_band=band,  # type: ignore[arg-type]
                    p=c.risk.p,
                    member_count=len(c.member_alert_ids),
                )
            )
        return out
