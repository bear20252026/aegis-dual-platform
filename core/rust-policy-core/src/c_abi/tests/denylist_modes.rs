// ⑨ 的四档位协议在 **C ABI 层**的行为面（第九轮 Q29 / R9-RS-5）。
//
// 为什么单独一份：档位状态机本身在 `ffi::broker::denylist` 的单元测试里已经跑全
//（staged 不可见、弃会话、无会话提交、旧路径不变、未知档位拒收、空会话提交清空），
// 而**这些结论要通过 ABI 传给三个宿主**——C# 的提交判定读的就是应答里的
// `mode/staged/served` 三字段（`commit.Staged/Accepted` → 拒收时留
// `denylist_commit_refused`），Kotlin 侧靠 `mode` 回显做能力探测。此前 ABI 层只端到端
// 跑过 0/1（`buffer_boundaries.rs`），三字段在 Rust 全测试树**零断言**，
// `denylist_mode_invalid` 也没有 ABI 层用例 ⇒ 核心改名/丢字段在 PR 面永不红
//（而那 8 例 C# 提交用例跑在假核心上、真 DLL 用例不在必需检查——R8-CI-18）。
//
// 本文件判的是**线格式**：字段在不在、类型对不对、值是否等于状态机在那个档位上应给的
// 那个数。状态机本身不在这里重证（避免两份真相）。
use super::super::*;

use super::common::*;
use crate::ffi::denylist::{MODE_APPEND, MODE_BEGIN, MODE_COMMIT, MODE_REPLACE};

/// 进程级单例位（`LIVE_BROKER`）在 panic 路径上也要归还：一条用例失败若把该位
/// 占住，同一进程里后续每条用例都会在 `broker_new` 拿到 null——**一个真失败会
/// 伪装成五条失败**，归因就此丢失（本文件写反向锚时实测到这个形态）。
struct LiveBroker(*mut CAbiBroker);

impl LiveBroker {
    fn ptr(&self) -> *mut CAbiBroker {
        self.0
    }
}

impl Drop for LiveBroker {
    fn drop(&mut self) {
        // SAFETY: 指针只能由下面 `aegis_policy_core_broker_new` 产生，且
        // `broker_free` 只置退休标志、不释放内存，重复调用幂等。
        unsafe { aegis_policy_core_broker_free(self.0) };
    }
}

fn new_broker() -> LiveBroker {
    let version = c_string("1.0");
    let broker = aegis_policy_core_broker_new(version.as_ptr());
    assert!(
        !broker.is_null(),
        "broker_new（若有测试未归还单例位，这里会拿到 null）"
    );
    LiveBroker(broker)
}

/// 档位应答的共同形状——每个档位都必须带齐这六个字段，且 `clear` 回显只在
/// 整批替换档为真（它是旧宿主判别「所加载核心有此参数」的唯一探针）。
#[track_caller]
fn assert_envelope(applied: &serde_json::Value, mode: i32, accepted: u64, served: u64) {
    assert_eq!(applied["decision"], "ok", "档位 {mode} 的注入被拒");
    for field in ["accepted", "input", "clear", "mode", "staged", "served"] {
        assert!(
            applied.get(field).is_some(),
            "档位 {mode} 的应答缺字段 {field}——宿主按对象取值会得 Null"
        );
    }
    assert_eq!(applied["mode"], mode, "档位未自证（能力探测面）");
    assert_eq!(
        applied["accepted"], accepted,
        "档位 {mode} 的 accepted 失实"
    );
    assert_eq!(applied["served"], served, "档位 {mode} 的 served 失实");
    assert_eq!(
        applied["clear"],
        serde_json::Value::Bool(mode == MODE_REPLACE),
        "clear 回显必须等价于「本批是整批替换」"
    );
}

