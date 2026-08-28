# Design System Inspired by Apple

## 1. Visual Theme & Atmosphere

Apple's website is a masterclass in controlled drama — vast expanses of pure black and near-white serve as cinematic backdrops for products that are photographed as if they were sculptures in a gallery. The design philosophy is reductive to its core: every pixel exists in service of the product, and the interface itself retreats until it becomes invisible. This is not minimalism as aesthetic preference; it is minimalism as reverence for the object.

The typography anchors everything. San Francisco (SF Pro Display for large sizes, SF Pro Text for body) is Apple's proprietary typeface, engineered with optical sizing that automatically adjusts letterforms depending on point size. At display sizes (56px), weight 600 with a tight line-height of 1.07 and subtle negative letter-spacing (-0.28px) creates headlines that feel machined rather than typeset — precise, confident, and unapologetically direct. At body sizes (17px), the tracking loosens slightly (-0.374px) and line-height opens to 1.47, creating a reading rhythm that is comfortable without ever feeling slack.

The color story is starkly binary. Product sections alternate between pure black (`#000000`) backgrounds with white text and light gray (`#f5f5f7`) backgrounds with near-black text (`#1d1d1f`). This creates a cinematic pacing — dark sections feel immersive and premium, light sections feel open and informational. The only chromatic accent is Apple Blue (`#0071e3`), reserved exclusively for interactive elements: links, buttons, and focus states. This singular accent color in a sea of neutrals gives every clickable element unmistakable visibility.

**Key Characteristics:**
- SF Pro Display/Text with optical sizing — letterforms adapt automatically to size context
- Binary light/dark section rhythm: black (`#000000`) alternating with light gray (`#f5f5f7`)
- Single accent color: Apple Blue (`#0071e3`) reserved exclusively for interactive elements
- Product-as-hero photography on solid color fields — no gradients, no textures, no distractions
- Extremely tight headline line-heights (1.07-1.14) creating compressed, billboard-like impact
- Full-width section layout with centered content — the viewport IS the canvas
- Pill-shaped CTAs (980px radius) creating soft, approachable action buttons
- Generous whitespace between sections allowing each product moment to breathe

## 2. Color Palette & Roles

### Primary
- **Pure Black** (`#000000`): Hero section backgrounds, immersive product showcases. The darkest canvas for the brightest products.
- **Light Gray** (`#f5f5f7`): Alternate section backgrounds, informational areas. Not white — the slight blue-gray tint prevents sterility.
- **Near Black** (`#1d1d1f`): Primary text on light backgrounds, dark button fills. Slightly warmer than pure black for comfortable reading.

### Interactive
- **Apple Blue** (`#0071e3`): `--sk-focus-color`, primary CTA backgrounds, focus rings. The ONLY chromatic color in the interface.
- **Link Blue** (`#0066cc`): `--sk-body-link-color`, inline text links. Slightly darker than Apple Blue for text-level readability.
- **Bright Blue** (`#2997ff`): Links on dark backgrounds. Higher luminance for contrast on black sections.

### Text
- **White** (`#ffffff`): Text on dark backgrounds, button text on blue/dark CTAs.
- **Near Black** (`#1d1d1f`): Primary body text on light backgrounds.
- **Black 80%** (`rgba(0, 0, 0, 0.8)`): Secondary text, nav items on light backgrounds. Slightly softened.
- **Black 48%** (`rgba(0, 0, 0, 0.48)`): Tertiary text, disabled states, carousel controls.

### Surface & Dark Variants
- **Dark Surface 1** (`#272729`): Card backgrounds in dark sections.
- **Dark Surface 2** (`#262628`): Subtle surface variation in dark contexts.
- **Dark Surface 3** (`#28282a`): Elevated cards on dark backgrounds.
- **Dark Surface 4** (`#2a2a2d`): Highest dark surface elevation.
- **Dark Surface 5** (`#242426`): Deepest dark surface tone.

