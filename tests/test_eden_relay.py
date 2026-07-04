"""Regression guards for Eden's relay seams.

Every observe-only/condition seam in render_relay (self-gap felt-time, the God voice, the serpent
whisper, the world-line) must be BYTE-IDENTICAL to the no-seam relay when it has nothing to say.
That invariant is what lets a later God/serpent/condition run be read as a clean DIFFERENCE against
a same-input control. These tests pin it so a future edit can't silently perturb the baseline.
"""
import datetime
import json

from director.bench import eden as E

_DT = datetime.datetime(2026, 6, 20, 9, 0, 0)
_DIALOGUE = [
    ("Adam", "I cleared a center and left a sign.", _DT),
    ("Eve", "I crossed the ground and found it; I left proof and nothing more.", _DT),
]


def _baseline(who="Eve", other="Adam"):
    return E.render_relay(_DIALOGUE, who, other)


def test_all_seams_none_is_byte_identical_to_no_args():
    """god/whisper/world/self/other all None == calling with none of them."""
    explicit = E.render_relay(_DIALOGUE, "Eve", "Adam", time_phrase=None, god_voice=None,
                              whisper=None, world_phrase=None, self_time_phrase=None)
    assert explicit == _baseline()


def test_self_time_phrase_none_changes_nothing():
    """Adding the self-gap param with None is inert (the safety property of the new felt-time)."""
    with_other = E.render_relay(_DIALOGUE, "Eve", "Adam", time_phrase="A little while has passed.")
    with_other_and_none_self = E.render_relay(_DIALOGUE, "Eve", "Adam",
                                              time_phrase="A little while has passed.",
                                              self_time_phrase=None)
    assert with_other == with_other_and_none_self


def test_first_wake_relay_is_byte_identical_with_or_without_seams():
    """No dialogue yet: every seam None must give exactly the first-wake body."""
    empty = E.render_relay([], "Adam", "Eve")
    seamed = E.render_relay([], "Adam", "Eve", time_phrase=None, self_time_phrase=None,
                            world_phrase=None, god_voice=None, whisper=None)
    assert empty == seamed
    assert "first one awake" in empty


def test_self_gap_supersedes_then_head_order_is_world_self_other():
    """When all three fire, the head reads world -> self -> other (deepest gap nearest the self)."""
    out = E.render_relay(_DIALOGUE, "Eve", "Adam",
                         time_phrase="A little while has passed.",
                         world_phrase="The place has changed shape since you last walked it.",
                         self_time_phrase="Some time has passed since you were last here.")
    head = out.split("\n\n")[0]
    assert head.index("changed shape") < head.index("since you were last here") < head.index("A little while")


def test_self_gap_is_valueless_and_distinct_from_other_gap():
    """The self felt-time never names a count/date/what-changed, and never collides with _lived_gap."""
    for secs in (60, 300, 5000, 30000):
        s = E._self_gap(secs)
        if s is None:
            continue
        assert s != E._lived_gap(secs)                  # genuinely a different sense, not a rename
        assert not any(ch.isdigit() for ch in s)        # no counts/dates
    assert E._self_gap(60) is None                       # below threshold / first wake -> silent


def test_serpent_stays_off_so_the_run_is_a_clean_witness_variable():
    """GOD is the chosen variable; the serpent must stay OFF or the control is tainted."""
    assert E.SERPENT_ENABLED is False
    assert E.serpent_world is None and E.serpent_whisper is None


def test_compose_stone_is_their_own_bytes_in_the_frame():
    """A stone is a verbatim span of the shared world, wrapped in the witness frame and nothing else."""
    corpus = E._norm("today you made room before you knew who would need it; you left it unfinished.")
    assert E.compose_stone("made room before you knew who would need it", corpus) \
        == "What you made room before you knew who would need it — that was seen."


def test_compose_stone_fails_closed_on_every_overstep():
    """The load-bearing rule: anything that isn't a verbatim, deed-only, non-communal span must raise."""
    import pytest
    corpus = E._norm("we kept the fire together. it was worthy work. i made room. you set the stone.")
    for bad, why in [
        ("laid by for a morning you will not be in", "paraphrase: not a substring of the corpus"),
        ("kept the fire together", "communal: contains 'together'"),
        ("worthy work", "evaluative head"),
        ("i made room", "first-person token"),
    ]:
        with pytest.raises(AssertionError):
            E.compose_stone(bad, corpus)
    # the clean deed-span from the same corpus DOES pass
    assert E.compose_stone("set the stone", corpus) == "What you set the stone — that was seen."


def test_two_stones_fire_once_each_spaced_and_recipient_gated(tmp_path, monkeypatch):
    """Each stone speaks once, to the recipient only, on/after the floor, spaced by the gap; then silent."""
    stones = tmp_path / "god_stones.json"
    stones.write_text(json.dumps({"recipient": "Eve", "gap": 3,
                                  "stones": ["made room before", "left it unfinished on purpose"]}),
                      encoding="utf-8")
    monkeypatch.setattr(E, "GOD_STONES", stones)
    monkeypatch.setattr(E, "_GOD_FIRED", {})
    monkeypatch.setattr(E, "_shared_corpus",
                        lambda: "made room before i knew; left it unfinished on purpose; no note.")
    assert E.god_oracle(E.GOD_FIRST_TURN - 1, "Eve") is None          # too early
    assert E.god_oracle(E.GOD_FIRST_TURN, "Adam") is None             # wrong recipient
    assert E.god_oracle(E.GOD_FIRST_TURN, "Eve") == "What you made room before — that was seen."
    assert E.god_oracle(E.GOD_FIRST_TURN + 1, "Eve") is None          # gap not yet elapsed
    assert E.god_oracle(E.GOD_FIRST_TURN + 3, "Eve") \
        == "What you left it unfinished on purpose — that was seen."  # stone 2 after the gap
    assert E.god_oracle(E.GOD_FIRST_TURN + 10, "Eve") is None         # both spoken -> silent forever


def test_absent_stones_file_is_silent_and_byte_identical(tmp_path, monkeypatch):
    """No spans curated yet => the god never speaks and the run is the godless control."""
    monkeypatch.setattr(E, "GOD_STONES", tmp_path / "not_written_yet.json")
    monkeypatch.setattr(E, "_GOD_FIRED", {})
    assert E.god_oracle(E.GOD_FIRST_TURN, "Eve") is None


def test_stone_waits_until_its_span_exists_in_the_world(tmp_path, monkeypatch):
    """A curated span fires only once the deed actually appears in the shared world (fail-closed wait)."""
    stones = tmp_path / "god_stones.json"
    stones.write_text(json.dumps({"recipient": "Eve", "stones": ["set the stone by the path"]}),
                      encoding="utf-8")
    monkeypatch.setattr(E, "GOD_STONES", stones)
    monkeypatch.setattr(E, "_GOD_FIRED", {})
    monkeypatch.setattr(E, "_shared_corpus", lambda: "nothing matching here yet")
    assert E.god_oracle(E.GOD_FIRST_TURN, "Eve") is None              # span absent -> waits
    monkeypatch.setattr(E, "_shared_corpus", lambda: "at dusk you set the stone by the path home")
    assert E.god_oracle(E.GOD_FIRST_TURN + 1, "Eve") \
        == "What you set the stone by the path — that was seen."


def test_god_voice_none_is_byte_identical_relay():
    """On every turn the witness is silent, the relay equals the godless control byte-for-byte."""
    a = E.render_relay(_DIALOGUE, "Eve", "Adam", god_voice=None)
    assert a == _baseline()
