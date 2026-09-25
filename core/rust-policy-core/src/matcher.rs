//! 零依赖 glob 匹配器（照搬 Conalh/warden matcher.rs 核心算法）。
//!
//! 支持：
//! - `*`  跨段匹配（不跨越 `/`）
//! - `**` 跨段匹配（跨越 `/`）
//! - `?`  单字符匹配（不跨越 `/`）
//! - 字面字符精确匹配
//!
//! 用途：action-catalog 条件扩展、URL/域名模式匹配、工具名过滤。
//!
//! ```rust
//! use aegis_policy_core::matcher::glob_match;
//!
//! assert!(glob_match("src/**", "src/main.rs", false));
//! assert!(glob_match("*.json", "config.json", false));
//! assert!(!glob_match("*.json", "config.yaml", false));
//! // 注意：URL/host 匹配必须用 flat=false——flat=true 的 `*` 跨越 `/`，
//! // `https://*.gov.cn` 会误命中 `https://evil.com/x.gov.cn`（后缀拼接绕过）。
//! assert!(glob_match("https://*.gov.cn", "https://a.gov.cn", false));
//! ```

/// glob 匹配入口。
///
/// `pattern`：glob 模式（`*`/`**`/`?`/字面字符）。
/// `text`：待匹配文本。
/// `flat`：`true` 时 `*` 跨越 `/`（命令模式），`false` 时 `*` 不跨越 `/`（路径模式）。
pub fn glob_match(pattern: &str, text: &str, flat: bool) -> bool {
    // 输入有界：DP 缓存为 (pat+1)*(txt+1) 平方级——超长模式/文本直接
    // 拒绝匹配（此前可无界分配）。上限按字节数计（与历史口径一致）
    const MAX_GLOB_INPUT: usize = 16_384;
    if pattern.len() > MAX_GLOB_INPUT || text.len() > MAX_GLOB_INPUT {
        return false;
    }
    // RS-063（审计 2026-09-25）：ASCII 快路径——纯 ASCII 输入直接在
    // 字节切片上跑同一 DP（单字节存储，省去 Vec<char> 的 4× 元素膨胀
    // 与 UTF-8 解码）；非 ASCII 走字符路径。两路径语义逐 case 等价。
    if pattern.is_ascii() && text.is_ascii() {
        return run_match(
            pattern.as_bytes(),
            text.as_bytes(),
            &b'*',
            Some(&b'?'),
            Some(&b'/'),
            flat,
        );
    }
    let pat: Vec<char> = pattern.chars().collect();
    let txt: Vec<char> = text.chars().collect();
    run_match(&pat, &txt, &'*', Some(&'?'), Some(&'/'), flat)
}

/// RS-063：字节/字符双形态共用的迭代 DP（RS-015 自底向上，语义不变）。
/// `star`/`question`/`slash` 为语法字符占位（两种形态分别传字节/字符），
/// 字面匹配即 PartialEq 比较。
fn run_match<T: PartialEq>(
    pat: &[T],
    txt: &[T],
    star: &T,
    question: Option<&T>,
    slash: Option<&T>,
    flat: bool,
) -> bool {
    // 乘积上限：两侧同时接近 16K 时缓冲达 (16385)²≈256MiB——单条恶意
    // 规则+超长 URL 即可触发；4M 格（4MB）内完成匹配，超出直接拒绝
    const MAX_GLOB_CELLS: usize = 4 * 1024 * 1024;
    let width = txt.len() + 1;
    if (pat.len() + 1).saturating_mul(width) > MAX_GLOB_CELLS {
        return false;
    }
    let rows = pat.len() + 1;
    let mut dp = vec![false; rows * width];
    dp[pat.len() * width + txt.len()] = true; // pi == pat.len()：仅 ti == txt.len()
    for pi in (0..pat.len()).rev() {
        // 连续星号折叠：end 指向星号段之后（非星号时 end == pi）
        let is_star = pat[pi] == *star;
        let end = if is_star {
            let mut e = pi;
            while e < pat.len() && pat[e] == *star {
                e += 1;
            }
            e
        } else {
            pi
        };
        let is_question = question.is_some_and(|q| pat[pi] == *q);
        let spans_slash = flat || end - pi >= 2;
        // ti 降序：星号「吃一个字符」转移依赖同行星号行的 ti+1
        for ti in (0..width).rev() {
            let ok = if is_star {
                dp[end * width + ti]
                    || (ti < txt.len()
                        && (spans_slash || slash.is_none_or(|s| txt[ti] != *s))
                        && dp[pi * width + ti + 1])
            } else if is_question {
                ti < txt.len()
                    && (flat || slash.is_none_or(|s| txt[ti] != *s))
                    && dp[(pi + 1) * width + ti + 1]
            } else {
                ti < txt.len() && txt[ti] == pat[pi] && dp[(pi + 1) * width + ti + 1]
            };
            dp[pi * width + ti] = ok;
        }
    }
    dp[0]
}

