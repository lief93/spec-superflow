# 业务迁移流程：当前实现进度

## 2026-10-15 用户调整交付范围：UI 实现＋业务语义转写

本节优先于下方完整业务落地的历史计划。用户明确重点为 UI 高还原、业务完整采集和
语义迁移，业务允许详细伪代码，不要求每个功能真实接通平台服务。

- UI 继续真实构建、安装、合成状态交互和配对截图验收，不能用伪代码替代可见控件/样式。
- 业务逐项对应源方法、条件分支、状态、数据关系、调用顺序及异常；已有实现保留，缺少的
  平台落地可用具名接口与详细伪代码表达。源业务规则不能缩成一句“保存/加载”。
- 在原 dossier 中区分真实代码、伪代码和未解析语义；不新增独立清单，不删除历史失败。
- 业务语义转写完成与运行验证完成分开报告；CLI 门禁含义不变，不把伪代码标记为 runtime PASS。

当前按同一标准核对十页；保留订阅弹窗关闭的 UI 修复，停止为样例追加网络、
存储、后台任务等真实业务集成，不再把十个目标补成完整应用。
未开始独立审查，未提交或推送。

本轮落地：迁移 Skill 与 semantic-transcription 参考增加显式用户选择的伪代码交付说明；
不改 CLI/状态机。Myne 书库/详情在原 dossier 补充导入、下载、取消、落库/回查、分享和
外部阅读的源方法伪代码；ReadYou 阅读补充加载、已读/收藏的不同链路及 DiffMap 语义。
源码核对补出了 null 文件流跳过、非文件流报错、null-only 错误默认值、Kotlin Int 解析、
2 秒 debounce 写缓存而非 DB 等此前概述易混淆的语义。现有运行代码不自动视为全部符合
这些补充语义，真实代码与伪代码分开记录。KeyPass 两页也已补充扫描返回、独立备份任务、
目录授权及 nullable 设置 effect 的源码伪代码。IdeaMemo/OnlyFlows 四页也已完成本轮
所检查业务链的源码核对与伪代码补充：IdeaMemo 编辑 4 链、搜索 6 链；OnlyFlows 补充
复发日期计算、任务转换、关联字段及查询顺序。十页原 dossier 均已按新范围更新。
本轮检查的链路未再留下具体未转写项；这不是任意输入的语义等价证明，也不代表十页 UI 已验收。

已有代码与转写不一致的地方单独保留：例如 IdeaMemo 的旧标签关系、删除后快照刷新、
分享/导出分支，以及 OnlyFlows 的复发 interval/无效 weekday 边界和关联派生标志。
本轮允许用源对应伪代码交付这些语义，因此不继续扩展真实平台实现；未把这些旧代码
改记为等价。后续若交付完整可运行应用，需要按已记录伪代码修正对应实现并验证。

本轮最新 UI 证据（覆盖下方旧表对应行）：KeyPass 05 的 a8126b78 候选原生 6/6，
suite 30.558s，dossier 21/21；ReadYou 08 匹配包原生 7/7，22.932s，重新启动后取得
有效 Web 分支截图 reader-launched-final.png，启动器空树截图不作验收。ReadYou 07
自动全套仍 3/6，立即读取所选偏好值失败，根因未定；另一次直接 UI 操作已确认
点击遮罩外部关闭且显示的选项不变，不冒充全套通过。父 Settings 样式仍未对齐。
本轮收口阶段只修改文档与画廊索引，没有因业务伪代码再发起 SDK 构建或设备测试。

共享检查：VS Code Plugin 24/24，154.355ms；git diff --check 通过，Ruby frontmatter 解析通过。
skill-creator quick_validate 因本机 Python 缺 PyYAML 未运行成功，不记录为 PASS，不安装依赖。

## 2026-10-15：当前十页修复回归（以下旧日期记录为历史）

当前证据根：`/tmp/ten-page-acceptance-20261015-VK6a9i`。本批是已有十个目标的
source-first 修复与回归，不是十页全新首版，不走生成器或 PSI 前置流程。
UI、业务、批量准入分别按迁移 Skill 的 Acceptance and readiness for batch testing 判定。
用户明确业务允许语法和平台机制不同，但不得遗漏源端逻辑；已确认的平台限制及接受的
适配单独记录。截图只证明可见状态，host 用例、原生交互和存储结果分别记录。

当前执行顺序：修复具体失败 → 同一生产路径回归 → 当前 HAP 身份绑定截图 → 逐页验收。
沿用已有 GPT-6-luna 实现者，设备操作串行；未开始独立审查，不提交或推送。

| 页面 | 当前有效证据 | 正在补齐 / 尚未验收 |
| --- | --- | --- |
| 01 IdeaMemo 编辑 | 当前原生 3/3 两轮通过，dossier 10/10，配对编辑页截图 | 保持源范围核对；截图不代表外部接收器均已执行 |
| 02 IdeaMemo 搜索 | 当前原生 2/2，dossier 9/9，源样式图标修复后截图 | 最终与其余页面统一呈现验收结论 |
| 03 OnlyFlows Inbox | 当前 5 个非提醒原生用例均通过：新增保存 13.596s、启动 1.863s、详情修改返回 10.895s、第二数据连接更新 1.875s、移动 3.909s；host 54/54 | 键盘遮挡与重复上移已修复，截图确认操作栏贴合键盘；11 链/53 测试的原基线 dossier 检查通过；提醒配额及外部平台项另列 |
| 04 OnlyFlows TaskDetail | 路由、附件、移动/转换、重复、计时五项原生用例通过；最新 dossier 19/19 | 旧快照路径变化被门禁拒绝，已用原哈希快照重跑通过，基线未变；完整套件曾受 ReminderAgent 配额阻断，不用选中用例冒充全套通过 |
| 05 KeyPass 详情 | ab170f7a/590a7620 滑杆候选原生 6/6，28.414s；显式 host 20/20；此前 QR dossier 17/17 | Canvas 重复缩放已修复，滑杆拖动持久化、备份和 QR 均回归通过；最新截图仍检出刻度色和小值端点绘制差异，继续按实际主题/源 TrackImpl 修正。首轮 Canvas 失败截图及启动等待失败保留；旧 QR 解码 10 字段证据不冒充本轮重新解码 |
| 06 KeyPass 备份 | 原生 1/1，实际数据库/加密/文件路径通过；最新 dossier 6/6，测试进程 0.326s | 私有自动备份＋手动另存为用户已接受的平台适配 |
| 07 ReadYou 订阅 | 6befdef5/f17b8053 弹窗候选原生 6/6，37.988s；host 30/30；新增 v21 源基线保留 v20 全部义务 | 样式设置入口→弹窗选择→持久化→系统 Back→筛选栏真实显示已通过。当前弹窗截图仍有源端内边距/表面色差异，继续小范围修正；父 Settings 页面不宣称整页高还原。早期等待失败仍保留，外部服务及整页验收未关闭 |
| 08 ReadYou 阅读 | 当前设置候选原生 6/6，17.754s；host/dossier 32/32；同文章、时间、作者和正文最新配对已完成 | 设置路由→标题/子标题大写→系统 Back→实际显示/持久化均执行通过。保留测试清理前失败；原生渲染器、外部字体、双栏宿主及外围平台检查仍未关闭，不以 6/6 宣称整页完整 |
| 09 Myne 书库 | 当前原生 5/5，13.426s；dossier 15/15；同主 HAP 新测试包已安装重拍 | 新增实际 EPUB→生产导入→文件/书库→正文读取→删除，3.041s，未替换数据/文件端口；OS 选文件另行打开验证，不冒充连续 picker E2E。空态动画和外部接收器未关闭 |
| 10 Myne 详情 | 当前主/测试 HAP 已安装，完整原生 2/2，4.707s：详情加载、持久化 EPUB→正文→系统 Back；显式 host/dossier 12/12；当前安装包已重拍 book84 | 测试上下文和 monitor 失败已保留后修正。原生证明已持久化文件的阅读链路，不是网络下载；连续下载→文件→DAO→Read 由 host 受控平台端口验证。扩展基线保留原 7 链/18 源范围与全部用例，仅追加链路检查；无简介动画、外部接收器及配对下载证据未关闭 |

这张表是执行进度，不是“十页完整迁移通过”。失败证据保留，不缩小源码基线来变绿。
细节、源定义及真实测试命令沿用各页面 dossier，不新增验收 JSON 或工作流状态。

## 2026-10-13：真实代码接入同一门禁（本轮最新）

