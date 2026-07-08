"""背景迴圈連續失敗告警：達到門檻才推播一次，成功後重置並補推「已恢復」。"""

import pytest

import main
from main import LOOP_FAILURE_ALERT_THRESHOLD, _record_loop_outcome


@pytest.fixture(autouse=True)
def clean_counters():
    main._loop_failure_counts.clear()
    main._loop_alerted.clear()
    yield
    main._loop_failure_counts.clear()
    main._loop_alerted.clear()


def test_no_alert_below_threshold():
    for _ in range(LOOP_FAILURE_ALERT_THRESHOLD - 1):
        assert _record_loop_outcome("測試迴圈", success=False) is None


def test_alert_fires_exactly_at_threshold():
    for _ in range(LOOP_FAILURE_ALERT_THRESHOLD - 1):
        _record_loop_outcome("測試迴圈", success=False)
    notification = _record_loop_outcome("測試迴圈", success=False)
    assert notification is not None
    assert "連續失敗" in notification


def test_alert_does_not_repeat_every_subsequent_failure():
    for _ in range(LOOP_FAILURE_ALERT_THRESHOLD):
        _record_loop_outcome("測試迴圈", success=False)
    # 已經告警過，之後繼續失敗不該再推播（避免洗版）
    assert _record_loop_outcome("測試迴圈", success=False) is None
    assert _record_loop_outcome("測試迴圈", success=False) is None


def test_success_resets_counter_without_prior_alert():
    _record_loop_outcome("測試迴圈", success=False)
    assert _record_loop_outcome("測試迴圈", success=True) is None
    # 計數器歸零，之後要重新累積到門檻才會再告警
    for _ in range(LOOP_FAILURE_ALERT_THRESHOLD - 1):
        assert _record_loop_outcome("測試迴圈", success=False) is None


def test_recovery_notification_after_prior_alert():
    for _ in range(LOOP_FAILURE_ALERT_THRESHOLD):
        _record_loop_outcome("測試迴圈", success=False)
    recovery = _record_loop_outcome("測試迴圈", success=True)
    assert recovery is not None
    assert "已恢復" in recovery


def test_different_loop_names_tracked_independently():
    for _ in range(LOOP_FAILURE_ALERT_THRESHOLD):
        _record_loop_outcome("迴圈A", success=False)
    assert _record_loop_outcome("迴圈B", success=False) is None
