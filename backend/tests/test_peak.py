"""Peak engine pure logic: quiet-slot choice, walk-out curve, bandit behaviour."""

from datetime import timedelta
from unittest import mock

from app.db import now
from app.services import peak


def _fc(base, kinds):
    return {"slots": [{"start": (base + timedelta(minutes=30 * i)).isoformat(), "expectedWaitSec": 0, "kind": k}
                      for i, k in enumerate(kinds)]}


def test_quiet_alternative_picks_closest_slot_with_earlier_penalised():
    base = now() + timedelta(hours=1)
    fc = _fc(base, ["quiet", "peak", "peak", "normal", "quiet", "quiet"])
    # 35 min earlier (cost 52.5) beats 85 min later (cost 85).
    assert peak._quiet_alternative(fc, base + timedelta(minutes=45)) == base + timedelta(minutes=10)
    # Later wins when the earlier option is further away than 1.5x the later one.
    fc2 = _fc(base, ["quiet", "normal", "peak", "peak", "quiet"])
    assert peak._quiet_alternative(fc2, base + timedelta(minutes=75)) == base + timedelta(minutes=130)


def test_quiet_alternative_none_when_out_of_range():
    base = now() + timedelta(hours=1)
    fc = _fc(base, ["peak"] * 3 + ["normal"] * 6 + ["quiet"])
    assert peak._quiet_alternative(fc, base) is None


def test_walkout_curve_bounds():
    assert peak.walkout_prob(120) == 0
    assert 0 < peak.walkout_prob(600) < 0.35
    assert peak.walkout_prob(10_000) == 0.35


def test_bandit_prefers_arm_with_best_value_per_bean():
    stats = {"10": {"offered": 400, "accepted": 20}, "20": {"offered": 400, "accepted": 200},
             "30": {"offered": 400, "accepted": 210}}
    with mock.patch.object(peak, "_arm_stats", return_value=stats):
        picks = [peak.choose_beans("x") for _ in range(200)]
    assert picks.count(20) > 150
