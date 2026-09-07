# Platform capability mappings

Use this table as routing guidance, then confirm APIs against the installed HarmonyOS SDK.

| Android capability | HarmonyOS target | Risk | Required verification |
|---|---|---:|---|
| OkHttp / Ktor / Retrofit | NetworkKit HTTP or approved client | Medium | timeout, retry, headers, TLS, serialization, offline/error behavior |
| Room | RelationalStore or approved ORM | Medium | schema, constraints, transactions, migration, concurrency |
| DataStore / SharedPreferences | Preferences | Low | defaults, types, migration, clearing |
| Navigation Compose | `Navigation` / `NavPathStack` | Medium | arguments, results, deep links, stack/back behavior |
| ViewModel + StateFlow | ArkUI observed state + explicit controller | Medium | lifecycle, cancellation, duplicate collection, restoration |
| Runtime permissions | `abilityAccessCtrl` and module permissions | High | first denial, permanent denial, settings recovery, device policy |
| Activity/Service | UIAbility / ExtensionAbility / background task APIs | High | lifecycle, process death, background limits |
| WorkManager/alarm | Background task/agent APIs | High | timing, quota, reboot, battery policy |
| Bluetooth | ConnectivityKit Bluetooth APIs | High | discovery, permission, pairing, disconnect/reconnect |
| MediaPlayer/AudioTrack | AudioKit / AVSessionKit | High | focus, interruption, routing, background playback |
| Camera / gallery picker | CameraKit / PhotoAccessHelper | High | permissions, URI/file lifetime, cancellation |
| ContentResolver / MediaStore / `java.io.File` | FileKit and user-file APIs | High | sandbox paths, grants, persistence, cleanup |
| Notifications / Firebase messaging | NotificationKit and approved push service | High | token lifecycle, foreground/background routing, channels |
| Glance / AppWidget | FormExtensionAbility and ArkUI Form | High | form metadata, supported dimensions, per-instance data, resize behavior, card actions, launcher placement |
| WebView | Web component | Medium | navigation policy, bridge security, cookies, file access |
| Biometrics | User authentication APIs | High | enrollment changes, fallback, cancellation, lockout |
| Location | LocationKit | High | permission precision, background limits, provider state |

For Glance/AppWidget migration, preserve the provider, receiver lifecycle, exact size breakpoints,
empty/content branches, per-instance cleanup, and every action target. Harmony Form supports a
restricted ArkUI component set. With the API 24 SDK, `Grid`/`GridItem` are not valid in a Form;
translate a two-column Glance grid with supported components such as `List` rows containing paired
items, then compile the actual Form source. A normal entry HAP build that omits the Form metadata or
card source is not Form verification. Treat launcher placement and card-action routing as device
gates.

## Security exceptions

Never preserve these merely for parity:

- trust-all certificate managers or disabled hostname validation;
- request/response logs containing tokens, cookies, PII, or full bodies;
- embedded production API keys;
- broad storage or permission requests unsupported by the actual feature;
- Android filesystem assumptions outside the HarmonyOS sandbox.

Semantic transcription does not authorize reading blocked secrets, copying unsafe credentials,
or bypassing platform/security restrictions. It also does not authorize silently fixing the source
and calling the result equivalent. Record the original observable behavior (without secret data),
the constrained operation, proposed safe replacement, observable differences, decision and proof
in the existing slice ledger and behavior scenarios. Keep the affected parity claim explicitly
non-equivalent/unresolved until the departure is decided; test an approved replacement separately.
If no permitted equivalent exists, report that boundary rather than claiming full transcription.
Ordinary source logic defects outside these restrictions are preserved, not automatically repaired.

## Unsupported capability workflow

1. Name the Android behavior, not only the API.
2. Identify the closest HarmonyOS capability and its OS/API floor.
3. Classify as `equivalent`, `adapted`, `degraded`, or `unsupported`.
4. Document user-visible differences and data migration impact.
5. Add a device proof for equivalent/adapted behavior.
6. Obtain a product decision before shipping degraded or unsupported behavior.

An API-name mapping alone is not semantic equivalence. Apply
[semantic-transcription.md](semantic-transcription.md) to check return/error behavior, state and
effect order, lifecycle, cancellation and data representation at the adapter boundary. An
`adapted` classification documents a substitution; it does not by itself establish parity.
