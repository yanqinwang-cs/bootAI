import json
from urllib import error, request


class OllamaClient:
    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        timeout_seconds: float = 60.0,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def chat(self, messages: list[dict[str, str]]) -> str:
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0},
        }
        request_body = json.dumps(body).encode("utf-8")
        http_request = request.Request(
            f"{self.host}/api/chat",
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                status = getattr(response, "status", 200)
                response_body = response.read()
        except error.URLError as exc:
            raise RuntimeError(f"Ollama connection failed: {exc}") from exc

        if status < 200 or status >= 300:
            raise RuntimeError(f"Ollama request failed with status {status}")

        try:
            data = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Ollama response was not valid JSON") from exc

        try:
            content = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError("Ollama response missing message content") from exc
        if not isinstance(content, str):
            raise RuntimeError("Ollama response content must be a string")
        return content
