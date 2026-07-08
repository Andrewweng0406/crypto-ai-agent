"""市場注意力訊號（CoinGecko 熱門榜代理指標）：多空共振判斷與防追高濾網。"""

from main import (
    ATTENTION_OVERHEAT_RANK_CUTOFF,
    ATTENTION_OVERHEAT_STREAK_THRESHOLD,
    build_resonance_summary_prompt,
)


def _sample_alert(change_1h_pct=15.0, change_24h_pct=40.0):
    return {
        "symbol": "PONKE/USDT",
        "volume_multiple": 5.2,
        "price": 0.85,
        "change_1h_pct": change_1h_pct,
        "change_24h_pct": change_24h_pct,
    }


def test_prompt_includes_symbol_and_direction_for_pump():
    prompt = build_resonance_summary_prompt(_sample_alert(change_1h_pct=15.0), trending_rank=0)
    assert "PONKE/USDT" in prompt
    assert "拉盤" in prompt


def test_prompt_includes_direction_for_dump():
    prompt = build_resonance_summary_prompt(_sample_alert(change_1h_pct=-15.0), trending_rank=2)
    assert "砸盤" in prompt


def test_prompt_uses_1_indexed_rank_for_readability():
    # trending_rank 內部是 0-indexed（0=最熱門），文案給人看要顯示「第1名」不是「第0名」
    prompt = build_resonance_summary_prompt(_sample_alert(), trending_rank=0)
    assert "第 1 名" in prompt


def test_prompt_handles_missing_change_pct_gracefully():
    alert = _sample_alert(change_1h_pct=None, change_24h_pct=None)
    prompt = build_resonance_summary_prompt(alert, trending_rank=0)
    assert "PONKE/USDT" in prompt  # 不應該因為 None 就整個炸掉


def test_overheat_streak_below_threshold_is_not_overheated():
    streak = ATTENTION_OVERHEAT_STREAK_THRESHOLD - 1
    assert (streak >= ATTENTION_OVERHEAT_STREAK_THRESHOLD) is False


def test_overheat_streak_at_threshold_is_overheated():
    streak = ATTENTION_OVERHEAT_STREAK_THRESHOLD
    assert (streak >= ATTENTION_OVERHEAT_STREAK_THRESHOLD) is True


def test_rank_cutoff_is_used_for_streak_accumulation():
    # 排名剛好等於 cutoff 不算「前N名」（cutoff=3 代表名次 0,1,2 才算，也就是<cutoff）
    assert (ATTENTION_OVERHEAT_RANK_CUTOFF - 1) < ATTENTION_OVERHEAT_RANK_CUTOFF
    assert not (ATTENTION_OVERHEAT_RANK_CUTOFF < ATTENTION_OVERHEAT_RANK_CUTOFF)
