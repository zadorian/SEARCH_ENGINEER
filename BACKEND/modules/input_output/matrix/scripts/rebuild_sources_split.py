#!/usr/bin/env python3
"""
Rebuild input_output/matrix/sources/*.json from sources.json and sources_news.json.

News output is merged into input_output/matrix/sources/news.json (canonical).

Output files are category-based and jurisdiction-keyed:
  input_output/matrix/sources/<bucket>.json
"""

import csv
import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET


MATRIX_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = MATRIX_DIR.parent.parent
DOMAIN_SOURCES_DIR = PROJECT_ROOT / "BACKEND" / "domain_sources"
MEDIA_SOURCES_DIR = DOMAIN_SOURCES_DIR / "media"
SOURCES_PATH = MATRIX_DIR / "sources.json"
NEWS_PATH = MATRIX_DIR / "sources_news.json"
NEWS_BACKUP_PATH = MATRIX_DIR / "sources_news_backup.json"
NEWS_BROKEN_PATH = MATRIX_DIR / "sources_news_broken.json"
OUT_DIR = MATRIX_DIR / "sources"
MANIFEST_PATH = MATRIX_DIR / "manifest.json"

FIXED_BUCKET_ALIASES = {
    "tech": {"tec", "ref", "edu"},
    "government": {"gov", "procurement", "license", "gazette"},
    "corporate_registries": {"cr", "company"},
    "assets": {"ass", "asset_registries", "land"},
    "news": {"med", "news"},
    "litigation": {"lit", "poi"},
    "regulators": {"reg", "regulatory"},
    "sanctions": {"sanctions"},
    "osint": {"investigation", "compliance"},
}

RAW_CATEGORY_MAP = {
    "mar": "ecommerce",
    "mul": "multimedia",
    "mis": "miscellaneous",
    "at": "asset_tracing",
    "geo": "geospatial",
    "map": "mapping_tools",
    "lif": "lifestyle",
    "rec": "recruitment",
    "hea": "health",
    "sci": "science",
    "wea": "weather",
    "grey": "grey_literature",
    "leak": "leaks",
    "lib": "libraries",
    "log": "tracking",
    "cre": "creative",
}

FIXED_BUCKET_ORDER = [
    "tech",
    "government",
    "corporate_registries",
    "assets",
    "news",
    "litigation",
    "regulators",
    "sanctions",
    "osint",
]


def load_json(path: Path):
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_bucket(value: str) -> str:
    return value.strip().lower()


def normalize_domain(value: str) -> str:
    domain = (value or "").strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def domain_from_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "http://" + raw
    try:
        host = urlparse(raw).netloc
    except Exception:
        return ""
    return normalize_domain(host)


def normalize_name(value: str) -> str:
    cleaned = (value or "").strip().lower()
    cleaned = re.sub(r"[\W_]+", " ", cleaned, flags=re.UNICODE)
    return re.sub(r"\s+", " ", cleaned).strip()


def map_raw_category(value: str) -> str:
    return RAW_CATEGORY_MAP.get(value, value)


def pick_category(source: dict) -> str:
    category = normalize_bucket(source.get("category") or "")
    section = normalize_bucket(source.get("section") or "")
    for candidate in (category, section):
        if not candidate:
            continue
        for bucket, aliases in FIXED_BUCKET_ALIASES.items():
            if candidate in aliases:
                return bucket
    if category:
        return map_raw_category(category)
    if section:
        return map_raw_category(section)
    return "uncategorized"


def pick_jurisdiction(source: dict) -> str:
    jur = source.get("jurisdiction")
    if isinstance(jur, str) and jur.strip():
        return jur.strip().upper()
    jurs = source.get("jurisdictions") or []
    if isinstance(jurs, list) and jurs:
        return str(jurs[0]).strip().upper()
    return "GLOBAL"


def count_sources(bucket: dict) -> int:
    return sum(len(items) for items in bucket.values())


def _news_key(source: dict) -> str:
    domain = normalize_domain(source.get("domain"))
    if domain:
        return domain
    return (str(source.get("id") or "").strip().lower())


def _merge_news_value(dest: dict, src: dict, fields: list[str]) -> None:
    for field in fields:
        value = src.get(field)
        if value not in (None, "", [], {}):
            dest[field] = value


