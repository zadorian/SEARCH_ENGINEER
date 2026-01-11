# CORPORELLA - TODO

> **Auto-updated by AI agents.** See `AGENT.md` for protocols.

---

## High Priority

- [ ] Expand UK API coverage to full Companies House integration
  - Priority: High
  - Added: 2025-12-04 by Claude
  - Notes: PSC, charges, filing history

- [ ] Implement dynamic button generation from Matrix
  - Priority: High
  - Added: 2025-12-04 by Claude
  - Notes: `MatrixDirectory.tsx` should read `sources.json` per jurisdiction

- [ ] Add more country_engines beyond UK
  - Priority: High
  - Added: 2025-12-04 by Claude
  - Notes: US (SEC EDGAR), EU national registries

## Medium Priority

- [ ] Integrate OpenSanctions real-time API
  - Priority: Medium
  - Added: 2025-12-04 by Claude
  - Notes: Currently using static data

- [ ] Add Beneficial Ownership extraction
  - Priority: Medium
  - Added: 2025-12-04 by Claude
  - Notes: PSC data for UK, equivalent for other jurisdictions

- [ ] Implement officer network analysis
  - Priority: Medium
  - Added: 2025-12-04 by Claude
  - Notes: Find common officers across companies

## Low Priority

- [ ] Add company similarity scoring
  - Priority: Low
  - Added: 2025-12-04 by Claude

- [ ] Implement shell company detection
  - Priority: Low
  - Added: 2025-12-04 by Claude
  - Notes: Cross-reference with red-flags use-case

---

## Completed

- [x] Document Global vs Jurisdictional paradigm in 1_CONCEPT.md
  - Completed: 2025-12-04 by Claude
  - Notes: Fundamental distinction clearly articulated

- [x] Map jurisdiction API status
  - Completed: 2025-12-04 by Claude
  - Notes: UK=complete, US/EU=partial, Others=Matrix links
