"""Pin the local-tier (Ollama) request body shape -- specifically that
think:false can never silently disappear from it.

No live model call here: this is a pure-function test against
`build_local_chat_request`, run in CI (Tech_Scope.md §5, S0 row: "this is
the one real assertion here and it's the point of the slice").
"""

from task_router.local_request import build_local_chat_request


def test_think_is_pinned_false():
    body = build_local_chat_request("hi")

    assert body["think"] is False


def test_stream_is_pinned_false():
    body = build_local_chat_request("hi")

    assert body["stream"] is False


def test_model_and_messages_shape():
    body = build_local_chat_request("hi", model="qwen3:1.7b")

    assert body["model"] == "qwen3:1.7b"
    assert body["messages"] == [{"role": "user", "content": "hi"}]


def test_default_model_is_qwen3_1_7b():
    body = build_local_chat_request("hi")

    assert body["model"] == "qwen3:1.7b"
