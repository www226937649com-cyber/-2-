#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else "buildsrc")
app = root / "app/src/main/java/com/aiguanjia/app"
main_file = app / "MainActivity.kt"
native_file = app / "NativeLlamaEngine.kt"
gradle_file = root / "app/build.gradle.kts"

def replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise SystemExit(f"{label}: expected one match, got {text.count(old)}")
    return text.replace(old, new, 1)

logger = r'''package com.aiguanjia.app

import android.app.ActivityManager
import android.content.Context
import android.os.Build
import android.os.Process
import java.io.File
import java.io.FileOutputStream
import java.io.PrintWriter
import java.io.StringWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.system.exitProcess

/** 本地诊断日志；不会记录聊天正文。 */
object AppDiagnostics {
    private const val LOG = "dongbake-runtime.log"
    private const val OLD_LOG = "dongbake-runtime.1.log"
    private const val MARKER = "dongbake-active-operation.txt"
    private const val MAX_BYTES = 512L * 1024L
    private val lock = Any()
    @Volatile private var handlerInstalled = false

    fun initialize(context: Context) {
        val app = context.applicationContext
        synchronized(lock) {
            val marker = File(app.filesDir, MARKER)
            if (marker.isFile) {
                val unfinished = runCatching { marker.readText(Charsets.UTF_8) }.getOrDefault("unknown")
                writeLocked(app, "FATAL", "previous_run", "上次进程疑似异常退出；最后未完成操作：" + oneLine(unfinished))
                runCatching { marker.delete() }
            }
            writeLocked(app, "INFO", "startup",
                "启动 Android=${Build.VERSION.RELEASE}/API${Build.VERSION.SDK_INT}; device=${Build.MANUFACTURER} ${Build.MODEL}; " +
                "ABI=${Build.SUPPORTED_ABIS.joinToString(",")}; version=${version(app)}; ${memorySnapshot(app)}")
            if (!handlerInstalled) {
                val previous = Thread.getDefaultUncaughtExceptionHandler()
                Thread.setDefaultUncaughtExceptionHandler { thread, error ->
                    runCatching { logThrowable(app, "FATAL", "uncaught_exception", "thread=${thread.name}", error) }
                    if (previous != null) previous.uncaughtException(thread, error)
                    else { Process.killProcess(Process.myPid()); exitProcess(10) }
                }
                handlerInstalled = true
            }
        }
    }

    fun log(context: Context, level: String, event: String, details: String = "") {
        runCatching { synchronized(lock) { writeLocked(context.applicationContext, level, event, details) } }
    }

    fun logThrowable(context: Context, level: String, event: String, details: String, error: Throwable) {
        val out = StringWriter()
        runCatching { error.printStackTrace(PrintWriter(out)) }
        log(context, level, event, details + "\n" + out.toString())
    }

    fun beginOperation(context: Context, operation: String, details: String) {
        val app = context.applicationContext
        synchronized(lock) {
            runCatching {
                FileOutputStream(File(app.filesDir, MARKER), false).use {
                    it.write((operation + "|" + now() + "|" + oneLine(details)).toByteArray(Charsets.UTF_8))
                    it.fd.sync()
                }
            }
            writeLocked(app, "INFO", operation + "_begin", details)
        }
    }

    fun finishOperation(context: Context, operation: String, outcome: String, details: String = "") {
        val app = context.applicationContext
        synchronized(lock) {
            writeLocked(app, if (outcome == "success") "INFO" else "WARN", operation + "_" + outcome, details)
            runCatching {
                val marker = File(app.filesDir, MARKER)
                if (marker.isFile && marker.readText(Charsets.UTF_8).substringBefore("|") == operation) marker.delete()
            }
        }
    }

    fun memorySnapshot(context: Context): String = runCatching {
        val manager = context.getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager
        val info = ActivityManager.MemoryInfo()
        manager?.getMemoryInfo(info)
        "available=${info.availMem}; total=${info.totalMem}; lowMemory=${info.lowMemory}; vmMax=${Runtime.getRuntime().maxMemory()}; nativeHeap=${android.os.Debug.getNativeHeapAllocatedSize()}"
    }.getOrDefault("memorySnapshot=unavailable")

    fun readAll(context: Context): String = synchronized(lock) {
        val dir = context.applicationContext.filesDir
        val chunks = listOf(OLD_LOG, LOG).mapNotNull { name ->
            val file = File(dir, name)
            if (file.isFile) runCatching { file.readText(Charsets.UTF_8) }.getOrNull() else null
        }
        if (chunks.isEmpty()) "暂无运行日志。\n" else chunks.joinToString("\n")
    }

    fun clear(context: Context) {
        synchronized(lock) {
            runCatching { File(context.filesDir, LOG).delete() }
            runCatching { File(context.filesDir, OLD_LOG).delete() }
            writeLocked(context.applicationContext, "INFO", "logs_cleared", "用户清空了日志。")
        }
    }

    private fun version(context: Context) = runCatching {
        val p = context.packageManager.getPackageInfo(context.packageName, 0)
        "${p.versionName.orEmpty()} (${p.longVersionCode})"
    }.getOrDefault("unknown")

    private fun writeLocked(context: Context, level: String, event: String, details: String) {
        runCatching {
            val file = File(context.filesDir, LOG)
            if (file.exists() && file.length() >= MAX_BYTES) {
                val old = File(context.filesDir, OLD_LOG)
                runCatching { old.delete() }
                runCatching { file.renameTo(old) }
            }
            val line = "${now()} [${level}] [${event}] ${details.trimEnd()}\n"
            FileOutputStream(file, true).use {
                it.write(line.toByteArray(Charsets.UTF_8))
                it.fd.sync()
            }
        }
    }

    private fun now() = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US).format(Date())
    private fun oneLine(value: String) = value.replace('\r', ' ').replace('\n', ' ').take(4000)
}
'''
(app / "AppDiagnostics.kt").write_text(logger.replace("${", "$" + "{"), encoding="utf-8")

