import json

import pytest

from evaluations.analyze import analyse, main, render_markdown


def case(
    case_id: str,
    *,
    relevant=(),
    ranked=(),
    distractors=(),
    scores=(),
    abstained: bool = False,
):
    return {
        "case_id": case_id,
        "project_key": "p1",
        "relevant": [list(item) for item in relevant],
        "distractors": [list(item) for item in distractors],
        "ranked": [list(item) for item in ranked],
        "scores": list(scores),
        "abstained": abstained,
    }


def report(*cases):
    return {
        "mode": "live",
        "dataset_version": "test-v1",
        "run_id": "abc123",
        "k": 5,
        "cases": list(cases),
    }


@pytest.fixture
def sample():
    return report(
        # relevant first, distractor second
        case(
            "a",
            relevant=[["d1", 0]],
            ranked=[["d1", 0], ["d2", 1], ["d3", 2]],
            distractors=[["d2", 1]],
            scores=[0.9, 0.5, 0.4],
        ),
        # distractor first, relevant second
        case(
            "b",
            relevant=[["d1", 1]],
            ranked=[["d2", 0], ["d1", 1], ["d3", 2]],
            distractors=[["d2", 0]],
            scores=[0.8, 0.7, 0.3],
        ),
        # two relevant passages, no distractor
        case(
            "c",
            relevant=[["d1", 0], ["d2", 0]],
            ranked=[["d1", 0], ["d2", 0]],
            scores=[0.7, 0.6],
        ),
        # unanswerable, abstained, with a distractor
        case(
            "d",
            ranked=[["d9", 0]],
            distractors=[["d9", 0]],
            scores=[0.2],
            abstained=True,
        ),
    )


def test_answerable_cases_exclude_unanswerable(sample):
    analysis = analyse(sample)

    assert analysis.total_cases == 4
    assert analysis.answerable_cases == 3
    assert analysis.abstained_rate == pytest.approx(0.25)


def test_cutoffs_compute_macro_and_micro_recall(sample):
    analysis = analyse(sample, ks=(1, 3))
    at_one, at_three = analysis.cutoffs

    assert at_one.k == 1
    # a: 1/1, b: 0/1, c: 1/2 -> mean 0.5
    assert at_one.macro_recall == pytest.approx(0.5)
    # 2 of the 4 relevant passages are inside the top-1 window
    assert at_one.micro_recall == pytest.approx(0.5)

    assert at_three.macro_recall == pytest.approx(1.0)
    assert at_three.micro_recall == pytest.approx(1.0)


def test_mrr_uses_the_first_relevant_position(sample):
    analysis = analyse(sample, ks=(5,))

    # a: rank 1 -> 1.0, b: rank 2 -> 0.5, c: rank 1 -> 1.0
    assert analysis.cutoffs[0].mrr == pytest.approx((1.0 + 0.5 + 1.0) / 3)


def test_distractor_exposure_is_reported_per_cutoff(sample):
    analysis = analyse(sample, ks=(1, 3))
    at_one, at_three = analysis.cutoffs

    assert at_one.distractor_cases == 2
    assert at_one.distractor_hit_cases == 1
    assert at_one.distractor_hit_rate == pytest.approx(0.5)

    assert at_three.distractor_hit_cases == 2
    assert at_three.distractor_hit_rate == pytest.approx(1.0)


def test_distractor_above_every_relevant_is_counted(sample):
    analysis = analyse(sample, ks=(1, 3))

    # Case b is the only one where a distractor outranks every relevant passage.
    assert analysis.cutoffs[0].distractor_above_relevant == 1
    assert analysis.cutoffs[1].distractor_above_relevant == 1


def test_scores_and_margins_are_medians_over_answerable_cases(sample):
    analysis = analyse(sample, ks=(5,))

    # top-1 scores: 0.9, 0.8, 0.7 -> median 0.8
    assert analysis.median_top1_score == pytest.approx(0.8)
    # margins: 0.4, 0.1, 0.1 -> median 0.1
    assert analysis.median_top1_margin == pytest.approx(0.1)


def test_corpus_coverage_uses_the_largest_cutoff(sample):
    analysis = analyse(sample, ks=(1, 3), corpus_chunks={"p1": 30, "p2": 0})

    assert analysis.coverage == (("p1", 30, pytest.approx(0.1)),)


def test_reading_flags_a_saturated_recall(sample):
    markdown = render_markdown(analyse(sample, ks=(1, 5)), source="run.json")

    assert "## Reading" in markdown
    assert "Recall@1 is 0.500" in markdown
    assert "recovered by k=5" in markdown


def test_reading_separates_tail_contamination_from_wrong_answer_wins():
    data = report(
        case(
            "a",
            relevant=[["d1", 0]],
            ranked=[["d1", 0], ["d2", 1]],
            distractors=[["d2", 1]],
        )
    )

    markdown = render_markdown(analyse(data, ks=(1, 3)), source="run.json")

    assert "tail contamination" in markdown


def test_reading_warns_when_the_cutoff_covers_the_corpus():
    data = report(case("a", relevant=[["d1", 0]], ranked=[["d1", 0]], scores=[0.9]))
    analysis = analyse(data, ks=(1, 5), corpus_chunks={"p1": 20})

    markdown = render_markdown(analysis, source="run.json")

    assert "25% of the whole Project corpus" in markdown


def test_rejects_a_report_without_cases():
    with pytest.raises(ValueError, match="no cases"):
        analyse({"cases": []})


def test_rejects_a_malformed_passage():
    bad = report(case("a", relevant=[["d1", 0]], ranked=[["only-one"], ["d1", 0]]))

    with pytest.raises(ValueError, match="not a passage reference"):
        analyse(bad)


def test_rejects_a_non_positive_cutoff(sample):
    with pytest.raises(ValueError, match="cutoffs"):
        analyse(sample, ks=(0,))


def test_render_is_stable_for_a_saved_run(tmp_path, sample):
    path = tmp_path / "run.json"
    path.write_text(json.dumps(sample), encoding="utf-8")

    loaded = json.loads(path.read_text(encoding="utf-8"))
    markdown = render_markdown(analyse(loaded), source=path)

    assert "| 1 |" in markdown
    assert "run `abc123`" in markdown


def test_main_rejects_a_report_dataset_version_mismatch(tmp_path):
    run = tmp_path / "run.json"
    run.write_text(
        json.dumps(
            report(case("a", relevant=[["d1", 0]], ranked=[["d1", 0]], scores=[0.9]))
        ),
        encoding="utf-8",
    )
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps(
            {
                "dataset_version": "other-v9",
                "projects": [
                    {
                        "project_key": "p1",
                        "documents": [{"content": "# heading\n\nbody"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="dataset version mismatch"):
        main(["--report", str(run), "--dataset", str(dataset)])


def test_main_accepts_a_mismatch_when_explicitly_allowed(tmp_path, capsys):
    run = tmp_path / "run.json"
    run.write_text(
        json.dumps(
            report(case("a", relevant=[["d1", 0]], ranked=[["d1", 0]], scores=[0.9]))
        ),
        encoding="utf-8",
    )
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps(
            {
                "dataset_version": "other-v9",
                "projects": [
                    {
                        "project_key": "p1",
                        "documents": [{"content": "# heading\n\nbody"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert main(
        [
            "--report",
            str(run),
            "--dataset",
            str(dataset),
            "--allow-version-mismatch",
        ]
    ) == 0
    assert "Rank-sensitivity analysis" in capsys.readouterr().out
