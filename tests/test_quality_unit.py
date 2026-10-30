from pipeline.quality import CHECKS, CheckResult, DataQualityError


def test_check_names_are_unique_per_table():
    keys = [(c.table, c.name) for c in CHECKS]
    assert len(keys) == len(set(keys))


def test_every_check_has_valid_severity():
    assert {c.severity for c in CHECKS} <= {"error", "warn"}


def test_error_message_lists_failures():
    failure = CheckResult("positive_quantity", "staging.stg_order_items", "error", 3)
    err = DataQualityError([failure])
    assert "positive_quantity=3" in str(err)
