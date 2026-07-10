from __future__ import annotations

from collections.abc import Collection
from urllib.parse import parse_qs

from starlette.requests import Request

_MAX_FORM_BYTES = 16_384
_MAX_FORM_FIELDS = 12


class FormDataError(ValueError):
    pass


async def read_urlencoded_form(
    request: Request,
    *,
    allowed_fields: Collection[str],
) -> dict[str, str]:
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    if content_type != "application/x-www-form-urlencoded":
        raise FormDataError("form content type is unavailable")

    body = await request.body()
    if len(body) > _MAX_FORM_BYTES:
        raise FormDataError("form submission is too large")
    try:
        text = body.decode("utf-8")
        parsed = parse_qs(
            text,
            keep_blank_values=True,
            strict_parsing=False,
            max_num_fields=_MAX_FORM_FIELDS,
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise FormDataError("form submission is malformed") from error

    unexpected = set(parsed) - set(allowed_fields)
    if unexpected:
        raise FormDataError("form contains unsupported fields")
    if any(len(values) != 1 for values in parsed.values()):
        raise FormDataError("form fields must be submitted exactly once")
    return {name: values[0] for name, values in parsed.items()}
