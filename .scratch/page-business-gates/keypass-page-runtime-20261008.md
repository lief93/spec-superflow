# KeyPass 密码生成页：实际实现与模拟器验证

## 最新续作：用户明确先实现、不审查

用户纠正顺序后，未联系 Reviewer，未再等待审查，也未制造 review PASS。使用独立初始化器创建新包 `com.example.keypass.cleanflow`，把同一源版本的已实现业务类、页面事件绑定和测试复用到新空工程。没有调用 UI/业务代码生成器；这不是一次从零独立转写，不把复用描述成新实现能力。工作流本身的14个tracked改动未扩展，也未改门禁来伪造正式流程通过。

- 新目标：`/private/tmp/source-first-25-pages-20261005/harmony-target-keypass-clean-flow`。
- 主包/测试包构建6.448秒/6.383秒，实际安装成功。
- 新包Hypium：17 PASS，0 FAIL/ERROR/IGNORE，24.166秒。
- 原Android业务代码2项instrumentation通过。新包与Android的25个状态检查点、6组DTO解码结果一致，差异为空。
- 两端外部UI各5组通过，包含真实按钮操作和进程重启后的加密配置/密码恢复。
- 新截图与前轮指标一致：SSIM color0.656098/luma0.664569/edges0.712258，严格视觉FAIL；本轮没有调整样式。
- 新证据目录：`/private/tmp/source-first-25-pages-20261005/page-runs/keypass-business-clean-flow-20261008`，详见其中`STATUS.md`。
- 新截图：`/private/tmp/source-first-25-pages-20261005/comparisons/keypass-clean-flow-20261008/side-by-side.png`。

这证明新安装目标的页面实现可运行，且所测业务分支一致；不冒充正常CLI独立审查门禁、全应用或所有并发边界通过。原有通用JSON词法兼容和并发边界限制保留，没有扩大成通用解析器开发。未commit/push。

## 最新：同输入、实际两端执行对照

本轮按用户“试流程做到一致”的要求继续亲自实现、测试；没有派发Dev、提交或推送。不是把两端各自通过的测试当作一致性证明。

### 对照方法与结果

- 隔离Android构建中新增 `BusinessParityTest`，调用未修改的原 `GeneratePasswordViewModel` 和源码依赖 kotlinx-serialization-json 1.8.1。源ViewModel与安全快照SHA256均为 `21770192b7375d3e615d74b4750d1eaab2bdd93cc8d721a1898894d7de6942d2`。
- Android instrumentation 在 `emulator-5554` 实际执行，导出25个状态检查点和6组JSON解码结果；不是重新用Python实现一遍Kotlin预期。对应Harmony测试在 `127.0.0.1:15557` 实际执行同输入。
- `compare_business_traces.py` 比较每步操作、参数、全部8个状态字段以及解码结果/拒绝结果；长度按原Kotlin binary32比较，避免把浮点数最短十进制编码差异当成业务差异。
- 25个状态检查点、6组解码输入最终全部相同。随机生成对照采用单一符号/空格等确定性输入；多字符随机分布不声称逐字符相同。
- 额外在真实Android DataStore 1.1.4执行受控慢写：源码的 `debounce(400).collectLatest` 在旧写入已进入serializer时收到新值，观察到 `pending=[start:11]`，最终 `[start:11, commit:11, start:12, commit:12]`。Harmony真实observer + 受控原生写入端口产生相同事件序列。该证据只覆盖此调度，不冒充所有并发语义证明。
- 最终比较文件：`/private/tmp/source-first-25-pages-20261005/page-runs/keypass-business-20261008-runtime/paired-comparison-delivery.json`，`verdict=pass`，`differences=[]`。

### 真实发现并修正的两处差异

1. Kotlin长度参数先成为Float，然后生成器转Int。原目标直接截断number，使 `10.99999999` 生成10位，源端生成11位。`paired-state-red.log` 保留真实失败；目标回调现在用 `Math.fround` 保留输入边界。
2. Kotlin默认序列化省略 `listOfSymbols`，反序列化补回14符号。原目标 `JSON.parse as PasswordConfig` 不补默认值，也不验证必填字段。`paired-decode-red.log` 保留真实失败；目标DTO适配现补默认值、验证必填/未知字段、保留已实测的引号数字/Boolean接受行为。

