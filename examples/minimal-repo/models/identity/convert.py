"""Build a trivial ONNX graph that returns its input unchanged.

A conversion script is a plain module with a top-level `convert` function.
The SDK imports this file and calls `convert(**args)` with the `args` map
from model.yaml, after substituting `{output}`, `{temp}`, `{repo}` and
friends in any string value.

A real script loads a checkpoint here and exports it – the shape of the
function is the same either way: read inputs, write ONNX files into the
output directory, return None. Raise to fail the build.
"""

from __future__ import annotations

from pathlib import Path

import onnx
from onnx import TensorProto, helper


def convert(output: str, opset: int = 20, channels: int = 3) -> None:
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Dynamic height/width via symbolic dim names. darktable reads these
    # names from config.json's `spatial_dims`, defaulting to
    # "height"/"width" – which is what we use, so no override is needed.
    shape = ["batch", channels, "height", "width"]
    inp = helper.make_tensor_value_info("input", TensorProto.FLOAT, shape)
    out = helper.make_tensor_value_info("output", TensorProto.FLOAT, shape)

    graph = helper.make_graph(
        nodes=[helper.make_node("Identity", ["input"], ["output"])],
        name="identity",
        inputs=[inp],
        outputs=[out],
    )
    model = helper.make_model(
        graph,
        opset_imports=[helper.make_opsetid("", opset)],
        producer_name="minimal-repo",
    )
    onnx.checker.check_model(model)
    onnx.save(model, str(out_path))

    print(f"    wrote {out_path}")
