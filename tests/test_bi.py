"""The Tableau / Power BI kit in bi/ must stay in step with the analysis."""

import json

from bi import build_bi


def test_bi_export_matches_committed_files(tmp_path):
    res = build_bi.build(tmp_path)
    committed = json.loads((build_bi.OUT / "kpis.json").read_text())
    assert json.loads(json.dumps(res["kpis"])) == committed, "re-run `python -m bi.build_bi` and commit bi/"
    for name, df in res["tables"].items():
        assert len(df) > 0, name
        assert (tmp_path / "data" / f"{name}.csv").exists(), name
        assert (build_bi.OUT / "data" / f"{name}.csv").exists(), f"bi/data/{name}.csv is not committed"
