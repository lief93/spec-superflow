# Compose Pager Mapping

The normal page command maps Foundation `HorizontalPager` and `VerticalPager` to
ArkUI `Swiper`. No pager-specific flag or extra backend input is needed. Regenerate
old source/page JSON: a mapping-catalog entry alone did not previously render pages.

## Data Flow

1. `frontend/api_adapters/pager.py` evaluates `rememberPagerState` through the shared
   PSI argument/value context, including named and trailing page-count lambdas.
2. `frontend/pager.py` resolves the initial page, count, spacing, padding and alignment.
   Fixed-state projection binds the lambda's page index and expands each page's children.
3. `source.pager` in the single Lanhu JSON retains ordered page-root groups. Two
   sibling children in one source page remain one target page, not two slides.
4. `contracts/pager.py` validates types, ranges and the complete child inventory.
5. `arkui/pager.py` emits native `Swiper` and renders every page through the existing
   component/style pipeline. It never reopens Kotlin source or reads runtime bounds.

## Current Boundary

Supported: finite resolved counts up to 200, initial index, `PageSize.Fill`, horizontal
or vertical direction, nonnegative page spacing, `PaddingValues`, cross-axis alignment,
and `userScrollEnabled`. No implicit autoplay, infinite loop or pager dots are added.
Swiper owns native gesture-driven page changes; Android business observers and coroutine
calls such as `animateScrollToPage` are not migrated by this UI mapping.

Unknown count retains a deferred template and reports incomplete generation. Invalid
indices/counts, fractional initial offsets, reverse layout, fixed/custom page sizes,
custom fling/snap/nested-scroll behavior are explicit unresolved boundaries. Known page
content may still be generated for preview, but must not be reported as fully equivalent.
The 200-page bound is diagnosed, not silently sampled or truncated.

## Tests

Run `python3 -m unittest test_pager -q` from `scripts/`. Tests cover single-JSON-only
generation after source deletion, page text/index expansion, multiple roots per page,
vertical and disabled pagers, variable/named lambda values, unknown/unsupported modes,
and malformed page groups. Native verification must additionally swipe forward/back,
verify disabled swipes, and measure page padding/spacing against the Android fixture.
Code generation tests alone do not establish visual equivalence or gesture behavior.

Framework references: [Compose Pager](https://developer.android.com/develop/ui/compose/layouts/pager)
and [ArkUI Swiper](https://developer.huawei.com/consumer/en/doc/harmonyos-references-V5/ts-container-swiper-V5).
