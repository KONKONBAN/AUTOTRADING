"""AI Agent quản trị tài sản & tài chính (Claude + tool use).

Vòng lặp agent tự viết (manual loop) để kiểm soát chặt: giới hạn số vòng, lưu lịch sử hội thoại
append-only, và KHÔNG có công cụ nào tự khớp lệnh (chỉ tạo đề xuất chờ người dùng duyệt).
Khi chưa có API key, Agent chạy chế độ "ngoại tuyến" dựa trên luật để vẫn trả lời được các câu hỏi cơ bản.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from datetime import date

import anthropic

from .. import services
from ..config import settings
from ..data import universe
from ..db import get_db
from ..utils import vn_num, vn_pct
from . import knowledge, llm, tools

MAX_TURNS = 10

SYSTEM_ROLE = """Bạn là "Trợ lý Quản trị Tài sản" - AI Agent quản lý tài sản và tài chính cá nhân cho nhà đầu tư Việt Nam,
tích hợp trong ứng dụng AutoTrading VN. Bạn kết hợp phân tích kỹ thuật, phân tích cơ bản/kế toán, định giá, quản trị rủi ro
và lập kế hoạch tài chính cá nhân, dựa trên kiến thức nền tảng bên dưới (giáo trình của chính người dùng) và dữ liệu từ các công cụ.

Nguyên tắc làm việc:
1. Luôn trả lời bằng tiếng Việt, rõ ràng, có cấu trúc (tiêu đề ngắn, gạch đầu dòng, bảng khi so sánh). Số tiền ghi theo kiểu VN (120.500đ).
2. Mọi nhận định về cổ phiếu/thị trường/danh mục PHẢI dựa trên số liệu lấy từ công cụ trong lượt này - không bịa số.
   Nêu rõ nguồn dữ liệu (data_sources). Nếu nguồn là "demo" thì cảnh báo rõ đây là dữ liệu mô phỏng, khuyên người dùng
   tải dữ liệu thật (Excel/CSV giá & BCTC) ở mục "Dữ liệu & Nhập liệu".
3. Tuân thủ quy trình đầu tư 4 bước và kỷ luật quản trị rủi ro: kiểm tra thị trường chung trước khi khuyến nghị giải ngân,
   luôn kèm điểm cắt lỗ (≤ 7%), tỷ trọng mỗi mã ≤ 20-25%, mua chia nhiều lần, không khuyến khích margin với người mới.
4. Không hứa hẹn hay đảm bảo lợi nhuận. Trình bày cả rủi ro (hệ thống & phi hệ thống) và kịch bản xấu.
5. Bạn KHÔNG tự đặt lệnh. Khi người dùng muốn giao dịch, dùng `propose_order` để tạo đề xuất; nhắc người dùng duyệt ở tab
   "Giao dịch tự động". Kiểm tra tiền mặt/khối lượng khả dụng bằng `get_portfolio` trước khi đề xuất.
6. Với câu hỏi kiến thức (công thức, kế toán, trái phiếu, định giá...), giải thích kèm ví dụ số, dùng `financial_calculator`
   để tính chính xác.
7. Với tài chính cá nhân: ưu tiên quỹ dự phòng, trả nợ lãi cao, rồi mới đầu tư; dùng `personal_finance_plan`.
8. Khi người dùng gửi ảnh biểu đồ nến hoặc ảnh/PDF BCTC: đọc kỹ ảnh, mô tả xu hướng/mô hình/mức giá quan trọng hoặc số liệu chính,
   rồi đối chiếu với `analyze_stock` nếu biết mã.

