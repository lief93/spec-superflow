# Four-page source fixture

`Page.kt` is a standalone, non-company Compose program, package `sample`.
The Android host calls `sample.Page()`; the ETS entry and source builder retain
the name `Page`. The fixture uses actual AndroidX dependencies from the official
Kotlin frontend probe's `classpath.json`, not local Compose API stubs.

- Entry: `Page(base: Int = 12, extra: Int = 4)`.
- Ordinary helpers: `Model(title, detail)`, `pageModel(page)`, `buttonLabel(page)`.
- Source builders: `PageFrame(title, content)`, `ContentPanel(spacing, content)`.
- Initial state: page 0; callback count 0; page count 4.
- `pageModel(0..3).title`: Chapter 1, Chapter 2, Chapter 3, Chapter 4.
- Button: Continue on indices 0/1/2; Finish on index 3.
- Action: increment callback count, animate to `(currentPage + 1) % 4`.
- Indicator click: animate to that indicator's index, without changing count.
- Swipe: current page and active indicator change; callback count is unchanged.
- Default computed spacing: `base + extra`, 16dp on Android and 16vp on ArkUI.
- Tags: `pager`, `page-0` through `page-3`, `indicator-0` through `indicator-3`,
  `action-button`, `callback-value`, `computed-spacing`.
- Visible status: `Page N of 4` and `Callback N`.

The fourth-page button must restore Continue after a backward swipe to index 2.
Restart resets both remembered state values. All wrapper content is nonempty.
The verification owner operates hosts/devices and checks fresh artifacts; the UI
tests exercise the official source-to-CLI seam and source-linked rejection.

## Target adaptation boundaries

`ComposeEmitter` keeps `Page`, `PageFrame`, and `ContentPanel` as source-named
`@Builder` methods, retaining their arguments. ArkUI's required `build()` invokes
the source entry with its declared defaults inside a native full-size Stack.
Resolved annotated Unit functions are UI builders; annotated value-returning
functions remain ordinary language helpers, with unsupported runtime reads rejected.
Content parameters use `WrappedBuilder<[]>` and invoke `content.builder()` directly
inside the source parent. No custom component or extra layout surrounds a slot;
multiple roots retain the caller's Column/Row sequence. There is no empty default.

An anonymous source slot becomes a builder named for its receiving function,
parameter, and IR source offset. A source local value becomes a builder parameter
for the following UI statements so its initializer executes once. Necessary
K2 named-argument temporaries retain a bridge if their value can change or their
initializer has effects. A compiler-origin single-use temporary can be aliased
only for a stable value or an immutable stored property with a default accessor.
The main fixture consequently needs only its source `model` value bridge and its
two anonymous slot methods. These are target syntax adaptations, not replacement
source render/preview/context methods.

Independent width/height/paint/tag/click attributes share the native source node.
Layers remain after padding, for repeated attributes, and where a native control's
intrinsic behavior needs a boundary. Constraints propagate into inner layers;
padding outside fixed size remains outside it. The fixture indicator uses its
source Box plus one outer padding Stack. `tests/ui/ModifierOrder.kt` isolates click-before-padding
and click-after-padding. Native geometry and event bounds remain verification
gates in addition to generated hierarchy assertions.

Modifier.clickable is bounded to homogeneous Row/repeat/empty-Box groups with
constant repeat count, fixed constant dp dimensions, enabled targets and symmetric outer padding.
48vp response regions preserve Compose's default minimum touch target without
changing paint or layout bounds. The Row selects the nearest nominal pointer
rectangle using native child positions and exclusive dispatch, rather than letting
overlapping response regions select an arbitrary sibling. Outer synthetic IDs are
dispatch identities; original inner test tags remain unchanged. Unsupported touch
topologies fail closed. Cross-branch expanded-hit competition and custom
ViewConfiguration providers are not covered by this bounded adapter.

The page host's default Material3 1.3.2 typography is an explicit platform
assumption: bodyLarge16/24sp, weight400, tracking0.5sp; Button supplies
labelLarge14/20sp, weight500, tracking0.1sp. Slot styles follow invocation, not
closure creation. Custom text providers and a source builder reached under
conflicting inherited styles fail closed. One typed native Text AttributeModifier
evaluates each source font size once and applies native font-metric first/last-line
leading padding while retaining requested line height. It adds no Builder/layout
node, uses no fixture coordinates, and does not alter normal dp-to-vp conversion.
Button content retains Material's real implicit centered Row, so multiple source
children remain siblings rather than overlapping in ArkUI's native Button.
Pinned source references and native-metric caveats are in tests/ui/PLATFORM-SOURCES.md.

Remembered pager state has a `currentPage` state field and native SwiperController.
The bounded coroutine adapter accepts only a remembered UI scope launching one
`PagerState.animateScrollToPage(page)` call. It uses `changeIndex(page, true)`;
Swiper `onChange` updates the remembered current page. Other coroutine operations
and explicit unsupported arguments produce source-linked errors.
Pager page count currently requires a positive integer literal; dynamic count
captures are rejected rather than emitting an unbound target reference.
