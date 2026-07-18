"""
Constrained-decoding schema for the investigation output.

Ollama compiles this JSON schema into a llama.cpp decoding grammar, so the
model *physically cannot* emit a gos_tag outside GOS_TAGS or skip the
evidence-first ordering — invalid tokens are masked before sampling, not
filtered after. This replaces the hand-written GBNF file from the original
spec with the same guarantee (see change.md).

Property order matters: llama.cpp's schema->grammar conversion emits required
properties in declaration order, which structurally enforces
evidence -> pattern -> sufficiency -> conclusion -> gos_tag -> narration.
The model must restate its evidence before it is allowed to conclude.
"""

# Closed FIU-IND-style Ground-of-Suspicion dictionary (curated demo subset).
GOS_TAGS = [
    "STRUCTURING_TO_AVOID_REPORTING_THRESHOLD",
    "SMURFING_DISPERSED_SMALL_CREDITS",
    "LAYERING_THROUGH_MULTIPLE_ACCOUNTS",
    "ROUND_TRIPPING_CIRCULAR_FLOW",
    "USE_OF_SHELL_OR_CONNECTED_ENTITIES",
    "TRANSACTIONS_INCONSISTENT_WITH_CUSTOMER_PROFILE",
    "UNEXPLAINED_SUDDEN_INCREASE_IN_ACTIVITY",
    "NO_ECONOMIC_RATIONALE",
]

RECOMMENDED_ACTIONS = [
    "FILE_STR_WITH_FIU_IND",
    "ENHANCED_DUE_DILIGENCE_AND_MONITOR",
    "REQUEST_ADDITIONAL_DOCUMENTS",
    "NO_ACTION_CLOSE_ALERT",
]

INVESTIGATION_SCHEMA = {
    "type": "object",
    "properties": {
        "evidence_assessment": {
            "type": "array",
            "minItems": 3,
            "maxItems": 12,
            "items": {
                "type": "object",
                "properties": {
                    "ev_id": {"type": "string"},
                    "observation": {"type": "string"},
                },
                "required": ["ev_id", "observation"],
                "additionalProperties": False,
            },
        },
        "behaviour_pattern": {"type": "string"},
        "evidence_sufficiency": {
            "type": "string",
            "enum": ["SUFFICIENT", "INSUFFICIENT"],
        },
        "investigation_summary": {"type": "string"},
        "suggested_questions": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {"type": "string"},
        },
        "gos_tag": {"type": "string", "enum": GOS_TAGS},
        "narration": {
            "type": "array",
            "minItems": 4,
            "maxItems": 8,
            "items": {"type": "string"},
        },
        "amounts_cited": {
            "type": "array",
            "items": {"type": "number"},
        },
        "recommended_action": {"type": "string", "enum": RECOMMENDED_ACTIONS},
    },
    "required": [
        "evidence_assessment",
        "behaviour_pattern",
        "evidence_sufficiency",
        "investigation_summary",
        "suggested_questions",
        "gos_tag",
        "narration",
        "amounts_cited",
        "recommended_action",
    ],
    "additionalProperties": False,
}
