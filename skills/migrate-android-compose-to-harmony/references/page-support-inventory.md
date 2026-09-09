# 单输入页面生成器：控件与属性核对表

统计口径：当前入口接纳 **39 个 Android 控件类型名称 + 3 个内部类型**，不是 42 个完整框架组件。
每个节点有 **66 个样式字段槽位 + 4 个结构字段**。槽位允许 null；不代表每个控件适用全部字段，
也不代表 Android SDK 的全部参数、重载、默认主题、修饰符顺序都已经支持。
下表的属性数量按适用顶层字段计算，含条件/证据/未支持项；圆角四角等嵌套字段不重复计数。
项目业务组件保持展开后的独立组件树，不作为固定原生控件种类计数。

## 每个控件

| 控件 | 适用属性数（含4结构字段） | 已实现 | 条件 | 近似 | 元数据 | 业务边界 | 未支持 | 范围 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `Row` | 30 | 8 | 19 | 1 | 1 | 1 | 0 | 原生 Row；LazyRow 为展开后的滚动树，不包含惰性复用策略 |
| `LazyRow` | 30 | 8 | 19 | 1 | 1 | 1 | 0 | 原生 Row；LazyRow 为展开后的滚动树，不包含惰性复用策略 |
| `Column` | 30 | 8 | 19 | 1 | 1 | 1 | 0 | 原生 Column；LazyColumn 为展开后的滚动树 |
| `LazyColumn` | 30 | 8 | 19 | 1 | 1 | 1 | 0 | 原生 Column；LazyColumn 为展开后的滚动树 |
| `Card` | 28 | 8 | 17 | 1 | 1 | 1 | 0 | Material Card 的 Column 内容布局、静态填充/圆角/裁剪；非零 elevation 仍需单独验证，不能删除子树 |
| `Box` | 29 | 8 | 18 | 1 | 1 | 1 | 0 | Stack + 原有子树；BoxWithConstraints 限已解析约束表达式 |
| `BoxWithConstraints` | 29 | 8 | 18 | 1 | 1 | 1 | 0 | Stack + 原有子树；BoxWithConstraints 限已解析约束表达式 |
| `Surface` | 29 | 8 | 18 | 1 | 1 | 1 | 0 | Stack + 原有子树；BoxWithConstraints 限已解析约束表达式 |
| `AnimatedVisibility` | 29 | 8 | 18 | 1 | 1 | 1 | 0 | Stack + 原有子树；BoxWithConstraints 限已解析约束表达式 |
| `PullToRefreshBox` | 32 | 8 | 21 | 1 | 1 | 1 | 0 | Box 内容子树、尺寸、weight、对齐，刷新指示器叠加而不挤动内容；固定 UI 状态，手势回调与自定义 indicator/state 另行接入 |
| `ConstraintLayout` | 28 | 8 | 17 | 1 | 1 | 1 | 0 | RelativeContainer；只接受已实现的 anchor 关系，不猜坐标 |
| `TopAppBar` | 29 | 8 | 18 | 1 | 1 | 1 | 0 | 当前小型栏骨架；导航/actions slot 和复杂 appbar 默认样式未全覆盖 |
| `CenterAlignedTopAppBar` | 29 | 8 | 18 | 1 | 1 | 1 | 0 | 当前小型栏骨架；导航/actions slot 和复杂 appbar 默认样式未全覆盖 |
| `Scaffold` | 28 | 8 | 17 | 1 | 1 | 1 | 0 | 保留 topBar/content/bottomBar 槽位；内容 padding 消费原生测量栏高；浮动按钮/snackbar 定位未覆盖 |
| `Button` | 30 | 8 | 19 | 1 | 1 | 1 | 0 | 已解析外观 + 子树；不能宣称完整 Material 默认主题/状态/业务 |
| `TextButton` | 30 | 8 | 19 | 1 | 1 | 1 | 0 | 已解析外观 + 子树；不能宣称完整 Material 默认主题/状态/业务 |
| `OutlinedButton` | 30 | 8 | 19 | 1 | 1 | 1 | 0 | 已解析外观 + 子树；不能宣称完整 Material 默认主题/状态/业务 |
| `IconButton` | 30 | 8 | 19 | 1 | 1 | 1 | 0 | 已解析外观 + 子树；不能宣称完整 Material 默认主题/状态/业务 |
| `FloatingActionButton` | 30 | 8 | 19 | 1 | 1 | 1 | 0 | 已解析外观 + 子树；不能宣称完整 Material 默认主题/状态/业务 |
| `SmallFloatingActionButton` | 30 | 8 | 19 | 1 | 1 | 1 | 0 | 已解析外观 + 子树；不能宣称完整 Material 默认主题/状态/业务 |
| `Text` | 43 | 12 | 27 | 1 | 1 | 1 | 1 | 原生文字；ClickableText 仅 UI，富文本/点击范围未全覆盖 |
| `BasicText` | 43 | 12 | 27 | 1 | 1 | 1 | 1 | 原生文字；ClickableText 仅 UI，富文本/点击范围未全覆盖 |
| `ClickableText` | 43 | 12 | 27 | 1 | 1 | 1 | 1 | 原生文字；ClickableText 仅 UI，富文本/点击范围未全覆盖 |
| `BasicTextField` | 48 | 13 | 31 | 1 | 1 | 1 | 1 | TextInput/TextArea、密码/只读/键盘；Material decoration/复杂 slot/label/error 仍需专门映射 |
| `TextField` | 48 | 13 | 31 | 1 | 1 | 1 | 1 | TextInput/TextArea、密码/只读/键盘；Material decoration/复杂 slot/label/error 仍需专门映射 |
| `OutlinedTextField` | 48 | 13 | 31 | 1 | 1 | 1 | 1 | TextInput/TextArea、密码/只读/键盘；Material decoration/复杂 slot/label/error 仍需专门映射 |
| `Image` | 36 | 8 | 22 | 1 | 2 | 1 | 2 | 原生 Image；资源/本征测量受验证门禁约束 |
| `Icon` | 36 | 8 | 22 | 1 | 2 | 1 | 2 | 原生 Image；资源/本征测量受验证门禁约束 |
| `AsyncImage` | 36 | 8 | 22 | 1 | 2 | 1 | 2 | 原生 Image；资源/本征测量受验证门禁约束 |
| `Spacer` | 28 | 8 | 17 | 1 | 1 | 1 | 0 | Blank 或空 Stack，随父容器与 weight 选择 |
| `Checkbox` | 30 | 8 | 19 | 1 | 1 | 1 | 0 | 原生 Checkbox/Toggle/Radio 状态；完整 Material colors/slots 未支持，不能宣称默认外观跨平台等价 |
| `Switch` | 30 | 8 | 19 | 1 | 1 | 1 | 0 | 原生 Checkbox/Toggle/Radio 状态；完整 Material colors/slots 未支持，不能宣称默认外观跨平台等价 |
| `RadioButton` | 30 | 8 | 19 | 1 | 1 | 1 | 0 | 原生 Checkbox/Toggle/Radio 状态；完整 Material colors/slots 未支持，不能宣称默认外观跨平台等价 |
| `Slider` | 32 | 8 | 21 | 1 | 1 | 1 | 0 | 明确数值/范围/离散步数的原生 Slider；连续型和自定义 thumb/track 阻断 |
| `LinearProgressIndicator` | 34 | 8 | 23 | 1 | 1 | 1 | 0 | 确定值的 Linear/Ring 进度；不把不确定进度变为固定0或演示百分比 |
| `CircularProgressIndicator` | 34 | 8 | 23 | 1 | 1 | 1 | 0 | 确定值的 Linear/Ring 进度；不把不确定进度变为固定0或演示百分比 |
| `Divider` | 30 | 8 | 19 | 1 | 1 | 1 | 0 | 原生水平/垂直分隔线；颜色与粗细直接消费 |
| `HorizontalDivider` | 30 | 8 | 19 | 1 | 1 | 1 | 0 | 原生水平/垂直分隔线；颜色与粗细直接消费 |
| `VerticalDivider` | 30 | 8 | 19 | 1 | 1 | 1 | 0 | 原生水平/垂直分隔线；颜色与粗细直接消费 |
| `content` | 28 | 8 | 17 | 1 | 1 | 1 | 0 | 内部结构或已结构化 ProgressRing，不计入 Android 控件数量 |
| `toolbar` | 28 | 8 | 17 | 1 | 1 | 1 | 0 | 内部结构或已结构化 ProgressRing，不计入 Android 控件数量 |
| `ProgressRing` | 28 | 8 | 17 | 1 | 1 | 1 | 0 | 内部结构或已结构化 ProgressRing，不计入 Android 控件数量 |

