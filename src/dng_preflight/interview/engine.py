"""Stateless interview decision tree.

`run()` walks the ordered question list, defers to an injectable
`answers_provider` callable for each applicable question, and assembles the
results into an `InterviewAnswers` instance. The engine is synchronous because
the only thing it ever waits on is the provider (which, for the CLI, is the
`questionary` prompt; for tests, it's a canned lambda).

The provider sees the question, the current snapshot, and the computed default
(if any). It returns the user's answer. The engine validates the answer
against the question and stores it in the running `prior` dict before moving
to the next question.

When `applies_when(snapshot, prior)` returns False, the engine skips the
prompt entirely and adopts `default_from(...)` as the answer — this is the
single mechanism behind "question skipped, value forced" (wildcard cert when
scope is RDP/SMB).
"""

from collections.abc import Callable, Mapping

from dng_preflight.interview.questions import ORDERED_QUESTIONS, Question
from dng_preflight.models.answers import InterviewAnswers
from dng_preflight.models.snapshot import EnvironmentSnapshot

AnswersProvider = Callable[[Question, EnvironmentSnapshot, object, Mapping[str, object]], object]
"""Callable invoked once per applicable question.

Signature: `(question, snapshot, default, prior) -> answer`. The provider
receives the question, the discovery snapshot, the engine-computed default
value (may be None), and a read-only mapping of all answers already
collected (keyed by question id). It returns the user's answer in the shape
the question expects — e.g. an `ExistingBundle` for `tls_strategy`, a
`LoadBalancerConfig | None` for `load_balancer`.

Per-question `validate_answer` runs immediately after the provider returns;
final pydantic validation runs once on the assembled `InterviewAnswers`.
"""


def run(snapshot: EnvironmentSnapshot, answers_provider: AnswersProvider) -> InterviewAnswers:
    """Run the interview against a snapshot using the given provider.

    Raises `ValueError` if any answer fails its question's validator and
    `pydantic.ValidationError` if the assembled answer set fails
    `InterviewAnswers` validation (which catches discriminator and
    cross-field shape issues the per-question validators cannot).
    """
    prior: dict[str, object] = {}
    for question in ORDERED_QUESTIONS:
        default = question.default_from(snapshot, prior)
        if not question.applies_when(snapshot, prior):
            answer = default
        else:
            answer = answers_provider(question, snapshot, default, prior)
        question.validate_answer(answer, snapshot, prior)
        prior[question.id] = answer
    return InterviewAnswers.model_validate(prior)