main = main_file.read_text(encoding="utf-8")
main = replace_once(main, '        super.onCreate(savedInstanceState)\n',
    '        super.onCreate(savedInstanceState)\n        AppDiagnostics.initialize(this)\n        AppDiagnostics.log(this, "INFO", "activity_onCreate", "MainActivity created; ${AppDiagnostics.memorySnapshot(this)}")\n',
    "install diagnostics")

main = replace_once(main, '''        if (modelFile.exists() && modelFile.length() > 0L) {
            statusText.text = "发现模型「${modelDisplayName(modelFile)}」（${formatBytes(modelFile.length())}），正在恢复模型…"
            // Native model state cannot survive process recreation; reload the previously imported file.
            loadLocalModel(autoTriggered = true)
        } else {
            statusText.text = "尚未加载模型：请先选择并加载一个 GGUF 文件，再发送消息。"
        }
''', '''        if (modelFile.exists() && modelFile.length() > 0L) {
            statusText.text = "发现本地模型「${modelDisplayName(modelFile)}」（${formatBytes(modelFile.length())}）。为避免启动时大模型自动加载导致闪退，请确认内存状态后手动点击“加载模型”。"
            AppDiagnostics.log(this, "INFO", "model_restore_deferred", "file=${modelFile.name}; bytes=${modelFile.length()}; auto reload disabled.")
        } else {
            statusText.text = "尚未加载模型：请先选择并加载一个 GGUF 文件，再发送消息。"
            AppDiagnostics.log(this, "INFO", "startup_no_model", "No selected model file.")
        }
''', "disable auto model reload")

launcher = '''    private val chooseModel = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        if (uri != null) importModel(uri)
    }
'''
launcher_new = '''    private val chooseModel = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        if (uri != null) importModel(uri)
    }

    private val exportDiagnosticsLauncher = registerForActivityResult(ActivityResultContracts.CreateDocument("text/plain")) { uri: Uri? ->
        if (uri != null) {
            val result = runCatching {
                val output = contentResolver.openOutputStream(uri) ?: error("无法打开导出目标")
                output.bufferedWriter(Charsets.UTF_8).use { it.write(AppDiagnostics.readAll(this@MainActivity)) }
            }
            if (result.isSuccess) {
                AppDiagnostics.log(this, "INFO", "logs_exported", "User exported diagnostics.")
                Toast.makeText(this, "日志已导出。", Toast.LENGTH_LONG).show()
            } else {
                AppDiagnostics.logThrowable(this, "ERROR", "logs_export_failed", "Export failed.", result.exceptionOrNull() ?: RuntimeException("unknown export error"))
                Toast.makeText(this, "导出失败：${result.exceptionOrNull()?.message ?: "未知错误"}", Toast.LENGTH_LONG).show()
            }
        }
    }
'''
main = replace_once(main, launcher, launcher_new, "add log export picker")

