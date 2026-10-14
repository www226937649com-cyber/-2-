#!/usr/bin/env python3
from pathlib import Path
import re
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else "buildsrc")
tests = root / "tests"
changed = False
for p in tests.rglob("*.py"):
    source = p.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    output = []
    file_changed = False
    for line in lines:
        updated = line
        # Version assertions must follow the incremented Android app metadata.
        if "versionCode" in updated and "24" in updated:
            updated = re.sub(r"(?<!\d)24(?!\d)", "25", updated)
        if ("versionName" in updated or "0.10.2" in updated) and "0.10.2" in updated:
            updated = updated.replace("0.10.2", "0.10.3")
        if updated != line:
            file_changed = True
        output.append(updated)
    if file_changed:
        p.write_text("".join(output), encoding="utf-8")
        print(f"Updated stale version assertions in {p.relative_to(root)}")
        changed = True
# Keep CPU-first loading genuinely independent of Vulkan probing. The native loader must
# only enumerate Vulkan devices when a nonzero GPU offload request is explicitly enabled.
main_file = root / "app/src/main/java/com/aiguanjia/app/MainActivity.kt"
main = main_file.read_text(encoding="utf-8")
old_main = """                        NativeLlamaEngine.initializeBackend(applicationInfo.nativeLibraryDir)
                        NativeLlamaEngine.loadModel(
                            path = path,
                            contextSize = contextSize,
                            threads = cpuThreads,
                            gpuLayers = preferences.getInt("inference_gpu_layers", 0)
                        )"""
new_main = """                        val requestedGpuLayers = preferences.getInt("inference_gpu_layers", 0).coerceAtLeast(0)
                        if (requestedGpuLayers > 0) {
                            NativeLlamaEngine.initializeBackend(applicationInfo.nativeLibraryDir)
                        }
                        NativeLlamaEngine.loadModel(
                            path = path,
                            contextSize = contextSize,
                            threads = cpuThreads,
                            gpuLayers = requestedGpuLayers
                        )"""
if old_main in main:
    main = main.replace(old_main, new_main, 1)
    main_file.write_text(main, encoding="utf-8")
    print("Patched MainActivity: CPU-first loading skips dynamic GPU backend initialization.")
    changed = True
elif new_main not in main:
    raise SystemExit("Could not find model-loading backend initialization block in MainActivity.kt")

native_file = root / "app/src/main/cpp/dongbake_llama_jni.cpp"
native = native_file.read_text(encoding="utf-8")
old_native = """        const bool vulkan_plugin_registered = ggml_backend_reg_by_name("Vulkan") != nullptr;
        const bool gpu_build_available = vulkan_plugin_registered && llama_supports_gpu_offload();
        const std::string device_report = describe_vulkan_devices();
        const bool device_seen = device_report.find("检测到 ") == 0;
        int chosen_layers = (gpu_build_available && device_seen) ? session->requested_gpu_layers : 0;"""
new_native = """        bool vulkan_plugin_registered = false;
        bool gpu_build_available = false;
        bool device_seen = false;
        int chosen_layers = 0;
        // Stability mode is CPU-only by default. Do not load/probe Vulkan drivers unless GPU offload was explicitly requested.
        if (session->requested_gpu_layers > 0) {
            vulkan_plugin_registered = ggml_backend_reg_by_name("Vulkan") != nullptr;
            gpu_build_available = vulkan_plugin_registered && llama_supports_gpu_offload();
            const std::string device_report = describe_vulkan_devices();
            device_seen = device_report.find("检测到 ") == 0;
            if (gpu_build_available && device_seen) chosen_layers = session->requested_gpu_layers;
        }"""
if old_native in native:
    native = native.replace(old_native, new_native, 1)
    native_file.write_text(native, encoding="utf-8")
    print("Patched native loader: Vulkan enumeration only runs when GPU layers > 0.")
    changed = True
elif new_native not in native:
    raise SystemExit("Could not find Vulkan probing block in dongbake_llama_jni.cpp")

if changed:
    (root / ".source25-test-repair-changed").write_text("changed\n", encoding="utf-8")
print("Source-25 maintenance:", "changed" if changed else "already current")