证据根：`/tmp/business-dossier-real-pS69s4`，汇总 `summary.json`；可复现命令与断言
在 `run-gates.mjs`（基线不可覆盖，重跑时保留原目录并使用新输出路径）。
没有新迁移一个页面；复用真实修复后的 KeyPass 与仍不完整的 Myne 来验证同一机制。

- KeyPass：独立重新阅读生产 Activity/Screen/VM、控件、设置读写/序列化/加密调用，
  选取14个源定义范围，8条业务链。不纳入共享设置文件的其它功能，也不纳入Compose预览。
  源码基线约1.192s；完整目标检查约1.628s，其中一次测试进程0.431s。
  5组测试执行实际ETS模块/页面控制器，含11条源/目标观察、6个业务holdout、3组存储、
  7组页面、2组控件检查。原Kotlin重新编译6.398s、执行0.133s；未运行PSI或生成器。
- 在隔离的目标源码副本中删除数字开关真实状态更新：源码引用仍有效，parity与page测试失败，
  目标门禁exit1。不修改原目标、源端、期望结果或已有证据。
- 在dossier副本删除整条Persist：source阶段报未覆盖加密/序列化/存储源码，target阶段
  报源基线丢失Persist；均exit1，不能通过删规格绕开未迁移业务。
- Myne：真实Library生产控制器发往不存在的ReaderDestination。旧测试仅观察dispatch，
  本轮在平台路由端口核对实际main_pages与目的源码，执行同一控制器后发现未注册路由；
  page CLI正确exit1，关联Read book链，整个目标检查0.613s（测试0.151s）。
  这是一个真实缺失consumer的负例，不是完整Myne规格采集或迁移完成。

共性小修：两个既有CLI输出`failed_checks`，把实际失败/错误/跳过测试关联到dossier业务链，
便于实现者定位返工。一个共享测试可能关联多条链，此列表是受影响映射，不是根因推断。
未加新门禁、状态、生成器或应用专属规则。公共CLI回归先RED（两入口缺failed_checks），
再GREEN；相关40/40测试10.504s，VS Code Plugin24/24、130.526ms。

边界：上述host测试替换平台机制；没有新SDK构建、模拟器安装/截图、原生HUKS验证。
KeyPass保留此前披露的平台差异；Myne阅读接收端仍缺失，不报业务完成。
新源范围检查是对AI从源码选择的范围对账，不会自动证明遗漏依赖不存在。
本轮确认“已声明且有真实检查的缺失不能被成功报告掩盖”，不把两样例复跑宣称为
十页新迁移或通用语义等价证明。没有设备操作、独立审查、commit或push。

## 2026-10-13：完整性闭环补充（晚于下文的轻量检查版本）

用户纠正：以完整迁移为交付目标，不能只检查目标侧自己填写的清单。已追加：

- 源端先选择真实页面及可达的完整定义范围；dossier 必须覆盖这些范围中的代码行，遗漏报源码位置。
- 源端检查报告保存为基线，后续实现/测试阶段必须提供它。整链删除、规则/源码引用变化、删验收用例、
  源版本改变均失败；已有源基线不能被检查命令覆盖。
- source-first 流程先追到实际数据/平台消费者，后实施；发现缺口继续补实现。发现新的源端规则，
  扩展基线和验收用例后重新核对，不通过删项或缩范围获得 PASS。
- 新增反例验证：初始漏源码方法/数据规则、同时删业务链和测试、无基线、覆盖基线、删除必测用例；
  真实目标入口测试还检出账号过滤遗漏、互斥设置遗漏和移动/清空顺序反转。
- 最新39/39相关测试通过（含15个 dossier CLI 测试），10.110s；Plugin 24/24，129.325ms；diff-check PASS。
  日志为 `/tmp/business-dossier-gate-CmGizb/completeness-final.log` 和 `completeness-plugin.log`。

这些是可复用流程与门禁的实现/反例验证，没有把新真实页面迁移算作已执行，也没有把源码行对账
单独当成语义一致证明。实际项目仍须按源端场景跑通整条链再交付。无设备操作、独立审查、提交或推送。

## 2026-10-13：直接 dossier 路径的可执行检查

本轮已接通两个既有 CLI 的 `--dossier` 模式，共用 `validate_business_dossier.py`；
迁移 Skill 在源码准备、实现连线后、报告已测行为前调用 source / implementation / target
检查。这些是校验阶段，不是新工作流状态。不创建 Contract、PSI 分析、生成器输出或额外业务 JSON。
实现仍由 AI 读源码完成；dossier 保持一份四列表。可核对真实代码范围，并实际执行一次项目测试，
要求已列测试全部出现且通过。源码过期、缺引用/实现文件、缺结果、跳过/失败测试、执行中修改
引用代码均失败；占位实现、断开调用、丢弃结果的变体被同一真实行为测试拒绝。

本轮验证：
- 新增10个公共 CLI 测试（含多个负例）；最新直接检查/业务相关34测试通过，7.451s。
- 较广95测试通过，270.050s（含当时已有6个直接检查，后补4个由上项覆盖）。
- VS Code Plugin 24/24，123.984ms；diff-check、Ruby frontmatter 通过；staged 为空。
- 较广首次94测试有45失败，原因为本进程未配置 Kotlin PSI classpath；使用本机已有
  Gradle JAR 的临时环境变量后通过。没有安装依赖、改全局配置或调整 PSI 产品实现。
- 官方 Skill quick_validate 因本机缺少 PyYAML 未运行成功，不计为通过。
- 日志：`/tmp/business-dossier-gate-CmGizb/{regression,direct-and-business,plugin}.log`。

本轮边界：检查声明的引用和用例结果，不推断完整调用图、不证明自定义测试运行器诚实，
也不能自动发现 dossier 中从未列出的业务链。实际语义仍由 source-first 对照和源端派生断言
验证。直接检查不设置 `business_verified` / `runtime_complete`，不替代 native/视觉门禁。
本轮没有新迁移页面、设备操作、独立审查、commit 或 push；不将该门禁实现等同于全部业务迁移验收。

## 当前结论

**当前完成共享实现与集成回归，整体交付尚未完成。** 下面的总计划是当前执行顺序；历史分节中的阶段“收口”不代表全部完成。样例页面的最终业务/视觉验收与流程实现分开报告。

## 总计划与唯一完成标准（2026-10-09 用户纠正后）

交付对象：其它项目可直接使用的业务迁移 Skill + 既有 CLI 门禁串联，而不是某个样例的
完整产品重写。实现由本任务直接进行，先实现和验证，再冻结供固定独立 Reviewer 审查；
不在实现中反复派发审查，不擅自提交或推送。

| 顺序 | 工作 | 验收依据 | 当前状态 |
| --- | --- | --- | --- |
| 1 | 固定流程输入、输出和范围 | 页面真实业务链、源码仍可读、复用 behavior-contract.v2，不走生成器 | 已完成 |
| 2 | 实现可复用 Skill 与 CLI 串联 | 同一入口贯通范围/规格、AI 转写交接、目标映射、当前执行证据与完成判定 | 已实现 |
| 3 | 验证共享逻辑与失败关闭 | 公共 CLI 正负路径、旧证据/缺映射/伪目标被拒绝，相关147测试通过 | 已完成 |
| 4 | 用既有真实项目验证同一流程可复用 | OnlyFlows Tags 与 IdeaMemo Locations 按同一入口整理源范围→事实→目标→场景→门禁结果，区分已运行证据和待补项；不靠手工改状态 | 真实入口已复跑；未通过，具体阻塞见文末 |
| 5 | 修复步骤4暴露的共享缺陷并冻结交付 | 仅修共享流程缺陷并重跑相关测试；给出改动清单、调用方式、两份验收结果与限制 | 待步骤4 |

步骤4复用已经实现的两页，不扩展新页面、整个平台库适配或无关功能。已有日志先核对
身份和覆盖；确需补跑时只补缺失的受支持场景，不重复已有效验证的全部设备动作。
样例业务差异与共享流程缺陷分开记录；不能用增加一个样例功能冒充完成一个流程步骤。
独立源码审查未完成时，正式 source/target PASS 保持 pending，不伪造 review 或 evidence。

停止标准：步骤1–5完成，剩余项明确只属于冻结后的独立审查/授权交付；若遇确实需要用户
选择或外部环境恢复的阻塞，给出具体阻塞及已经尝试的措施。单项测试变绿、文档写完或
样例新增一个业务分支均不是整体停点。进度按上述步骤更新，不再不断生成新的收尾计划。
没有新建/调用 Dev 或 Reviewer，没有伪造独立审查或 evidence_runner 门禁记录。

