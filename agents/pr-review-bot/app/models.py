from enum import Enum
from pydantic import BaseModel


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    SUGGESTION = "suggestion"


class Category(str, Enum):
    SECURITY = "security"
    BUG = "bug"
    STYLE = "style"
    PERFORMANCE = "performance"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReviewFinding(BaseModel):
    file: str
    line: int
    severity: Severity
    category: Category
    comment: str


class ReviewResult(BaseModel):
    summary: str
    risk_level: RiskLevel
    findings: list[ReviewFinding]
    checklist: dict[str, bool]
