# EYE-D Output Specification (Drill Search)

All dataclasses live in `legend/models/output_models.py`.

## Person Intelligence (187–190)

| Legend | Dataclass             | Description                                    | Primary Sources                         |
| ------ | --------------------- | ---------------------------------------------- | --------------------------------------- |
| 187    | `BreachData`          | Credential breach history + compromised fields | DeHashed                                |
| 188    | `SocialProfile`       | Social + LinkedIn profiles with metadata       | ContactOut, Kaspr, OSINT Industries     |
| 189    | `PhoneRecord`         | Carrier/location + linked identifiers          | RocketReach, ContactOut                 |
| 190    | `PersonIdentityGraph` | Linked emails, domains, orgs, socials          | RocketReach, OSINT Industries, DeHashed |

## Domain Intelligence (191–197)

| Legend | Dataclass                | Description                         | Primary Sources                   |
| ------ | ------------------------ | ----------------------------------- | --------------------------------- |
| 191    | `DomainBacklinks`        | Backlinks/backlink summary metrics  | Firecrawl MAP, Majestic           |
| 192    | `DomainWaybackSnapshots` | Wayback Machine captures + statuses | Archive.org, Archive.today        |
| 193    | `DomainDNSRecords`       | DNS answers for pivots/resolution   | WhoisXML, resolver integrations   |
| 195    | `WhoisHistoryEntry`      | Registrant/registrar history        | WhoisXML, Eye-D WHOIS pipelines   |
| 196    | `SSLCertificate`         | SSL/CT SAN coverage                 | crt.sh, CT feeds                  |
| 197    | `DomainTimeline`         | Live/dead timeline for each URL     | Firecrawl MAP, archive collectors |

## Historic Keyword Evidence (198)

| Legend | Dataclass              | Description                            | Primary Sources                                    |
| ------ | ---------------------- | -------------------------------------- | -------------------------------------------------- |
| 198    | `DomainKeywordResults` | Keyword presence in historic snapshots | Eye-D keyword scanner (`scan_gitedanslesvosges_*`) |

Use these legend codes in the IO matrix and routing layers when referencing Eye-D outputs.