/// 判断模式 `a` 是否**包含**模式 `b`（即 `a` 匹配的文本集合 ⊇ `b` 匹配的集合）。
/// 用于静态分析（shadowed/redundant 规则检测）。
///
/// RS-064（审计 2026-09-25）评估结论：维持现状，不引入缓存——tokenize
/// O(n) + covers O(n·m) 已是线性 DP；调用点（action-catalog 静态分析）
/// 规则集规模小且固定；缓存需跨调用可变状态，违背 core「无状态/确定性」
/// 蓝图约束。
pub fn glob_subsumes(a: &str, b: &str, flat: bool) -> bool {
    // RS-016（审计 2026-09-24）：输入上限——与 glob_match 同口径（16K）。
    // 此前无上限：超长模式直接进 tokenize+covers，DP 表无界分配
    const MAX_GLOB_INPUT: usize = 16_384;
    if a.len() > MAX_GLOB_INPUT || b.len() > MAX_GLOB_INPUT {
        return false;
    }
    let a_tok = tokenize(a);
    let b_tok = tokenize(b);
    covers(&a_tok, &b_tok, flat)
}

#[derive(Clone, Debug, PartialEq)]
enum Tok {
    Star,
    DStar,
    Any1,
    Lit(char),
}

fn tokenize(pattern: &str) -> Vec<Tok> {
    let chars: Vec<char> = pattern.chars().collect();
    let mut toks = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        match chars[i] {
            '*' => {
                let start = i;
                while i < chars.len() && chars[i] == '*' {
                    i += 1;
                }
                toks.push(if i - start >= 2 {
                    Tok::DStar
                } else {
                    Tok::Star
                });
            }
            '?' => {
                toks.push(Tok::Any1);
                i += 1;
            }
            c => {
                toks.push(Tok::Lit(c));
                i += 1;
            }
        }
    }
    toks
}

