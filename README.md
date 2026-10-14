# DongBaKe Android — source-31 crash diagnostic

This is an isolated diagnostic branch. It does not replace or merge into the source-30 branch.

- Version: **0.10.9** (versionCode 31); application ID remains `com.aiguanjia.app`.
- Diagnostic change: keep the selected context length but cap `n_batch` at 128 and `n_ubatch` at 64. The purpose is to test whether lower graph-reserve pressure changes the historical native crash; root cause is not yet confirmed.
- Source archive: [DongBaKe-source-31.zip](https://github.com/www226937649com-cyber/-2-/blob/work/source-31-crash-diagnostic/DongBaKe-source-31.zip).
- Build and APK artifacts: [GitHub Actions run 38600058603](https://github.com/www226937649com-cyber/-2-/actions/runs/38600058603).
- In-app test procedure: see [source-31-crash-diagnostic.md](https://github.com/www226937649com-cyber/-2-/blob/work/source-31-crash-diagnostic/docs/source-31-crash-diagnostic.md).

The source tests pass locally and in the workflow's source-audit step. Android/NDK compilation and packaging are still being checked by the workflow. A successful build does not establish that inference works on a physical Redmi device.

**Installation caution:** the application ID is unchanged. If Android reports a signature conflict while installing the diagnostic APK, do not uninstall the existing app just to force installation; app data and app-specific model files may be removed. The diagnostic build must still be tested on the device before any compatibility claim is made.
