import os
import json
import re
import time
import datetime
from pathlib import Path
from typing import Union
import sys

# Ensure module paths are on sys.path for local imports
MODULE_DIR = Path(__file__).resolve().parent
MODULES_ROOT = MODULE_DIR.parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))
if str(MODULES_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULES_ROOT))

try:
    from whoisxmlapi import WhoisApiException
except ImportError:
    from eyed.whoisxmlapi import WhoisApiException  # type: ignore

try:
    import whois_discovery as linklater_whois

    get_whois_history = linklater_whois.get_whois_history
    reverse_whois_search = linklater_whois.reverse_whois_search
    reverse_nameserver_search = linklater_whois.reverse_nameserver_search
    normalize_domain = linklater_whois.normalize_domain
    fetch_current_whois_record = linklater_whois.fetch_current_whois_record
    WHOIS_DISCOVERY_AVAILABLE = True
except Exception:
    try:
        from whoisxmlapi import (  # type: ignore
            get_whois_history,
            reverse_whois_search,
            reverse_nameserver_search,
            normalize_domain,
            fetch_current_whois_record,
        )
    except ImportError:
        from eyed.whoisxmlapi import (  # type: ignore
            get_whois_history,
            reverse_whois_search,
            reverse_nameserver_search,
            normalize_domain,
            fetch_current_whois_record,
        )
    WHOIS_DISCOVERY_AVAILABLE = False

# Maintain CLI behavior
MAX_DOMAINS_TO_DETAIL = 10


def whois_lookup(query: str, query_type: str = "domain") -> dict:
    """Run historic WHOIS lookup or reverse WHOIS search."""
    try:
        if query_type == "domain":
            records = get_whois_history(query)
            return {
                "query": query,
                "query_type": query_type,
                "records": records,
                "count": len(records),
            }
        if query_type == "email":
            return reverse_whois_search(query, "basicSearchTerms")
        if query_type == "terms":
            return reverse_whois_search(query, "basicSearchTerms")
        if query_type == "phone":
            clean_number = re.sub(r"\D", "", query)
            return reverse_whois_search(clean_number, "basicSearchTerms", search_field="telephone")
        return reverse_whois_search(query, "basicSearchTerms")
    except WhoisApiException as exc:
        return {"query": query, "query_type": query_type, "error": str(exc)}
    except Exception as exc:
        return {"query": query, "query_type": query_type, "error": f"Unexpected error: {exc}"}


def _serialize_structured_record(record) -> dict:
    return {
        "domain": record.domain,
        "registrant": {
            "name": record.registrant_name,
            "organization": record.registrant_org,
            "email": record.registrant_email,
            "country": record.registrant_country,
        },
        "registrar": record.registrar,
        "dates": {
            "created": record.created_date,
            "updated": record.updated_date,
            "expires": record.expires_date,
        },
        "nameservers": record.nameservers or [],
        "status": record.status or [],
    }


