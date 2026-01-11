"""
SASTRE Tool Validators
Input validation functions for production hardening.
"""

from typing import Dict, Any, List

class ValidationError(Exception):
    """Input validation error."""
    pass

def validate_execute_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate execute tool arguments."""
    if not args.get("query"):
        raise ValidationError("query is required")
    if len(str(args["query"])) > 2000:
        raise ValidationError("query too long (max 2000 chars)")
    args["project_id"] = args.get("project_id", "default")
    return args

def validate_assess_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate assess tool arguments."""
    if not args.get("project_id"):
        args["project_id"] = "default"
    return args

def validate_query_lab_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate query_lab_build arguments."""
    if not args.get("intent"):
        raise ValidationError("intent is required")
    return args

def validate_stream_finding_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate stream_finding arguments."""
    if not args.get("watcher_id"):
        raise ValidationError("watcher_id is required")
    if not args.get("content"):
        raise ValidationError("content is required")
    return args

def validate_resolve_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate resolve (disambiguator) arguments."""
    if not args.get("project_id"):
        args["project_id"] = "default"
    operation = args.get("operation", "detect")
    if operation not in ["detect", "fuse", "repel", "binary_star", "auto"]:
        raise ValidationError(f"Invalid operation: {operation}")
    return args

def validate_edith_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate EDITH tool arguments."""
    if not args.get("project_id"):
        args["project_id"] = "default"
    return args

def validate_torpedo_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate TORPEDO tool arguments."""
    if not args.get("query"):
        raise ValidationError("query is required for TORPEDO")
    return args

def validate_investigate_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate investigation tool arguments."""
    if not args.get("target"):
        raise ValidationError("target is required")
    if not args.get("project_id"):
        args["project_id"] = "default"
    return args

def validate_watcher_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate watcher tool arguments."""
    if not args.get("project_id"):
        args["project_id"] = "default"
    return args

def validate_nexus_brute_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate nexus_brute arguments."""
    if not args.get("query"):
        raise ValidationError("query is required for BRUTE search")
    return args

# Export all validators
VALIDATORS = {
    "execute": validate_execute_args,
    "assess": validate_assess_args,
    "query_lab_build": validate_query_lab_args,
    "stream_finding": validate_stream_finding_args,
    "resolve": validate_resolve_args,
    "edith_rewrite": validate_edith_args,
    "edith_answer": validate_edith_args,
    "edith_edit_section": validate_edith_args,
    "torpedo_search": validate_torpedo_args,
    "torpedo_process": validate_torpedo_args,
    "investigate_person": validate_investigate_args,
    "investigate_company": validate_investigate_args,
    "investigate_domain": validate_investigate_args,
    "investigate_phone": validate_investigate_args,
    "investigate_email": validate_investigate_args,
    "get_watchers": validate_watcher_args,
    "create_watcher": validate_watcher_args,
    "nexus_brute": validate_nexus_brute_args,
}