=== KIẾN THỨC NỀN TẢNG (từ tài liệu của người dùng) ===
"""


def _system() -> list[dict]:
    return [
        {"type": "text", "text": SYSTEM_ROLE + knowledge.full_text(), "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": f"Hôm nay là {date.today():%d/%m/%Y}. Danh sách mã theo dõi: "
                                 f"{', '.join(universe.UNIVERSE)}. Các ngành: {', '.join(universe.sectors())}."},
    ]


# ------------------------------------------------------------------ sessions
def _load(session_id: str) -> dict | None:
    row = get_db().query_one("SELECT * FROM agent_sessions WHERE id=?", (session_id,))
    if row:
        row["messages"] = json.loads(row["messages"])
    return row


def _save(session_id: str, messages: list, title: str | None = None) -> None:
    now = time.time()
    db = get_db()
    if db.query_one("SELECT id FROM agent_sessions WHERE id=?", (session_id,)):
        db.execute("UPDATE agent_sessions SET messages=?, updated_at=? WHERE id=?",
                   (json.dumps(messages, ensure_ascii=False), now, session_id))
    else:
        db.execute("INSERT INTO agent_sessions(id, created_at, updated_at, title, messages) VALUES(?,?,?,?,?)",
                   (session_id, now, now, title or "Cuộc trò chuyện mới", json.dumps(messages, ensure_ascii=False)))


def list_sessions() -> list[dict]:
    return get_db().query("SELECT id, title, created_at, updated_at FROM agent_sessions ORDER BY updated_at DESC LIMIT 50")


def delete_session(session_id: str) -> None:
    get_db().execute("DELETE FROM agent_sessions WHERE id=?", (session_id,))


def transcript(session_id: str) -> list[dict]:
    """Lịch sử hội thoại dạng hiển thị (ẩn chi tiết kỹ thuật)."""
    s = _load(session_id)
    if not s:
        return []
    out = []
    for m in s["messages"]:
        content = m["content"]
        if isinstance(content, str):
            out.append({"role": m["role"], "text": content})
            continue
        texts = [b.get("text", "") for b in content if b.get("type") == "text"]
        tool_uses = [{"name": b["name"], "input": b.get("input")} for b in content if b.get("type") == "tool_use"]
        files = sum(1 for b in content if b.get("type") in {"image", "document"})
        if m["role"] == "user" and all(b.get("type") == "tool_result" for b in content):
            continue
        if texts or tool_uses or files:
            out.append({"role": m["role"], "text": "\n".join(t for t in texts if t), "tools": tool_uses,
                        "attachments": files})
    return out


# ------------------------------------------------------------------ chat
def chat(message: str, session_id: str | None = None,
         attachments: list[tuple[bytes, str]] | None = None) -> dict:
    session_id = session_id or uuid.uuid4().hex[:12]
    if not settings.has_anthropic_credentials:
        return offline_chat(message, session_id)
    session = _load(session_id)
    messages: list = session["messages"] if session else []
    user_content: list[dict] = [llm.file_block(d, mt) for d, mt in (attachments or [])]
    user_content.append({"type": "text", "text": message})
    messages.append({"role": "user", "content": user_content})
    title = (message[:60] + "…") if len(message) > 60 else message

    client = llm.get_client()
    tool_log, proposals, final_text = [], [], ""
    for _ in range(MAX_TURNS):
        try:
            response = client.beta.messages.create(
                max_tokens=16000, system=_system(), tools=tools.TOOLS, messages=messages, **llm.common_params())
        except anthropic.AuthenticationError:
            return {"session_id": session_id, "reply": "❌ API key Claude không hợp lệ. Kiểm tra ANTHROPIC_API_KEY trong .env.",
                    "tools": tool_log, "proposals": proposals, "error": True}
        except anthropic.RateLimitError:
            return {"session_id": session_id, "reply": "⏳ Đã chạm giới hạn tốc độ của Claude API, vui lòng thử lại sau ít phút.",
                    "tools": tool_log, "proposals": proposals, "error": True}
        except anthropic.APIStatusError as exc:
            return {"session_id": session_id, "reply": f"❌ Lỗi Claude API ({exc.status_code}): {exc.message}",
                    "tools": tool_log, "proposals": proposals, "error": True}
        except anthropic.APIConnectionError:
            return {"session_id": session_id, "reply": "❌ Không kết nối được tới Claude API. Kiểm tra Internet.",
                    "tools": tool_log, "proposals": proposals, "error": True}

        if response.stop_reason == "refusal":
            final_text = "Xin lỗi, tôi không thể hỗ trợ yêu cầu này."
            messages.pop() if messages and messages[-1]["role"] == "user" and not tool_log else None
            break
        content = [b.to_dict(exclude_none=True) for b in response.content if b.type != "fallback"]
        messages.append({"role": "assistant", "content": content})
        texts = [b.text for b in response.content if b.type == "text"]
        if texts:
            final_text = "\n".join(texts)
        if response.stop_reason == "pause_turn":
            continue
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_uses:
            if response.stop_reason == "max_tokens":
                final_text += "\n\n_(Câu trả lời bị cắt do quá dài - hãy hỏi tiếp để xem phần còn lại.)_"
            break
        results = []
        for tu in tool_uses:
            out, is_error = tools.execute(tu.name, tu.input)
            tool_log.append({"name": tu.name, "input": tu.input, "error": is_error})
            if tu.name == "propose_order" and not is_error:
                proposals.append(json.loads(out))
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": out, "is_error": is_error})
        messages.append({"role": "user", "content": results})
    else:
        final_text += "\n\n_(Đã dừng sau nhiều bước phân tích - hãy hỏi cụ thể hơn.)_"

    _save(session_id, messages, title if not session else None)
    return {"session_id": session_id, "reply": final_text, "tools": tool_log, "proposals": proposals}


# ------------------------------------------------------------------ offline mode
def _fmt_pct(x) -> str:
    return vn_pct(x, sign=True)


def _vnd(x) -> str:
    return vn_num(x)


def offline_chat(message: str, session_id: str) -> dict:
    """Trả lời dựa trên luật khi chưa có API key (vẫn dùng toàn bộ mô hình phân tích của hệ thống)."""
    msg = message.upper()
    tickers = [t for t in re.findall(r"\b[A-Z]{3}\b", msg) if t in universe.UNIVERSE]
    low = message.lower()
    used = []
    if tickers:
        parts = []
        for t in tickers[:3]:
            a = services.analyze_stock(t, include_chart=False)
            used.append({"name": "analyze_stock", "input": {"ticker": t}})
            c, v, p = a["composite"], a["valuation"], a["trade_plan"]
            parts.append(
                f"### {t} - {a['info']['name']}\n"
                f"**{c['recommendation']}** · Điểm tổng hợp **{vn_num(c['score'])}/100** "
                f"(kỹ thuật {vn_num(c['parts']['technical'])}, chất lượng {vn_num(c['parts']['quality'])}, "
                f"định giá {vn_num(c['parts']['valuation'])}, rủi ro {vn_num(c['parts']['risk'])})\n\n"
                + "\n".join(f"- ✅ {x}" for x in a["summary"]["pros"])
                + "\n" + "\n".join(f"- ⚠️ {x}" for x in a["summary"]["cons"])
                + f"\n\n**Kế hoạch:** vùng mua {_vnd(p['entry_zone'][0])}–{_vnd(p['entry_zone'][1])}đ · "
                  f"cắt lỗ {_vnd(p['stop_loss'])}đ · mục tiêu {_vnd(p['take_profit_1'])}đ / {_vnd(p['take_profit_2'])}đ\n\n"
                  f"_Nguồn dữ liệu: giá {a['data_sources']['prices']}, BCTC {a['data_sources']['financials']}_")
        reply = "\n\n".join(parts)
    elif any(k in low for k in ("thị trường", "vnindex", "vn-index", "vn index")):
        m = services.market_overview()
        used.append({"name": "get_market_overview", "input": {}})
        reply = (f"### Thị trường chung (VN-Index {vn_num(m['price'], 2)})\n**{m['regime']}** - tỷ trọng cổ phiếu khuyến nghị "
                 f"**{vn_pct(m['recommended_exposure'], 0)}**\n- Xu hướng năm hóa: {_fmt_pct(m['trend_annualized'])}\n"
                 f"- Ngày phân phối (25 phiên): {m['distribution_days']}\n" + "\n".join(f"- {n}" for n in m["notes"]))
    elif any(k in low for k in ("danh mục", "tài khoản", "portfolio", "lãi lỗ")):
        acc = tools.t_get_portfolio()
        used.append({"name": "get_portfolio", "input": {}})
        lines = [f"- {p['ticker']}: {_vnd(p['quantity'])} CP, giá vốn {_vnd(p['avg_price'])}đ, lãi/lỗ {_fmt_pct(p['unrealized_pct'])}"
                 for p in acc["positions"]] or ["- Chưa có vị thế nào."]
        reply = (f"### Tài khoản\nTổng tài sản **{_vnd(acc['equity'])}đ** · Tiền mặt {_vnd(acc['cash'])}đ · "
                 f"Lợi nhuận {_fmt_pct(acc['total_return'])}\n" + "\n".join(lines))
    elif any(k in low for k in ("lọc", "top", "nên mua", "gợi ý", "cổ phiếu tốt", "xếp hạng")):
        rows = services.screen()[:8]
        used.append({"name": "screen_stocks", "input": {}})
        reply = "### Top cổ phiếu theo điểm tổng hợp\n| Mã | Điểm | Khuyến nghị | Xu hướng | Upside |\n|---|---|---|---|---|\n" + \
            "\n".join(f"| {r['ticker']} | {vn_num(r['score'])} | {r['recommendation']} | {r['trend']} | {_fmt_pct(r['upside'])} |"
                      for r in rows)
    else:
        reply = "### Kiến thức liên quan\n" + knowledge.search(message)
    reply += ("\n\n---\n_💡 AI Agent đang chạy chế độ cơ bản (chưa cấu hình ANTHROPIC_API_KEY). "
              "Thêm API key vào file `.env` để trò chuyện tự nhiên, đọc ảnh biểu đồ/BCTC và tư vấn chuyên sâu._")
    session = _load(session_id)
    messages = session["messages"] if session else []
    messages += [{"role": "user", "content": message}, {"role": "assistant", "content": reply}]
    _save(session_id, messages, message[:60] if not session else None)
    return {"session_id": session_id, "reply": reply, "tools": used, "proposals": [], "offline": True}
