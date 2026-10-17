#!/usr/bin/env python3
"""Apply Source40 model lifecycle corrections to a freshly reconstructed source tree."""
from pathlib import Path
import re
import shutil
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one source match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: apply_source40_lifecycle.py <buildsrc-root> <source-test-file>")
    root = Path(sys.argv[1]).resolve()
    test_source = Path(sys.argv[2]).resolve()
    main_path = root / "app/src/main/java/com/aiguanjia/app/MainActivity.kt"
    source = main_path.read_text(encoding="utf-8")

    old_start = """        initialiseSpeech()
        if (modelFile.exists() && modelFile.length() > 0L) {
            statusText.text = "发现本地模型「${modelDisplayName(modelFile)}」（${formatBytes(modelFile.length())}）。为避免启动时大模型自动加载导致闪退，请确认内存状态后手动点击“加载模型”。"
            AppDiagnostics.log(this, "INFO", "model_restore_deferred", "file=${modelFile.name}; bytes=${modelFile.length()}; auto reload disabled.")
        } else {
            statusText.text = "尚未加载模型：请先选择并加载一个 GGUF 文件，再发送消息。"
            AppDiagnostics.log(this, "INFO", "startup_no_model", "No selected model file.")
        }
"""
    new_start = """        initialiseSpeech()
        if (modelFile.exists() && modelFile.length() > 0L) {
            if (preferences.getBoolean("model_auto_load", false)) {
                val restoreName = modelFile.name
                statusText.text = "已找到上次使用的模型「${modelDisplayName(modelFile)}」（${formatBytes(modelFile.length())}），正在准备自动恢复。"
                AppDiagnostics.log(this, "INFO", "model_restore_scheduled", "file=$restoreName; delayMs=1200; lowMemoryGate=true")
                window.decorView.postDelayed({
                    if (isFinishing || isDestroyed) return@postDelayed
                    val selectedFile = modelFile
                    if (!selectedFile.isFile || selectedFile.length() <= 0L || selectedFile.name != restoreName) {
                        statusText.text = "自动恢复已取消：所选模型已变化或文件不可用，请手动检查模型。"
                        AppDiagnostics.log(this, "WARN", "model_restore_cancelled", "reason=selected_model_changed_or_missing; startupFile=$restoreName")
                        return@postDelayed
                    }
                    val manager = getSystemService(ACTIVITY_SERVICE) as? ActivityManager
                    val memoryInfo = ActivityManager.MemoryInfo()
                    runCatching { manager?.getMemoryInfo(memoryInfo) }
                    if (memoryInfo.lowMemory) {
                        statusText.text = "已保存上次模型，但系统当前提示低内存；为避免启动闪退，暂不自动恢复。释放内存后可以手动点击“加载模型”。"
                        AppDiagnostics.log(this, "WARN", "model_restore_deferred_low_memory", "file=$restoreName; availableBytes=${memoryInfo.availMem}; totalBytes=${memoryInfo.totalMem}")
                        return@postDelayed
                    }
                    AppDiagnostics.log(this, "INFO", "model_restore_auto_begin", "file=$restoreName; bytes=${selectedFile.length()}; availableBytes=${memoryInfo.availMem}; lowMemory=false")
                    loadLocalModel(autoTriggered = true)
                }, 1200L)
            } else {
                statusText.text = "发现本地模型「${modelDisplayName(modelFile)}」（${formatBytes(modelFile.length())}），这是首次加载或尚未启用自动恢复，请点击“加载模型”。"
                AppDiagnostics.log(this, "INFO", "model_restore_manual_first_load", "file=${modelFile.name}; autoLoadPreference=false")
            }
        } else {
            statusText.text = "尚未加载模型：请先选择并加载一个 GGUF 文件，再发送消息。"
            AppDiagnostics.log(this, "INFO", "startup_no_model", "No selected model file.")
        }
"""
    source = replace_once(source, old_start, new_start, "startup auto-restore")

    # Loading the serialized session list is not enough: the old startup path
    # immediately created a blank conversation and left the transcript/history empty.
    old_session_start = """        loadSavedSessions()
        createNewConversation(showWelcome = false)
"""
    new_session_start = """        loadSavedSessions()
        val previousConversation = sessions.lastOrNull { session -> session.messages.any { it.isUser } }
        if (previousConversation != null) {
            AppDiagnostics.log(this, "INFO", "conversation_restore_begin", "sessionId=${previousConversation.id}; messages=${previousConversation.messages.size}")
            openConversation(previousConversation.id)
            AppDiagnostics.log(this, "INFO", "conversation_restore_complete", "sessionId=${previousConversation.id}; transcriptMessages=${transcript.size}; historyPairs=${history.size}")
        } else {
            createNewConversation(showWelcome = false)
            AppDiagnostics.log(this, "INFO", "conversation_restore_empty", "no_saved_user_conversation=true; createdFreshConversation=true")
        }
"""
    source = replace_once(source, old_session_start, new_session_start, "startup conversation restore")

    old_cache = """        addExpandableCard(
            "② KV Cache：缓存状态与复用边界",
            "本轮生成使用上下文缓存；跨多轮聊天的 KV Cache 复用目前并未实现，不会显示为已开启。",
            "重要核对：当前原生生成路径会为一次回答创建 llama.cpp context，并在该次生成结束后释放它。因此 KV Cache 可在单轮预填充/生成期间使用，但下一条消息不会直接接续上一轮的 KV 状态；应用会根据新的提示词重新构建上下文。元宝所说“第二轮只算新句子”的跨轮复用，在这份源码中不成立。真正加入跨轮复用需要处理消息分支、编辑/删除历史、取消生成、模板变化与 KV 回滚，不能仅放一个开关就声称完成。"
        )
"""
    new_cache = """        addExpandableCard(
            "② KV Cache：缓存状态与复用边界",
            "跨轮 KV 前缀复用已在原生层实现，并保留于当前进程内；是否命中取决于两轮提示词的真实 Token 前缀是否足够相同。",
            "原生层会保留同一模型句柄的 llama_context，并用 Token ID 逐个比较新旧提示词的共同前缀；仅当共同前缀至少连续一致 16 个 Token，且 llama.cpp 能安全裁剪后缀时，才会跳过这部分 Prefill。真实命中以 prefix_cache_hit、prefix_cache_reused_tokens、prefill_processed_tokens 和 prefix_cache_reason 原生指标为准。缓存只驻留当前进程内存；内存压力、模型/上下文重载、推理错误或进程结束会释放或重建缓存，不会写入聊天历史文件。F16/Q8_0 是缓存精度选项，不等同于跨轮缓存是否命中。"
        )
"""
    source = replace_once(source, old_cache, new_cache, "KV cache explanation")

    old_oom = """            } catch (e: OutOfMemoryError) {
                AppDiagnostics.logThrowable(this@MainActivity, "FATAL", "model_load_out_of_memory", "file=${modelFile.name}; bytes=$loadFileSize; ${AppDiagnostics.memorySnapshot(this@MainActivity)}", e)
"""
    new_oom = """            } catch (e: OutOfMemoryError) {
                if (autoTriggered) preferences.edit().putBoolean("model_auto_load", false).apply()
                if (autoTriggered) AppDiagnostics.log(this@MainActivity, "WARN", "model_auto_load_disabled_after_failure", "autoTriggered=true; failure=OutOfMemoryError; manualRetryRequired=true")
                AppDiagnostics.logThrowable(this@MainActivity, "FATAL", "model_load_out_of_memory", "file=${modelFile.name}; bytes=$loadFileSize; ${AppDiagnostics.memorySnapshot(this@MainActivity)}", e)
"""
    source = replace_once(source, old_oom, new_oom, "out-of-memory auto-load recovery")

    old_exception = """            } catch (e: Exception) {
                AppDiagnostics.logThrowable(this@MainActivity, "ERROR", "model_load_exception", "file=${modelFile.name}; bytes=$loadFileSize; ${AppDiagnostics.memorySnapshot(this@MainActivity)}; nativeLog=${NativeLlamaEngine.lastNativeLogTail().takeLast(6000)}", e)
"""
    new_exception = """            } catch (e: Exception) {
                if (autoTriggered) preferences.edit().putBoolean("model_auto_load", false).apply()
                if (autoTriggered) AppDiagnostics.log(this@MainActivity, "WARN", "model_auto_load_disabled_after_failure", "autoTriggered=true; failure=Exception; manualRetryRequired=true")
                AppDiagnostics.logThrowable(this@MainActivity, "ERROR", "model_load_exception", "file=${modelFile.name}; bytes=$loadFileSize; ${AppDiagnostics.memorySnapshot(this@MainActivity)}; nativeLog=${NativeLlamaEngine.lastNativeLogTail().takeLast(6000)}", e)
"""
    source = replace_once(source, old_exception, new_exception, "exception auto-load recovery")

    main_path.write_text(source, encoding="utf-8")

    # The Source39 test suite had an assertion that encoded the old, incorrect cache explanation.
    # Keep the regression test's intent while asserting the real native prefix-cache contract.
    performance_test_path = root / "tests/test_performance_management.py"
    if not performance_test_path.is_file():
        raise SystemExit("performance management regression test is missing")
    performance_test = performance_test_path.read_text(encoding="utf-8")
    stale_method = re.compile(
        r"(?ms)^    def test_cross_turn_kv_reuse_is_not_falsely_reported\(self\):\n.*?(?=^    def [A-Za-z_]\w*\(|^class [A-Za-z_]\w*|\Z)"
    )
    corrected_method = '''    def test_cross_turn_kv_reuse_is_not_falsely_reported(self):
        from pathlib import Path
        source_root = Path(__file__).resolve().parents[1]
        main_source = (source_root / "app/src/main/java/com/aiguanjia/app/MainActivity.kt").read_text(encoding="utf-8")
        native_source = (source_root / "app/src/main/cpp/dongbake_llama_jni.cpp").read_text(encoding="utf-8")
        self.assertIn("跨轮 KV 前缀复用已在原生层实现", main_source)
        self.assertIn("共同前缀至少连续一致 16 个 Token", main_source)
        self.assertIn("prefix_cache_reused_tokens", main_source)
        self.assertIn("exact_prefix_reused", native_source)
        self.assertIn("contextPersistent", native_source)
        self.assertNotIn("跨多轮聊天的 KV Cache 复用目前并未实现", main_source)
'''
    performance_test, rewritten = stale_method.subn(corrected_method, performance_test, count=1)
    if rewritten != 1:
        raise SystemExit(f"stale KV-cache regression assertion: expected exactly one method, rewrote {rewritten}")
    performance_test_path.write_text(performance_test, encoding="utf-8")

    tests_dir = root / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(test_source, tests_dir / test_source.name)
    print("Applied delayed, memory-aware auto-restore; disabled automatic retries after failures; corrected KV-cache guidance; copied source contract tests.")


if __name__ == "__main__":
    main()
