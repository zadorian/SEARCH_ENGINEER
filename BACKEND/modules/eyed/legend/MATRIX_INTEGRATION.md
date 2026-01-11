# EYE-D Matrix Integration (Drill Search)

## Inputs → Outputs

| Input Legend    | Description       | Outputs            |
| --------------- | ----------------- | ------------------ |
| 1 (email)       | `EmailInput`      | 187, 188, 189, 190 |
| 2 (phone)       | `PhoneInput`      | 187, 189, 190      |
| 6 (domain_url)  | `DomainUrlInput`  | 191, 192, 193, 195 |
| 7 (person_name) | `PersonNameInput` | 187, 188, 190      |

## Resources

| Resource           | Outputs  | Notes                                     |
| ------------------ | -------- | ----------------------------------------- |
| `dehashed`         | 187      | Credential breaches (DeHashed engine)     |
| `osint_industries` | 188, 190 | Social profiles & linked identities       |
| `rocketreach`      | 189, 190 | Contact enrichment (emails/phones/titles) |
| `contactout`       | 188, 189 | LinkedIn-driven contact discovery         |
| `kaspr`            | 188      | Deep LinkedIn enrichment                  |
| `whoisxmlapi`      | 193, 195 | WHOIS history + DNS answers               |
| `archive_org`      | 192      | Wayback/Archive.today captures            |

## Router / IO Matrix

- Update `input_output/master_input_output_matrix.json` to include legends 187–198 and the `eyed_osint_platform` descriptor pointing at `python-backend/eyed/legend`.
- The Io Matrix indexer will then surface Eye-D under the same structure as the corporate (global/national) modules.
- Global corporate search already consumes Eye-D company data via `globalCorporateSearchService`. With this legend layer we can also answer “what can Eye-D do with input X?” just like the corporate module.

## Drill Search Runtime Notes

- The Express router (`server/routers/eyedRouter.ts`) exposes WHOIS, backlinks, outlinks, OSINT Industries, OpenCorporates, and Aleph endpoints. Extend it with additional routes (e.g., `/breaches`) as new resources are enabled.
- Collectors in `OSINT_tools/unified_osint.py` already call DeHashed, RocketReach, ContactOut, Kaspr, etc. Ensure API keys are configured via `.env` or server secrets so Drill Search instances achieve parity with the standalone MCP server.
