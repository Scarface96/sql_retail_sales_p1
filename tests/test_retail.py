import pandas as pd
import pytest

from analysis import data


@pytest.fixture(scope="module")
def con():
    return data.connect()


def test_cleaning_matches_the_sql_file(con):
    q = data.quality(con).iloc[0]
    assert q["raw_rows"] == 2000
    assert q["rows_removed"] == 3
    assert q["totals_that_dont_add_up"] == 0


def test_every_business_question_runs(con):
    answers = data.answers(con)
    assert [a[0] for a in answers] == [f"Q{i}" for i in range(1, 11)]
    assert all(isinstance(a[3], pd.DataFrame) for a in answers)


def test_category_totals_add_up(con):
    total = con.sql("SELECT SUM(total_sale) FROM retail_sales").fetchone()[0]
    by_cat = con.sql(data.QUESTIONS[2][2]).df()["net_sale"].sum()
    assert by_cat == pytest.approx(total)


def test_shifts_cover_all_orders(con):
    shifts = con.sql(data.QUESTIONS[9][2]).df()
    assert shifts["total_orders"].sum() == con.sql("SELECT COUNT(*) FROM retail_sales").fetchone()[0]


def test_rfm_scores_and_segments(con):
    r = data.rfm(con)
    assert r["customer_id"].is_unique
    assert r[["r", "f", "m"]].isin([1, 2, 3, 4]).all().all()
    assert set(r["segment"]) <= {"Champions", "Active", "Valuable but slipping", "Lapsed"}


def test_cohorts_start_at_full_retention(con):
    c = data.cohorts(con)
    assert (c.loc[c["quarters_later"] == 0, "retention"] == 1).all()
    assert c["retention"].between(0, 1).all()
