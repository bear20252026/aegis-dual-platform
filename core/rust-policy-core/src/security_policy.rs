/*
 * security_policy.rs — 集中安全策略（照搬 Omni Browser SecurityPolicy.kt 本地化适配）。
 *
 * 原始版权：Omni Browser - Copyright (C) 2026 RebelRoot Ltd
 * 原始许可：GNU General Public License v3.0
 * 来源：https://github.com/REBEL-ROOT/omni-browser
 * 改动：将 Kotlin 实现翻译为 Rust，适配 Aegis 架构。
 */

/// 安全导航 scheme 白名单。
const ALLOWED_NAVIGATION_SCHEMES: &[&str] = &["http", "https", "about", "file", "content"];

/// 外部意图危险 scheme 黑名单。
const DANGEROUS_EXTERNAL_SCHEMES: &[&str] =
    &["javascript", "data", "blob", "intent", "market", "chrome"];

/// Windows 保留设备名。
const RESERVED_NAMES: &[&str] = &[
    "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8",
    "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
];

const MAX_FILENAME_LENGTH: usize = 200;

/// 集中安全策略（照搬 Omni Browser SecurityPolicy）。
pub struct SecurityPolicy;

impl SecurityPolicy {
    /// 检查 scheme 是否为安全导航 scheme。
    ///
    /// 审计第六轮（2026-10-03）：`None` / `Some("")` 改为 **false**。此前
    /// 把「scheme 缺失/解析失败」当作相对 URL 放行（true）——在 fail-closed
    /// 裁决器里提取失败不是「合法」的证据，错误→ALLOW 是方向性缺陷：
    /// 上游解析畸形输入拿不到 scheme 时，调用方按本函数返回值即放行。
    /// 需要相对 URL 语义的调用方必须先自行补全 scheme 再判定。
    pub fn is_valid_navigation_scheme(scheme: Option<&str>) -> bool {
        match scheme {
            // 提取失败面：无 scheme / 空 scheme 一律拒绝（fail-closed）
            None | Some("") => false,
            Some(s) => ALLOWED_NAVIGATION_SCHEMES
                .iter()
                .any(|allowed| allowed.eq_ignore_ascii_case(s)),
        }
    }

    /// 检查 scheme 是否为外部意图危险 scheme（空返回 false）。
    pub fn is_dangerous_external_scheme(scheme: Option<&str>) -> bool {
        match scheme {
            None | Some("") => false,
            Some(s) => DANGEROUS_EXTERNAL_SCHEMES
                .iter()
                .any(|dangerous| dangerous.eq_ignore_ascii_case(s)),
        }
    }

