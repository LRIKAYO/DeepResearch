"""Guard the baseline -> change -> result report template's required shape."""

from pathlib import Path


TEMPLATE = Path(__file__).resolve().parents[2] / "evaluations" / "reports" / "TEMPLATE.md"


def test_template_has_required_comparison_rows_and_columns():
    text = TEMPLATE.read_text(encoding="utf-8")

    for row in ("single-round", "3-round loop", "3-round loop + citation verifier"):
        assert f"| {row} |" in text
    for column in (
        "Recall@5",
        "MRR",
        "nDCG@5",
        "Hard-negative hit rate",
        "Citation support rate",
        "Avg rounds",
        "Cost/run",
        "Latency p50",
    ):
        assert column in text


def test_template_has_baseline_change_result_layout():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "## 2. Baseline" in text
    assert "## 3. Change under test" in text
    assert "## 4. Result" in text
    assert "## 5. Comparison table" in text


def test_template_never_promises_unmeasured_numbers():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "TODO(needs-credentials)" in text
    assert "Never fill a cell with an estimate" in text
