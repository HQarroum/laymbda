"""Validate Lambda events against Laya's native prediction protocol."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

type LayaState = str | dict[str, JsonValue] | list[JsonValue]
type ChoiceCriteria = Annotated[
    dict[str, JsonValue] | list[str],
    Field(min_length=1),
]
type ScoreCriteria = Annotated[list[JsonValue], Field(min_length=1)]
type NoulCriteria = dict[Literal["false", "true"], JsonValue]


class WireModel(BaseModel):
    """Base model for strict, immutable request objects."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ChoiceQuestion(WireModel):
    """Select one label from a set of named alternatives."""

    type: Literal["choice"]
    instructions: JsonValue
    criteria: ChoiceCriteria


class ScoreQuestion(WireModel):
    """Place the state on an ordered scale."""

    type: Literal["score"]
    instructions: JsonValue
    criteria: ScoreCriteria


class NoulQuestion(WireModel):
    """Estimate the probability that a statement is true."""

    type: Literal["noul"]
    instructions: JsonValue
    criteria: NoulCriteria | None = None


type LayaQuestion = Annotated[
    ChoiceQuestion | ScoreQuestion | NoulQuestion,
    Field(discriminator="type"),
]


class InferenceRequest(WireModel):
    """A validated call to ``laya.Agent.predict``."""

    state: LayaState
    questions: dict[str, LayaQuestion] = Field(min_length=1)

    def as_laya_input(
        self,
    ) -> tuple[LayaState, dict[str, dict[str, Any]]]:
        """Convert the validated request into Laya's native input objects.

        Returns:
            A pair containing the state and question mapping accepted by
            ``laya.Agent.predict``.
        """

        questions = {
            question_id: question.model_dump(mode="json")
            for question_id, question in self.questions.items()
        }
        return self.state, questions


class InvalidRequestError(ValueError):
    """Raised when an invocation does not match Laya's input protocol."""


def validate_request(event: object) -> InferenceRequest:
    """Validate an untrusted Lambda event against the Laya protocol.

    Args:
        event: Raw event supplied to the Lambda function.

    Returns:
        The validated and typed inference request.

    Raises:
        InvalidRequestError: If the event does not match Laya's input format.
    """

    try:
        return InferenceRequest.model_validate(event)
    except ValidationError as error:
        details = "; ".join(
            _format_validation_error(item)
            for item in error.errors(
                include_input=False,
                include_url=False,
            )
        )
        raise InvalidRequestError(f"Invalid Laya request: {details}") from None


def _format_validation_error(error: dict[str, Any]) -> str:
    """Render a validation error without exposing request data.

    Args:
        error: Structured validation error produced by Pydantic.

    Returns:
        A concise message containing the invalid field and failure reason.
    """

    path = ".".join(str(part) for part in error["loc"]) or "request"
    return f"{path}: {error['msg']}"
