"""Deterministic model adapters for an operational local development stack."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import AsyncIterator, Sequence


class LocalEmbeddingModel:
    """Produce stable normalized vectors without downloading a model."""

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def encode(
        self,
        sentences: Sequence[str],
        *,
        normalize_embeddings: bool = True,
    ) -> list[list[float]]:
        """Encode text with a deterministic signed feature hash."""
        return [
            self._encode_sentence(sentence, normalize=normalize_embeddings)
            for sentence in sentences
        ]

    def _encode_sentence(self, sentence: str, *, normalize: bool) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[a-z0-9]+", sentence.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0 if digest[4] & 1 else -1.0
        if normalize:
            norm = math.sqrt(sum(value * value for value in vector))
            if norm:
                vector = [value / norm for value in vector]
        return vector


class LocalRerankerModel:
    """Score query/passage pairs by deterministic lexical overlap."""

    def predict(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        """Return overlap scores in input order."""
        return [self._score(query, passage) for query, passage in pairs]

    @staticmethod
    def _score(query: str, passage: str) -> float:
        query_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
        passage_tokens = set(re.findall(r"[a-z0-9]+", passage.lower()))
        if not query_tokens:
            return 0.0
        return len(query_tokens & passage_tokens) / len(query_tokens)


class LocalGroundedLLMClient:
    """Return deterministic, citation-bound text for local workflow validation."""

    provider_name = "local_demo"

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
    ) -> str:
        """Generate query-understanding JSON or a grounded cited response."""
        if "Return compact JSON with keys" in prompt:
            query = prompt.rsplit("User query:", maxsplit=1)[-1].strip()
            return json.dumps(
                {
                    "rewritten_query": query,
                    "intent": "question",
                    "entities": {},
                }
            )

        evidence = self._evidence(prompt)
        if not evidence:
            return "The available FDA guidance evidence is insufficient."
        statements = [
            f"{self._concise_passage(passage)} {citation}" for citation, passage in evidence[:2]
        ]
        return " ".join(statements)

    async def stream(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """Yield the deterministic response as one chunk."""
        yield await self.generate(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stop_sequences=stop_sequences,
        )

    @staticmethod
    def _evidence(prompt: str) -> list[tuple[str, str]]:
        blocks = re.findall(
            r"(?ms)^(\[\d+\]) [^\n]+\n.*?^Passage: (.*?)(?=\n\n\[\d+\] |\n\nReturn |\Z)",
            prompt,
        )
        return [
            (citation, " ".join(passage.split())) for citation, passage in blocks if passage.strip()
        ]

    @staticmethod
    def _concise_passage(passage: str) -> str:
        normalized = re.sub(r"^\d+\s+", "", passage.strip())
        sentences = re.split(r"(?<=[.!?])\s+", normalized)
        return next((sentence for sentence in sentences if len(sentence) >= 40), sentences[0])
