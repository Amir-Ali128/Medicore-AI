"""Context-local reader telemetry; no prompt, image, patient or filename is logged."""
from contextvars import ContextVar
from app.domain import consistency_config as cfg

reader_calls = ContextVar('lab_reader_calls', default=None)


def record_response_usage(provider, model, response):
    calls = reader_calls.get()
    if calls is None: return
    usage = getattr(response,'usage',None)
    def integer(key):
        raw = usage.get(key) if isinstance(usage,dict) else getattr(usage,key,None)
        return raw if isinstance(raw,int) and not isinstance(raw,bool) and raw>=0 else None
    inputs,outputs=integer('input_tokens'),integer('output_tokens')
    cached = integer('cache_read_input_tokens') or integer('cache_creation_input_tokens') or 0
    details = getattr(usage,'input_tokens_details',None)
    cached += (details.get('cached_tokens',0) if isinstance(details,dict) else getattr(details,'cached_tokens',0)) or 0
    prices=cfg.READER_PRICES_PER_MILLION_USD.get(model)
    cost=(inputs*prices[0]+outputs*prices[1])/cfg.TOKEN_PRICE_DIVISOR if prices and inputs is not None and outputs is not None and not cached else None
    calls.append({'provider':provider,'model':model,'input_tokens':inputs,'output_tokens':outputs,
                  'estimated_cost_usd':round(cost,8) if cost is not None else None,
                  'cost_status':'estimated' if cost is not None else 'pricing_or_usage_unavailable'})


def summarize_calls(calls, *, local=False):
    def total(key):
        values=[call.get(key) for call in calls]
        return sum(values) if values and all(value is not None for value in values) else (0 if local else None)
    return {'calls':calls,'input_tokens':total('input_tokens'),'output_tokens':total('output_tokens'),
            'estimated_cost_usd':total('estimated_cost_usd'),
            'cost_status':'local_no_api_cost' if local else 'estimated' if calls and all(call['estimated_cost_usd'] is not None for call in calls) else 'pricing_or_usage_unavailable'}
