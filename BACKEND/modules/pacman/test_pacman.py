from __future__ import annotations

from PACMAN import Pacman


TEST_CONTENT = """
John Smith is the CEO of Acme Corp Ltd.
Contact: john.smith@acme.com or +1 (555) 123-4567
Company registered at Companies House: 12345678
Bank: IBAN DE89370400440532013000
Bitcoin: 1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2
"""


def test_pacman_smoke():
    pacman = Pacman()

    entities = pacman.extract_entities(TEST_CONTENT)
    assert isinstance(entities, dict)

    persons = pacman.extract_persons(TEST_CONTENT)
    assert isinstance(persons, list)

    companies = pacman.extract_companies(TEST_CONTENT)
    assert isinstance(companies, list)

    tier = pacman.classify_url("https://companieshouse.gov.uk/company/12345678")
    assert tier

    flags = pacman.scan_red_flags("The company was involved in money laundering and sanctions violations.")
    assert isinstance(flags, list)
    assert all("pattern" in f for f in flags)

    result = pacman.full_extract(TEST_CONTENT, "https://example.com")
    assert result.tier
    assert isinstance(result.entities, dict)
    assert isinstance(result.persons, list)
    assert isinstance(result.companies, list)
    assert isinstance(result.red_flags, list)