主仓库仍为 page-scoped-migration-closure，HEAD 9d3ca4136e53e07d0a99a048face51087c728d84。
早期页面实现和原始测试放在独立临时工程；后续通用 Skill、CLI 和测试改动见下方按时间排列的增量。
git diff --check 通过。未commit/push。

## 实际进展（不是业务覆盖百分比）

| 项目/页面 | 新增成果 | 仍未完成 |
| --- | --- | --- |
| KeyPass 密码生成 | 上轮已有17项Hypium、25状态检查点和6个DTO配对结果、真实UI及重启恢复 | 复用已有目标实现，不算本轮新转写；完整取消/失败调度等价、正式门禁仍未通过 |
| OnlyFlows Tags | 本轮新转写；修复“同ID编辑落库但行未刷新”；8个真实Room/RdbStore配对检查点；两端实际新增/取消/编辑/删除/批量删除通过；Android重启持久化通过；已有有效并排截图 | 配置LAN peer的同步未迁移；正式source/target门禁未通过；严格视觉gate FAIL；扫描范围扩散 |
| IdeaMemo LocationList | 本轮新转写；原查询/清除SQL和调用链；4个真实数据库配对检查点完全相等；鸿蒙业务+UI 2/2通过 | Android完整UI采集遇30s超时；鸿蒙后续重启/截图命令阻塞；最终配对截图及正式source/target门禁未通过 |

## 流程中发现的实际问题

1. **可观察UI也是业务结果。** OnlyFlows重启前旧行、重启后新行的反例说明仅比较ViewModel/数据库不够。目标列表render key补充name/color，业务id保持不变；原UI回归从RED到GREEN。不要将此页局部修复说成所有框架适配均已解决。
2. **业务扫描仍过宽。** OnlyFlows有效闭包中的business census包含199文件、670顶层定义、1332边；源因是audit_behavior_source按整个顶层class递归，OnlyFlowsApp/AppContainer把应用级初始化和旁支也带入。闭包是约1MiB，仍有requires_source_resolution。不能把这些计数说成真实业务功能数，也不能无依据删除依赖来假造完整覆盖。需要围绕页面实际调用和已存在的注入对象明确范围，保留必要初始化/外部边界。
3. **已生成闭包不等于正常流程完成。** 两个新增页目前是源码驱动的独立实现验证，还没有完整经业务规格映射→正式source gate→target evidence gate闭环。用户暂不审查，不能造一份review.json绕过该事实。
4. **环境与产品失败分开。** Earlier OnlyFlows capture Kotlin PSI OOM保留；单文件、完整index和新的两端capture成功，未稳定复现，所以没有改heap/timeout/parser。之后主机高负载期间Android uiautomator 30s超时、HDC重启命令不返回；未关闭其它用户应用或改变模拟器安全设置。

## 下一步顺序与完成标准

1. 在设备响应恢复后，从现有IdeaMemo fixture继续取消/确认/导航/重启路径，采集两端相同状态截图；不要重新初始化或清空已测试数据库。
2. 修复页面业务范围扩散：先用包含共享DI容器、页面专用repository和无关旁支的小反例固定边界，再验证真实Tags。保留真实调用、状态、必要初始化和副作用；不做逐API生成器适配，不无证据排除源码。
3. 将真实页业务分支/源码/目标方法/执行结果整理进已有behavior-contract.v2结构，跑正常CLI路径；独立审查尚未进行时，明确保持相应门禁pending。
4. 完成判据：流程实现与当前源码范围一致；新增页面有真实源/目标行为对照和配对截图；缺失分支不会被标成完成；无生成器替代AI转写。代码/测试/evidence齐备后再报告可审查候选，不抢先commit/push。

## 证据入口

- OnlyFlows：/private/tmp/source-first-25-pages-20261005/page-runs/onlyflows-tags-business-20261008/STATUS.md
- OnlyFlows配对图：/private/tmp/source-first-25-pages-20261005/comparisons/onlyflows-tags-after-bulk-r2/side-by-side.png
- 旧OnlyFlows launcher误采图已标INVALID；.333398不能用于还原度结论。
- IdeaMemo：/private/tmp/source-first-25-pages-20261005/page-runs/ideamemo-locations-business-20261008/STATUS.md
- IdeaMemo目标：/private/tmp/source-first-25-pages-20261005/harmony-target-ideamemo-locations
- IdeaMemo源端临时工程：/tmp/ideamemo-location-android-mZsKUO

## 已测试HAP身份

- OnlyFlows主包：9f6155216d812df1d9f92e04bddb88320949d704b46154952750f947bfdef792
- IdeaMemo主包：c0a94be8bdfdff47619d01d7a0e9ec085ae7a87dcf90f64a422e1a8de16e458a
- IdeaMemo测试包：ab160829e1a20ebce327b4655e477678bfd3d3cafff4189832bedaf6285da5aa

## 继续实现后的增量（同日，覆盖上方旧设备阻塞状态）

- 未派发任何开发/审查，未修改冻结副本，未commit/push。设备恢复响应后，继续原数据库而非重建环境。
- IdeaMemo Android取消、确认、导航参数、重启持久化四组真实UI验证通过。两端Tokyo/Hidden配对截图已补齐；像素SSIM约.923，严格视觉仍FAIL，不能宣称整页完成。
- 继续追源码发现标题Back遗漏：Android无上一页时仅警告，目标错误退出应用。Android原页实测确认；Harmony RED 1失败，修正原生路由栈guard后GREEN 1通过。
- 目标原先仅在原页面切换detail文字，不是原生导航。新增平台路由栈测试RED（1不等于2），改成真实pushUrl传递location到明确的测试host目的页；GREEN 2/2（栈1→2→1、参数、root Back）。没有假装已实现LocationDetail业务。
- 两端继续“导航返回后清除Tokyo”均通过，Harmony 1/1 4.486秒；列表仍接收数据库变化。当前两端只剩Hidden。最终配对采集为capture-after-native-return-r2；第一次误遇launcher被树断言拒绝并标INVALID，没有用于对比。
- 已编写真实页的现有business inventory/contract：6动作、3状态、13事实、7场景、7个hash-bound源码锚点。事实结构/引用无缺项，但collection仍pending、范围绑定/独立审查和异常时序仍未闭合，正常source门禁退出1；未造review或签名运行证据。
- 主仓库新增compare_behavior_traces.py及其CLI测试，并在现有source-page-workflow引用：比较真实源/目标JSON记录的值、类型、数组/记录顺序和预定数量，拒绝空/截断/重复JSON字段等。不会运行测试或把trace equality标成business_verified。OnlyFlows现存原始日志8条一致，IdeaMemo4条一致；不是重新执行旧业务测试。
- TDD：新CLI缺失时RED；初版类型/重复键/非有限值/非对象四个负路径RED；修正后两个测试方法含10个负子例GREEN。
- 回归：compare_behavior_traces + page_commands + behavior_contract_v2 + behavior_collection + behavior_source_closure + effective_page_closure + existing_target + source_dependencies，110/110，130.875秒。evidence_runner及4个既有project编排用例32/32，9.228秒。git diff --check通过，staged为空。

### 未擅自改变的门禁设计

范围扩散不是简单解析bug：当前既有census明确以整个被引用class为分母。把它直接裁成页面调用链会改变门禁定义，不能用排除表或伪造映射悄悄通过。已向用户提出一次异步设计选择：建议AI追踪真实页面业务链，CLI检验源码/目标/实测引用；DI/应用初始化作阅读上下文，后续独立Review判断边界。尚未收到选择，尚未修改census/validator以削减分母，也未另加分析器。

### 当前最新IdeaMemo包

- main: 11dd7211962bd08aae33a9575abf21ae067d474d4ade135c7354a8346c49ecba
- test: 2f6511d728bcb9cee78d8e04b8a6cf7b0fd7479356fa78209cb72770660fea6a
- 正常构建与模拟器安装通过；最新包的导航/返回后更新实测通过，旧四条全字段数据库trace仍标注为先前包证据，没有冒称整套fresh重跑。

## 2026-10-09 用户批准页面业务范围后：实现与验证

用户回复“修改”，已批准上一节待定方案，覆盖“尚未收到选择”的旧状态。
本轮自行实现，未派发开发/审查，未更改冻结副本、Android/Harmony实现或设备数据库。

- 在既有 `behavior-source-scope.v1` 中增加可选 `definition_boundaries`：AI读取源码后
  指明完整业务行范围、DI实际依赖、阅读上下文理由、未解决事项。不是自动推断成员调用图，
  不是API支持表，不生成业务代码。未指定时保留原保守行为。
