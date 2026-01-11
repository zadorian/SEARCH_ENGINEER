"""
SASTRE Schema Reader - Reads from the REAL node schemas in Cymonides.

This module reads entity schemas from:
    BACKEND/modules/CYMONIDES/metadata/c-1/matrix_schema/nodes.json

NOT from hardcoded fake field lists.

The schema defines:
    - Entity types (person, company, phone, email, etc.)
    - Properties for each type (with required/optional, types, validation)
    - Which module handles each type (eyed, corporella, alldom, etc.)
    - FtM (Follow the Money) schema mappings
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set
from enum import Enum

logger = logging.getLogger(__name__)


class AbacusClass(Enum):
    """
    Abacus V4.2 canonical classes.
    """
    SUBJECT = "SUBJECT"
    LOCATION = "LOCATION"
    NEXUS = "NEXUS"
    NARRATIVE = "NARRATIVE"


class StorageClass(Enum):
    """Canonical schema classes as they appear in nodes.json."""
    SUBJECT = "SUBJECT"
    LOCATION = "LOCATION"
    NEXUS = "NEXUS"
    NARRATIVE = "NARRATIVE"


STORAGE_TO_ABACUS_CLASS: Dict[str, AbacusClass] = {
    "SUBJECT": AbacusClass.SUBJECT,
    "LOCATION": AbacusClass.LOCATION,
    "NEXUS": AbacusClass.NEXUS,
    "NARRATIVE": AbacusClass.NARRATIVE,
}


@dataclass
class PropertyDef:
    """A property definition from the schema."""
    name: str
    prop_type: str                           # string, array, object, date, enum, etc.
    required: bool = False
    codes: List[int] = field(default_factory=list)
    format: Optional[str] = None             # email, url, YYYY-MM-DD, etc.
    ftm_property: Optional[str] = None       # FtM schema mapping
    description: Optional[str] = None
    validation: Dict[str, Any] = field(default_factory=dict)
    enum_values: Optional[List[str]] = None

    @property
    def is_array(self) -> bool:
        return self.prop_type == "array"

    @property
    def is_object(self) -> bool:
        return self.prop_type == "object"


@dataclass
class EntityTypeDef:
    """An entity type definition from the schema."""
    type_name: str                           # person, company, email, etc.
    label: str                               # Human-readable: "Person", "Company"
    description: str
    # Abacus semantic class (SUBJECT/LOCATION/NEXUS/NARRATIVE)
    abacus_class: AbacusClass
    # Schema class from nodes.json (SUBJECT/LOCATION/NEXUS/NARRATIVE)
    storage_class: StorageClass
    codes: List[int] = field(default_factory=list)
    handled_by: List[str] = field(default_factory=list)  # eyed, corporella, alldom, etc.
    ftm_schema: Optional[str] = None         # Person, Company, etc.
    properties: Dict[str, PropertyDef] = field(default_factory=dict)

    @property
    def required_properties(self) -> List[PropertyDef]:
        """Get properties that are required."""
        return [p for p in self.properties.values() if p.required]

    @property
    def optional_properties(self) -> List[PropertyDef]:
        """Get properties that are optional."""
        return [p for p in self.properties.values() if not p.required]

    def get_empty_fields(self, data: Dict[str, Any]) -> List[str]:
        """
        Get fields that are empty in the provided data.

        This is the REAL slot detection - based on schema, not hardcoded lists.
        """
        empty = []

        for prop_name, prop_def in self.properties.items():
            value = data.get(prop_name)

            # Check if field is empty
            if value is None:
                empty.append(prop_name)
            elif prop_def.is_array and len(value) == 0:
                empty.append(prop_name)
            elif prop_def.is_object and not value:
                empty.append(prop_name)
            elif isinstance(value, str) and not value.strip():
                empty.append(prop_name)

        return empty

    def get_missing_required(self, data: Dict[str, Any]) -> List[str]:
        """Get required fields that are missing."""
        missing = []

        for prop in self.required_properties:
            value = data.get(prop.name)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(prop.name)

        return missing

    def get_enrichment_module(self) -> Optional[str]:
        """Get primary module for enriching this entity type."""
        if self.handled_by:
            return self.handled_by[0]
        return None


class CymonidesSchemaReader:
    """
    Reads and caches the real Cymonides node schema.

    This is the SINGLE SOURCE OF TRUTH for entity fields.
    """

    _instance: Optional['CymonidesSchemaReader'] = None
    _schema: Optional[Dict[str, Any]] = None
    _entity_types: Dict[str, EntityTypeDef] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._schema is None:
            self._load_schema()

    def _find_schema_path(self) -> Path:
        """Find the nodes.json schema file.

        AUTHORITATIVE SOURCE: CYMONIDES/metadata/c-1/matrix_schema/nodes.json
        This is the single source of truth for all node types.
        """
        # CYMONIDES is authoritative - try it first
        cymonides_path = Path(__file__).parent.parent.parent / "CYMONIDES" / "metadata" / "c-1" / "matrix_schema" / "nodes.json"

        # Fallback paths for other locations
        possible_paths = [
            # Authoritative: CYMONIDES (relative)
            cymonides_path,
            # Authoritative: CYMONIDES (absolute)
            Path("/Users/attic/01. DRILL_SEARCH/drill-search-app/BACKEND/modules/CYMONIDES/metadata/c-1/matrix_schema/nodes.json"),
            # Fallback: input_output (if CYMONIDES not found)
            Path(__file__).parent.parent.parent.parent.parent / "input_output" / "matrix" / "schema" / "nodes.json",
            Path(__file__).parent.parent.parent.parent.parent / "input_output2" / "matrix" / "schema" / "nodes.json",
        ]

        for p in possible_paths:
            if p.exists():
                logger.info(f"Using schema from: {p}")
                return p

        raise FileNotFoundError(f"Could not find nodes.json schema. Checked: {possible_paths}")

    def _load_schema(self):
        """Load the schema from nodes.json."""
        schema_path = self._find_schema_path()
        logger.info(f"Loading Cymonides schema from: {schema_path}")

        with open(schema_path, 'r') as f:
            self._schema = json.load(f)

        self._parse_schema()
        logger.info(f"Loaded {len(self._entity_types)} entity types from schema")

    def _parse_schema(self):
        """Parse the schema into EntityTypeDef objects."""
        classes = self._schema.get("classes", {})

        for class_name, class_def in classes.items():
            storage_class = StorageClass(class_name)
            abacus_class = STORAGE_TO_ABACUS_CLASS.get(class_name, AbacusClass.SUBJECT)
            types = class_def.get("types", {})

            for type_name, type_def in types.items():
                # Parse properties
                properties = {}
                for prop_name, prop_def in type_def.get("properties", {}).items():
                    properties[prop_name] = PropertyDef(
                        name=prop_name,
                        prop_type=prop_def.get("type", "string"),
                        required=prop_def.get("required", False),
                        codes=prop_def.get("codes", []),
                        format=prop_def.get("format"),
                        ftm_property=prop_def.get("ftm_property"),
                        description=prop_def.get("description"),
                        validation=prop_def.get("validation", {}),
                        enum_values=prop_def.get("values"),
                    )

                # Create entity type definition
                entity_type = EntityTypeDef(
                    type_name=type_name,
                    label=type_def.get("label", type_name.title()),
                    description=type_def.get("description", ""),
                    abacus_class=abacus_class,
                    storage_class=storage_class,
                    codes=type_def.get("codes", []),
                    handled_by=type_def.get("handled_by", []),
                    ftm_schema=type_def.get("ftm_schema"),
                    properties=properties,
                )

                self._entity_types[type_name] = entity_type

    def get_entity_type(self, type_name: str) -> Optional[EntityTypeDef]:
        """Get entity type definition by name."""
        return self._entity_types.get(type_name)

    def get_types_by_abacus_class(self, abacus_class: AbacusClass) -> List[EntityTypeDef]:
        """Get type definitions by Abacus class."""
        return [et for et in self._entity_types.values() if et.abacus_class == abacus_class]

    def get_all_entity_types(self) -> List[EntityTypeDef]:
        """Get all entity type definitions."""
        return list(self._entity_types.values())

    def get_entity_types_by_class(self, entity_class: Any) -> List[EntityTypeDef]:
        """
        Access by class name or enum.

        Accepts:
          - AbacusClass
          - StorageClass
          - string names ("SUBJECT", "LOCATION", ...)
        """
        if isinstance(entity_class, AbacusClass):
            return self.get_types_by_abacus_class(entity_class)
        if isinstance(entity_class, StorageClass):
            return [et for et in self._entity_types.values() if et.storage_class == entity_class]
        if isinstance(entity_class, str):
            key = entity_class.strip().upper()
            if key in AbacusClass.__members__:
                return self.get_types_by_abacus_class(AbacusClass[key])
            if key in StorageClass.__members__:
                return [et for et in self._entity_types.values() if et.storage_class == StorageClass[key]]
        return []

    def get_entity_types_handled_by(self, module: str) -> List[EntityTypeDef]:
        """Get all entity types handled by a specific module."""
        return [et for et in self._entity_types.values() if module in et.handled_by]

    def detect_empty_slots(
        self,
        entity_type: str,
        properties: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """
        Detect empty slots in an entity based on its real schema.

        Returns:
            {
                "missing_required": [...],
                "empty_optional": [...],
                "enrichment_module": "corporella"
            }
        """
        type_def = self.get_entity_type(entity_type)
        if not type_def:
            return {"missing_required": [], "empty_optional": [], "enrichment_module": None}

        missing_required = type_def.get_missing_required(properties)
        all_empty = type_def.get_empty_fields(properties)
        empty_optional = [f for f in all_empty if f not in missing_required]

        return {
            "missing_required": missing_required,
            "empty_optional": empty_optional,
            "enrichment_module": type_def.get_enrichment_module(),
        }

    def get_property_codes(self, entity_type: str, property_name: str) -> List[int]:
        """Get IO Matrix codes for a property."""
        type_def = self.get_entity_type(entity_type)
        if not type_def:
            return []

        prop = type_def.properties.get(property_name)
        return prop.codes if prop else []

    def get_all_property_names(self, entity_type: str) -> Set[str]:
        """Get all property names for an entity type."""
        type_def = self.get_entity_type(entity_type)
        if not type_def:
            return set()
        return set(type_def.properties.keys())


# Singleton accessor
def get_schema_reader() -> CymonidesSchemaReader:
    """Get the singleton schema reader instance."""
    return CymonidesSchemaReader()


# Convenience functions
def get_entity_slots(entity_type: str) -> List[str]:
    """Get all slot names for an entity type."""
    reader = get_schema_reader()
    type_def = reader.get_entity_type(entity_type)
    if not type_def:
        return []
    return list(type_def.properties.keys())


def get_required_slots(entity_type: str) -> List[str]:
    """Get required slot names for an entity type."""
    reader = get_schema_reader()
    type_def = reader.get_entity_type(entity_type)
    if not type_def:
        return []
    return [p.name for p in type_def.required_properties]


def get_enrichment_module(entity_type: str) -> Optional[str]:
    """Get the primary enrichment module for an entity type."""
    reader = get_schema_reader()
    type_def = reader.get_entity_type(entity_type)
    if not type_def:
        return None
    return type_def.get_enrichment_module()


def detect_gaps(entity_type: str, data: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Detect gaps (empty slots) in entity data.

    This is the REAL gap detection based on actual Cymonides schema.
    """
    reader = get_schema_reader()
    return reader.detect_empty_slots(entity_type, data)