def structured_whois_history(domain: str) -> dict:
    """Return structured WHOIS history (Linklater format) alongside distinct registrants."""
    try:
        if WHOIS_DISCOVERY_AVAILABLE and hasattr(linklater_whois, "historic_whois_lookup_sync"):
            history_records = linklater_whois.historic_whois_lookup_sync(domain)
            structured = [_serialize_structured_record(record) for record in history_records]
            distinct = (
                linklater_whois.find_all_distinct_registrants(history_records)
                if hasattr(linklater_whois, "find_all_distinct_registrants")
                else []
            )
            return {
                "domain": domain,
                "count": len(structured),
                "records": structured,
                "distinct_registrants": distinct,
                "source": "linklater_structured",
            }

        raw_records = get_whois_history(domain)
        structured = []
        for record in raw_records:
            if not isinstance(record, dict):
                continue
            registrant = record.get("registrantContact", {}) or {}
            nameservers = record.get("nameServers", [])
            if isinstance(nameservers, dict):
                nameservers = nameservers.get("hostNames", []) or []
            if isinstance(nameservers, str):
                nameservers = [nameservers]
            status = record.get("status", [])
            if isinstance(status, str):
                status = [status]

            structured.append({
                "domain": record.get("domainName", domain),
                "registrant": {
                    "name": registrant.get("name"),
                    "organization": registrant.get("organization"),
                    "email": registrant.get("email"),
                    "country": registrant.get("country"),
                },
                "registrar": record.get("registrarName"),
                "dates": {
                    "created": record.get("createdDateISO8601") or record.get("audit", {}).get("createdDate"),
                    "updated": record.get("updatedDateISO8601"),
                    "expires": record.get("expiresDateISO8601"),
                },
                "nameservers": [ns for ns in nameservers if isinstance(ns, str)],
                "status": status,
            })

        return {
            "domain": domain,
            "count": len(structured),
            "records": structured,
            "distinct_registrants": [],
            "source": "raw_fallback",
        }
    except Exception as exc:
        return {
            "domain": domain,
            "count": 0,
            "records": [],
            "distinct_registrants": [],
            "error": str(exc),
        }


def save_results(results_data: Union[dict, list], query: str, filename_prefix: str):
    """Save results to JSON file."""
    try:
        safe_query = re.sub(r"[^\w\-_.]", "_", query).strip().replace(" ", "_")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{filename_prefix}_{safe_query}_{timestamp}.json"

        output_wrapper = {
            "query_time": datetime.datetime.now().isoformat(),
            "query": query,
            "results": results_data,
        }

        save_path = os.path.join(os.getcwd(), output_file)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(output_wrapper, f, indent=2, default=str)

        print(f"\nFull results saved to {save_path}")
    except IOError as exc:
        print(f"Error saving results to file '{save_path}': {exc}")
    except Exception as exc:
        print(f"Unexpected error saving results: {exc}")


def display_domain_history(domain: str, records: list):
    """Display domain history in a clean format."""
    if not records:
        print(f"\nNo WHOIS history records found for {domain}.")
        return

    print("\n=== WHOIS History Summary ===")
    print(f"Domain: {domain}")
    print(f"Total Records Found: {len(records)}")
    print("=" * 50)

    for i, record in enumerate(records, 1):
        if not isinstance(record, dict):
            print(f"\nSkipping Record {i} - Unexpected format: Expected dictionary, got {type(record)}")
            print("-" * 50)
            continue

        created_audit = record.get("audit", {}).get("createdDate", "N/A")
        print(f"\nRecord {i} - Audit Created: {created_audit}")
        print("-" * 50)

        summary = {}
        if record.get("domainName"):
            summary["Domain Name"] = record["domainName"]
        if record.get("domainType"):
            summary["Domain Type"] = record["domainType"]
        if record.get("createdDateISO8601"):
            summary["Created"] = record["createdDateISO8601"]
        if record.get("updatedDateISO8601"):
            summary["Updated"] = record["updatedDateISO8601"]
        if record.get("expiresDateISO8601"):
            summary["Expires"] = record["expiresDateISO8601"]
        if record.get("registrarName"):
            summary["Registrar"] = record["registrarName"]
        if record.get("whoisServer"):
            summary["WHOIS Server"] = record.get("whoisServer")

        status = record.get("status")
        if status:
            summary["Status"] = ", ".join(status) if isinstance(status, list) else status

        ns_data = record.get("nameServers")
        ns_list = []
        if isinstance(ns_data, dict):
            ns_list = ns_data.get("hostNames", [])
            if not ns_list and "rawText" in ns_data:
                ns_list = [
                    line.strip()
                    for line in ns_data["rawText"].splitlines()
                    if line.strip() and "Name Server" in line
                ]
        elif isinstance(ns_data, list):
            ns_list = ns_data
        if ns_list:
            summary["Name Servers"] = ", ".join(filter(None, ns_list))

        for contact_type in ["registrant", "administrative", "technical", "billing", "zone"]:
            contact_key = f"{contact_type}Contact"
            contact_data = record.get(contact_key)
            if isinstance(contact_data, dict):
                contact_info = {}
                for field in [
                    "name",
                    "organization",
                    "email",
                    "telephone",
                    "street",
                    "city",
                    "state",
                    "postalCode",
                    "country",
                ]:
                    value = contact_data.get(field)
                    if value and not any(
                        term in str(value).upper()
                        for term in ["REDACTED", "PRIVACY", "PROTECTION", "PROXY", "GUARD", "PRIVATE REGISTRANT", "WHOISGUARD"]
                    ):
                        display_field = field.replace("postalCode", "Postal Code").capitalize()
                        contact_info[display_field] = value
                if contact_info:
                    summary[f"{contact_type.title()} Contact"] = contact_info

        for key, value in summary.items():
            if isinstance(value, dict):
                print(f"\n{key}:")
                for k, v in value.items():
                    print(f"  {k}: {v}")
            else:
                print(f"{key}: {value}")

        print("-" * 50)