- 正常 page CLI 与 closure CLI 接受 `--behavior-source-scope`；除边界外必须与生成的
  页面入口、revision、identity完全相同。原源码文件仍hash-bound；更改范围使旧review失效。
- CLI反例验证：拒绝缩小页面入口、截断方法体、缺失DI目标/未知定义；未知DI仍unresolved；
  已选业务的事实/场景映射缺失仍失败。结构验证不证明AI选中的整组方法已穷尽所有业务，
  这个判断仍由既有独立源码review负责；本轮没有造review文件。
- 真实IdeaMemo暴露已有索引问题：`class VM @Inject constructor`的构造器注解被误算为
  下一个顶层property的起点。新增公共CLI回归先RED后GREEN，修正为声明体内注解不泄漏到后续定义。

### 真实源范围验证（不是运行期验收）

材料目录：`/tmp/page-business-boundaries-20261009-KOjzIs`。
范围JSON由AI阅读真实源码编写，census/closure/validation由现有CLI生成。

| 页面 | 默认文件/定义/语法项 | 选择后文件/定义/语法项 | unresolved |
| --- | --- | --- | --- |
| OnlyFlows Tags | 199 / 670 / 15831 | 41 / 135 / 991 | 5 → 0 |
| IdeaMemo Locations | 22 / 33 / 612 | 10 / 16 / 166 | 0 → 0 |

OnlyFlows仍保留TagRepository、DAO、tombstone、writeTag/writeTombstone、实际enqueue发送链；
不是将同步行为整块排除。App/Container与同步器未调用成员保留阅读上下文。
IdeaMemo保留getAllLocationInfo/clearLocationInfo和原Room SQL、页面回调、导航、返回行为。
未声称这些范围已经独立Review批准。

两页closure CLI均exit0，绑定同一生成页面root。OnlyFlows这次未绑定runtime capture，
仍是`candidate_requires_runtime_facts`；IdeaMemo为`candidate_ready_for_ai`，不是页面验收。
IdeaMemo现有未完成behavior材料在新范围下source validator仍exit1：166项待映射、
collection pending、review缺失等均保留，`source_complete=false/runtime_complete=false`。
本轮没有新的build/install/截图/业务执行证据，不复用旧包证据冒称本轮fresh运行。

### 最终回归

Python `/opt/homebrew/opt/python@3.14/bin/python3.14`，沿用固定JDK17/Kotlin PSI classpath：

```
-m unittest test_compare_behavior_traces test_page_commands test_behavior_contract_v2
test_behavior_collection test_behavior_source_closure test_effective_page_closure
test_existing_target test_source_dependencies test_evidence_runner
```

143/143 PASS，144.171s，exit0。
四个既有编排回归（start、resume identity、tampered snapshot、missing contract）
4/4 PASS，5.066s，exit0。最终合计147/147；没有把中途114测试重复计入。
`git diff --check` PASS。staged为空，未commit/push。

## 2026-10-09 继续自行实现：IdeaMemo 双端业务闭环

本轮材料：`/tmp/ideamemo-business-completion-20261009-hFXSjn/RESULTS.md`。
没有派发 Dev/Reviewer，没有修改冻结副本或原 Android snapshot；主仓库产品代码沿用上节
147/147 回归版本。本轮补业务工件、临时 Android host 测试和 Harmony 目标实现/测试。

- 继续读取 App 既有 context、LocationDetail route 和同名 getString 的真实 receiver 后，
  scope 保留 10 个完整阅读文件、65 个页面业务 obligation；65/65 结构映射完整、27 个事实。
  scope 选择尚未独立 Review，不以减少数字证明语义完整。
- 原 Android VM/Room 与 Harmony VM/RDB 的六个观察点完全一致：去重/空值/软删除、
  精确字符串清除、missing key、不误删笔记、取消订阅、释放后迟到调用、闭库失败。
- 新增反例真实发现目标释放后还能写库：Android 不写、Harmony 清除 Hidden，RED 1 failure。
  在目标 `NoteViewModel.clearLocationInfo` 加 active guard，GREEN 2/2，5306ms；
  不回滚已提交写入、不新增通用协程框架。
- Android 原页面和 Harmony 真 UI 均通过取消、确认、精确参数导航、原生返回、返回后刷新、
  root Back；Android 还实测 process restart。Harmony 通过两个独立 aa-test 进程验证
  已提交清除仍落盘且笔记未删除（1/1 1951ms + 1/1 1876ms）。
- 测试使用隔离数据库或可精确识别的临时行；仅清理本测试数据，原库保留，最终两端仍为 Hidden。
- 新截图在 `capture-lifecycle-final/`；本地脚本比较在 `comparison-lifecycle-final/`。
  未让模型读取图片，严格视觉门禁仍不能称 PASS。
- 正常 source validator 仍 exit1：collection pending、独立审查缺失、in-flight/进程级异常
  等价性尚未证明。6/6 implemented 与 65/65 mapped 都不是最终业务验收。
  没有伪造独立 Review/签名 evidence，没有降低门禁。

## 2026-10-09 可复用流程收口

用户明确目标是供其它项目复用的业务迁移流程，不是继续完善 IdeaMemo 样例。本轮未再操作
设备或扩展样例业务，没有派发开发/审查，没有 commit/push。

- 现有 Skill 的 canonical 执行循环收敛在 `references/semantic-transcription.md`：
  UI/系统触发与状态 → 真实业务调用链 → 源行为用例 → AI 按源码逐层转写 → 源/目标结果比较
  → 现有 target gate 与适用运行验证。MVVM、reducer、use case 使用同一条流程。
- Skill 入口、source-page-workflow 和 page CLI 的 ready handoff 均指向这个循环；不增加
  handoff 文件，不新增状态机/schema/生成器。异步行为按实际源码 owner 判断，不默认页面
  消失等于 ViewModel 销毁，也不把整个平台库的等价性扩成额外需求。
- target validator 原先仅凭非空 target 字符串可接受 `Missing.ets#refresh`。现在复用
  当前 target source manifest，要求 file#symbol 指向唯一的生产源码文件；拒绝不存在、
  越界路径、构建文件、测试文件、重名 basename 和空符号。完整相对路径和唯一 basename
  均保持可用。该检查验证文件出处，不声称解析或证明符号体的业务语义。
- 公共 CLI 测试在有效、当前 runtime receipt 下先复现 4 个负路径错误通过（RED），修复后
  GREEN；最终覆盖上述 6 类反例和两类合法引用。使用受控 evidence-runner/HDC fixture，
  不冒称真实设备验收。原 page CLI 的 source/target 正向及失败关闭路径仍通过。

### 本轮验证证据

目录：`/tmp/reusable-business-workflow-20261009-42rEW5`。

使用 Python 3.14 和既有固定 JDK17/Kotlin PSI 环境：

```
-m unittest test_compare_behavior_traces test_page_commands test_behavior_contract_v2
test_behavior_collection test_behavior_source_closure test_effective_page_closure
test_existing_target test_source_dependencies test_evidence_runner
```

143/143 PASS，139.859s，exit0（regression.log）。既有四个 project 编排回归 4/4 PASS，
4.274s，exit0（orchestrator.log），本轮合计147/147。Skill quick_validate 使用系统
Python3/PyYAML，通过。git diff --check PASS，staged 为空。

停止标准：本需求的共享执行指引、source/target gate 串联、实际发现的引用漏洞修复及相关
回归已完成；不再为了完善单个样例无限追加平台适配。真实项目仍须按其范围提供源码审查、
当前行为/设备证据及适用 UI 验收，任何未通过项保持未通过。此前样例 pending/visual FAIL
没有被本轮工具测试覆盖或改写成 PASS。

## 步骤4：真实入口复跑（2026-10-09）

证据：`/tmp/business-workflow-reuse-20261009-BZiXwH`。本轮未改样例目标源码、未操作设备、
未执行生成器、未伪造 Review，未 commit/push。并非又一次完整设备迁移验收。

### OnlyFlows Tags

- 同一公开 `migrate_compose_page.py`，原 snapshot/contract/styles，绑定真实 after-bulk
  page.json 与已有 runtime theme，使用明确 Work 一项、unusedCount=0、showCreateDialog=false、
  editingTag=null 的新状态 fixture；复用已批准边界结构。
- 9.803秒 exit1。closure 生成成功且 business_transcription=ready_for_source_transcription，
  但 UI selection=candidate_requires_runtime_facts，所以在业务规格校验之前停止。
- 可定位反例：TagsScreen.kt:162 的 `editingTag?.let` 内 TagEditDialog 的
  `name.isNotBlank()` 仍出现在 unresolved_branches；editingTag 已显式 null。当前闭包
  未正确排除这一层不可见上下文；不据此猜填 name 或把隐蔽弹窗说成真实可见。
