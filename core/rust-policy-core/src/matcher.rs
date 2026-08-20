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
//! assert!(glob_match("https://*.gov.cn", "https://a.gov.cn", true));
//! ```

/// glob 匹配入口。
///
/// `pattern`：glob 模式（`*`/`**`/`?`/字面字符）。
/// `text`：待匹配文本。
/// `flat`：`true` 时 `*` 跨越 `/`（命令模式），`false` 时 `*` 不跨越 `/`（路径模式）。
pub fn glob_match(pattern: &str, text: &str, flat: bool) -> bool {
    let pat: Vec<char> = pattern.chars().collect();
    let txt: Vec<char> = text.chars().collect();
    let width = txt.len() + 1;
    let mut cache = vec![0u8; (pat.len() + 1) * width];
    matches_impl(&pat, &txt, 0, 0, flat, &mut cache, width)
}

fn matches_impl(
    pat: &[char],
    txt: &[char],
    pi: usize,
    ti: usize,
    flat: bool,
    cache: &mut [u8],
    width: usize,
) -> bool {
    let idx = pi * width + ti;
    match cache[idx] {
        1 => return true,
        2 => return false,
        _ => {}
    }
    let result = compute(pat, txt, pi, ti, flat, cache, width);
    cache[idx] = if result { 1 } else { 2 };
    result
}

fn compute(
    pat: &[char],
    txt: &[char],
    pi: usize,
    ti: usize,
    flat: bool,
    cache: &mut [u8],
    width: usize,
) -> bool {
    if pi == pat.len() {
        return ti == txt.len();
    }
    match pat[pi] {
        '*' => {
            // 连续星号折叠：两个及以上 = `**`（跨越 `/`），单个 `*` 保持段内——
            // 除非 flat=true（命令模式，每个 `*` 都跨越 `/`）。
            let mut end = pi;
            while end < pat.len() && pat[end] == '*' {
                end += 1;
            }
            let spans_slash = flat || end - pi >= 2;
            // 星号匹配空：跳过星号继续
            if matches_impl(pat, txt, end, ti, flat, cache, width) {
                return true;
            }
            // 星号匹配一个字符：跨越 `/` 或不跨越（取决于 spans_slash）
            ti < txt.len()
                && (spans_slash || txt[ti] != '/')
                && matches_impl(pat, txt, pi, ti + 1, flat, cache, width)
        }
        '?' => {
            ti < txt.len()
                && (flat || txt[ti] != '/')
                && matches_impl(pat, txt, pi + 1, ti + 1, flat, cache, width)
        }
        literal => {
            ti < txt.len()
                && txt[ti] == literal
                && matches_impl(pat, txt, pi + 1, ti + 1, flat, cache, width)
        }
    }
}

/// 判断模式 `a` 是否**包含**模式 `b`（即 `a` 匹配的文本集合 ⊇ `b` 匹配的集合）。
/// 用于静态分析（shadowed/redundant 规则检测）。
pub fn glob_subsumes(a: &str, b: &str, flat: bool) -> bool {
    let a_tok = tokenize(a);
    let b_tok = tokenize(b);
    covers(&a_tok, &b_tok, 0, 0, flat)
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

fn covers(a: &[Tok], b: &[Tok], ai: usize, bi: usize, flat: bool) -> bool {
    if bi == b.len() {
        return true;
    }
    if ai == a.len() {
        return false;
    }
    match (&a[ai], &b[bi]) {
        (Tok::DStar, _) => covers(a, b, ai + 1, bi, flat) || covers(a, b, ai, bi + 1, flat),
        (Tok::Star, Tok::Star) | (Tok::Star, Tok::DStar) => covers(a, b, ai + 1, bi + 1, flat),
        (Tok::Star, _) => {
            if flat || !matches!(b[bi], Tok::Lit('/')) {
                covers(a, b, ai, bi + 1, flat)
            } else {
                false
            }
        }
        (_, Tok::Star | Tok::DStar) => false,
        (Tok::Any1, Tok::Any1) => covers(a, b, ai + 1, bi + 1, flat),
        (Tok::Any1, Tok::Lit(_)) => {
            if flat || !matches!(b[bi], Tok::Lit('/')) {
                covers(a, b, ai + 1, bi + 1, flat)
            } else {
                false
            }
        }
        (Tok::Lit(_), Tok::Any1) => false,
        (Tok::Lit(ca), Tok::Lit(cb)) => {
            if ca == cb {
                covers(a, b, ai + 1, bi + 1, flat)
            } else {
                false
            }
        }
    }
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
        assert!(glob_match("https://*.gov.cn", "https://evil.com", true) == false);
    }

    #[test]
    fn subsumes_reflexive() {
        assert!(glob_subsumes("src/**", "src/**", false));
    }

    #[test]
    fn subsumes_catch_all() {
        assert!(glob_subsumes("**", "src/main.rs", false));
    }
}
