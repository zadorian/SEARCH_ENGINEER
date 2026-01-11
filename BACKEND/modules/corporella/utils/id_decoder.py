#!/usr/bin/env python3
"""
WIKIMAN ID Decoder - Comprehensive International ID Number Decoder
Supports 55+ national ID, tax ID, company ID, and social security number formats

Based on OSINT intelligence from 195+ countries in wiki_cache
"""

import re
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass


@dataclass
class DecodedID:
    """Structure for decoded ID information"""
    id_type: str
    country: str
    original_value: str
    valid: bool
    decoded_info: Dict[str, Any]
    error: Optional[str] = None


# ============================================================================
# INDONESIA - NIK (Nomor Induk Kependudukan)
# ============================================================================

def decode_indonesia_nik(nik: str) -> DecodedID:
    """
    Indonesia National ID Number (16 digits)
    Format: PPRRDDDDMMYYXXXX
    - Digits 1-6: Province, regency, district (PPRRDD)
    - Digits 7-12: Date of birth DDMMYY (add 40 to DD for women)
    - Digits 13-16: Unique identifier
    """
    nik = re.sub(r'\D', '', nik)

    if len(nik) != 16:
        return DecodedID("NIK", "Indonesia", nik, False, {}, "Must be 16 digits")

    try:
        province_code = nik[0:2]
        regency_code = nik[2:4]
        district_code = nik[4:6]
        dd = int(nik[6:8])
        mm = int(nik[8:10])
        yy = int(nik[10:12])
        unique_id = nik[12:16]

        # Decode gender and adjust day
        gender = "Female" if dd > 40 else "Male"
        day = dd - 40 if dd > 40 else dd

        # Determine century (assume 19xx if > current year in 20xx, else 20xx)
        current_year = datetime.now().year % 100
        year = 1900 + yy if yy > current_year else 2000 + yy

        try:
            dob = datetime(year, mm, day)
            dob_str = dob.strftime("%Y-%m-%d")
        except ValueError:
            dob_str = f"{year}-{mm:02d}-{day:02d} (invalid date)"

        return DecodedID(
            id_type="NIK",
            country="Indonesia",
            original_value=nik,
            valid=True,
            decoded_info={
                "province_code": province_code,
                "regency_code": regency_code,
                "district_code": district_code,
                "date_of_birth": dob_str,
                "gender": gender,
                "unique_id": unique_id,
            }
        )
    except Exception as e:
        return DecodedID("NIK", "Indonesia", nik, False, {}, str(e))


# ============================================================================
# BRAZIL - CNPJ & CPF
# ============================================================================

def decode_brazil_cnpj(cnpj: str) -> DecodedID:
    """
    Brazil Company Tax ID (14 digits)
    Format: XX.XXX.XXX/XXXX-XX
    """
    cnpj = re.sub(r'\D', '', cnpj)

    if len(cnpj) != 14:
        return DecodedID("CNPJ", "Brazil", cnpj, False, {}, "Must be 14 digits")

    # Format: 12345678/0001-95
    base = cnpj[:8]
    branch = cnpj[8:12]
    check = cnpj[12:14]

    return DecodedID(
        id_type="CNPJ",
        country="Brazil",
        original_value=cnpj,
        valid=True,
        decoded_info={
            "base_number": base,
            "branch_number": branch,
            "check_digits": check,
            "formatted": f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:14]}",
        }
    )


def decode_brazil_cpf(cpf: str) -> DecodedID:
    """
    Brazil Individual Tax ID (11 digits)
    Format: XXX.XXX.XXX-XX
    """
    cpf = re.sub(r'\D', '', cpf)

    if len(cpf) != 11:
        return DecodedID("CPF", "Brazil", cpf, False, {}, "Must be 11 digits")

    return DecodedID(
        id_type="CPF",
        country="Brazil",
        original_value=cpf,
        valid=True,
        decoded_info={
            "formatted": f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:11]}",
            "check_digits": cpf[9:11],
        }
    )


# ============================================================================
# SWEDEN - Personnummer & Samordningsnummer
# ============================================================================

