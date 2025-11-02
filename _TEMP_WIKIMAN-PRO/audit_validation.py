#!/usr/bin/env python3
"""
OPUS AUDIT: Granular line-by-line verification of input validation
"""

import os
import re
from pathlib import Path

# Handler list
HANDLERS = ["uk", "sg", "hk", "au", "jp", "de", "fr", "hu", "it", "nl", "es"]

def audit_handler(country_code):
    """Audit a single handler for proper validation implementation."""
    handler_path = Path(f"countries/{country_code}/handler.py")

    if not handler_path.exists():
        return f"❌ {country_code}: FILE NOT FOUND"

    with open(handler_path, 'r') as f:
        lines = f.readlines()

    results = {
        'import': None,
        'company_validation': None,
        'person_validation': None,
        'company_error_handling': None,
        'person_error_handling': None
    }

    # Find import line
    for i, line in enumerate(lines, 1):
        if 'from countries.input_validation import sanitize_input' in line:
            results['import'] = i
            break

    # Find company validation
    for i, line in enumerate(lines, 1):
        if 'company_name = sanitize_input(company_name)' in line:
            results['company_validation'] = i
            # Check for proper error handling
            for j in range(max(0, i-10), min(len(lines), i+10)):
                if 'except ValueError as e:' in lines[j]:
                    results['company_error_handling'] = j + 1
                    break
            break

    # Find person validation
    for i, line in enumerate(lines, 1):
        if 'person_name = sanitize_input(person_name)' in line:
            results['person_validation'] = i
            # Check for proper error handling
            for j in range(max(0, i-10), min(len(lines), i+10)):
                if 'except ValueError as e:' in lines[j]:
                    results['person_error_handling'] = j + 1
                    break
            break

    # Build report
    status = "✅" if all(results.values()) else "❌"
    report = f"\n{status} {country_code.upper()} HANDLER:\n"
    report += f"  Import: Line {results['import'] or 'MISSING'}\n"
    report += f"  Company validation: Line {results['company_validation'] or 'MISSING'}\n"
    report += f"  Company error handling: Line {results['company_error_handling'] or 'MISSING'}\n"
    report += f"  Person validation: Line {results['person_validation'] or 'MISSING'}\n"
    report += f"  Person error handling: Line {results['person_error_handling'] or 'MISSING'}\n"

    # Extract actual code snippets for verification
    if results['company_validation']:
        line_num = results['company_validation'] - 1
        snippet = lines[line_num].strip()
        report += f"  Company code: {snippet}\n"

    if results['person_validation']:
        line_num = results['person_validation'] - 1
        snippet = lines[line_num].strip()
        report += f"  Person code: {snippet}\n"

    return report

def main():
    print("=" * 80)
    print("OPUS GRANULAR AUDIT - INPUT VALIDATION IMPLEMENTATION")
    print("=" * 80)

    all_valid = True
    for handler in HANDLERS:
        report = audit_handler(handler)
        print(report)
        if "❌" in report:
            all_valid = False

    print("=" * 80)
    if all_valid:
        print("✅ ALL 11 HANDLERS PROPERLY VALIDATED")
    else:
        print("❌ VALIDATION ISSUES FOUND")
    print("=" * 80)

if __name__ == "__main__":
    main()