#[test]
fn session_modes_travel_over_the_abi_and_stay_invisible_until_committed() {
    let _serial = broker_test_guard();
    let broker = new_broker();

    let baseline = push_denylist(broker.ptr(), &denylist_payload("base", 2), MODE_REPLACE);
    assert_envelope(&baseline, MODE_REPLACE, 2, 2);
    assert!(!baseline["staged"].as_bool().unwrap());
    assert_eq!(
        evaluate_code(broker.ptr(), "https://base-0.deny.example/")["decision"],
        "deny"
    );

    // 开会话：本批进暂存，判定侧仍读上一份完整快照（⑨ 的全部意义）
    let begin = push_denylist(broker.ptr(), &denylist_payload("pending", 3), MODE_BEGIN);
    assert_envelope(&begin, MODE_BEGIN, 3, 2);
    assert!(
        begin["staged"].as_bool().unwrap(),
        "begin 之后必有未提交会话"
    );
    assert_eq!(
        evaluate_code(broker.ptr(), "https://pending-0.deny.example/")["decision"],
        "allow",
        "暂存条目参与判定＝推送窗口内读残缺名单"
    );

    // 会话内追加仍进暂存，不是活动快照
    let append = push_denylist(broker.ptr(), &denylist_payload("more", 1), MODE_APPEND);
    assert_envelope(&append, MODE_APPEND, 1, 2);
    assert!(append["staged"].as_bool().unwrap());
    assert_eq!(
        evaluate_code(broker.ptr(), "https://more-0.deny.example/")["decision"],
        "allow"
    );

    // 提交：整份暂存换进活动快照；accepted 报的是「这次换没换」而不是条目数
    let commit = push_denylist(broker.ptr(), &denylist_payload("ignored", 0), MODE_COMMIT);
    assert_envelope(&commit, MODE_COMMIT, 1, 4);
    assert!(!commit["staged"].as_bool().unwrap(), "提交后会话必须结束");
    assert_eq!(
        evaluate_code(broker.ptr(), "https://pending-0.deny.example/")["decision"],
        "deny"
    );
    assert_eq!(
        evaluate_code(broker.ptr(), "https://more-0.deny.example/")["decision"],
        "deny"
    );
    // 提交是**整份替换**：基线快照被这份新名单换掉（宿主不能指望它叠加）
    assert_eq!(
        evaluate_code(broker.ptr(), "https://base-0.deny.example/")["decision"],
        "allow"
    );
}

#[test]
fn commit_without_a_session_reports_no_swap_and_serves_the_previous_snapshot() {
    let _serial = broker_test_guard();
    let broker = new_broker();

    // 空会话提交：什么都没换，accepted=0（宿主据此判失败，不会误认为已生效）
    let stray = push_denylist(broker.ptr(), &denylist_payload("ghost", 1), MODE_COMMIT);
    assert_envelope(&stray, MODE_COMMIT, 0, 0);
    assert_eq!(
        evaluate_code(broker.ptr(), "https://ghost-0.deny.example/")["decision"],
        "allow"
    );

    let baseline = push_denylist(broker.ptr(), &denylist_payload("keep", 2), MODE_REPLACE);
    assert_eq!(baseline["served"], 2);
    // 再来一次无会话提交：served 必须仍是上一份完整快照的条目数
    let again = push_denylist(broker.ptr(), &denylist_payload("ghost", 0), MODE_COMMIT);
    assert_envelope(&again, MODE_COMMIT, 0, 2);
    assert_eq!(
        evaluate_code(broker.ptr(), "https://keep-0.deny.example/")["decision"],
        "deny"
    );
}

#[test]
fn replace_discards_an_uncommitted_session_instead_of_landing_it_later() {
    let _serial = broker_test_guard();
    let broker = new_broker();

    push_denylist(broker.ptr(), &denylist_payload("old", 1), MODE_REPLACE);
    let begin = push_denylist(broker.ptr(), &denylist_payload("pending", 3), MODE_BEGIN);
    assert!(begin["staged"].as_bool().unwrap());

    // 整批替换表达的是「以本批为准」——留着半截会话更糟，所以暂存被丢弃
    let replaced = push_denylist(broker.ptr(), &denylist_payload("fresh", 2), MODE_REPLACE);
    assert_envelope(&replaced, MODE_REPLACE, 2, 2);
    assert!(!replaced["staged"].as_bool().unwrap());

    // 丢弃是真的丢弃：之后的提交换不出任何东西
    let commit = push_denylist(broker.ptr(), &denylist_payload("none", 0), MODE_COMMIT);
    assert_envelope(&commit, MODE_COMMIT, 0, 2);
    assert_eq!(
        evaluate_code(broker.ptr(), "https://pending-0.deny.example/")["decision"],
        "allow"
    );
    assert_eq!(
        evaluate_code(broker.ptr(), "https://old-0.deny.example/")["decision"],
        "allow"
    );
    assert_eq!(
        evaluate_code(broker.ptr(), "https://fresh-0.deny.example/")["decision"],
        "deny"
    );
}

