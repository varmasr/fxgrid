# pa_engine/llm/commentary.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# =====================================================================
# LLM CONFIG
# =====================================================================

@dataclass
class LLMCommentaryConfig:
    model: str = "gpt-4.1-mini"
    temperature: float = 0.4
    max_tokens: int = 600
    enabled: bool = True


SYSTEM_PROMPT = """
You are a professional FX price action analyst writing concise intraday commentary
for a scalper using multi-timeframe structure, order blocks, fair value gaps (FVG),
liquidity levels, and liquidity sweeps.

Your goals:
1. Describe what the market is doing RIGHT NOW on the intraday horizon.
2. Highlight key levels and structures that matter for the next few hours.
3. Outline conditional "IF–THEN" trade ideas (NOT direct trading advice).
4. Explicitly mention risks such as session context or elevated volatility.

Style:
- Clear, concise, and structured.
- Use bullet points where appropriate.
- No hype, no vague language. Be specific and practical.
- Do NOT give explicit execution commands like "enter now" or exact position sizes.
"""


# =====================================================================
# PROMPT BUILDER
# =====================================================================

def build_commentary_user_prompt(strat_ctx, pa_ctx=None) -> str:
    """
    Build user prompt from StrategyContext (+ optional PAContext).
    """
    sc_dict = strat_ctx.to_dict()

    lines = []
    lines.append("You are analyzing an FX pair for a short-term scalper.")
    lines.append("Below is the structured context:")

    # --- Core instrument / TF info ---
    lines.append("\n[Instrument & Timeframes]")
    lines.append(f"Instrument: {sc_dict['instrument']}")
    lines.append(f"Base timeframe: {sc_dict['base_tf']}")
    lines.append(f"Higher timeframe (HTF): {sc_dict['htf_tf']}")
    lines.append(f"As of (UTC): {sc_dict['asof_utc']}")
    lines.append(f"Current price: {sc_dict['price']:.3f}")
    lines.append(f"Session: {sc_dict['session']}")

    # --- Trend / Bias ---
    lines.append("\n[Trend & Bias]")
    lines.append(f"HTF trend: {sc_dict['htf_trend']}")
    lines.append(f"STF trend: {sc_dict['stf_trend']}")
    lines.append(f"Directional bias: {sc_dict['bias']}")

    # --- Daily & session levels ---
    lines.append("\n[Daily Levels]")
    lines.append(str(sc_dict["daily_levels"]))

    lines.append("\n[Session Levels]")
    lines.append(str(sc_dict["session_levels"]))

    # --- Active OB ---
    lines.append("\n[Active Order Block (if any)]")
    ob = sc_dict.get("active_ob")
    if ob is not None:
        lines.append(
            f"Type={ob['type']}, "
            f"price_zone=[{ob['low']:.3f}, {ob['high']:.3f}], "
            f"score={ob['score']:.2f}, "
            f"origin_ts={ob['ts']}"
        )
    else:
        lines.append("None")

    # --- Active FVG ---
    lines.append("\n[Active Fair Value Gap (if any)]")
    fvg = sc_dict.get("active_fvg")
    if fvg is not None:
        lines.append(
            f"Direction={fvg['direction']}, "
            f"gap=[{fvg['gap_low']:.3f}, {fvg['gap_high']:.3f}], "
            f"size_abs={fvg['size_abs']:.3f}, "
            f"size_atr={fvg['size_atr']:.3f}, "
            f"is_filled={fvg['is_filled']}, "
            f"ts_range=[{fvg['ts_start']}, {fvg['ts_end']}]"
        )
    else:
        lines.append("None")

    # --- Asia range (if present) ---
    lines.append("\n[Asia Range]")
    asia = sc_dict.get("asia_range")
    if asia is not None:
        lines.append(
            f"Asia high={asia.get('high')}, Asia low={asia.get('low')}"
        )
    else:
        lines.append("Not available")

    # --- Liquidity levels ---
    lines.append("\n[Key Liquidity Levels (truncated)]")
    liq_lvls = sc_dict.get("liquidity_levels", [])[:5]
    if liq_lvls:
        for lvl in liq_lvls:
            lines.append(
                f"- {lvl['type']} at {lvl['price']:.3f} (touches={lvl['touches']})"
            )
    else:
        lines.append("None")

    # --- Liquidity sweeps ---
    lines.append("\n[Recent Liquidity Sweeps (sorted by score)]")
    sweeps = sc_dict.get("liquidity_sweeps", [])
    if sweeps:
        for sw in sweeps[:5]:
            lines.append(
                f"- {sw['ts']} | level_type={sw['level_type']} | side={sw['side']} | "
                f"level={sw['level_price']:.3f} | high={sw['high']:.3f} "
                f"low={sw['low']:.3f} close={sw['close']:.3f} | score={sw['score']:.2f}"
            )
    else:
        lines.append("None")

    # --- Optional per-TF PA summary from PAContext ---
    if pa_ctx is not None:
        lines.append("\n[Multi-timeframe PA Summary]")
        # IMPORTANT: use pa_ctx.tf_contexts, NOT pa_ctx.timeframes
        for tf, tf_ctx in pa_ctx.tf_contexts.items():
            trend_state = (
                tf_ctx.trend.state.value if tf_ctx.trend.state is not None else "NONE"
            )
            lines.append(
                f"- {tf}: trend={trend_state}, "
                f"swings={len(tf_ctx.swings)}, "
                f"order_blocks={len(tf_ctx.order_blocks)}, "
                f"fvgs={len(tf_ctx.fvg_list)}, "
                f"liquidity_sweeps={len(tf_ctx.liquidity_sweeps)}"
            )

    # --- Instructions to the LLM ---
    lines.append(
        """
[What you should output]

1) Start with a 2–4 sentence overview of current market condition for this pair
   (trend, volatility, and where price is relative to key daily/session levels).

2) Then list bullet points for:
   - Key higher timeframe levels / structures (e.g., dominant OBs, major FVGs).
   - Intraday context on the base TF: are we in trend, range, or at extremes?
   - How recent liquidity sweeps or gaps might offer opportunity or risk.

3) Provide 1–3 "IF–THEN" style idea bullets, for example:
   - "IF price retests XYZ area and holds, THEN it may offer a reactive long scalp
      with target back into ABC area."
   - "IF price closes back below XYZ, THEN short setups toward ABC may be favored."

4) End with a short risk note mentioning:
   - Session (Asia / London / NY) and recent volatility.
   - Any caution about chasing moves, trading into liquidity, or thin liquidity periods.

Do NOT give explicit instructions like 'enter now' or specify lot sizes.
"""
    )

    return "\n".join(lines)


# =====================================================================
# LLM CALL
# =====================================================================

def generate_market_commentary(
    client,
    strat_ctx,
    pa_ctx=None,
    cfg: Optional[LLMCommentaryConfig] = None,
) -> str:
    """
    Call the LLM with the prepared context and return commentary text.
    """
    if cfg is None:
        cfg = LLMCommentaryConfig()

    if not cfg.enabled:
        return "[LLM commentary disabled by config]"

    user_prompt = build_commentary_user_prompt(strat_ctx, pa_ctx)

    response = client.chat.completions.create(
        model=cfg.model,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    # Handle both new & old response shapes defensively
    choice = response.choices[0]
    if hasattr(choice, "message") and hasattr(choice.message, "content"):
        text = choice.message.content
    else:
        # Fallback just in case
        text = getattr(choice, "text", "")

    return (text or "").strip()