- 当前 CLI 把 UI 投影器分支选择完整性作为业务规格/AI交接的硬前置，和用户要求
  “不要求解析器适配所有语法，后续 AI source-first 完成”有冲突。新增逐语法适配或
  放宽这个前置条件都不是简单补业务测试，需要明确采用哪种边界；本轮没有悄悄改门禁。

### IdeaMemo Locations

- 正常入口 preflight exit1：现有材料没有完整的 state-fixture + Android page.json +
  runtime theme 输入组合；既有原始截图/XML/日志不是这些结构化输入的替代。
- 另通过同一现有 source validator 重跑真实行为工件，exit1：collection pending、
  独立 semantic review 缺失、U-LIFETIME/U-REVIEW 未解决。65个区域的映射完整仍非 source PASS。
- 因而不能将以前的 6 组配对观察和设备 UI 成功说成这条正式工作流已全程通过。

### 身份和边界

只读重算当前目标源码身份：
- OnlyFlows：sha256:757c303fd57dde5ece0c4496cecf7cf5c8f9b78ad603b797e42fadac3d03fda3
- IdeaMemo：sha256:926e0a4ae79ace539b0deb2e6eddf915e3578de5b96c31fa389a9bcd2e554c74

保留旧配对证据为历史结果（OnlyFlows8组，IdeaMemo6组），未重新签发运行凭据。
尝试把 hash_target_source CLI 的输出放在外部证据目录被它正常拒绝，之后只读调用
其 create_manifest 计算身份，没有修改目标的已有 manifest。

当前不能进入步骤5并宣称交付完成。需先解决上述 UI 解析硬前置的边界冲突；独立审查仍是
既有正式 source gate 的要求，不能由实现者补一个通过文件。优先解决共享流程，不继续
扩展样例业务或重跑无法改变该入口结果的设备测试。

## 已批准的整页交接修复与复跑

用户明确：整体迁移保留源条件和全部业务分支，由运行时选择显示，不逐个填写分支判定。
因此本轮只调整正常 page CLI 的交接条件，并同步 Skill/语义转写/页面流程说明；没有改
投影器语法支持、业务 validator、状态机或生成器。执行 contract 已记录这个批准的边界。

- 允许 `candidate_requires_runtime_facts` 进入已有 source gate；报告继续保留
  `runtime_state_selection=unresolved`，未将未知可见性涂成 resolved。
- 缺业务规格/审查仍阻断，完整业务规格通过后才能交接；implementation/business/visual
  均不因交接而被标成完成。闭包保留两条分支及源码身份，不根据当前截图删业务。
- 公开 CLI 反例先 RED（2.429s），修复后 GREEN（2.268s）。额外正向用例通过真实
  source validator 后进入 handoff（3.119s）；其 review/runtime 输入是明确的测试 fixture，
  不冒称真实项目的独立 Review。回归包含原有缺源码/状态矛盾/旧审查/缺映射/无效证据负路径。
- 本轮相关144/144 PASS，150.953s；项目编排4/4 PASS，4.612s；合计148/148。
  日志在同一 evidence 目录的 whole-page-regression.log / whole-page-orchestrator.log。
  Skill quick_validate 与 git diff --check PASS，staged 空，未commit/push。

OnlyFlows 实际入口：默认256 MiB JVM先后两次发生 heap OOM（约6.00s/5.33s），均保留失败。
仅对第三次验证命令设置 `_JAVA_OPTIONS=-Xmx768m`，9.367s 到达
`business_specification_required` / `behavior-source-validation`；旧的未解析弹窗条件不再
挡住业务规格入口，44个完整源码阅读文件及未解析状态保留。没有修改系统环境、产品堆配置、
模拟器或样例目标源码。此验证有明确的768 MiB环境条件，不能称默认环境运行全部通过。
详情：onlyflows-whole-page-entry-768m/result.json。

本轮交接边界修复完成。总计划步骤4的真实业务 source/target 完整通过仍未完成：OnlyFlows
尚缺正式业务工件/Review，IdeaMemo保留上节材料/Review缺项；它们不是已经通过的完整迁移。
不把这次修复、148个集成测试或入口越过旧卡点改写成两页最终验收成功。

## 2026-10-11：压缩重复映射，不增加逐节点任务

本轮沿用用户批准的步骤：检查逐节点记录负担，只修实际重复，继续既有两页，不扩展业务。
原有场景和独立审查 expectation 已经可以覆盖多个区域；真正重复的是 bindings 中相同的
record_ids/scenario_ids。新增可选 obligation_ids 分组，旧 obligation_id 保持兼容。
source closure 与 semantic review 使用同一展开函数；每个区域仍独立检查原表达式、
源码锚点、决策类型、场景和完整分母。遗漏、重复、未知ID、混用两种ID字段、空组均失败。
改动 contract 后旧 Review 仍失效，没有新增生成器、状态机或工件。

### 本轮证据

- 公共 source validator 测试先 RED：1 failure，34.542s；实现后 GREEN：1 test，43.713s，
  包括旧审查失效、合法分组、混合格式及六类负子例。测试 Review 是受控 fixture，非真实审查。
- 既有 IdeaMemo contract 在独立临时副本中机械合并：65行→21组；展开映射完全相等；
  bindings 序列化9104→5965 bytes（约34%），6动作/7场景不变。此百分比仅指映射大小，
  不表示整个JSON或迁移耗时减少34%。原业务工件未修改。
- 证据目录：`/tmp/business-binding-groups-20261011-lZK8ZJ`，含转换脚本、分组工件、
  真实验证失败JSON/log及扩展回归log。转换脚本没有生成 Review。
- 扩展回归命令：Python3.14，既有JDK17/PSI环境，`-m unittest test_behavior_source_closure
  test_behavior_collection test_behavior_contract_v2 test_page_commands`。运行超过约11分钟
  仍未结束，已仅对本轮PID80811发送INT，exit130；中止前观察到19个通过点，无最终汇总。
  本轮扩展回归是 INCOMPLETE，不是PASS；此前148/148不能替代当前版本完整回归。
- Skill quick_validate PASS；git diff --check PASS，staged为空。schema JSON解析成功；
  系统Python无jsonschema，因此未完成独立JSON Schema元校验，未安装依赖。

### 真实项目阻塞与完成边界

IdeaMemo 原 snapshot `/private/tmp/source-first-25-pages-20261005/apps/ideamemo/snapshot`
缺 `.android-to-harmony-safe.json`，原项目contract也缺失，现存源/host目录无可用Git身份。
真实分组工件的source validator因此失败，保留 missing_safe_manifest 等错误，不能把机械
映射等价说成当前源码验证通过。没有伪造安全清单、审查或签名执行证据，没有操作设备。

共享映射优化已实现；整体迁移流程的真实样例source/target闭环仍未验收通过。继续真实
验证需要恢复可核验身份的原始输入，再补既有业务工件/运行输入和冻结后的独立审查；不靠
重复运行失去输入的命令，也不扩展为新页面开发。未commit/push，未派发Dev或Reviewer。

## 2026-10-11 继续：恢复原始源码，补真实分组验证

本节覆盖上节“原始输入无法继续验证”的状态，不抹去原失败记录。

- 找到两份旧源仓库保留的 Git pack。未修改旧目录；将现存完整pack/idx复制到新的隔离
  Git仓库，checkout历史工件中已记录的精确commit。没有从当前上游HEAD猜测版本。
- 新证据根：`/tmp/business-source-recovery-20261011-hgY4gl`。
  IdeaMemo revision `e3d7205919e8b7a41070a15310a4402fa469fd9a`；
  OnlyFlows revision `bb29fdb4d70d4eb885577e58890111e1a46fbf58`。
  两份恢复仓库均detached、dirty=false。没有新commit、push或远端访问。
- 通过既有prepare_safe_snapshot重新生成，不补造旧manifest。独立safe-tree校验通过：
  IdeaMemo 133文件、OnlyFlows 241文件（含各自manifest），均0 violations。
- 正常census重跑后，两页files（含源码哈希）与obligations均与原记录逐字段完全一致：
  IdeaMemo 10业务文件/65项；OnlyFlows 41业务文件/991项，均0 unresolved。
  新snapshot manifest身份不同，不能直接沿用旧census/review身份。
- 在新临时副本中，仅重绑IdeaMemo分组工件的source_closure.census_sha256；脚本先严格
  比较新旧files与obligations再写副本，未修改原工件、业务事实、目标代码或审查记录。
