"""The plan's follow-up is stored in one numbered format, whatever the model wrote."""

from clear_agents.plan import format_points


def test_numbered_follow_ups_are_one_per_line():
    written = ("1) Monitor customs: escalate within 1 day. 2) If the hold passes 3.8 days, re-open "
               "the case. 3) Verify the 20 MT STO (VAL-0002) is dispatched.")
    assert format_points(written) == (
        "1. Monitor customs: escalate within 1 day.\n"
        "2. If the hold passes 3.8 days, re-open the case.\n"
        "3. Verify the 20 MT STO (VAL-0002) is dispatched."
    )
    assert format_points("(1) Check customs. (2) Check the ETA.") == "1. Check customs.\n2. Check the ETA."
    assert format_points("1. A\n2. B") == "1. A\n2. B"


def test_other_text_is_left_alone():
    for text in ("Discharge progress at Tanjung Priok.",
                 "Coverage of 4.83 days. 2. Then something",
                 "Watch plant 1100, which is at 20. Then 2. check",
                 "Only 1. item"):
        assert format_points(text) == text.strip()