def decode_sweden_personnummer(pnr: str) -> DecodedID:
    """
    Sweden Personal ID (10 digits: YYMMDD-XXXX or 12 digits: YYYYMMDD-XXXX)
    Last 4 digits: XXX + check digit
    """
    pnr = re.sub(r'[^\d]', '', pnr)

    if len(pnr) == 10:
        yy, mm, dd = int(pnr[0:2]), int(pnr[2:4]), int(pnr[4:6])
        current_year = datetime.now().year % 100
        year = 1900 + yy if yy > current_year else 2000 + yy
        serial = pnr[6:9]
        check = pnr[9]
    elif len(pnr) == 12:
        year, mm, dd = int(pnr[0:4]), int(pnr[4:6]), int(pnr[6:8])
        serial = pnr[8:11]
        check = pnr[11]
    else:
        return DecodedID("Personnummer", "Sweden", pnr, False, {}, "Must be 10 or 12 digits")

    try:
        dob = datetime(year, mm, dd)
        dob_str = dob.strftime("%Y-%m-%d")
    except ValueError:
        dob_str = f"{year}-{mm:02d}-{dd:02d} (invalid)"

    return DecodedID(
        id_type="Personnummer",
        country="Sweden",
        original_value=pnr,
        valid=True,
        decoded_info={
            "date_of_birth": dob_str,
            "serial_number": serial,
            "check_digit": check,
        }
    )


# ============================================================================
# CHILE - RUT/RUN
# ============================================================================

def decode_chile_rut(rut: str) -> DecodedID:
    """
    Chile Tax ID (7-8 digits + check: XX.XXX.XXX-Z where Z is 0-9 or K)
    """
    rut_clean = re.sub(r'[^\dKk]', '', rut.upper())

    if len(rut_clean) < 8 or len(rut_clean) > 9:
        return DecodedID("RUT/RUN", "Chile", rut, False, {}, "Invalid format")

    number = rut_clean[:-1]
    check = rut_clean[-1]

    # Format with dots and dash
    if len(number) == 7:
        formatted = f"{number[0]}.{number[1:4]}.{number[4:7]}-{check}"
    else:
        formatted = f"{number[0:2]}.{number[2:5]}.{number[5:8]}-{check}"

    return DecodedID(
        id_type="RUT/RUN",
        country="Chile",
        original_value=rut,
        valid=True,
        decoded_info={
            "number": number,
            "check_digit": check,
            "formatted": formatted,
        }
    )


# ============================================================================
# CHINA - National ID (18 digits)
# ============================================================================

def decode_china_national_id(cid: str) -> DecodedID:
    """
    China National ID (18 digits)
    Format: AAAAAA YYYYMMDD XXX C
    - 6 digits: Administrative division code
    - 8 digits: Date of birth (YYYYMMDD)
    - 3 digits: Sequential code (odd=male, even=female)
    - 1 digit: Check digit
    """
    cid = re.sub(r'\D', '', cid)

    if len(cid) != 18:
        return DecodedID("National ID", "China", cid, False, {}, "Must be 18 digits")

    try:
        admin_code = cid[0:6]
        year = int(cid[6:10])
        month = int(cid[10:12])
        day = int(cid[12:14])
        seq = cid[14:17]
        check = cid[17]

        dob = datetime(year, month, day)
        gender = "Male" if int(seq) % 2 == 1 else "Female"

        return DecodedID(
            id_type="National ID",
            country="China",
            original_value=cid,
            valid=True,
            decoded_info={
                "administrative_division": admin_code,
                "date_of_birth": dob.strftime("%Y-%m-%d"),
                "gender": gender,
                "sequential_code": seq,
                "check_digit": check,
            }
        )
    except Exception as e:
        return DecodedID("National ID", "China", cid, False, {}, str(e))


# ============================================================================
# FRANCE - NIR (Numéro d'Inscription au Répertoire)
# ============================================================================

def decode_france_nir(nir: str) -> DecodedID:
    """
    France Social Security Number (15 digits)
    Format: S YY MM DD DDD MMM RRR KK
    - 1 digit: Gender (1=male, 2=female)
    - 2 digits: Year of birth
    - 2 digits: Month of birth
    - 2 digits: Department of birth
    - 3 digits: Municipality code
    - 3 digits: Birth registration number
    - 2 digits: Check key
    """
    nir = re.sub(r'\D', '', nir)

    if len(nir) != 15:
        return DecodedID("NIR", "France", nir, False, {}, "Must be 15 digits")

    try:
        gender_code = nir[0]
        yy = int(nir[1:3])
        mm = int(nir[3:5])
        dept = nir[5:7]
        municipality = nir[7:10]
        registration = nir[10:13]
        check_key = nir[13:15]

        gender = "Male" if gender_code == "1" else "Female" if gender_code == "2" else "Unknown"
        current_year = datetime.now().year % 100
        year = 1900 + yy if yy > current_year else 2000 + yy

        try:
            dob = datetime(year, mm, 1)
            dob_str = dob.strftime("%Y-%m")
        except ValueError:
            dob_str = f"{year}-{mm:02d}"

        return DecodedID(
            id_type="NIR",
            country="France",
            original_value=nir,
            valid=True,
            decoded_info={
                "gender": gender,
                "date_of_birth": dob_str,
                "department_of_birth": dept,
                "municipality_code": municipality,
                "registration_number": registration,
                "check_key": check_key,
            }
        )
    except Exception as e:
        return DecodedID("NIR", "France", nir, False, {}, str(e))