def _fill_news_value(dest: dict, src: dict, fields: list[str]) -> None:
    for field in fields:
        value = src.get(field)
        if value not in (None, "", [], {}) and not dest.get(field):
            dest[field] = value


def _ensure_news_jurisdiction(dest: dict, jur: str) -> None:
    if not dest.get("jurisdiction"):
        dest["jurisdiction"] = jur


def _xlsx_col_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
    return max(idx - 1, 0)


def _read_xlsx_sheets(path: Path) -> list[list[list[str]]]:
    if not path.exists():
        return []
    with zipfile.ZipFile(path) as zf:
        shared_strings = []
        if "xl/sharedStrings.xml" in zf.namelist():
            ss_xml = zf.read("xl/sharedStrings.xml")
            ss_root = ET.fromstring(ss_xml)
            for si in ss_root.findall(".//{*}si"):
                text_parts = []
                for t_el in si.findall(".//{*}t"):
                    text_parts.append(t_el.text or "")
                shared_strings.append("".join(text_parts))

        sheets = []
        for name in sorted(zf.namelist()):
            if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                continue
            sheet_xml = zf.read(name)
            root = ET.fromstring(sheet_xml)
            rels = {}
            rels_name = f"xl/worksheets/_rels/{Path(name).name}.rels"
            if rels_name in zf.namelist():
                rels_root = ET.fromstring(zf.read(rels_name))
                for rel in rels_root.findall("{*}Relationship"):
                    rels[rel.attrib.get("Id", "")] = rel.attrib.get("Target", "")
            hyperlink_map = {}
            for hyperlink in root.findall(".//{*}hyperlink"):
                ref = hyperlink.attrib.get("ref")
                rid = hyperlink.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                if not rid:
                    rid = hyperlink.attrib.get("r:id")
                target = rels.get(rid, "") if rid else ""
                if ref and target:
                    hyperlink_map[ref] = target
            rows = []
            for row in root.findall(".//{*}row"):
                row_values = {}
                max_col = -1
                for cell in row.findall("{*}c"):
                    cell_ref = cell.attrib.get("r", "")
                    col_idx = _xlsx_col_index(cell_ref)
                    max_col = max(max_col, col_idx)
                    cell_type = cell.attrib.get("t")
                    value = ""
                    if cell_type == "inlineStr":
                        text_parts = []
                        for t_el in cell.findall(".//{*}t"):
                            text_parts.append(t_el.text or "")
                        value = "".join(text_parts)
                    else:
                        v_el = cell.find("{*}v")
                        if v_el is not None and v_el.text is not None:
                            if cell_type == "s":
                                try:
                                    value = shared_strings[int(v_el.text)]
                                except Exception:
                                    value = v_el.text
                            else:
                                value = v_el.text
                    if not value and cell_ref in hyperlink_map:
                        value = hyperlink_map[cell_ref]
                    row_values[col_idx] = value
                if max_col >= 0:
                    row_list = [row_values.get(i, "") for i in range(max_col + 1)]
                    if any(cell for cell in row_list):
                        rows.append(row_list)
            if rows:
                sheets.append(rows)
        return sheets


def _select_header_row(rows: list[list[str]]) -> tuple[list[str], int]:
    for idx, row in enumerate(rows):
        if not row:
            continue
        normalized = [str(cell or "").strip() for cell in row]
        lowered = [cell.lower() for cell in normalized]
        has_url = any("url" in cell or "link" in cell or "domain" in cell for cell in lowered)
        has_desc = any("description" in cell or cell in ("desc", "notes", "note", "summary", "about") for cell in lowered)
        if has_url and has_desc:
            return normalized, idx
    for idx, row in enumerate(rows):
        if not row:
            continue
        normalized = [str(cell or "").strip() for cell in row]
        if sum(1 for cell in normalized if cell) >= 2:
            return normalized, idx
    return [], -1


def _find_header_index(headers: list[str], candidates: list[str]) -> int:
    for i, header in enumerate(headers):
        key = header.strip().lower()
        if not key:
            continue
        for candidate in candidates:
            if candidate in key:
                return i
    return -1


def _add_description(desc_map: dict, key: str, description: str) -> None:
    if not key or not description:
        return
    description = description.strip()
    if not description:
        return
    current = desc_map.get(key)
    if current is None or len(description) > len(current):
        desc_map[key] = description