def display_reverse_whois(results: dict):
    """Display reverse WHOIS results, attempting to find registrant details from historical records."""
    print("=== Reverse WHOIS Search Results ===")
    search_term = results.get("search_term", "N/A")
    search_type = results.get("search_type", "N/A")
    print(f"Search term: {search_term}")
    print(f"Search type: {search_type}")
    print(f"Total domains found: {results.get('domains_count', 0)}")
    print("=" * 50)

    normalized_search_term = search_term
    is_phone_search = search_type == "phone" or (search_type == "basicSearchTerms" and re.match(r"^\+?\d+$", search_term))
    if is_phone_search:
        normalized_search_term = re.sub(r"\D", "", search_term)
    is_email_search = "@" in search_term and search_type in ["email", "basicSearchTerms"]
    is_terms_search = not is_phone_search and not is_email_search

    if results.get("error"):
        print(f"Error: {results['error']}")
    elif results.get("domains_count", 0) > 0 and results.get("domains"):
        domains_list = results["domains"]
        print(
            f"Associated domains (checking history for first {min(len(domains_list), MAX_DOMAINS_TO_DETAIL)} for relevant contact):"
        )

        for i, domain in enumerate(domains_list):
            if i < MAX_DOMAINS_TO_DETAIL:
                print(f"  {i+1}. {domain}")
                try:
                    time.sleep(1.2)
                    print(f"      Fetching full history for {domain}...")
                    history_records = get_whois_history(domain)

                    if not history_records or not isinstance(history_records, list):
                        print(f"        Could not fetch or parse history details for {domain}.")
                        continue

                    match_found_for_domain = False
                    print(f"      Scanning {len(history_records)} historical records for connection to '{search_term}'...")

                    for record in history_records:
                        if not isinstance(record, dict):
                            continue

                        record_date = record.get("audit", {}).get("createdDate", "Unknown Date")
                        contacts_to_check = []
                        for contact_type_key in [
                            "registrantContact",
                            "administrativeContact",
                            "technicalContact",
                            "billingContact",
                        ]:
                            contact_data = record.get(contact_type_key)
                            if isinstance(contact_data, dict):
                                contacts_to_check.append(contact_data)

                        for contact_data in contacts_to_check:
                            match_in_contact = False
                            details_to_display = {}

                            if is_email_search and str(contact_data.get("email", "")).lower() == search_term.lower():
                                match_in_contact = True
                            elif is_phone_search:
                                phone_in_record = re.sub(r"\D", "", str(contact_data.get("telephone", "")))
                                if phone_in_record and phone_in_record == normalized_search_term:
                                    match_in_contact = True
                            elif is_terms_search:
                                name_in_record = str(contact_data.get("name", "")).lower()
                                org_in_record = str(contact_data.get("organization", "")).lower()
                                search_term_lower = search_term.lower()
                                if (search_term_lower in name_in_record) or (search_term_lower in org_in_record):
                                    match_in_contact = True

                            if match_in_contact:
                                print(f"        Match found in record from ~{record_date}")
                                for field in [
                                    "name",
                                    "organization",
                                    "email",
                                    "telephone",
                                    "street",
                                    "city",
                                    "state",
                                    "postalCode",
                                    "country",
                                ]:
                                    value = contact_data.get(field)
                                    if value and not any(
                                        term in str(value).upper()
                                        for term in ["REDACTED", "PRIVACY", "PROTECTION", "PROXY", "GUARD", "PRIVATE REGISTRANT", "WHOISGUARD"]
                                    ):
                                        display_field = field.replace("postalCode", "Postal Code").capitalize()
                                        details_to_display[display_field] = value

                                if details_to_display:
                                    for k, v in details_to_display.items():
                                        print(f"          {k}: {v}")
                                else:
                                    print("          Contact details in matching record appear redacted.")

                                match_found_for_domain = True
                                break

                        if match_found_for_domain:
                            break

                    if not match_found_for_domain:
                        print(
                            f"        Could not find specific historical contact linking to '{search_term}' (or details were redacted)."
                        )

                except WhoisApiException as exc:
                    print(f"        API Error processing history for {domain}: {exc}")
                except Exception as exc:
                    print(f"        Unexpected Error processing history for {domain}: {exc}")
            else:
                if i == MAX_DOMAINS_TO_DETAIL:
                    print(f"  --- Remaining {len(domains_list) - MAX_DOMAINS_TO_DETAIL} domains (history not checked) ---")
                print(f"  {i+1}. {domain}")

        print("\nNote: Full WHOIS history may be available by running a direct domain search.")
    else:
        print("No domains found matching this search term.")


