# String-valued resource calls

Run `node tools/kotlin-ets/tests/ui/strings/run.mjs`, then pass its Page.ets to
`node tools/kotlin-ets/tests/ui/strings/sdk.mjs`. Install the resulting HAP and
check `[Resource title]` and `Resource subtitle` in the native layout dump.

Prepare input with `python3 tools/kotlin-ets/string-resources.py --res-dir <dir>
--namespace <R-package> --out <fresh-dir>`, then pass `--string-resources <fresh-dir>`
to either compiler entry. Use the selected module/variant's merged resources, or
an explicitly selected standalone fixture; this script does not infer overlays.

The generated sibling `<output>.resources` contains referenced native strings.
Dynamic-ID consumers also include all supported entries in the supplied ID map.
Merge its qualifier/element entries into the target module's resources without
overwriting unrelated entries. Language-only and language/region folders map to
native resource qualifiers. No startup locale is baked into ETS.

The XML materializer accepts plain text and the bounded formats described below. Styled, escaped,
reference and whitespace-normalized forms, as well as other qualifiers, retain
an unsupported reason which is reported when that resource is referenced. Missing
resources fail without ETS/resource output. Runtime
locale changes triggering recomposition are not certified by the fixed-locale test.
## Dynamic IDs and formatting

The `Formatted` CLI fixture passes resource IDs and varargs through an ordinary
class. `--symbols R.txt` connects original integer IDs to native resource names.
The materializer accepts `%s`, `%d` and positional variants; formatting itself
uses the native resource manager. Other format syntax remains diagnosed.

Compile `Formatted.ets` unchanged with `tests/ui/basic-controls-sdk.mjs`, install
and launch its HAP, then pass a native layout dump to `native.mjs <dump> formatted`.
Expected text is `Hello Ada: 3 items` and `Resource title` (empty varargs).
