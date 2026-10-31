"""One parsing recovery per semantic stage; no transport or SDK retry loops."""
import asyncio
import json
from time import monotonic
from typing import Any, Callable, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from .records import Diagnostics, EvidenceError, ModelOutputError

T = TypeVar('T')
MODEL_TIMEOUT_SECONDS = 40
MAX_MODEL_CALLS = 6


class ModelGateway:
    def __init__(self, model: Any, diagnostics: Diagnostics, *, config: dict | None = None):
        self.model = model
        self.diagnostics = diagnostics
        self.config = config or {}

    async def structured(self, prompt: str, payload: dict, schema: type,
                         validator: Callable[[Any], T]) -> T:
        system = prompt + '\nReturn JSON only, matching this schema:\n' + json.dumps(schema.model_json_schema())
        messages = [SystemMessage(content=system), HumanMessage(content=json.dumps(payload, default=str))]
        for attempt in range(2):
            if self.diagnostics.model_calls >= MAX_MODEL_CALLS:
                raise ModelOutputError('Point 14 model call budget exhausted')
            self.diagnostics.model_calls += 1
            start = monotonic()
            try:
                response = await asyncio.wait_for(
                    self.model.ainvoke(messages, config=self.config), MODEL_TIMEOUT_SECONDS)
            finally:
                self.diagnostics.model_latency_seconds += monotonic() - start
            usage = getattr(response, 'usage_metadata', None) or {}
            for key, value in usage.items():
                if type(value) is int:
                    self.diagnostics.usage[key] = self.diagnostics.usage.get(key, 0) + value
            try:
                proposal = schema.model_validate_json(response.content)
                return validator(proposal)
            except (ValidationError, EvidenceError, TypeError) as exc:
                # Only finite local codes enter repair instructions, never raw output.
                allowed = {'incomplete_claim_matching', 'unknown_fact_reference',
                           'incomplete_event_coverage', 'unknown_claim_reference',
                           'unsupported_numeric_value', 'unsupported_numeric_unit',
                           'non_numeric_numeric_value', 'unsupported_qualitative_text',
                           'unsupported_definition_quote', 'unsupported_assertion_span', 'unsupported_qualifier',
                           'incompatible_qualitative_numeric_value'}
                code = str(exc) if isinstance(exc, EvidenceError) and str(exc) in allowed else (
                    'schema_mismatch' if isinstance(exc, ValidationError) else 'grounding_mismatch')
                self.diagnostics.validation_rejections.append(code)
                if attempt:
                    raise ModelOutputError('Invalid structured evidence after one recovery') from exc
                self.diagnostics.parsing_retries += 1
                # Never echo arbitrary provider output or tool text into instructions.
                messages.append(HumanMessage(content=(
                    f'The previous candidate failed validation ({code}). Re-extract from '
                    'the ORIGINAL evidence. Use exact quotations, correct periods, and supplied '
                    'evidence IDs only; do not add fields or numbers. '
                    'Use qualitative_text for quoted descriptions and value_text only for a copied numeric token. '
                    'Do not combine a qualitative assertion with a numeric value. '
                    'Keep unsupported definitions unknown; never invent definition wording. '
                    'This is the only recovery.')))
        raise AssertionError('Unreachable')
