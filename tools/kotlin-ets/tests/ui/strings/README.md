# String-valued resource calls

Run `node tools/kotlin-ets/tests/ui/strings/run.mjs`, then pass its Page.ets to
`node tools/kotlin-ets/tests/ui/strings/sdk.mjs`. Install the resulting HAP and
check `[Resource title]` and `Resource subtitle` in the native layout dump.

Prepare input with `node tools/kotlin-ets/string-resources.mjs --res-dir <dir>
--namespace <R-package> --out <fresh-dir> --symbols <selected-R.txt>`, then pass
`--string-resources <fresh-dir>` to direct source compilation. Project mode
performs the same materialization automatically from its selected Android
variant's ordered source-set roots and final IDs.

The generated sibling `<output>.resources` contains referenced native strings,
plurals and string arrays.
Dynamic-ID consumers also include all supported entries in the supplied ID map.
Merge its qualifier/element entries into the target module's resources without
overwriting unrelated entries. Language-only and language/region folders map to
native resource qualifiers. No startup locale is baked into ETS.

The XML materializer accepts plain text, Android escapes and the bounded formats
described below. Styled spans, references, complex ICU messages and complex locale
qualifiers retain an unsupported reason which is reported when that resource is
referenced. Missing resources and unknown constant IDs fail without ETS/resource output. Runtime
locale changes triggering recomposition are not certified by the fixed-locale test.
## Dynamic IDs and formatting

The `Formatted` CLI fixture passes resource IDs and varargs through an ordinary
class. `--symbols R.txt` connects original integer IDs to native resource names.
The materializer accepts `%s`, `%d` and positional variants; formatting itself
uses the native resource manager. Other format syntax remains diagnosed.

Compile `Formatted.ets` unchanged with `tests/ui/basic-controls-sdk.mjs`, install
and launch its HAP, then pass a native layout dump to `native.mjs <dump> formatted`.
Expected text is `Hello Ada: 3 items` and `Resource title` (empty varargs).
