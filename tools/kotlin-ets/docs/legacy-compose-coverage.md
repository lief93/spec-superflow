# Legacy Compose coverage and backend gaps

Inventory checked on 2026-09-14 against the old Python/JSON implementation,
its support documents, tests and historical project evidence. This is not a
fresh test run or a claim of complete visual/behavioral equivalence.

The initial inventory preceded the image increment. The new backend now has
15 control families: the original [basic controls](compose-basic-controls.md)
and bounded [Image/Icon/AsyncImage rules](compose-images.md).
Recognition of a source name, generated target syntax, SDK compilation and
device equivalence are separate evidence levels.

## Coverage comparison

Paths below are relative to the repository root. The old reference directory is
`skills/migrate-android-compose-to-harmony/references/`; its implementation is
under the adjacent `scripts/ui_migration/` directory.

| Family | Old route | New backend gap | Priority |
| --- | --- | --- | --- |
| Image, Icon, AsyncImage | Native Image for resolved media; bounded HTTP(S) URLs, scaling, tint and intrinsic dimensions. Unresolved media can become a diagnosed empty Stack. | Local Painter resources, explicit tint/scaling and literal URL rules now exist. ImageVector, default tint, qualified/intrinsic sizing and request objects remain gaps. | P0 remaining |
| Row, Column, Box, Spacer | Layout, spacing, alignment and bounded modifier handling. | Basic rules exist; old modifier coverage is not automatically inherited. | P0 shared work |
| Surface, Card, BoxWithConstraints | Surface styling and resolved constraints; elevation remains approximate. | Container rules, theme inheritance and constraint handling. | P0 |
| Scaffold, TopAppBar, CenterAlignedTopAppBar | Bar/content slots and measured bar padding; not all actions or FAB/snackbar placement. | Rules, slots and required runtime measurements. | P0 |
| Text, BasicText, ClickableText | Typography, resources and bounded rich-text handling. | Text/BasicText exist with narrower arguments; resources, styles and rich text remain gaps. | P0 shared work |
| Button variants | Button, TextButton, OutlinedButton, IconButton, FloatingActionButton, SmallFloatingActionButton. Full Material/behavior equivalence not established. | Only basic Button exists; variants and defaults remain. | P0 |
| HorizontalPager, VerticalPager | Native Swiper, finite page groups, spacing, padding and scroll-enabled; old fixed-state mapping does not migrate business observers. | HorizontalPager exists; vertical mode and additional properties remain. Preserve live state in the new route. | P0 follow-up |
| LazyRow, LazyColumn, grids and flow | Expanded scrolling trees, grid tracks and wrapping; not full lazy/recycling semantics. | List/grid/flow rules and runtime iteration semantics. | P1 |
| BasicTextField, TextField, OutlinedTextField | TextInput/TextArea, password, read-only and keyboard options; complex decorations incomplete. | Input rules, state updates and styling. | P1 |
| Checkbox, Switch, RadioButton, Slider | Bounded selection and discrete slider values; incomplete Material defaults. | Checkbox/Switch now exist; RadioButton/Slider and remaining parameters do not. | P1 |
| Progress indicators, dividers | Determinate progress only; native dividers. | Dividers now exist; progress rules remain. A custom progress test rule is not production support. | P1 |
| Dialogs, sheets, menus, tabs and navigation | Separate registered rules with explicit slot/state boundaries. | Rules and corresponding native behavior. | P1/P2 by page demand |
| AnimatedVisibility, PullToRefreshBox, ConstraintLayout | Selected-state rendering, bounded refresh overlay and anchor mappings; not complete animation/gesture support. | Structural and behavioral adaptation, not merely call renaming. | P2 |

P0 prioritizes the onboarding composition described by the user; it is not proof
that these are its only blockers. An actual offline compiler diagnostic inventory
is still needed for that private project.

## Inventory sources

- `references/page-support-inventory.md` lists 39 Android type names and three
  internal types, with explicit per-property limitations. This is a historical
  inventory, not a current total of fully implemented controls.
- `references/registered-controls.md` and `scripts/ui_migration/controls/registry.py`
  cover 19 separately registered controls: Dialog, AlertDialog, ModalBottomSheet,
  DropdownMenu, DropdownMenuItem, ExposedDropdownMenuBox, Tab, TabRow,
  PrimaryTabRow, SecondaryTabRow, NavigationBar, NavigationBarItem,
  NavigationDrawer, NavigationRail, NavigationRailItem, FlowRow,
  ContextualFlowRow, LazyVerticalGrid and LazyVerticalStaggeredGrid.
- `references/pager-mapping.md` documents both pager directions separately.
- Actual image output is in `scripts/ui_migration/arkui/leaves.py`; resource,
  material-icon and intrinsic-size support is in `arkui/resources.py`,
  `arkui/material_icons.py` and `arkui/layout.py`.
- `scripts/test_materialize_compose_icons.py` asserts vector path preservation,
  arc conversion, invalid-command rejection and logical icon dimensions.
  `scripts/test_property_resources.py` includes resource-backed icon tint.
  These are test definitions inspected here, not newly executed results.

## Historical project evidence

- `/tmp/contact-full-regression-20260911-r12/code-fidelity-review.md` records a
  public Banking-App-Mock-Compose contact page. Build/install/capture passed,
  but AsyncImage(imageReq) became an empty Stack and visual acceptance failed.
  Thus this page is a useful regression fixture, not proof of image support.
- `artifacts/dropdown-menu-select-20260824-174331/final-evidence-index.md`
  records generation/builds for PersonalFinanceManager and Ekspensify, and an
  architecture-samples menu device test for open/select/dismiss callbacks.
  Candidates still required review; the latter used visible text instead of
  a resolved icon. Do not generalize this into complete icon/page equivalence.
- `artifacts/ui-program-transcription-manager-20260913/contact-live-acceptance.md`
  is an acceptance checklist explicitly marked in progress, not a passing run.

## Porting order and boundaries

1. Image/resource vertical slice: resolved source resource identity, target
   resource materialization/import, Image/Icon typed rules, dimensions,
   ContentScale and tint, then focused SDK/resource checks. AsyncImage request
   objects, placeholders, errors and network behavior need separate contracts;
   passing a URL alone does not port the image-loading library.
2. Shared visual values and containers: colors, typography, dimensions, ordered
   modifiers, Surface/Card and Scaffold/app-bar slots; then button variants.
3. Lists, input, selection and overlays according to real source diagnostics.

Reuse bounded mapping semantics, resource conversion utilities where separable,
and regression fixtures. Do not route the new compiler through old fixed-state
JSON projection or copy its string-emitting renderer. Each new control keeps its
own rule file and uses the common API adaptation, typed target tree, validator
and printer. Values, calls and callbacks continue through language lowering.