    /// 文件名安全化（防路径遍历/空字节/控制字符/保留名攻击）。
    ///
    /// 处理：
    /// - URL 编码的遍历序列（%2e%2e%2f）
    /// - 空字节注入（%00, \u0000）
    /// - 控制字符（ASCII < 32）
    /// - 路径分隔符（../, ..\）
    /// - Windows 保留设备名（RS-114：截断后复查）
    ///   审计第六轮（2026-10-03）：基名按**首个**点切分（Win32 在首点截断
    ///   设备名——`CON.dll.exe` 仍是 CON），且 `_` 前缀在长度复查之前加入
    ///   （≤MAX 的名字加前缀后不得溢出）
    /// - RTL 双向控制符（RS-113：扩展名伪装面）
    /// - 过长文件名（保留扩展名）
    pub fn sanitize_filename(name: Option<&str>) -> String {
        let name = match name {
            None | Some("") => return "download".to_string(),
            Some(n) => n.trim(),
        };

        // URL 解码（捕获编码遍历序列——零依赖手动实现）
        let mut sanitized = Self::url_decode(name).unwrap_or_else(|| name.to_string());

        // 去空字节
        sanitized = sanitized.replace('\u{0000}', "");

        // RS-188（审计 2026-09-25）：控制字符与控制空白（\n \r \t）全部
        // 剥离——此前保留 \n\r\t 是"日志可读性"未论证的宽松口径：文件名
        // 内嵌换行在资源管理器/下载面板可做视觉伪装（名称截断伪造扩展名），
        // 且跨平台同步时行为不一致。剥离 = 空白类控制符与 >=0x20 可打印
        // 字符的两分口径，单一且可解释。
        sanitized.retain(|c| c as u32 >= 32);

        // RS-113（审计 2026-09-25）：剥 RTL 双向控制符——U+202E（RLO）等
        // 可把 "exe.jpg" 视觉伪装成 "gjp.exe"（扩展名伪装/钓鱼面）
        sanitized = sanitized
            .chars()
            .filter(|c| {
                !matches!(
                    c,
                    '\u{202A}'..='\u{202E}' | '\u{2066}'..='\u{2069}' | '\u{200E}' | '\u{200F}'
                )
            })
            .collect();

        // 去路径分隔符和遍历序列
        for sep in &["../", "..\\", "/", "\\", ":", "|", "?", "*", "\""] {
            sanitized = sanitized.replace(sep, "");
        }

        // 折叠剩余双点——RS-017（审计 2026-09-24）：单趟 replace 不闭合
        //（"...." 单趟后仍剩 ".."，嵌套遍历序列逃逸），fixpoint 循环到
        // 不再含 ".."。每趟 replace 严格缩短串长——必然终止
        while sanitized.contains("..") {
            sanitized = sanitized.replace("..", ".");
        }

        // 去首尾点/空格（Windows 兼容）
        sanitized = sanitized.trim_start_matches(['.', ' ']).to_string();
        sanitized = sanitized.trim_end_matches(['.', ' ']).to_string();

        if sanitized.is_empty() {
            return "download".to_string();
        }

        // 检查 Windows 保留设备名（RS-114：helper 抽出供截断后复查）
        Self::ensure_not_reserved(&mut sanitized);

        // 长度限制（保留扩展名）——全部经 floor_char_boundary 类似语义：
        // 字节索引切片落在多字节 UTF-8 字符中间即 panic（文件名攻击者可控）
        if sanitized.len() > MAX_FILENAME_LENGTH {
            if let Some(dot_pos) = sanitized.rfind('.') {
                let ext = &sanitized[dot_pos..];
                let max_base = MAX_FILENAME_LENGTH.saturating_sub(ext.len());
                let base_end = max_base.min(dot_pos);
                let base_end = floor_boundary(&sanitized, base_end);
                sanitized = format!("{}{}", &sanitized[..base_end], ext);
            } else {
                let cut = floor_boundary(&sanitized, MAX_FILENAME_LENGTH);
                sanitized.truncate(cut);
            }

            // RS-281（2026-10-02 审计）：截断后二次长度复查——扩展名自身
            // ≥ MAX 时 max_base 饱和 0，保扩展名重组后整体仍超限（文件名
            // 上限被突破）。超限整体截到 MAX（floor_boundary 字符边界内
            // 截断，多字节字符安全——Rust String 为 UTF-8，不存在孤立
            // 代理对形态）
            if sanitized.len() > MAX_FILENAME_LENGTH {
                let cut = floor_boundary(&sanitized, MAX_FILENAME_LENGTH);
                sanitized.truncate(cut);
            }

            // RS-114（审计 2026-09-25）：截断后复查保留名——此前检查仅在
            // 截断前执行，"CONX.ffff..." 截断后 base 变 "CON" 即绕过保留名
            // 消解（截断保头部，可把非保留 base 裁成保留名）
            if sanitized.is_empty() {
                return "download".to_string();
            }
            Self::ensure_not_reserved(&mut sanitized);
        }

        // 审计第六轮（2026-10-03）：长度上限复查移到保留名消解**之后**——
        // 此前 RS-281 的整体截断复查只跑在截断分支内、且早于该分支尾部的
        // `_` 前缀，恰好 ≤MAX 的保留名加前缀后变 MAX+1（200 → 201），文档
        // 上限被突破 1 字节。截断只保头部，前缀已在首字符（基名变 "_…"
        // 形态，ensure_not_reserved 幂等不再追加），故无需再复查保留名
        if sanitized.len() > MAX_FILENAME_LENGTH {
            let cut = floor_boundary(&sanitized, MAX_FILENAME_LENGTH);
            sanitized.truncate(cut);
        }

        if sanitized.is_empty() {
            "download".to_string()
        } else {
            sanitized
        }
    }
}

/// 向下取整到 UTF-8 字符边界（cut 处落在多字节字符中间时回退到字符起点）。
/// 文件名截断用——字节切片落在多字节 UTF-8 字符中间会 panic。
fn floor_boundary(s: &str, cut: usize) -> usize {
    if cut >= s.len() {
        return s.len();
    }
    let mut i = cut;
    while i > 0 && !s.is_char_boundary(i) {
        i -= 1;
    }
    i
}

impl SecurityPolicy {
    /// Windows 保留设备名检查 + `_` 前缀消解（RS-114：抽 helper 供截断后复查）。
    ///
    /// 审计第六轮（2026-10-03）：候选基名取**首个**点前段（`split_once('.')`）
    /// 而非末个点前段（`rsplit_once('.')`）。Win32 解析设备名时在第一个点处
    /// 截断——`CON.dll` 本身就是 `CON` 设备（多层扩展同理：`CON.dll.exe`），
    /// 末点口径给出的基名 `CON.dll` 不在 RESERVED_NAMES 里即放行。
    fn ensure_not_reserved(sanitized: &mut String) {
        let base_name = sanitized
            .split_once('.')
            .map(|(b, _)| b)
            .unwrap_or(sanitized.as_str())
            .to_uppercase();
        if RESERVED_NAMES.contains(&base_name.as_str()) {
            *sanitized = format!("_{sanitized}");
        }
    }

