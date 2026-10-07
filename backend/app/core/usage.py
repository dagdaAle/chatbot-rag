"""Server-authored usage; unavailable token counts/costs remain null."""
from contextvars import ContextVar
from contextlib import contextmanager
from time import perf_counter
import logging
from app.auth import request_user
from app.core.admin import privileged

operation_context = ContextVar('usage_context', default={})
logger = logging.getLogger(__name__)


def record(provider, model, operation, status, duration_ms, input_tokens=None, output_tokens=None, error_code=None):
    try:
        user = request_user.get()
    except LookupError:
        return  # Offline pure-function tests/jobs have no authenticated caller.
    rate_rows = privileged('GET', '/rest/v1/app_models', params={'provider': f'eq.{provider}', 'model_id': f'eq.{model}'})
    rate = rate_rows[0] if rate_rows else {}
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
        try:
            record(provider, model, operation, 'error', int((perf_counter()-started)*1000), error_code=type(exc).__name__)
        except Exception:
            logger.error('Usage recording failed for provider operation')
        raise
    else:
        # Accounting failures are visible, never silently discard successful billable work.
        record(provider, model, operation, 'success', int((perf_counter()-started)*1000), **usage)
