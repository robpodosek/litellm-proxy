from free_frontier.capabilities import missing_capabilities, required_capabilities
from free_frontier.models import Capability


def test_extracts_streaming_tools_structured_output_and_vision() -> None:
    required = required_capabilities(
        {
            "stream": True,
            "tools": [{"type": "function", "function": {"name": "lookup"}}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "answer"}},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "describe this"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,x"}},
                    ],
                }
            ],
        }
    )

    assert required == {
        Capability.STREAMING,
        Capability.TOOLS,
        Capability.STRUCTURED_OUTPUT,
        Capability.VISION,
    }


def test_text_response_format_does_not_require_structured_output() -> None:
    required = required_capabilities(
        {
            "stream": False,
            "messages": [{"role": "user", "content": "hello"}],
            "response_format": {"type": "text"},
        }
    )

    assert Capability.STRUCTURED_OUTPUT not in required


def test_legacy_function_fields_require_tool_capability() -> None:
    required = required_capabilities(
        {
            "messages": [{"role": "user", "content": "hello"}],
            "functions": [{"name": "lookup", "parameters": {"type": "object"}}],
        }
    )

    assert required == {Capability.TOOLS}


def test_missing_capabilities_returns_only_required_features_not_supported() -> None:
    missing = missing_capabilities(
        frozenset({Capability.STREAMING, Capability.TOOLS}),
        frozenset({Capability.STREAMING, Capability.STRUCTURED_OUTPUT}),
    )

    assert missing == {Capability.STRUCTURED_OUTPUT}
