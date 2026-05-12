"""Interview phase — stateless decision tree over the discovery snapshot."""

from dng_preflight.interview.engine import AnswersProvider, run
from dng_preflight.interview.questions import (
    DEPLOYMENT_SCOPE,
    IDP,
    INTERNAL_DNS,
    LOAD_BALANCER,
    ORDERED_QUESTIONS,
    PUBLIC_HOSTNAME,
    SEED_APPS,
    TLS_STRATEGY,
    WILDCARD_CERT,
    Choice,
    Question,
    QuestionKind,
)

__all__ = [
    "DEPLOYMENT_SCOPE",
    "IDP",
    "INTERNAL_DNS",
    "LOAD_BALANCER",
    "ORDERED_QUESTIONS",
    "PUBLIC_HOSTNAME",
    "SEED_APPS",
    "TLS_STRATEGY",
    "WILDCARD_CERT",
    "AnswersProvider",
    "Choice",
    "Question",
    "QuestionKind",
    "run",
]
