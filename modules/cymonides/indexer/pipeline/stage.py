"""
Pipeline Stages - Building blocks for data transformation
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
import hashlib
import re


@dataclass
class StageResult:
    """Result from a pipeline stage"""
    success: bool
    data: Optional[Dict[str, Any]]
    action: str = "continue"  # continue, skip, dlq
    error: Optional[str] = None
    transform_name: Optional[str] = None
    
    @classmethod
    def ok(cls, data: Dict[str, Any], transform_name: str = None) -> 'StageResult':
        return cls(success=True, data=data, transform_name=transform_name)
    
    @classmethod
    def skip(cls, reason: str = None) -> 'StageResult':
        return cls(success=True, data=None, action="skip", error=reason)
    
    @classmethod
    def fail(cls, error: str, send_to_dlq: bool = False) -> 'StageResult':
        return cls(
            success=False, 
            data=None, 
            action="dlq" if send_to_dlq else "skip",
            error=error
        )


class PipelineStage(ABC):
    """Base class for all pipeline stages"""
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
        self.processed_count = 0
        self.error_count = 0
        self.skip_count = 0
    
    @abstractmethod
    def process(self, data: Dict[str, Any]) -> StageResult:
        """Process a single document"""
        pass
    
    def process_batch(self, batch: List[Dict[str, Any]]) -> List[StageResult]:
        """Process a batch of documents"""
        return [self.process(doc) for doc in batch]
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "processed": self.processed_count,
            "errors": self.error_count,
            "skipped": self.skip_count,
        }


class TransformStage(PipelineStage):
    """Stage that transforms document fields"""
    
    def __init__(
        self,
        name: str,
        transforms: Dict[str, Callable[[Any], Any]] = None,
        field_renames: Dict[str, str] = None,
        field_defaults: Dict[str, Any] = None,
        add_fields: Dict[str, Any] = None,
        remove_fields: List[str] = None,
    ):
        super().__init__(name)
        self.transforms = transforms or {}
        self.field_renames = field_renames or {}
        self.field_defaults = field_defaults or {}
        self.add_fields = add_fields or {}
        self.remove_fields = remove_fields or []
    
    def process(self, data: Dict[str, Any]) -> StageResult:
        try:
            result = data.copy()
            
            # Apply field transforms
            for field, transform_fn in self.transforms.items():
                if field in result:
                    result[field] = transform_fn(result[field])
            
            # Rename fields
            for old_name, new_name in self.field_renames.items():
                if old_name in result:
                    result[new_name] = result.pop(old_name)
            
            # Add default values for missing fields
            for field, default in self.field_defaults.items():
                if field not in result or result[field] is None:
                    result[field] = default() if callable(default) else default
            
            # Add static fields
            for field, value in self.add_fields.items():
                result[field] = value() if callable(value) else value
            
            # Remove fields
            for field in self.remove_fields:
                result.pop(field, None)
            
            self.processed_count += 1
            return StageResult.ok(result, self.name)
        
        except Exception as e:
            self.error_count += 1
            return StageResult.fail(f"Transform error: {str(e)}")


class FilterStage(PipelineStage):
    """Stage that filters documents based on conditions"""
    
    def __init__(
        self,
        name: str,
        required_fields: List[str] = None,
        field_conditions: Dict[str, Callable[[Any], bool]] = None,
        custom_filter: Callable[[Dict[str, Any]], bool] = None,
        min_field_count: int = 0,
    ):
        super().__init__(name)
        self.required_fields = required_fields or []
        self.field_conditions = field_conditions or {}
        self.custom_filter = custom_filter
        self.min_field_count = min_field_count
    
    def process(self, data: Dict[str, Any]) -> StageResult:
        try:
            # Check required fields
            for field in self.required_fields:
                if field not in data or data[field] is None:
                    self.skip_count += 1
                    return StageResult.skip(f"Missing required field: {field}")
            
            # Check field conditions
            for field, condition in self.field_conditions.items():
                if field in data:
                    if not condition(data[field]):
                        self.skip_count += 1
                        return StageResult.skip(f"Field condition failed: {field}")
            
            # Check minimum field count
            non_null_fields = sum(1 for v in data.values() if v is not None)
            if non_null_fields < self.min_field_count:
                self.skip_count += 1
                return StageResult.skip(f"Too few fields: {non_null_fields} < {self.min_field_count}")
            
            # Custom filter
            if self.custom_filter and not self.custom_filter(data):
                self.skip_count += 1
                return StageResult.skip("Custom filter rejected")
            
            self.processed_count += 1
            return StageResult.ok(data, self.name)
        
        except Exception as e:
            self.error_count += 1
            return StageResult.fail(f"Filter error: {str(e)}")


class EnrichStage(PipelineStage):
    """Stage that enriches documents with derived/computed fields"""
    
    def __init__(
        self,
        name: str,
        enrichments: Dict[str, Callable[[Dict[str, Any]], Any]] = None,
    ):
        super().__init__(name)
        self.enrichments = enrichments or {}
    
    def process(self, data: Dict[str, Any]) -> StageResult:
        try:
            result = data.copy()
            
            for field, enrichment_fn in self.enrichments.items():
                try:
                    result[field] = enrichment_fn(result)
                except Exception:
                    pass  # Skip failed enrichments
            
            self.processed_count += 1
            return StageResult.ok(result, self.name)
        
        except Exception as e:
            self.error_count += 1
            return StageResult.fail(f"Enrich error: {str(e)}")


class DedupeStage(PipelineStage):
    """Stage that deduplicates documents based on a key"""
    
    def __init__(
        self,
        name: str,
        key_fields: List[str],
        hash_algorithm: str = "md5",
    ):
        super().__init__(name)
        self.key_fields = key_fields
        self.hash_algorithm = hash_algorithm
        self._seen_keys = set()
    
    def _compute_key(self, data: Dict[str, Any]) -> str:
        key_values = [str(data.get(f, "")) for f in self.key_fields]
        key_string = "|".join(key_values)
        
        if self.hash_algorithm == "md5":
            return hashlib.md5(key_string.encode()).hexdigest()
        elif self.hash_algorithm == "sha256":
            return hashlib.sha256(key_string.encode()).hexdigest()
        else:
            return key_string
    
    def process(self, data: Dict[str, Any]) -> StageResult:
        try:
            key = self._compute_key(data)
            
            if key in self._seen_keys:
                self.skip_count += 1
                return StageResult.skip("Duplicate")
            
            self._seen_keys.add(key)
            data["_dedupe_key"] = key
            
            self.processed_count += 1
            return StageResult.ok(data, self.name)
        
        except Exception as e:
            self.error_count += 1
            return StageResult.fail(f"Dedupe error: {str(e)}")
    
    def reset(self):
        """Reset seen keys (e.g., between files)"""
        self._seen_keys.clear()


# Common transform functions
class CommonTransforms:
    """Library of common transform functions"""
    
    @staticmethod
    def lowercase(value: str) -> str:
        return value.lower() if isinstance(value, str) else value
    
    @staticmethod
    def uppercase(value: str) -> str:
        return value.upper() if isinstance(value, str) else value
    
    @staticmethod
    def strip(value: str) -> str:
        return value.strip() if isinstance(value, str) else value
    
    @staticmethod
    def extract_domain(email: str) -> Optional[str]:
        if isinstance(email, str) and '@' in email:
            return email.split('@')[1].lower()
        return None
    
    @staticmethod
    def normalize_phone(phone: str) -> str:
        if isinstance(phone, str):
            return re.sub(r'[^0-9+]', '', phone)
        return phone
    
    @staticmethod
    def hash_value(value: str, algorithm: str = "md5") -> str:
        if isinstance(value, str):
            if algorithm == "md5":
                return hashlib.md5(value.encode()).hexdigest()
            elif algorithm == "sha256":
                return hashlib.sha256(value.encode()).hexdigest()
        return value
    
    @staticmethod
    def timestamp_now() -> str:
        return datetime.utcnow().isoformat()