old_version_ui = '''        val systemStatusView = TextView(this).apply {
            text = getSystemVersionText()
            textSize = 12.5f; setTextColor(C_MUTED); setLineSpacing(dp(3).toFloat(), 1f)
            setTextIsSelectable(true)
        }
        root.addView(featureCard("📱 系统版本介绍", "显示当前设备的 Android 版本、API 级别、应用版本和 Vulkan 系统功能标志；信息来自 Android 系统 API，不会用固定文案假装检测成功。").apply {
            addView(systemStatusView, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) })
            addView(styledButton("↻ 刷新系统信息", C_PANEL_2, C_TEXT, C_STROKE).apply {
                setOnClickListener { refreshEngineAndSystem(engineStatusView, systemStatusView, this) }
            }, LinearLayout.LayoutParams(-1, dp(42)))
        }, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) })
'''
new_version_ui = '''        val appStatusView = TextView(this).apply {
            text = getAppVersionText()
            textSize = 12.5f; setTextColor(C_MUTED); setLineSpacing(dp(3).toFloat(), 1f)
            setTextIsSelectable(true)
        }
        root.addView(featureCard("📦 应用版本介绍", "显示东巴壳已安装版本、版本代码、包名及构建架构信息。").apply {
            addView(appStatusView, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) })
            addView(styledButton("↻ 刷新应用版本信息", C_PANEL_2, C_TEXT, C_STROKE).apply {
                setOnClickListener { appStatusView.text = getAppVersionText() }
            }, LinearLayout.LayoutParams(-1, dp(42)))
        }, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) })

        val systemStatusView = TextView(this).apply {
            text = getSystemVersionText()
            textSize = 12.5f; setTextColor(C_MUTED); setLineSpacing(dp(3).toFloat(), 1f)
            setTextIsSelectable(true)
        }
        val systemDetails = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            visibility = View.GONE
            addView(systemStatusView, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) })
            addView(styledButton("↻ 刷新系统信息", C_PANEL_2, C_TEXT, C_STROKE).apply {
                setOnClickListener { refreshEngineAndSystem(engineStatusView, systemStatusView, this) }
            }, LinearLayout.LayoutParams(-1, dp(42)))
        }
        val systemToggle = styledButton("展开系统版本详情", C_PANEL_2, C_TEXT, C_STROKE)
        systemToggle.setOnClickListener {
            val expanded = systemDetails.visibility != View.VISIBLE
            systemDetails.visibility = if (expanded) View.VISIBLE else View.GONE
            systemToggle.text = if (expanded) "收起系统版本详情" else "展开系统版本详情"
        }
        root.addView(featureCard("📱 系统版本介绍", "系统信息默认折叠，点击按钮查看 Android 版本、API 级别和 Vulkan 系统功能标志。").apply {
            addView(systemToggle, LinearLayout.LayoutParams(-1, dp(42)).apply { bottomMargin = dp(8) })
            addView(systemDetails, LinearLayout.LayoutParams(-1, -2))
        }, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) })
'''
main = replace_once(main, old_version_ui, new_version_ui, "separate app and system version descriptions")

diag_card = '''        root.addView(featureCard("🧾 运行与崩溃日志", "记录启动、模型导入/加载阶段、内存风险和异常堆栈；如果进程在原生加载时突然退出，下次启动会记录最后未完成操作。日志仅保存在本机，可查看并导出分析。").apply {
            addView(styledButton("查看运行日志", C_BLUE, Color.WHITE, C_BLUE_BRIGHT).apply { setOnClickListener { showDiagnosticLogsScreen() } }, LinearLayout.LayoutParams(-1, dp(44)))
        }, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) })
'''
anchor = '''        root.addView(featureCard("📋 后台任务与进度", "查看当前/最近任务、阶段、耗时、结果和错误日志。没有底层真实进度回调时只显示阶段，不伪造百分比。").apply {
'''
main = replace_once(main, anchor, diag_card + anchor, "add diagnostic log page entry")

