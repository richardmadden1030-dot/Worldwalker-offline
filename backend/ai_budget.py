"""Request-local reservation budget shared by every model role in one turn.

Estimates are conservative reservations, not an exact billing meter. Failed
requests retain their reservation. No global mutable budget is shared with
another player's turn or background work.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import math


class AIBudgetError(RuntimeError):
    pass


@dataclass
class Budget:
    cost_limit: float = 0.0
    retry_limit: int = 2
    reserved: float = 0.0
    retries: int = 0

    def reserve(self, estimate):
        if estimate is None:
            if self.cost_limit:
                raise AIBudgetError("This model's price is unknown, so Worldwalker cannot enforce the configured estimated turn budget. Choose a priced model or explicitly disable that limit.")
            return
        if not math.isfinite(estimate) or estimate < 0:
            raise AIBudgetError("The AI request cost estimate is invalid.")
        if self.cost_limit and self.reserved + estimate > self.cost_limit + 1e-12:
            raise AIBudgetError("This turn reached its estimated AI budget before another request could be sent. The turn can be retried with a different model, shorter output, or a higher limit.")
        self.reserved += estimate

    def retry(self):
        if self.retries >= self.retry_limit:
            raise AIBudgetError("This turn reached its automatic repair limit. No further AI request was sent. Review the reported error before retrying the turn.")
        self.retries += 1


_current = ContextVar("worldwalker_turn_budget", default=None)


@contextmanager
def turn_budget(cost_limit=0.0, retry_limit=2):
    if _current.get() is not None:
        yield _current.get()
        return
    limit = float(cost_limit or 0)
    retries = int(retry_limit)
    if not math.isfinite(limit) or limit < 0 or not 0 <= retries <= 5:
        raise AIBudgetError("The turn budget settings are invalid.")
    value = Budget(limit, retries)
    token = _current.set(value)
    try:
        yield value
    finally:
        _current.reset(token)


def reserve(estimate):
    if _current.get() is not None:
        _current.get().reserve(estimate)


def consume_retry():
    if _current.get() is not None:
        _current.get().retry()
