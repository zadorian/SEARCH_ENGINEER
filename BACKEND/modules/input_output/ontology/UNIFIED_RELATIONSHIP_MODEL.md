# NEXUS Unified Relationship Model

**Version:** 2.0.0
**Last Updated:** 2026-01-06
**Total Relationships:** 72
**Categories:** 12

---

## Design Principles

1. **Every directed relationship has an explicit inverse** - No guessing inverses
2. **Bidirectional relationships are marked explicitly** - married_to, sibling_of, same_as
3. **Generic fallbacks exist for each category** - related_to, linked_to when specific type unknown
4. **Temporal bounds available on all relationships** - start_date/end_date
5. **Confidence scores (0-1) required on all relationships**
6. **FTM (Follow The Money) compatibility noted where applicable**

---

## Category Overview

| Category | Code Range | Count | Description |
|----------|------------|-------|-------------|
| Corporate Structure | 100-199 | 5 | Officer and governance relationships |
| Ownership | 200-299 | 7 | Ownership and beneficial ownership |
| Employment | 300-399 | 4 | Employment and professional services |
| Family | 400-499 | 6 | Family and personal relationships |
| Financial | 500-599 | 7 | Financial and investment relationships |
| Legal | 600-699 | 5 | Legal proceedings and litigation |
| Contact Info | 700-799 | 6 | Contact information relationships |
| Location | 800-899 | 7 | Geographic and jurisdictional |
| Web/Digital | 900-999 | 7 | Web, domain, and digital infrastructure |
| Evidence | 1000-1099 | 5 | Evidence, documentation, and mentions |
| Association | 1100-1199 | 7 | Generic and deduplication |
| Regulatory | 1200-1299 | 7 | Regulatory, licensing, and compliance |

---

## Complete Relationship List

### 1. Corporate Structure (100-199)

| Code | Relationship | Source | Target | Inverse | Bidirectional | Temporal |
|------|--------------|--------|--------|---------|---------------|----------|
| 101 | `officer_of` | person | company, organization | has_officer | No | Yes |
| 102 | `director_of` | person | company, organization | has_director | No | Yes |
| 103 | `secretary_of` | person | company | has_secretary | No | Yes |
| 104 | `founder_of` | person | company, organization | founded_by | No | No |
| 105 | `authorized_signatory_of` | person | company, organization | has_authorized_signatory | No | Yes |

### 2. Ownership (200-299)

| Code | Relationship | Source | Target | Inverse | Bidirectional | Temporal |
|------|--------------|--------|--------|---------|---------------|----------|
| 201 | `owner_of` | person, company | company, property, vehicle, etc. | owned_by | No | Yes |
| 202 | `beneficial_owner_of` | person, company | company | has_beneficial_owner | No | Yes |
| 203 | `shareholder_of` | person, company | company | has_shareholder | No | Yes |
| 204 | `legal_owner_of` | person, company | company, property, vehicle, etc. | legally_owned_by | No | Yes |
| 205 | `subsidiary_of` | company | company | parent_of | No | Yes |
| 206 | `parent_of` | company | company | subsidiary_of | No | Yes |
| 207 | `ultimate_parent_of` | company | company | ultimate_subsidiary_of | No | Yes |

### 3. Employment (300-399)

| Code | Relationship | Source | Target | Inverse | Bidirectional | Temporal |
|------|--------------|--------|--------|---------|---------------|----------|
| 301 | `employed_by` | person | company, organization | employs | No | Yes |
| 302 | `contractor_for` | person, company | company, organization | has_contractor | No | Yes |
| 303 | `advisor_to` | person | company, organization, person | has_advisor | No | Yes |
| 304 | `representative_of` | person | company, organization | has_representative | No | Yes |

### 4. Family (400-499)

| Code | Relationship | Source | Target | Inverse | Bidirectional | Temporal |
|------|--------------|--------|--------|---------|---------------|----------|
| 401 | `married_to` | person | person | married_to | **Yes** | Yes |
| 402 | `child_of` | person | person | parent_of_person | No | No |
| 403 | `parent_of_person` | person | person | child_of | No | No |
| 404 | `sibling_of` | person | person | sibling_of | **Yes** | No |
| 405 | `relative_of` | person | person | relative_of | **Yes** | No |
| 406 | `domestic_partner_of` | person | person | domestic_partner_of | **Yes** | Yes |

### 5. Financial (500-599)

