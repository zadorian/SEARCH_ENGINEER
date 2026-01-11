import pytest


def test_parse_io_prefix_social_media_preserves_platform():
    from modules.syntax.executor import parse_io_prefix

    entity_type, value, jurisdiction = parse_io_prefix("fb: John Smith")
    assert entity_type == "social_media"
    assert value.lower().startswith("fb:")
    assert "john smith" in value.lower()
    assert jurisdiction is None

    entity_type, value, jurisdiction = parse_io_prefix("social: Acme Corp")
    assert entity_type == "social_media"
    assert value.lower().startswith("social:")
    assert "acme" in value.lower()
    assert jurisdiction is None


def test_parse_io_prefix_normalizes_linkedin_slug_and_url():
    from modules.syntax.executor import parse_io_prefix

    entity_type, value, _ = parse_io_prefix("li: melissa-smet-529476130")
    assert entity_type == "linkedin_url"
    assert value == "https://linkedin.com/in/melissa-smet-529476130"

    entity_type, value, _ = parse_io_prefix("li: https://www.linkedin.com/in/foo/?trk=abc#x")
    assert entity_type == "linkedin_url"
    assert value == "https://linkedin.com/in/foo"


def test_parse_io_prefix_parses_linkedin_username_slug():
    from modules.syntax.executor import parse_io_prefix

    entity_type, value, _ = parse_io_prefix("liu: melissa-smet-529476130")
    assert entity_type == "linkedin_username"
    assert value == "melissa-smet-529476130"

    entity_type, value, _ = parse_io_prefix("liu: https://linkedin.com/in/foo/?trk=abc#x")
    assert entity_type == "linkedin_username"
    assert value == "foo"


def test_has_io_prefix_includes_li_u_and_social():
    from modules.syntax.executor import has_io_prefix

    assert has_io_prefix("li: foo")
    assert has_io_prefix("liu: foo")
    assert has_io_prefix("u: foo")
    assert has_io_prefix("twitter: @foo")
    assert has_io_prefix("social: foo")


def test_looks_like_submarine_exploration_detects_indom_inurl_and_hops():
    from modules.syntax.executor import looks_like_submarine_exploration

    assert looks_like_submarine_exploration("indom: pharma")
    assert looks_like_submarine_exploration('inurl:"login" hop(2)')
    assert not looks_like_submarine_exploration("p: John Smith")


def test_parse_io_exec_flags_strips_and_parses_values():
    from modules.syntax.executor import _parse_io_exec_flags

    flags, cleaned = _parse_io_exec_flags(
        "e: test@example.com --recurse --max-depth 3 --max-nodes 10 --recurse-types email,domain"
    )

    assert cleaned == "e: test@example.com"
    assert flags["recurse"] is True
    assert flags["max_depth"] == 3
    assert flags["max_nodes"] == 10
    assert flags["recurse_types"] == ["email", "domain"]


@pytest.mark.asyncio
async def test_execute_io_uses_recursive_when_flag_set():
    from modules.syntax.executor import UnifiedExecutor

    class DummyIO:
        def __init__(self):
            self.project_id = "proj"
            self.calls = []

        async def execute(self, *args, **kwargs):
            self.calls.append(("execute", args, kwargs))
            return {"mode": "execute"}

        async def execute_recursive(self, *args, **kwargs):
            self.calls.append(("execute_recursive", args, kwargs))
            return {"mode": "execute_recursive"}

    executor = UnifiedExecutor()
    executor._io_router = object()
    executor._io_executor = DummyIO()

    result = await executor._execute_io("e: test@example.com --recurse --max-depth 3", project_id="proj")

    assert result.get("_executor") == "io"
    assert result.get("_project_id") == "proj"
    assert executor._io_executor.calls
    call_name, _args, kwargs = executor._io_executor.calls[0]
    assert call_name == "execute_recursive"
    assert kwargs.get("persist_project") == "proj"
    assert kwargs.get("max_depth") == 3


@pytest.mark.asyncio
async def test_config_driven_router_skips_missing_index():
    from INPUT_OUTPUT.matrix.io_cli import ConfigDrivenRouter

    class DummyIndices:
        def exists(self, index):
            return False

    class DummyES:
        def __init__(self):
            self.indices = DummyIndices()

    router = ConfigDrivenRouter()
    router._get_es_client = lambda: DummyES()

    res = await router.execute_elasticsearch("cymonides-3", "test", query_type="match")
    assert res.get("status") == "missing_index"
    assert res.get("index") == "cymonides-3"
    assert res.get("total") == 0


def test_config_driven_router_maps_linkedin_username_to_linkedin_url_code():
    from INPUT_OUTPUT.matrix.io_cli import ConfigDrivenRouter

    router = ConfigDrivenRouter()
    assert router.get_field_code("linkedin_url") == 5
    assert router.get_field_code("linkedin_username") == 5


def test_io_cli_extract_pivot_entities_extracts_linkedin_username():
    from INPUT_OUTPUT.matrix import io_cli

    pivots = io_cli._extract_pivot_entities({"linkedin_url": "https://linkedin.com/in/foo-bar"})
    assert pivots.get("linkedin_url") == ["https://linkedin.com/in/foo-bar"]
    assert pivots.get("linkedin_username") == ["foo-bar"]
