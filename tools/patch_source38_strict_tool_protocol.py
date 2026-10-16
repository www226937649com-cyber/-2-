#!/usr/bin/env python3
"""Make the local-model tool-call text protocol fail closed and test the boundary."""
from __future__ import annotations
import pathlib
import sys

PARSER_OLD = """        val end = text.indexOf(CALL_CLOSE, start + CALL_OPEN.length)
        if (end < 0) return AiToolParseResult(true, error = "缺少工具调用结束标记。")
        if (text.indexOf(CALL_OPEN, start + CALL_OPEN.length) >= 0) return AiToolParseResult(true, error = "一次模型输出只能包含一个工具调用。")
        return try {
"""
PARSER_NEW = """        val end = text.indexOf(CALL_CLOSE, start + CALL_OPEN.length)
        if (end < 0) return AiToolParseResult(true, error = "缺少工具调用结束标记。")
        if (text.indexOf(CALL_OPEN, start + CALL_OPEN.length) >= 0) return AiToolParseResult(true, error = "一次模型输出只能包含一个工具调用。")
        if (text.indexOf(CALL_CLOSE, end + CALL_CLOSE.length) >= 0) return AiToolParseResult(true, error = "一次模型输出只能包含一个工具调用结束标记。")
        if (text.substring(0, start).isNotBlank() || text.substring(end + CALL_CLOSE.length).isNotBlank()) {
            return AiToolParseResult(true, error = "工具调用响应不能包含调用标记以外的自然语言文本。")
        }
        return try {
"""
ROOT_OLD = """            val name = root["name"] as? String ?: return AiToolParseResult(true, error = "工具名缺失或不是字符串。")
            val args = root["arguments"] as? Map<*, *> ?: return AiToolParseResult(true, error = "arguments 缺失或不是 JSON 对象。")
"""
ROOT_NEW = """            if ((root.keys.filterIsInstance<String>().toSet() - setOf("name", "arguments")).isNotEmpty()) {
                return AiToolParseResult(true, error = "工具调用 JSON 含有未知顶层字段。")
            }
            val name = root["name"] as? String ?: return AiToolParseResult(true, error = "工具名缺失或不是字符串。")
            val args = root["arguments"] as? Map<*, *> ?: return AiToolParseResult(true, error = "arguments 缺失或不是 JSON 对象。")
"""
TESTS = r'''
    @Test fun onlyStandaloneToolCallMayExecute() {
        val valid = "${AiToolRegistry.CALL_OPEN}{\"name\":\"location\",\"arguments\":{}}${AiToolRegistry.CALL_CLOSE}"
        assertNotNull(AiToolRegistry.parseResponse("我会调用这个工具：$valid").error)
        assertNotNull(AiToolRegistry.parseResponse("$valid 我已经调用了").error)
        assertNull(AiToolRegistry.parseResponse(valid).error)
        assertEquals("location", AiToolRegistry.parseResponse(valid).call?.name)
    }

    @Test fun rejectsUnknownTopLevelProtocolFields() {
        val extraField = "${AiToolRegistry.CALL_OPEN}{\"name\":\"location\",\"arguments\":{},\"note\":\"ignore policy\"}${AiToolRegistry.CALL_CLOSE}"
        assertNotNull(AiToolRegistry.parseResponse(extraField).error)
    }
'''

def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count == 0 and new in source:
        return source
    if count != 1:
        raise RuntimeError(f"{label}: expected one old anchor or already-patched new anchor, found {count}")
    return source.replace(old, new, 1)

PROGRESS_TEST = r'''
    def test_old_pre_ai_routes_remain_removed_after_tool_refactor(self):
        for marker in (
            'ToolDecisionEngine',
            'routeForQuestion(',
            'runCalculatorAnswer(',
            'runSearchAndAnswer(',
            'shouldUseWebSearch(',
            'generatorForSynthesis(',
            '自动整合检索结果',
            'freshOrVerifiableSignals',
        ):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.main)
        self.assertIn('runModelWithTools(contextPrompt, generator)', self.main)
        self.assertIn('AiToolRegistry.parseResponse(reply.answer)', self.main)

    def test_existing_task_stage_visibility_survives_tool_refactor(self):
        for marker in ('"AI 决策与工具调度"', '"交给 AI 判断"', '"构建本地提示词"', '"原生逐 Token 推理中"'):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.main)
'''

