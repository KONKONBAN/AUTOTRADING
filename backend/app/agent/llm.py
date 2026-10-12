"""Kết nối Claude API (Anthropic SDK) dùng chung cho AI Agent và các tác vụ đọc ảnh/PDF."""

from __future__ import annotations

import base64
from typing import Any

import anthropic

from ..config import settings

FALLBACK_BETA = "server-side-fallback-2026-07-01"
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
PDF_TYPE = "application/pdf"
MAX_FILE_BYTES = 20 * 1024 * 1024


class AIUnavailable(RuntimeError):
    """Chưa cấu hình Claude API key."""


class AIRefusal(RuntimeError):
    pass


_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if not settings.has_anthropic_credentials:
        raise AIUnavailable("Chưa cấu hình ANTHROPIC_API_KEY trong file .env - tính năng AI đang tắt.")
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def common_params() -> dict[str, Any]:
    """Tham số chung: model, mức nỗ lực suy luận, và cơ chế fallback phía máy chủ khi model từ chối."""
    return {
        "model": settings.agent_model,
        "output_config": {"effort": settings.agent_effort},
        "betas": [FALLBACK_BETA],
        "fallbacks": "default",
    }


def file_block(data: bytes, media_type: str) -> dict:
    """Tạo content block cho ảnh (PNG/JPG/WEBP/GIF) hoặc PDF."""
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("File quá lớn (tối đa 20MB)")
    b64 = base64.standard_b64encode(data).decode("utf-8")
    if media_type in IMAGE_TYPES:
        return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}
    if media_type == PDF_TYPE:
        return {"type": "document", "source": {"type": "base64", "media_type": PDF_TYPE, "data": b64}}
    raise ValueError(f"Định dạng {media_type} chưa được hỗ trợ (dùng PNG, JPG, WEBP, GIF hoặc PDF)")


def check_stop(response) -> None:
    if response.stop_reason == "refusal":
        detail = getattr(response, "stop_details", None)
        raise AIRefusal(f"AI từ chối xử lý yêu cầu ({getattr(detail, 'category', None) or 'không rõ'}).")


def parse(system: str, content: list[dict], output_format, max_tokens: int = 16000):
    """Gọi Claude với structured output (Pydantic) - trả về đối tượng đã kiểm tra hợp lệ."""
    client = get_client()
    response = client.beta.messages.parse(
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
        output_format=output_format,
        **common_params(),
    )
    check_stop(response)
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise RuntimeError("Phản hồi của AI bị cắt ngắn hoặc không hợp lệ, vui lòng thử lại với ít trang/ảnh hơn.")
    return response.parsed_output