- 真实source validator：source_closure.coverage_complete=true、65/65、missing=[]、
  errors=[]；collection.source_fact_coverage=18/18。完整命令仍exit1，仅剩collection
  pending、缺独立semantic review、U-LIFETIME/U-REVIEW。这不是正式source/runtime PASS。
  U-LIFETIME指已提交原生操作与owner销毁的顺序、未捕获平台异常处理仍未证明等价。
- 上轮中止的4模块回归补跑75/75 PASS，107.565s，exit0；日志位于上一证据目录的
  `regression-retry.log`。四个项目编排回归4/4 PASS，6.006s，exit0（本目录orchestrator.log）。

本轮未改共享产品实现，未操作设备，未派发审查。恢复的是验证输入和可重跑能力，不是
把样例未完成项改成通过；不再以“源码快照丢失”作为当前阻塞。

最终相关回归（同既有Python3.14/JDK17/PSI环境）：

```
-m unittest test_compare_behavior_traces test_page_commands test_behavior_contract_v2
test_behavior_collection test_behavior_source_closure test_effective_page_closure
test_existing_target test_source_dependencies test_evidence_runner
```

145/145 PASS，149.964s，exit0（本目录regression.log）。加四个项目编排用例，
本轮最终149/149 PASS；不重复计入先前75项。git diff --check PASS，staged为空。
本轮共享实现回归不再标INCOMPLETE；历史中断记录仍保留。样例正式验收状态仍按上文未通过。

## 2026-10-11 正常入口修复：已初始化目标的 Contract 绑定

本轮继续“修改到流程通过”，没有新增生成器、状态机或放宽业务验证。

### 修复与回归

- 新增公开 page CLI 端到端测试：预先 init 但未绑定 Contract 的自有目标，直接运行
  页面入口，再经过受控 evidence runner 和 target validator 到 `page_business_verified`。
  测试断言原页面字节未被覆盖，并检查已记录 Contract 被删除或修改时拒绝、不自动重绑。
- RED：1 failure，2.414s，错误为 `target project is not bound to the migration contract`。
- 首次接入既有 attach helper 后再次 RED：1 failure，2.592s，暴露 helper 修改 state 后
  未更新原有 ownership proof。修复为先验证已有 proof，再对合法元数据更新重新签名；
  没有新建或伪造 ownership。新增篡改目标 state 的拒绝用例，原 state 保持不变。
- GREEN：单个完整闭环测试通过，4.048s。入口+安全回归49/49通过，101.683s。
- 最终相关回归161/161通过，151.605s，exit0：原145项相关模块，新增 page 测试，
  security_hardening模块及既有 attach export 用例。测试中的 Review/SDK/HDC明确是
  受控测试 fixture，不作为真实项目的审查或设备验收。
- 日志：`/tmp/business-source-recovery-20261011-hgY4gl/final-binding-regression.log`。
  Skill quick_validate、git diff --check通过；staged为空，未commit/push。

### 真实设备与入口

- HarmonyKitPhone保留数据启动，HDC `127.0.0.1:15557`连接成功。Android旧临时AVD配置
  丢失后，用已有SDK镜像新建隔离`BusinessFlow_20261011`，没有删除旧AVD或重置旧数据。
- 既有IdeaMemo APK/HAP安装后运行：Harmony LocationParity两测试通过；Android原始
  ViewModel/repository/Room测试通过。六条业务观察用公开trace comparator逐项一致，
  comparator仍正确保持`business_verified=false`，不是签名目标门禁证据。
- 在隔离Android测试host内加现有RuntimeThemeFactsProbe，原Android源码仓库不变。
  使用本地缓存Gradle8.11.1离线构建成功34s，新APK及test APK安装成功；采集36个颜色
  和15个字体角色。没有下载工具或更改系统安全设置。
- 新真实Android page capture成功写出，7 runtime components；其visual verdict为fail、
  visible primitive mapping ratio为0，未冒充视觉还原通过；没有用截图生成目标代码。
- 带新snapshot/contract/runtime page/theme/state及原精确业务scope跑正常入口：
  effective-page-closure exit0，2.660s。最终exit1，`business_specification_required`，
  `failed_stage=behavior-source-validation`，因缺`--behavior-source-review`。
  证据：`ideamemo-normal-entry/result.json`及同名log，仍`business_verified=false`。

### 仍未关闭的验收项

真实样例的collection pending、独立语义审查缺失和U-LIFETIME仍保留。没有把
“原生操作已提交后销毁owner的调度/失败处理尚未证明等价”直接改成通过。
代码级公开CLI闭环现已通过；IdeaMemo真实业务门禁和OnlyFlows第二样例尚未验收。
已向用户询问是否可复用现有固定会话“Spec Workflow Reviewer · Android→Harmony”；
未收到授权前不发送跨任务消息、不新建Reviewer、不伪造审查。恢复审查后需冻结确切
候选及业务工件，独立核对生命周期边界，再继续两页真实source/target闭环。

## 2026-10-11 用户纠正后：先完成实现及开发验证，不派发审查

上一节的“先恢复审查”计划已被用户明确纠正，现不执行。继续开发和可执行验证，不把
缺少 review 当成开发停工条件；正式 source/target 验收仍不得伪造通过。本节没有派发
Dev/Reviewer，没有 commit/push，没有运行任何确定性页面代码生成器。

证据根仍为 `/tmp/business-source-recovery-20261011-hgY4gl`。本轮业务实现/测试改动发生在
隔离的临时 Android host 与 Harmony target，不是已随共享 Skill 分发的应用代码。

### 已执行的业务与页面测试

- IdeaMemo：新测试在原始 Room 同步 UPDATE 已进入时用 latch 暂停，取消原 VM 后再放行，
  验证已提交写入仍完成；Harmony 对应测试验证已提交 native write 完成且无销毁后观察通知。
  Android 首次 instrumentation 启动 ANR 的日志保留；重跑通过。Harmony `LocationParity`
  3/3 PASS。原六条顺序观察加独立 in-flight 观察，共七条一致；没有排序掩盖单个测试内的时序。
  日志：`android-inflight-retry.log`、`harmony-inflight.log`、`ideamemo-seven-paired.json`。
- IdeaMemo：两次独立进程调用分别运行 restart prepare/verify，均 1/1 PASS。已有笔记未删除。
  日志：`ideamemo-restart-prepare.log`、`ideamemo-restart-verify.log`。
- IdeaMemo：补跑原始 Compose 页面，取消、精确 route 参数、系统返回、返回后清除、重启持久化、
  root Back 全部 PASS，exit0。测试比较真实运行前的 location 集合，不再假定新模拟器里必有
  旧测试数据 Hidden；只创建/清理本测试拥有的行。日志：`ideamemo-android-ui-final.log`。
- OnlyFlows：移除目标端“存在 paired peer 就抛异常”的占位实现，按源码异步 enqueue，不等待
  远端结果再继续本地删除。真实 peer failure 用例先 RED（1 error）后 GREEN。
- OnlyFlows：增加 disposed VM 晚到事件测试，先 RED（预期0行、实际1行），在 onEvent 入口恢复
  owner-active 检查后 GREEN。未加重试、回滚或源端没有的用户提示。
- OnlyFlows：最终 native business suite 4/4 PASS，包含 owner 生命周期、目标 outbound、失败 peer
  不阻断本地删除、真实数据库响应式事件序列。Android 原始 VM/Room oracle 与目标九条顺序记录
  全部一致：`onlyflows-nine-paired.json`；仍显式 `business_verified=false`。
- OnlyFlows Android 原始 UI 五组 PASS（创建/校验/选色、取消、编辑、删除与批量删除、重启持久化）；
  Harmony 原页面交互 1/1 PASS，23.507秒。日志：`onlyflows-android-ui-final.log`、
  `onlyflows-ui-controls.log`。

### 发现并纠正的测试输入问题

- Harmony UI 测试最初向 `entry_test` 模块数据库写夹具，而真实页面读取 `entry` 模块数据库。
  等待页面或换 context 不能可靠证明两者一致。最终通过真实页面控件创建缺少的 Home/Later，
  断言两行可见后再做批量删除；没有删除断言、没有清空用户数据库。临时生产诊断日志已移除。
- OnlyFlows fresh analysis 默认256MiB PSI堆 OOM，`-Xss4m`尝试未解决并保留失败；仅此次命令用
  `_JAVA_OPTIONS=-Xmx1024m`后分析 PASS（72.842秒）。未改产品超时或默认环境，未掩盖失败。
- 纠正共享 `references/page-snapshot.md` 的 Harmony capture 示例：`--source-root` 应指向
  Android 安全 `$SNAPSHOT`，不是 Harmony target。两端都用同一源组件身份。

