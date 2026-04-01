from app.models import ReviewFinding, ReviewResult, Severity, Category, RiskLevel


def test_review_finding_creation():
    finding = ReviewFinding(
        file="src/auth.py",
        line=42,
        severity=Severity.ERROR,
        category=Category.SECURITY,
        comment="SQL injection risk",
    )
    assert finding.file == "src/auth.py"
    assert finding.line == 42
    assert finding.severity == Severity.ERROR


def test_review_result_creation():
    result = ReviewResult(
        summary="Looks good overall",
        risk_level=RiskLevel.LOW,
        findings=[],
        checklist={"has_tests": True, "no_secrets": True},
    )
    assert result.risk_level == RiskLevel.LOW
    assert len(result.findings) == 0


def test_review_result_from_json():
    data = {
        "summary": "Found issues",
        "risk_level": "high",
        "findings": [
            {
                "file": "main.py",
                "line": 10,
                "severity": "error",
                "category": "bug",
                "comment": "Null pointer",
            }
        ],
        "checklist": {"has_tests": False},
    }
    result = ReviewResult.model_validate(data)
    assert result.risk_level == RiskLevel.HIGH
    assert len(result.findings) == 1
    assert result.findings[0].severity == Severity.ERROR
