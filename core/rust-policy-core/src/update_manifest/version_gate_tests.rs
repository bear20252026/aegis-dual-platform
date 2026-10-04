use super::accept_update_version;

#[test]
fn strictly_higher_version_is_accepted() {
    assert!(accept_update_version("1.0.1", "1.0.0", None));
    assert!(accept_update_version("2.0.0", "1.9.9", None));
    // 语义化数值比较而非字符串比较："10.0.0" > "9.0.0"
    assert!(accept_update_version("10.0.0", "9.0.0", None));
}

#[test]
fn equal_and_older_are_rejected() {
    // 相等即拒——同版本重放不得被当作一次有效更新
    assert!(!accept_update_version("1.0.0", "1.0.0", None));
    assert!(!accept_update_version("0.9.0", "1.0.0", None));
    assert!(!accept_update_version("1.0.0", "1.0.1", None));
}

#[test]
fn min_version_floor_is_enforced() {
    assert!(accept_update_version("1.5.0", "1.0.0", Some("1.2.0")));
    assert!(!accept_update_version("1.1.0", "1.0.0", Some("1.2.0")));
}

#[test]
fn unparseable_version_fails_closed() {
    // 解析失败 ≠ 放行（与全核 fail-closed 口径一致）
    for bad in [
        "",
        "1",
        "1.",
        "v1.2.3",
        "1.2.3.4",
        "abc",
        "1.2.x",
        "0x1.0.0",
        "1.2.3-beta",
    ] {
        assert!(
            !accept_update_version(bad, "0.0.0", None),
            "不可解析版本 {bad} 必须拒绝"
        );
    }
    assert!(!accept_update_version("9.9.9", "not-a-version", None));
    assert!(!accept_update_version("9.9.9", "0.0.0", Some("???")));
}

#[test]
fn u64_sized_component_does_not_overflow_reject_incorrectly() {
    // version_tuple 对越界分量的处置即 fail-closed（RS 既有测试覆盖），
    // 此处锁定门不 panic
    assert!(!accept_update_version(
        "99999999999999999999999.0.0",
        "1.0.0",
        None
    ));
}