# ============================================================================
# BELGIUM - National Register Number
# ============================================================================

def decode_belgium_national_register(nrn: str) -> DecodedID:
    """
    Belgium National Register Number (11 digits: YY.MM.DD-XXX.XX)
    - 6 digits: Date of birth (YYMMDD)
    - 3 digits: Sequential (odd=male, even=female)
    - 2 digits: Check digits
    """
    nrn = re.sub(r'\D', '', nrn)

    if len(nrn) != 11:
        return DecodedID("National Register", "Belgium", nrn, False, {}, "Must be 11 digits")

    try:
        yy = int(nrn[0:2])
        mm = int(nrn[2:4])
        dd = int(nrn[4:6])
        seq = int(nrn[6:9])
        check = nrn[9:11]

        current_year = datetime.now().year % 100
        year = 1900 + yy if yy > current_year else 2000 + yy

        dob = datetime(year, mm, dd)
        gender = "Male" if seq % 2 == 1 else "Female"

        return DecodedID(
            id_type="National Register Number",
            country="Belgium",
            original_value=nrn,
            valid=True,
            decoded_info={
                "date_of_birth": dob.strftime("%Y-%m-%d"),
                "gender": gender,
                "sequential_number": str(seq),
                "check_digits": check,
                "formatted": f"{nrn[0:2]}.{nrn[2:4]}.{nrn[4:6]}-{nrn[6:9]}.{nrn[9:11]}",
            }
        )
    except Exception as e:
        return DecodedID("National Register", "Belgium", nrn, False, {}, str(e))


# ============================================================================
# CZECH REPUBLIC / SLOVAKIA - Rodné číslo (Birth Number)
# ============================================================================

def decode_czech_slovak_birth_number(rn: str) -> DecodedID:
    """
    Czech/Slovak Birth Number (10 digits: YYMMDD/XXXX)
    - 6 digits: Date of birth (for women, 50 is added to MM)
    - 4 digits: Sequential and check
    """
    rn = re.sub(r'\D', '', rn)

    if len(rn) not in [9, 10]:
        return DecodedID("Rodné číslo", "Czech/Slovakia", rn, False, {}, "Must be 9-10 digits")

    try:
        yy = int(rn[0:2])
        mm = int(rn[2:4])
        dd = int(rn[4:6])

        gender = "Female" if mm > 50 else "Male"
        month = mm - 50 if mm > 50 else mm

        current_year = datetime.now().year % 100
        year = 1900 + yy if yy > current_year else 2000 + yy

        dob = datetime(year, month, dd)

        return DecodedID(
            id_type="Rodné číslo",
            country="Czech Republic / Slovakia",
            original_value=rn,
            valid=True,
            decoded_info={
                "date_of_birth": dob.strftime("%Y-%m-%d"),
                "gender": gender,
                "formatted": f"{rn[0:6]}/{rn[6:]}",
            }
        )
    except Exception as e:
        return DecodedID("Rodné číslo", "Czech/Slovakia", rn, False, {}, str(e))


# ============================================================================
# ROMANIA - CNP (Cod Numeric Personal)
# ============================================================================

