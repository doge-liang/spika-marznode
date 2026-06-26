"""Single-source-of-truth guard (per-repo): the two primary node compose
files must pin the SAME spika-marznode image tag. compose.voyra-preprod.yml
is a deliberately separate node deployment and is exempt (asserted distinct
on purpose elsewhere)."""
import re
from pathlib import Path

NODE_DIR = Path(__file__).resolve().parents[1]
PRIMARY = ["compose.yml", "compose.preprod.yml"]
IMG_RE = re.compile(r"ghcr\.io/[\w./-]*spika-marznode:([\w.\-]+)")


def _tag(name: str) -> str:
    text = (NODE_DIR / name).read_text()
    m = IMG_RE.search(text)
    assert m, f"no spika-marznode image pin found in {name}"
    return m.group(1)


def test_primary_compose_files_agree_on_tag():
    tags = {name: _tag(name) for name in PRIMARY}
    assert len(set(tags.values())) == 1, f"node image tag drift: {tags}"
