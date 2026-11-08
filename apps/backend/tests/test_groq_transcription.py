import httpx
import pytest

from api.scoring.application.ports import TranscriptionError
from api.scoring.infrastructure.groq_transcription import GroqTranscription


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_transcribe_posts_multipart_and_returns_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/audio/transcriptions")
        assert request.headers["Authorization"] == "Bearer test-key"
        assert b"whisper-large-v3" in request.content
        assert b'name="language"' in request.content and b"en" in request.content
        return httpx.Response(200, json={"text": " hello world "})

    groq = GroqTranscription(
        "test-key",
        "whisper-large-v3",
        "https://api.groq.com/openai/v1",
        client=_client(handler),
    )
    text = await groq.transcribe(b"fake-audio", filename="answer.m4a", language="en")
    assert text == "hello world"
    await groq.aclose()


@pytest.mark.asyncio
async def test_transcribe_http_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="nope")

    groq = GroqTranscription(
        "test-key",
        "whisper-large-v3",
        "https://api.groq.com/openai/v1",
        client=_client(handler),
    )
    with pytest.raises(TranscriptionError):
        await groq.transcribe(b"x", filename="a.m4a")
    await groq.aclose()


@pytest.mark.asyncio
async def test_transcribe_empty_text_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": "   "})

    groq = GroqTranscription(
        "test-key",
        "whisper-large-v3",
        "https://api.groq.com/openai/v1",
        client=_client(handler),
    )
    with pytest.raises(TranscriptionError):
        await groq.transcribe(b"x", filename="a.m4a")
    await groq.aclose()
