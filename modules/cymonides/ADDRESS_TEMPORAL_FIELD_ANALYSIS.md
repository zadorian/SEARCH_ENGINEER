# CYMONIDES-3 Architecture Analysis: Address & Temporal Fields

## Overview

CYMONIDES-3 is a unified search ecosystem consolidating 10+ indices into entity-specific indices with comprehensive address and temporal coverage across 150+ source indices.

**Current Status:** 913M+ breach records indexed, consolidation ongoing

---

## Address Field Architecture (HIGH QUALITY)

### 1. Full Street Addresses (6 field mappings)

**Field Group:** ADDRESS_FULL (Quality: HIGH)

| Field Name | Indices | Sample Data |
|------------|---------|-------------|
| `address` | openownership, uk_addresses | "Oak House, Hirzel Street, St Peter Port, Guernsey, GY1 3RH" |
| `address_normalized` | uk_addresses | Standardized UK addresses |
| `property_address` | uk_ccod, uk_ocod, uk_property_unified | "Spaces The Maylands Building Maylands Avenue, Hemel Hempstead, HP2 7TG" |
| `proprietor_address` | uk_ocod | Owner addresses from Land Registry |
| `proprietor_address_1` | uk_ccod | Primary proprietor address |
| `proprietor_address_2` | uk_ccod | Secondary proprietor address |

**Coverage:** UK Land Registry (ccod, ocod, property_unified, addresses), OpenOwnership global

---

### 2. City/District (3 field mappings)

**Field Group:** CITY (Quality: HIGH)

| Field Name | Indices | Sample Data |
|------------|---------|-------------|
| `district` | uk_ccod, uk_ocod, uk_addresses | "KIRKLEES", "TOWER HAMLETS", "LIVERPOOL" |

**Coverage:** UK administrative districts from Land Registry

---

### 3. County/Region (4 field mappings)

**Field Group:** COUNTY (Quality: HIGH)

| Field Name | Indices | Sample Data |
|------------|---------|-------------|
| `county` | uk_ccod, uk_ocod, uk_leases, uk_addresses | "WEST YORKSHIRE", "GREATER LONDON" |
| `region` | uk_ccod, uk_ocod, uk_leases, uk_addresses | "YORKS AND HUMBER" |

**Coverage:** UK counties and regions from Land Registry + lease records

---

### 4. Country (5 field mappings)

**Field Group:** COUNTRY (Quality: HIGH)

| Field Name | Indices | Sample Data |
|------------|---------|-------------|
| `country` | openownership, phones_unified | "GB", "BRITISH VIRGIN ISLANDS", "CYPRUS" |
| `address_country` | openownership | Country from BODS addresses |
| `country_incorporated` | uk_ocod | Incorporation jurisdiction |

**Coverage:** Global (OpenOwnership + phone metadata)

---

### 5. Postal Codes (4 field mappings)

**Field Group:** POSTCODE (Quality: HIGH)

| Field Name | Indices | Sample Data |
|------------|---------|-------------|
| `postcode` | uk_ccod, uk_ocod, uk_addresses, uk_property_unified | "HX3 7AF", "LS12 3NP", "W3" |
| `postcode_district` | uk_ccod, uk_ocod | District-level postcodes |

**Coverage:** UK postal codes from 4 Land Registry indices

---

### 6. Additional Address Context

**Field Group:** JURISDICTION (Quality: HIGH)

| Field Name | Indices | Sample Data |
|------------|---------|-------------|
| `jurisdiction` | openownership, uk_addresses | "gb", "GB" (ISO 2-letter) |

**Field Group:** LAND_TITLE (Quality: HIGH)

| Field Name | Indices | Sample Data |
|------------|---------|-------------|
| `title_number` | uk_ccod, uk_ocod, uk_addresses, uk_property_unified | "WYK803313", "AGL334118" |
| `tenure` | uk_ccod, uk_addresses | "Freehold", "Leasehold" |

---

## Temporal Field Architecture

### 1. Business/Legal Event Dates (HIGH QUALITY)

**Field Group:** DATE_BUSINESS (Quality: HIGH)

| Field Name | Indices | Format | Sample Data |
|------------|---------|--------|-------------|
| `incorporation_date` | openownership, search_nodes | YYYY-MM-DD | "2013-08-07" |
| `dissolution_date` | openownership | YYYY-MM-DD | "2021-11-30" |
| `statement_date` | openownership | YYYY-MM-DD | Ownership statement dates |

**Use Case:** Legal entity lifecycle events, ownership changes

---

### 2. Communication Timestamps (HIGH QUALITY)

**Field Group:** DATE_MESSAGE (Quality: HIGH)

| Field Name | Indices | Format | Sample Data |
|------------|---------|--------|-------------|
| `date` | kazaword_emails | ISO8601 with timezone | "2008-12-07T09:48:16-08:00" |

**Use Case:** Email/message chronology, communication timeline analysis

---

### 3. System Processing Timestamps (INTERNAL_ONLY)

**Field Group:** DATE_SYSTEM (Quality: INTERNAL_ONLY - NOT FOR USER SEARCH)