def _load_description_csv(path: Path, desc_map: dict, name_map: dict) -> None:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        sample = f.readline()
        if not sample:
            return
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
        f.seek(0)
        reader = csv.DictReader(f, delimiter=delimiter)
        if not reader.fieldnames:
            return
        headers = [h.strip().lower() for h in reader.fieldnames]
        desc_keys = [k for k in headers if "description" in k or k in ("desc", "note", "notes", "summary")]
        url_keys = [k for k in headers if k in ("url", "website", "site", "link")]
        domain_keys = [k for k in headers if k in ("domain", "domain_normalized")]
        name_keys = [k for k in headers if k in ("name", "site_name", "publication", "outlet")]
        if not desc_keys or (not url_keys and not domain_keys):
            return
        for row in reader:
            desc = ""
            for key in desc_keys:
                desc = row.get(key) or desc
            domain = ""
            for key in domain_keys:
                domain = row.get(key) or domain
            if not domain:
                for key in url_keys:
                    domain = domain_from_url(row.get(key))
            if domain:
                _add_description(desc_map, normalize_domain(domain), desc)
            name = ""
            for key in name_keys:
                name = row.get(key) or name
            if name:
                _add_description(name_map, normalize_name(name), desc)


def _load_description_xlsx(path: Path, desc_map: dict, name_map: dict) -> None:
    for rows in _read_xlsx_sheets(path):
        if not rows:
            continue
        headers, header_idx = _select_header_row(rows)
        if header_idx < 0:
            continue
        url_idx = _find_header_index(headers, ["url", "website", "site", "link", "domain"])
        name_idx = _find_header_index(headers, ["name", "publication", "outlet", "paper", "station"])
        desc_idx = _find_header_index(headers, ["description", "desc", "notes", "summary", "about"])
        if desc_idx < 0:
            continue
        for row in rows[header_idx + 1:]:
            if desc_idx >= len(row):
                continue
            url_val = ""
            if url_idx >= 0 and url_idx < len(row):
                url_val = str(row[url_idx] or "").strip()
            desc_val = str(row[desc_idx] or "").strip()
            if not desc_val:
                continue
            if url_val:
                domain = domain_from_url(url_val) or normalize_domain(url_val)
                if domain:
                    _add_description(desc_map, domain, desc_val)
            if name_idx >= 0 and name_idx < len(row):
                name_val = str(row[name_idx] or "").strip()
                if name_val:
                    _add_description(name_map, normalize_name(name_val), desc_val)


def build_description_lookup() -> tuple[dict, dict]:
    desc_map = {}
    name_map = {}
    if DOMAIN_SOURCES_DIR.exists():
        for csv_path in DOMAIN_SOURCES_DIR.glob("*.csv"):
            _load_description_csv(csv_path, desc_map, name_map)
    if MEDIA_SOURCES_DIR.exists():
        for xlsx_path in MEDIA_SOURCES_DIR.glob("*.xlsx"):
            if xlsx_path.name.startswith("~$"):
                continue
            _load_description_xlsx(xlsx_path, desc_map, name_map)
    return desc_map, name_map


TYPE_ALIASES = {
    "media": "news_outlet",
    "public broadcaster": "public_broadcaster",
    "public_broadcaster": "public_broadcaster",
    "wire_service": "wire_service",
    "wire service": "wire_service",
    "news outlet": "news_outlet",
    "news_outlet": "news_outlet",
}


def normalize_news_type(value: str) -> str:
    if not value:
        return "news_outlet"
    cleaned = value.strip().lower()
    cleaned = re.sub(r"[\s\-]+", "_", cleaned)
    return TYPE_ALIASES.get(cleaned, cleaned)


