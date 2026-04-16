"""YAML round-trip tests for all 5 committed recipes.

Pillar 3 (D-11c): verifies that loading and dumping a recipe with the
runner's ruamel YAML configuration produces byte-identical output.
This guarantees that --write-back (which round-trips the file) does not
introduce spurious diffs.
"""
import io
import pytest
from pathlib import Path

RECIPE_DIR = Path(__file__).parent.parent.parent / "recipes"
RECIPE_FILES = sorted(RECIPE_DIR.glob("*.yaml"))


@pytest.mark.parametrize(
    "recipe_path",
    RECIPE_FILES,
    ids=lambda p: p.stem,
)
def test_yaml_roundtrip_is_lossless(recipe_path, yaml_rt):
    """Load a recipe with ruamel round-trip, dump it back, compare byte-for-byte.

    Uses the exact same YAML configuration as the runner (yaml_rt fixture from
    conftest.py) so null representation, indentation, and quote preservation
    all match.
    """
    original = recipe_path.read_text()
    data = yaml_rt.load(original)
    buf = io.StringIO()
    yaml_rt.dump(data, buf)
    roundtripped = buf.getvalue()
    assert roundtripped == original, (
        f"Round-trip mismatch for {recipe_path.name}.\n"
        f"First difference at char {_first_diff(original, roundtripped)}"
    )


def _first_diff(a: str, b: str) -> int:
    """Return the index of the first character difference."""
    for i, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            return i
    return min(len(a), len(b))