| Field Name | Indices | Format | Purpose |
|------------|---------|--------|---------|
| `indexed_at` | openownership, domains_unified, kazaword_emails, linklater_corpus, uk_addresses, uk_ccod, uk_leases, uk_ocod | ISO8601 with microseconds | ETL tracking |
| `crawl_timestamp` | drill_pages | ISO8601 | Crawl job tracking |
| `fetched_at` | onion-pages | ISO8601 | Scrape timing |
| `enriched_at` | onion-pages | ISO8601 | AI processing timestamp |
| `scraped_at` | linklater_corpus | ISO8601 | LINKLATER crawl time |
| `last_updated` | domains_unified | ISO8601 | Record refresh |
| `updated_on` | onion-pages | ISO8601 | Dark web update time |

**Sample:** "2025-12-29T18:31:41.531239"

**Note:** These are ETL/pipeline timestamps, not business events. Should NOT be exposed in user search interface.

---

### 4. Additional Temporal Fields

**From field_meta.json:**

- **person_dob** (group 2): Person date of birth
- **company_incorporation_date** (group 5): Company founding date
- **company_dissolution_date** (group 6): Company closure date
- **company_officer_appointment_date** (group 7): Officer appointment
- **company_officer_resignation_date** (group 7): Officer resignation
- **company_accounts_filing_date** (group 6): Financial filing dates
- **property_purchase_date** (group 12): Land Registry purchase dates
- **license_issued_date** (group 10): License issuance
- **license_expiry_date** (group 10): License expiration
- **domain_creation_date** (group 14): WHOIS creation date
- **domain_update_date** (group 14): WHOIS update
- **domain_expiry_date** (group 14): WHOIS expiry
- **breach_date** (group 15): Data breach occurrence date
- **litigation_filing_date** (group 9): Court case filing
- **litigation_judgment_date** (group 9): Judgment date
- **sanction_date_added** (group 11): Sanctions list addition
- **sanction_date_removed** (group 11): Delisting date

---

## CYMONIDES-3 Consolidation Structure

### Target Entity Indices (7+ Core)

Based on field_groups.json and field_meta.json analysis:

#### 1. **persons_unified** (PERSON index)
- **Name Fields:** PERSON_NAME (HIGH), MIXED_NAME (MEDIUM)
- **Address Fields:** All ADDRESS_FULL, CITY, COUNTY, COUNTRY, POSTCODE
- **Temporal Fields:** DATE_BUSINESS (dob, appointments), DATE_MESSAGE (comms)
- **Current Issues:** persons_unified.full_name is GARBAGE (NER failures)

#### 2. **companies_unified** (COMPANY index)
- **Name Fields:** COMPANY_NAME (HIGH)
- **Address Fields:** Full address suite from uk_ccod, uk_ocod, openownership
- **Temporal Fields:** incorporation_date, dissolution_date, accounts_filing_date, officer dates
- **Current Issues:** companies_unified.name is GARBAGE

#### 3. **emails_unified** (EMAIL index)
- **Email Fields:** EMAIL_RAW (HIGH), EMAIL_DOMAIN (HIGH), EMAIL_LOCAL (HIGH)
- **Temporal Fields:** DATE_MESSAGE from kazaword_emails
- **Current Issues:** emails_unified.email_domain is CORRUPTED, .local_part is CORRUPTED

#### 4. **phones_unified** (PHONE index)
- **Phone Fields:** PHONE_FULL (HIGH), PHONE_PART (HIGH)
- **Country Fields:** COUNTRY (HIGH) - geolocation metadata
- **Current Issues:** phones_unified.person_names is GARBAGE, .organization_names is GARBAGE

#### 5. **domains_unified** (DOMAIN index)
- **Domain Fields:** DOMAIN_BARE (HIGH), URL_FULL (HIGH), URL_SOCIAL (HIGH)
- **Address Fields:** WHOIS address data from domain_registrant_address
- **Temporal Fields:** domain_creation_date, domain_update_date, domain_expiry_date

#### 6. **usernames** (USERNAME index - NEW)
- **Username Fields:** To be extracted from breach_records.username
- **Temporal Fields:** breach_date, account creation dates

#### 7. **passwords** (PASSWORD index - NEW)
- **Password Fields:** PASSWORD_HASH (HIGH), password_hash + hash_type
- **Temporal Fields:** breach_date
- **Security Fields:** security_tier classification

---

### Edge/Relationship Indices

#### 8. **uk_addresses** (ADDRESS linking)
- **Full Coverage:** address, address_normalized, district, county, postcode, title_number
- **Links:** Connects properties → owners → companies via uk_ccod/uk_ocod

#### 9. **openownership** (OWNERSHIP edges)
- **Temporal:** statement_date, incorporation_date, dissolution_date
- **Address:** Full international addresses with country codes
- **Links:** beneficial_owner → company relationships

#### 10. **breach_records** (CREDENTIAL edges)
- **Current State:** 913M+ records aliased as cymonides-3
- **Target:** Split into emails_unified, usernames, passwords indices
- **Temporal:** breach_date, indexed_at