methods = '''    private fun getAppVersionText(): String = buildString {
        val info = runCatching { packageManager.getPackageInfo(packageName, 0) }.getOrNull()
        val label = runCatching { applicationInfo.loadLabel(packageManager).toString() }.getOrDefault("东巴壳")
        append("应用名称：").append(label).append('\\n')
        append("应用版本：").append(info?.versionName ?: "未知").append('\\n')
        append("版本代码：").append(info?.longVersionCode ?: -1L).append('\\n')
        append("应用包名：").append(packageName).append('\\n')
        append("最低支持系统：Android 10（API 29）及以上").append('\\n')
        append("本地引擎：llama.cpp v0.6.0").append('\\n')
        append("APK 原生架构：").append(Build.SUPPORTED_ABIS.joinToString(", ")).append('\\n')
        append("当前设备：").append(Build.MANUFACTURER).append(' ').append(Build.MODEL)
    }

    private fun showDiagnosticLogsScreen() {
        val root = makeFeatureScreen("运行与崩溃日志", ::showMoreFeaturesScreen)
        root.addView(TextView(this).apply {
            text = "日志仅保存在本机应用私有目录，不会上传，也不会记录聊天正文。若原生模型加载导致进程突然结束，下次启动会显示疑似异常退出及最后未完成操作。复现后请导出日志发来分析。"
            textSize = 12f; setTextColor(C_MUTED); setLineSpacing(dp(3).toFloat(), 1f); setPadding(0, 0, 0, dp(8))
        })
        val logView = TextView(this).apply {
            textSize = 11f; setTextColor(C_TEXT); typeface = Typeface.MONOSPACE
            setTextIsSelectable(true); setPadding(dp(10), dp(10), dp(10), dp(10))
            background = rounded(C_PANEL, 14, C_STROKE_SOFT)
        }
        fun refreshLogView() {
            val all = AppDiagnostics.readAll(this)
            logView.text = if (all.length > 90000) "（页面仅显示日志末尾 90,000 个字符；导出文件包含完整保留日志。）§n§n" + all.takeLast(90000) else all
        }
        val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        actions.addView(styledButton("刷新", C_PANEL_2, C_TEXT, C_STROKE).apply { setOnClickListener { refreshLogView() } }, LinearLayout.LayoutParams(0, dp(42), 1f))
        actions.addView(styledButton("导出日志", C_BLUE, Color.WHITE, C_BLUE_BRIGHT).apply {
            setOnClickListener { exportDiagnosticsLauncher.launch("DongBaKe-diagnostics-${System.currentTimeMillis()}.txt") }
        }, LinearLayout.LayoutParams(0, dp(42), 1f).apply { marginStart = dp(6) })
        actions.addView(styledButton("清空", C_PANEL_2, C_TEXT, C_STROKE).apply {
            setOnClickListener {
                AlertDialog.Builder(this@MainActivity).setTitle("清空运行日志？")
                    .setMessage("只删除日志，不会删除模型、聊天记录或个人记忆。")
                    .setNegativeButton("取消", null)
                    .setPositiveButton("清空") { _, _ -> AppDiagnostics.clear(this@MainActivity); refreshLogView() }
                    .show()
            }
        }, LinearLayout.LayoutParams(0, dp(42), 0.72f).apply { marginStart = dp(6) })
        root.addView(actions, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(8) })
        val scroll = ScrollView(this).apply { isFillViewport = true; addView(logView) }
        root.addView(scroll, LinearLayout.LayoutParams(-1, dp(340)))
        refreshLogView()
    }

'''
main = replace_once(main, '    private fun showMoreFeaturesScreen() {\n', methods + '    private fun showMoreFeaturesScreen() {\n', "add log page and app version formatter")

