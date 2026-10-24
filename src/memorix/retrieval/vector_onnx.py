"""Optional ONNX embedder adapter (offline, no network).

Requires ``pip install 'mem-patrol[vector]'`` (onnxruntime + numpy) and a model
plus tokenizer callable supplied by the user. This module is imported lazily.
"""
from __future__ import annotations

from typing import Any, Callable, Sequence

from .provider import VectorUnavailableError


class OnnxEmbedder:
    """Mean-pool a model's last hidden state into sentence vectors.

    ``tokenizer(texts) -> dict[input_name, np.ndarray]``; it must return every
    input the ONNX model declares. This adapter deliberately does not bundle a
    model, vocab, or tokenizer.
    """

    def __init__(self, model_path: str, tokenizer: Callable[[Sequence[str]], dict[str, Any]], *, pool: str = "mean") -> None:
        try:
            import numpy as np
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover - optional extra
            raise VectorUnavailableError("install 'mem-patrol[vector]' for ONNX support") from exc
        self._np = np
        self._session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self._tokenizer = tokenizer
        self._pool = pool

    def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        feeds = self._tokenizer(list(texts))
        output = self._session.run(None, feeds)[0]
        array = self._np.asarray(output)
        if array.ndim == 3:
            array = array.mean(axis=1)
        elif array.ndim != 2:
            raise VectorUnavailableError("expected 2D/3D model output, got shape %r" % (array.shape,))
        return array.astype("float32").tolist()
