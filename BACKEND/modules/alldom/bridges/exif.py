"""
EXIF Bridge - Routes metadata extraction operations to EXIF module.

Operators:
    meta!: - Full metadata scan of domain
    meta?: - Quick metadata scan
    exif!: - Extract EXIF from images on domain
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def scan(domain: str, **kwargs) -> Dict[str, Any]:
    """
    Full metadata scan of all files on domain.

    Discovers files via MAPPER, extracts metadata, runs entity extraction.

    Args:
        domain: Target domain
        **kwargs: Optional parameters:
            - max_files: Max files to scan (default 200)
            - file_types: Specific extensions to target
            - use_ai: Use Haiku for entity extraction (default True)
            - save_entities: Save to Elasticsearch (default True)

    Returns:
        Dict with entities, dates, metadata results
    """
    try:
        from modules.EXIF import MetadataScanner
        from modules.EXIF.entity_extractor import extract_and_save_entities

        max_files = kwargs.get("max_files", 200)
        file_types = kwargs.get("file_types")
        use_ai = kwargs.get("use_ai", True)
        save_entities = kwargs.get("save_entities", True)

        # Initialize scanner
        scanner = MetadataScanner(max_files=max_files)

        # Scan domain for metadata
        scan_result = await scanner.scan_domain(domain, file_types=file_types)

        # Extract entities with optional AI
        entity_result = await extract_and_save_entities(
            scan_result,
            save_to_elastic=save_entities
        )

        return {
            "success": True,
            "domain": domain,
            "files_scanned": scan_result.files_scanned,
            "files_with_metadata": scan_result.files_with_metadata,
            "entities": entity_result.to_dict(),
            "dates": {
                "earliest_creation": entity_result.earliest_creation,
                "latest_modification": entity_result.latest_modification,
                "date_range": entity_result.date_range,
                "all_dates": [
                    {"date": d.date_str, "type": d.date_type, "source": d.source_url}
                    for d in entity_result.dates[:100]  # Limit for response size
                ],
            },
            "summary": {
                "persons": len(entity_result.persons),
                "companies": len(entity_result.companies),
                "software": len(entity_result.software),
                "locations": len(entity_result.locations),
                "dates": len(entity_result.dates),
            }
        }

    except ImportError as e:
        logger.error(f"EXIF module not available: {e}")
        return {
            "success": False,
            "error": f"EXIF module not available: {e}"
        }
    except Exception as e:
        logger.error(f"EXIF scan failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def quick_scan(domain: str, **kwargs) -> Dict[str, Any]:
    """
    Quick metadata scan - fewer files, no AI.

    Args:
        domain: Target domain
        **kwargs: Optional max_files (default 50)

    Returns:
        Dict with basic metadata findings
    """
    return await scan(
        domain,
        max_files=kwargs.get("max_files", 50),
        use_ai=False,
        save_entities=False,
        **kwargs
    )


async def images_only(domain: str, **kwargs) -> Dict[str, Any]:
    """
    Extract EXIF from images only.

    Targets: JPG, JPEG, PNG, HEIC, TIFF, RAW formats.

    Args:
        domain: Target domain
        **kwargs: Optional max_files

    Returns:
        Dict with image metadata and GPS locations
    """
    image_types = ["jpg", "jpeg", "png", "heic", "tiff", "tif", "cr2", "nef", "arw", "dng"]

    return await scan(
        domain,
        file_types=image_types,
        max_files=kwargs.get("max_files", 200),
        **kwargs
    )


async def documents_only(domain: str, **kwargs) -> Dict[str, Any]:
    """
    Extract metadata from documents only.

    Targets: PDF, DOCX, XLSX, PPTX, DOC, XLS, PPT.

    Args:
        domain: Target domain
        **kwargs: Optional max_files

    Returns:
        Dict with document metadata and authors
    """
    doc_types = ["pdf", "docx", "xlsx", "pptx", "doc", "xls", "ppt", "odt", "ods"]

    return await scan(
        domain,
        file_types=doc_types,
        max_files=kwargs.get("max_files", 200),
        **kwargs
    )


async def extract_persons(domain: str, **kwargs) -> Dict[str, Any]:
    """
    Extract person names from domain metadata.

    Returns only the persons found, with sources.
    """
    result = await scan(domain, **kwargs)

    if not result.get("success"):
        return result

    return {
        "success": True,
        "domain": domain,
        "persons": result.get("entities", {}).get("persons", []),
        "count": result.get("summary", {}).get("persons", 0),
    }


async def extract_dates(domain: str, **kwargs) -> Dict[str, Any]:
    """
    Extract date information from domain metadata.

    Returns creation dates, modification dates, and date ranges.
    """
    result = await scan(domain, use_ai=False, save_entities=False, **kwargs)

    if not result.get("success"):
        return result

    return {
        "success": True,
        "domain": domain,
        "dates": result.get("dates", {}),
        "count": result.get("summary", {}).get("dates", 0),
    }