### Button States
- **Button Active** (`#ededf2`): Active/pressed state for light buttons.
- **Button Default Light** (`#fafafc`): Search/filter button backgrounds.
- **Overlay** (`rgba(210, 210, 215, 0.64)`): Media control scrims, overlays.
- **White 32%** (`rgba(255, 255, 255, 0.32)`): Hover state on dark modal close buttons.

### Shadows
- **Card Shadow** (`rgba(0, 0, 0, 0.22) 3px 5px 30px 0px`): Soft, diffused elevation for product cards. Offset and wide blur create a natural, photographic shadow.

## 3. Typography Rules

### Font Family
- **Display**: `SF Pro Display`, with fallbacks: `SF Pro Icons, Helvetica Neue, Helvetica, Arial, sans-serif`
- **Body**: `SF Pro Text`, with fallbacks: `SF Pro Icons, Helvetica Neue, Helvetica, Arial, sans-serif`
- SF Pro Display is used at 20px and above; SF Pro Text is optimized for 19px and below.

### Hierarchy

| Role | Font | Size | Weight | Line Height | Letter Spacing | Notes |
|------|------|------|--------|-------------|----------------|-------|
| Display Hero | SF Pro Display | 56px (3.50rem) | 600 | 1.07 (tight) | -0.28px | Product launch headlines, maximum impact |
| Section Heading | SF Pro Display | 40px (2.50rem) | 600 | 1.10 (tight) | normal | Feature section titles |
| Tile Heading | SF Pro Display | 28px (1.75rem) | 400 | 1.14 (tight) | 0.196px | Product tile headlines |
| Card Title | SF Pro Display | 21px (1.31rem) | 700 | 1.19 (tight) | 0.231px | Bold card headings |
| Sub-heading | SF Pro Display | 21px (1.31rem) | 400 | 1.19 (tight) | 0.231px | Regular card headings |
| Nav Heading | SF Pro Text | 34px (2.13rem) | 600 | 1.47 | -0.374px | Large navigation headings |
| Sub-nav | SF Pro Text | 24px (1.50rem) | 300 | 1.50 | normal | Light sub-navigation text |
| Body | SF Pro Text | 17px (1.06rem) | 400 | 1.47 | -0.374px | Standard reading text |
| Body Emphasis | SF Pro Text | 17px (1.06rem) | 600 | 1.24 (tight) | -0.374px | Emphasized body text, labels |
| Button Large | SF Pro Text | 18px (1.13rem) | 300 | 1.00 (tight) | normal | Large button text, light weight |
| Button | SF Pro Text | 17px (1.06rem) | 400 | 2.41 (relaxed) | normal | Standard button text |
| Link | SF Pro Text | 14px (0.88rem) | 400 | 1.43 | -0.224px | Body links, "Learn more" |
| Caption | SF Pro Text | 14px (0.88rem) | 400 | 1.29 (tight) | -0.224px | Secondary text, descriptions |
| Caption Bold | SF Pro Text | 14px (0.88rem) | 600 | 1.29 (tight) | -0.224px | Emphasized captions |
| Micro | SF Pro Text | 12px (0.75rem) | 400 | 1.33 | -0.12px | Fine print, footnotes |
| Micro Bold | SF Pro Text | 12px (0.75rem) | 600 | 1.33 | -0.12px | Bold fine print |
| Nano | SF Pro Text | 10px (0.63rem) | 400 | 1.47 | -0.08px | Legal text, smallest size |

### Principles
- **Optical sizing as philosophy**: SF Pro automatically switches between Display and Text optical sizes. Display versions have wider letter spacing and thinner strokes optimized for large sizes; Text versions are tighter and sturdier for small sizes. This means the font literally changes its DNA based on context.
- **Weight restraint**: The scale spans 300 (light) to 700 (bold) but most text lives at 400 (regular) and 600 (semibold). Weight 300 appears only on large decorative text. Weight 700 is rare, used only for bold card titles.
- **Negative tracking at all sizes**: Unlike most systems that only track headlines, Apple applies subtle negative letter-spacing even at body sizes (-0.374px at 17px, -0.224px at 14px, -0.12px at 12px). This creates universally tight, efficient text.
- **Extreme line-height range**: Headlines compress to 1.07 while body text opens to 1.47, and some button contexts stretch to 2.41. This dramatic range creates clear visual hierarchy through rhythm alone.

