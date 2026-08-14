# Mobile Repo Doctor — AI report

> Machine-readable repository health report. Each finding has a stable `id`, a `severity` (critical > high > medium > low > info), why it matters, and a concrete `fix`. Use it to prioritize and apply fixes; lower `score` is worse (0–100 per axis).

- **repository:** android (`D:\abrowser\review\aegis_dual_platform\android`)
- **stack:** android
- **scanned:** 2026-08-14T21:10:27.627Z · **tool:** v1.0.20 · **duration:** 0.1s
- **files:** 31 (32.2 MB)

## Health score

- **overall:** 92/100 (grade A)
- **axes:** size 81 · speed 99 · stability 93 · hygiene 100

## Summary

- **findings:** 12 total — Critical 0 · High 3 · Medium 0 · Low 6 · Info 3
- **top issues:**
  - [high] 2 oversized font file(s) (high) (`assets-oversized-font`)
  - [high] 2 heavy font file(s) (high) (`assets-heavy-font-file`)
  - [high] Hardcoded signing credentials in app/build.gradle.kts (`android-hardcoded-signing`)
  - [low] 1 oversized font file(s) (low) (`assets-oversized-font`)
  - [low] 1 heavy font file(s) (low) (`assets-heavy-font-file`)
- **quick wins:**
  - 2 oversized font file(s) (high) (`assets-oversized-font`)
  - Hardcoded signing credentials in app/build.gradle.kts (`android-hardcoded-signing`)

## Findings

### High (3)

#### Hardcoded signing credentials in app/build.gradle.kts — `android-hardcoded-signing`
- **severity:** high | **confidence:** likely | **category:** android | **horizon:** today
- **what:** The Gradle file "app/build.gradle.kts" contains 1 hardcoded signing password (storePassword/keyPassword) as literal strings inside signingConfigs.
- **why it matters:** Committing signing credentials leaks release-signing material into version control. Anyone with repo access (or git history) can sign builds that impersonate your app.
- **impact:** Removing 1 hardcoded signing secret eliminates leaked release-signing material. (1 count)
- **fix:** Move signing credentials to a git-ignored keystore.properties file or CI environment variables, and read them via System.getenv("...") or project.findProperty("...") in signingConfigs.
- **evidence:**
  - `app/build.gradle.kts:62` — storePassword "***"

#### 2 heavy font file(s) (high) — `assets-heavy-font-file`
- **severity:** high | **confidence:** confirmed | **category:** assets | **horizon:** this_sprint
- **what:** 2 font file(s) exceed the 488.3 KB threshold, totaling 31.5 MB.
- **why it matters:** Heavy font files significantly increase app size. Consider subsetting to include only the glyphs you need.
- **impact:** 31.5 MB could potentially be saved by subsetting these fonts. (33076160 bytes)
- **fix:** Subset the font to include only required glyphs, or switch to a variable font to reduce the number of files.
- **evidence:**
  - `app/src/main/res/font/source_han_sans_sc_medium.otf` (15.8 MB)
  - `app/src/main/res/font/source_han_sans_sc_regular.otf` (15.8 MB)

#### 2 oversized font file(s) (high) — `assets-oversized-font`
- **severity:** high | **confidence:** confirmed | **category:** assets | **horizon:** today
- **what:** Found 2 font file(s) exceeding the high size threshold, totalling 31.5 MB.
- **why it matters:** Large font files increase app bundle size, slow down downloads, and consume more device storage and memory.
- **impact:** 31.5 MB can be saved by optimizing these files. (33076160 bytes)
- **fix:** Compress or resize the font files, convert to a more efficient format (e.g., WebP for images), or consider lazy-loading.
- **evidence:**
  - `app/src/main/res/font/source_han_sans_sc_medium.otf` (15.8 MB)
  - `app/src/main/res/font/source_han_sans_sc_regular.otf` (15.8 MB)

### Low (6)

#### Release build missing resource shrinking in app/build.gradle.kts — `android-missing-shrink-resources`
- **severity:** low | **confidence:** likely | **category:** android | **horizon:** later
- **what:** The release build type in "app/build.gradle.kts" does not have shrinkResources set to true.
- **why it matters:** Without resource shrinking, unused resources remain in the APK, unnecessarily increasing bundle size.
- **impact:** Enabling resource shrinking removes unused resources from the final bundle.
- **fix:** Add "shrinkResources true" (or "isShrinkResources = true" in Kotlin DSL) to the release build type. Note: this requires minifyEnabled to be true.
- **evidence:**
  - `app/build.gradle.kts` — shrinkResources not set to true in release buildType

