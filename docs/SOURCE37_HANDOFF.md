# DongBaKe source-37 handoff / continuation record

更新时间：2026-10-16（当前对话）
仓库：www226937649com-cyber/-2-
工作分支：work/source-37-context-logging
主分支：main

## 1. 重要：新对话从这里继续

不要从“已经生成 APK”或“源码已经完全合并”开始推断。
source-37 当前仍是工作分支实验/修复线，main 尚未合并 source-37。

当前工作分支 HEAD：
ad987582180d90c3ac02ebc64693ed6fc8f5be1c

当前 main HEAD：
bea338084655e0bf7c9a30594f28088e7e8dbe78

## 2. 本轮目标

source-37 的核心方向是：
- 不同思考模式动态使用不同的软性上下文/思考长度策略；
- 优化推理参数页面及参数切换 UI；
- 全面升级运行日志，记录 prefill/decode、warmup、缓存、线程/大核、ADPF、上下文、终止原因等可诊断数据；
- 日志记录开关、导出优化，并让后续版本构建流程持续携带日志能力；
- 精简系统提示词，减少每轮 prefill；
- 软性早停代替正常情况下的硬截断；
- 截断后自动兜底续写，避免只显示半截思考/半截答案；
- 保留旧数据/旧设置兼容。

## 3. 用户已确认的运行现象

更新前/测试中曾出现：
- 模型有时思考约 30 秒；
- 有时思考到一半直接停止；
- 有时正式回答写到一半直接终止。
用户怀疑存在固定生成上限。

已讨论并决定的工程原则：
- 硬上限只做异常护栏，不承担正常思考长度控制；
- 不同思考模式使用不同软性预算；
- 达到软阈值时应收敛并继续正式回答，而不是直接断电；
- 若检测到思考未闭合且没有正式回答，做一次“停止思考、直接给结论”的兜底生成；
- 必须区分“模型自然结束”和“系统硬性截断”，并写入日志。

## 4. 元宝建议：哪些可采用，哪些需要谨慎

有价值的方向：
- warmup / mmap 懒加载导致首轮缺页读取；
- system prompt 前缀缓存；
- KV cache 内存控制/量化；
- chunked prefill / n_batch；
- 上下文接近上限时的压缩或提示；
- 推理线程调度；
- tokenizer/token 序列缓存；
- Android 性能/温控信息；
- decode 采样器精简；
- UI 流式渲染节流；
- 后台线程、内存预算、前台服务等健壮性。

必须谨慎：
- 不能假定所有本地 llama.cpp/后端版本都原生提供独立 thinking budget；
- “插入早停指令”必须与当前模型的 thinking 格式兼容，不能破坏模型输出；
- 不能假装动态改变了底层模型的原生 context size。若实际模型容量未重新加载，日志/界面必须区分“模式建议值、实际加载值、有效值”；
- ADPF/大核绑定/前台服务等必须以 Android 版本和设备能力为前提，失败时应安全降级；
- KV cache 量化是否可用取决于当前后端 API，不能仅靠配置名假设。

## 5. 系统提示词需求

用户提供的精简方向：
- 删除礼貌套话、重复规则、长篇外貌/背景、few-shot、显而易见行为说明、长免责声明；
- 必须保留：思考停止条件、软性思考长度规则、简单问题直接答、输出格式、核心角色信息、安全约束；
- 目标：系统提示词控制在 100 字以内；
- 简单问题不展开推理；
- 复杂问题思考到有结论立即停止，不反复验证；
- 不能因为系统提示词精简导致自定义 AI 名称丢失。

本轮已发现并修正一个兼容细节：
旧版会把用户自定义助手名称传给模型；精简提示词不能固定写成“中文伙伴”而丢掉名称。
因此应继续保留一个短名称参数，名称限制为 16 字以内，以控制 prompt 长度。

## 6. 已经实际修改/新增的 source-37 文件

工作分支已有：
- patches/source37-parts/part00.txt
- patches/source37-parts/part01.txt
- patches/source37-parts/part02.txt
- patches/source37-parts/part03.txt
- patches/source37-parts/part04.txt
- patches/source37-parts/part05.txt
- patches/source37-parts/part06.txt

这些分段用于重建 source-37 主补丁。

另外已有：
- patches/source37-kotlin-compile-fix.patch

该修复针对 Android Kotlin 编译错误：
Spinner 的 popupBackground Kotlin 属性在当前接口下不能直接赋值。
6 处应使用：
setPopupBackgroundDrawable(...)
而不是：
popupBackground = ...

对应推理参数页面的多个 Spinner（线程、上下文、GPU layer、KV cache、Flash Attention、draft 等）。

## 7. CI / 构建历史中的关键事实

一次完整 source-37 构建已经：
- 通过补丁校验/应用；
- 通过原生 CPU/Vulkan 库构建；
- 通过源码测试阶段；
- 最终在 Android Kotlin 编译阶段失败。

失败不是 6 个独立逻辑问题，而是上述 Spinner API 用法导致的同类编译错误。

之后已经增加了快速诊断 workflow，用于打印 MainActivity.kt 约 1768-1860 行并核对 patch headers；诊断确认了上述原因。

当前 build workflow：
.github/workflows/build-apk-workflow-source-37.yml

该 workflow 已恢复自动触发，并已加入：
- source-37 patch 分段输入；
- source-37-kotlin-compile-fix.patch 作为输入路径；
- patch/hash/源码诊断信息；
- 构建超时与 concurrency 控制。

注意：当前还没有把“完整修复后的 APK 构建成功”当成事实。下一步必须重新跑完整 CI 验证。

## 8. 临时诊断 workflow

曾新增：
.github/workflows/inspect-source-37-kotlin-errors.yml

用途只是快速确认 Kotlin 编译错误。
如果后续完整构建已经稳定通过，应考虑删除该临时诊断 workflow，避免仓库留下无必要的维护负担。

## 9. 当前真正的下一步

不要重新设计 source-37。
从现有工作分支继续：

1. 确认 source37 主补丁在构建 workflow 中确实包含 source37-kotlin-compile-fix.patch；
2. 确认修复补丁实际应用后 MainActivity.kt 六处 Spinner 都使用 setPopupBackgroundDrawable；
3. 删除/停用仅用于诊断的临时 workflow（完整 CI 通过后做）；
4. 重新运行完整 Android CI；
5. 若编译通过，继续检查 APK、版本号、side-by-side 包、source archive；
6. 检查 source-37 功能相关日志和推理参数代码没有因 Kotlin 修复发生回归；
7. 最后再决定是否需要生成最终 APK/合并 main。

## 10. 不要做的事

- 不要把 source-37 直接合并 main，除非用户明确要求并且最终构建/测试通过；
- 不要因为一次 CI 通过就声称所有运行时功能已经验证；
- 不要重新生成一套新的 source-37；
- 不要删除旧数据兼容层；
- 不要把“动态软性上下文长度”误写成底层 context size 已经实时扩容；
- 不要用未经验证的 API 猜测替换后端实现。

## 11. 用户目前希望的工作方式

用户希望先核对状态、发现卡点后从准确位置继续，不要反复从头开始。
如果构建卡住，应先检查 workflow/job 状态，再决定是否等待、修复或重新触发。
