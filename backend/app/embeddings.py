"""Sentence embeddings with multilingual-e5-small, run locally through ONNX Runtime.

Why this model: free, runs on a laptop CPU, 384-dimensional vectors, and it was
trained on ~100 languages including Tamil, so the same index will serve the
Tamil milestone later. Why ONNX Runtime instead of PyTorch: a ~15 MB install
instead of hundreds of MB, and the same numerical model.

E5 models expect a prefix: "query: " for the user's question and "passage: "
for the stored text. Vectors are mean-pooled over tokens and L2-normalised,
so cosine similarity is a plain dot product.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import numpy as np

from .config import REPO_ROOT, settings

EMBED_DIM = 384
MODEL_NAME = "multilingual-e5-small"
# Official repo first; Xenova's is the same model exported to ONNX, used only if the first has no ONNX file.
MODEL_REPOS = ("intfloat/multilingual-e5-small", "Xenova/multilingual-e5-small")
MODEL_FILES = ["onnx/model.onnx", "tokenizer.json", "config.json"]
MAX_TOKENS = 512


class ModelMissingError(RuntimeError):
    pass


class Embedder(Protocol):
    name: str

    def embed_queries(self, texts: list[str]) -> np.ndarray: ...
    def embed_passages(self, texts: list[str]) -> np.ndarray: ...


def model_dir() -> Path:
    return Path(settings.embedding_model_dir) if settings.embedding_model_dir else REPO_ROOT / "models" / MODEL_NAME


def download_model() -> dict:
    """Fetch the model files from Hugging Face into models/ (≈490 MB, once)."""
    from huggingface_hub import HfApi, hf_hub_download

    target = model_dir()
    api = HfApi()
    errors = []
    for repo in MODEL_REPOS:
        try:
            info = api.model_info(repo)
            names = {s.rfilename for s in info.siblings}
            if not all(f in names for f in MODEL_FILES):
                errors.append(f"{repo}: missing {[f for f in MODEL_FILES if f not in names]}")
                continue
            for f in MODEL_FILES:
                hf_hub_download(repo, f, revision=info.sha, local_dir=target)
            source = {"repo": repo, "revision": info.sha, "files": MODEL_FILES}
            (target / "MODEL_SOURCE.json").write_text(json.dumps(source, indent=2), encoding="utf-8")
            return source
        except Exception as exc:  # network error, repo layout changed, ...
            errors.append(f"{repo}: {exc}")
    raise ModelMissingError("could not download the embedding model:\n  " + "\n  ".join(errors))


def model_source() -> dict | None:
    path = model_dir() / "MODEL_SOURCE.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


class E5Embedder:
    name = MODEL_NAME

    def __init__(self, directory: Path):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        onnx_path, tok_path = directory / "onnx" / "model.onnx", directory / "tokenizer.json"
        if not onnx_path.exists() or not tok_path.exists():
            raise ModelMissingError(f"embedding model not found in {directory}. Run: python -m app.embed")
        self.tokenizer = Tokenizer.from_file(str(tok_path))
        self.tokenizer.enable_truncation(MAX_TOKENS)
        self.tokenizer.enable_padding()
        self.session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        self.input_names = {i.name for i in self.session.get_inputs()}

    def _embed(self, texts: list[str]) -> np.ndarray:
        enc = self.tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        feeds = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.input_names:
            feeds["token_type_ids"] = np.zeros_like(ids)
        hidden = self.session.run(None, feeds)[0]  # (batch, tokens, 384)
        summed = (hidden * mask[:, :, None]).sum(axis=1)
        pooled = summed / np.clip(mask.sum(axis=1, keepdims=True), 1, None)
        return pooled / np.linalg.norm(pooled, axis=1, keepdims=True)

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        return self._embed([f"query: {t}" for t in texts])

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._embed([f"passage: {t}" for t in texts])


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Loaded once per process (about a second); tests replace it with a fake."""
    return E5Embedder(model_dir())
