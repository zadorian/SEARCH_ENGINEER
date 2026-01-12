#!/usr/bin/env python3
"""
C-1 Bridge Builder Subagent

Analyzes modules with node creation capabilities and generates/configures
C1 bridges to index their output to cymonides-1-{projectId} indices.

Responsibilities:
- Discover module output types (person, company, email, domain, etc.)
- Generate C1 bridge code from templates
- Map module-specific fields to canonical node schema
- Validate bridge configuration against relationships.json
- Track bridge creation tasks via StatusTracker

Usage:
    from subagents.c1_bridge_builder import C1BridgeBuilder

    builder = C1BridgeBuilder(project_id="my-project")

    # Analyze a module
    analysis = builder.analyze_module("/path/to/module")

    # Generate bridge code
    bridge_code = builder.generate_bridge(analysis)

    # Validate the bridge
    validation = builder.validate_bridge(bridge_code)
"""

import ast
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Import canonical standards
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.canonical_standards import (
    CANONICAL_PATHS,
    NODE_CLASSES,
    C1_NODE_SCHEMA,
    C1_BRIDGE_TEMPLATE,
    generate_node_id,
    canonical_value,
    get_node_class,
)
from memory.status_tracker import StatusTracker, C1BridgeTask


@dataclass
class ModuleAnalysis:
    """Analysis results for a module."""
    module_name: str
    module_path: str

    # Discovered capabilities
    output_types: List[str] = field(default_factory=list)  # Entity types produced
    edge_types: List[str] = field(default_factory=list)    # Relationship types
    input_types: List[str] = field(default_factory=list)   # What it takes as input

    # Code analysis
    has_existing_bridge: bool = False
    existing_bridge_path: Optional[str] = None

    # Discovered patterns
    node_creation_patterns: List[Dict] = field(default_factory=list)
    indexing_patterns: List[Dict] = field(default_factory=list)

    # Recommendations
    recommended_mappings: List[Dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Metadata
    analyzed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class BridgeConfig:
    """Configuration for a C1 bridge."""
    module_name: str
    module_path: str
    bridge_file: str

    # Type mappings
    type_map: Dict[str, str] = field(default_factory=dict)  # module_type -> canonical_type

    # Node creation rules
    node_rules: List[Dict] = field(default_factory=list)

    # Edge creation rules
    edge_rules: List[Dict] = field(default_factory=list)

    # Index configuration
    default_index: str = "cymonides-1-default"
    source_system: str = ""


class C1BridgeBuilder:
    """
    Builds and configures C1 bridges for modules.

    Workflow:
    1. Analyze module to discover output types
    2. Map types to canonical node classes/types
    3. Generate bridge code from template
    4. Validate against canonical standards
    5. Track progress in StatusTracker
    """

    # Known entity type patterns in code
    ENTITY_PATTERNS = {
        r"person|people|name|individual": "person",
        r"company|organization|org|corp|entity": "company",
        r"email|mail|e-mail": "email",
        r"phone|tel|mobile|cell": "phone",
        r"domain|site|website|url": "domain",
        r"username|handle|user": "username",
        r"ip|ip_address|ipaddr": "ip",
        r"address|location|place": "address",
    }

    # Known relationship patterns
    RELATIONSHIP_PATTERNS = {
        r"officer|director|executive": "officer_of",
        r"owner|owns|ownership": "owns",
        r"shareholder|stockholder": "shareholder_of",
        r"employee|works_at|employed": "employed_by",
        r"links_to|backlink|outlink": "links_to",
        r"found_on|appears_on": "found_on",
        r"mentions|references": "mentions",
        r"same_as|identical|duplicate": "same_as",
        r"related|associated|connected": "related_to",
    }

    def __init__(self, project_id: str = "default"):
        self.project_id = project_id
        self.tracker = StatusTracker(project_id)
        self._load_canonical_data()

    def _load_canonical_data(self):
        """Load canonical type and relationship definitions."""
        self.canonical_types = set()
        self.canonical_relationships = set()

        # Load from entity_class_type_matrix.json
        try:
            matrix_path = CANONICAL_PATHS["entity_class_type_matrix"]
            if Path(matrix_path).exists():
                with open(matrix_path) as f:
                    matrix = json.load(f)
                # Extract all types from all classes
                for class_data in matrix.get("classes", {}).values():
                    for type_category in class_data.get("types", {}).values():
                        if isinstance(type_category, list):
                            self.canonical_types.update(type_category)
                        elif isinstance(type_category, dict):
                            self.canonical_types.update(type_category.keys())
        except Exception as e:
            logger.warning(f"Could not load entity matrix: {e}")
            # Fallback to NODE_CLASSES
            for class_def in NODE_CLASSES.values():
                for types in class_def.get("types", {}).values():
                    if isinstance(types, list):
                        self.canonical_types.update(types)

        # Load relationships
        try:
            rel_path = CANONICAL_PATHS["relationships"]
            if Path(rel_path).exists():
                with open(rel_path) as f:
                    rel_data = json.load(f)
                for rel_name in rel_data.get("relationships", {}).keys():
                    self.canonical_relationships.add(rel_name)
        except Exception as e:
            logger.warning(f"Could not load relationships: {e}")
            # Use default root relationships from NODE_CLASSES
            self.canonical_relationships = set(NODE_CLASSES["NEXUS"].get("root_relationships", []))

    def analyze_module(self, module_path: str) -> ModuleAnalysis:
        """
        Analyze a module to discover its output types and patterns.

        Args:
            module_path: Path to the module directory or file

        Returns:
            ModuleAnalysis with discovered types and patterns
        """
        path = Path(module_path)
        module_name = path.stem if path.is_file() else path.name

        analysis = ModuleAnalysis(
            module_name=module_name,
            module_path=str(path)
        )

        # Check for existing bridge
        if path.is_dir():
            bridge_candidates = list(path.glob("*c1_bridge*.py"))
            if bridge_candidates:
                analysis.has_existing_bridge = True
                analysis.existing_bridge_path = str(bridge_candidates[0])

        # Analyze Python files
        py_files = []
        if path.is_file() and path.suffix == ".py":
            py_files = [path]
        elif path.is_dir():
            py_files = list(path.glob("**/*.py"))

        for py_file in py_files:
            try:
                self._analyze_python_file(py_file, analysis)
            except Exception as e:
                analysis.warnings.append(f"Could not analyze {py_file}: {e}")

        # Deduplicate and sort
        analysis.output_types = sorted(set(analysis.output_types))
        analysis.edge_types = sorted(set(analysis.edge_types))
        analysis.input_types = sorted(set(analysis.input_types))

        # Generate recommended mappings
        analysis.recommended_mappings = self._generate_mappings(analysis)

        # Create tracking task
        self.tracker.add_c1_bridge_task(
            module_name=module_name,
            module_path=str(path),
            output_types=analysis.output_types
        )

        return analysis

    def _analyze_python_file(self, file_path: Path, analysis: ModuleAnalysis):
        """Analyze a single Python file for entity/relationship patterns."""
        try:
            content = file_path.read_text()
        except Exception:
            return

        # Parse AST for deeper analysis
        try:
            tree = ast.parse(content)
            self._analyze_ast(tree, analysis)
        except SyntaxError:
            pass

        # Pattern matching on raw code
        content_lower = content.lower()

        # Find entity type mentions
        for pattern, entity_type in self.ENTITY_PATTERNS.items():
            if re.search(pattern, content_lower):
                analysis.output_types.append(entity_type)

        # Find relationship mentions
        for pattern, rel_type in self.RELATIONSHIP_PATTERNS.items():
            if re.search(pattern, content_lower):
                analysis.edge_types.append(rel_type)

        # Look for specific patterns

        # Pattern: Dictionary with "type" key
        type_dicts = re.findall(r'["\']type["\']\s*:\s*["\'](\w+)["\']', content)
        for t in type_dicts:
            if t.lower() in self.canonical_types or self._fuzzy_match_type(t):
                analysis.output_types.append(self._normalize_type(t))

        # Pattern: Node class references
        node_class_refs = re.findall(r'node_class\s*[=:]\s*["\'](\w+)["\']', content)
        for nc in node_class_refs:
            analysis.node_creation_patterns.append({
                "type": "node_class_assignment",
                "value": nc,
                "file": str(file_path)
            })

        # Pattern: Entity type assignments
        entity_type_refs = re.findall(r'entity_type\s*[=:]\s*["\'](\w+)["\']', content)
        for et in entity_type_refs:
            analysis.output_types.append(self._normalize_type(et))

        # Pattern: Elasticsearch indexing
        if "elasticsearch" in content_lower or "es.index" in content_lower or "helpers.bulk" in content_lower:
            analysis.indexing_patterns.append({
                "type": "elasticsearch_indexing",
                "file": str(file_path)
            })

    def _analyze_ast(self, tree: ast.AST, analysis: ModuleAnalysis):
        """Analyze AST for type definitions and patterns."""
        for node in ast.walk(tree):
            # Look for dataclass definitions
            if isinstance(node, ast.ClassDef):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name) and decorator.id == "dataclass":
                        # This is a dataclass - check fields
                        for item in node.body:
                            if isinstance(item, ast.AnnAssign):
                                field_name = item.target.id if isinstance(item.target, ast.Name) else ""
                                if field_name in ["type", "entity_type", "node_type"]:
                                    analysis.node_creation_patterns.append({
                                        "type": "dataclass_type_field",
                                        "class_name": node.name
                                    })

            # Look for function definitions that might create entities
            if isinstance(node, ast.FunctionDef):
                if any(keyword in node.name.lower() for keyword in ["create", "extract", "build", "make"]):
                    if any(keyword in node.name.lower() for keyword in ["node", "entity", "person", "company"]):
                        analysis.node_creation_patterns.append({
                            "type": "entity_creation_function",
                            "function_name": node.name
                        })

    def _fuzzy_match_type(self, type_str: str) -> bool:
        """Check if a type string fuzzy-matches any canonical type."""
        type_lower = type_str.lower()
        for pattern in self.ENTITY_PATTERNS.keys():
            if re.search(pattern, type_lower):
                return True
        return False

    def _normalize_type(self, type_str: str) -> str:
        """Normalize a type string to canonical form."""
        type_lower = type_str.lower()

        # Direct match
        if type_lower in self.canonical_types:
            return type_lower

        # Pattern match
        for pattern, canonical in self.ENTITY_PATTERNS.items():
            if re.search(pattern, type_lower):
                return canonical

        return type_lower

    def _generate_mappings(self, analysis: ModuleAnalysis) -> List[Dict]:
        """Generate recommended type mappings for the module."""
        mappings = []

        for output_type in analysis.output_types:
            canonical = self._normalize_type(output_type)
            node_class = get_node_class(canonical)

            mappings.append({
                "module_type": output_type,
                "canonical_type": canonical,
                "node_class": node_class,
                "confidence": 0.9 if canonical in self.canonical_types else 0.7
            })

        return mappings

    def generate_bridge(
        self,
        analysis: ModuleAnalysis,
        config: Optional[BridgeConfig] = None
    ) -> str:
        """
        Generate C1 bridge code for a module.

        Args:
            analysis: Module analysis results
            config: Optional custom configuration

        Returns:
            Generated Python code for the bridge
        """
        if config is None:
            config = self._create_default_config(analysis)

        # Build type map entries
        type_map_entries = "{\n"
        for mapping in analysis.recommended_mappings:
            type_map_entries += f'        "{mapping["module_type"]}": "{mapping["canonical_type"]}",\n'
        type_map_entries += "    }"

        # Generate from template
        bridge_code = C1_BRIDGE_TEMPLATE.format(
            module_name=analysis.module_name.upper(),
            module_name_lower=analysis.module_name.lower(),
            node_types_list=", ".join(analysis.output_types),
            edge_types_list=", ".join(analysis.edge_types) or "embedded edges",
            default_project="default",
            type_map_entries=type_map_entries
        )

        # Add module-specific transform method
        transform_method = self._generate_transform_method(analysis)
        bridge_code = bridge_code.replace(
            "raise NotImplementedError(\"Implement _transform_result in subclass\")",
            transform_method
        )

        return bridge_code

    def _create_default_config(self, analysis: ModuleAnalysis) -> BridgeConfig:
        """Create default bridge configuration from analysis."""
        type_map = {}
        for mapping in analysis.recommended_mappings:
            type_map[mapping["module_type"]] = mapping["canonical_type"]

        return BridgeConfig(
            module_name=analysis.module_name,
            module_path=analysis.module_path,
            bridge_file=f"{analysis.module_name.lower()}_c1_bridge.py",
            type_map=type_map,
            source_system=analysis.module_name.lower()
        )

    def _generate_transform_method(self, analysis: ModuleAnalysis) -> str:
        """Generate the _transform_result method for the bridge."""
        # Build extraction logic based on discovered patterns
        code = '''"""Transform module result to C1Node."""
        if not result:
            return None

        # Extract entity type
        entity_type = result.get("type") or result.get("entity_type") or "unknown"
        node_type = self.TYPE_MAP.get(entity_type.lower(), entity_type)

        # Extract value
        value = (
            result.get("value") or
            result.get("name") or
            result.get("canonical_value") or
            result.get("label") or
            ""
        )

        if not value:
            return None

        # Create node
        node = self.create_node(
            entity_type=node_type,
            value=value,
            label=result.get("label", value),
            metadata=result.get("metadata", {})
        )

        # Add edges if present
        for edge in result.get("edges", []) + result.get("relationships", []):
            target_type = edge.get("target_type", "entity")
            target_value = edge.get("target", "") or edge.get("target_value", "")
            relation = edge.get("relation", "") or edge.get("type", "related_to")

            if target_value:
                target_node = self.create_node(
                    entity_type=target_type,
                    value=target_value,
                    label=target_value
                )
                node.embedded_edges.append(asdict(EmbeddedEdge(
                    target_id=target_node.id,
                    target_class=self._get_node_class(target_type),
                    target_type=target_type,
                    target_label=target_value,
                    relation=relation,
                    direction="outgoing",
                    confidence=edge.get("confidence", 0.85)
                )))

        return node'''

        return code

    def validate_bridge(self, bridge_code: str) -> Dict[str, Any]:
        """
        Validate bridge code against canonical standards.

        Args:
            bridge_code: Generated bridge Python code

        Returns:
            Validation results with errors and warnings
        """
        results = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "checks": []
        }

        # Check 1: Valid Python syntax
        try:
            ast.parse(bridge_code)
            results["checks"].append({"check": "syntax", "passed": True})
        except SyntaxError as e:
            results["valid"] = False
            results["errors"].append(f"Syntax error: {e}")
            results["checks"].append({"check": "syntax", "passed": False, "error": str(e)})
            return results

        # Check 2: Required imports
        required_imports = ["hashlib", "datetime", "elasticsearch"]
        for imp in required_imports:
            if imp not in bridge_code:
                results["warnings"].append(f"Missing recommended import: {imp}")
        results["checks"].append({"check": "imports", "passed": True})

        # Check 3: Required classes
        if "class C1Node" not in bridge_code and "C1Node" not in bridge_code:
            results["warnings"].append("No C1Node class/import found")
        if "class C1Bridge" not in bridge_code:
            results["errors"].append("Missing C1Bridge class")
            results["valid"] = False
        results["checks"].append({"check": "required_classes", "passed": "C1Bridge" in bridge_code})

        # Check 4: Type mappings use canonical types
        type_map_match = re.search(r'TYPE_MAP\s*=\s*\{([^}]+)\}', bridge_code, re.DOTALL)
        if type_map_match:
            type_values = re.findall(r':\s*["\'](\w+)["\']', type_map_match.group(1))
            for tv in type_values:
                if tv not in self.canonical_types and tv != "entity":
                    results["warnings"].append(f"Non-canonical type in TYPE_MAP: {tv}")
        results["checks"].append({"check": "type_mappings", "passed": True})

        # Check 5: ID generation uses deterministic hash
        if "sha256" not in bridge_code and "generate_id" not in bridge_code:
            results["warnings"].append("No deterministic ID generation found")
        results["checks"].append({"check": "id_generation", "passed": "sha256" in bridge_code or "generate_id" in bridge_code})

        # Check 6: Embedded edges structure
        if "embedded_edges" in bridge_code:
            results["checks"].append({"check": "embedded_edges", "passed": True})
        else:
            results["warnings"].append("No embedded_edges handling found")
            results["checks"].append({"check": "embedded_edges", "passed": False})

        return results

    def save_bridge(
        self,
        bridge_code: str,
        output_path: str,
        task_id: Optional[str] = None
    ) -> str:
        """
        Save generated bridge code to file.

        Args:
            bridge_code: Generated Python code
            output_path: Where to save the file
            task_id: Optional task ID to update in tracker

        Returns:
            Path to saved file
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(bridge_code)

        if task_id:
            self.tracker.update_c1_bridge_task(task_id, {
                "status": "complete",
                "bridge_file": str(path),
                "completed_at": datetime.utcnow().isoformat()
            })

        logger.info(f"Saved bridge to: {path}")
        return str(path)

    def get_pending_bridges(self) -> List[Dict]:
        """Get all pending C1 bridge tasks."""
        return self.tracker.get_c1_bridge_tasks(status="pending")

    def get_bridge_status(self, module_name: str) -> Optional[Dict]:
        """Get status of a specific bridge task."""
        tasks = self.tracker.get_c1_bridge_tasks()
        for task in tasks:
            if task.get("module_name") == module_name:
                return task
        return None


# CLI interface
if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="C-1 Bridge Builder")
    parser.add_argument("module_path", help="Path to module to analyze")
    parser.add_argument("--project", "-p", default="default", help="Project ID")
    parser.add_argument("--output", "-o", help="Output path for generated bridge")
    parser.add_argument("--analyze-only", action="store_true", help="Only analyze, don't generate")

    args = parser.parse_args()

    builder = C1BridgeBuilder(project_id=args.project)

    print(f"\nAnalyzing module: {args.module_path}")
    print("=" * 60)

    analysis = builder.analyze_module(args.module_path)

    print(f"\nModule: {analysis.module_name}")
    print(f"Path: {analysis.module_path}")
    print(f"Has existing bridge: {analysis.has_existing_bridge}")
    if analysis.existing_bridge_path:
        print(f"Existing bridge: {analysis.existing_bridge_path}")

    print(f"\nOutput types discovered: {analysis.output_types}")
    print(f"Edge types discovered: {analysis.edge_types}")
    print(f"Node creation patterns: {len(analysis.node_creation_patterns)}")
    print(f"Indexing patterns: {len(analysis.indexing_patterns)}")

    if analysis.warnings:
        print(f"\nWarnings:")
        for w in analysis.warnings:
            print(f"  - {w}")

    print(f"\nRecommended mappings:")
    for m in analysis.recommended_mappings:
        print(f"  {m['module_type']} -> {m['canonical_type']} ({m['node_class']}) [{m['confidence']:.0%}]")

    if not args.analyze_only:
        print("\n" + "=" * 60)
        print("Generating bridge code...")

        bridge_code = builder.generate_bridge(analysis)

        # Validate
        validation = builder.validate_bridge(bridge_code)
        print(f"\nValidation: {'PASSED' if validation['valid'] else 'FAILED'}")
        for check in validation["checks"]:
            status = "OK" if check["passed"] else "WARN"
            print(f"  [{status}] {check['check']}")

        if validation["warnings"]:
            print("\nWarnings:")
            for w in validation["warnings"]:
                print(f"  - {w}")

        if args.output:
            saved_path = builder.save_bridge(bridge_code, args.output)
            print(f"\nSaved to: {saved_path}")
        else:
            print("\n--- Generated Bridge Code Preview (first 100 lines) ---")
            lines = bridge_code.split('\n')[:100]
            for i, line in enumerate(lines, 1):
                print(f"{i:4d} | {line}")
            if len(bridge_code.split('\n')) > 100:
                print("... (truncated)")
