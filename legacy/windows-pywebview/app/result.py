"""result.py —— R-21 整改（宽泛异常替换——Result/AppError 结果类型）。

体验/功能审查（R-21）：禁止在产品逻辑中使用 `except Exception: pass`。
方法应返回可处理的结果；不可恢复错误必须被记录、向用户显示稳定错误码，
并按策略中止相关操作（实施手册 R-21 示例）。UI 只显示 user_message，
诊断系统记录 code/上下文（不向用户显示原始堆栈或 SQL/文件路径）。
"""

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class AppError:
    """稳定错误码 + 用户可读消息（R-21：用户可见错误与结构化诊断）。"""

    code: str
    user_message: str
    retryable: bool = False
    details: dict[str, str] | None = None


@dataclass(frozen=True)
class Result(Generic[T]):
    """方法结果（R-21：成功值或错误——替代裸异常吞噬）。"""

    value: T | None = None
    error: AppError | None = None

    @property
    def is_ok(self) -> bool:
        return self.error is None

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        return cls(value=value)

    @classmethod
    def fail(cls, error: AppError) -> "Result[T]":
        return cls(error=error)
