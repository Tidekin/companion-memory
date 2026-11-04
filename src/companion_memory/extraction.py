# Generated from Companion Core 30628cff61d6642d6ababf833d6432cd83695c0f; see provenance/upstream.json.
# SPDX-License-Identifier: MIT
# ruff: noqa: E501
import json
from .models import CoreError, Extraction

def short_refs(data):
    """Replace long event/reference IDs in the extractor input with e0/r0, and repeated
    episode groups with g0. Returns (payload, mapping); the model answers in short refs
    and from_refs() restores the real IDs before any validation."""
    refs, groups, mapping = ({}, {}, {})
    for index, item in enumerate(data):
        refs[item['event_id']] = f'e{index}'
        mapping[f'e{index}'] = item['event_id']
    events = []
    for item in data:
        group = tuple(item['episode_source_event_ids'])
        key = None
        if group:
            if group not in groups:
                groups[group] = f'g{len(groups)}'
                mapping[groups[group]] = list(group)
            key = groups[group]
        references = []
        for reference in item['references']:
            ref = f"r{sum((name.startswith('r') for name in mapping))}"
            mapping[ref] = reference['reference_id']
            references.append({'ref': ref, **{k: v for k, v in reference.items() if k != 'reference_id'}})
        events.append({'ref': refs[item['event_id']], 'occurred_at': item['occurred_at'], 'group': key, 'text': item['text'], 'references': references})
    payload = {'groups': {ref: [refs.get(e, e) for e in group] for group, ref in groups.items()}, 'events': events}
    return (payload, mapping)

def from_refs(value, mapping):
    """Real IDs for the short refs an extraction used; unknown values stay unchanged
    and fail the usual evidence checks."""

    def one(ref):
        target = mapping.get(ref, ref)
        return target if isinstance(target, str) else ref
    for item in value.get('memories', []) if isinstance(value, dict) else []:
        if isinstance(item, dict):
            for key in ('evidence_event_id', 'evidence_reference_id'):
                if isinstance(item.get(key), str):
                    item[key] = one(item[key])
    for item in value.get('episode_summaries', []) if isinstance(value, dict) else []:
        if isinstance(item, dict) and isinstance(item.get('source_event_ids'), list):
            ids = []
            for ref in item['source_event_ids']:
                target = mapping.get(ref, ref) if isinstance(ref, str) else ref
                ids += target if isinstance(target, list) else [target]
            item['source_event_ids'] = ids
    for item in value.get('interaction_signals', []) if isinstance(value, dict) else []:
        if isinstance(item, dict) and isinstance(item.get('event_id'), str):
            item['event_id'] = one(item['event_id'])
    return value

def repair_json(text):
    """Close brackets the model left open (e.g. a source list missing its ']').

    Only bracket structure outside strings is touched; nothing is invented, and the
    result still passes the strict schema and every evidence check. None when the
    text is not repairable this way."""
    stack, out, in_string, escaped = ([], [], False, False)
    pairs = {'{': '}', '[': ']'}
    for char in text:
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in pairs:
            stack.append(pairs[char])
        elif char in '}]':
            if char not in stack:
                return None
            while stack and stack[-1] != char:
                out.append(stack.pop())
            stack.pop()
        out.append(char)
    if in_string:
        return None
    out.extend(reversed(stack))
    try:
        return json.loads(''.join(out))
    except ValueError:
        return None

def parse_extraction(text, mapping):
    """(Extraction, repaired) from model text in short refs."""
    try:
        value, repaired = (json.loads(text), False)
    except ValueError:
        value, repaired = (repair_json(text), True)
        if value is None:
            raise
    return (Extraction.model_validate(from_refs(value, mapping)), repaired)

def require_settled(store, request_id):
    usage = store.one('SELECT state FROM model_usage WHERE request_id=?', (request_id,))
    if not usage or usage['state'] != 'SETTLED':
        raise CoreError('MODEL_USAGE_UNRESOLVED', 409)
