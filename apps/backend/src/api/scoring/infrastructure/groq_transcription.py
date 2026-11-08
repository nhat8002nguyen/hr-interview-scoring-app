"""Groq Whisper adapter implementing :class:`TranscriptionPort`."""

import httpx

from api.scoring.application.ports import TranscriptionError


class GroqTranscription:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = (
            client if client is not None else httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        )

    async def transcribe(
        self,
        data: bytes,
        *,
        filename: str,
        language: str = "en",
    ) -> str:
        try:
            response = await self._client.post(
                f"{self._base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                data={
                    "model": self._model,
                    "language": language,
                    "response_format": "json",
                },
                files={"file": (filename, data)},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TranscriptionError(f"Groq transcription request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise TranscriptionError("Groq transcription response was not JSON") from exc

        if not isinstance(payload, dict):
            raise TranscriptionError("Groq transcription response must be a JSON object")

        text = payload.get("text")
        if not isinstance(text, str) or text.strip() == "":
            raise TranscriptionError("Groq transcription text was empty")

        return text.strip()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
