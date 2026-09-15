# Project compiler plugin inputs

Status: scoped implementation and acceptance complete; independent review deferred.
Approved by user "实现吧". Evidence: [acceptance](acceptance.md).

Scope: unblock the official frontend for Gradle projects requiring Kotlin
serialization 2.1.20. Reuse the selected task's serialized compiler arguments and
the official compiler's plugin loading. Do not implement another plugin engine.

Acceptance:
- Collect actual plugin paths, options and compiler settings after prerequisites.
- Preserve supported semantic options; separate target-owned build options and
  reject unhandled plugins/options clearly, without silently removing behavior.
- A real Gradle serialization fixture compiles normally, fails frontend analysis
  without its plugin, and reaches plugin-generated IR with its captured settings.
- Exercise public project input and existing plugin-free regressions. Backend
  rejection of serialization runtime code is distinct from frontend acceptance.
- Keep source/output files unchanged on failures, retain command/evidence logs.

Non-goals: arbitrary plugin compatibility, serialization runtime ETS support,
running JVM Compose lowering instead of our ArkUI adapter, full compiler-version
switching, or private project source access. Independent review stays deferred.
