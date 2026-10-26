"""Exercise the publication workflow's tag resolver without building images."""

import os
import subprocess
from pathlib import Path

import pytest

from tarawasm.toolchains.catalog import LANGUAGES, default_image


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize(
    ("ref", "tag"),
    [
        ("refs/heads/master", "latest"),
        ("refs/tags/v0.4.0", "v0.4.0"),
        ("refs/tags/v0.4.0-rc1", "v0.4.0-rc1"),
        ("refs/pull/42/merge", "test"),
    ],
)
def test_language_image_publication_tag(tmp_path, language, ref, tag):
    workflow = (
        Path(__file__).resolve().parents[1] / ".github/workflows/docker.yaml"
    ).read_text()
    resolver = workflow.split("      - name: Resolve language image reference\n", 1)[1]
    resolver = resolver.split("        run: |\n", 1)[1].split("      - name:", 1)[0]
    script = "\n".join(line[10:] for line in resolver.splitlines())
    script = script.replace("${{ matrix.language }}", language)
    output = tmp_path / "output"
    subprocess.run(
        ["bash", "-e", "-c", script],
        env={**os.environ, "GITHUB_REF": ref, "GITHUB_OUTPUT": str(output)},
        check=True,
    )
    image = f"mandeser0/tarawasm:{tag}-{language}"
    assert output.read_text() == f"tag={image}\n"
    if ref == "refs/heads/master":
        assert default_image(language) == image
