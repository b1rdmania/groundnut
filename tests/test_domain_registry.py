from pathlib import Path

import pytest

from groundnut.registry import DomainRegistry


ROOT = Path(__file__).resolve().parent.parent


def test_shipped_domains_load_and_remain_explicitly_experimental():
    registry = DomainRegistry.from_directory(ROOT / "domains")

    assert registry.keys() == ("grant_compliance", "ic_research", "ma_dd", "trust_obligations")
    assert len(registry.get("ma_dd").categories) == 18
    assert len(registry.get("grant_compliance").document_types) == 10
    assert len(registry.get("trust_obligations").categories) == 13
    assert len(registry.get("ic_research").categories) == 1
    assert {registry.get(key).evidence.status for key in registry.keys()} == {
        "experimental"
    }


def test_unknown_domain_never_silently_falls_back():
    registry = DomainRegistry.from_directory(ROOT / "domains")
    with pytest.raises(KeyError, match="unknown domain"):
        registry.get("not_a_domain")
