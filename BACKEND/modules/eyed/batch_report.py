#!/usr/bin/env python3
"""
EYE-D Batch Report Generator

Run a list of emails, phones, and names through EYE-D and generate full reports.

Usage:
    python batch_report.py --input entities.txt --output output/
    python batch_report.py --emails "a@b.com,c@d.com" --phones "+1234567890" --names "John Doe"
"""

import asyncio
import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add EYE-D to path
EYED_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(EYED_ROOT))

from unified_osint import UnifiedSearcher


class BatchReporter:
    """Run batch OSINT searches and generate reports."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.searcher = UnifiedSearcher()
        self.all_results = []

    async def search_email(self, email: str) -> Dict:
        """Search single email."""
        print(f"\n{'='*60}")
        print(f"📧 Searching email: {email}")
        print(f"{'='*60}")
        try:
            result = await self.searcher.search_email(email)
            result['_search_type'] = 'email'
            result['_search_value'] = email
            return result
        except Exception as e:
            print(f"❌ Error searching {email}: {e}")
            return {'error': str(e), '_search_type': 'email', '_search_value': email}

    async def search_phone(self, phone: str) -> Dict:
        """Search single phone."""
        print(f"\n{'='*60}")
        print(f"📱 Searching phone: {phone}")
        print(f"{'='*60}")
        try:
            result = await self.searcher.search_phone(phone)
            result['_search_type'] = 'phone'
            result['_search_value'] = phone
            return result
        except Exception as e:
            print(f"❌ Error searching {phone}: {e}")
            return {'error': str(e), '_search_type': 'phone', '_search_value': phone}

    async def search_name(self, name: str) -> Dict:
        """Search single name."""
        print(f"\n{'='*60}")
        print(f"👤 Searching name: {name}")
        print(f"{'='*60}")
        try:
            result = await self.searcher.search_people(name)
            result['_search_type'] = 'name'
            result['_search_value'] = name
            return result
        except Exception as e:
            print(f"❌ Error searching {name}: {e}")
            return {'error': str(e), '_search_type': 'name', '_search_value': name}

    async def run_batch(
        self,
        emails: List[str] = None,
        phones: List[str] = None,
        names: List[str] = None
    ) -> List[Dict]:
        """Run batch searches for all entities."""
        emails = emails or []
        phones = phones or []
        names = names or []

        total = len(emails) + len(phones) + len(names)
        print(f"\n{'#'*60}")
        print(f"# EYE-D BATCH SEARCH")
        print(f"# Emails: {len(emails)} | Phones: {len(phones)} | Names: {len(names)}")
        print(f"# Total: {total} entities")
        print(f"{'#'*60}")

        results = []
        current = 0

        # Search emails
        for email in emails:
            current += 1
            print(f"\n[{current}/{total}]", end="")
            result = await self.search_email(email.strip())
            results.append(result)

        # Search phones
        for phone in phones:
            current += 1
            print(f"\n[{current}/{total}]", end="")
            result = await self.search_phone(phone.strip())
            results.append(result)

        # Search names
        for name in names:
            current += 1
            print(f"\n[{current}/{total}]", end="")
            result = await self.search_name(name.strip())
            results.append(result)

        self.all_results = results
        return results

    def generate_entity_report(self, result: Dict) -> str:
        """Generate markdown report for single entity."""
        search_type = result.get('_search_type', 'unknown')
        search_value = result.get('_search_value', 'unknown')

        report = []
        report.append(f"# {search_type.upper()}: {search_value}")
        report.append(f"\n*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")

        if result.get('error'):
            report.append(f"\n## Error\n\n{result['error']}\n")
            return '\n'.join(report)

        # Summary
        total_results = result.get('total_results', 0)
        entities_found = len(result.get('entities', []))
        report.append(f"## Summary\n")
        report.append(f"- **Results Found:** {total_results}")
        report.append(f"- **Entities Extracted:** {entities_found}")
        report.append("")

        # Results by source
        results_list = result.get('results', [])
        if results_list:
            report.append(f"## Data Sources ({len(results_list)})\n")

            for i, res in enumerate(results_list, 1):
                source = res.get('source', 'unknown')
                report.append(f"### {i}. {source.upper()}\n")

                # Handle different result types
                data = res.get('data', {})

                if source == 'dehashed':
                    # Breach data
                    if isinstance(data, list):
                        report.append(f"**Breach Records:** {len(data)}\n")
                        for j, record in enumerate(data[:10], 1):  # Limit display
                            report.append(f"**Record {j}:**")
                            if record.get('database_name'):
                                report.append(f"- Database: {record['database_name']}")
                            if record.get('email'):
                                report.append(f"- Email: {record['email']}")
                            if record.get('username'):
                                report.append(f"- Username: {record['username']}")
                            if record.get('name'):
                                report.append(f"- Name: {record['name']}")
                            if record.get('phone'):
                                report.append(f"- Phone: {record['phone']}")
                            if record.get('ip_address'):
                                report.append(f"- IP: {record['ip_address']}")
                            if record.get('address'):
                                report.append(f"- Address: {record['address']}")
                            report.append("")
                        if len(data) > 10:
                            report.append(f"*... and {len(data) - 10} more records*\n")
                    else:
                        report.append(f"```json\n{json.dumps(data, indent=2, default=str)[:2000]}\n```\n")

                elif source in ['brute_web_search', 'brute_name_variations', 'brute_web_linkedin']:
                    # Web search results
                    if isinstance(data, list):
                        report.append(f"**URLs Found:** {len(data)}\n")
                        for url_data in data[:15]:
                            if isinstance(url_data, dict):
                                url = url_data.get('url', url_data.get('link', ''))
                                title = url_data.get('title', '')
                                report.append(f"- [{title[:60]}...]({url})" if title else f"- {url}")
                            else:
                                report.append(f"- {url_data}")
                        if len(data) > 15:
                            report.append(f"\n*... and {len(data) - 15} more URLs*")
                        report.append("")
                    else:
                        report.append(f"```json\n{json.dumps(data, indent=2, default=str)[:1500]}\n```\n")

                elif source == 'whoisxmlapi_reverse':
                    # WHOIS domains
                    domains = data.get('domains', []) if isinstance(data, dict) else []
                    if domains:
                        report.append(f"**Domains Registered:** {len(domains)}\n")
                        for domain in domains[:20]:
                            report.append(f"- {domain}")
                        if len(domains) > 20:
                            report.append(f"\n*... and {len(domains) - 20} more domains*")
                        report.append("")
                    else:
                        report.append(f"```json\n{json.dumps(data, indent=2, default=str)[:1500]}\n```\n")

                elif source == 'cymonides_index':
                    # Cymonides records
                    if isinstance(data, list):
                        report.append(f"**Index Records:** {len(data)}\n")
                        for record in data[:10]:
                            if isinstance(record, dict):
                                report.append(f"- {record.get('name', '')} | {record.get('phone', '')} | {record.get('company', '')}")
                        report.append("")
                    else:
                        report.append(f"```json\n{json.dumps(data, indent=2, default=str)[:1500]}\n```\n")

                elif source == 'sherlock':
                    # Social profiles
                    if isinstance(data, list):
                        report.append(f"**Profiles Found:** {len(data)}\n")
                        for profile in data[:20]:
                            if isinstance(profile, dict):
                                site = profile.get('site', profile.get('name', 'unknown'))
                                url = profile.get('url', '')
                                report.append(f"- **{site}**: {url}")
                        report.append("")
                    else:
                        report.append(f"```json\n{json.dumps(data, indent=2, default=str)[:1500]}\n```\n")

                else:
                    # Generic data dump
                    if isinstance(data, (dict, list)):
                        report.append(f"```json\n{json.dumps(data, indent=2, default=str)[:2000]}\n```\n")
                    else:
                        report.append(f"{data}\n")

        # Extracted entities
        entities = result.get('entities', [])
        if entities:
            report.append(f"## Extracted Entities ({len(entities)})\n")

            # Group by type
            by_type = {}
            for ent in entities:
                etype = ent.get('type', 'OTHER')
                if etype not in by_type:
                    by_type[etype] = []
                by_type[etype].append(ent)

            for etype, ents in sorted(by_type.items()):
                report.append(f"### {etype} ({len(ents)})\n")
                seen = set()
                for ent in ents[:25]:
                    val = ent.get('value', '')
                    if val and val not in seen:
                        seen.add(val)
                        ctx = ent.get('context', '')
                        report.append(f"- {val}" + (f" *({ctx})*" if ctx else ""))
                if len(ents) > 25:
                    report.append(f"\n*... and {len(ents) - 25} more*")
                report.append("")

        # WHOIS domains (if separate)
        whois_domains = result.get('whois_domains', [])
        if whois_domains:
            report.append(f"## WHOIS Domains ({len(whois_domains)})\n")
            for domain in whois_domains[:30]:
                report.append(f"- {domain}")
            if len(whois_domains) > 30:
                report.append(f"\n*... and {len(whois_domains) - 30} more*")
            report.append("")

        return '\n'.join(report)

    def generate_full_report(self) -> str:
        """Generate combined report for all searches."""
        report = []
        report.append("# EYE-D OSINT BATCH REPORT")
        report.append(f"\n*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")
        report.append(f"**Total Entities Searched:** {len(self.all_results)}\n")

        # Table of contents
        report.append("## Table of Contents\n")
        for i, result in enumerate(self.all_results, 1):
            stype = result.get('_search_type', 'unknown')
            sval = result.get('_search_value', 'unknown')
            report.append(f"{i}. [{stype.upper()}: {sval}](#{stype}-{sval.replace('@', '').replace(' ', '-').replace('.', '').lower()})")
        report.append("\n---\n")

        # Individual reports
        for result in self.all_results:
            report.append(self.generate_entity_report(result))
            report.append("\n---\n")

        return '\n'.join(report)

    def save_reports(self, prefix: str = "eyed_report"):
        """Save all reports to files."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Save combined report
        combined_path = self.output_dir / f"{prefix}_{timestamp}_FULL.md"
        with open(combined_path, 'w') as f:
            f.write(self.generate_full_report())
        print(f"\n📄 Full report: {combined_path}")

        # Save individual reports
        for result in self.all_results:
            stype = result.get('_search_type', 'unknown')
            sval = result.get('_search_value', 'unknown').replace('@', '_at_').replace(' ', '_').replace('.', '_')
            ind_path = self.output_dir / f"{prefix}_{timestamp}_{stype}_{sval}.md"
            with open(ind_path, 'w') as f:
                f.write(self.generate_entity_report(result))

        # Save raw JSON
        json_path = self.output_dir / f"{prefix}_{timestamp}_RAW.json"
        with open(json_path, 'w') as f:
            json.dump(self.all_results, f, indent=2, default=str)
        print(f"📊 Raw JSON: {json_path}")

        return combined_path


