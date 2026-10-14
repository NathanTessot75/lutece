import json
from pathlib import Path

import onnx
import pytest
import torch
from transformers import Dinov2Model

from lutece_pipeline import export_model, vision


def test_positions_of_the_patches_are_computed_once(
    small_embedder: export_model.Embedder,
) -> None:
    pixels = torch.from_numpy(export_model.probe())
    # The same weights, left to work out the positions for each photo.
    plain = Dinov2Model(small_embedder.backbone.config).eval()
    plain.load_state_dict(small_embedder.backbone.state_dict())
    with torch.no_grad():
        whole = plain(pixel_values=pixels).pooler_output
        expected = torch.nn.functional.normalize(whole, dim=-1)
        given = small_embedder(pixels)
    assert given.shape == (4, vision.DIMENSIONS)
    assert torch.linalg.norm(given, dim=1) == pytest.approx([1.0] * 4, abs=1e-5)
    assert (expected * given).sum(dim=1).min() > 0.9999


def test_model_is_exported_in_three_weights(exported_models: Path) -> None:
    sizes = {
        name: (exported_models / file).stat().st_size
        for name, file in export_model.FILES.items()
    }
    assert sizes["float32"] > 1.8 * sizes["fp16"]
    assert sizes["fp16"] > 1.5 * sizes["int8"]

    graph = onnx.load(exported_models / export_model.FILES["float32"]).graph
    assert [value.name for value in graph.input] == ["pixels"]
    assert [value.name for value in graph.output] == ["embedding"]
    # Resizing the grid of positions is what the lighter forms get wrong.
    assert "Resize" not in {node.op_type for node in graph.node}

    pixels = export_model.probe()
    vectors = {
        name: vision.embed(vision.open_model(exported_models / file), pixels)
        for name, file in export_model.FILES.items()
    }
    assert vectors["float32"].shape == (4, vision.DIMENSIONS)
    assert export_model.agreement(vectors["float32"], vectors["fp16"]) > 0.999
    assert export_model.agreement(vectors["float32"], vectors["int8"]) > 0.8
    # Any number of photos at a time gives the same vectors.
    alone = vision.embed(
        vision.open_model(exported_models / "dinov2-small.onnx"), pixels[:1]
    )
    assert export_model.agreement(vectors["float32"][:1], alone) > 0.9999


def test_models_are_described_in_a_manifest(
    small_embedder: export_model.Embedder,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(export_model, "load_embedder", lambda: small_embedder)
    monkeypatch.setattr(export_model, "MODELS_FOLDER", tmp_path)
    monkeypatch.setattr(export_model, "MANIFEST", tmp_path / "models.json")
    assert export_model.main([]) == 0

    manifest = json.loads((tmp_path / "models.json").read_text())
    assert manifest["model"] == "facebook/dinov2-small"
    assert manifest["revision"] == export_model.REVISION
    assert [model["name"] for model in manifest["files"]] == ["float32", "fp16", "int8"]
    for model in manifest["files"]:
        path = tmp_path / model["file"]
        assert model["bytes"] == path.stat().st_size
        assert model["sha256"] == export_model.checksum(path)
    assert manifest["files"][0]["agreement_on_noise"] > 0.9999


def test_export_that_changes_what_the_model_says_is_refused(
    small_embedder: export_model.Embedder,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(export_model, "FAITHFUL", 1.01)
    with pytest.raises(RuntimeError, match="differs from the trained one"):
        export_model.export(small_embedder, tmp_path)