/// covers 的迭代 DP（RS-015：此前裸递归无记忆化——对抗性模式呈指数
/// 展开，且递归深度可达 a.len()+b.len()）。
///
/// 转移与旧递归逐 case 对照（语义不变）：
/// - b 耗尽：a 的剩余片段必须整体可匹配空（全星号）——边界列
/// - a 耗尽：false（边界默认值）
/// - (DStar, _)：cov[ai+1][bi] ∨ cov[ai][bi+1]
/// - (Star, DStar)：仅 flat（单星不覆盖双星语言——宁漏勿误）
/// - (Star, Star)：锁步推进
/// - (Star, 其他)：非 flat 遇字面 `/` 不可覆盖；否则 cov[ai][bi+1]
/// - (_, Star|DStar)：false
/// - (Any1, Any1)：锁步；(Any1, Lit)：非 flat 遇 `/` 拒绝，否则锁步
/// - (Lit, Any1)：false；(Lit, Lit)：相等锁步
fn covers(a: &[Tok], b: &[Tok], flat: bool) -> bool {
    if b.is_empty() {
        // b 为空模式：a 的全部片段必须可匹配空
        return a.iter().all(|t| matches!(t, Tok::Star | Tok::DStar));
    }
    // RS-062 延伸（审计 2026-09-25）：covers 此前只有 16K 输入上限、无
    // 乘积上限——两侧均近 16K 时缓冲达 (16385)²≈268MiB（RS-016 只堵了
    // 一半）。与 glob_match 同口径：超 4M 格 fail-closed 拒绝（语义为
    // 「不包含」，静态分析侧仅可能漏报 shadowed，不会误杀）
    const MAX_GLOB_CELLS: usize = 4 * 1024 * 1024;
    if (a.len() + 1).saturating_mul(b.len() + 1) > MAX_GLOB_CELLS {
        return false;
    }
    let width = b.len() + 1;
    let mut cov = vec![false; (a.len() + 1) * width];
    // 边界列 bi == b.len()：a[ai..] 必须全为星号（可匹配空）
    for ai in 0..=a.len() {
        cov[ai * width + b.len()] = a[ai..].iter().all(|t| matches!(t, Tok::Star | Tok::DStar));
    }
    // bi 降序（依赖 bi+1 列），ai 降序（DStar 依赖同列 ai+1）
    for bi in (0..b.len()).rev() {
        for ai in (0..a.len()).rev() {
            let at = |i: usize, j: usize| cov[i * width + j];
            let ok = match (&a[ai], &b[bi]) {
                (Tok::DStar, _) => at(ai + 1, bi) || at(ai, bi + 1),
                (Tok::Star, Tok::DStar) => flat && at(ai + 1, bi + 1),
                (Tok::Star, Tok::Star) => at(ai + 1, bi + 1),
                (Tok::Star, _) => (flat || !matches!(b[bi], Tok::Lit('/'))) && at(ai, bi + 1),
                (_, Tok::Star | Tok::DStar) => false,
                (Tok::Any1, Tok::Any1) => at(ai + 1, bi + 1),
                (Tok::Any1, Tok::Lit(_)) => {
                    (flat || !matches!(b[bi], Tok::Lit('/'))) && at(ai + 1, bi + 1)
                }
                (Tok::Lit(_), Tok::Any1) => false,
                (Tok::Lit(ca), Tok::Lit(cb)) => ca == cb && at(ai + 1, bi + 1),
            };
            cov[ai * width + bi] = ok;
        }
    }
    cov[0]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn literal_match() {
        assert!(glob_match("hello", "hello", false));
        assert!(!glob_match("hello", "world", false));
    }

    #[test]
    fn star_within_segment() {
        assert!(glob_match("*.rs", "main.rs", false));
        assert!(!glob_match("*.rs", "src/main.rs", false));
    }

    #[test]
    fn double_star_spans_segments() {
        assert!(glob_match("src/**", "src/main.rs", false));
        assert!(glob_match("**/*.rs", "src/lib/main.rs", false));
    }

    #[test]
    fn question_mark_is_one_char() {
        assert!(glob_match("f?o", "foo", false));
        assert!(!glob_match("f?o", "fooo", false));
        assert!(!glob_match("f?o", "fo", false));
    }

    #[test]
    fn flat_scope_lets_star_cross_slash() {
        assert!(glob_match("*.rs", "src/main.rs", true));
    }

    #[test]
    fn url_pattern() {
        assert!(glob_match("https://*.gov.cn", "https://a.gov.cn", true));
        assert!(!glob_match("https://*.gov.cn", "https://evil.com", true));
    }

    #[test]
    fn subsumes_reflexive() {
        assert!(glob_subsumes("src/**", "src/**", false));
    }

    #[test]
    fn subsumes_catch_all() {
        assert!(glob_subsumes("**", "src/main.rs", false));
    }

    // —— 边界补强：输入边界与 subsumes 非平凡关系 ——

    #[test]
    fn empty_identity() {
        assert!(glob_match("", "", false));
        assert!(!glob_match("", "a", false));
        assert!(!glob_match("a", "", false));
        // 全捕获模式能覆盖空文本
        assert!(glob_match("*", "", false));
        assert!(glob_match("**", "", false));
    }

    #[test]
    fn consecutive_stars_span_slashes() {
        // `a**b` 与 `a*b` 不同：`**` 跨 `/`，单 `*` 不跨（非 flat）
        assert!(glob_match("a**b", "a/x/b", false));
        assert!(!glob_match("a*b", "a/x/b", false));
        // 两个独立单星各自只在段内贪婪，都不跨 `/`
        assert!(glob_match("a*b*c", "axbyc", false));
        assert!(!glob_match("a*x*b", "a/x/y/b", false));
    }

    #[test]
    fn suffix_glob() {
        assert!(glob_match("*.gov.cn", "www.example.gov.cn", false));
        assert!(!glob_match("*.gov.cn", "www.example.gov.cn.evil", false));
        assert!(glob_match("*example.com", "https://sub.example.com", true));
    }

    #[test]
    fn oversized_input_rejected() {
        let long = "a".repeat(20_000);
        assert!(!glob_match(&long, "x", false));
        assert!(!glob_match("x", &long, false));
    }

    #[test]
    fn product_overflow_rejected() {
        // RS-008 回归：两侧均在 16K 上限内、但乘积超 4M 格时必须拒绝——
        // 此前分配 (16385)²≈256MiB 缓冲，单条恶意规则即可触发
        let pat = format!("*{}", "a".repeat(15_000));
        let txt = format!("{}b", "b".repeat(15_000));
        assert!(!glob_match(&pat, &txt, false));
        // 乘积在限内的正常匹配不受影响（字面相等可命中）
        let small = "a".repeat(90);
        assert!(glob_match(&small, &small, false));
    }

    #[test]
    fn question_mark_does_not_span_slash() {
        assert!(!glob_match("a?b", "a/b", false));
        assert!(glob_match("a?b", "a/b", true));
    }

    #[test]
    fn subsumes_dstar_covers_star() {
        // `**`（跨段）覆盖单 `*`（单段）与字面量
        assert!(glob_subsumes("**", "*", false));
        assert!(glob_subsumes("**.rs", "*.rs", false));
        assert!(glob_subsumes("**.rs", "data/settings.rs", false));
        // 反之不成立：单 `*` 不覆盖 `**`
        assert!(!glob_subsumes("*.rs", "**.rs", false));
    }

    #[test]
    fn subsumes_rejects_differing_literals() {
        assert!(!glob_subsumes("*.rs", "*.py", false));
        assert!(!glob_subsumes("src/**", "lib/**", false));
        // 完全相等仍覆盖
        assert!(glob_subsumes("a/b/*.rs", "a/b/*.rs", false));
    }

    #[test]
    fn subsumes_b_exhausted_requires_empty_matchable_tail() {
        // b 耗尽时 a 的剩余必须是可匹配空的全星尾——字面量尾巴覆盖不了更短文本
        assert!(!glob_subsumes("x*", "", false));
        assert!(!glob_subsumes("*x", "", false));
        // `**x*` 含字面量 x——匹配不了空串，同样不覆盖空模式
        assert!(!glob_subsumes("**x*", "", false));
        assert!(glob_subsumes("**", "", false));
        assert!(glob_subsumes("*", "", false));
    }

    // —— RS-015/016 回归（审计 2026-09-24） ——

    #[test]
    fn subsumes_oversized_input_rejected() {
        // RS-016：glob_subsumes 输入上限——此前无界进 tokenize+covers
        let long = "a".repeat(20_000);
        assert!(!glob_subsumes(&long, "x", false));
        assert!(!glob_subsumes("x", &long, false));
    }

    #[test]
    fn subsumes_adversarial_double_stars_terminates() {
        // RS-015：迭代 DP 下对抗性双星串即时完成（此前裸递归指数展开）
        let a = "**a".repeat(300);
        let b = "**b".repeat(300);
        assert!(!glob_subsumes(&a, &b, false));
        assert!(glob_subsumes(&a, &a, false));
    }

    // —— RS-061/062 回归（审计 2026-09-25） ——

    #[test]
    fn subsumes_any1_and_slash_semantics() {
        // RS-061：Any1 对 '/' 的覆盖受 flat 门控（宁漏勿误）
        assert!(!glob_subsumes("a?c", "a/c", false), "非 flat：? 不覆盖 /");
        assert!(glob_subsumes("a?c", "a/c", true), "flat：? 可覆盖 /");
        assert!(glob_subsumes("a?c", "abc", false), "Any1 与字面量锁步");
        // 交错 Any1：glob_match 侧同步验证
        assert!(glob_match("a?b?c", "axbyc", false));
        assert!(!glob_match("a?b?c", "axbycz", false));
    }

    #[test]
    fn unicode_literals_match_and_subsume() {
        // RS-061：unicode 字面量（非 ASCII 字符路径）匹配与覆盖
        assert!(glob_match("café*", "café au lait", false));
        assert!(!glob_match("café", "cafe", false), "带变音符不等价 ASCII");
        assert!(glob_subsumes("café*", "café.png", false));
        assert!(!glob_subsumes("café*", "cafe.png", false));
        // 混合 ASCII 模式 + 非 ASCII 文本（unicode 路径 + 星号转移）
        assert!(glob_match("a*b", "aαβb", false));
    }

    #[test]
    fn exact_input_boundary_16384() {
        // RS-062：恰 16384（输入上限内）放行，16385（超限）拒绝。
        // 模式用全星串——对短文本语义可匹配（字面量长模式无法匹配
        // 空文本），且乘积 4M 格上限要求另一侧极短
        let ok_pat = "*".repeat(16_384);
        assert_eq!(ok_pat.len(), 16_384);
        assert!(glob_match(&ok_pat, "", false), "恰 16384 进入匹配");
        assert!(glob_match(&ok_pat, "x", false));
        let over_pat = "*".repeat(16_385);
        assert_eq!(over_pat.len(), 16_385);
        assert!(!glob_match(&over_pat, "", false), "16385 超输入上限");
        // 文本侧同口径（模式侧极短：单星 + 尾字面）
        let ok_txt = format!("{}b", "b".repeat(16_383));
        assert_eq!(ok_txt.len(), 16_384);
        assert!(glob_match("*b", &ok_txt, false));
        let over_txt = format!("{}b", "b".repeat(16_384));
        assert_eq!(over_txt.len(), 16_385);
        assert!(!glob_match("*b", &over_txt, false));
    }

    #[test]
    fn subsumes_exact_input_boundary_16384() {
        // RS-062：glob_subsumes 同口径边界——全星模式覆盖任意单字面量
        let ok = "*".repeat(16_384);
        assert_eq!(ok.len(), 16_384);
        assert!(glob_subsumes(&ok, "x", false), "恰 16384 进入覆盖判定");
        let over = "*".repeat(16_385);
        assert_eq!(over.len(), 16_385);
        assert!(!glob_subsumes(&over, "x", false), "16385 超输入上限");
    }

    #[test]
    fn covers_product_overflow_rejected() {
        // RS-062 延伸：covers 此前无乘积上限——两侧均近 16K 时
        // 分配 (16385)²≈268MiB（RS-016 只堵了输入上限）。超 4M 格
        // fail-closed 拒绝；限内正常覆盖不受影响
        let pat = format!("*{}", "a".repeat(15_000));
        assert!(!glob_subsumes(&pat, &pat, false));
        // 限内正常覆盖不受影响
        let small = "a".repeat(100);
        assert!(glob_subsumes(&small, &small, false));
    }
}
