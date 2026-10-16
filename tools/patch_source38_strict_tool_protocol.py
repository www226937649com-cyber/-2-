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

EXTRACTOR_TESTS = r'''

    @Test fun extractsExplicitCallsAtTheEndOfReasoningBlocks() {
        val valid = "${AiToolRegistry.CALL_OPEN}{\"name\":\"location\",\"arguments\":{}}${AiToolRegistry.CALL_CLOSE}"
        assertEquals(valid, AiToolRegistry.extractExplicitToolCallBlock("<think>需要当前信息。$valid</think>"))
        assertEquals(valid, AiToolRegistry.extractExplicitToolCallBlock("<think>已完成判断</think>$valid"))
        assertNull(AiToolRegistry.extractExplicitToolCallBlock("这里仅仅引用协议：$valid"))
        assertNull(AiToolRegistry.extractExplicitToolCallBlock("<think>协议示例 $valid 但我还要继续思考</think>"))
        assertNull(AiToolRegistry.extractExplicitToolCallBlock("$valid $valid"))
    }
'''



def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count == 0 and new in source:
        return source
    if count != 1:
        raise RuntimeError(f"{label}: expected one old anchor or already-patched new anchor, found {count}")
    return source.replace(old, new, 1)

EXTRACTOR = r'''
    /**
     * Extracts one explicit tool call even when a reasoning model places it as the
     * final content of a <think> block. Reasoning itself is never a tool decision:
     * execution still requires this exact structured call marker.
     */
    fun extractExplicitToolCallBlock(raw: String): String? {
        val start = raw.indexOf("[[TOOL_CALL")
        if (start < 0 || raw.indexOf(CALL_OPEN) != start) return null
        val end = raw.indexOf(CALL_CLOSE, start + CALL_OPEN.length)
        if (end < 0 || raw.indexOf("[[/TOOL_CALL") != end) return null
        if (raw.indexOf("[[TOOL_CALL", start + CALL_OPEN.length) >= 0) return null
        if (raw.indexOf("[[/TOOL_CALL", end + CALL_CLOSE.length) >= 0) return null
        val thinkPattern = Regex("(?is)<think>(.*?)(?:</think>|$)")
        val visibleBefore = thinkPattern.replace(raw.substring(0, start), "").replace("</think>", "").trim()
        val visibleAfter = thinkPattern.replace(raw.substring(end + CALL_CLOSE.length), "").replace("</think>", "").trim()
        if (visibleBefore.isNotEmpty() || visibleAfter.isNotEmpty()) return null
        return raw.substring(start, end + CALL_CLOSE.length)
    }

'''

OLD_PARSE_MODEL_REPLY = r'''    private fun parseModelReply(raw: String): ModelReply {
        // Keep only the local model's explicitly tagged think block as an optional collapsed record.
        // The reasoning is never injected back into conversation context or used as factual evidence.
        val thoughtPattern = Regex("(?is)<think>(.*?)(?:</think>|$)")
        val reasoning = thoughtPattern.findAll(raw).map { it.groupValues[1].trim() }
            .filter { it.isNotBlank() }.joinToString("\n\n").take(4000)
        val strippedThink = thoughtPattern.replace(raw, "")
        val answer = strippedThink.replace(Regex("(?m)^\\s*(assistant|助手|AI管家)\\s*[:：]\\s*"), "").trim()
        return ModelReply(answer.ifBlank { "模型这次没有生成明确答案，请换个问法再试试。" }, reasoning)
    }
'''