## 逐属性核对

生成路径：`static_style_for_call` 提取源码，`project_source_page` 解析页面状态，
`lanhu_layer` 保留完整 `migration.style`；不能仅凭原始蓝湖字段中有 frame 就推定全部样式已经消费。
“已实现”限表中明确的值域；“条件”要满足源端与目标端边界；“未支持”非默认值必须失败。
业务点击不属于仅 UI 渲染保证，已明确单列，不能用此表替代 behavior contract。

| 字段 | 适用类别 | 首要阶段 | 状态 | 源码生成/支持边界 | 目标消费逻辑 |
| --- | --- | --- | --- | --- | --- |
| `layout.padding_dp` | all | measure | 条件 | expand_ordered_layout_modifiers 保留纯常量 padding/size/width/height 嵌套；交织绘制/重复同轴尺寸阻断 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `layout.margin_dp` | all | layout | 条件 | 运行测量/页面事实；Compose 没有通用 margin 参数 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `layout.layout_direction` | all | layout | 条件 | 页面事实；CompositionLocal 的上下文解析未全覆盖 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `layout.z_index` | all | draw | 条件 | zIndex 走 layoutRules；该字段来自运行/页面事实 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `layout.alignment` | row column box refresh appbar | layout | 条件 | contentAlignment/horizontalAlignment/verticalAlignment; 枚举 | [page_snapshot_container_alignment_lines](../scripts/ui_migration/arkui/layout.py#L602) |
| `layout.horizontal_arrangement` | row | layout | 条件 | Arrangement + 常量 spacedBy | [page_snapshot_container_alignment_lines](../scripts/ui_migration/arkui/layout.py#L602) |
| `layout.vertical_arrangement` | column | layout | 条件 | Arrangement + 常量 spacedBy | [page_snapshot_container_alignment_lines](../scripts/ui_migration/arkui/layout.py#L602) |
| `layout.aspect_ratio` | all | measure | 已实现 | aspectRatio 常量；不猜动态表达式 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `layout.width_dp` | all | measure | 条件 | width/size; 无显式值使用原生测量，不用参考 frame | [page_snapshot_dimension_lines](../scripts/ui_migration/arkui/layout.py#L147) |
| `layout.height_dp` | all | measure | 条件 | height/size; 无显式值使用原生测量，不用参考 frame | [page_snapshot_dimension_lines](../scripts/ui_migration/arkui/layout.py#L147) |
| `surface.background` | all | draw | 条件 | solid/null、水平/垂直 Clamp 渐变；未知端点/径向/图片背景阻断 | [SurfaceEmitter.emit](../scripts/ui_migration/arkui/surface.py#L13) |
| `surface.corner_radius_dp` | all | draw | 条件 | 四角事实；AbsoluteRoundedCornerShape、统一圆角；方向未知的非对称 Start/End 阻断 | [SurfaceEmitter.emit](../scripts/ui_migration/arkui/surface.py#L13) |
| `surface.corner_sizes` | all | draw | 条件 | 带单位四角：dp/px/percent；百分比依赖原生测量的较短边；方向未知的非对称 Start/End 未解析 | [SurfaceEmitter.emit](../scripts/ui_migration/arkui/surface.py#L13) |
| `surface.border` | all | draw | 条件 | 统一 solid/dashed/dotted/none；单边、自定义 dash 阻断 | [SurfaceEmitter.emit](../scripts/ui_migration/arkui/surface.py#L13) |
| `surface.shadows` | all | draw | 近似 | 单阴影且 spread=0；Android elevation 转换仍是近似；多阴影阻断 | [SurfaceEmitter.emit](../scripts/ui_migration/arkui/surface.py#L13) |
| `surface.alpha` | all | draw | 已实现 | alpha 常量 0..1 | [SurfaceEmitter.emit](../scripts/ui_migration/arkui/surface.py#L13) |
| `surface.clip` | all | draw | 条件 | 矩形/圆角；自定义 Path 未支持 | [SurfaceEmitter.emit](../scripts/ui_migration/arkui/surface.py#L13) |
| `typography.font_size_sp` | text input | measure | 条件 | Text/TextStyle 常量或已解析主题；字体缩放由运行平台消费 | [TypographyEmitter.emit](../scripts/ui_migration/arkui/typography.py#L15) |
| `typography.font_weight` | text input | measure | 条件 | FontWeight 常量/已解析主题 | [TypographyEmitter.emit](../scripts/ui_migration/arkui/typography.py#L15) |
| `typography.font_style` | text input | measure | 已实现 | FontStyle.Normal/Italic; 未知值 unresolved | [TypographyEmitter.emit](../scripts/ui_migration/arkui/typography.py#L15) |
| `typography.font_family` | text input | measure | 条件 | 仅已校验字体资产或声明的系统字体 | [TypographyEmitter.emit](../scripts/ui_migration/arkui/typography.py#L15) |
| `typography.letter_spacing_sp` | text input | measure | 已实现 | letterSpacing 常量 sp；支持负数 | [TypographyEmitter.emit](../scripts/ui_migration/arkui/typography.py#L15) |
| `typography.line_height_sp` | text input | measure | 条件 | 常量/主题；自定义 LineHeightStyle、低于自然行高未证明等价 | [TypographyEmitter.emit](../scripts/ui_migration/arkui/typography.py#L15) |
| `typography.text_align` | text input | layout | 已实现 | Start/Center/End/Justify | [TypographyEmitter.emit](../scripts/ui_migration/arkui/typography.py#L15) |
| `typography.max_lines` | text input | measure | 条件 | 正整数；TextInput 与多行 TextArea 不是同一控件 | [TypographyEmitter.emit](../scripts/ui_migration/arkui/typography.py#L15) |
| `typography.overflow` | text input | measure | 条件 | clip/ellipsis；visible 未支持并阻断；两类 ArkUI 签名分开 | [TypographyEmitter.emit](../scripts/ui_migration/arkui/typography.py#L15) |
| `typography.color` | text input button | draw | 条件 | 明确颜色或已解析主题；容器颜色需实际下传到文字 | [TypographyEmitter.emit](../scripts/ui_migration/arkui/typography.py#L15) |
| `typography.decoration` | text input | draw | 已实现 | none/underline/line_through | [TypographyEmitter.emit](../scripts/ui_migration/arkui/typography.py#L15) |
| `asset.resource` | image | draw | 条件 | 本地资源或 AsyncImage HTTP(S)；无预览图回退 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `asset.sha256` | image | draw | 证据 | 资源提取记录；格式转换后由资源 provenance 验证，不是绘制属性 | [build_target_phase_consumption_gate](../scripts/ui_migration/contracts/consumption.py#L39) |
| `asset.width_px` | image | draw | 未支持 | 可记录源像素尺寸；单输入渲染必须有逻辑尺寸，不能直接按 px 布局 | [build_target_phase_consumption_gate](../scripts/ui_migration/contracts/consumption.py#L39) |
| `asset.height_px` | image | draw | 未支持 | 可记录源像素尺寸；不能当作 dp 使用 | [build_target_phase_consumption_gate](../scripts/ui_migration/contracts/consumption.py#L39) |
| `asset.width_dp` | image | measure | 条件 | 资源本征尺寸，不是控件硬宽度 | [page_snapshot_intrinsic_image_lines](../scripts/ui_migration/arkui/layout.py#L229) |
| `asset.height_dp` | image | measure | 条件 | 资源本征尺寸，不是控件硬高度 | [page_snapshot_intrinsic_image_lines](../scripts/ui_migration/arkui/layout.py#L229) |
| `asset.content_scale` | image | draw | 条件 | fit/crop/fill/inside/none; 未指定尺寸时需可验证本征测量 | [page_snapshot_intrinsic_image_lines](../scripts/ui_migration/arkui/layout.py#L229) / [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `asset.tint` | image | draw | 条件 | 显式 tint/ColorFilter.tint；仅支持当前颜色滤镜映射 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `transform.translation_x_dp` | all | draw | 条件 | 运行/页面事实；源码 offset 单独走 layoutRules，混合变换阻断 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `transform.translation_y_dp` | all | draw | 条件 | 运行/页面事实；源码 offset 单独走 layoutRules，混合变换阻断 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `transform.scale_x` | all | draw | 条件 | scale 常量；graphicsLayer/自定义原点/顺序组合未支持 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `transform.scale_y` | all | draw | 条件 | scale 常量；不推算未知表达式 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `transform.rotation_degrees` | all | draw | 条件 | rotate 常量；默认中心原点 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `state.visible` | all | draw | 条件 | 显式布尔页面状态；消失不占位，不等于完整动画状态机 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `state.refreshing` | refresh | draw | 条件 | isRefreshing 固定布尔状态；Box 叠加原生 LoadingProgress，动画外观近似，不包含刷新业务回调 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `state.enabled` | all | draw | 已实现 | 显式布尔优先于默认值；动态未知值不填 true | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `state.selected` | selection | draw | 条件 | RadioButton 的明确选中态；不代表任意容器都有选中样式 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `state.checked` | selection | draw | 条件 | Checkbox/Switch 的明确布尔状态；缺失或动态未解析阻断 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `state.clickable` | all | draw | 业务边界 | 只记录入口元数据；UI 渲染不产生业务 onClick，另走 behavior contract | [build_target_phase_consumption_gate](../scripts/ui_migration/contracts/consumption.py#L39) |
| `content.text` | text input button | measure | 条件 | text/value/已解析资源；Button 文本在子 Text 实际消费 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `content.placeholder` | input | measure | 条件 | 纯文字提示；复杂 slot/浮动 label 不等同 placeholder | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `content.content_description` | all | draw | 已实现 | contentDescription; 显式 null 不设置 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `content.role` | all | draw | 证据 | 用于页面语义匹配，不代表已实现对应业务 | [build_target_phase_consumption_gate](../scripts/ui_migration/contracts/consumption.py#L39) |
| `content.locale` | text input | draw | 未支持 | 可存储/采集；未单独消费，非空时阻断 | [build_target_phase_consumption_gate](../scripts/ui_migration/contracts/consumption.py#L39) |
| `input.single_line` | input | measure | 已实现 | 显式布尔；源码省略按 Compose 多行默认；TextInput/TextArea 原生分流 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `input.read_only` | input | draw | 条件 | 显式布尔；禁止软键盘及内容修改，保留选中；API 20+ | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `input.password` | input | draw | 条件 | 标准 PasswordVisualTransformation/None；多行密码、自定义字符变换阻断 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `input.keyboard_type` | input | draw | 条件 | Text/Number/Phone/Email/Uri/Decimal/Password/NumberPassword；不等同内容校验 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `input.ime_action` | input | draw | 条件 | 键盘动作枚举；Previous/单行 None 阻断；业务提交回调另走 contract | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `typography.soft_wrap` | text | measure | 条件 | 显式布尔；false 支持不含硬换行的单段文字，硬换行逐段渲染未支持 | [TypographyEmitter.emit](../scripts/ui_migration/arkui/typography.py#L15) |
| `typography.min_lines` | text input | measure | 条件 | 1 为原生默认；多行 Text 使用已验证字体运行时 metrics，复杂约束/输入框多行最低行数阻断 | [TypographyEmitter.emit](../scripts/ui_migration/arkui/typography.py#L15) |
| `control.value` | range progress | draw | 条件 | 明确 value/progress；不使用样例数值；UI 当前态不等同业务订阅 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `control.minimum` | range progress | draw | 条件 | Slider valueRange 或明确默认 0；进度固定 0..1 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `control.maximum` | range progress | draw | 条件 | Slider valueRange 或明确默认 1；上限必须大于下限 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `control.steps` | range | draw | 条件 | 离散 steps 转 (max-min)/(steps+1)；连续型与小于平台最小步长阻断 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `control.active_color` | progress divider refresh | draw | 条件 | 显式 color 常量或刷新指示器主题色，作用于轨迹/分隔线而非文字 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `control.inactive_color` | progress refresh | draw | 条件 | 显式 trackColor 常量或刷新指示器主题背景 | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |
| `control.stroke_width_dp` | progress divider | draw | 条件 | 常量 thickness/strokeWidth；分隔线默认1dp | [page_snapshot_component_lines](../scripts/ui_migration/arkui/renderer.py#L305) |

## 结构与布局操作

| 项目 | 生成逻辑 | 消费逻辑 | 边界 |
| --- | --- | --- | --- |
| type/parent/children/sibling | SourceTree + lanhu_layer | page_snapshot_component_lines | 对应同一实例；不靠全屏坐标重建父子 |
| fillMaxWidth/Height/Size、matchParentSize、wrapContentWidth/Height/Size | normalized_layout_rules | page_snapshot_dimension_lines | 常量比例；不支持的组合失败 |
| width/height IntrinsicSize | normalized_layout_rules | page_snapshot_dimension_lines | 保留原生内容测量；不估算文字宽度 |
| widthIn/heightIn/sizeIn | normalized_layout_rules | constraintSize | 四个边界逐值使用目标密度取整 |
| weight | normalized_layout_rules | page_snapshot_source_layout_weight | 仅 Row/Column，fill=false 失败 |
| align/constrainAs | normalized_layout_rules + SourceLayout relationships | alignSelf/align/alignRules | 不支持关系失败，不回退绝对布局 |
| offset | normalized_layout_rules | page_snapshot_explicit_offset_line | 常量支持；parent_fraction 当前仍依赖参考父尺寸，不能宣称响应式等价 |
| verticalScroll/horizontalScroll | normalized_layout_rules | Scroll + 原生流式子树 | 不等价于完整 Lazy 虚拟化 |
| zIndex | normalized_layout_rules | zIndex | 数值常量 |
| scale/rotate | static_style_for_call + required facts | scale/rotate | 中心原点常量；graphicsLayer/顺序组合未支持 |
| 重复padding/size与padding顺序 | expand_ordered_layout_modifiers | 原生嵌套 Box + 原组件 | 常量纯布局链；交织绘制/重复同轴尺寸仍 unresolved |

## 已补的缺口与未完成边界

- 已补：fontStyle、letterSpacing 入口采集、输入 value/placeholder、enabled/visible、contentDescription、scale/rotate/translation、tint。
- 已修：蓝湖 paint.isEnabled 覆盖 Android enabled、TextInput overflow 签名、空 Row/Column 类型、约束像素取整。
- 已阻断：多阴影/非零spread、自定义dash/单边border、选中/checked真值、已识别但无映射的原生参数。
- 本轮补齐：输入单/多行、只读、密码与键盘动作；水平/垂直 Clamp 渐变；绝对四角圆角；纯布局修饰符嵌套。
- 仍有限制：非轴向/径向渐变、复杂输入框装饰、框架默认样式、动态/多重变换、资源像素到逻辑尺寸、locale。
- 阴影近似、文字行高/字体边界仍需真机像素校验，不能因有 emitter 宣称等价。

## 代码与验证入口

- [static_style_for_call](../scripts/ui_migration/frontend/styles.py#L15)
- [project_source_page](../scripts/ui_migration/frontend/fixed_state.py#L135)
- [lanhu_layer](../scripts/ui_migration/frontend/lanhu_export.py#L220)
- [build_required_facts](../scripts/component_required_facts.py#L580)
- [build_target_phase_consumption_gate](../scripts/ui_migration/contracts/consumption.py#L39)
- `test_page_property_coverage.py`：源值→JSON→生成代码、负路径、25类共享属性、目录与schema闭合。
- `test_layout_mapping_contract.py`：布局/字体/资源/measure与layout关系专项。
- `test_page_input_surface.py` / `test_ordered_layout_wrappers.py`：新增端到端属性、负路径、布局顺序。
- `test_common_page_controls.py`：Kotlin 参数库存、选择状态、离散范围、进度、分隔线、文字、父约束和失败路径。
- 本表不是截图通过证明，必须另外运行同尺寸页面比较。

重建表格：`python3 -B scripts/audit_page_support.py --output references/page-support-inventory.md`
伴随的 CSV 按每个控件×70字段展开，包含不适用项，不把未支持项算作已实现。
