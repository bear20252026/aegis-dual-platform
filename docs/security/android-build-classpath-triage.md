# Android 构建类路径依赖告警分诊（2026-10-03）

**背景**：Gradle-Dependency-Graph 接入（PR #62，SP-246 收尾）后，Dependabot
alerts 首次对 Android 构建面生效——11 项告警（1 critical / 3 high / 4 medium /
3 low）。本文档记录分诊证据、已落地修复与剩余项的处置依据。

## 一、暴露面判定（关键证据）

`gradle-dependency-insight.yml`（dispatch 诊断工具）实测三条 classpath 闭包：

| 闭包 | 受影响包命中 | 结论 |
|---|---|---|
| `:app:debugRuntimeClasspath`（产品 APK 面） | **零命中** | **产品不受影响**——受影响包全部不在出厂制品内 |
| `debugUnitTestRuntimeClasspath`（测试面） | 仅 bcprov（经 Robolectric BOM 约束已解析 **1.85** 修复版） | 测试面干净 |
| build classpath（`buildEnvironment`——构建机面） | bcprov/bcpkix 1.80.2、jose4j 0.9.5（bundletool）、jdom2 2.0.6（jetifier）、commons-lang3 3.16.0（sdklib）、httpclient 4.5.6（sdklib） | **全部为 AGP 9.4.1 构建类路径传递依赖** |

即：受影响代码只在**构建机（dev/CI）执行构建时**存在于 AGP 工具链进程内；
攻击面 = 恶意输入喂给 jetifier/bundletool/sdklib 的构建期场景，产品运行时
零暴露。

## 二、已落地修复（PR #65）

`android/build.gradle.kts` 根加 **buildscript 类路径安全地板**——与 plugins
DSL 类路径同域冲突解析（地板后 insight 复测：classpath 配置内
`commons-lang3:3.16.0 -> 3.18.0`、`bcpkix:1.80.2 -> 1.84` 等箭头实证）：

| 包 | 地板版 | 对应告警 |
|---|---|---|
| bcprov/bcutil-jdk18on | 1.85 | #11(critical)/#12/#8 |
| bcpkix-jdk18on | 1.84 | #7 |
| jose4j | 0.9.6 | #5（已消除） |
| jdom2 | 2.0.6.1 | #4（已消除） |
| commons-lang3 | 3.18.0 | #3 |
| httpclient | 4.5.14（钉版防回退） | #2 |

验证：android-quality（ubuntu）/contracts/native-policy 门禁全绿 +
release-android dispatch 走真实 assembleRelease/打包/对齐链全绿（
含 SP-223 readelf 探针加固——窄输出折行缺陷修复，见该 workflow 注释）。

## 三、剩余告警处置（9 项）

地板后图重提交（08:05Z）仍有 9 项 open：bcprov×3、bcpkix、lang3、
httpclient（AGP 传递）+ logback×3（低危，不在本仓任何解析树内，疑为
插件自有类路径节点）。判定：**地板不可达面**——这些版本记录存在于
AGP 插件 detached 配置的独立解析域，用户侧无法对插件内部传递依赖做
版本选择（jose4j/jdom2 之所以能消除，是其脆弱节点仅存在于已修的
classpath 域）。

**判定：tolerable_risk**（构建机侧暴露、产品运行时零命中、上游无稳定修复）。

> ⚠ **R8-CI-06 更正（第八轮 2026-10-05）**：本段原文写作「处置：tolerable_risk……
> 附证据 **dismissing**」，把「判定」表述成了「已在 GitHub 上执行的操作」。
> 只读复核实测：9 条告警全部 `state=open`、`dismissed_at` 为 null，`dismissed`
> 计数 0（#11 critical bcprov / #12 high bcprov / #8 #7 #3 #2 medium /
> #10 #9 #6 low）——即这批告警**一条都没有被 dismiss**，只是被分诊过。
> 本表的严重度列与实况一致，问题只在这句状态描述。
>
> dismiss 一条 Dependabot 告警是对该仓安全姿态的正式处置声明（影响所有读该仓
> 告警面的人，且默认不在任何 CI 门禁里留痕），属仓库所有者操作，需你确认后执行。
> 本轮只更正陈述、不代做操作。若确认按「tolerable_risk」正式 dismiss，
> 需要连证据一起写进 dismiss comment，并保留下面的解除条件。

解除条件：AGP 9.5 stable 发布（当前 alpha——9.5 内 tools/bundletool 预期携带
修复版传递依赖）→ 重开评估，届时地板可整体退役。

| 告警 | 严重度 | 包 | 脆弱版本 → 修复版 |
|---|---|---|---|
| #11 | critical | bcprov-jdk18on | <1.85（Name Constraints bypass） |
| #12 | high | bcprov-jdk18on | <1.85（ASN.1 nesting-depth） |
| #8 | medium | bcprov-jdk18on | LDAP injection <1.84 |
| #7 | medium | bcpkix-jdk18on | Risky Crypto <1.84 |
| #3 | medium | commons-lang3 | Uncontrolled Recursion <3.18.0 |
| #2 | medium | httpclient | XSS <4.5.13（树内已解析 4.5.14） |
| #6/#9/#10 | low×3 | logback-core | 1.5.25/1.5.33/1.5.34 |

## 四、复检规程

1. `gh workflow run gradle-dependency-insight.yml`（master）→ 看 build-env.txt
   命中行与 `->` 解析箭头；
2. AGP 9.5 stable 发布后：bump `libs.versions.toml` 的 agp → 跑 insight 复查
   → 逐一 reopen/复核剩余告警 → 地板退役评估。
