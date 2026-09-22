# Image Resource Materialization

This is a local asset preparation tool for the new Kotlin-to-ETS backend, not
the old page JSON renderer. It never uploads assets or edits an Android/Harmony
project.

```sh
node tools/kotlin-ets/image-resources.mjs \
  --res-dir /absolute/android/res \
  --namespace example \
  --out /absolute/fresh/output
```

The output contains `media/` and `image-resources.properties`. Properties use
ASCII keys and values compatible with Java Properties:

```properties
example.R.drawable.banner = img_<sha256_of_complete_symbol>
```

When a resource ID crosses an ordinary `Int` parameter, also supply the selected
Android build's final `R.txt`, for example with `--symbols /absolute/R.txt`.
The tool writes `source-resource-ids.properties` beside the mapping. These are
actual Android IDs, not hashes or invented target IDs. Zero/unresolved IDs,
missing selected symbols and duplicate numeric IDs are rejected. The backend
keeps method parameter types/numbers and emits a typed `painterResource` lookup;
an unknown runtime ID fails explicitly.

Use `--include banner,logo` to prepare only an explicitly selected asset set.
Unselected assets are not converted. Selected missing assets and ambiguous
variants still fail. Omitting `--include` retains the complete drawable scan.

The actual value is `img_` plus the complete 64-character lowercase SHA-256 of
`example.R.drawable.banner`, not the placeholder above. File extensions are not
part of the mapped value. Namespace and source symbol participate in naming;
identical image bytes belonging to different symbols get distinct names.
Repeated inputs produce identical names and bytes. Detected target-name
collisions fail, rather than aliasing two symbols.

## Supported Inputs

- Regular `.png`, `.jpg`, `.jpeg` and `.webp` files in `drawable/` or
  `drawable-nodpi/`. Bytes are copied unchanged; `.jpeg` uses target `.jpg`.
- Static VectorDrawable `.xml` in unqualified `drawable/`, converted to SVG.
  Literal colors and the existing converter's bounded static features apply.
- Exactly one file per source drawable symbol. Unqualified/nodpi duplicates,
  same-name different formats and any nonempty other `drawable-*` directory
  fail. No density, locale, night, orientation or API-level selection is guessed.

Nine-patch files, arbitrary drawable XML (selectors, shapes, etc.), raw SVG input,
unknown extensions, symlinks, malformed vectors and invalid resource names fail.
The standalone `--res-dir` command does not collect other resource types such as
`mipmap/` and `values/`; project mode adds bounded mipmap support below.
Bitmap checks are file-signature checks, not a full production pixel decoder;
the test fixtures additionally undergo independent decoding.

## Automatic project materialization

The formal `--project ... --variant ...` entry automatically uses the selected
Android variant's declared resource inputs when `--image-resources` is omitted.
The Gradle collector records the module namespace, AGP source-set order, existing
resource roots and the process-resources task's declared runtime `R.txt` artifact.
It does not search `build/`, parse source text or infer integer IDs.

Project materialization supports unqualified or `-nodpi` `drawable` and `mipmap`
PNG, JPEG, WebP and SVG files. Static unqualified Android VectorDrawable XML is
converted through the same deterministic bridge. Later source sets override
earlier ones; the winning source, numeric overlay priority and shadowed origins
are recorded in `image-resource-origins.json`. Two definitions at the same
priority fail as ambiguous. Density/theme/API-qualified inputs are not guessed.

Selector, animated-vector, layer-list and other unsupported XML definitions are
recorded against their resolved `namespace.R.type.name` and selected-build ID.
They do not block an unrelated entry, but a selected source reference produces
an exact source diagnostic and no ETS. A selected `R` symbol with no file in the
collected module roots behaves the same way. Kotlin constant folding is handled
with the real `R.txt` ID only after the symbol-to-file decision has been made.

Successful target generation publishes used images under
`<output>.resources/base/media/` and copies the provenance manifest to
`<output>.resources/image-resource-origins.json`. Calls remain typed `Resource`
values rendered as `$r('app.media.<deterministic-name>')`. An explicit
`--image-resources` path remains an override for externally prepared assets.

## Direct Vector Reuse

An embedded Python bridge calls the existing pure API directly:

`skills/migrate-android-compose-to-harmony/scripts/convert_android_vector.py`
`convert_vector(Path, color_resources) -> (svg_bytes, metadata)`.

No legacy CLI, safe-snapshot ledger, source parser or page-renderer stage is
invoked. The old script is unchanged. `python3 -B` avoids writing bytecode into
its directory. Production needs Python's standard library, not Pillow.
Reused script SHA-256 at verification:
`0247530d21d9e00a2483bad6f436f0091843c4de4df1eeafc23252515255cb7b`.

The bridge checks `requires_target_tint`, `dynamic_color_tokens` and
`requires_auto_mirroring`. Dynamic theme/tint and automatic mirroring are rejected:
the current properties contract has no consumer for those semantics. Literal
static tint may be baked into SVG by the existing converter. The color map is
empty, so unresolved `@color/` references fail rather than reading guessed
resource overlays. Width/height/viewBox are embedded in SVG; the tool does not
claim Android intrinsic density/layout equivalence for image controls.

## Publication And Integration

Both paths must be absolute; output must be absent and outside the input tree.
All files are first materialized in a fresh sibling staging directory. Only then
does an exclusive `mkdir` claim the output directory. Media is published first,
the complete properties file last. Ordinary failures clean staging and owned
partial output and return nonzero. This is not a single atomic directory swap:
a process crash may leave an incomplete directory, which must not be treated as
success. Existing output, including an empty directory or symlink, is never
reused or overwritten.

Pass the resulting properties file to the backend's `--image-resources` option.
The backend publishes consumed media under `<output>.resources/base/media/`
after successful target validation. Dynamic resource-ID lookup includes every
entry in its supplied ID map, because any may be passed at runtime. Direct
symbol calls include only their used images.
**The tool does not automatically modify the target project.** Copy the emitted
media files to the target module's
`src/main/resources/base/media/` (typically `entry/src/main/resources/base/media/`),
preserving exact filenames. The properties and optional ID map stay adjacent to the original
`media/` directory for the backend reader's existence validation.

## Focused Evidence

Run from `tools/kotlin-ets`:

```sh
node tests/resources/run.mjs
```

The independent fixture decoder requires test-only Pillow. All bitmap inputs are
fixed synthetic one-pixel assets; vector fixtures are authored local shapes.
No company/user assets or network requests are involved.

Final GREEN: `tests/resources/.work/run-v6BLTo/complete.json`.
It verifies PNG/JPG/JPEG/WebP exact bytes and actual pixel decoding, vector SVG
geometry/color, deterministic names, namespace separation, project drawable and
mipmap inputs, raw SVG, variant overlay provenance, unsupported XML/missing
records and 15 direct-materializer rejection boundaries, including failure after
a valid asset has already been staged.
Production SHA-256:
`991a2d5c9b7d07113a3d68a1466d49c70cb1b11f68bf526c28b78a813ec795bf`.

The final run's `res/` contains `drawable/banner.png`, `drawable/second.xml` and
`drawable-nodpi/logo.png`; use namespace `imagecontrols` for the manager's public
compiler fixture. Earlier `run-8XATIu` retains a diagnostic-case assertion failure;
`run-5km0wB` used a subsequently discovered corrupt base64 PNG and is not usable
image-validity evidence. The final replacement assets all decode successfully.
Public Kotlin/SDK integration is owned by the manager and is not claimed passed
by this lightweight test.
