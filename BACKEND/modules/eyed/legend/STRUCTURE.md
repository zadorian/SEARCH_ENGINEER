# EYE-D Legend-Aligned Structure (Drill Search)

```
python-backend/eyed/
├── __init__.py
├── classifier.py
├── claude_utils.py
├── legend/
│   ├── __init__.py
│   ├── module.py
│   ├── STRUCTURE.md
│   ├── OUTPUT.md
│   ├── MATRIX_INTEGRATION.md
│   ├── input/
│   │   ├── __init__.py
│   │   ├── email.py          # Legend 1
│   │   ├── phone.py          # Legend 2
│   │   ├── domain_url.py     # Legend 6
│   │   └── person_name.py    # Legend 7
│   ├── models/
│   │   ├── __init__.py
│   │   └── output_models.py  # Legends 187-198
│   └── resources/
│       ├── __init__.py
│       ├── base.py
│       ├── archive_org.py
│       ├── contactout.py
│       ├── dehashed.py
│       ├── kaspr.py
│       ├── osint_industries.py
│       ├── rocketreach.py
│       └── whoisxml.py
└── (legacy collectors live in OSINT_tools/)
```

## Inputs

| Legend | File                   | Description                                         |
| ------ | ---------------------- | --------------------------------------------------- |
| 1      | `input/email.py`       | Email enrichment toggles (breaches, person, domain) |
| 2      | `input/phone.py`       | Phone normalization + regional hints                |
| 6      | `input/domain_url.py`  | Domain/URL analysis flags (DNS, wayback, SSL)       |
| 7      | `input/person_name.py` | Person context hints for social + corporate lookups |

## Outputs

| Legend | Dataclass                | Notes                                                          |
| ------ | ------------------------ | -------------------------------------------------------------- |
| 187    | `BreachData`             | Consolidated DeHashed/OSINT breach results                     |
| 188    | `SocialProfile`          | Social + LinkedIn profiles (ContactOut/Kaspr/OSINT Industries) |
| 189    | `PhoneRecord`            | Reverse phone + carrier data                                   |
| 190    | `PersonIdentityGraph`    | Linked identifiers/organizations                               |
| 191    | `DomainBacklinks`        | Majestic/Firecrawl backlink sets                               |
| 192    | `DomainWaybackSnapshots` | Archive.org/Archive.today captures                             |
| 193    | `DomainDNSRecords`       | DNS answers derived from WHOISXML + field collectors           |
| 195    | `WhoisHistoryEntry`      | WHOIS historical timeline                                      |
| 196    | `SSLCertificate`         | SSL certificate inventory (via CT)                             |
| 197    | `DomainTimeline`         | URL timelines/liveness (Firecrawl MAP + archives)              |
| 198    | `DomainKeywordResults`   | Historic keyword hits from archived snapshots                  |

## Resources

| Resource           | Inputs  | Outputs | Backing modules                                 |
| ------------------ | ------- | ------- | ----------------------------------------------- |
| `dehashed`         | 1,2,6,7 | 187     | `OSINT_tools/unified_osint.py` (DeHashedEngine) |
| `osint_industries` | 1,2,7   | 188,190 | `python-backend/eyed/osintindustries.py`        |
| `rocketreach`      | 1,2,6,7 | 189,190 | RocketReach collectors in Eye-D service         |
| `contactout`       | 1,2,6,7 | 188,189 | ContactOut collectors                           |
| `kaspr`            | 7       | 188     | LinkedIn enrichment                             |
| `whoisxmlapi`      | 1,2,6   | 193,195 | WHOISXML + DNS history                          |
| `archive_org`      | 6       | 192     | Wayback/Archive.today scrapers                  |

This structure mirrors the corporate global/national modules so the IO matrix, router, and MCP tooling can reason about Eye-D inputs/outputs inside Drill Search.