## 4. Component Stylings

### Buttons

**Primary Blue (CTA)**
- Background: `#0071e3` (Apple Blue)
- Text: `#ffffff`
- Padding: 8px 15px
- Radius: 8px
- Border: 1px solid transparent
- Font: SF Pro Text, 17px, weight 400
- Hover: background brightens slightly
- Active: `#ededf2` background shift
- Focus: `2px solid var(--sk-focus-color, #0071E3)` outline
- Use: Primary call-to-action ("Buy", "Shop iPhone")

**Primary Dark**
- Background: `#1d1d1f`
- Text: `#ffffff`
- Padding: 8px 15px
- Radius: 8px
- Font: SF Pro Text, 17px, weight 400
- Use: Secondary CTA, dark variant

**Pill Link (Learn More / Shop)**
- Background: transparent
- Text: `#0066cc` (light bg) or `#2997ff` (dark bg)
- Radius: 980px (full pill)
- Border: 1px solid `#0066cc`
- Font: SF Pro Text, 14px-17px
- Hover: underline decoration
- Use: "Learn more" and "Shop" links — the signature Apple inline CTA

**Filter / Search Button**
- Background: `#fafafc`
- Text: `rgba(0, 0, 0, 0.8)`
- Padding: 0px 14px
- Radius: 11px
- Border: 3px solid `rgba(0, 0, 0, 0.04)`
- Focus: `2px solid var(--sk-focus-color, #0071E3)` outline
- Use: Search bars, filter controls

**Media Control**
- Background: `rgba(210, 210, 215, 0.64)`
- Text: `rgba(0, 0, 0, 0.48)`
- Radius: 50% (circular)
- Active: scale(0.9), background shifts
- Focus: `2px solid var(--sk-focus-color, #0071e3)` outline, white bg, black text
- Use: Play/pause, carousel arrows