没有修改Android业务源码，没有使用ArkUI/Lanhu生成器。改动只在独立目标的对应方法和基准测试中，工作流14个tracked文件的已有改动没有扩展。

### 完整运行验证

- 最终主HAP构建成功，实际安装；测试HAP最终构建5.848秒、实际安装。
- 最终Hypium `hypium-paired-delivery.log`：17 PASS，0 FAIL，0 ERROR，0 IGNORE，23.971秒。
- Android和Harmony外部真实UI操作各5组通过：类别开关、空结果、纯数字生成、符号分支、关闭进程后恢复配置与生成值。日志 `android-ui-paired-final.log` / `harmony-ui-paired-final.log`。
- 剪贴板真实按钮写入及系统读回包含在17项中。受控存储测试与真实AssetStore/UI测试分别记录，不混为同一种证据。
- 本轮还遇到Android测试依赖未缓存、测试缺少显式serialization依赖的问题；仅在隔离构建增加test依赖并成功重建，没有改变业务依赖版本。
- 源码清单：`sha256:8f4b10c14b3c131712ab4ef4510d2219c4be069321fa7c6a76c89e42551aff88`，33文件。
- 主HAP：`c210ab122f4938f276d527dc2418a5dd69bd62380d1e48b3a39e7b530466096d`。
- 测试HAP：`7acc9feda856928d57a84a021054318e717ab457d6fe3bc5886839dea1b19424`。

### 截图与尚未收口的边界

新截图：`/private/tmp/source-first-25-pages-20261005/comparisons/keypass-paired-parity-full-size-20261008/side-by-side.png`。与上一轮相同1080×2145内容归一化：color0.656098 / luma0.664569 / edges0.712258，严格视觉FAIL，没有冒充视觉改善。额外377×750诊断图保留，但其分数不与全尺寸历史分数比较。

现有业务artifacts已更新为17场景；实际collection与288区段来源绑定通过。独立源码审查尚未执行，正式source/target门禁未通过，也未伪造签署证据。因此这是已执行并修正的**页面业务一致性试验**，不是source gate→target gate全流程最终验收通过。

完整Kotlin JSON词法兼容（如裸数字Char）仍不宣称；Android加密文件互通、其它UserSettings/账户/备份不在此独立页面范围。异常/取消的任意交错也不由一个慢写调度证明。上述限制不改变本轮已实测25状态、6解码及1写入调度的一致结果。

## 本轮续作：流程与业务实现串联

本轮继续由主 Agent 实现，没有派发 Dev、没有启动独立 Review、没有 commit/push。
下面“上一轮记录”保留原始失败和旧包身份；本节为当前状态。

### 流程侧

- 现有页面 CLI 本来就会拦住缺少业务规格的输入；没有发现需要再叠加一个状态机的证据。
- `references/source-page-workflow.md` 补齐业务链执行方法及入口图：读源码 → 作者填写现有业务 inventory/contract → 现有 source gate → 同名方法/状态转写 → 场景执行 → 现有 target gate。使用 skill-creator 做的是窄范围说明修正，不引入额外文档/DSL/生成器。
- KeyPass 新增实际 `behavior-source-inventory.v1.json` 和 `behavior-contract.v2.json`，位于 `/private/tmp/source-first-25-pages-20261005/page-runs/keypass-business-20261008-prepare/`。15组作者填写的源码事实、6个动作、15个场景绑定288个源码区段。`author_business_artifacts.py` 只为这些明确填写的事实补锚点/哈希/引用，不推导业务含义、不生成目标代码、不制造审查。
- 真实 source validator：collection/provenance 和 source closure 均 PASS，当前唯一 source gate 错误为缺少独立语义审查。**这不是 source gate PASS，也不是业务100%。** 未制造 review 文件或 evidence_runner 身份。
- 本轮独立复跑6个页面CLI门禁回归：缺业务输入、有效source材料、缺target映射、缺场景证据、有效已签署证据、过期/错误运行身份，6/6 PASS，35.448秒。日志 `workflow-gates-six.log`。
- Skill quick_validate PASS（系统Python3.9已有PyYAML）；Python3.14/3.13缺PyYAML的失败保留，不安装新依赖。`git diff --check` PASS，staged为空。

