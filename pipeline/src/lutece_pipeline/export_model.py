"""Export the image model to ONNX, in the forms that the app could carry.

DINOv2 ViT-S/14 (SPEC §6.2) turns a photo into a vector of 384 numbers: two
photos of the same building give close vectors. The step writes the model as
the phone can run it, in three weights: as trained, with numbers on 16 bits,
and with weights on 8 bits. The retrieval evaluation tells what each one costs.

Run with: uv run python -m lutece_pipeline.export_model
"""

import argparse
import hashlib
import json
import logging
import warnings
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import onnx
import torch
from onnxruntime.quantization import QuantType, quantize_dynamic
from onnxruntime.transformers import float16
from transformers import AutoModel

from lutece_pipeline import vision
from lutece_pipeline.paths import PROCESSED_DIR

logger = logging.getLogger(__name__)

MODEL_NAME = "facebook/dinov2-small"
# The weights as published on Hugging Face on the day of the first export.
REVISION = "ed25f3a31f01632728cabb09d1542f84ab7b0056"
OPSET = 17
# Below this, an exported model no longer says what the trained one says.
FAITHFUL = 0.9999

MODELS_FOLDER = PROCESSED_DIR / "models"
MANIFEST = MODELS_FOLDER / "models.json"
FILES = {
    "float32": "dinov2-small.onnx",
    "fp16": "dinov2-small-fp16.onnx",
    "int8": "dinov2-small-int8.onnx",
}


class Embedder(torch.nn.Module):
    """The model as the app needs it: pixels in, a vector of length 1 out."""

    def __init__(self, backbone: torch.nn.Module) -> None:
        super().__init__()
        self.backbone = backbone
        # The trained model works out where the patches are for each photo, by
        # resizing a grid: an operation that the lighter forms of the model get
        # wrong and that a phone runs badly. The photos all have the same
        # size, so it is done once, here.
        patches = backbone.embeddings
        count = (vision.SIDE // backbone.config.patch_size) ** 2
        tokens = torch.zeros(1, 1 + count, backbone.config.hidden_size)
        with torch.no_grad():
            positions = patches.interpolate_pos_encoding(
                tokens, vision.SIDE, vision.SIDE
            )
        self.register_buffer("positions", positions.clone())
        patches.interpolate_pos_encoding = lambda tokens, height, width: self.positions

    def forward(self, pixels: torch.Tensor) -> torch.Tensor:
        # The vector of the whole photo, not those of its patches.
        whole = self.backbone(pixel_values=pixels).pooler_output
        return torch.nn.functional.normalize(whole, dim=-1)


def load_embedder() -> Embedder:
    """Load the trained model, downloading its weights the first time."""
    backbone = AutoModel.from_pretrained(MODEL_NAME, revision=REVISION)
    return Embedder(backbone).eval()


def export_float32(embedder: Embedder, destination: Path) -> None:
    """Write the model as trained, for any number of photos at a time."""
    example = torch.zeros(1, 3, vision.SIDE, vision.SIDE)
    with warnings.catch_warnings():
        # The tracer warns about every branch that depends on the size of the photo.
        warnings.simplefilter("ignore")
        torch.onnx.export(
            embedder,
            (example,),
            str(destination),
            # The exporter that needs nothing more than PyTorch.
            dynamo=False,
            input_names=["pixels"],
            output_names=["embedding"],
            dynamic_axes={"pixels": {0: "batch"}, "embedding": {0: "batch"}},
            opset_version=OPSET,
        )


def to_fp16(source: Path, destination: Path) -> None:
    """Halve the model: numbers on 16 bits inside, pixels and vector unchanged."""
    halved = float16.convert_float_to_float16(onnx.load(source), keep_io_types=True)
    onnx.save(halved, destination)


def to_int8(source: Path, destination: Path) -> None:
    """Quarter the model: the weights of its layers on 8 bits."""
    # The tool reports every tensor that it leaves alone, a thousand lines.
    logging.disable(logging.INFO)
    try:
        quantize_dynamic(source, destination, weight_type=QuantType.QUInt8)
    finally:
        logging.disable(logging.NOTSET)


def probe() -> np.ndarray:
    """Pixels drawn once and for all, to compare what the models say."""
    noise = np.random.default_rng(0).standard_normal((4, 3, vision.SIDE, vision.SIDE))
    return noise.astype(np.float32)


def agreement(expected: np.ndarray, given: np.ndarray) -> float:
    """The least cosine between the vectors that two models give for the same pixels."""
    return float((expected * given).sum(axis=1).min())


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(embedder: Embedder, folder: Path) -> list[dict[str, object]]:
    """Write the three forms of the model and describe each of them."""
    folder.mkdir(parents=True, exist_ok=True)
    paths = {name: folder / file for name, file in FILES.items()}
    export_float32(embedder, paths["float32"])
    to_fp16(paths["float32"], paths["fp16"])
    to_int8(paths["float32"], paths["int8"])

    pixels = probe()
    with torch.no_grad():
        trained = embedder(torch.from_numpy(pixels)).numpy()
    described = []
    for name, path in paths.items():
        given = vision.embed(vision.open_model(path), pixels)
        described.append(
            {
                "name": name,
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": checksum(path),
                "agreement_on_noise": round(agreement(trained, given), 6),
            }
        )
    exact = described[0]["agreement_on_noise"]
    if exact < FAITHFUL:
        raise RuntimeError(f"The exported model differs from the trained one: {exact}")
    return described


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export the image model to ONNX, in three weights."
    )
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    described = export(load_embedder(), MODELS_FOLDER)
    manifest = {"model": MODEL_NAME, "revision": REVISION, "files": described}
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote %d models to %s", len(described), MODELS_FOLDER)
    for model in described:
        logger.info(
            "  %-8s %6.1f MB   agreement with the trained model on noise %.4f",
            model["name"],
            model["bytes"] / 1e6,
            model["agreement_on_noise"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
