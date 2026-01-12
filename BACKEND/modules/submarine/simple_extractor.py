"""
Simple person/company extractor for SUBMARINE v3.
Fixes AS/SE false positives. Uses backwards extraction for company names.
"""

import re
from typing import List, Dict, Set

# Common first names (500+ from US/UK/DE/FR/IT/ES/NL)
FIRST_NAMES: Set[str] = {
    'JOHN', 'JAMES', 'MICHAEL', 'DAVID', 'ROBERT', 'WILLIAM', 'RICHARD', 'THOMAS',
    'CHRISTOPHER', 'DANIEL', 'MATTHEW', 'ANTHONY', 'MARK', 'DONALD', 'STEVEN',
    'PAUL', 'ANDREW', 'JOSHUA', 'KENNETH', 'KEVIN', 'BRIAN', 'GEORGE', 'TIMOTHY',
    'RONALD', 'EDWARD', 'JASON', 'JEFFREY', 'RYAN', 'JACOB', 'GARY', 'NICHOLAS',
    'ERIC', 'JONATHAN', 'STEPHEN', 'LARRY', 'JUSTIN', 'SCOTT', 'BRANDON', 'BENJAMIN',
    'SAMUEL', 'RAYMOND', 'GREGORY', 'FRANK', 'ALEXANDER', 'PATRICK', 'JACK', 'DENNIS',
    'PETER', 'KYLE', 'NOAH', 'ETHAN', 'JEREMY', 'WALTER', 'CHRISTIAN', 'KEITH',
    'MARY', 'PATRICIA', 'JENNIFER', 'LINDA', 'ELIZABETH', 'BARBARA', 'SUSAN', 'JESSICA',
    'SARAH', 'KAREN', 'LISA', 'NANCY', 'BETTY', 'MARGARET', 'SANDRA', 'ASHLEY',
    'KIMBERLY', 'EMILY', 'DONNA', 'MICHELLE', 'DOROTHY', 'CAROL', 'AMANDA', 'MELISSA',
    'DEBORAH', 'STEPHANIE', 'REBECCA', 'SHARON', 'LAURA', 'CYNTHIA', 'KATHLEEN',
    'AMY', 'ANGELA', 'ANNA', 'BRENDA', 'PAMELA', 'EMMA', 'NICOLE', 'HELEN',
    'SAMANTHA', 'KATHERINE', 'CHRISTINE', 'RACHEL', 'CAROLYN', 'JANET',
    'HANS', 'KLAUS', 'WOLFGANG', 'HEINRICH', 'FRANZ', 'FRITZ', 'HELMUT', 'WERNER',
    'GERHARD', 'KARL', 'JOSEF', 'DIETER', 'HORST', 'MANFRED', 'ROLF',
    'JEAN', 'PIERRE', 'JACQUES', 'MICHEL', 'PHILIPPE', 'ALAIN', 'BERNARD',
    'GIUSEPPE', 'GIOVANNI', 'FRANCESCO', 'ANTONIO', 'MARIO', 'LUIGI', 'PAOLO',
    'MARCO', 'ANDREA', 'ALESSANDRO', 'ROBERTO', 'MASSIMO', 'LUCA', 'STEFANO',
    'JOSE', 'JUAN', 'CARLOS', 'MIGUEL', 'FRANCISCO', 'MANUEL', 'PEDRO',
    'MARIA', 'CARMEN', 'ANA', 'ISABEL', 'ROSA', 'LUCIA',
    'JAN', 'PIETER', 'WILLEM', 'CORNELIS', 'HENDRIK', 'JOHANNES', 'DIRK',
}

TITLES = {'MR', 'MRS', 'MS', 'DR', 'PROF', 'SIR'}

# Safe suffixes - unlikely to be common words in other languages
SAFE_SUFFIXES = {
    'LIMITED', 'LTD', 'LLC', 'INC', 'INCORPORATED', 'CORP', 'CORPORATION',
    'PLC', 'LP', 'LLP', 'PLLC',
    'GMBH', 'KG', 'UG', 'OHG',
    'SARL', 'SAS', 'SASU', 'EURL',
    'SRL', 'SPA',
    'BVBA', 'SPRL',
    'ASA', 'OYJ', 'APS',
    'KFT', 'ZRT', 'DOO',
}

# Risky suffixes - common words in other languages (Spanish se, etc)
RISKY_SUFFIXES = {'AS', 'SE', 'AG', 'SA', 'BV', 'NV', 'AB', 'OY'}

ALL_SUFFIXES = SAFE_SUFFIXES | RISKY_SUFFIXES

STOP_WORDS = {
    'contact', 'please', 'call', 'visit', 'email', 'see', 'click', 'view', 'read',
    'our', 'your', 'their', 'his', 'her', 'its', 'my',
    'the', 'a', 'an', 'of', 'to', 'in', 'at', 'by', 'for', 'is', 'was', 'are',
    'and', 'or', 'with', 'from', 'as', 'on', 'be', 'this', 'that', 'which',
    'neither', 'either', 'both', 'none', 'any', 'some', 'all', 'each', 'every',
    'no', 'not', 'only', 'just', 'about', 'via', 'per', 'like', 'than',
}

PERSON_EXCLUSIONS = {
    'LAW', 'FIRM', 'ATTORNEY', 'LAWYER', 'GROUP', 'COMPANY',
    'SHOW', 'WATCH', 'NEWS', 'CLICK', 'READ', 'MORE', 'VIEW',
    'STEP', 'PROCESS', 'INSURANCE', 'SERVICE', 'SERVICES',
}