### 实现侧

沿用已有同名 `GeneratePasswordViewModel` / `PasswordGenerator`，只补平台生命周期适配与缺省配置：

- `PasswordConfigObserver` 承接源码两条独立scope任务。读异常向上传递；存储任务失败后该订阅停止，不在下次状态变化时偷偷重试。
- 销毁时取消待触发的400ms保存、忽略迟到读取；原生已提交写入不能撤销，明确保留此边界。
- 串行提交原生保存，忽略过时待提交状态，防止旧慢写覆盖新状态。
- 无存储记录也发布默认配置，保留源端 `firstOrNull() ?: UserSettings()` 的行为，包括覆盖读取期间发生的新编辑；没有把这个源端竞态“优化”掉。
- 页面不再靠 `@Watch` 和只记录日志的catch维持假成功，直接订阅对应业务状态。
- 复制生产代码无需读取剪贴板权限。原失败来自测试读回条件不足：仅测试module声明 READ_PASTEBOARD，并通过系统原生可见“本次使用允许”授权，实际按钮复制的文本及标签读回均通过。未修改系统安全策略或生产module权限。

### 验证与失败记录

- 两个源码反例先RED：缺省读取未覆盖状态、慢写并发。`hypium-source-negative-red.log` 为6项中2 FAIL；修复后对应测试通过。
- 15项Hypium完整回归已通过（`hypium-source-final-r2.log`：15 PASS、0 FAIL、0 ERROR、0 IGNORE，23.913秒）。包括真实控件顺序/显隐/只读输入、真实复制读回、原有业务分支、以及6项异步/存储边界测试。重新构建的最终包又安装并执行，`hypium-delivery.log` 同为15 PASS、0 FAIL、0 ERROR、0 IGNORE，24.129秒。
- 两端外部UI驱动各5组通过，包括关闭进程重新启动恢复配置/密码。Harmony：`harmony-interactions-source-final.log`；Android：`android-interactions-start-wait.log`。
- Android此前失败日志未覆盖：uiautomator可能exit0但没有新XML，旧临时驱动读了旧文件。本轮驱动拒绝旧XML、对采集作最多3次有界重试（不重复业务点击），并使用 `am start -W` 等待Activity启动。Android业务源码未改。
- 一次测试曾14 PASS/1 ERROR且OHOS_REPORT_CODE为0；没有因此报通过。错误来自只读输入探针结束后遗留焦点/IME，修正测试清理后完整15项通过。
- 额外存储解码探针发现，Kotlin JSON真实接受引号内Boolean/数字，甚至单个数字Char；不能把“更严格JSON检查”冒充源码语义。探针用源码依赖版本 serialization1.8.1 + Kotlin stdlib2.0.21（`DecodeProbe.java`、`kotlin-json-characterization.log`）。探索性严格解码代码/不正确断言未并入当前候选。当前 `JSON.parse` 读取仍不等价于Kotlin完整类型解码，此项在contract的数据映射中明确为partial，不算通过。

原始日志均在 `/private/tmp/source-first-25-pages-20261005/page-runs/keypass-business-20261008-runtime/`。

### 当前身份与截图

