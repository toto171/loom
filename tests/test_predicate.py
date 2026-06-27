"""Safe-eval predicate layer: correct evaluation, three-valued None handling,
and rejection of disallowed constructs."""
import pytest

from loom.monitors.predicate import UNAVAILABLE, PredicateError, evaluate


def test_comparisons_and_or():
    assert evaluate("temp < -20 or temp > 60", {"temp": 70}) is True
    assert evaluate("temp < -20 or temp > 60", {"temp": 25}) is False
    assert evaluate("temp < -20 or temp > 60", {"temp": -30}) is True


def test_chained_comparison():
    assert evaluate("-20 < temp < 60", {"temp": 25}) is True
    assert evaluate("-20 < temp < 60", {"temp": 80}) is False


def test_abs_arithmetic():
    assert evaluate("abs(a - b) > 5", {"a": 10, "b": 2}) is True
    assert evaluate("abs(a - b) > 5", {"a": 10, "b": 8}) is False


def test_boolean_and_not():
    assert evaluate("a and b", {"a": True, "b": False}) is False
    assert evaluate("a or b", {"a": False, "b": True}) is True
    assert evaluate("not a", {"a": False}) is True


def test_dropped_sensor_is_unavailable():
    assert evaluate("temp < -20 or temp > 60", {"temp": None}) is UNAVAILABLE
    assert evaluate("abs(a - b) > 5", {"a": None, "b": 8}) is UNAVAILABLE


def test_is_none_check_still_works():
    assert evaluate("temp is None", {"temp": None}) is True
    assert evaluate("temp is None", {"temp": 25}) is False
    assert evaluate("temp is not None", {"temp": 25}) is True


def test_three_valued_short_circuit():
    assert evaluate("a and (temp > 60)", {"a": False, "temp": None}) is False
    assert evaluate("a or (temp > 60)", {"a": True, "temp": None}) is True


def test_unknown_variable_raises():
    with pytest.raises(PredicateError):
        evaluate("foo > 1", {})


@pytest.mark.parametrize(
    "expr,variables",
    [
        ("__import__('os')", {}),
        ("obj.attr", {"obj": 1}),
        ("d['k']", {"d": {}}),
        ("len([1, 2])", {}),
        ("(lambda: 1)()", {}),
        ("1 +", {}),
    ],
)
def test_disallowed_or_malformed_constructs_raise(expr, variables):
    with pytest.raises(PredicateError):
        evaluate(expr, variables)


def test_dropped_sensor_as_bare_boolean_operand_is_unavailable():
    # Regression: a dropped boolean sensor used directly in and/or/not must yield
    # UNAVAILABLE (so the monitor fires), not be treated as plain falsy. This is the
    # ADAS odd_exit_undetected shape: "speed_kph > max and lka_engaged".
    assert evaluate("speed > max and lka", {"speed": 100, "max": 80, "lka": None}) is UNAVAILABLE
    assert evaluate("not temp", {"temp": None}) is UNAVAILABLE
    assert evaluate("a and b", {"a": None, "b": True}) is UNAVAILABLE
    assert evaluate("a or b", {"a": None, "b": False}) is UNAVAILABLE


def test_equality_against_dropped_sensor_is_unavailable():
    assert evaluate("state == 5", {"state": None}) is UNAVAILABLE
    assert evaluate("state != 5", {"state": None}) is UNAVAILABLE


@pytest.mark.parametrize(
    "expr,variables",
    [
        ("temp < 60", {"temp": "hot"}),  # string vs number ordering
        ("a + b", {"a": 1, "b": "x"}),   # type-confused arithmetic
        ("a / b", {"a": 1, "b": 0}),     # division by zero
        ("a % b", {"a": 1, "b": 0}),     # modulo by zero
    ],
)
def test_type_confused_or_zero_divisor_raises_predicate_error(expr, variables):
    with pytest.raises(PredicateError):
        evaluate(expr, variables)


def test_value_position_whitelisted_name_is_a_variable():
    from loom.monitors.predicate import referenced_names

    assert referenced_names("abs + 1") == {"abs"}
    assert referenced_names("abs(x) > 1") == {"x"}
    assert evaluate("abs + 1", {"abs": 5}) == 6
