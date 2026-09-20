"""Tests for the public Laya invocation protocol."""

import pytest
from protocol import InvalidRequestError, validate_request


def test_validate_request_accepts_all_question_types() -> None:
    """Accept one native definition for each Laya question type."""

    request = validate_request(
        {
            "state": {"message": "A customer was charged twice."},
            "questions": {
                "department": {
                    "type": "choice",
                    "instructions": "Which department should handle this?",
                    "criteria": {
                        "billing": "Payments and refunds",
                        "technical": "Product defects",
                    },
                },
                "urgency": {
                    "type": "score",
                    "instructions": "How urgent is this request?",
                    "criteria": ["low", "medium", "high"],
                },
                "requires_refund": {
                    "type": "noul",
                    "instructions": "Does this request require a refund?",
                },
            },
        }
    )

    state, questions = request.as_laya_input()

    assert state == {"message": "A customer was charged twice."}
    assert set(questions) == {"department", "urgency", "requires_refund"}


def test_validate_request_rejects_unknown_fields_without_echoing_input() -> None:
    """Reject unknown fields without including their values in the error."""

    with pytest.raises(InvalidRequestError) as captured:
        validate_request(
            {
                "state": "private customer content",
                "questions": {
                    "valid": {
                        "type": "noul",
                        "instructions": "Is this valid?",
                    }
                },
                "unknown": "sensitive value",
            }
        )

    message = str(captured.value)

    assert "unknown" in message
    assert "private customer content" not in message
    assert "sensitive value" not in message


def test_validate_request_rejects_empty_questions() -> None:
    """Require at least one question for every inference request."""

    with pytest.raises(InvalidRequestError, match="questions"):
        validate_request({"state": "hello", "questions": {}})
