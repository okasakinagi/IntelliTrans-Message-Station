import json
import logging
from collections.abc import Iterable
from typing import Any

import requests
from flask import current_app

logger = logging.getLogger(__name__)


class WorkflowServiceError(RuntimeError):
    """外部工作流调用失败时抛出的统一异常。"""


def process_new_message(
    *,
    new_message: str,
    chat_history: list[dict],
    user_language: str = "",
) -> dict[str, Any]:
    """处理新消息自动流程：安全检查 + 语言判断 + 可选翻译 + 推荐回复。"""
    try:
        result = _invoke_workflow(
            new_message=new_message,
            chat_history=chat_history,
            is_translation_requested=False,
            target_language="",
            user_language=user_language,
        )
        return _normalize_result(result, new_message, is_translation_requested=False)
    except Exception as exc:  # pragma: no cover - demo 以可用性优先
        if current_app.config["WORKFLOW_FAIL_OPEN"]:
            logger.warning("工作流调用失败，按 fail-open 放行消息: %s", exc)
            return {
                "is_safe": True,
                "unsafe_reason": "",
                "need_translate": False,
                "translated_text": "",
                "detected_language": "",
                "suggested_replies": [],
                "trace_id": "",
                "workflow_error": str(exc),
            }
        raise WorkflowServiceError(str(exc)) from exc


def request_manual_translation(
    *,
    new_message: str,
    target_language: str,
    user_language: str = "",
) -> dict[str, Any]:
    """处理手动翻译：仅返回翻译结果，不生成推荐回复。"""
    if not target_language.strip():
        raise WorkflowServiceError("target_language 不能为空")

    result = _invoke_workflow(
        new_message=new_message,
        # 手动翻译场景通常只依赖当前消息，避免额外上下文成本。
        chat_history=[],
        is_translation_requested=True,
        target_language=target_language.strip(),
        user_language=user_language,
    )
    normalized = _normalize_result(result, new_message, is_translation_requested=True)
    return normalized


def _invoke_workflow(
    *,
    new_message: str,
    chat_history: list[dict],
    is_translation_requested: bool,
    target_language: str,
    user_language: str,
) -> dict[str, Any]:
    if not current_app.config["WORKFLOW_ENABLED"]:
        return {
            "is_safe": True,
            "need_translate": False,
            "translated_text": "",
            "suggested_replies": [],
            "detected_language": "",
            "trace_id": "",
        }

    api_url = current_app.config["WORKFLOW_API_URL"]
    api_token = current_app.config["WORKFLOW_API_TOKEN"]
    timeout = current_app.config["WORKFLOW_TIMEOUT_SECONDS"]

    if not api_url:
        raise WorkflowServiceError("缺少 WORKFLOW_API_URL")
    if not api_token:
        raise WorkflowServiceError("缺少 WORKFLOW_API_TOKEN")

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "new_message": new_message,
        "chat_history": chat_history,
        "is_translation_requested": is_translation_requested,
        "target_language": target_language,
        "user_language": user_language,
    }

    logger.warning(
        "调用工作流: url=%s, is_translation_requested=%s, history_count=%s",
        api_url,
        is_translation_requested,
        len(chat_history),
    )

    response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
    if response.status_code < 200 or response.status_code >= 300:
        raise WorkflowServiceError(
            f"工作流 HTTP 错误: {response.status_code} - {response.text[:300]}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise WorkflowServiceError("工作流响应不是有效 JSON") from exc

    if isinstance(body, dict):
        return body
    raise WorkflowServiceError("工作流响应 JSON 顶层必须是对象")


def _normalize_result(raw: dict[str, Any], original_message: str, *, is_translation_requested: bool) -> dict[str, Any]:
    is_safe = _coerce_bool(_find_value(raw, ["is_safe", "safe", "is_valid", "security_passed"]), default=True)
    unsafe_reason = str(
        _find_value(raw, ["unsafe_reason", "safety_reason", "invalid_reason", "block_reason", "reason"]) or ""
    )
    need_translate = _coerce_bool(
        _find_value(
            raw,
            ["need_translate", "needs_translation", "requires_translation", "should_translate", "translation_needed"],
        ),
        default=False,
    )
    detected_language = str(
        _find_value(raw, ["detected_language", "source_language", "language", "lang"]) or ""
    )
    translated_text = _extract_text(
        _find_value(raw, ["translated_text", "translation_result", "translation", "translated_message", "target_text"])
    )
    trace_id = str(_find_value(raw, ["trace_id", "request_id", "id"]) or "")

    suggestions = _to_string_list(
        _find_value(raw, ["suggested_replies", "recommended_replies", "reply_suggestions", "suggestions"])
    )

    if is_translation_requested:
        # 手动翻译不返回推荐回复，遵循工作流约定。
        suggestions = []
        if is_safe and not need_translate and not translated_text:
            translated_text = original_message

    return {
        "is_safe": is_safe,
        "unsafe_reason": unsafe_reason,
        "need_translate": need_translate,
        "translated_text": translated_text,
        "detected_language": detected_language,
        "suggested_replies": suggestions,
        "trace_id": trace_id,
        "raw": raw,
    }


def _find_value(data: Any, keys: list[str]) -> Any:
    key_set = {k.lower() for k in keys}

    def _walk(node: Any) -> Any:
        if isinstance(node, dict):
            for k, v in node.items():
                if str(k).lower() in key_set and v not in (None, ""):
                    return v
            # 有些工作流会把真正结果包在 output/result/data 文本里。
            for v in node.values():
                parsed = _try_parse_json_string(v)
                if parsed is not None:
                    found = _walk(parsed)
                    if found not in (None, ""):
                        return found
            for v in node.values():
                found = _walk(v)
                if found not in (None, ""):
                    return found
        elif isinstance(node, list):
            for item in node:
                found = _walk(item)
                if found not in (None, ""):
                    return found
        return None

    return _walk(data)


def _try_parse_json_string(value: Any) -> Any | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text[0] not in "[{":
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off"}:
            return False
    return default


def _extract_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("text", "content", "message", "value"):
            if key in value and isinstance(value[key], str):
                return value[key].strip()
    return str(value).strip()


def _to_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        # 兼容返回单字符串时，按换行拆分建议。
        return [item.strip() for item in value.split("\n") if item.strip()]
    if isinstance(value, Iterable) and not isinstance(value, (dict, bytes, bytearray)):
        result: list[str] = []
        for item in value:
            text = _extract_text(item)
            if text:
                result.append(text)
        return result
    text = _extract_text(value)
    return [text] if text else []
