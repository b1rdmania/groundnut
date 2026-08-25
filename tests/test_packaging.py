import json
from pathlib import Path
import tomllib

from groundnut._version import __version__
from groundnut.ic_loop import (
    DEFAULT_DOMAIN,
    DEFAULT_PROFILE,
    DEFAULT_SUPPORT_POLICY,
)


ROOT = Path(__file__).parent.parent


def test_package_version_matches_build_metadata():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert metadata["project"]["version"] == __version__


def test_bundled_ic_defaults_match_repository_contracts():
    pairs = (
        (DEFAULT_DOMAIN, ROOT / "domains" / "ic_research.json"),
        (DEFAULT_PROFILE, ROOT / "profiles" / "ic-research-pipeline.json"),
        (
            DEFAULT_SUPPORT_POLICY,
            ROOT / "policies" / "exact-support-baseline-v1.json",
        ),
    )
    for bundled, repository in pairs:
        assert json.loads(bundled.read_text()) == json.loads(repository.read_text())

