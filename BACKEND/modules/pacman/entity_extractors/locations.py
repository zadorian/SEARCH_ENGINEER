"""
PACMAN Location/Jurisdiction Extractor
Extracts countries, cities, and jurisdictional references from text
"""

import re
from typing import List, Dict, Set

# Major jurisdictions and their variations
COUNTRIES = {
    # Full names mapped to ISO code
    'UNITED STATES': 'US', 'USA': 'US', 'U.S.A.': 'US', 'U.S.': 'US', 'AMERICA': 'US',
    'UNITED KINGDOM': 'GB', 'UK': 'GB', 'U.K.': 'GB', 'BRITAIN': 'GB', 'GREAT BRITAIN': 'GB', 'ENGLAND': 'GB', 'SCOTLAND': 'GB', 'WALES': 'GB',
    'GERMANY': 'DE', 'DEUTSCHLAND': 'DE',
    'FRANCE': 'FR',
    'ITALY': 'IT', 'ITALIA': 'IT',
    'SPAIN': 'ES', 'ESPANA': 'ES',
    'NETHERLANDS': 'NL', 'HOLLAND': 'NL', 'THE NETHERLANDS': 'NL',
    'BELGIUM': 'BE', 'BELGIQUE': 'BE',
    'SWITZERLAND': 'CH', 'SCHWEIZ': 'CH', 'SUISSE': 'CH',
    'AUSTRIA': 'AT', 'OSTERREICH': 'AT',
    'SWEDEN': 'SE', 'SVERIGE': 'SE',
    'NORWAY': 'NO', 'NORGE': 'NO',
    'DENMARK': 'DK', 'DANMARK': 'DK',
    'FINLAND': 'FI', 'SUOMI': 'FI',
    'IRELAND': 'IE', 'EIRE': 'IE',
    'PORTUGAL': 'PT',
    'GREECE': 'GR', 'HELLAS': 'GR',
    'POLAND': 'PL', 'POLSKA': 'PL',
    'CZECH REPUBLIC': 'CZ', 'CZECHIA': 'CZ',
    'HUNGARY': 'HU', 'MAGYARORSZAG': 'HU',
    'ROMANIA': 'RO',
    'BULGARIA': 'BG',
    'CROATIA': 'HR', 'HRVATSKA': 'HR',
    'SLOVENIA': 'SI',
    'SLOVAKIA': 'SK',
    'ESTONIA': 'EE', 'EESTI': 'EE',
    'LATVIA': 'LV', 'LATVIJA': 'LV',
    'LITHUANIA': 'LT', 'LIETUVA': 'LT',
    'LUXEMBOURG': 'LU',
    'MALTA': 'MT',
    'CYPRUS': 'CY',
    'ICELAND': 'IS',
    'RUSSIA': 'RU', 'RUSSIAN FEDERATION': 'RU',
    'UKRAINE': 'UA',
    'BELARUS': 'BY',
    'TURKEY': 'TR', 'TURKIYE': 'TR',
    'ISRAEL': 'IL',
    'UNITED ARAB EMIRATES': 'AE', 'UAE': 'AE', 'DUBAI': 'AE',
    'SAUDI ARABIA': 'SA',
    'QATAR': 'QA',
    'KUWAIT': 'KW',
    'BAHRAIN': 'BH',
    'OMAN': 'OM',
    'EGYPT': 'EG',
    'SOUTH AFRICA': 'ZA',
    'NIGERIA': 'NG',
    'KENYA': 'KE',
    'MOROCCO': 'MA',
    'TUNISIA': 'TN',
    'ALGERIA': 'DZ',
    'LIBYA': 'LY',
    'CHINA': 'CN', 'PEOPLES REPUBLIC OF CHINA': 'CN', 'PRC': 'CN',
    'JAPAN': 'JP', 'NIPPON': 'JP',
    'SOUTH KOREA': 'KR', 'KOREA': 'KR',
    'INDIA': 'IN',
    'PAKISTAN': 'PK',
    'BANGLADESH': 'BD',
    'INDONESIA': 'ID',
    'MALAYSIA': 'MY',
    'SINGAPORE': 'SG',
    'THAILAND': 'TH',
    'VIETNAM': 'VN',
    'PHILIPPINES': 'PH',
    'AUSTRALIA': 'AU',
    'NEW ZEALAND': 'NZ',
    'CANADA': 'CA',
    'MEXICO': 'MX',
    'BRAZIL': 'BR', 'BRASIL': 'BR',
    'ARGENTINA': 'AR',
    'CHILE': 'CL',
    'COLOMBIA': 'CO',
    'PERU': 'PE',
    'VENEZUELA': 'VE',
    # Offshore/Special jurisdictions
    'CAYMAN ISLANDS': 'KY', 'CAYMANS': 'KY',
    'BRITISH VIRGIN ISLANDS': 'VG', 'BVI': 'VG',
    'VIRGIN ISLANDS': 'VG',
    'BERMUDA': 'BM',
    'BAHAMAS': 'BS',
    'PANAMA': 'PA',
    'BELIZE': 'BZ',
    'SEYCHELLES': 'SC',
    'MAURITIUS': 'MU',
    'JERSEY': 'JE',
    'GUERNSEY': 'GG',
    'ISLE OF MAN': 'IM',
    'GIBRALTAR': 'GI',
    'LIECHTENSTEIN': 'LI',
    'MONACO': 'MC',
    'ANDORRA': 'AD',
    'SAN MARINO': 'SM',
    'HONG KONG': 'HK',
    'MACAU': 'MO', 'MACAO': 'MO',
    'TAIWAN': 'TW',
    'DELAWARE': 'US-DE',  # US state known for incorporation
    'NEVADA': 'US-NV',
    'WYOMING': 'US-WY',
}