#### 1 heavy font file(s) (low) — `assets-heavy-font-file`
- **severity:** low | **confidence:** confirmed | **category:** assets | **horizon:** this_sprint
- **what:** 1 font file(s) exceed the 488.3 KB threshold, totaling 595.3 KB.
- **why it matters:** Heavy font files significantly increase app size. Consider subsetting to include only the glyphs you need.
- **impact:** 595.3 KB could potentially be saved by subsetting these fonts. (609600 bytes)
- **fix:** Subset the font to include only required glyphs, or switch to a variable font to reduce the number of files.
- **evidence:**
  - `app/src/main/res/font/inter_regular.otf` (595.3 KB)

#### 1 oversized font file(s) (low) — `assets-oversized-font`
- **severity:** low | **confidence:** confirmed | **category:** assets | **horizon:** this_sprint
- **what:** Found 1 font file(s) exceeding the low size threshold, totalling 595.3 KB.
- **why it matters:** Large font files increase app bundle size, slow down downloads, and consume more device storage and memory.
- **impact:** 595.3 KB can be saved by optimizing these files. (609600 bytes)
- **fix:** Compress or resize the font files, convert to a more efficient format (e.g., WebP for images), or consider lazy-loading.
- **evidence:**
  - `app/src/main/res/font/inter_regular.otf` (595.3 KB)

#### Gradle daemon heap tuned without a metaspace bound (1 file) — `repo-gradle-jvmargs-no-metaspace`
- **severity:** low | **confidence:** review_needed | **category:** config | **horizon:** this_sprint
- **what:** 1 gradle.properties file(s) set org.gradle.jvmargs with an explicit -Xmx heap bound but no -XX:MaxMetaspaceSize=. Overriding org.gradle.jvmargs replaces Gradle's default JVM args, dropping its default 256m metaspace cap.
- **why it matters:** A heap-tuned Gradle daemon with no metaspace bound can grow metaspace unbounded and OOM (java.lang.OutOfMemoryError: Metaspace) on large multi-module builds — an intermittent, machine-dependent build failure that is hard to diagnose.
- **impact:** Risk of intermittent Gradle daemon OutOfMemoryError (Metaspace) on large builds.
- **fix:** Add an explicit metaspace bound to org.gradle.jvmargs, e.g. `-XX:MaxMetaspaceSize=512m` alongside your -Xmx value.
- **evidence:**
  - `gradle.properties` — org.gradle.jvmargs has -Xmx but no -XX:MaxMetaspaceSize=

#### Gradle build cache not enabled — `repo-gradle-perf-buildcache`
- **severity:** low | **confidence:** likely | **category:** config | **horizon:** this_sprint
- **what:** The root gradle.properties does not set org.gradle.caching=true. The Gradle build cache is off by default, so every build re-executes cacheable tasks even when a previous build (or CI) already produced identical output.
- **why it matters:** Without the build cache, unchanged modules are rebuilt from scratch on every run, and CI cannot reuse task output across jobs — a silent, recurring waste of build time.
- **impact:** Cacheable Gradle tasks re-run on every build.
- **fix:** Add `org.gradle.caching=true` to the root gradle.properties.
- **evidence:**
  - `gradle.properties` — no org.gradle.caching=true

#### Gradle configuration cache not enabled (Gradle 9.x) — `repo-gradle-perf-configcache`
- **severity:** low | **confidence:** review_needed | **category:** config | **horizon:** this_sprint
- **what:** The root gradle.properties does not set org.gradle.configuration-cache=true, and this build runs Gradle 9.x where the configuration cache is opt-in. Without it, Gradle re-runs the configuration phase on every build instead of reusing a cached task graph.
- **why it matters:** Re-running configuration on every invocation is a silent, recurring build-time cost, especially on large multi-module builds. (The configuration cache can surface incompatible tasks — enable it and fix any reported problems, rather than assuming it is free.)
- **impact:** Configuration phase re-runs on every build.
- **fix:** Add `org.gradle.configuration-cache=true` to the root gradle.properties and resolve any incompatible-task problems Gradle reports.
- **evidence:**
  - `gradle.properties` — no org.gradle.configuration-cache=true

