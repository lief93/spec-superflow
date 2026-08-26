# Privacy boundary

## Objective

Prevent original image files, font files, vector artwork, recognized embedded image payloads,
recognized credential literals, and unintended binary files from entering model-visible context
while still allowing local builds to reuse approved assets.

## Allowed model-visible inputs

- Files copied into the safe snapshot by `prepare_safe_snapshot.py`.
- The safe-snapshot manifest.
- The migration contract.
- Asset path, byte count, and SHA-256 metadata.
- Generated HarmonyOS source and generated non-confidential placeholder assets.
- Hashes and field-level metadata emitted by the deterministic Android-vector converter.
- Build and test logs that do not contain secrets or image encodings.

## Forbidden operations

- Open, view, OCR, describe, upload, base64-encode, hex-dump, or print an original image or font.
- Read Android `drawable` or `mipmap` vector XML through model tools.
- Follow a source or snapshot symbolic link.
- Inspect a file excluded as sensitive or blocked.
- Paste image bytes into source, logs, prompts, reports, or data URLs.
- Run broad source-tree reads after the safe snapshot exists.

## Trusted local operations

Deterministic scripts may read image or font bytes only to calculate a hash or perform a
byte-for-byte local copy, and may convert a manifest-approved Android VectorDrawable directly into
a protected target SVG.
They must never print source bytes, XML, `pathData`, or generated SVG bytes. Verify the original
size and SHA-256 immediately before the operation and record the destination hash afterward. Do
not open the converted SVG with model-visible file or image tools; use its conversion ledger and
hash as the model-visible evidence.

The local screenshot comparator is a separate, explicitly authorized diagnostic operation. It may
decode two screenshots through the local Pillow package, normalize caller-selected crops,
calculate numeric similarity metrics and candidate difference coordinates, and write local
difference/annotated/side-by-side PNGs. It must not print pixels, record absolute input paths,
upload data, run OCR, call a model, or start an external image process. Its generated PNGs remain
protected image data subject to the same access boundary as the inputs. The image-processing
channel itself may expose only hashes, dimensions, crops, labels, Pillow version, numeric
metrics/coordinates, and text limitations to model-visible context.

An optional component-bound inventory may expose only strict ASCII component identifiers, generic
component types, an optional sanitized semantic key, and integer bounds. It must reject display
text, accessibility labels, content descriptions, account/customer data, arbitrary metadata, and
dimensions that do not match the bound screenshot. Even sanitized identifiers can reveal business
structure; keep the complete comparison report local unless policy explicitly permits those
identifiers to enter model-visible context.

The vector converter is a narrow semantic transform, not image understanding. It accepts only its
documented VectorDrawable fields, including basic path fill alpha and stroke semantics. It can
resolve literal `@color` values from the validated safe
snapshot, translate the fixed Android platform colors `black`, `white`, and `transparent`, and
preserve one dynamic theme token as `currentColor` plus an explicit target-tint contract. It fails
closed on groups, clips, gradients, selectors, multiple dynamic color tokens,
animation, or other unsupported features. Do not substitute a guessed icon after a conversion
failure; record an explicit unsupported conversion or use an approved local tool.

Treat resource names as hints, not proof of appearance. An agent may map `R.drawable.avatar` to an
opaque asset named `avatar.png`, but may not claim its color, content, or visual quality.
A passed deterministic vector conversion proves only the translated vector fields and hashes
recorded in the ledger; it does not authorize semantic description of the artwork.

## Fail-closed sequence

1. Generate the snapshot into a new directory.
2. Validate the snapshot independently.
3. Analyze only the validated snapshot.
4. Revalidate inside the analyzer and verify every recorded file hash.
5. Reject all symlinks, forbidden generated/metadata directories, image extensions,
   drawable/mipmap XML, non-UTF-8 files, NUL bytes, image data URIs, contiguous Base64 payloads of
   256 or more characters, known credential literals, and known sensitive configuration files.
6. Repeat validation after any snapshot regeneration.

Do not weaken a rule to make intake succeed. Record the excluded file and ask for an approved
textual contract when its behavior is essential.

Pattern scanning cannot mathematically prove that arbitrary source text contains no cleverly
split, escaped, encrypted, or novel image/credential encoding. The manifest records the exact
checks performed instead of asserting an absolute Base64 guarantee. For a hard enterprise
boundary, add repository-native secret scanning/DLP before snapshot generation and expose only the
validated snapshot mount to the model.

## Isolation strength

The scripts implement a strong logical boundary, not an operating-system security boundary. A
model process with unrestricted filesystem access could still bypass the workflow. For enforceable
enterprise isolation, run the model under a separate OS user/container and expose only the safe
snapshot and target through ACLs or a broker. Keep the original repository and asset store outside
that mount.

## Visual verification without AI image access

Use two independent channels:

- Agent evidence: component tree, modifiers, tokens, resources, semantics, navigation, state, and
  opaque asset hashes.
- Human/local evidence: side-by-side visual inspection performed by an authorized person or a
  non-AI local pixel-diff system whose image data never reaches the model.

A local comparison report is diagnostic and non-authoritative. Record the actual human result as
visual-review evidence; do not ask the model to infer it from a score or protected image artifact.