| Code | Relationship | Source | Target | Inverse | Bidirectional | Temporal |
|------|--------------|--------|--------|---------|---------------|----------|
| 501 | `investor_in` | person, company | company | has_investor | No | Yes |
| 502 | `funded_by` | company, organization | company, organization, person | funds | No | Yes |
| 503 | `debtor_of` | person, company | person, company, organization | creditor_of | No | Yes |
| 504 | `creditor_of` | person, company, organization | person, company | debtor_of | No | Yes |
| 505 | `transacted_with` | person, company, crypto_wallet | person, company, crypto_wallet | transacted_with | **Yes** | Yes |
| 506 | `guarantor_of` | person, company | person, company | guaranteed_by | No | Yes |
| 507 | `controls_account` | person, company | bank_account, crypto_wallet | controlled_by | No | Yes |

### 6. Legal (600-699)

| Code | Relationship | Source | Target | Inverse | Bidirectional | Temporal |
|------|--------------|--------|--------|---------|---------------|----------|
| 601 | `party_to` | person, company | legal_case | involves_party | No | Yes |
| 602 | `plaintiff_in` | person, company | legal_case | has_plaintiff | No | Yes |
| 603 | `defendant_in` | person, company | legal_case | has_defendant | No | Yes |
| 604 | `witness_in` | person | legal_case | has_witness | No | Yes |
| 605 | `legal_counsel_of` | person, company | person, company, organization | represented_by | No | Yes |

### 7. Contact Info (700-799)

| Code | Relationship | Source | Target | Inverse | Bidirectional | Temporal |
|------|--------------|--------|--------|---------|---------------|----------|
| 701 | `has_email` | person, company, organization, domain | email | email_of | No | Yes |
| 702 | `has_phone` | person, company, organization | phone | phone_of | No | Yes |
| 703 | `has_address` | person, company, organization | address | address_of | No | Yes |
| 704 | `has_profile` | person, company, organization | url | profile_of | No | Yes |
| 705 | `has_username` | person | username | username_of | No | Yes |
| 706 | `has_website` | person, company, organization | domain, url | website_of | No | Yes |

### 8. Location (800-899)

| Code | Relationship | Source | Target | Inverse | Bidirectional | Temporal |
|------|--------------|--------|--------|---------|---------------|----------|
| 801 | `registered_in` | company, vessel, aircraft, vehicle | country, region | registers | No | Yes |
| 802 | `headquartered_at` | company, organization | address, municipality, country | headquarters_of | No | Yes |
| 803 | `located_at` | company, organization, person, property | address, municipality, region, country | location_of | No | Yes |
| 804 | `operates_in` | company, organization | country, region, industry | has_operator | No | Yes |
| 805 | `resides_at` | person | address | residence_of | No | Yes |
| 806 | `citizen_of` | person | country | has_citizen | No | Yes |
| 807 | `tax_resident_of` | person, company | country | has_tax_resident | No | Yes |

### 9. Web/Digital (900-999)

| Code | Relationship | Source | Target | Inverse | Bidirectional | Temporal |
|------|--------------|--------|--------|---------|---------------|----------|
| 901 | `registrant_of` | person, company | domain | registered_by | No | Yes |
| 902 | `links_to` | domain, url | domain, url | linked_from | No | Yes |
| 903 | `hosted_at` | domain | ip_address | hosts | No | Yes |
| 904 | `shares_tracker` | domain | domain | shares_tracker | **Yes** | Yes |
| 905 | `subdomain_of` | domain | domain | has_subdomain | No | No |
| 906 | `nameserver_of` | domain | domain | serves_names_for | No | Yes |
| 907 | `ssl_issued_to` | domain | company, organization, person | has_ssl_for | No | Yes |

### 10. Evidence (1000-1099)

| Code | Relationship | Source | Target | Inverse | Bidirectional | Temporal |
|------|--------------|--------|--------|---------|---------------|----------|
| 1001 | `mentioned_in` | person, company, organization, address, event | document, url, file, source | mentions | No | Yes |
| 1002 | `documented_by` | person, company, organization, address, event, legal_case | document, file, source | documents | No | Yes |
| 1003 | `extracted_from` | person, company, organization, address, email, phone, event | document, url, source, domain | yielded | No | Yes |
| 1004 | `filed_with` | document, file | organization | received_filing | No | Yes |
| 1005 | `appeared_in` | person, company, organization | document, url, source | features | No | Yes |

### 11. Association (1100-1199)