def main() -> int:
    sources_data = load_json(SOURCES_PATH)
    if not sources_data:
        print(f"ERROR: Missing {SOURCES_PATH}")
        return 1

    sources_obj = sources_data.get("sources") if isinstance(sources_data, dict) else None
    if sources_obj is None:
        sources_obj = sources_data

    if isinstance(sources_obj, dict):
        sources_list = list(sources_obj.values())
    elif isinstance(sources_obj, list):
        sources_list = sources_obj
    else:
        print("ERROR: sources.json has unexpected structure")
        return 1

    news_base_path = None
    if NEWS_BACKUP_PATH.exists():
        news_base_path = NEWS_BACKUP_PATH
    elif NEWS_PATH.exists():
        news_base_path = NEWS_PATH
    use_news_file = news_base_path is not None
    news_candidates = []

    buckets = defaultdict(lambda: defaultdict(list))
    for bucket in FIXED_BUCKET_ORDER:
        buckets[bucket]

    for source in sources_list:
        if not isinstance(source, dict):
            continue
        category = pick_category(source)
        if category == "news" and use_news_file:
            news_candidates.append(source)
            continue
        jur = pick_jurisdiction(source)
        buckets[category][jur].append(source)

    if use_news_file:
        news_bucket = defaultdict(list)
        news_index = defaultdict(dict)

        news_data = load_json(news_base_path) or {}
        if isinstance(news_data, dict):
            for jur, sources in news_data.items():
                if not isinstance(sources, list):
                    continue
                for source in sources:
                    key = _news_key(source)
                    if not key:
                        continue
                    entry = dict(source)
                    _ensure_news_jurisdiction(entry, jur)
                    news_index[jur][key] = entry
                    news_bucket[jur].append(entry)

        if news_base_path != NEWS_PATH and NEWS_PATH.exists():
            override_data = load_json(NEWS_PATH) or {}
            if isinstance(override_data, dict):
                for jur, sources in override_data.items():
                    if not isinstance(sources, list):
                        continue
                    for source in sources:
                        key = _news_key(source)
                        if not key:
                            continue
                        entry = news_index[jur].get(key)
                        if entry is None:
                            entry = dict(source)
                            _ensure_news_jurisdiction(entry, jur)
                            news_index[jur][key] = entry
                            news_bucket[jur].append(entry)
                            continue
                        _merge_news_value(entry, source, [
                            "search_template",
                            "search_url",
                            "search_recipe",
                            "scrape_method",
                            "date_filtering",
                            "needs_js",
                            "reliability",
                            "name",
                            "id",
                            "type",
                            "category",
                            "region",
                            "description",
                        ])

        if NEWS_BROKEN_PATH.exists():
            broken_data = load_json(NEWS_BROKEN_PATH) or {}
            if isinstance(broken_data, dict):
                for jur, sources in broken_data.items():
                    if not isinstance(sources, list):
                        continue
                    for source in sources:
                        key = _news_key(source)
                        if not key:
                            continue
                        entry = news_index[jur].get(key)
                        if entry is None:
                            continue
                        _fill_news_value(entry, source, [
                            "search_recipe",
                            "scrape_method",
                            "date_filtering",
                            "needs_js",
                        ])

        if news_candidates:
            for source in news_candidates:
                jur = pick_jurisdiction(source)
                key = _news_key(source)
                if not key or key in news_index[jur]:
                    continue
                entry = dict(source)
                _ensure_news_jurisdiction(entry, jur)
                news_index[jur][key] = entry
                news_bucket[jur].append(entry)

        description_lookup, name_lookup = build_description_lookup()
        filled_descriptions = 0
        for sources in news_bucket.values():
            for source in sources:
                source["category"] = "news"
                source["type"] = normalize_news_type(source.get("type"))
                if not source.get("description"):
                    domain = normalize_domain(source.get("domain"))
                    description = description_lookup.get(domain)
                    if not description:
                        name_key = normalize_name(source.get("name"))
                        description = name_lookup.get(name_key)
                    if description:
                        source["description"] = description
                        filled_descriptions += 1
        if filled_descriptions:
            print(f"Backfilled {filled_descriptions} news descriptions")

        buckets["news"] = news_bucket

    category_order = FIXED_BUCKET_ORDER + sorted(
        bucket for bucket in buckets.keys() if bucket not in FIXED_BUCKET_ORDER
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    category_counts = {}
    for category in category_order:
        out_path = OUT_DIR / f"{category}.json"
        data = buckets[category]
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        category_counts[category] = count_sources(data)
        print(f"Wrote {out_path} ({category_counts[category]} sources)")

    manifest = load_json(MANIFEST_PATH) or {}
    manifest["version"] = manifest.get("version", "2.0")
    manifest["migrated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["source_files"] = [f"sources/{name}.json" for name in category_order]
    manifest["rules_file"] = manifest.get("rules_file", "rules.json")
    manifest["categories"] = category_counts
    manifest["total_sources"] = sum(category_counts.values())

    with MANIFEST_PATH.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"Updated manifest at {MANIFEST_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
