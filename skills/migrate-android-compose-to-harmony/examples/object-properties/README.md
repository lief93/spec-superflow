# 通用对象属性 Adapter 示例

这里继续使用 `KeyedResourceAdapter(kind='object')`，没有新增 TextStyle 专用 adapter。
`project_adapters.py` 是可加载的完整示例；测试直接加载该文件，不维护另一份示例副本。

## 只按消费类型接管表达式

不需要对象映射时，使用 `consumer_adapters.py`。它不注册 Token 名称，也不声明对象属性。
生成器从 `fontSize` 的原生参数契约获得 TextUnit，从 `color` 获得 Color；在常量、上下文、
源码求值之后，把仍未解析的表达式及期望类型交给相应 adapter。无需动态代理。

```kotlin
fun captionSize() = company.theme.Dimensions.body
fun captionColor() = company.theme.Colors.body

Text("A", style = TextStyle(fontSize = captionSize(), color = captionColor()))
```

即使 helper/getter 未显式写返回类型，已知的消费类型也会传到其返回表达式。
adapter 看到的是 `company.theme.Dimensions.body` 和 `company.theme.Colors.body`，
分别生成 `.fontSize(ProjectTypography.fontSize('body'))` 和 `.fontColor(ProjectTypography.color('body'))`。
`reference.source_type/expression/source_file/reason` 提供兜底调用的类型和诊断上下文。
参数先按源码绑定求值，不会只根据参数名称猜类型。

自定义业务对象也走相同的入口：接收参数的完整类型对应 `kind='object'` adapter 的
`source_type`，返回目标对象引用即可，不要求生成器认识这个结构体。
已有明确值不会为了匹配消费类型而强制走 adapter；已知类型错误保留诊断，视觉默认值不算修复源类型。
显式 tokenMappings 的优先级高于类型兜底，`None` 继续尝试其他同类型 adapter。

这是统一分发，不是所有原生 API 都已支持。动态 padding、部分边框及运行时颜色继承的消费覆盖
仍需补充；泛型/函数签名也不属于目前的命名对象类型支持范围。

## 约定

- `source_type`：Android 对象的完整类型名。
- `target_type`：鸿蒙导出的目标类型，由实际编译检查是否与业务组件兼容。
- 返回的 `target`：整体传递这个对象时使用的属性或方法。
- 返回的 `properties`：以 **Android 属性名** 为键，值是对应的鸿蒙类型、单位及属性/方法引用。
  不需要两端字段同名，也不会通过 `color` 等字段名猜值类型。
- `properties` 可包含另一个 `kind='object'` 描述及其 `properties`，用于嵌套对象。
- 未声明的成员保持 unresolved；`None` 表示 adapter 不处理这个表达式。

例如任意业务对象都可以声明下面的映射，不限于 TextStyle：

```python
return {
    'key': key,
    'target': {'module': './ButtonStyles', 'export': 'ButtonStyles', 'member': 'active'},
    'properties': {
        'loadingTint': {
            'kind': 'color',
            'target': {'module': './ButtonStyles', 'export': 'ButtonStyles',
                       'member': 'active.spinnerColor'},
        },
        'iconSize': {
            'kind': 'dimension', 'sourceUnit': 'dp', 'targetUnit': 'vp',
            'target': {'module': './ButtonStyles', 'export': 'ButtonStyles',
                       'member': 'active.icon.size'},
        },
    },
}
```

声明此 adapter 时将 `source_type` 和 `target_type` 换成自己的业务类型。
源码实际读取 `style.loadingTint` 时才选择该成员映射。
整体对象仍可以传给明确映射的业务组件，不需要生成器拆解其实现。

## 按 Owner 匹配整个 Token 家族

示例只注册 `company.theme.TypographyTokens.*`。`resolve()` 用 `rpartition('.')`
分离 owner 和成员名，检查完整 owner 后以成员名作为 key，不枚举 body/title 等 Token。
显式 import 和 import 别名会解析为完整符号；source getter/函数/参数沿已有源码求值链传递。
没有解析证据时不会把 `tokens.xxx` 的变量名当成所属类型，也不会从成员名推断库 key。
也可将 symbols 设为 `()`，只使用已知 `source_type` 下的默认兜底分发。
显式 owner 注册会直接接管该 owner；仅需正常源码解析失败后接管时使用空 symbols。

Android 示例：

```kotlin
import company.theme.TypographyTokens as Tokens

Text("Body", style = Tokens.body)
Text("Title", style = Tokens.title, fontSize = 20.sp)
Text("Property", fontSize = Tokens.body.fontSize)
```

鸿蒙示例输出（import 别名由生成器分配）：

```ts
Text('Body')
  .fontSize(StyleToken0.fontSize('body'))
  .fontWeight(StyleToken0.fontWeight('body'))
  .fontColor(StyleToken0.color('body'))
  .lineHeight(StyleToken0.lineHeight('body'))
```

`ProjectTypography.ets` 展示如何从自定义结构 `size/weight/foreground/height` 取值。
它的示例数据和默认值仅用于演示；实际项目应接公司的鸿蒙样式库。
两端 key 不同时由桥接层转换。多级属性路径可直接使用 `member: 'body.metrics.size'`；
`getStyle(key).size` 这种先调用后取属性的操作仍放在桥接方法里，不填写原始代码字符串。

## 原生消费者边界

普通业务属性按照源码的成员读取映射。`Text(style = ...)` 则由 Compose Text 的框架规则
消费 TextStyle 的 `fontSize/fontWeight/color/fontFamily/lineHeight/letterSpacing`，分别校验类型和单位。
源码 `copy(...)` 覆盖基础 style，Text 显式单项参数再覆盖 style。
其他 TextStyle 属性若没有受支持的目标映射仍会报告，不会伪装成全部还原。
任意对象的属性映射不等于任意原生组件/任意属性消费都已支持；尺寸、回调、泛型等仍受现有边界约束。

## 接入与验证

1. 将 `project_adapters.py` 放到项目 extensions 目录，修改 owner、类型和桥接目标。
2. 把 `ProjectTypography.ets` 或自己的桥接模块放到生成文件可导入的位置。
3. 按 [adapter manifest 文档](../../references/project-api-adapters.md) 登记文件和 SHA256，
   使用现有 `--api-adapters` 参数生成 Lanhu JSON。修改 Python 后同步更新 SHA256。
4. 重新生成 Lanhu JSON 后再生成 ArkTS；后端仍只读取一个 JSON，不执行 Python adapter。
   如果旧 contract 缺少 getter/参数类型或源码定义，需要先重新分析生成 contract/source-page。

在 skill 的 scripts 目录执行：

```sh
python3 -m unittest test_object_property_adapter test_object_resource_adapter -q
```

测试覆盖 owner/别名、任意字段名、嵌套对象、跨 getter/函数传递、属性覆盖、整对象复用、
未匹配与非法映射。编译成功不代表 Android/Harmony 的字体度量与视觉效果完全相同。
