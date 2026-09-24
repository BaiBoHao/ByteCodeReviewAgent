class ReviewAgentError(Exception):
    """Base exception for expected, user-facing failures."""


class ConfigurationError(ReviewAgentError):
    """Raised when required configuration is missing or unsafe."""


class SourceError(ReviewAgentError):
    """Raised when a review source cannot be loaded safely."""


class BudgetExceeded(ReviewAgentError):
    """Raised before an LLM request that would exceed the run budget."""


class ModelResponseError(ReviewAgentError):
    """Raised when the model response is unavailable or malformed."""


class RunNotFound(ReviewAgentError):
    """Raised when a requested run does not exist."""


class RunExecutionError(ReviewAgentError):
    """Raised after a run has been checkpointed as failed."""

    def __init__(self, run_id: str, message: str) -> None:
        self.run_id = run_id
        super().__init__(
            f"run {run_id} failed: {message}; resume with `review-agent resume {run_id}`"
        )