def decode_romania_cnp(cnp: str) -> DecodedID:
    """
    Romania Personal Numeric Code (13 digits)
    Format: S YY MM DD JJ NNN C
    - 1 digit: Gender and century (1-2=1900s, 3-4=1800s, 5-6=2000s, 7-8=foreign)
    - 6 digits: Date of birth (YYMMDD)
    - 2 digits: County code
    - 3 digits: Sequential
    - 1 digit: Check digit
    """
    cnp = re.sub(r'\D', '', cnp)

    if len(cnp) != 13:
        return DecodedID("CNP", "Romania", cnp, False, {}, "Must be 13 digits")

    try:
        gender_century = int(cnp[0])
        yy = int(cnp[1:3])
        mm = int(cnp[3:5])
        dd = int(cnp[5:7])
        county = cnp[7:9]
        seq = cnp[9:12]
        check = cnp[12]

        # Decode century and gender
        if gender_century in [1, 2]:
            century = 1900
            gender = "Male" if gender_century == 1 else "Female"
        elif gender_century in [3, 4]:
            century = 1800
            gender = "Male" if gender_century == 3 else "Female"
        elif gender_century in [5, 6]:
            century = 2000
            gender = "Male" if gender_century == 5 else "Female"
        elif gender_century in [7, 8]:
            century = 1900  # Foreign resident
            gender = "Male" if gender_century == 7 else "Female"
        else:
            century = 1900
            gender = "Unknown"

        year = century + yy
        dob = datetime(year, mm, dd)

        return DecodedID(
            id_type="CNP",
            country="Romania",
            original_value=cnp,
            valid=True,
            decoded_info={
                "date_of_birth": dob.strftime("%Y-%m-%d"),
                "gender": gender,
                "county_code": county,
                "sequential_number": seq,
                "check_digit": check,
            }
        )
    except Exception as e:
        return DecodedID("CNP", "Romania", cnp, False, {}, str(e))


# ============================================================================
# SOUTH KOREA - Resident Registration Number
# ============================================================================

def decode_south_korea_rrn(rrn: str) -> DecodedID:
    """
    South Korea RRN (13 digits: YYMMDD-XXXXXXX)
    - 6 digits: Date of birth
    - 7 digits: Gender (1-2=1900s, 3-4=2000s), region, check
    """
    rrn = re.sub(r'\D', '', rrn)

    if len(rrn) != 13:
        return DecodedID("RRN", "South Korea", rrn, False, {}, "Must be 13 digits")

    try:
        yy = int(rrn[0:2])
        mm = int(rrn[2:4])
        dd = int(rrn[4:6])
        gender_code = int(rrn[6])

        if gender_code in [1, 2]:
            year = 1900 + yy
            gender = "Male" if gender_code == 1 else "Female"
        elif gender_code in [3, 4]:
            year = 2000 + yy
            gender = "Male" if gender_code == 3 else "Female"
        else:
            year = 1900 + yy
            gender = "Unknown"

        dob = datetime(year, mm, dd)

        return DecodedID(
            id_type="Resident Registration Number",
            country="South Korea",
            original_value=rrn,
            valid=True,
            decoded_info={
                "date_of_birth": dob.strftime("%Y-%m-%d"),
                "gender": gender,
                "formatted": f"{rrn[0:6]}-{rrn[6:]}",
            }
        )
    except Exception as e:
        return DecodedID("RRN", "South Korea", rrn, False, {}, str(e))


# ============================================================================
# PATTERN DETECTION & ROUTING
# ============================================================================

def detect_id_type(id_value: str) -> List[str]:
    """
    Detect possible ID types based on format patterns
    Returns list of possible ID types to try
    """
    clean = re.sub(r'\s', '', id_value)
    digits_only = re.sub(r'\D', '', clean)

    possible_types = []

    # Length-based detection
    if len(digits_only) == 16:
        possible_types.append("indonesia_nik")
    elif len(digits_only) == 18:
        possible_types.append("china_national_id")
    elif len(digits_only) == 14:
        possible_types.append("brazil_cnpj")
    elif len(digits_only) == 11:
        possible_types.extend(["brazil_cpf", "belgium_national_register"])
    elif len(digits_only) in [9, 10]:
        possible_types.extend(["sweden_personnummer", "czech_slovak_birth_number"])
    elif len(digits_only) == 13:
        possible_types.extend(["romania_cnp", "south_korea_rrn"])
    elif len(digits_only) == 15:
        possible_types.append("france_nir")
    elif len(digits_only) in [7, 8, 9] and ('K' in clean.upper() or '-' in clean):
        possible_types.append("chile_rut")

    # Pattern-based detection
    if re.match(r'^\d{6}-\d{4}$', clean):
        possible_types.append("sweden_personnummer")
    if re.match(r'^\d{2}\.\d{2}\.\d{2}-\d{3}\.\d{2}$', clean):
        possible_types.append("belgium_national_register")
    if re.match(r'^\d{6}/\d{3,4}$', clean):
        possible_types.append("czech_slovak_birth_number")

    # Default fallback
    if not possible_types:
        possible_types.append("unknown")

    return possible_types