### 采集、结构绑定及诚实边界

- OnlyFlows fresh Android/Harmony 页面已采集。首次 Harmony 采集与另一页面测试重叠且 source root
  错误，明确标 INVALID；后续 `onlyflows-harmony-page-r2` 独占设备重新采集。
- 新配对 `onlyflows-comparison/`：全屏严格 SSIM=0.923433。严格 verdict=fail，包含逻辑 viewport
  不兼容和组件映射不完整；不宣称视觉验收通过。Harmony density/insets沿用同一保留数据模拟器
  的既有测量，不是本轮新测；Android是新AVD。未让模型读取截图或借截图生成页面代码。
- IdeaMemo 在现有业务工件中补入 SC-INFLIGHT 及 collection 场景映射；源码覆盖仍65/65、事实18/18。
  缩小 U-LIFETIME 到尚未证明的未捕获平台异常策略，未把已通过的在途写入重复列为未知。
  collection pending、独立 source review缺失仍保留，source validator仍exit1。
- OnlyFlows 用已有 definition_boundaries 格式选择完整页面可达 DAO/client 方法，保留全部原文件
  作为阅读上下文。新 `onlyflows-scope-r2.json` / `onlyflows-census-r2.json`：664区域、40文件、
  unresolved=[]（原991/41）；页面root与revision不变。它不是业务实现百分比，也不是独立审查结论。
- OnlyFlows 的完整 behavior inventory/contract与正式目标场景绑定仍未完成，不能把九条 trace
  一致声称为整页 source/target gate PASS。仍含保守同名/扩展函数候选，未为缩小数字删除未知代码。
- 原 Android postApply 日志称 OK，但 loopback peer 没收到原端 payload；源码写 outputStream 后直接
  disconnect，未读取 response。目标 outbound 收到 Tag/tombstone 已验证，只证明目标能发送，
  **不是远端投递等价证明**。保留这个源码/运行差异，不悄悄修改原 Android 或宣称网络完整迁移。

临时 localhost:18473 peer 已停止；只移除了本轮 adb reverse 与 hdc rport 的18473映射，复查无监听
及映射。没有重置模拟器、删除应用数据或改安全设置。共享可执行代码维持先前161/161最终回归版本；
本段新增共享修改仅上述文档参数修正，staged仍空。整体验收尚未完成，但当前实测业务/UI成功项均
有真实日志，不依赖提前审查来推动开发。

## 2026-10-11 开发与真实执行收口（独立审查尚未启动）

用户明确答复“这种细节异常问题可以跳过不追究”。原 Android outbound 未抵达 loopback peer、
未捕获平台异常策略保留为已披露、不再追究的差异，不报告等价通过。共享门禁未降低。

### 本轮共享实现与回归

- 为同名扩展函数的已有 definition boundary / resolved dependency 增加可选 `definition_line`，
  精确选择完整顶层定义；不做类型推断，不删除完整源文件。错行、布尔、字符串、歧义选择均拒绝。
  真实 OnlyFlows Tag/Task 同名序列化器据此选择，完整文件仍保留 hash-bound 阅读上下文。
  `overload-boundary-red.log` 先失败，`overload-boundary-green.log` 19/19 PASS。
- 发现 literal mask 使 `const val TAG = "..."` 被当作未结束赋值，跨越已遮蔽 context 拼接到下一方法。
  用保留字符串、排除注释的文本判断换行终止，仅修正 census 的语句边界；不放宽 collection 校验。
  `literal-boundary-red.log` 精确复现非原始源表达式；`literal-boundary-green.log` 20/20 PASS。
- 最终命令在 Skill scripts 下执行：
  `python3.14 -m unittest test_compare_behavior_traces test_page_commands test_behavior_contract_v2 test_behavior_collection test_behavior_source_closure test_effective_page_closure test_existing_target test_source_dependencies test_evidence_runner test_security_hardening test_tools.MigrationToolTests.test_attaches_contract_without_exporting_local_paths`。
  使用原记录中的 JDK17/Kotlin PSI classpath 和 Python3.14.5，最终 **163/163 PASS，169.075秒**，
  日志 `final-business-workflow-regression.log`。包含正常 page entry 的 source→执行器→target 正向链路，
  及丢失/篡改/过期证据、source scope 不一致等负向验证。
- 保留失败记录：早先 `final-overload-regression.log` 命令误写不存在的模块，162 run/1 import error，
  不算通过；修正命令后 `final-overload-regression-corrected.log` 为162/162 PASS，160.171秒。

### 两个真实 fixture 的规格与执行

- IdeaMemo：18/18 事实、65/65 源区域、6/6 target action mapping；8/8 场景均被 target validator
  确认为当前源码对应的真实签名设备执行，而非仅计数文件存在。
- OnlyFlows：25/25 事实、278/278 源区域、10/10 action mapping；6/6 场景同样通过签名执行核对。
  完整37个源文件仍保留（其中16个贡献当前行为），不宣称278个区域=278条业务或必须278个测试。
  增补真实符号及 page→VM→repository→DAO/writer→coordinator/client 关系，不再用组名冒充类名。
- OnlyFlows 正常 Back 路径发现宿主已有上一页时也 terminateSelf。隔离 native UI 测试先观察到
  点击后 UI execution context 消失，修复为有上一页时 native router.back、孤立 root 时沿用显式
  terminate adaptation，`onlyflows-back-green.log` 1/1 PASS，4.124秒。后续整组 UI 测试包括返回后
  创建/编辑/取消/删除/批量删除，2/2 PASS。未增加新的迁移页面。
  首次 Back 测试把 SDK string depth 与数字相加，先修正测试的 Number 转换再观察真实 RED；两份
  RED 日志均保留，不把最初测试错误算作产品缺陷。
- 通过现有 `build_run_state` / ownership / attach helper 建立隔离 developer execution identity，
  没有伪造 source review，也没有把正常 page handoff 标为通过。`prepare-developer-evidence.py`
  仅为本次开发前置验证调用现有 helper；不是新的用户入口。正常入口仍须真实审查。
- 现有 `evidence_runner.py` 实际 main→test HAP 安装与 aa test：OnlyFlows native 4/4、UI 2/2；
  IdeaMemo LocationParity 3/3，加两个独立 aa-test 进程的 restart prepare 1/1、verify 1/1。
  签名记录在对应 target `.migration/evidence/`；OnlyFlows最终为 `onlyflows-native-bound.json`、
  `onlyflows-ui-bound.json`，IdeaMemo为 `ideamemo-parity-final.json`、
  `ideamemo-restart-prepare-final.json`、`ideamemo-restart-verify-final.json`。
  `bind-executed-scenarios.py` 只验证并索引这些已有 receipt，未创建/改写 attestations。
- OnlyFlows最终 scope 为 `onlyflows-scope-r4.json`，census 为 `onlyflows-census-r5.json`；scope id
  与真实 capture 的 `onlyflows-tags/after-bulk` 对齐。早先正常入口混用了旧 three-tags fixture，
  被正确拒绝并保留失败日志；新 `onlyflows-state.json` 据原始测试 seed 和 after-bulk 结果填写，
  没有改 Android capture、没有关闭 page/state/hash/content 校验。

### 当前尚未通过的验收项（不得隐去）

- 两页 target validator 都已确认完整源映射、action mapping、8/8或6/6 executed scenarios；当前
  剩余 errors 都是 collection 仍pending、独立 semantic review 缺失、显式 U-REVIEW。
  `ideamemo-target-validation-final.json` / `onlyflows-target-validation-bound.json` 仍 verdict=fail，
  `runtime_complete` 仍不冒充整体通过。source completeness 不是开发者自己签字。
- 正常入口 `ideamemo-normal-entry-final` 与 `onlyflows-normal-entry-bound` 都生成正确闭包，然后在
  `behavior-source-validation` 停于真实缺失的 source review。不存在业务映射或执行证据遗留错误。
  OnlyFlows固定画面的9项 visibility未知仍保留；整页源条件转写不因此删除分支。
- 视觉严格比较仍fail（OnlyFlows SSIM0.923433及viewport/mapping限制），dark-theme与无效存储颜色
  尚未获视觉验收。此次是业务流程/门禁开发验证完成，不是所有UI状态、整应用迁移已验收。
- 尚未派发独立Reviewer，未commit/push/stage。所有原始 Android 源和 safe snapshot 未修改；
  设备限定模拟器，未清数据、未重置。临时loopback peer停止，测试用反向端口映射单独清理。

## 2026-10-11 独立审查 r1 与正常入口收口修复

