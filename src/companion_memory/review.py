# Generated from Companion Core 30628cff61d6642d6ababf833d6432cd83695c0f; see provenance/upstream.json.
# SPDX-License-Identifier: MIT
# ruff: noqa: E501
import json
from .models import CoreError, MemoryReview

class MemoryReviewError(CoreError):
    """Settled review feedback, consumed only by the original bounded checkpoint."""

    def __init__(self, reason, issues=()):
        self.feedback = {'reason': reason, 'issues': list(issues)}
        self.reextract = bool(issues)
        super().__init__('MEMORY_REVIEW_DISAGREEMENT' if issues else 'MEMORY_REVIEW_INVALID', 502)

def _repair_matches(original, candidate):
    quote = original['evidence_quote']
    return original['evidence_event_id'] == candidate.evidence_event_id and original.get('evidence_reference_id') == candidate.evidence_reference_id and (original['subject'] == candidate.subject) and (original['kind'] == candidate.kind) and (quote in candidate.evidence_quote or candidate.evidence_quote in quote)

def resolve_review(text, candidates, catalog, *, repair_candidates=(), audit=None, clock=None, request_id='reference-review'):
    """Apply native relation consistency checks to already source-validated candidates."""
    audit = audit or (lambda *args, **kwargs: None)
    clock = clock or (lambda: '')
    validation_reason = 'schema'
    disagreements = []
    try:
        value = json.loads(text)
        if isinstance(value, dict) and isinstance(value.get('relations'), list):
            for relation in value['relations']:
                if not isinstance(relation, dict):
                    continue
                if isinstance(relation.get('same'), list) and len(relation['same']) == 1 and isinstance(relation['same'][0], str):
                    relation['same'] = relation['same'][0]
                for field in ('conflicts', 'replaces'):
                    if isinstance(relation.get(field), list):
                        relation[field] = [item['ref'] if isinstance(item, dict) and set(item) == {'ref'} else item for item in relation[field]]
        review = MemoryReview.model_validate(value)
        if len(review.relations) != len(candidates):
            validation_reason = 'relation_count'
            raise ValueError('relation count mismatch')
        resolutions, supported, positions = ([], [], {})
        for i, relation in enumerate(review.relations):
            unsupported_replacement = relation.claims_replacement and (not relation.update_authorized)
            if bool(candidates[i].update) != relation.update_authorized or unsupported_replacement:
                disagreements.append({'candidate': f'c{i}', 'reason': 'unsupported_replacement_claim' if unsupported_replacement else 'update_marker_mismatch', 'expected_update': 'replaces_previous' if relation.update_authorized else None})
                continue
            if not relation.supported:
                if any((_repair_matches(original, candidates[i]) for original in repair_candidates)):
                    disagreements.append({'candidate': f'c{i}', 'reason': 'repair_candidate_rejected', 'expected_update': candidates[i].update})
                    continue
                audit('memory.candidate_rejected', candidates[i].evidence_event_id, 'memory', clock(), reason='UNSUPPORTED_MEMORY_CLAIM')
                continue
            refs = ([relation.same] if relation.same else []) + relation.conflicts
            if len(refs) != len(set(refs)):
                validation_reason = 'duplicate_relation'
                raise ValueError('duplicate relation')
            if len(set(relation.replaces)) != len(relation.replaces) or not set(relation.replaces) <= set(relation.conflicts) or (relation.replaces and (not relation.update_authorized)):
                validation_reason = 'invalid_replacement'
                raise ValueError('invalid replacement relation')
            allowed = {**catalog, **{f'c{j}': {'subject': candidates[j].subject, 'origin': 'event_observed' if candidates[j].evidence_reference_id else 'model_inferred'} for j in positions}}
            if any((ref not in allowed or allowed[ref]['subject'] != candidates[i].subject or (allowed[ref]['origin'] == 'event_observed') != bool(candidates[i].evidence_reference_id) for ref in refs)):
                validation_reason = 'invalid_reference'
                raise ValueError('invalid memory reference')
            if relation.update_authorized and relation.conflicts and (not relation.replaces):
                validation_reason = 'missing_replacement_target'
                raise ValueError('authorized update cannot leave every conflicting target current')

            def resolve(ref):
                return catalog[ref]['memory_id'] if ref in catalog else f'c{positions[int(ref[1:])]}' if ref else None
            positions[i] = len(supported)
            supported.append(candidates[i])
            resolutions.append({'same': resolve(relation.same) if relation.same else None, 'conflicts': [resolve(ref) for ref in relation.conflicts], 'replaces': [resolve(ref) for ref in relation.replaces]})
        if disagreements:
            validation_reason = 'update_disagreement'
            raise ValueError('extractor and source review disagree on update authorization')
        return (supported, resolutions)
    except ValueError as error:
        audit('memory.review_invalid', request_id, 'memory', clock(), reason=validation_reason)
        raise MemoryReviewError(validation_reason, disagreements) from error
