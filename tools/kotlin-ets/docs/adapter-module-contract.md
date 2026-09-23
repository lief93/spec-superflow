# Independent adapter modules: fixed implementation contract

Priority task, before further language expansion. New adapter modules should add
their own source, JVM SPI service descriptor and tests without editing central
rule lists or ArkUiCalls. Rebuilding remains required; no hot-loading or downloads.

Main owns src/adapters/AdapterModules.kt plus Main.kt and ComposeLowering wiring.
Parfit owns build-time module discovery/launcher changes, independent example
modules, tests and the user-facing guide. Neither lane edits language lowering,
target tree/validator/printer, existing control classes or the other's files.

Public API in package dev.ets:
- AdapterModule: id:String; sourceCalls:Set<String> (default empty);
  projectCalls:List<AdapterProjectCall> (default empty); sourceTypes:Set<String>
  (default empty); sourceFields:Set<String> (default empty);
  targetCalls:List<AdapterTargetCall> (default empty);
  targetValues:List<AdapterTargetValue> (default empty); imports:List<EtsImport>
  (default empty);
  create(target:AdapterTargetApi, ui:AdapterUiServices?):CallRule.
- AdapterTargetCall(id:String, name:String, signature:EtsFunctionType).
- AdapterTargetValue(id:String, name:String, type:EtsType).
- AdapterTargetApi.call(id:String, arguments:List<EtsExpression>, source:SourceSpan,
  receiver:EtsExpression? = null):EtsCall. Exact arity, argument and return types
  remain checked; errors retain source. Signature declarations travel with module.
- AdapterTargetApi.value(id:String, type:EtsType, source:SourceSpan):EtsReference.
  The registered target type must structurally match the requested type. Declared
  symbol identities remain exact; an omitted symbol identity is a typed template.
- AdapterUiServices.content(IrExpression, Scope):List<EtsStatement> and
  decorate(IrExpression?, Scope, EtsUiElement, Set<String> = emptySet()):List<EtsStatement>
  delegate existing content/modifier conversion, never reparse source.
- AdapterModules(modules:List<AdapterModule> = emptyList()); companion load()
  uses JVM ServiceLoader. rules(ui:AdapterUiServices? = null):List<CallRule>;
  imports:List<EtsImport>. Module construction order is sorted by id. Duplicate
  module IDs, claimed source calls/types/fields, project declaration ownership,
  target call/value IDs and conflicting import bindings fail before generation.
  Core and UI factories use the same CallRule
  dispatcher and typed target nodes. Null ui creates value/effect/type rules;
  scoped nonnull ui creates UI rules only, preventing duplicated value dispatch.

Build contract: discover module directories beneath built-in `adapters/` plus
optional external roots from KOTLIN_ETS_ADAPTER_DIRS (platform path separator).
Each module has *.kt sources and META-INF/services/dev.ets.AdapterModule, using
ordinary SPI provider lines/comments. Compile sources with tool sources and merge
descriptors into tool.jar deterministically. Do not parse Kotlin text to find
classes or edit a global provider list. Malformed/missing requested roots or
providers must fail clearly; source Kotlin dependencies remain separate.

Tests: no-extension behavior unchanged; public CLI loads an independently added
module from an external directory (including spaces); ordinary value/effect and
real Compose UI extension use typed targets; no central registration/signature
edit; unknown overload/arguments, conflicting registrations, wrong types and
missing provider reject. A focused actual SDK check validates any example's new
ArkUI API. No full native/install loop. Examples are synthetic, never company code.

Cost sample 1: limited parallel implementation (main API/wiring, Parfit build/tests)
with one serialized heavy build slot and fixed reviewer after freeze. Capture
fresh token counters before dispatch, before/after review and at acceptance.
Report cached versus uncached input, output and actual elapsed time; no invented
serial speedup. Prior R2H review is outside this sample. Prefer serial next sample.