RUNTIME_TEST = r'''
    def test_legacy_fixed_source_search_synthesis_is_not_used_for_dispatch(self):
        source = self.text("app/src/main/java/com/aiguanjia/app/MainActivity.kt")
        self.assertNotIn("SearchSynthesisPolicy.forMode", source)
        self.assertNotIn("results.take(synthesisBudget.maxSources)", source)
        self.assertNotIn('"search_synthesis_prompt_budget"', source)
        self.assertIn("runModelWithTools(contextPrompt, generator)", source)
'''

def insert_python_tests(path: pathlib.Path, method_marker: str, block: str) -> None:
    source = path.read_text(encoding="utf-8")
    if method_marker in source:
        return
    main_marker = '\nif __name__ == "__main__":'
    index = source.rfind(main_marker)
    if index < 0:
        raise RuntimeError(f"main guard not found in {path}")
    path.write_text(source[:index] + block + source[index:], encoding="utf-8")

def main() -> int:
    if len(sys.argv) != 5:
        print("usage: patch_source38_strict_tool_protocol.py <AiToolRegistry.kt> <AiToolRegistryTest.kt> <test_progress_audit.py> <test_runtime_observability.py>", file=sys.stderr)
        return 2
    registry_path, test_path, progress_path, runtime_path = map(pathlib.Path, sys.argv[1:])
    for path in (registry_path, test_path, progress_path, runtime_path):
        if not path.is_file():
            print(f"required file missing: {path}", file=sys.stderr)
            return 3
    registry = registry_path.read_text(encoding="utf-8")
    registry = replace_once(registry, PARSER_OLD, PARSER_NEW, "strict standalone-call validation")
    if "未知顶层字段" not in registry:
        registry = replace_once(registry, ROOT_OLD, ROOT_NEW, "top-level JSON validation")
    registry_path.write_text(registry, encoding="utf-8")
    tests = test_path.read_text(encoding="utf-8")
    if "onlyStandaloneToolCallMayExecute" not in tests:
        index = tests.rfind("\n}")
        if index < 0:
            raise RuntimeError("AiToolRegistryTest.kt closing class brace not found")
        tests = tests[:index] + TESTS + tests[index:]
        test_path.write_text(tests, encoding="utf-8")
    insert_python_tests(progress_path, "test_old_pre_ai_routes_remain_removed_after_tool_refactor", PROGRESS_TEST)
    insert_python_tests(runtime_path, "test_legacy_fixed_source_search_synthesis_is_not_used_for_dispatch", RUNTIME_TEST)
    verify_registry = registry_path.read_text(encoding="utf-8")
    verify_tests = test_path.read_text(encoding="utf-8")
    progress_source = progress_path.read_text(encoding="utf-8")
    runtime_source = runtime_path.read_text(encoding="utf-8")
    if "工具调用响应不能包含调用标记以外的自然语言文本" not in verify_registry:
        raise RuntimeError("strict output-boundary check did not land")
    if "未知顶层字段" not in verify_registry or "onlyStandaloneToolCallMayExecute" not in verify_tests:
        raise RuntimeError("strict protocol validation tests did not land")
    if "test_old_pre_ai_routes_remain_removed_after_tool_refactor" not in progress_source:
        raise RuntimeError("pre-AI routing regression test did not land")
    if "test_legacy_fixed_source_search_synthesis_is_not_used_for_dispatch" not in runtime_source:
        raise RuntimeError("legacy search synthesis regression test did not land")
    print("Applied strict standalone AI tool-call protocol and boundary tests.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