### Info (3)

#### Gradle configuration: app/build.gradle.kts — `android-gradle-overview`
- **severity:** info | **confidence:** confirmed | **category:** android | **horizon:** later
- **what:** Extracted Gradle build configuration from "app/build.gradle.kts": minSdk=26, targetSdk=36, compileSdk=36, applicationId=com.aegis.browser.
- **why it matters:** Understanding the Gradle configuration helps identify SDK targeting issues and build setup problems.
- **impact:** Informational overview of the Android build configuration.
- **fix:** Review SDK versions to ensure they align with your target audience and platform requirements.
- **evidence:**
  - `app/build.gradle.kts` — minSdk=26, targetSdk=36, compileSdk=36, applicationId=com.aegis.browser

#### Top 20 largest files in the repository — `assets-top-size-contributors`
- **severity:** info | **confidence:** confirmed | **category:** assets | **horizon:** later
- **what:** The 20 largest files account for 32.2 MB of repository size. Review these to identify optimization opportunities.
- **why it matters:** Understanding which files contribute most to repository size helps prioritize optimization efforts for maximum impact.
- **impact:** These 20 files total 32.2 MB. (33805039 bytes)
- **fix:** Review each large file to determine if it can be compressed, optimized, moved to a CDN, or removed if unused.
- **evidence:**
  - `app/src/main/res/font/source_han_sans_sc_medium.otf` (15.8 MB) — 15.8 MB
  - `app/src/main/res/font/source_han_sans_sc_regular.otf` (15.8 MB) — 15.8 MB
  - `app/src/main/res/font/inter_regular.otf` (595.3 KB) — 595.3 KB
  - `gradle/wrapper/gradle-wrapper.jar` (46.4 KB) — 46.4 KB
  - `detekt.yml` (21.6 KB) — 21.6 KB
  - `gradlew` (8.5 KB) — 8.5 KB
  - `app/src/main/java/com/aegis/browser/MainActivity.kt` (7.3 KB) — 7.3 KB
  - `app/src/main/java/com/aegis/browser/VerticalTabBar.kt` (5.3 KB) — 5.3 KB
  - `app/src/main/java/com/aegis/browser/TabManager.kt` (5.3 KB) — 5.3 KB
  - `app/src/main/java/com/aegis/browser/TabBar.kt` (4.1 KB) — 4.1 KB
  - `app/build.gradle.kts` (4.0 KB) — 4.0 KB
  - `gradlew.bat` (2.8 KB) — 2.8 KB
  - `app/detekt-baseline.xml` (2.1 KB) — 2.1 KB
  - `app/src/main/java/com/aegis/browser/BrowserEngine.kt` (2.1 KB) — 2.1 KB
  - `app/src/main/java/com/aegis/browser/AegisTheme.kt` (1.9 KB) — 1.9 KB
  - `app/src/main/java/com/aegis/browser/Tab.kt` (1.1 KB) — 1.1 KB
  - `app/src/main/AndroidManifest.xml` (1.1 KB) — 1.1 KB
  - `app/src/main/java/com/aegis/browser/UiColors.kt` (1.0 KB) — 1.0 KB
  - `app/src/main/java/com/aegis/browser/SecureWebViewFactory.kt` (963 B) — 963 B
  - `app/src/main/java/com/aegis/browser/DownloadPolicy.kt` (927 B) — 927 B

#### Module inventory: 2 module(s) detected — `structure-module-inventory`
- **severity:** info | **confidence:** confirmed | **category:** structure | **horizon:** later
- **what:** Found 2 module definition(s) across 1 type(s): Android/Gradle (Kotlin DSL): 2.
- **why it matters:** Understanding the module structure of the repository helps identify build dependencies, potential code sharing opportunities, and structural complexity.
- **impact:** 2 modules across 1 technology types. (2 count)
- **fix:** No action required. This is an informational finding for visibility into the repository structure.
- **evidence:**
  - `app/build.gradle.kts` — Android/Gradle (Kotlin DSL)
  - `build.gradle.kts` — Android/Gradle (Kotlin DSL)