def main():
    """Main function for command-line usage."""
    print("WhoisXMLAPI Search Tool")
    print("========================")
    print("1: Domain WHOIS History")
    print("2: Email Reverse WHOIS")
    print("3: Name/Company Reverse WHOIS")
    print("4: Phone Reverse WHOIS")

    choice = input("Enter type of search (1-4): ")

    query = None
    results_data = None
    filename_prefix = "whois"

    try:
        if choice == "1":
            query = input("Enter domain name: ")
            filename_prefix = "history"
            print(f"\nSearching WHOIS history for domain: {query}")
            records = get_whois_history(query)
            results_data = records
            display_domain_history(query, records)
        elif choice == "2":
            query = input("Enter email address: ")
            filename_prefix = "reverse_email"
            print(f"\nPerforming reverse WHOIS search for email: {query}")
            results_data = whois_lookup(query, query_type="email")
            display_reverse_whois(results_data)
        elif choice == "3":
            query = input("Enter name or company: ")
            filename_prefix = "reverse_terms"
            print(f"\nPerforming reverse WHOIS search for name/company: {query}")
            results_data = whois_lookup(query, query_type="terms")
            display_reverse_whois(results_data)
        elif choice == "4":
            query = input("Enter phone number (include country code if possible): ")
            filename_prefix = "reverse_phone"
            print(f"\nPerforming reverse WHOIS search for phone number: {query}")
            results_data = whois_lookup(query, query_type="phone")
            display_reverse_whois(results_data)
        else:
            print("Invalid choice.")
            return

        if results_data is not None:
            is_api_error = isinstance(results_data, dict) and results_data.get("error")
            is_empty_history = isinstance(results_data, list) and not results_data
            is_empty_reverse = isinstance(results_data, dict) and results_data.get("domains_count", 0) == 0

            if is_api_error:
                print("\nSkipping save due to API error during lookup.")
            elif is_empty_history or is_empty_reverse:
                print("\nNo records or domains found to save.")
            else:
                save_results(results_data, query, filename_prefix)
    except WhoisApiException as exc:
        print(f"\nAPI Error encountered: {exc}")
        if exc.response_text:
            print(f"API Response: {exc.response_text[:500]}...")
    except Exception as exc:
        print(f"\nAn unexpected error occurred: {exc}")


if __name__ == "__main__":
    main()