- 目标源码manifest：`sha256:7d5ad5ca27f02660fad71cc2a19f8934a10d54bf1098577518566531670d5748`（32文件）。
- 最终主HAP：`ad73d2b151daddb1f53e207a6d8352aa9556011016c9f6c72dde586542b9480b`。
- 最终测试HAP：`143286ebf1e4e9e5bfd8b56bc79ad0c3335909534a1a8352a15e3f82711d14e9`。
- 最新两端同一initial状态截图：`/private/tmp/source-first-25-pages-20261005/comparisons/keypass-business-source-final-20261008/side-by-side.png`。
- 本地对比SSIM color0.656098/luma0.664569/edges0.712258，严格FAIL，与上一轮相同；本轮没有调整UI样式、阈值或图片。采集metadata不是UI代码生成器，也没有将图片交给模型识别。

### 尚未完成的验收

1. 独立源码语义复核和随后可接纳的target gate执行证据；当前原始测试日志不是签署门禁材料。
2. 原生已提交写入的取消边界；当前测试证明最后写入顺序，不证明任意DataStore/AssetStore取消语义等价。
3. 异常/遗留序列化数据的完整类型解码兼容，及原Android加密文件互通（后者原本不在独立页面范围）。
4. 视觉严格验收仍FAIL；不能用业务测试通过替代。

因此本轮是补齐业务规格、修正页面并跑出可追溯验证，**不是已完成 source gate→target gate 的全流程最终验收**。

## 上一轮记录

## 本轮做了什么

不是又一轮工作流门禁开发，也不是新生成另一个页面。沿用已有的 KeyPass ArkUI 页面，主 Agent 亲自补齐源码对应的业务实现和真实页面测试。没有调用 UI 代码生成器，没有派发 Dev，没有提交或推送。

Android 安全源码基线：`ca9adca05c5a73bd854e4dec52cf46415602514f`。
选定入口：`GeneratePasswordScreen`，独立 `GeneratePasswordActivity` 宿主。
目标：`/private/tmp/source-first-25-pages-20261005/harmony-target-keypass`。

## 源码与目标对应

| Android 源码行为 | 本轮目标实现 | 验证 |
| --- | --- | --- |
| `PasswordConfig.Initial` 的长度10、五类别true、14符号、空密码 | `GeneratePasswordViewModel.viewState` | Hypium 初值断言 |
| `PasswordGenerator.generatePassword` 先选类别、再选字符 | 同名 ArkTS 类与方法，保留分类顺序和长度截断 | 各类别、4.9→4、256、全关闭 |
| 空符号列表 `.random()` 抛错，不发布生成结果 | 不再静默忽略该字符；抛错且旧状态不变 | Hypium 负路径 |
| `selectSymbolForPassword` 的 All→单选、追加、移除、最后一项→All | 同名 ViewModel 方法，原有分支顺序 | Hypium + 两端实际 UI |
| 六个长度/勾选回调仅更新各自字段 | 同名 `onPasswordLengthSliderChange` / `on*CheckedChange` 方法 | 字段保留和真实点击 |
| `StateFlow` 对相等 data class/list 不重复发布 | `replaceState` 比较所有字段及有序列表 | 相同值不触发回调 |
| `retrieveSavedPasswordConfig` 整体替换状态 | 页面生命周期 adapter 读取 AssetStore 后 `replaceState` | 关闭进程后重新启动恢复配置与生成值 |
| `debounce(400)` 保存 | 页面 adapter 保留400ms延迟 | 页面操作后读取实际加密存储；进程重启 |
| copy 的文本和 `random_password` 标签 | PasteData 文本 + tag；成功后资源字符串 Toast | 数据对象检查通过；系统读回探针失败，尚不能关闭复制验收 |

业务类在 `entry/src/main/ets/model/PasswordGenerator.ets`、`GeneratePasswordViewModel.ets`。
页面 `entry/src/main/ets/pages/Index.ets` 的控件事件直接绑定这些业务方法。
存储继续使用 `PasswordConfigStore.ets`，没有明文配置替代加密。

## 实测结果