# Major financial/business cities
CITIES = {
    'NEW YORK': 'US', 'NYC': 'US', 'MANHATTAN': 'US',
    'LOS ANGELES': 'US', 'LA': 'US',
    'CHICAGO': 'US',
    'HOUSTON': 'US',
    'MIAMI': 'US',
    'SAN FRANCISCO': 'US',
    'BOSTON': 'US',
    'WASHINGTON': 'US', 'DC': 'US', 'WASHINGTON DC': 'US',
    'LONDON': 'GB',
    'MANCHESTER': 'GB',
    'BIRMINGHAM': 'GB',
    'EDINBURGH': 'GB',
    'GLASGOW': 'GB',
    'PARIS': 'FR',
    'LYON': 'FR',
    'MARSEILLE': 'FR',
    'BERLIN': 'DE',
    'FRANKFURT': 'DE',
    'MUNICH': 'DE', 'MUNCHEN': 'DE',
    'HAMBURG': 'DE',
    'DUSSELDORF': 'DE',
    'COLOGNE': 'DE', 'KOLN': 'DE',
    'AMSTERDAM': 'NL',
    'ROTTERDAM': 'NL',
    'THE HAGUE': 'NL', 'DEN HAAG': 'NL',
    'BRUSSELS': 'BE', 'BRUXELLES': 'BE',
    'ANTWERP': 'BE', 'ANTWERPEN': 'BE',
    'ZURICH': 'CH', 'ZUERICH': 'CH',
    'GENEVA': 'CH', 'GENEVE': 'CH',
    'BASEL': 'CH',
    'VIENNA': 'AT', 'WIEN': 'AT',
    'STOCKHOLM': 'SE',
    'GOTHENBURG': 'SE', 'GOTEBORG': 'SE',
    'MALMO': 'SE',
    'OSLO': 'NO',
    'COPENHAGEN': 'DK', 'KOBENHAVN': 'DK',
    'HELSINKI': 'FI',
    'DUBLIN': 'IE',
    'MADRID': 'ES',
    'BARCELONA': 'ES',
    'MILAN': 'IT', 'MILANO': 'IT',
    'ROME': 'IT', 'ROMA': 'IT',
    'LISBON': 'PT', 'LISBOA': 'PT',
    'ATHENS': 'GR',
    'WARSAW': 'PL', 'WARSZAWA': 'PL',
    'PRAGUE': 'CZ', 'PRAHA': 'CZ',
    'BUDAPEST': 'HU',
    'BUCHAREST': 'RO',
    'MOSCOW': 'RU', 'MOSKVA': 'RU',
    'ST PETERSBURG': 'RU', 'SAINT PETERSBURG': 'RU',
    'KYIV': 'UA', 'KIEV': 'UA',
    'ISTANBUL': 'TR',
    'TEL AVIV': 'IL',
    'JERUSALEM': 'IL',
    'DUBAI': 'AE',
    'ABU DHABI': 'AE',
    'RIYADH': 'SA',
    'DOHA': 'QA',
    'CAIRO': 'EG',
    'JOHANNESBURG': 'ZA',
    'CAPE TOWN': 'ZA',
    'LAGOS': 'NG',
    'NAIROBI': 'KE',
    'BEIJING': 'CN', 'PEKING': 'CN',
    'SHANGHAI': 'CN',
    'SHENZHEN': 'CN',
    'GUANGZHOU': 'CN',
    'HONG KONG': 'HK',
    'TOKYO': 'JP',
    'OSAKA': 'JP',
    'SEOUL': 'KR',
    'MUMBAI': 'IN', 'BOMBAY': 'IN',
    'DELHI': 'IN', 'NEW DELHI': 'IN',
    'BANGALORE': 'IN', 'BENGALURU': 'IN',
    'SINGAPORE': 'SG',
    'KUALA LUMPUR': 'MY',
    'BANGKOK': 'TH',
    'JAKARTA': 'ID',
    'SYDNEY': 'AU',
    'MELBOURNE': 'AU',
    'TORONTO': 'CA',
    'VANCOUVER': 'CA',
    'MONTREAL': 'CA',
    'MEXICO CITY': 'MX',
    'SAO PAULO': 'BR',
    'RIO DE JANEIRO': 'BR',
    'BUENOS AIRES': 'AR',
    'SANTIAGO': 'CL',
    'GEORGE TOWN': 'KY',  # Cayman Islands
    'ROAD TOWN': 'VG',  # BVI
    'NASSAU': 'BS',
    'PANAMA CITY': 'PA',
    'HAMILTON': 'BM',
    'VICTORIA': 'SC',  # Seychelles
    'PORT LOUIS': 'MU',
    'ST HELIER': 'JE',
    'ST PETER PORT': 'GG',
    'DOUGLAS': 'IM',
    'VADUZ': 'LI',
}

