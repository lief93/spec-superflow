# Static Animation Projection

Animation is explicitly out of scope for the POC. In report-mode pages:

- `remember { Animatable(initialFloat) }` becomes a typed readonly holder of the
  source initial value. Its `value` remains usable by static UI and collections.
  Motion and remember caching are not implemented; the diagnosis says so.
- In a Compose body containing this animation construction, LaunchedEffect-only
  statements/guards and standard forEach/forEachIndexed/repeat wrappers are
  discarded before dependency selection. Their keys, guards, iterables and
  callbacks are not evaluated. Mixed loops containing UI are not discarded.
- Unsupported graphicsLayer blocks in that body are omitted while retaining the
  Modifier receiver/chain. Private immutable locals consumed only by discarded
  work are pruned through the same dependency logic as theme projection.
- List UI forEach uses the existing typed ForEach target node. Supported uniform
  background shapes use native borderRadius without clipping child content.
- There is no animation engine, timer, interpolation, coroutine or fake velocity.
  Other required animation properties/operations, keyed or complex remember
  bodies and unsupported initial values still fail explicitly. Strict and
  language modes do not enable this degradation. Ordinary UI state is unchanged.

Run against real Compose dependencies:

```sh
node tools/kotlin-ets/tests/ui/static-animation/check.mjs /path/to/classpath.txt
node tools/kotlin-ets/tests/ui/static-animation/runtime.mjs /fresh/initial.ets
node tools/kotlin-ets/tests/ui/basic-controls-sdk.mjs /fresh/page.ets
node tools/kotlin-ets/tests/ui/static-animation/native.mjs /tmp/layout.json /tmp/screenshot.jpeg
```

Install the unmodified SDK output before native validation. The page must show
Before, three red static circles (including duplicate zero initial values), and
After. Generated-code and strict/required-value negatives do not alone prove
native geometry; the native checker verifies the three circles and both labels.