- 主 HAP ArkTS/SDK build 成功（5.498秒）；测试 HAP 最终 build 成功（6.040秒）。
- 两个 HAP 在 `127.0.0.1:15557` HarmonyKitPhone 模拟器安装成功。当前模拟器接受 unsigned HAP；没有修改签名校验设置，不宣称这是签名发布包。
- 最终 Hypium：8项，7 PASS、1 FAIL、0 skip，11.690秒。`aa test` 进程返回0但报告 `OHOS_REPORT_CODE=-1`，因此整体测试不是 PASS。
- 失败项 `clipboardRuntimeRoundTrip`：测试直接写入固定文本，读取的记录数仍为0；数据对象内文本和tag操作成功。延长等待和异步record读取都未消除失败。尚未证明权限/模拟器具体根因，也未证明实际复制端到端成功；没有扩大生产权限绕过。
- Android `emulator-5554` 上实际点击验证：关闭全部类别→空，纯数字10位，配置/密码重启恢复，符号选择/追加/移除及最后符号重置，checkbox本体点击；最后恢复全选空密码。
- Harmony 外部UI驱动独立验证相同主要场景，含真实进程重启恢复。
- 设备仅为两个模拟器；没有操作真机。

原始日志目录：`/private/tmp/source-first-25-pages-20261005/page-runs/keypass-business-20261008-runtime`。
最终 Hypium：`hypium-final.log`；Android：`android-interactions-r1.log`；Harmony：`harmony-interactions-final.log`。

## 不能声称已完成的部分

1. 当前是这一页可运行实现和分支测试，不是 KeyPass 整应用迁移，更不是25页完成。
2. 用户要求先实现、暂不审查；没有伪造独立 source review。正式 `behavior-contract.v2` 逐条映射和独立复核尚未完成，source/target正式门禁没有通过。上述原始测试日志不冒充 evidence_runner 签署的门禁证据。
3. 288个 census obligations 是覆盖台账，不是288项业务功能；本轮不报“业务100%”。
4. AssetStore 是密码配置的加密适配，不兼容原 Android AES-CBC 文件格式；源应用其它 UserSettings/账号、认证、备份、Dashboard导航不在此独立页面验证中。
5. 异步存储失败处理、进行中的写入取消、复杂生命周期竞态尚未与 Kotlin DataStore/collectLatest 做完整等价验证。现有页面 adapter 的错误日志处理与源端无局部catch不同，不能将正常路径通过扩展为失败路径等价。
6. 没有将视觉比较阈值降低，也没有把 UI 结构采集成功当成视觉 PASS。截图采用本轮真实运行结果，状态栏差异按实测 Insets 处理。

## 候选绑定

- 主 HAP SHA256：`478be53fd42676977f2f81a76125b83f4f44641bdaac2b292b9ee1904b2b7c0e`
- 测试 HAP SHA256：`e67ff2f8bceaa57eb4852ebe133fda06f9c38bce77d740077861c5f1468f331d`
- 目标源码manifest：`sha256:4bad0173bcfa1b1525f1613bde48c3be238da458819837a6b3b99b8fc3b8cf02`

工作流仓库原有14个tracked文件的未提交改动保留；本轮页面实现位于上述独立目标项目。staged为空。

## 本轮截图

Android：`/private/tmp/source-first-25-pages-20261005/android-captures/keypass-business-20261008-insets/screenshot.png`

Harmony：`/private/tmp/source-first-25-pages-20261005/harmony-captures/keypass-business-20261008/screenshot.png`

并排图：`/private/tmp/source-first-25-pages-20261005/comparisons/keypass-business-20261008/side-by-side.png`

原始系统窗口事实：Android 顶部107px、底部69px；Harmony 顶部136px、底部98px。Android现有采集器没有识别新格式的InsetsSource文本，本轮使用实测值的显式参数重新生成页面快照，没有改截图像素或伪造运行期字段，也未扩大本轮去改采集器。

比较：SSIM color **0.656098**，luma **0.664569**，edges **0.712258**，严格结论 **FAIL**。组件映射、几何、样式和viewport检查均未通过；不能称高还原度验收通过。这轮重点是业务方法和真实交互，未重新调优UI样式；不将与旧截图的指标差异解释成视觉改善。

比较报告SHA256：`ff6ae33d838a1ebb8ded1d16e86c8e3da52c7fae116372db432dd3a68831313c`。