| Code | Relationship | Source | Target | Inverse | Bidirectional | Temporal |
|------|--------------|--------|--------|---------|---------------|----------|
| 1101 | `same_as` | person, company, etc. | person, company, etc. | same_as | **Yes** | No |
| 1102 | `linked_to` | person, company, email, phone, etc. | person, company, email, phone, etc. | linked_to | **Yes** | Yes |
| 1103 | `related_to` | person, company, etc. | person, company, etc. | related_to | **Yes** | Yes |
| 1104 | `associated_with` | person, company, organization | person, company, organization, event | associated_with | **Yes** | Yes |
| 1105 | `partner_of` | company, organization | company, organization | partner_of | **Yes** | Yes |
| 1106 | `affiliated_with` | company, organization | company, organization | affiliated_with | **Yes** | Yes |
| 1107 | `member_of` | person, company | organization | has_member | No | Yes |

### 12. Regulatory (1200-1299)

| Code | Relationship | Source | Target | Inverse | Bidirectional | Temporal |
|------|--------------|--------|--------|---------|---------------|----------|
| 1201 | `licensed_by` | person, company | organization | licenses | No | Yes |
| 1202 | `regulated_by` | company, organization | organization | regulates | No | Yes |
| 1203 | `sanctioned_by` | person, company, organization, vessel, aircraft | organization, sanction_entry | sanctions | No | Yes |
| 1204 | `investigated_by` | person, company, organization | organization | investigates | No | Yes |
| 1205 | `flagged_with` | person, company, organization, vessel, aircraft | pep_entry, sanction_entry, tag | flags | No | Yes |
| 1206 | `pep_related_to` | person | pep_entry, person | has_pep_relation | No | Yes |
| 1207 | `audited_by` | company, organization | company, organization | audits | No | Yes |

---

## Deprecated Relationships

| Old Name | Replacement | Reason |
|----------|-------------|--------|
| `owns` | `owner_of` | Standardize on _of suffix |
| `has_linkedin` | `has_profile` | Use generic has_profile with platform metadata |
| `has_twitter` | `has_profile` | Use generic has_profile with platform metadata |
| `involved_in_litigation` | `party_to` | Use party_to with party_role metadata |
| `legal_parent_of` | `parent_of` | Redundant - parent_of covers legal parent |

---

## FTM (Follow The Money) Compatibility

| FTM Type | NEXUS Relationships |
|----------|---------------------|
| Directorship | officer_of, director_of, secretary_of |
| Ownership | owner_of, beneficial_owner_of, shareholder_of, subsidiary_of, parent_of |
| Employment | employed_by |
| Family | married_to, child_of, parent_of_person, sibling_of, relative_of |
| CourtCaseParty | party_to, plaintiff_in, defendant_in |
| Sanction | sanctioned_by, flagged_with |
| SameAs | same_as |
| UnknownLink | linked_to, related_to |
| Associate | associated_with, partner_of, affiliated_with |
| Membership | member_of |
| Representation | representative_of |

---

## Usage Examples

### Corporate Officer
```json
{
  "source": "person:john-smith-123",
  "target": "company:acme-corp",
  "relationship_type": "director_of",
  "metadata": {
    "role_type": "non_executive_director",
    "appointment_date": "2020-01-15",
    "resignation_date": null
  },
  "confidence": 0.95,
  "start_date": "2020-01-15"
}
```

### Beneficial Ownership
```json
{
  "source": "person:jane-doe-456",
  "target": "company:shell-co",
  "relationship_type": "beneficial_owner_of",
  "metadata": {
    "share_percentage": 75.5,
    "voting_percentage": 100,
    "natures_of_control": ["ownership-of-shares-75-to-100-percent", "voting-rights-75-to-100-percent"]
  },
  "confidence": 0.9,
  "start_date": "2019-06-01"
}
```

### Domain Intelligence
```json
{
  "source": "domain:example.com",
  "target": "domain:related-site.com",
  "relationship_type": "shares_tracker",
  "metadata": {
    "tracker_type": "google_analytics",
    "tracker_id": "UA-12345678-1"
  },
  "confidence": 0.9
}
```

### Sanctions
```json
{
  "source": "person:sanctioned-individual",
  "target": "sanction_entry:ofac-sdn-123",
  "relationship_type": "sanctioned_by",
  "metadata": {
    "sanction_program": "OFAC SDN",
    "sanction_reason": "Weapons proliferation",
    "listing_date": "2022-03-15"
  },
  "confidence": 0.98,
  "start_date": "2022-03-15"
}
```

---

## Migration Notes

When migrating from the old relationship files:

1. **input_output/matrix/relationship.json** - Replace with UNIFIED_RELATIONSHIP_MODEL.json
2. **input_output/ontology/relationships.json** - Archive and reference new model
3. **BACKEND/modules/CYMONIDES/edge_types.json** - Sync with new codes and categories
4. **BACKEND/modules/NEXUS/data/relationship_synonyms.json** - Keep for NLP, reference new canonical names

The unified model should be the **single source of truth** for all relationship type definitions.