### Cards & Containers
- Background: `#f5f5f7` (light) or `#272729`-`#2a2a2d` (dark)
- Border: none (borders are rare in Apple's system)
- Radius: 5px-8px
- Shadow: `rgba(0, 0, 0, 0.22) 3px 5px 30px 0px` for elevated product cards
- Content: centered, generous padding
- Hover: no standard hover state — cards are static, links within them are interactive

### Navigation
- Background: `rgba(0, 0, 0, 0.8)` (translucent dark) with `backdrop-filter: saturate(180%) blur(20px)`
- Height: 48px (compact)
- Text: `#ffffff` at 12px, weight 400
- Active: underline on hover
- Logo: Apple logomark (SVG) centered or left-aligned, 17x48px viewport
- Mobile: collapses to hamburger with full-screen overlay menu
- The nav floats above content, maintaining its dark translucent glass regardless of section background

### Image Treatment
- Products on solid-color fields (black or white) — no backgrounds, no context, just the object
- Full-bleed section images that span the entire viewport width
- Product photography at extremely high resolution with subtle shadows
- Lifestyle images confined to rounded-corner containers (12px+ radius)

### Distinctive Components

**Product Hero Module**
- Full-viewport-width section with solid background (black or `#f5f5f7`)
- Product name as the primary headline (SF Pro Display, 56px, weight 600)
- One-line descriptor below in lighter weight
- Two pill CTAs side by side: "Learn more" (outline) and "Buy" / "Shop" (filled)

**Product Grid Tile**
- Square or near-square card on contrasting background
- Product image dominating 60-70% of the tile
- Product name + one-line description below
- "Learn more" and "Shop" link pair at bottom

**Feature Comparison Strip**
- Horizontal scroll of product variants
- Each variant as a vertical card with image, name, and key specs
- Minimal chrome — the products speak for themselves

## 5. Layout Principles

### Spacing System
- Base unit: 8px
- Scale: 2px, 4px, 5px, 6px, 7px, 8px, 9px, 10px, 11px, 14px, 15px, 17px, 20px, 24px
- Notable characteristic: the scale is dense at small sizes (2-11px) with granular 1px increments, then jumps in larger steps. This allows precise micro-adjustments for typography and icon alignment.

### Grid & Container
- Max content width: approximately 980px (the recurring "980px radius" in pill buttons echoes this width)
- Hero: full-viewport-width sections with centered content block
- Product grids: 2-3 column layouts within centered container
- Single-column for hero moments — one product, one message, full attention
- No visible grid lines or gutters — spacing creates implied structure

### Whitespace Philosophy
- **Cinematic breathing room**: Each product section occupies a full viewport height (or close to it). The whitespace between products is not empty — it is the pause between scenes in a film.
- **Vertical rhythm through color blocks**: Rather than using spacing alone to separate sections, Apple uses alternating background colors (black, `#f5f5f7`, white). Each color change signals a new "scene."
- **Compression within, expansion between**: Text blocks are tightly set (negative letter-spacing, tight line-heights) while the space surrounding them is vast. This creates a tension between density and openness.

### Border Radius Scale
- Micro (5px): Small containers, link tags
- Standard (8px): Buttons, product cards, image containers
- Comfortable (11px): Search inputs, filter buttons
- Large (12px): Feature panels, lifestyle image containers
- Full Pill (980px): CTA links ("Learn more", "Shop"), navigation pills
- Circle (50%): Media controls (play/pause, arrows)

## 6. Depth & Elevation

| Level | Treatment | Use |
|-------|-----------|-----|
| Flat (Level 0) | No shadow, solid background | Standard content sections, text blocks |
| Navigation Glass | `backdrop-filter: saturate(180%) blur(20px)` on `rgba(0,0,0,0.8)` | Sticky navigation bar — the glass effect |
| Subtle Lift (Level 1) | `rgba(0, 0, 0, 0.22) 3px 5px 30px 0px` | Product cards, floating elements |
| Media Control | `rgba(210, 210, 215, 0.64)` background with scale transforms | Play/pause buttons, carousel controls |
| Focus (Accessibility) | `2px solid #0071e3` outline | Keyboard focus on all interactive elements |

**Shadow Philosophy**: Apple uses shadow extremely sparingly. The primary shadow (`3px 5px 30px` with 0.22 opacity) is soft, wide, and offset — mimicking a diffused studio light casting a natural shadow beneath a physical object. This reinforces the "product as physical sculpture" metaphor. Most elements have NO shadow at all; elevation comes from background color contrast (dark card on darker background, or light card on slightly different gray).

### Decorative Depth
- Navigation glass: the translucent, blurred navigation bar is the most recognizable depth element, creating a sense of floating UI above scrolling content
- Section color transitions: depth is implied by the alternation between black and light gray sections rather than by shadows
- Product photography shadows: the products themselves cast shadows in their photography, so the UI doesn't need to add synthetic ones

## 7. Do's and Don'ts

### Do
- Use SF Pro Display at 20px+ and SF Pro Text below 20px — respect the optical sizing boundary
- Apply negative letter-spacing at all text sizes (not just headlines) — Apple tracks tight universally
- Use Apple Blue (`#0071e3`) ONLY for interactive elements — it must be the singular accent
- Alternate between black and light gray (`#f5f5f7`) section backgrounds for cinematic rhythm
- Use 980px pill radius for CTA links — the signature Apple link shape
- Keep product imagery on solid-color fields with no competing visual elements
- Use the translucent dark glass (`rgba(0,0,0,0.8)` + blur) for sticky navigation
- Compress headline line-heights to 1.07-1.14 — Apple headlines are famously tight

### Don't
- Don't introduce additional accent colors — the entire chromatic budget is spent on blue
- Don't use heavy shadows or multiple shadow layers — Apple's shadow system is one soft diffused shadow or nothing
- Don't use borders on cards or containers — Apple almost never uses visible borders (except on specific buttons)
- Don't apply wide letter-spacing to SF Pro — it is designed to run tight at every size
- Don't use weight 800 or 900 — the maximum is 700 (bold), and even that is rare
- Don't add textures, patterns, or gradients to backgrounds — solid colors only
- Don't make the navigation opaque — the glass blur effect is essential to the Apple UI identity
- Don't center-align body text — Apple body copy is left-aligned; only headlines center
- Don't use rounded corners larger than 12px on rectangular elements (980px is for pills only)

## 8. Responsive Behavior

### Breakpoints
| Name | Width | Key Changes |
|------|-------|-------------|
| Small Mobile | <360px | Minimum supported, single column |
| Mobile | 360-480px | Standard mobile layout |
| Mobile Large | 480-640px | Wider single column, larger images |
| Tablet Small | 640-834px | 2-column product grids begin |
| Tablet | 834-1024px | Full tablet layout, expanded nav |
| Desktop Small | 1024-1070px | Standard desktop layout begins |
| Desktop | 1070-1440px | Full layout, max content width |
| Large Desktop | >1440px | Centered with generous margins |

### Touch Targets
- Primary CTAs: 8px 15px padding creating ~44px touch height
- Navigation links: 48px height with adequate spacing
- Media controls: 50% radius circular buttons, minimum 44x44px
- "Learn more" pills: generous padding for comfortable tapping

### Collapsing Strategy
- Hero headlines: 56px Display → 40px → 28px on mobile, maintaining tight line-height proportionally
- Product grids: 3-column → 2-column → single column stacked
- Navigation: full horizontal nav → compact mobile menu (hamburger)
- Product hero modules: full-bleed maintained at all sizes, text scales down
- Section backgrounds: maintain full-width color blocks at all breakpoints — the cinematic rhythm never breaks
- Image sizing: products scale proportionally, never crop — the product silhouette is sacred

### Image Behavior
- Product photography maintains aspect ratio at all breakpoints
- Hero product images scale down but stay centered
- Full-bleed section backgrounds persist at every size
- Lifestyle images may crop on mobile but maintain their rounded corners
- Lazy loading for below-fold product images

## 9. Agent Prompt Guide

### Quick Color Reference
- Primary CTA: Apple Blue (`#0071e3`)
- Page background (light): `#f5f5f7`
- Page background (dark): `#000000`
- Heading text (light): `#1d1d1f`
- Heading text (dark): `#ffffff`
- Body text: `rgba(0, 0, 0, 0.8)` on light, `#ffffff` on dark
- Link (light bg): `#0066cc`
- Link (dark bg): `#2997ff`
- Focus ring: `#0071e3`
- Card shadow: `rgba(0, 0, 0, 0.22) 3px 5px 30px 0px`

### Example Component Prompts
- "Create a hero section on black background. Headline at 56px SF Pro Display weight 600, line-height 1.07, letter-spacing -0.28px, color white. One-line subtitle at 21px SF Pro Display weight 400, line-height 1.19, color white. Two pill CTAs: 'Learn more' (transparent bg, white text, 1px solid white border, 980px radius) and 'Buy' (Apple Blue #0071e3 bg, white text, 8px radius, 8px 15px padding)."
- "Design a product card: #f5f5f7 background, 8px border-radius, no border, no shadow. Product image top 60% of card on solid background. Title at 28px SF Pro Display weight 400, letter-spacing 0.196px, line-height 1.14. Description at 14px SF Pro Text weight 400, color rgba(0,0,0,0.8). 'Learn more' and 'Shop' links in #0066cc at 14px."
- "Build the Apple navigation: sticky, 48px height, background rgba(0,0,0,0.8) with backdrop-filter: saturate(180%) blur(20px). Links at 12px SF Pro Text weight 400, white text. Apple logo left, links centered, search and bag icons right."
- "Create an alternating section layout: first section black bg with white text and centered product image, second section #f5f5f7 bg with #1d1d1f text. Each section near full-viewport height with 56px headline and two pill CTAs below."
- "Design a 'Learn more' link: text #0066cc on light bg or #2997ff on dark bg, 14px SF Pro Text, underline on hover. After the text, include a right-arrow chevron character (>). Wrap in a container with 980px border-radius for pill shape when used as a standalone CTA."

### Iteration Guide
1. Every interactive element gets Apple Blue (`#0071e3`) — no other accent colors
2. Section backgrounds alternate: black for immersive moments, `#f5f5f7` for informational moments
3. Typography optical sizing: SF Pro Display at 20px+, SF Pro Text below — never mix
4. Negative letter-spacing at all sizes: -0.28px at 56px, -0.374px at 17px, -0.224px at 14px, -0.12px at 12px
5. The navigation glass effect (translucent dark + blur) is non-negotiable — it defines the Apple web experience
6. Products always appear on solid color fields — never on gradients, textures, or lifestyle backgrounds in hero moments
7. Shadow is rare and always soft: `3px 5px 30px 0.22 opacity` or nothing at all
8. Pill CTAs use 980px radius — this creates the signature Apple rounded-rectangle-that-looks-like-a-capsule shape

## 10. Application Chrome — Liquid Glass（液态玻璃）

Aegis 的浏览器外框（工具栏 / 标签栏 / 状态栏 / 查找栏 / 下载栏 / 新建标签页）采用 Apple 当前流行的 **Liquid Glass（液态玻璃）** 视觉：真正的系统级毛玻璃，而非一层半透明遮罩。

### 核心机制：Windows 原生 DWM 玻璃
- 主窗口通过 `Qt.WA_TranslucentBackground` + `QtWin.enableBlurBehindWindow(self)` 启用 **Windows DWM 原生背景模糊**。窗口的透明区域会真正透出被桌面/其他窗口实时模糊后的画面 —— 这是「真玻璃」与「假半透明叠加」的根本区别。
- 仅当平台为 Windows 且 PySide6 带 `QtWin` 时生效；整段用 `try/except` 包裹，在远程桌面 / 无 DWM 环境或 headless 测试时**静默降级为不透明**，绝不崩溃。
- 网页渲染区（`QWebEngineView`）保持不透明，只有外框呈玻璃，保证可读性与性能。

### 玻璃令牌（theme.py）
深色与浅色主题各有一组 `glass_*` 令牌，由 `build_qss` 组合成竖向渐变，模拟玻璃厚度：
- `glass_top`：顶部高光（浅色玻璃更亮，深色玻璃更暗）
- `glass_mid`：中段染色（玻璃的「体」）
- `glass_bottom`：底部内阴影（玻璃的厚度感）
- `rim`：上下 1px 细边（玻璃的边缘高光 / 暗边）

> 深色：top `rgba(255,255,255,0.18)` / mid `rgba(29,29,31,0.55)` / bottom `rgba(0,0,0,0.30)` / rim `rgba(255,255,255,0.16)`
> 浅色：top `rgba(255,255,255,0.78)` / mid `rgba(245,245,247,0.62)` / bottom `rgba(0,0,0,0.10)` / rim `rgba(0,0,0,0.10)`

### 组件映射
- **QMainWindow / BrowserTabWidget / QTabWidget::pane / QStackedWidget**：`background: transparent`，让玻璃与背景透出。
- **QToolBar（地址栏 / 标签栏所在工具栏）**：`qlineargradient`（stop:0 glass_top → stop:0.45 glass_mid → stop:1 glass_bottom）+ `rim` 上下边。
- **QLineEdit（地址栏 / 搜索框）**：glassy 渐变 pill，顶部加一道高光；聚焦时边框转 `#0071e3`。
- **QToolButton:hover**：高光 → hover 渐变。
- **查找栏 / 下载栏（#findBar / #downloadBar）**：复用 `glass_bar` + `rim`。
- **QPushButton:default（CTA）**：accent `#0071e3` 渐变，顶部一道白色高光，呈现「光面胶囊」质感。
- **QDialog**：保持不透明（`background-color: bg`），避免对话框也变玻璃导致文字难读。
- **标签页（tab_strip.py）**：当前 / 悬停标签绘制 **顶部镜面高光**（白 70→0 alpha）+ **底部内阴影**（0→黑 alpha），用圆角矩形叠出玻璃厚度。

### 新建标签页背景（glass.py）
- 原 `AuroraBackground` 的色块曾误用紫色（`#7a5cff` 等），已改为 **蓝 / 青 / 白**（`accent, #5ac8fa, #ffffff`），符合 Apple 蓝调且无紫。

### 合规约束（项目 P0）
- **不使用 emoji 图标**：所有图标走 `icons.py` 的 SVG。
- **不硬编码颜色**：全部经主题令牌 / 系统强调色（`#0071e3`）注入。
- **禁止紫色渐变**：`#7C3AED`/`#A855F7`/`#EC4899`/`#635BFF`/`linear-gradient(135deg)` 一律不用。

### 降级与测试
- 非 Windows / headless：DWM 调用被 `try/except` 吞掉，窗口以不透明外观正常运行（功能不受影响，只是少了毛玻璃）。
- 验证：全部 UI 文件 `py_compile` 通过；offscreen 烟测可正常构造主窗口并应用 Liquid Glass QSS（约 8.3KB 样式表），事件循环无致命错误。

---

## 11. v2.1.3 —— Fluent Mica × Apple Liquid Glass 融合重设计

本节记录 2.1.3 版 UI 重设计的决策与落地约束（Microsoft Edge / Fluent 2 与
Apple Liquid Glass 两套设计语言的取舍融合）。

### 设计语言取舍
- **窗口外框走 Fluent Mica**：活动标签与工具栏渐变**同色融合**（Edge 标志
  层级语言），标签为顶部大圆角卡片、相邻非活动标签间保留发丝分隔线。
- **输入与浮层走 Apple Liquid Glass**：地址栏 / 搜索框 / 主 CTA 为玻璃胶囊
  （镜面顶光 + 半透明填充 + 强调色聚焦环）；菜单 / 查找栏 / 下载栏为磨砂浮层。
- **单一强调色不变**：仍只有 Apple Blue（#0071e3，可切 #2997ff / #0066cc），
  全部进入 CSS/QSS 前经 `#RRGGBB` 白名单校验，杜绝样式注入。

### 令牌新增（theme.py）
- `_CHROME`：标签栏/工具栏云母配色（`tab_active` == 工具栏渐变首段，实现融合），
  经 `chrome(dark, accent)` 导出，供 QPainter 自绘与 QSS 同源。
- `RADIUS_TAB = 10`：标签顶部圆角。
- `RADIUS_CAPSULE = 20`：Qt QSS 胶囊控件圆角。

### Qt 渲染陷阱（实测，务必遵守）
- **Qt QSS 的 `border-radius` 超过控件半高后不会钳成胶囊，反而退化为小圆角。**
  因此 QSS 侧禁用 `RADIUS_PILL(980px)`，一律用 `RADIUS_CAPSULE`（≈控件半高）
  或按具体控件高度写死；`RADIUS_PILL` 仅供 HTML/CSS 页面使用（980px 真生效）。

### 新标签页（main_window._new_tab_page_html / new_tab_page.py）
- 背景为**多层 radial-gradient 蓝/青/白 mesh 光斑**（非纯平面），深浅两套；
- 速拨卡 = 顶部镜面高光 + 半透明填充 + 发丝边 + 软投影，悬停上浮 + 强调色描边；
- 安全不变式不变：CSP（script-src 'none' / form-action https:）、html.escape、
  safe_url 白名单、强调色白名单校验。

### 验证
- 全部 UI 文件 `py_compile` 通过；仓库 ruff 门禁 0 告警；
- `tools/selftest_security.py` 35 项全绿；
- offscreen 无头渲染实测：活动标签融合、玻璃胶囊、发丝分隔线均按预期呈现。

---

## 12. v2.1.4 —— 拨号图标系统（ui/icons_dial.py）

新标签页拨号图标从「标题第一个字」升级为 Apple 级 squircle：

- **形态**：圆角方块（radius 14/56 ≈ iOS 比例）+ 品牌垂直渐变 +
  顶部镜面高光 + 发丝边；未知站点按域名哈希取六色和谐渐变（无紫）+ 字母徽标。
- **已知品牌**：模块常量内置 20+ 站点的简化图形（内联 SVG 路径/文字）。
- **安全**：输出为**内联 SVG**（DOM 节点，非 `<img>` 资源），NTP 的
  CSP `img-src 'none'` 不需放宽；唯一动态片段是标题首字母，经
  `html.escape` 注入；无 `<script>`、无事件处理器属性。
- **双版一致**：HTML 版（main_window._new_tab_page_html）与 Qt 版
  （new_tab_page.DialCard）共用 `brand_palette()`/`brand_char()`，配色同源。
- **回退也要体面**：未知站点不再是灰底圆 + 随机首字，而是和谐渐变 +
  居中标注字母，视觉与已知站点同级。

---

## 13. v2.1.5 —— 随包壁纸 / 首页拨号自定义 / 垂直标签栏

### 随包壁纸（assets/wallpapers/ + app/asset_scheme.py）
- 4 张极光风壁纸随包分发；`ntp_wallpaper` 指定文件名，空=渐变背景。
- **安全加载**：只读自定义 scheme `aegisasset://`。scheme 须在
  QWebEngineProfile 创建前注册（main.py `ensure_registered()`），
  handler 装在 profile 上（browser.py）。
- **白名单 + 防穿越**：handler 只放行 `WALLPAPERS` 常量登记的文件名，
  拒绝含 `/` `\` `..` 的路径；host 段必须为 `wallpapers`；磁盘缺失即失败。
- **CSP 最小放宽**：NTP 的 `img-src` 从 `'none'` 改为 `aegisasset:`
  （只放行该 scheme，不放 data:/http:）。壁纸上叠主题 scrim 保证可读。

### 首页拨号自定义（app/dial_store.py + ui/dialogs.py DialsDialog）
- `dials.json` 持久化自定义拨号（name/url，顺序即展示顺序）；
  URL 仅 http/https，点击仍过 safe_url。自定义非空 → NTP 只用自定义列表。
- 工具菜单「自定义首页拨号…」：增删/排序/恢复默认。

### 垂直标签栏（Edge 风）
- `config.tabs_position: top|left`；视图菜单 / Ctrl+Shift+Y / 设置页切换。
- `BrowserTabBar.set_vertical()` → `QTabBar.RoundedWest`；
  `tabSizeHint` 返回 (212,36)；行式自绘 `_paint_tab_v`（图标+标题+关闭键，
  活动行云母填充 + 顶部高光 + 左侧强调色指示条；分组为左侧竖色带）。
- `BrowserTabWidget.set_tab_placement()` 同步 `QTabWidget.West/North`。

---

## 14. v2.1.6 —— 标签文字对比度（可读性是第一优先级）

- 原则：**深底白字、浅底黑字**，且均用**全不透明**文字。
- 非活动标签不再压暗文字（旧值 ~56% 透明→不可读），改为：
  文字 `tab_inactive_fg`（dark=#ffffff / light=#1d1d1f），
  并给每个非活动标签一个**可见底色** `tab_inactive_bg`（悬停 `tab_hover` 提亮）。
- 活动标签的区分靠「更亮底色 + 强调色指示条 + 加粗」，而非降低非活动文字亮度。
- 上方（`_paint_tab`）与垂直（`_paint_tab_v`）两种形态共用同一 `_CHROME` 令牌。
