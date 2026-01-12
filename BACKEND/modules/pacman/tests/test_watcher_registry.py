from __future__ import annotations

from pathlib import Path

from PACMAN.watcher_registry import (
    ExtractionTarget,
    WatcherSpec,
    extract_for_watcher,
    get_watcher,
    register_watcher,
)


def test_registry_roundtrip(tmp_path: Path):
    path = tmp_path / "watchers.json"

    spec = WatcherSpec(
        watcher_id="w1",
        submarine_order="find contacts",
        domain_count=100,
        ttl_seconds=60,
        targets=[
            ExtractionTarget(name="companies", mode="builtin"),
            ExtractionTarget(
                name="iban",
                mode="regex",
                pattern=r"IBAN\s+([A-Z0-9]{10,34})",
                group=1,
            ),
        ],
    )

    register_watcher(spec, path)
    loaded = get_watcher("w1", path)
    assert loaded is not None
    assert loaded.watcher_id == "w1"
    assert loaded.submarine_order == "find contacts"
    assert loaded.domain_count == 100
    assert [t.mode for t in loaded.targets] == ["builtin", "regex"]


def test_extract_for_watcher_includes_snippets():
    spec = WatcherSpec(
        watcher_id="w2",
        submarine_order="extract company + iban",
        domain_count=50,
        ttl_seconds=60,
        targets=[
            ExtractionTarget(name="companies", mode="builtin"),
            ExtractionTarget(
                name="iban",
                mode="regex",
                pattern=r"IBAN\s+([A-Z0-9]{10,34})",
                group=1,
            ),
        ],
    )

    text = (
        "one two three four five six seven eight nine ten "
        "Acme Corp Ltd has a bank account. "
        "eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty "
        "IBAN DE89370400440532013000 is listed on the page for payments. "
        "twentyone twentytwo twentythree twentyfour twentyfive twentysix"
    )

    findings = extract_for_watcher(watcher=spec, content=text, url="https://example.com")
    assert findings
    assert all("snippet" in f for f in findings)
    assert all(isinstance(f.get("snippet"), str) for f in findings)
    assert any("Acme" in (f.get("snippet") or "") for f in findings)
    assert any("DE89370400440532013000" in (f.get("snippet") or "") for f in findings)


def test_haiku_skipped_when_domain_count_unknown():
    spec = WatcherSpec(
        watcher_id="w3",
        submarine_order="extract something hard",
        domain_count=None,
        ttl_seconds=60,
        targets=[ExtractionTarget(name="ubo statement", mode="haiku")],
    )

    findings = extract_for_watcher(watcher=spec, content="some content", url="https://example.com", allow_ai=True)
    assert findings == []