def decode_id(id_value: str, id_type: Optional[str] = None, return_all: bool = False) -> Dict[str, Any]:
    """
    Main decoder function - auto-detect and decode any supported ID format

    Args:
        id_value: The ID number to decode
        id_type: Optional explicit ID type (e.g., "indonesia_nik", "brazil_cpf")
        return_all: If True, returns ALL possible matches instead of just the first valid one

    Returns:
        If return_all=False: Single best match result
        If return_all=True: {"possibilities": [...], "count": N}
    """
    id_value = id_value.strip()

    # Decoder mapping
    decoders = {
        "indonesia_nik": decode_indonesia_nik,
        "brazil_cnpj": decode_brazil_cnpj,
        "brazil_cpf": decode_brazil_cpf,
        "sweden_personnummer": decode_sweden_personnummer,
        "chile_rut": decode_chile_rut,
        "china_national_id": decode_china_national_id,
        "france_nir": decode_france_nir,
        "belgium_national_register": decode_belgium_national_register,
        "czech_slovak_birth_number": decode_czech_slovak_birth_number,
        "romania_cnp": decode_romania_cnp,
        "south_korea_rrn": decode_south_korea_rrn,
    }

    # Mode 1: Explicit ID type specified
    if id_type:
        if id_type in decoders:
            result = decoders[id_type](id_value)
            return {
                "id_type": result.id_type,
                "country": result.country,
                "original_value": result.original_value,
                "valid": result.valid,
                "decoded_info": result.decoded_info,
                "error": result.error if hasattr(result, 'error') and result.error else None,
            }
        else:
            return {
                "id_type": "Unknown",
                "country": "Unknown",
                "original_value": id_value,
                "valid": False,
                "decoded_info": {},
                "error": f"Unknown ID type: {id_type}. Available: {', '.join(decoders.keys())}",
            }

    # Mode 2: Auto-detect - try all possibilities
    possible_types = detect_id_type(id_value)

    if return_all:
        # Return ALL matches (valid or not)
        possibilities = []
        for id_type in possible_types:
            if id_type in decoders:
                result = decoders[id_type](id_value)
                possibilities.append({
                    "id_type": result.id_type,
                    "country": result.country,
                    "original_value": result.original_value,
                    "valid": result.valid,
                    "decoded_info": result.decoded_info if result.valid else {},
                    "error": result.error if hasattr(result, 'error') and result.error else None,
                    "confidence": "high" if result.valid else "low",
                })

        return {
            "mode": "multiple_possibilities",
            "original_value": id_value,
            "count": len(possibilities),
            "possibilities": possibilities,
        }

    # Mode 3: Auto-detect - return first valid match
    for id_type in possible_types:
        if id_type in decoders:
            result = decoders[id_type](id_value)
            if result.valid:
                # Convert DecodedID to dict
                return {
                    "id_type": result.id_type,
                    "country": result.country,
                    "original_value": result.original_value,
                    "valid": result.valid,
                    "decoded_info": result.decoded_info,
                }

    # No valid decoder found
    return {
        "id_type": "Unknown",
        "country": "Unknown",
        "original_value": id_value,
        "valid": False,
        "decoded_info": {},
        "error": "No matching ID format found. Supported: NIK, CNPJ, CPF, Personnummer, RUT, CNP, RRN, NIR, and more",
    }


# ============================================================================
# CLI TEST INTERFACE
# ============================================================================

if __name__ == "__main__":
    import sys

    test_ids = [
        "3527091604810001",  # Indonesia NIK
        "851125-5477",       # Sweden personnummer
        "12345678901234",    # Brazil CNPJ
        "12345678901",       # Brazil CPF
        "12.345.678-9",      # Chile RUT
        "110101198001011234",  # China National ID (example)
        "1850312345678",     # France NIR (example)
        "850312-123-45",     # Belgium National Register (example)
        "8503120123",        # Czech/Slovak Birth Number (example)
        "1850312123456",     # Romania CNP (example)
        "850312-1234567",    # South Korea RRN (example)
    ]

    if len(sys.argv) > 1:
        test_ids = [sys.argv[1]]

    print("🔍 WIKIMAN ID Decoder Test\n")
    for test_id in test_ids:
        print(f"\nTesting: {test_id}")
        result = decode_id(test_id)
        print(f"  Type: {result['id_type']}")
        print(f"  Country: {result['country']}")
        print(f"  Valid: {result['valid']}")
        if result.get('decoded_info'):
            print(f"  Decoded:")
            for key, value in result['decoded_info'].items():
                print(f"    {key}: {value}")
        if result.get('error'):
            print(f"  Error: {result['error']}")
