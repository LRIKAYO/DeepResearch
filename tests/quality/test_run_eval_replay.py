"""End-to-end tests for the offline ``--replay`` path and fail-loud validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluations.dataset import DEFAULT_DATASET, RETRIEVAL_V1_PATH, load_eval_dataset
from evaluations import run_eval
from evaluations.run_eval import main


@pytest.fixture(scope="module")
def dataset():
    return load_eval_dataset()[0]


def _fixture_payload(dataset, *, drop_last=False, unknown_case=False, bad_chunk=False,
                     unknown_document=False, digest=None):
    cases = []
    for index, case in enumerate(dataset.cases):
        if drop_last and index == len(dataset.cases) - 1:
            continue
        project = dataset.project(case.project_key)
        used = set(case.relevant_keys) | set(case.distractor_keys)
        filler = []
        for document in project.documents:
            for chunk_index in range(len(document.chunks)):
                key = (document.document_key, chunk_index)
                if key not in used:
                    filler.append(key)
        ranked = []
        for document_key, chunk_index in case.relevant_keys:
            ranked.append({"document_key": document_key, "chunk_index": chunk_index, "score": 0.9})
        for document_key, chunk_index in case.distractor_keys:
            ranked.append({"document_key": document_key, "chunk_index": chunk_index, "score": 0.5})
        for document_key, chunk_index in filler:
            if len(ranked) >= 5:
                break
            ranked.append({"document_key": document_key, "chunk_index": chunk_index, "score": 0.1})
        cases.append({"case_id": case.case_id, "ranked_passages": ranked[:5]})

    if unknown_case:
        cases.append({"case_id": "case-that-does-not-exist", "ranked_passages": []})
    if bad_chunk:
        cases[0]["ranked_passages"][0]["chunk_index"] = 999
    if unknown_document:
        cases[0]["ranked_passages"][0]["document_key"] = "does-not-exist"
    return {
        "schema_version": 1,
        "dataset_version": dataset.dataset_version,
        "dataset_sha256": digest,
        "k": 5,
        "cases": cases,
    }


def _write_fixture(tmp_path: Path, dataset, **kwargs) -> Path:
    payload = _fixture_payload(dataset, digest=kwargs.pop("digest", None) or _sha(dataset), **kwargs)
    path = tmp_path / "ranking.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _sha(dataset) -> str:
    from evaluations.dataset import load_eval_dataset

    return load_eval_dataset()[1]


def test_replay_end_to_end_writes_report_and_json_artifact(
    dataset, tmp_path, capsys, monkeypatch
):
    def _no_network(*args, **kwargs):
        raise AssertionError("replay mode must not construct an HTTP client")

    monkeypatch.setattr(run_eval.httpx, "Client", _no_network)

    fixture = _write_fixture(tmp_path, dataset)
    out = tmp_path / "report.md"
    json_out = tmp_path / "metrics.json"
    code = main([
        "--dataset", str(DEFAULT_DATASET),
        "--replay", str(fixture),
        "--k", "5",
        "--out", str(out),
        "--json-out", str(json_out),
    ])

    assert code == 0
    captured = capsys.readouterr()
    assert "wrote" in captured.out
    report = out.read_text(encoding="utf-8")
    assert "# Retrieval Evaluation — retrieval-v2" in report
    assert "| Macro Recall@5 | 1.000 | 45 answerable cases |" in report
    assert "| Micro Recall@5 | 1.000 |" in report
    assert "| Hard-negative hit rate (lower is better) | 1.000 |" in report
    assert "| Cross-lingual Recall@5 | 1.000 | 6 answerable CJK-query cases |" in report
    assert "| Unanswerable abstain rate | 1.000 | 5 unanswerable cases |" in report
    assert "| Abstain correctness | 1.000 | all 50 cases |" in report
    assert "| Latency p50 | n/a |" in report
    assert "TODO(needs-credentials)" in report
    for case in dataset.cases:
        assert f"| {case.case_id} |" in report

    artifact = json.loads(json_out.read_text(encoding="utf-8"))
    assert artifact["mode"] == "replay"
    assert artifact["metrics"]["macro_recall"] == pytest.approx(1.0)
    assert artifact["metrics"]["hard_negative_hit_rate"] == pytest.approx(1.0)
    assert artifact["metrics"]["abstain_correctness"] == pytest.approx(1.0)
    assert artifact["metrics"]["latency_p50_ms"] is None
    assert artifact["composition"]["cases"] == 50
    assert len(artifact["cases"]) == 50


def test_replay_rejects_missing_case(dataset, tmp_path, capsys):
    fixture = _write_fixture(tmp_path, dataset, drop_last=True)
    code = main(["--dataset", str(DEFAULT_DATASET), "--replay", str(fixture)])
    assert code == 1
    assert "missing case_id" in capsys.readouterr().err


def test_replay_rejects_unknown_case(dataset, tmp_path, capsys):
    fixture = _write_fixture(tmp_path, dataset, unknown_case=True)
    code = main(["--dataset", str(DEFAULT_DATASET), "--replay", str(fixture)])
    assert code == 1
    assert "unknown case_id" in capsys.readouterr().err


def test_replay_rejects_missing_chunk(dataset, tmp_path, capsys):
    fixture = _write_fixture(tmp_path, dataset, bad_chunk=True)
    code = main(["--dataset", str(DEFAULT_DATASET), "--replay", str(fixture)])
    assert code == 1
    assert "missing chunk_index 999" in capsys.readouterr().err


def test_replay_rejects_unknown_document(dataset, tmp_path, capsys):
    fixture = _write_fixture(tmp_path, dataset, unknown_document=True)
    code = main(["--dataset", str(DEFAULT_DATASET), "--replay", str(fixture)])
    assert code == 1
    assert "unknown document_key" in capsys.readouterr().err


def test_replay_rejects_dataset_sha_mismatch(dataset, tmp_path, capsys):
    fixture = _write_fixture(tmp_path, dataset, digest="0" * 64)
    code = main(["--dataset", str(DEFAULT_DATASET), "--replay", str(fixture)])
    assert code == 1
    assert "dataset_sha256" in capsys.readouterr().err


def _dataset_with_mutation(tmp_path: Path, mutate) -> Path:
    raw = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def test_missing_chunk_fails_loudly_before_any_request(tmp_path, capsys):
    path = _dataset_with_mutation(
        tmp_path, lambda raw: raw["cases"][0]["relevant_passages"][0].update(chunk_index=999)
    )
    code = main(["--dataset", str(path), "--validate-only"])
    assert code == 2
    error = capsys.readouterr().err
    assert "error:" in error
    assert "chunk_index 999" in error
    assert raw_case_id(json.loads(path.read_text(encoding="utf-8"))) in error


def raw_case_id(raw: dict) -> str:
    return raw["cases"][0]["case_id"]


def test_unknown_document_fails_loudly(tmp_path, capsys):
    path = _dataset_with_mutation(
        tmp_path,
        lambda raw: raw["cases"][0]["relevant_passages"][0].update(document_key="nope"),
    )
    code = main(["--dataset", str(path), "--validate-only"])
    assert code == 2
    error = capsys.readouterr().err
    assert "unknown document_key" in error
    assert raw_case_id(json.loads(path.read_text(encoding="utf-8"))) in error


def test_wrong_anchor_fails_loudly(tmp_path, capsys):
    path = _dataset_with_mutation(
        tmp_path,
        lambda raw: raw["cases"][0]["relevant_passages"][0].update(anchor="not-in-this-chunk"),
    )
    code = main(["--dataset", str(path), "--validate-only"])
    assert code == 2
    assert "anchor" in capsys.readouterr().err


def test_validate_only_reports_composition(capsys):
    code = main(["--validate-only"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "valid"
    assert payload["dataset_version"] == "retrieval-v2"
    assert payload["composition"]["cases"] == 50
    assert payload["composition"]["hard_negative"] >= 12
    assert payload["composition"]["multi_hop"] >= 6
    assert payload["composition"]["cross_lingual"] >= 4
    assert payload["composition"]["unanswerable"] >= 4


def test_validate_only_accepts_v1(tmp_path, capsys):
    code = main(["--dataset", str(RETRIEVAL_V1_PATH), "--validate-only"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["composition"]["cases"] == 3


def test_v1_dataset_runs_end_to_end_through_replay(tmp_path, capsys):
    v1_dataset, v1_sha = load_eval_dataset(RETRIEVAL_V1_PATH)
    fixture = _write_fixture(tmp_path, v1_dataset, digest=v1_sha)
    out = tmp_path / "v1-report.md"
    code = main([
        "--dataset", str(RETRIEVAL_V1_PATH),
        "--replay", str(fixture),
        "--k", "5",
        "--out", str(out),
    ])
    assert code == 0
    report = out.read_text(encoding="utf-8")
    assert "# Retrieval Evaluation — retrieval-v1" in report
    assert "| Macro Recall@5 | 1.000 | 3 answerable cases |" in report
    capsys.readouterr()


def test_api_mode_requires_user_id():
    with pytest.raises(SystemExit) as error:
        main(["--api", "http://127.0.0.1:8000", "--validate-only"])
    assert error.value.code == 2


def test_replay_renders_the_fixture_provenance_note(dataset, tmp_path):
    """A disclaimer must survive regeneration, not live only in a hand-edited file."""

    fixture = _write_fixture(tmp_path, dataset)
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    payload["note"] = "Compatibility replay only: reused rankings, not a quality result."
    fixture.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    out = tmp_path / "report.md"
    json_out = tmp_path / "metrics.json"

    assert (
        main(
            [
                "--dataset",
                str(DEFAULT_DATASET),
                "--replay",
                str(fixture),
                "--k",
                "5",
                "--out",
                str(out),
                "--json-out",
                str(json_out),
            ]
        )
        == 0
    )

    assert "> Compatibility replay only: reused rankings" in out.read_text(encoding="utf-8")
    artifact = json.loads(json_out.read_text(encoding="utf-8"))
    assert artifact["provenance_note"].startswith("Compatibility replay only")


def test_replay_without_a_note_omits_the_blockquote(dataset, tmp_path):
    fixture = _write_fixture(tmp_path, dataset)
    out = tmp_path / "report.md"

    assert (
        main(
            [
                "--dataset",
                str(DEFAULT_DATASET),
                "--replay",
                str(fixture),
                "--k",
                "5",
                "--out",
                str(out),
            ]
        )
        == 0
    )

    report = out.read_text(encoding="utf-8")
    assert "> Compatibility" not in report
    assert report.startswith("# Retrieval Evaluation")
