#!/usr/bin/env python3
"""
TORPEDO OUTPUT MANAGER - Centralized output storage for all processors.

Saves:
1. Processing results (recipes, codes, classifications)
2. Source JSON copies for reproducibility
3. Run manifests linking results to sources

Output structure:
    TORPEDO/output/
    ├── manifest.json              # Index of all runs
    ├── sources/                   # Copies of source JSONs
    │   ├── corporate_registries_2024-01-04.json
    │   └── news_2024-01-04.json
    ├── classifications/           # Scrape method classifications
    │   ├── cr_HR_2024-01-04.json
    │   └── news_global_2024-01-04.json
    ├── extractions/               # Field/code extractions
    │   ├── cr_HR_2024-01-04.json
    │   └── seekleech_2024-01-04.json
    └── runs/                      # Full run records
        └── run_2024-01-04_143022.json

Usage:
    from TORPEDO.output_manager import TorpedoOutputManager

    manager = TorpedoOutputManager()

    # Save source JSON being processed
    manager.save_source("corporate_registries.json", source_data)

    # Save classification results
    manager.save_classification("cr", "HR", results)

    # Save extraction results (field codes, templates)
    manager.save_extraction("seekleech", results)

    # Complete a run with summary
    manager.complete_run(stats)
"""

import json
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field


logger = logging.getLogger("TORPEDO.OutputManager")

# Paths
TORPEDO_DIR = Path(__file__).parent
OUTPUT_DIR = TORPEDO_DIR / "output"


@dataclass
class RunRecord:
    """Record of a processing run."""
    run_id: str
    started_at: str
    completed_at: Optional[str] = None
    processor_type: str = ""  # "cr", "news", "seekleech"
    jurisdiction: Optional[str] = None
    source_file: str = ""
    source_snapshot: str = ""  # Path to saved source copy

    # Results
    total_processed: int = 0
    successful: int = 0
    failed: int = 0

    # Output files
    classification_file: Optional[str] = None
    extraction_file: Optional[str] = None

    # Stats by method/code
    method_counts: Dict[str, int] = field(default_factory=dict)
    code_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)