def parse_input_file(filepath: str) -> Dict[str, List[str]]:
    """Parse input file with entities (one per line, auto-detect type)."""
    import re

    emails = []
    phones = []
    names = []

    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Auto-detect type
            if '@' in line and '.' in line:
                emails.append(line)
            elif re.match(r'^[\+\d\s\-\(\)]{7,}$', line):
                phones.append(line)
            else:
                names.append(line)

    return {'emails': emails, 'phones': phones, 'names': names}


async def main():
    parser = argparse.ArgumentParser(description='EYE-D Batch OSINT Report Generator')
    parser.add_argument('--input', '-i', help='Input file with entities (one per line)')
    parser.add_argument('--output', '-o', default='output', help='Output directory for reports')
    parser.add_argument('--emails', '-e', help='Comma-separated emails')
    parser.add_argument('--phones', '-p', help='Comma-separated phones')
    parser.add_argument('--names', '-n', help='Comma-separated names')
    parser.add_argument('--prefix', default='eyed_report', help='Report filename prefix')

    args = parser.parse_args()

    emails = []
    phones = []
    names = []

    # Parse input file
    if args.input:
        parsed = parse_input_file(args.input)
        emails.extend(parsed['emails'])
        phones.extend(parsed['phones'])
        names.extend(parsed['names'])

    # Parse command line args
    if args.emails:
        emails.extend([e.strip() for e in args.emails.split(',')])
    if args.phones:
        phones.extend([p.strip() for p in args.phones.split(',')])
    if args.names:
        names.extend([n.strip() for n in args.names.split(',')])

    if not emails and not phones and not names:
        print("No entities provided. Use --input FILE or --emails/--phones/--names")
        parser.print_help()
        return

    # Run batch search
    reporter = BatchReporter(output_dir=args.output)
    await reporter.run_batch(emails=emails, phones=phones, names=names)

    # Generate and save reports
    report_path = reporter.save_reports(prefix=args.prefix)

    print(f"\n{'='*60}")
    print(f"✅ BATCH COMPLETE")
    print(f"📁 Reports saved to: {args.output}/")
    print(f"{'='*60}")


if __name__ == '__main__':
    asyncio.run(main())
