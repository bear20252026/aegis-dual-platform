namespace Aegis.Windows.Storage;

/// <summary>阶段 C（蓝图 windows/src/Aegis.Windows.Storage）：
/// bookmarks/history/profile/settings 的加密与迁移骨架。
/// 迁移后：加密存储、最小化、schema migration 与导入审计（蓝图迁移表——
/// bookmark_store/history_store/database 迁入）。阶段 C 最小——数据服务
/// 仅经 Broker 授权访问（ADR-002——没有 AuthorizedAction 不能访问 profile）。</summary>
public sealed class StorageService
{
    // 阶段 C 骨架：加密存储（DPAPI/Keystore——迁移蓝图 Storage 语义）
    // 完整实现按蓝图阶段 C 完成标准（加密/最小化/迁移）迭代
}
