#!/usr/bin/env python3
"""Apply a narrow, repeatable Kotlin compile repair to the source-38 work tree.

The helper only classifies short conversational turns for response-length policy.
It never dispatches or executes any AI tool.
"""
from __future__ import annotations

import pathlib
import sys

HELPER = r'''
    /**
     * Classifies short social/conversational turns for response-style budgeting only.
     * This function MUST NOT select, execute, or dispatch tools.
     */
    private fun isCasualMessage(question: String): Boolean {
        val q = question.trim()
            .trimEnd('。', '！', '？', '!', '?', '…', '.', ',', '，')
            .lowercase()
        if (q.isBlank() || q.length > 40) return false

        val exact = setOf(
            "你好", "您好", "嗨", "哈喽", "嘿", "hello", "hi", "hey",
            "在吗", "谢谢", "感谢", "好的", "好吧", "好", "嗯", "嗯嗯", "哦", "噢",
            "啊", "是的", "没错", "对", "行", "可以", "收到", "明白了",
            "晚安", "早安", "早上好", "晚上好", "再见", "拜拜", "辛苦了",
            "我回来了", "继续聊聊", "哈哈", "呵呵", "笑死", "笑死了", "真的吗"
        )
        if (q in exact) return true

        return Regex(
            "^(你好|您好|嗨+|哈喽+|嘿+|hello+|hi+|hey+|在吗|谢谢|感谢|好的|好吧|嗯+|哦+|噢+|啊+|哈哈+|呵呵+|再见|拜拜|晚安|早安|早上好|晚上好|笑死了?)[呀啊哦呢嘛吧哇～~！!，,。 ]*$",
            RegexOption.IGNORE_CASE
        ).matches(q)
    }

'''

def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_source38_casual_classifier.py <MainActivity.kt>", file=sys.stderr)
        return 2
    path = pathlib.Path(sys.argv[1])
    if not path.is_file():
        print(f"source file not found: {path}", file=sys.stderr)
        return 3
    source = path.read_text(encoding="utf-8")
    if "private fun isCasualMessage(question: String)" in source:
        print("isCasualMessage already exists; no change needed")
        return 0
    marker = "    private fun classifyQuestion(question: String): ResponseEffort {"
    count = source.count(marker)
    if count != 1:
        print(f"expected exactly one classifyQuestion anchor, found {count}", file=sys.stderr)
        return 4
    path.write_text(source.replace(marker, HELPER + marker, 1), encoding="utf-8")
    check = path.read_text(encoding="utf-8")
    if check.count("private fun isCasualMessage(question: String)") != 1:
        print("failed to verify inserted helper", file=sys.stderr)
        return 5
    print(f"inserted response-style-only isCasualMessage helper into {path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
