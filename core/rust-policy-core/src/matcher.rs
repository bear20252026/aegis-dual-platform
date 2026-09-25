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
    // 拒绝匹配（此前可无界分配）
    const MAX_GLOB_INPUT: usize = 16_384;
    // 乘积上限：两侧同时接近 16K 时缓冲达 (16385)²≈256MiB——单条恶意规则
    // +超长 URL 即可触发；4M 格（4MB）内完成匹配，超出直接拒绝
    const MAX_GLOB_CELLS: usize = 4 * 1024 * 1024;
    if pattern.len() > MAX_GLOB_INPUT || text.len() > MAX_GLOB_INPUT {
        return false;
    }
    let pat: Vec<char> = pattern.chars().collect();
    let txt: Vec<char> = text.chars().collect();
    let width = txt.len() + 1;
    if (pat.len() + 1).saturating_mul(width) > MAX_GLOB_CELLS {
        return false;
    }
    // RS-015（审计 2026-09-24）：自底向上迭代 DP——此前 memo 化递归深度
    // 可达 pat.len()+txt.len()≈32K 帧，嵌入式栈上有溢出风险。
    // 全表分配（字节数 ≤ MAX_GLOB_CELLS，与旧 cache 同量级）。
    let rows = pat.len() + 1;
    let mut dp = vec![false; rows * width];
    dp[pat.len() * width + txt.len()] = true; // pi == pat.len()：仅 ti == txt.len()
    for pi in (0..pat.len()).rev() {
        // 连续星号折叠：end 指向星号段之后（非星号时 end == pi）
        let end = if pat[pi] == '*' {
            let mut e = pi;
            while e < pat.len() && pat[e] == '*' {
                e += 1;
            }
            e
        } else {
            pi
        };
        let spans_slash = flat || end - pi >= 2;
        // ti 降序：星号「吃一个字符」转移依赖同行星号行的 ti+1
        for ti in (0..width).rev() {
            let ok = match pat[pi] {
                '*' => {
                    dp[end * width + ti]
                        || (ti < txt.len()
                            && (spans_slash || txt[ti] != '/')
                            && dp[pi * width + ti + 1])
                }
                '?' => ti < txt.len() && (flat || txt[ti] != '/') && dp[(pi + 1) * width + ti + 1],
                literal => ti < txt.len() && txt[ti] == literal && dp[(pi + 1) * width + ti + 1],
            };
            dp[pi * width + ti] = ok;
        }
    }
    dp[0]
}

/// 判断模式 `a` 是否**包含**模式 `b`（即 `a` 匹配的文本集合 ⊇ `b` 匹配的集合）。
/// 用于静态分析（shadowed/redundant 规则检测）。
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
}