---

## Data Quality Warnings

### GARBAGE Fields (DO NOT USE FOR SEARCH)

From field_groups.json GARBAGE_NAME group:

| Field | Index | Issue | Example Garbage |
|-------|-------|-------|-----------------|
| `full_name` | persons_unified | NER extraction failures | "Koei Tecmo Releases New Trailer" |
| `name` | breach_records | Usernames, not names | "18718190" |
| `name` | companies_unified | Article titles, locations | "Hong Kong" |
| `person_names` | phones_unified | NER failures | Random text |
| `persons` | drill_pages, onion-pages | Web scraping noise | Article content |
| `companies` | drill_pages, onion-pages | Web scraping noise | Headlines |
| `organization_names` | phones_unified | NER failures | Gibberish |

### CORRUPTED Fields (DO NOT USE)

From field_groups.json notes:

- `emails_unified.email_domain` - CORRUPTED
- `emails_unified.local_part` - CORRUPTED

---

## Breach Indexing Status

**Current Operation:**
- Indexing breach data from `/Volumes/My Book/Raidforums/DATABASES/Raidforums`
- Target: breach_records (aliased as cymonides-3)
- Progress: 913,196,721 records indexed (151.5GB)
- Status: Processing youku.com (1/183 breaches)
- Checkpoint: Line 99,688,552

**Target Consolidation:**
- emails_unified: Email addresses with breach metadata
- usernames: NEW dedicated index
- passwords: NEW with security_tier field
- All integrated into unified CYMONIDES-3 search

---

## Index Coverage Summary

**43 Field Groups** mapped across **150+ indices**

**Address Coverage:**
- UK Land Registry: 5 indices (uk_ccod, uk_ocod, uk_property_unified, uk_addresses, uk_leases)
- International: OpenOwnership (global corporate addresses)
- Phone geo: phones_unified (country codes)

**Temporal Coverage:**
- Business dates: openownership (incorporations, dissolutions, ownership statements)
- Communication dates: kazaword_emails (email timestamps)
- Land transactions: uk_leases, uk_ccod (purchase dates, lease terms)
- Regulatory dates: License issuance, expiry, violation dates
- Breach timeline: breach_records.breach_date
- Court dates: litigation_filing_date, litigation_judgment_date
- Domain lifecycle: WHOIS creation/update/expiry dates

**System Timestamps (INTERNAL ONLY):**
- 8 different ETL timestamp fields
- NOT for user search - pipeline tracking only

---

## Query Routing Flow

```
User Query → IO Router → Field Group Resolver → Query Patterns → Elasticsearch

Example: "123 Main Street, London"
1. Field Group: ADDRESS_FULL
2. Indices: uk_addresses, uk_ccod, uk_ocod
3. Fields: address, property_address, proprietor_address_1
4. Quality: HIGH
5. Execute multi-index search
```

---

## Key Insights

### "We Have So Much"

**Quantified:**
- **43 semantic field groups** across 150+ indices
- **280+ distinct field definitions** in field_meta.json
- **10+ indices** currently aliased as cymonides-3
- **913M+ breach records** already indexed
- **7+ core entity indices** as consolidation target
- **Multiple UK indices:** ccod, ocod, property_unified, addresses, leases (comprehensive UK property coverage)
- **International coverage:** OpenOwnership (global), phones_unified (worldwide)
- **Temporal breadth:** Business dates, communication dates, regulatory dates, breach dates, court dates, domain dates

### Critical Gaps

**GARBAGE data identified:**
- persons_unified.full_name - DO NOT USE
- companies_unified.name - DO NOT USE
- breach_records.name - DO NOT USE
- drill_pages.persons/companies - DO NOT USE
- phones_unified.person_names/organization_names - DO NOT USE

**CORRUPTED data identified:**
- emails_unified.email_domain - DO NOT USE
- emails_unified.local_part - DO NOT USE

**Consolidation ongoing:**
- breach_records needs split → emails_unified, usernames, passwords
- Edge indices need creation for ownership links, web graph relationships

---

## Next Steps (Ongoing Consolidation)

1. **Complete breach indexing** (80/183 breaches remaining)
2. **Split breach_records** into dedicated entity indices
3. **Create username index** from breach data
4. **Create password index** with security_tier classification
5. **Build edge indices** for ownership relationships
6. **Deprecate GARBAGE fields** from search interface
7. **Fix CORRUPTED fields** in emails_unified
8. **Add address fields** to all 7 core entity indices
9. **Add temporal fields** to all relevant entity indices
10. **Implement multi-dimensional filtering** with dimension_keys

---

## Architecture Files Reference

- `/data/CYMONIDES/UNIFIED_SEARCH_ARCHITECTURE_PLAN.md` - Overall architecture
- `/data/CYMONIDES/field_groups.json` - 43 semantic field groups with quality ratings
- `/data/CYMONIDES/field_meta.json` - 280+ field definitions with datatypes, PII flags, cardinality
- `/tmp/breach_bulk_indexer.py` - Breach indexing script (currently running)
- `/tmp/breach_indexer_output.log` - Real-time indexing progress