# Jurisdictional terms (regulatory/legal contexts)
JURISDICTION_TERMS = [
    'JURISDICTION', 'INCORPORATED', 'REGISTERED', 'DOMICILED',
    'HEADQUARTERED', 'BASED IN', 'LOCATED IN', 'RESIDENT OF',
    'CITIZEN OF', 'NATIONAL OF', 'UNDER THE LAWS OF',
    'GOVERNED BY', 'SUBJECT TO', 'REGULATED BY',
]


def extract_locations(text: str, max_results: int = 100) -> List[Dict]:
    """
    Extract locations/jurisdictions from text.
    Returns list of dicts with: name, type (country/city), iso_code, context
    """
    if not text:
        return []

    text_upper = text.upper()
    results = []
    seen = set()

    # Extract countries
    for name, iso in COUNTRIES.items():
        if name in text_upper:
            if iso not in seen:
                # Find actual position for context
                pattern = re.compile(re.escape(name), re.IGNORECASE)
                match = pattern.search(text)
                if match:
                    context = _extract_context(text, match.start(), match.end())
                    results.append({
                        'name': name.title() if len(name) > 3 else name,
                        'type': 'country',
                        'iso_code': iso,
                        'context': context,
                        'confidence': 0.9
                    })
                    seen.add(iso)

    # Extract cities
    for name, country_iso in CITIES.items():
        if name in text_upper:
            key = f"city:{name}"
            if key not in seen:
                pattern = re.compile(re.escape(name), re.IGNORECASE)
                match = pattern.search(text)
                if match:
                    context = _extract_context(text, match.start(), match.end())
                    results.append({
                        'name': name.title(),
                        'type': 'city',
                        'iso_code': country_iso,
                        'context': context,
                        'confidence': 0.85
                    })
                    seen.add(key)

    # Sort by confidence and limit
    results.sort(key=lambda x: x['confidence'], reverse=True)
    return results[:max_results]


def _extract_context(text: str, start: int, end: int, window: int = 10) -> str:
    """Extract context around a match (+/- N words)"""
    words_before = text[:start].split()
    matched_text = text[start:end]
    words_after = text[end:].split()

    context_before = ' '.join(words_before[-window:]) if words_before else ''
    context_after = ' '.join(words_after[:window]) if words_after else ''

    context = ''
    if context_before:
        context = '...' + context_before + ' '
    context += f'[{matched_text}]'
    if context_after:
        context += ' ' + context_after + '...'

    return context.strip()


def get_jurisdiction_from_text(text: str) -> List[Dict]:
    """
    Extract jurisdictions mentioned in legal/regulatory context.
    Looks for patterns like "incorporated in X", "registered in Y"
    """
    results = []
    text_upper = text.upper()

    for term in JURISDICTION_TERMS:
        if term in text_upper:
            # Look for location after the term
            pattern = rf'{term}\s+(?:THE\s+)?([A-Z][A-Za-z\s]+?)(?:\.|,|\s+AND|\s+OR|\s+WITH|\s+UNDER|\s+AS|\s+TO|\s+BY|$)'
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                location = match.group(1).strip().upper()
                # Check if it's a known location
                if location in COUNTRIES:
                    results.append({
                        'name': location.title(),
                        'type': 'jurisdiction',
                        'iso_code': COUNTRIES[location],
                        'legal_context': term.lower(),
                        'context': _extract_context(text, match.start(), match.end())
                    })

    return results


# Combine all location extractors
def extract_all_locations(text: str, max_results: int = 100) -> List[Dict]:
    """Extract all location types with deduplication"""
    locations = extract_locations(text, max_results)
    jurisdictions = get_jurisdiction_from_text(text)

    # Merge, preferring jurisdiction context when available
    seen = {}
    for loc in jurisdictions + locations:
        key = loc.get('iso_code', loc['name'])
        if key not in seen:
            seen[key] = loc
        elif loc.get('legal_context'):
            # Prefer entries with legal context
            seen[key] = loc

    return list(seen.values())[:max_results]