#[test]
fn unknown_modes_are_refused_at_the_abi_with_their_own_code_and_change_nothing() {
    let _serial = broker_test_guard();
    let broker = new_broker();
    push_denylist(broker.ptr(), &denylist_payload("live", 2), MODE_REPLACE);

    // 未知档位不得「当作 0 处理」：静默 reinterpret 会让下一版新增档位时把旧核心
    // 的行为错认成新行为。取 4/256/-1 三种形态——-1 是 i32 负值面，256 是
    // 「字节宽以外」的整数面。
    for unknown in [4, 256, -1] {
        let refused = push_denylist(broker.ptr(), &denylist_payload("poison", 5), unknown);
        assert_eq!(
            refused["decision"], "deny",
            "未知档位 {unknown} 被当成合法注入"
        );
        assert_eq!(
            refused["reason"]["code"], "denylist_mode_invalid",
            "未知档位 {unknown} 的拒绝码跑偏（宿主无法区分它与输入非法）"
        );
        // 三处都不许留下痕迹：判定仍读那 2 条
        assert_eq!(
            evaluate_code(broker.ptr(), "https://live-0.deny.example/")["decision"],
            "deny"
        );
        assert_eq!(
            evaluate_code(broker.ptr(), "https://poison-0.deny.example/")["decision"],
            "allow"
        );
    }

    // 被拒的注入不得污染会话：拒绝之后 BEGIN/COMMIT 照常工作
    let begin = push_denylist(broker.ptr(), &denylist_payload("after", 3), MODE_BEGIN);
    assert_envelope(&begin, MODE_BEGIN, 3, 2);
    let commit = push_denylist(broker.ptr(), &denylist_payload("none", 0), MODE_COMMIT);
    assert_envelope(&commit, MODE_COMMIT, 1, 3);
    assert_eq!(
        evaluate_code(broker.ptr(), "https://after-0.deny.example/")["decision"],
        "deny"
    );
    assert_eq!(
        evaluate_code(broker.ptr(), "https://live-0.deny.example/")["decision"],
        "allow"
    );
}

#[test]
fn form_rejected_entries_are_visible_as_counts_on_the_abi() {
    let _serial = broker_test_guard();
    let broker = new_broker();

    // 形态非法的条目收下即「已登记但永不命中」的死条目（比不登记更坏：订阅源
    // 看起来是工作的）。ABI 层的可见面就是 accepted < input——宿主唯一能发现的入口。
    let payload = serde_json::json!([
        "ok.example",
        ".leading.example",
        "trailing.example.",
        "a..b.example",
        "host with space",
    ])
    .to_string();
    let applied = push_denylist(broker.ptr(), &payload, MODE_REPLACE);
    assert_eq!(applied["decision"], "ok");
    assert_eq!(
        applied["input"], 5,
        "input 是本批**收到**的条数，不是被收下的条数"
    );
    assert_eq!(applied["accepted"], 1);
    assert_eq!(applied["served"], 1, "四条死条目不得进活动快照");

    assert_eq!(
        evaluate_code(broker.ptr(), "https://ok.example/")["decision"],
        "deny"
    );
    assert_eq!(
        evaluate_code(broker.ptr(), "https://trailing.example/")["decision"],
        "allow"
    );
    assert_eq!(
        evaluate_code(broker.ptr(), "https://a.b.example/")["decision"],
        "allow"
    );
}
