# Bounded wrap content

The resolved wrapContentWidth/Height/Size APIs introduce a native Stack boundary,
preserve outer sizing and clear the wrapped axis's propagated fill constraint.
No generated custom measurement implementation is needed for this bounded path.
`unbounded=true` retains wrapping, alignment and the remaining modifier chain, but
records that ArkUI native wrap-content measurement replaces Compose's infinite
child constraint. Dynamic booleans and effectful alignment values fail explicitly
instead of changing evaluation order.

Run `node tools/kotlin-ets/tests/ui/wrap-content/run.mjs`, pass Page.ets to
`tests/ui/basic-controls-sdk.mjs`, then pass the resulting HAP to `native.mjs`.
Native assertions check outer80/inner20 dimensions, axis retention, centering,
End alignment and reversed modifier order. Font rendering is not involved.
