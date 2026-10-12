"""Phân tích định lượng ngành (FQA): dữ liệu chéo, chuỗi thời gian, dữ liệu bảng.

Phân rã Mundlak (1978) cho dữ liệu bảng ROE–ROA của một ngành:
    ROA_it = E(ROA) + [E(ROA_i) − E(ROA)] + [ROA_it − E(ROA_i)]
              (chung)     (trạng thái)          (động lực)
    ROE_it = a' + bB·E(ROA_i) + bW·[ROA_it − E(ROA_i)] + u'_it
- bB (quan hệ trạng thái): DN A có ROA cao hơn DN B 1% → ROE cao hơn bB%.
- bW (quan hệ động lực): ROA của một DN tăng 1% → ROE của DN đó tăng bW%.
- Hồi quy gộp b = wB·bB + wW·bW, với wB, wW là tỷ trọng phương sai trạng thái/động lực.
- bs = E(ROE)/E(ROA): hệ số trạng thái ổn định chung của ngành.
"""

from __future__ import annotations

import numpy as np

from .fundamental import ols


def mundlak(panel: dict[str, list[tuple[float, float]]]) -> dict | None:
    """panel: {ticker: [(roa, roe), ...]}"""
    rows = []
    for tk, obs in panel.items():
        obs = [(a, e) for a, e in obs if a is not None and e is not None]
        if len(obs) < 2:
            continue
        mean_i = float(np.mean([a for a, _ in obs]))
        for a, e in obs:
            rows.append((tk, a, e, mean_i))
    if len(rows) < 6 or len({r[0] for r in rows}) < 2:
        return None
    roa = np.array([r[1] for r in rows])
    roe = np.array([r[2] for r in rows])
    mean_i = np.array([r[3] for r in rows])
    within = roa - mean_i
    X = np.column_stack([np.ones(len(rows)), mean_i, within])
    coef, *_ = np.linalg.lstsq(X, roe, rcond=None)
    a_p, b_between, b_within = (float(c) for c in coef)
    pred = X @ coef
    r2 = 1 - float(((roe - pred) ** 2).sum()) / float(((roe - roe.mean()) ** 2).sum())
    pooled = ols(list(roa), list(roe))
    grand = float(roa.mean())
    var_total = float(np.var(roa))
    var_between = float(np.var(mean_i - grand))
    var_within = float(np.var(within))
    w_b = var_between / var_total if var_total else None
    w_w = var_within / var_total if var_total else None
    bs = float(roe.mean()) / grand if grand else None
    firms = {}
    for tk in panel:
        sub = [(r[1], r[2]) for r in rows if r[0] == tk]
        if sub:
            firms[tk] = {"mean_roa": float(np.mean([s[0] for s in sub])),
                         "mean_roe": float(np.mean([s[1] for s in sub])),
                         "state_vs_industry": float(np.mean([s[0] for s in sub])) - grand}
    return {
        "n_obs": len(rows), "n_firms": len(firms),
        "pooled": pooled, "a_prime": a_p, "b_between": b_between, "b_within": b_within, "r2": r2,
        "w_between": w_b, "w_within": w_w, "bs": bs,
        "expected_roa": grand, "expected_roe": float(roe.mean()),
        "interpretation": {
            "between": f"Nếu ROA của DN A cao hơn DN B 1%, ROE của A cao hơn B khoảng {b_between:.2f}%.",
            "within": f"Nếu ROA của một DN tăng 1%, ROE của DN đó tăng khoảng {b_within:.2f}%.",
            "stability": ("bs > bB: trạng thái ổn định chung của ngành mạnh hơn khác biệt giữa các DN."
                          if bs and bs > b_between else
                          "bs ≤ bB: khác biệt giữa các DN chi phối hiệu quả tài chính của ngành."),
        },
        "firms": firms,
    }
