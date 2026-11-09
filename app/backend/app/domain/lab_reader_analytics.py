"""Aggregate anonymous page-reader events without clinical content."""
from datetime import datetime


def summarize_reader_events(metadata_rows, *, cutoff, limit):
    events={}
    for metadata in metadata_rows:
        for event in (metadata or {}).get('lab_reader_usage',[]):
            if not isinstance(event,dict) or not event.get('event_id'): continue
            try: recorded=datetime.fromisoformat(event['recorded_at'])
            except (KeyError,TypeError,ValueError): continue
            if recorded.tzinfo is None or recorded<cutoff: continue
            # Never include patient/source text or provider error payloads in admin cost responses.
            from app.domain.consistency_config import READER_ANALYTICS_FIELDS
            events[event['event_id']]={key:event.get(key) for key in READER_ANALYTICS_FIELDS}
    values=sorted(events.values(),key=lambda event:event['recorded_at'],reverse=True)
    costs=[event['estimated_cost_usd'] for event in values if event['estimated_cost_usd'] is not None]
    return {'page_reader_events':len(values),'known_estimated_cost_usd':round(sum(costs),8),
            'unpriced_events':sum(event['estimated_cost_usd'] is None for event in values),
            'input_tokens':sum(event['input_tokens'] or 0 for event in values),
            'output_tokens':sum(event['output_tokens'] or 0 for event in values),'events':values[:limit]}