load_start = '''        val loadStartedAt = android.os.SystemClock.elapsedRealtime()
        val loadFileSize = modelFile.length()
        statusText.text = "加载阶段 1/4：检查模型文件「${modelDisplayName(modelFile)}」（${formatBytes(loadFileSize)}）…"
'''
load_start_new = '''        val loadStartedAt = android.os.SystemClock.elapsedRealtime()
        val loadFileSize = modelFile.length()
        AppDiagnostics.beginOperation(this, "model_load", "file=${modelFile.name}; bytes=$loadFileSize")
        AppDiagnostics.log(this, "INFO", "model_load_configuration", "file=${modelFile.name}; bytes=$loadFileSize; context=${configuredContextSize()}; threads=${configuredCpuThreads()}; gpuLayersDefault=0; ${AppDiagnostics.memorySnapshot(this)}")
        statusText.text = "加载阶段 1/4：检查模型文件「${modelDisplayName(modelFile)}」（${formatBytes(loadFileSize)}）…"
'''
main = replace_once(main, load_start, load_start_new, "mark the beginning of model load")

try_anchor = '''            try {
                updateTrackedTask("模型加载", "检查文件", "已确认文件存在且非空，准备分析 GGUF 元数据。", null)
'''
try_new = '''            try {
                val manager = getSystemService(ACTIVITY_SERVICE) as? ActivityManager
                val memoryInfo = ActivityManager.MemoryInfo()
                runCatching { manager?.getMemoryInfo(memoryInfo) }
                val safeModelLimit = if (memoryInfo.availMem > 0L && memoryInfo.totalMem > 0L) {
                    minOf(memoryInfo.availMem * 7L / 10L, memoryInfo.totalMem * 50L / 100L)
                } else Long.MAX_VALUE
                AppDiagnostics.log(this@MainActivity, "INFO", "model_load_memory_preflight", "file=${modelFile.name}; bytes=$loadFileSize; available=${memoryInfo.availMem}; total=${memoryInfo.totalMem}; safeEstimate=$safeModelLimit; lowMemory=${memoryInfo.lowMemory}")
                if (loadFileSize > safeModelLimit) {
                    val message = "为降低闪退风险，已暂停加载此模型。模型文件 ${formatBytes(loadFileSize)}，系统可用内存约 ${formatBytes(memoryInfo.availMem)}，保守估算的安全上限约 ${formatBytes(safeModelLimit)}。请关闭后台应用后重试，或选择更小的 GGUF 量化模型。此估算偏保守，不代表模型文件损坏。"
                    AppDiagnostics.finishOperation(this@MainActivity, "model_load", "blocked_memory", message)
                    finishTrackedTask("模型加载", false, message)
                    statusText.text = message
                    showThinking(message, 100)
                    return@launch
                }
                updateTrackedTask("模型加载", "检查文件", "已确认文件存在且非空，准备分析 GGUF 元数据。", null)
'''
main = replace_once(main, try_anchor, try_new, "add model memory preflight")
main = replace_once(main, 'gpuLayers = preferences.getInt("inference_gpu_layers", 16)', 'gpuLayers = preferences.getInt("inference_gpu_layers", 0)', "default GPU layers to zero")

main = replace_once(main, '''                nativeModelHandle = loadedHandle
                generateReply = { prompt, webResearch ->
''', '''                nativeModelHandle = loadedHandle
                AppDiagnostics.finishOperation(this@MainActivity, "model_load", "success", "file=${modelFile.name}; bytes=$loadFileSize; elapsedMs=${android.os.SystemClock.elapsedRealtime() - loadStartedAt}")
                generateReply = { prompt, webResearch ->
''', "log model load success")

