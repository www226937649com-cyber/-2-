import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "app/src/main/java/com/aiguanjia/app/MainActivity.kt"
NATIVE = ROOT / "app/src/main/cpp/dongbake_llama_jni.cpp"


class ModelAutoLoadSourceContractTests(unittest.TestCase):
    def setUp(self):
        self.main = MAIN.read_text(encoding="utf-8")
        self.native = NATIVE.read_text(encoding="utf-8")

    def test_successfully_used_model_is_restored_after_ui_startup(self):
        self.assertIn('preferences.getBoolean("model_auto_load", false)', self.main)
        self.assertIn("window.decorView.postDelayed({", self.main)
        self.assertIn("loadLocalModel(autoTriggered = true)", self.main)
        self.assertIn("model_restore_auto_begin", self.main)

    def test_low_memory_defers_and_auto_failures_do_not_retry_forever(self):
        self.assertIn("if (memoryInfo.lowMemory)", self.main)
        self.assertIn("model_restore_deferred_low_memory", self.main)
        disable = 'if (autoTriggered) preferences.edit().putBoolean("model_auto_load", false).apply()'
        self.assertGreaterEqual(self.main.count(disable), 2)

    def test_last_saved_conversation_is_restored_on_startup(self):
        self.assertIn("val previousConversation = sessions.lastOrNull", self.main)
        self.assertIn("openConversation(previousConversation.id)", self.main)
        self.assertIn("conversation_restore_complete", self.main)
        self.assertIn("conversation_restore_empty", self.main)
        self.assertIn("createNewConversation(showWelcome = false)", self.main)
    def test_kv_cache_help_matches_native_exact_token_prefix_implementation(self):
        self.assertIn("exact_prefix_reused", self.native)
        self.assertIn("prefix_cache_reused_tokens", self.native)
        self.assertNotIn("跨多轮聊天的 KV Cache 复用目前并未实现", self.main)
        self.assertIn("共同前缀至少连续一致 16 个 Token", self.main)