固定 Reviewer `01a03b6b-98e6-7a40-8c36-175a9def7bd9` 审查冻结
`/private/tmp/page-business-review-20261011-UUOsHM`（identity
`8040878f72abae73ed48de9b07ad782225b16c3d5db40e9f5541fb66f898d553`），
原始结论保存于证据根 `independent-review-r1.md`。共享 Skill/CLI 未发现阻塞问题，
IdeaMemo source 语义 Approved；OnlyFlows 一个 Medium：普通 Stack 编辑弹窗未消费系统 Back。
审查独立执行20项 source-closure、25项入口/closure测试及2项 comparator测试；未操作设备。

- OnlyFlows 新增真实控件回归：创建/编辑时输入尚未保存的新名字，明确关闭输入法，再按系统 Back；
  页面仍在、弹窗消失、没有新行、旧名字未改变，重新打开仍是旧值。第一次测试错误假定 inputText
  一定显示输入法，失败日志保留；改用明确 hideTextInput 后，第二次 RED 精确失败于页面不再可见。
  仅在目标 TagsScreen 增加 onBackPress：弹窗打开时 dismiss 并返回 true，其余返回 false。
  重建 main/test HAP 后 `onlyflows-dialog-back-green` 真实模拟器 UITest，2/2 PASS，28.685秒。
  同一 target revision 的 `onlyflows-native-reviewed` 4/4 PASS，2.627秒；loopback收到实际 Tag 和
  tombstone payload。仍不宣称原 Android outbound 投递等价。SC-UI/A-DISMISS补入普通 Back 取消语义。
- IdeaMemo 按独立 Reviewer 明确授权，仅把 collection.status 改为 reviewed、移除 U-REVIEW。
  `ideamemo-source-review-r1.json` 是其五组原始 expectations 的机械展开（65个原 obligation），
  不是实现者自行评审。SC-AFTER-RETURN作为审查支持事实保留在原文，不冒充当前绑定的SC-NAVIGATE。
- 真实正常入口首次带审查运行发现闭包 compact 删除 scope 中必要空数组（unresolved、
  resolved_dependencies、context-only behavior_ranges），下游 census 正确拒绝。因此保留 hash-bound
  scope原样，仅展示事实继续compact；不放宽validator。既有公共CLI测试新增scope精确相等与census
  回读校验，先RED后GREEN。首次命令误写测试类复数是导入失败，不计产品RED；修正命令后的
  `scope-roundtrip-red-corrected.log` 精确失败于scope不一致。定向54/54 PASS，118.160秒。
- 修复后 IdeaMemo 正常入口 `ideamemo-normal-entry-reviewed2/result.json` exit0，4.828秒：
  status=page_business_verified、source_complete=true、runtime_complete=true；
  application_complete=false，视觉/build整体验收仍分开，不宣称整应用完成。
- OnlyFlows最新target validator仍仅为pending/source-review/U-REVIEW三个错误；278/278源映射和
  6/6当前签名场景均已核对。未在独立复审前自行改成reviewed。
- 临时loopback进程已停止、18473映射已移除，fport ls Empty、本地18473无监听。
  无commit/push/stage，无生成器运行，无截图字节进入模型。
- 最终共享回归同上一节完整11个suite/指定测试命令，163/163 PASS，154.492秒，
  `final-business-workflow-review2-regression.log`；git diff --check通过、index为空。

## 2026-10-12 自动业务 Gate 与 Review 解耦

用户批准：业务 Gate 不能依赖 Review。此次修改为同一仓库现有入口的小范围修正，
不增加状态机节点、不改生成器、不操作模拟器或业务样本源码。前一轮冻结候选保留不动。

- `validate_behavior_contract_v2.py` 的 source/target verdict 与 exit code 不再依赖 Review。
  可选 Review 的批准/绑定错误单列 `semantic_review`，取值 `not_provided/pass/fail`。
  拒绝、过期、格式错误、不可读取均不能变成 Review 通过，也不阻断自动检查。
- `migrate_compose_page.py` 不再要求 `--behavior-source-review`，仍要求真实业务 contract/inventory，
  保留生成页面根、源码范围、目标所有权及 current/scoped execution evidence 检查。
- 收集表新增 `status=complete`，兼容既有 `reviewed`；两者都执行完整机械校验，
  不意味着 Review 批准。pending/unknown/null、源码漏项与未执行场景继续失败。
- Skill、业务规格参考与页面入口文档同步。source_complete 仅表示自动源码校验通过，
  不表示语义等价或独立批准；周边工作流如需 Review 应独立判断。

RED/GREEN：无 Review 源校验先因 semantic review required 失败，修复后通过；无 Review 页面入口
先因必填参数失败，修复后通过；可选缺失/损坏 Review 与 complete 收集状态均先复现失败后修复。
现有 tests 使用受控工具 fixture；不冒充真实设备/业务页面测试。

最终稳定代码回归（所有可执行修改完成后）：从 Skill scripts 目录 source 本次独立实验的
`/private/tmp/business-migration-10-pages-20261011-9zdWsK/benchmark-env.sh`，再运行：

```text
_JAVA_OPTIONS=-Xmx1024m /opt/homebrew/opt/python@3.14/bin/python3.14 -m unittest \
  test_behavior_contract_v2 test_behavior_source_closure test_behavior_collection \
  test_evidence_runner test_orchestrator test_security_hardening test_existing_target \
  test_compare_behavior_traces test_page_commands
```

168/168 PASS，exit0，183.392秒；命令环境 PYTHONDONTWRITEBYTECODE=1。
之前31项、36项、132项及定向重跑只是开发反馈，不重复累加成最终测试数量。
真实实验原有 Search contract/inventory 在新 target validator 下仍 exit1，缺 collection/source scope、
六项登记映射与 scenario results；不再报 Review 缺失。六项映射缺失不是脚本对代码缺失的语义证明。
十页迁移实验未重启、已失败/污染样本没有提升为通过。

当前分支 page-scoped-migration-closure，HEAD 9d3ca4136e53e07d0a99a048face51087c728d84。
git diff --check PASS；index 空。原有未提交修改完整保留，本轮也未stage/commit/push。
本轮没有派发独立 Reviewer，测试通过不是新的独立 Review 批准。

## 2026-10-11 最终：独立复审通过，两页正常入口业务验证完成

固定Reviewer复审冻结 `/private/tmp/page-business-review2-20261011-xjDJVB`，identity
`c1b462f62f5e5b9dc005d47eb5e35a071dc7138a7afb35272d7aee53ff8a9ab0`，
turn `01a12aef-2ac6-70d3-8dc9-1f106e184044`，明确共享代码与OnlyFlows source/场景均Approved，
IdeaMemo维持Approved。完整回复在证据根 `independent-review-r2.md`。Reviewer独立核对scope
roundtrip、真实receipt与IdeaMemo source validator；没有将开发163项回归说成独立重新执行。

按其明确授权，OnlyFlows只提升collection.status并删除唯一U-REVIEW；六组原expectations机械展开
为278个原obligation，存 `onlyflows-source-review-r2.json` 并绑定最终contract hash。未改写源分母、
未伪造设备签名或用缺失review占位。最终正常用户入口真实执行：

| 页面 | 正常入口结果 | source_complete | runtime_complete | 场景 | 命令耗时 |
| --- | --- | --- | --- | --- | --- |
| IdeaMemo Locations | page_business_verified | true | true | 8/8 | 4.828秒 |
| OnlyFlows Tags | page_business_verified | true | true | 6/6 | 15.249秒 |

结果路径分别为证据根 `ideamemo-normal-entry-reviewed2/result.json` 与
`onlyflows-normal-entry-reviewed2/result.json`，两者exit0、business_verified=true；
application_complete=false、implementation_complete=false、migration_complete=false保留为其原本的
独立整体验收语义。此处完成的是本轮可复用业务迁移流程及两个页面范围业务门禁，不是整应用验收。

OnlyFlows第一次最终入口在effective-page-closure阶段因Java heap space失败，失败记录保留于
`onlyflows-normal-entry-reviewed/`。仅第二次命令用 `_JAVA_OPTIONS=-Xmx1024m` 后通过；没有修改
产品默认堆/超时或关闭验证。该真实项目仍需足够PSI堆内存，不宣称默认环境无条件成功。

视觉严格比较仍fail，暗色/无效存储颜色视觉未验收；原Android outbound和平台异常策略是已披露
豁免，不是parity PASS。此次不重跑或改写原图对比记录，不宣称新增Back修复获得全视觉验收。
没有新页面、没有生成器、没有新状态机、没有提交/推送/暂存；共享可执行代码与复审冻结一致，
本段只是最终结果记录。