main = replace_once(main, '''            } catch (e: Exception) {
                finishTrackedTask("模型加载", false, "模型加载失败：${e.message ?: "请确认这是受支持的 GGUF 模型"}")
                nativeModelHandle = 0L
                loadedModelFileName = null
                statusText.text = "模型加载失败：${e.message ?: "请确认这是受支持的 GGUF 模型"}"
''', '''            } catch (e: OutOfMemoryError) {
                AppDiagnostics.logThrowable(this@MainActivity, "FATAL", "model_load_out_of_memory", "file=${modelFile.name}; bytes=$loadFileSize; ${AppDiagnostics.memorySnapshot(this@MainActivity)}", e)
                AppDiagnostics.finishOperation(this@MainActivity, "model_load", "failed_memory", "OutOfMemoryError: ${e.message.orEmpty()}")
                finishTrackedTask("模型加载", false, "模型加载时内存不足。请关闭后台应用或换用更小的 GGUF 模型。")
                nativeModelHandle = 0L
                loadedModelFileName = null
                statusText.text = "模型加载时内存不足。为避免再次闪退，请使用更小的模型或更低的上下文设置。"
            } catch (e: Exception) {
                AppDiagnostics.logThrowable(this@MainActivity, "ERROR", "model_load_exception", "file=${modelFile.name}; bytes=$loadFileSize; ${AppDiagnostics.memorySnapshot(this@MainActivity)}", e)
                AppDiagnostics.finishOperation(this@MainActivity, "model_load", "failed", "${e.javaClass.simpleName}: ${e.message.orEmpty()}")
                finishTrackedTask("模型加载", false, "模型加载失败：${e.message ?: "请确认这是受支持的 GGUF 模型"}")
                nativeModelHandle = 0L
                loadedModelFileName = null
                statusText.text = "模型加载失败：${e.message ?: "请确认这是受支持的 GGUF 模型"}"
''', "log load failures including Java OOM")

main = replace_once(main, '        val destination = File(modelDirectory, destinationName)\n        statusText.text = "正在导入模型',
    '        val destination = File(modelDirectory, destinationName)\n        AppDiagnostics.log(this, "INFO", "model_import_begin", "file=$destinationName; uriScheme=${uri.scheme.orEmpty()}")\n        statusText.text = "正在导入模型',
    "log import start")
main = replace_once(main,
    '                Toast.makeText(this@MainActivity, "模型分析完成；已保留其他模型和聊天数据。", Toast.LENGTH_LONG).show()\n',
    '                AppDiagnostics.log(this@MainActivity, "INFO", "model_import_success", "file=${destination.name}; bytes=${destination.length()}; architecture=${profile.architecture}; quantization=${profile.quantizationHint}")\n                Toast.makeText(this@MainActivity, "模型分析完成；已保留其他模型和聊天数据。", Toast.LENGTH_LONG).show()\n',
    "log import success")
main = replace_once(main,
    '            } catch (e: Exception) {\n                finishTrackedTask("模型导入", false, "导入失败：${e.message ?: "未知错误"}")',
    '            } catch (e: Exception) {\n                AppDiagnostics.logThrowable(this@MainActivity, "ERROR", "model_import_exception", "model import failed: ${e.message.orEmpty()}", e)\n                finishTrackedTask("模型导入", false, "导入失败：${e.message ?: "未知错误"}")',
    "log import failures")
main_file.write_text(main, encoding="utf-8")

native = native_file.read_text(encoding="utf-8")
native = replace_once(native, 'gpuLayers: Int = 16', 'gpuLayers: Int = 0', "native engine wrapper CPU first")
native_file.write_text(native, encoding="utf-8")

gradle = gradle_file.read_text(encoding="utf-8")
gradle = replace_once(gradle, 'versionCode = 24', 'versionCode = 25', "increment version code")
gradle = replace_once(gradle, 'versionName = "0.10.2"', 'versionName = "0.10.3"', "increment version name")
gradle_file.write_text(gradle, encoding="utf-8")

for p in root.rglob("*"):
    if p.is_file() and p.suffix in {".py", ".kt", ".kts", ".sh"}:
        try:
            source = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        updated = source.replace(r'versionCode\\s*=\\s*24\\b', r'versionCode\\s*=\\s*25\\b')
        if updated != source:
            p.write_text(updated, encoding="utf-8")

main_text = main_file.read_text(encoding="utf-8")
gradle_text = gradle_file.read_text(encoding="utf-8")
for expected in ['AppDiagnostics.beginOperation(this, "model_load"', '📦 应用版本介绍',
                 '展开系统版本详情', 'private fun showDiagnosticLogsScreen()',
                 'gpuLayers = preferences.getInt("inference_gpu_layers", 0)',
                 'versionCode = 25', 'versionName = "0.10.3"']:
    if expected not in main_text + "\n" + gradle_text:
        raise SystemExit("Post-patch assertion failed: " + expected)

print("Patched source revision 25, versionName 0.10.3.")