    /// 高危主机判定（审计第六轮 2026-10-03/04；第八轮 B9 由
    /// `is_local_or_private_host` 改名——段集早已含文档段/基准测试段/组播广播，
    /// 既非 local 也非 private，旧名与实际语义相反）——纯函数，不做 DNS。
    ///
    /// 高危 = 「不是任何设备 / 会自我折叠到元数据 / 不可路由」：0/8、169.254/16、
    /// 100.64/10 CGNAT（含阿里云 100.100.100.200）、TEST-NET-1/2/3、198.18/15
    /// 基准段、224/4 组播与受限广播。**不含**回环与 RFC1918——第七轮 B8 裁决。
    ///
    /// 只判定**已规范化后的 host**（`origin::canonicalize_external` 之后）。
    /// 归一层的既有收紧使本函数无需处理任何混淆编码：非点分 IPv4
    ///（2130706433 / 0x7f000001 / 127.1）、逐段前导零八进制（0177.0.0.1 =
    /// inet_aton 解释成 127.0.0.1）、`0x` 混合段与 IPv6 字面量方括号形态
    /// 均已在归一层被拒（PY-071/072、RS-228、RS-238），残余形态只有标准
    /// 点分四段与域名。
    ///
    /// 有意**不**按 `.local`/`.internal` 等后缀名判定：宿主自有资产虚拟主机
    ///（Windows `ntp.aegis.local` / `geo.aegis.local`）正是该形态，按名匹配会
    /// 把 chrome UI 自身拖进高危集。域名经 DNS 指向环回（rebinding）超出纯
    /// 函数能力，属宿主侧判定面——此处不为不可判定的形态假装全覆盖。
    ///
    /// **IPv6 不在本函数覆盖面内**（如实记边界，第七轮 R7-RS-05）：入参是归一
    /// 后的 host，而 `origin::try_parse_external` 的字符集闸门只允许
    /// `[A-Za-z0-9.-]`——`:`/`[` 形态的 IPv6 字面量在归一层即被拒（RS-177/
    /// PY-069/070，见 origin/tests/host_grammar.rs 的
    /// bracketed_ipv6_authority_rejected）。故 C# 孪生
    ///（`UrlSafety.IsPublicIp`）按 IPAddress 字节判的 IPv6 ULA `fc00::/7`、
    /// 组播 `ff00::/8`、site-local `fec0::/10` 在本函数**取不到入参**，
    /// 不是"漏判"而是"无从判定"；要覆盖须先动归一层的 IPv6 支持，属另一批次。
    pub fn is_high_risk_host(host: &str) -> bool {
        let mut octets = [0u8; 4];
        let mut count = 0usize;
        for segment in host.split('.') {
            if count >= 4 {
                return false;
            }
            // 非数字段（域名）直接判 false——空段/超长段 parse 失败同样 false
            match segment.parse::<u8>() {
                Ok(value) => octets[count] = value,
                Err(_) => return false,
            }
            count += 1;
        }
        if count != 4 {
            return false;
        }
        let (a, b) = (octets[0], octets[1]);
        // 第七轮 B8 裁决（不可回退：本机与内网必须能打开）落进核心——127/8、10/8、
        // 172.16/12、192.168/16 与 localhost 名不再判高危，与托管孪生
        // ReservedAddressBoundary 段集一致（别再"顺手"加回来）。0/8：整段不可路由。
        a == 0
        // 链路本地含云元数据地址 169.254.169.254
            || (a == 169 && b == 254)
            // 审计第七轮 R7-RS-05（2026-10-04）：补齐至 C# 孪生
            // `UrlSafety.IsPublicIp`（windows/.../Core/UrlSafety.cs:183-200）
            // 的高危段集——以下四段此前核心判"公网"，R6-21 声称的「SSRF 面在
            // 核心层被拦」对其不成立。段集边界由向量逐条钉住
            //（contracts/vectors/native-navigation-decision.json R7_RS_05_*，
            // 含每段左右两侧的公网对照，防"整段扩大化"式过度收紧）：
            // 100.64.0.0/10 CGNAT——含阿里云元数据端点 100.100.100.200
            || (a == 100 && (64..=127).contains(&b))
            // 192.0.2.0/24 TEST-NET-1（文档示例段，不可路由）
            || (a == 192 && b == 0 && octets[2] == 2)
            // 第八轮 B9：补齐 TEST-NET-2/3——C# 孪生 ReservedAddressBoundary
            // 早已覆盖这两段（:129/:131），核心缺即段集跨端不一致
            || (a == 198 && b == 51 && octets[2] == 100)
            || (a == 203 && b == 0 && octets[2] == 113)
            // 198.18.0.0/15 基准测试段
            || (a == 198 && (b == 18 || b == 19))
            // 224.0.0.0/4 组播（含 239.*/255.255.255.255 广播——孪生同段收口）
            || a >= 224
    }

    /// 手动 URL 解码（零依赖——处理 %XX 编码）。
    pub fn url_decode(input: &str) -> Option<String> {
        let bytes = input.as_bytes();
        let mut result = Vec::with_capacity(bytes.len());
        let mut i = 0;
        while i < bytes.len() {
            if bytes[i] == b'%' && i + 2 < bytes.len() {
                let hi = hex_digit(bytes[i + 1])?;
                let lo = hex_digit(bytes[i + 2])?;
                result.push((hi << 4) | lo);
                i += 3;
            } else {
                result.push(bytes[i]);
                i += 1;
            }
        }
        String::from_utf8(result).ok()
    }
}

use crate::util::hex_digit;

#[cfg(test)]
mod tests;
