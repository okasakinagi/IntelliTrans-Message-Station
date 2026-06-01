"""workflow_service 模块的单元测试。

测试 _normalize_result、_find_value 等核心解析逻辑，无需外部依赖。
"""

from app.services.workflow_service import (
    _coerce_bool,
    _extract_text,
    _find_value,
    _normalize_result,
    _to_string_list,
    _try_parse_json_string,
)


class TestFindValue:
    """_find_value 深度搜索测试。"""

    def test_find_top_level_key(self):
        data = {"is_safe": True, "translated_text": "Hello"}
        assert _find_value(data, ["is_safe"]) is True
        # 多个别名候选：第一个匹配的键获胜
        assert _find_value(data, ["is_safe", "safe"]) is True
        assert _find_value(data, ["safe"]) is None  # "safe" ≠ "is_safe"，精确匹配
        assert _find_value(data, ["translated_text"]) == "Hello"

    def test_find_nested_key(self):
        data = {"output": {"result": {"safe": False}}}
        assert _find_value(data, ["safe"]) is False

    def test_find_in_list(self):
        data = {"results": [{"lang": "en"}, {"lang": "zh"}]}
        assert _find_value(data, ["lang"]) == "en"  # first match

    def test_find_returns_none_for_missing(self):
        assert _find_value({}, ["nonexistent"]) is None
        assert _find_value({"a": 1}, ["b"]) is None

    def test_find_json_string_value(self):
        data = {"output": '{"is_safe": false, "reason": "bad word"}'}
        assert _find_value(data, ["is_safe"]) is False
        assert _find_value(data, ["reason"]) == "bad word"


class TestTryParseJsonString:
    """_try_parse_json_string 测试。"""

    def test_parse_valid_json_object(self):
        result = _try_parse_json_string('{"a": 1}')
        assert result == {"a": 1}

    def test_parse_valid_json_array(self):
        result = _try_parse_json_string('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_ignore_non_json_strings(self):
        assert _try_parse_json_string("hello") is None
        assert _try_parse_json_string("") is None
        assert _try_parse_json_string("   ") is None

    def test_ignore_non_string_types(self):
        assert _try_parse_json_string(123) is None
        assert _try_parse_json_string(None) is None
        assert _try_parse_json_string({"already": "dict"}) is None


class TestCoerceBool:
    """_coerce_bool 类型转换测试。"""

    def test_bool_values(self):
        assert _coerce_bool(True, default=False) is True
        assert _coerce_bool(False, default=True) is False

    def test_int_values(self):
        assert _coerce_bool(1, default=False) is True
        assert _coerce_bool(0, default=True) is False
        assert _coerce_bool(-1, default=False) is True

    def test_string_values(self):
        assert _coerce_bool("true", default=False) is True
        assert _coerce_bool("TRUE", default=False) is True
        assert _coerce_bool("false", default=True) is False
        assert _coerce_bool("1", default=False) is True
        assert _coerce_bool("yes", default=False) is True
        assert _coerce_bool("no", default=True) is False

    def test_none_returns_default(self):
        assert _coerce_bool(None, default=True) is True
        assert _coerce_bool(None, default=False) is False

    def test_unknown_returns_default(self):
        assert _coerce_bool("unknown", default=True) is True
        assert _coerce_bool([], default=False) is False


class TestExtractText:
    """_extract_text 测试。"""

    def test_string(self):
        assert _extract_text("hello") == "hello"

    def test_none(self):
        assert _extract_text(None) == ""

    def test_dict_with_text_key(self):
        assert _extract_text({"text": "hi"}) == "hi"
        assert _extract_text({"content": "hello"}) == "hello"
        assert _extract_text({"message": "hey"}) == "hey"

    def test_fallback_to_str(self):
        assert _extract_text(123) == "123"


class TestToStringList:
    """_to_string_list 测试。"""

    def test_none(self):
        assert _to_string_list(None) == []

    def test_string_splits_lines(self):
        result = _to_string_list("hello\nworld\n")
        assert result == ["hello", "world"]

    def test_list_of_strings(self):
        assert _to_string_list(["a", "b"]) == ["a", "b"]

    def test_list_of_objects(self):
        assert _to_string_list([{"text": "hi"}, {"content": "hey"}]) == ["hi", "hey"]

    def test_single_item(self):
        assert _to_string_list("hello") == ["hello"]


class TestNormalizeResult:
    """_normalize_result 完整流程测试。"""

    def test_safe_message_with_translation(self):
        raw = {
            "is_safe": True,
            "need_translate": True,
            "translated_text": "你好",
            "detected_language": "en",
            "suggested_replies": ["谢谢", "不客气"],
            "trace_id": "abc123",
        }
        result = _normalize_result(raw, "Hello", is_translation_requested=False)
        assert result["is_safe"] is True
        assert result["need_translate"] is True
        assert result["translated_text"] == "你好"
        assert result["detected_language"] == "en"
        assert result["suggested_replies"] == ["谢谢", "不客气"]
        assert result["trace_id"] == "abc123"

    def test_unsafe_message(self):
        raw = {
            "safe": False,
            "safety_reason": "包含违规内容",
        }
        result = _normalize_result(raw, "bad words", is_translation_requested=False)
        assert result["is_safe"] is False
        assert result["unsafe_reason"] == "包含违规内容"

    def test_alias_fields(self):
        """测试各种别名字段的兼容性。"""
        raw = {"is_valid": True, "requires_translation": True, "target_text": "Hola"}
        result = _normalize_result(raw, "Hola", is_translation_requested=False)
        assert result["is_safe"] is True
        assert result["need_translate"] is True
        assert result["translated_text"] == "Hola"

    def test_translation_requested_mode(self):
        """手动翻译模式不应返回推荐回复。"""
        raw = {
            "is_safe": True,
            "translated_text": "Hello",
            "suggested_replies": ["Yes", "No"],
        }
        result = _normalize_result(raw, "你好", is_translation_requested=True)
        assert result["suggested_replies"] == []
        assert result["translated_text"] == "Hello"

    def test_defaults_when_empty(self):
        result = _normalize_result({}, "test", is_translation_requested=False)
        assert result["is_safe"] is True
        assert result["need_translate"] is False
        assert result["translated_text"] == ""
        assert result["suggested_replies"] == []
        assert result["trace_id"] == ""