class TorpedoOutputManager:
    """
    Centralized output manager for TORPEDO processors.

    Ensures all processing results, source copies, and run metadata
    are saved to TORPEDO/output/ for reproducibility and analysis.
    """

    def __init__(self):
        # Create output directories
        self.output_dir = OUTPUT_DIR
        self.sources_dir = OUTPUT_DIR / "sources"
        self.classifications_dir = OUTPUT_DIR / "classifications"
        self.extractions_dir = OUTPUT_DIR / "extractions"
        self.runs_dir = OUTPUT_DIR / "runs"

        for d in [self.output_dir, self.sources_dir, self.classifications_dir,
                  self.extractions_dir, self.runs_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Current run
        self.run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.current_run = RunRecord(
            run_id=self.run_id,
            started_at=datetime.now().isoformat()
        )

        # Load manifest
        self.manifest_path = OUTPUT_DIR / "manifest.json"
        self.manifest = self._load_manifest()

        logger.info(f"TorpedoOutputManager initialized (run_id: {self.run_id})")

    def _load_manifest(self) -> Dict:
        """Load or create manifest."""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path) as f:
                    return json.load(f)
            except:
                pass
        return {
            "created_at": datetime.now().isoformat(),
            "runs": [],
            "sources": {},
            "classifications": {},
            "extractions": {}
        }

    def _save_manifest(self):
        """Save manifest."""
        with open(self.manifest_path, 'w') as f:
            json.dump(self.manifest, f, indent=2)

    # ─────────────────────────────────────────────────────────────
    # Source JSON Management
    # ─────────────────────────────────────────────────────────────

    def save_source(
        self,
        source_name: str,
        source_data: Any,
        source_path: Optional[Path] = None
    ) -> Path:
        """
        Save a copy of the source JSON being processed.

        Args:
            source_name: Name for the source (e.g., "corporate_registries")
            source_data: The source data (dict or list)
            source_path: Original path (for metadata)

        Returns:
            Path to saved source copy
        """
        # Clean name
        clean_name = source_name.replace(".json", "").replace("/", "_")
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"{clean_name}_{date_str}.json"
        output_path = self.sources_dir / filename

        # Save
        with open(output_path, 'w') as f:
            json.dump(source_data, f, indent=2)

        # Update manifest
        self.manifest["sources"][filename] = {
            "saved_at": datetime.now().isoformat(),
            "original_path": str(source_path) if source_path else None,
            "record_count": len(source_data) if isinstance(source_data, (list, dict)) else 0
        }
        self._save_manifest()

        # Update current run
        self.current_run.source_file = str(source_path) if source_path else source_name
        self.current_run.source_snapshot = str(output_path)

        logger.info(f"Saved source snapshot: {output_path}")
        return output_path

    def copy_source_file(self, source_path: Path) -> Path:
        """
        Copy an existing source file to output.

        Args:
            source_path: Path to source JSON

        Returns:
            Path to saved copy
        """
        with open(source_path) as f:
            data = json.load(f)
        return self.save_source(source_path.name, data, source_path)

    # ─────────────────────────────────────────────────────────────
    # Classification Results
    # ─────────────────────────────────────────────────────────────

    def save_classification(
        self,
        processor_type: str,
        jurisdiction: Optional[str],
        results: List[Dict],
        stats: Optional[Dict] = None
    ) -> Path:
        """
        Save scrape method classification results.

        Args:
            processor_type: "cr", "news", etc.
            jurisdiction: Optional jurisdiction code
            results: List of ProcessorResult dicts
            stats: Optional summary stats

        Returns:
            Path to saved classification file
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        jur_suffix = f"_{jurisdiction}" if jurisdiction else ""
        filename = f"{processor_type}{jur_suffix}_{date_str}.json"
        output_path = self.classifications_dir / filename

        # Build output
        output = {
            "classified_at": datetime.now().isoformat(),
            "run_id": self.run_id,
            "processor_type": processor_type,
            "jurisdiction": jurisdiction,
            "total_results": len(results),
            "stats": stats or {},
            "results": results
        }

        # Extract method counts
        method_counts = {}
        for r in results:
            method = r.get("scrape_method", "unknown")
            method_counts[method] = method_counts.get(method, 0) + 1
        output["method_counts"] = method_counts

        # Save
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)

        # Update manifest
        self.manifest["classifications"][filename] = {
            "saved_at": datetime.now().isoformat(),
            "run_id": self.run_id,
            "processor_type": processor_type,
            "jurisdiction": jurisdiction,
            "total_results": len(results),
            "method_counts": method_counts
        }
        self._save_manifest()

        # Update current run
        self.current_run.processor_type = processor_type
        self.current_run.jurisdiction = jurisdiction
        self.current_run.classification_file = str(output_path)
        self.current_run.total_processed = len(results)
        self.current_run.method_counts = method_counts

        logger.info(f"Saved classification: {output_path} ({len(results)} results)")
        return output_path

    # ─────────────────────────────────────────────────────────────
    # Extraction Results (Field Codes, Templates)
    # ─────────────────────────────────────────────────────────────

    def save_extraction(
        self,
        extraction_type: str,
        results: List[Dict],
        jurisdiction: Optional[str] = None,
        stats: Optional[Dict] = None
    ) -> Path:
        """
        Save field extraction results (IO codes, templates, etc.).

        Args:
            extraction_type: "cr_fields", "seekleech", "templates", etc.
            results: List of extraction result dicts
            jurisdiction: Optional jurisdiction code
            stats: Optional summary stats

        Returns:
            Path to saved extraction file
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        jur_suffix = f"_{jurisdiction}" if jurisdiction else ""
        filename = f"{extraction_type}{jur_suffix}_{date_str}.json"
        output_path = self.extractions_dir / filename

        # Collect IO codes across all results
        all_codes = {}
        all_fields = set()
        unmapped_fields = set()

        for r in results:
            # IO codes
            for code in r.get("outputs", []):
                all_codes[code] = all_codes.get(code, 0) + 1
            # Raw fields
            for field in r.get("raw_fields", []):
                all_fields.add(field)
            # Unmapped
            for field in r.get("unmapped_fields", []):
                unmapped_fields.add(field)

        # Build output
        output = {
            "extracted_at": datetime.now().isoformat(),
            "run_id": self.run_id,
            "extraction_type": extraction_type,
            "jurisdiction": jurisdiction,
            "total_results": len(results),
            "stats": stats or {},
            "io_code_summary": {
                "unique_codes": len(all_codes),
                "code_counts": dict(sorted(all_codes.items(), key=lambda x: -x[1]))
            },
            "field_summary": {
                "unique_fields": len(all_fields),
                "unmapped_count": len(unmapped_fields),
                "unmapped_fields": sorted(list(unmapped_fields))
            },
            "results": results
        }

        # Save
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)

        # Update manifest
        self.manifest["extractions"][filename] = {
            "saved_at": datetime.now().isoformat(),
            "run_id": self.run_id,
            "extraction_type": extraction_type,
            "jurisdiction": jurisdiction,
            "total_results": len(results),
            "unique_codes": len(all_codes),
            "unique_fields": len(all_fields)
        }
        self._save_manifest()

        # Update current run
        self.current_run.extraction_file = str(output_path)
        self.current_run.code_counts = all_codes

        logger.info(f"Saved extraction: {output_path} ({len(results)} results, {len(all_codes)} unique codes)")
        return output_path

    # ─────────────────────────────────────────────────────────────
    # Run Management
    # ─────────────────────────────────────────────────────────────

    def complete_run(
        self,
        successful: int = 0,
        failed: int = 0,
        extra_stats: Optional[Dict] = None
    ) -> Path:
        """
        Complete the current run and save the run record.

        Args:
            successful: Number of successful items
            failed: Number of failed items
            extra_stats: Any additional stats to include

        Returns:
            Path to saved run record
        """
        self.current_run.completed_at = datetime.now().isoformat()
        self.current_run.successful = successful
        self.current_run.failed = failed

        # Build run record
        run_data = self.current_run.to_dict()
        if extra_stats:
            run_data["extra_stats"] = extra_stats

        # Save run record
        filename = f"run_{self.run_id}.json"
        output_path = self.runs_dir / filename

        with open(output_path, 'w') as f:
            json.dump(run_data, f, indent=2)

        # Update manifest
        self.manifest["runs"].append({
            "run_id": self.run_id,
            "file": filename,
            "processor_type": self.current_run.processor_type,
            "jurisdiction": self.current_run.jurisdiction,
            "total": self.current_run.total_processed,
            "successful": successful,
            "failed": failed,
            "completed_at": self.current_run.completed_at
        })
        self._save_manifest()

        logger.info(f"Completed run {self.run_id}: {successful} successful, {failed} failed")
        return output_path

    # ─────────────────────────────────────────────────────────────
    # Query/Reporting
    # ─────────────────────────────────────────────────────────────

    def get_latest_classification(self, processor_type: str, jurisdiction: Optional[str] = None) -> Optional[Dict]:
        """Get the most recent classification for a processor type."""
        prefix = f"{processor_type}_{jurisdiction}" if jurisdiction else processor_type

        matching = [
            f for f in self.manifest.get("classifications", {}).keys()
            if f.startswith(prefix)
        ]

        if not matching:
            return None

        # Sort by date (newest first)
        matching.sort(reverse=True)
        latest = matching[0]

        with open(self.classifications_dir / latest) as f:
            return json.load(f)

    def get_all_codes(self) -> Dict[int, int]:
        """Get aggregate counts of all IO codes across all extractions."""
        all_codes = {}

        for filename in self.manifest.get("extractions", {}).keys():
            try:
                with open(self.extractions_dir / filename) as f:
                    data = json.load(f)
                for code, count in data.get("io_code_summary", {}).get("code_counts", {}).items():
                    code_int = int(code)
                    all_codes[code_int] = all_codes.get(code_int, 0) + count
            except:
                pass

        return dict(sorted(all_codes.items(), key=lambda x: -x[1]))

    def get_unmapped_fields(self) -> List[str]:
        """Get all unmapped fields across all extractions."""
        unmapped = set()

        for filename in self.manifest.get("extractions", {}).keys():
            try:
                with open(self.extractions_dir / filename) as f:
                    data = json.load(f)
                for field in data.get("field_summary", {}).get("unmapped_fields", []):
                    unmapped.add(field)
            except:
                pass

        return sorted(list(unmapped))

    def print_summary(self):
        """Print summary of all output data."""
        print(f"\n{'='*60}")
        print("TORPEDO OUTPUT SUMMARY")
        print(f"{'='*60}")

        print(f"\nRuns: {len(self.manifest.get('runs', []))}")
        for run in self.manifest.get('runs', [])[-5:]:  # Last 5 runs
            print(f"  - {run['run_id']}: {run['processor_type']} {run.get('jurisdiction', '')} "
                  f"({run['successful']}/{run['total']})")

        print(f"\nSources: {len(self.manifest.get('sources', {}))}")
        for name, info in list(self.manifest.get('sources', {}).items())[:5]:
            print(f"  - {name}: {info.get('record_count', 0)} records")

        print(f"\nClassifications: {len(self.manifest.get('classifications', {}))}")
        for name, info in list(self.manifest.get('classifications', {}).items())[:5]:
            print(f"  - {name}: {info.get('total_results', 0)} results")

        print(f"\nExtractions: {len(self.manifest.get('extractions', {}))}")
        for name, info in list(self.manifest.get('extractions', {}).items())[:5]:
            print(f"  - {name}: {info.get('unique_codes', 0)} codes, {info.get('unique_fields', 0)} fields")

        print(f"\nOutput directory: {self.output_dir}")


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="TORPEDO Output Manager")
    parser.add_argument("--summary", action="store_true", help="Print output summary")
    parser.add_argument("--codes", action="store_true", help="List all IO codes")
    parser.add_argument("--unmapped", action="store_true", help="List unmapped fields")
    args = parser.parse_args()

    manager = TorpedoOutputManager()

    if args.summary:
        manager.print_summary()
    elif args.codes:
        codes = manager.get_all_codes()
        print(f"IO Codes ({len(codes)} unique):")
        for code, count in list(codes.items())[:30]:
            print(f"  {code}: {count}")
    elif args.unmapped:
        unmapped = manager.get_unmapped_fields()
        print(f"Unmapped Fields ({len(unmapped)}):")
        for f in unmapped[:50]:
            print(f"  - {f}")
    else:
        manager.print_summary()
