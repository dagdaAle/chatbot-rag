"""Server-authored usage; unavailable token counts/costs remain null."""
from contextvars import ContextVar
from contextlib import contextmanager
from time import monotonic, perf_counter
import logging
from app.auth import request_user
from app.core.admin import privileged

operation_context = ContextVar('usage_context', default={})
logger = logging.getLogger(__name__)


_rates: dict = {}
RATE_TTL = 60


def _rate(provider, model):
    """Model tariffs change rarely: cache them instead of one extra query per LLM call."""
    key = (provider, model)
    cached = _rates.get(key)
    if cached and monotonic() - cached[0] < RATE_TTL:
        return cached[1]
    rows = privileged('GET', '/rest/v1/app_models', params={'provider': f'eq.{provider}', 'model_id': f'eq.{model}'})
    _rates[key] = (monotonic(), rows[0] if rows else {})
    return _rates[key][1]


def _safe_record(*args, **kwargs):
    # The provider call already happened (and is billed): an accounting failure must not
    # discard the user's answer. It is logged loudly instead.
    try:
        record(*args, **kwargs)
    except Exception:
        logger.exception('Usage recording failed for %s/%s', args[0], args[1])


def record(provider, model, operation, status, duration_ms, input_tokens=None, output_tokens=None, error_code=None):
    try:
        user = request_user.get()
    except LookupError:
        return  # Offline pure-function tests/jobs have no authenticated caller.
    rate = _rate(provider, model)
    input_rate, output_rate = rate.get('input_per_million'), rate.get('output_per_million')
    cost = None
    if input_tokens is not None and output_tokens is not None and input_rate is not None and output_rate is not None:
        cost = (input_tokens * float(input_rate) + output_tokens * float(output_rate)) / 1_000_000
    privileged('POST', '/rest/v1/usage_events', body={**operation_context.get(), 'user_id': user.id,
        'provider': provider, 'model_id': model, 'operation': operation, 'status': status,
        'input_tokens': input_tokens, 'output_tokens': output_tokens, 'duration_ms': duration_ms,
        'estimated_cost': cost, 'currency': rate.get('currency'), 'input_rate': input_rate, 'output_rate': output_rate,
        'error_code': error_code})


@contextmanager
def measure(provider, model, operation):
    usage = {'input_tokens': None, 'output_tokens': None}
    started = perf_counter()
    try:
        yield usage
    except Exception as exc:
        _safe_record(provider, model, operation, 'error', int((perf_counter()-started)*1000), error_code=type(exc).__name__)
        raise
    else:
        _safe_record(provider, model, operation, 'success', int((perf_counter()-started)*1000), **usage)
