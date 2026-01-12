def test_targets_note_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("EDITH_B_DATA_DIR", str(tmp_path / "edith_b"))
    monkeypatch.setenv("EDITH_B_DOCS_DIR", str(tmp_path / "edith_b" / "documents"))
    monkeypatch.setenv("EDITH_B_DB_PATH", str(tmp_path / "edith_b" / "edith_b.sqlite"))

    from SUBMARINE.exploration.targets_note import load_targets, update_targets

    doc, merged = update_targets(
        project_id="proj1",
        add_domains=["Example.com", "www.test.com"],
        add_urls=["https://example.com/a"],
        add_domain_rules=["acme"],
        add_url_rules=["login"],
    )

    assert doc.get("project_id") == "proj1"
    assert "example.com" in merged.target_domains
    assert "test.com" in merged.target_domains
    assert "https://example.com/a" in merged.target_urls
    assert "acme" in merged.domain_rules
    assert "login" in merged.url_rules

    doc2, merged2 = load_targets(project_id="proj1")
    assert doc2.get("id") == doc.get("id")
    assert merged2.to_dict() == merged.to_dict()

    meta = (doc2.get("metadata") or {}).get("submarine") or {}
    counts = meta.get("counts") or {}
    assert counts.get("target_domains") == 2
    assert counts.get("target_urls") == 1


def test_explorer_parsing_directives_and_hops():
    from SUBMARINE.exploration import explorer

    directives = explorer._parse_directives('indom:"foo bar" inurl:login')
    assert directives["indom"] == ["foo bar"]
    assert directives["inurl"] == ["login"]

    assert explorer._parse_hops("hop(0)") == 0
    assert explorer._parse_hops("hop(2)") == 2
    assert explorer._parse_hops("hop(999)") == 5
