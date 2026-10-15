# Source-36 audit note: cancellation boundary, CI status, and remaining verification

Updated: 2026-10-15

This file is the persistent project handoff note for future DongBaKe AI Manager updates. Read it before changing inference-budget or build/release logic.

## 1. Do not conflate the two issues

### Runtime logic boundary: explicit user cancellation

A real runtime edge case was identified in the inference continuation policy. If code only checks whether `generatedTokens >= requestedTokens`, it could mistake a user-stopped generation for token-cap exhaustion and automatically restart with a continuation. That would violate the user's explicit stop action.

Required invariant:
- If native generation metrics explicitly contain `cancelled=true`, automatic continuation must be suppressed.
- A reached token cap is not by itself proof that the user intended another generation.
- Keep separate detection for token-cap exhaustion, blank output, an unclosed `<think>` block, and a closed thinking block with no final answer.
- Automatic continuation is bounded (one continuation pass); it must not form an infinite generation loop.
- If the safe cap is exhausted, expose that the answer may be incomplete rather than claiming successful completion.

Current code puts this policy in `app/src/main/java/com/aiguanjia/app/InferenceBudgetPolicy.kt`; tests are in `app/src/test/java/com/aiguanjia/app/InferenceBudgetPolicyTest.kt`.

### CI / archive publishing issue

Run `38724050322` successfully completed native compilation, Android tests, APK builds, and source ZIP packaging/upload, but the final source-archive push failed because the branch advanced during the run (non-fast-forward). This was a CI publishing failure, distinct from an Android runtime failure.

The workflow was hardened to fetch/rebase before pushing the archive. Final run `38724206328` completed **successfully, including the archive publish step**. Its uploaded artifact is `DongBaKe-source-36-v0.12.2-thinking-budget-continuation-run-5`.

Do not report the earlier archive-publish failure as a current unresolved failure; also do not confuse a successful CI build with proof of device runtime correctness.

## 2. Source-36 inference budget policy

Version: `0.12.2-thinking-budget-continuation`, versionCode `36`.

Soft thinking targets (guidance to the model, not guaranteed hard stops):
- Quick / 快速: 64 tokens.
- Balanced / 均衡: 384 tokens.
- Deep / 深度: 1024 tokens.

Initial-pass output budgets:
- Quick: 288 tokens.
- Balanced: 768 tokens.
- Deep: 1792 tokens.

The total hard cap is context-sensitive: at most 4096 tokens and at most half the clamped context window (minimum 256), leaving context space for the prompt/history. The pinned llama.cpp v0.6.0 integration does not expose the newer Qwen-style reasoning-budget sampler as an app API, so soft targets are implemented via prompting plus bounded continuation, not as a true sampler-level forced closure. Different models may respond differently to `/no_think` or answer-first prompts.

## 3. Latest verifiable build and tests

Latest verified workflow run: https://github.com/www226937649com-cyber/-2-/actions/runs/38724206328
- Workflow result: success.
- Source commit used for build: `7bc5cf41d9cbd32789abc8d992cedfc024387ec3`.
- Python regression suite: 72 passed.
- Source audit suite: 15 passed.
- Android `testDebugUnitTest`: 14 passed, 0 failed, 0 ignored.
- CPU/Vulkan native libraries: build passed for arm64-v8a and x86_64.
- Debug main APK and safe side-by-side APK: build and signature checks passed.
- Source ZIP: integrity check passed; generated caches excluded.
- Side-by-side APK: `DongBaKe-v0.12.2-thinking-budget-continuation-side-by-side.apk`, package `com.aiguanjia.app.fix36`, label `东巴壳（软预算测试）`.
- Side-by-side APK SHA-256: `56053be1616f22f1c378511c1190cc943d7847970adeb87d72217804aff6b5e3`.
- Source ZIP SHA-256: `e4f80fe8542b9f8996d6e2b56fed7a2d68dcfb6bc231ec828cac6e51d69bfd2b`.

## 4. Current status and non-claims

- The repair work remains on `work/source-36-thinking-budget`; `main` was not merged/changed by this task and was still at `bea338084655e0bf7c9a30594f28088e7e8dbe78` during final audit.
- The build provenance explicitly says `device_execution=not_yet_verified`. Cloud tests are not a substitute for real-device validation.
- Do not claim “the software has no problems” or promise future updates will never have problems. Correct wording: automated tests/build checks passed, but the device-level behavior of thinking convergence, long outputs, continuation, cancellation, and memory/latency still needs confirmation on target hardware.
- For future updates, review both app runtime logic and the CI workflow/archive/release path. After changes, verify the actual tested commit SHA, the complete workflow result, artifact contents, APK package/version/signature/hash, and device test results. Do not assume “APK step succeeded” means the final workflow succeeded.
