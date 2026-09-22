# Pinned Platform Sources

Official Google Maven source archives, read outside dependency caches:

- https://dl.google.com/dl/android/maven2/androidx/compose/material3/material3-android/1.3.2/material3-android-1.3.2-sources.jar
  SHA256 `e58d105a4fcf1f65a6b2838ca8a6fe40b5784b5dba9ddcf27aabcdfc92b3e4e2`.
- https://dl.google.com/dl/android/maven2/androidx/compose/ui/ui-android/1.8.1/ui-android-1.8.1-sources.jar
  SHA256 `2f3467c129ffbf2ca55d727ec23836cefc9415bc8e7bf70ca7da88b63b376ac5`.
- https://dl.google.com/dl/android/maven2/androidx/compose/ui/ui-text-android/1.8.1/ui-text-android-1.8.1-sources.jar
  SHA256 `85e428d1a35935daf78d940a64d6f91964349a4dcd9619c5fd251c36b0e7a7a7`.

## Typography

Material3 `MaterialTheme.kt` supplies `typography.bodyLarge`. `Button.kt`
supplies `typography.labelLarge` through `ProvideContentColorTextStyle`.
`Text.kt` merges explicit arguments with the inherited style, so overriding
fontSize does not discard lineHeight, fontWeight, or letterSpacing.
`tokens/TypeScaleTokens.kt` defines bodyLarge as 16sp/24sp, weight400, tracking0.5sp;
labelLarge is 14sp/20sp, weight500, tracking0.1sp.
`tokens/TypographyTokens.kt` sets centered line-height alignment and no trimming.
The two-argument LineHeightStyle uses Mode.Fixed. Android
`TextLayout.android.kt#getLineHeightPaddings` adds outer first/last-line padding
when the requested line height is below font ascent/descent. This is not the same
as increasing every line's height or using Mode.Minimum for multiline text.

The page host starts with default Material3 typography. MaterialTheme overrides,
Button label style, and ProvideTextStyle scopes travel in the typed material
context. Source builders and WrappedBuilder slots consume the context supplied at
their invocation site, so the same builder may run under multiple text styles.
ArkUI lineHeight/halfLeading must additionally pass native geometry verification;
matching source tokens alone is not proof of identical platform font metrics.

## Touch

Compose UI `platform/ViewConfiguration.kt` defines minimumTouchTargetSize as
48dp square. `node/NodeCoordinator.kt`, calculateMinimumTouchTargetPadding and
distanceInMinimumTouchTarget, expand each undersized axis symmetrically and
compare squared distance to the nominal pointer rectangle. Direct hits win.
`node/HitTestResult.kt` keeps the nearer candidate, not simply the last sibling.
Thus padding outside a clickable paint layer remains separate layout/paint, but
does not imply that touch input in that padding is ignored. Native expanded
response regions alone do not prove correct overlapping-sibling arbitration.