NEW_PARSE_MODEL_REPLY = r'''    private fun parseModelReply(raw: String): ModelReply {
        // A reasoning model may put the explicit tool call at the end of <think>.
        // Preserve only a canonical standalone call for the dispatcher; never execute
        // a quoted call surrounded by visible prose.
        val thoughtPattern = Regex("(?is)<think>(.*?)(?:</think>|$)")
        val extractedToolCall = AiToolRegistry.extractExplicitToolCallBlock(raw)
        val reasoning = thoughtPattern.findAll(raw).map { match ->
            val block = match.groupValues[1]
            (if (extractedToolCall != null) block.replace(extractedToolCall, "") else block).trim()
        }.filter { it.isNotBlank() }.joinToString("\n\n").take(4000)
        if (extractedToolCall != null) return ModelReply(extractedToolCall, reasoning)

        val strippedThink = thoughtPattern.replace(raw, "")
        // Keep invalid protocol markers visible to parseResponse so it can return a
        // protocol error to the model instead of turning a malformed call into an empty answer.
        if (raw.contains("[[TOOL_CALL") || raw.contains("[[/TOOL_CALL")) {
            val candidate = strippedThink.trim().ifBlank { raw.trim() }
            return ModelReply(candidate, reasoning)
        }
        val answer = strippedThink.replace(Regex("(?m)^\\s*(assistant|助手|AI管家)\\s*[:：]\\s*"), "").trim()
        return ModelReply(answer.ifBlank { "模型这次没有生成明确答案，请换个问法再试试。" }, reasoning)
    }
'''

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
    if len(sys.argv) != 6:
        print("usage: patch_source38_strict_tool_protocol.py <AiToolRegistry.kt> <AiToolRegistryTest.kt> <test_progress_audit.py> <test_runtime_observability.py> <MainActivity.kt>", file=sys.stderr)
        return 2
    registry_path, test_path, progress_path, runtime_path, main_activity_path = map(pathlib.Path, sys.argv[1:])
    for path in (registry_path, test_path, progress_path, runtime_path, main_activity_path):
        if not path.is_file():
            print(f"required file missing: {path}", file=sys.stderr)
            return 3
    registry = registry_path.read_text(encoding="utf-8")
    registry = replace_once(registry, PARSER_OLD, PARSER_NEW, "strict standalone-call validation")
    if "未知顶层字段" not in registry:
        registry = replace_once(registry, ROOT_OLD, ROOT_NEW, "top-level JSON validation")
    if "fun extractExplicitToolCallBlock(raw: String): String?" not in registry:
        anchor = "    fun parseResponse(text: String): AiToolParseResult {"
        if registry.count(anchor) != 1:
            raise RuntimeError("AiToolRegistry parseResponse insertion anchor is not unique")
        registry = registry.replace(anchor, EXTRACTOR + anchor, 1)
    registry_path.write_text(registry, encoding="utf-8")
    tests = test_path.read_text(encoding="utf-8")
    if "onlyStandaloneToolCallMayExecute" not in tests:
        index = tests.rfind("\n}")
        if index < 0:
            raise RuntimeError("AiToolRegistryTest.kt closing class brace not found")
        tests = tests[:index] + TESTS + tests[index:]
    if "extractsExplicitCallsAtTheEndOfReasoningBlocks" not in tests:
        index = tests.rfind("\n}")
        if index < 0:
            raise RuntimeError("AiToolRegistryTest.kt closing class brace not found")
        tests = tests[:index] + EXTRACTOR_TESTS + tests[index:]
    test_path.write_text(tests, encoding="utf-8")
    main_source = main_activity_path.read_text(encoding="utf-8")
    if "AiToolRegistry.extractExplicitToolCallBlock(raw)" not in main_source:
        method_start = main_source.find("    private fun parseModelReply(raw: String): ModelReply {")
        if method_start < 0:
            raise RuntimeError("parseModelReply method start not found in MainActivity.kt")
        next_method = main_source.find("\n    private fun ", method_start + 1)
        if next_method < 0:
            raise RuntimeError("parseModelReply next method boundary not found in MainActivity.kt")
        current_method = main_source[method_start:next_method]
        if "thoughtPattern" not in current_method or "ModelReply(" not in current_method:
            raise RuntimeError("parseModelReply structure differs from expected safe patch target")
        main_source = main_source[:method_start] + NEW_PARSE_MODEL_REPLY.rstrip() + main_source[next_method:]
        main_activity_path.write_text(main_source, encoding="utf-8")
    insert_python_tests(progress_path, "test_old_pre_ai_routes_remain_removed_after_tool_refactor", PROGRESS_TEST)
    insert_python_tests(runtime_path, "test_legacy_fixed_source_search_synthesis_is_not_used_for_dispatch", RUNTIME_TEST)
    verify_registry = registry_path.read_text(encoding="utf-8")
    verify_tests = test_path.read_text(encoding="utf-8")
    progress_source = progress_path.read_text(encoding="utf-8")
    runtime_source = runtime_path.read_text(encoding="utf-8")
    if "工具调用响应不能包含调用标记以外的自然语言文本" not in verify_registry:
        raise RuntimeError("strict output-boundary check did not land")
    if "fun extractExplicitToolCallBlock(raw: String): String?" not in verify_registry or "extractsExplicitCallsAtTheEndOfReasoningBlocks" not in verify_tests:
        raise RuntimeError("think-tag tool-call compatibility tests did not land")
    if "AiToolRegistry.extractExplicitToolCallBlock(raw)" not in main_source:
        raise RuntimeError("MainActivity does not preserve explicit tool call markers from reasoning-model output")
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