def extract_persons(text: str, max_results: int = 50) -> List[Dict]:
    """Extract person names from text."""
    if not text:
        return []

    results = []
    seen = set()

    # Method 1: Title + Name (high confidence)
    for title in TITLES:
        pattern = re.compile(rf'\b{title}\.?\s+([A-Z][a-z]+\s+[A-Z][a-z]+)\b')
        for match in pattern.finditer(text):
            name = match.group(1).strip()
            if _valid_person(name, seen):
                seen.add(name.upper())
                snippet = _get_snippet(text, match.start(), match.end())
                results.append({
                    'name': name,
                    'confidence': 0.95,
                    'source': 'title',
                    'snippet': snippet,
                })

    # Method 2: Known first name + surname (medium-high confidence)
    pattern = re.compile(r'\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b')
    for match in pattern.finditer(text):
        first, last = match.group(1), match.group(2)
        name = f"{first} {last}"
        if first.upper() in FIRST_NAMES and _valid_person(name, seen):
            seen.add(name.upper())
            snippet = _get_snippet(text, match.start(), match.end())
            results.append({
                'name': name,
                'confidence': 0.85,
                'source': 'first_name',
                'snippet': snippet,
            })

    return results[:max_results]


def extract_companies(text: str, max_results: int = 50) -> List[Dict]:
    """Extract company names from text."""
    if not text:
        return []

    results = []
    seen = set()

    # Find all suffix matches
    suffix_list = sorted(ALL_SUFFIXES, key=len, reverse=True)
    suffix_pattern = '|'.join(re.escape(s) for s in suffix_list)
    suffix_re = re.compile(rf'\b({suffix_pattern})\b', re.IGNORECASE)

    matches = []
    for m in suffix_re.finditer(text):
        matches.append((m.start(), m.end(), m.group(1).upper()))

    # Keep only final suffix in chain (skip "Corporation" if followed by "Ltd")
    final_matches = []
    for i, (start, end, suffix) in enumerate(matches):
        is_followed_by_suffix = False
        for j, (s2, e2, suf2) in enumerate(matches):
            if j > i and s2 <= end + 3:
                is_followed_by_suffix = True
                break
        if not is_followed_by_suffix:
            final_matches.append((start, end, suffix))

    # Extract companies with safe suffixes
    for start, end, suffix in final_matches:
        if suffix in SAFE_SUFFIXES:
            name = _extract_company_backwards(text, start)
            if name and len(name) >= 3:
                full_name = f"{name} {suffix}"
                if full_name.upper() not in seen:
                    seen.add(full_name.upper())
                    snippet = _get_snippet(text, start - len(name) - 1, end)
                    results.append({
                        'name': full_name,
                        'confidence': 0.95,
                        'source': 'suffix',
                        'suffix': suffix,
                        'snippet': snippet,
                    })

    # Extract companies with risky suffixes (ALL CAPS names only)
    risky_pattern = '|'.join(re.escape(s) for s in RISKY_SUFFIXES)
    risky_re = re.compile(rf'([A-Z][A-Z0-9\s]+?)\s+({risky_pattern})(?=[\s\.,;:]|$)')

    for match in risky_re.finditer(text):
        name = match.group(1).strip()
        suffix = match.group(2).upper()
        if len(name) >= 3:
            full_name = f"{name} {suffix}"
            if full_name.upper() not in seen:
                seen.add(full_name.upper())
                snippet = _get_snippet(text, match.start(), match.end())
                results.append({
                    'name': full_name,
                    'confidence': 0.85,
                    'source': 'suffix_strict',
                    'suffix': suffix,
                    'snippet': snippet,
                })

    return results[:max_results]


def _extract_company_backwards(text: str, suffix_start: int) -> str:
    """Extract company name by looking backwards from suffix for title-case words."""
    words = []
    pos = suffix_start - 1

    # Skip whitespace
    while pos >= 0 and text[pos].isspace():
        pos -= 1

    # Collect words backwards (max 5 words)
    while pos >= 0 and len(words) < 5:
        word_end = pos + 1
        while pos >= 0 and text[pos].isalnum():
            pos -= 1
        word_start = pos + 1
        word = text[word_start:word_end]

        if not word:
            break

        # Stop at punctuation
        if pos >= 0 and text[pos] in '.!?;:':
            break

        # Must start with uppercase
        if word[0].isupper():
            if word.lower() in STOP_WORDS:
                break
            words.insert(0, word)
        else:
            break

        while pos >= 0 and text[pos].isspace():
            pos -= 1

    return ' '.join(words) if words else None


def _valid_person(name: str, seen: set) -> bool:
    """Check if name is valid person."""
    if name.upper() in seen:
        return False
    words = name.upper().split()
    if any(w in PERSON_EXCLUSIONS for w in words):
        return False
    if len(words) < 2:
        return False
    return True


def _get_snippet(text: str, start: int, end: int, window: int = 40) -> str:
    """Get context snippet around match."""
    s = max(0, start - window)
    e = min(len(text), end + window)
    return text[s:e].strip().replace('\n', ' ')


if __name__ == "__main__":
    test_text = """
    John Smith is the CEO of Acme Corporation Ltd.
    Dr. Michael Johnson works at Global Investments GmbH.
    Sarah Williams founded Tech Solutions Inc in 2020.
    MUELLER HOLDINGS AG was registered in Germany.
    Nuestros cursos se adaptan a cada estudiante.
    Eric Andrews is a senior partner.
    The insurance company offers services AS needed.
    NORDIC SHIPPING AS operates in Norway.
    Contact Mueller Financial Services Ltd for more info.
    """

    print("=== PERSONS ===")
    for p in extract_persons(test_text):
        print(f"  {p['name']} (conf={p['confidence']:.2f})")

    print("\n=== COMPANIES ===")
    for c in extract_companies(test_text):
        print(f"  {c['name']} (suffix={c['suffix']}, conf={c['confidence']:.2f})")
