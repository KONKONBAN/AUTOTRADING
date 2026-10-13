"""Kiểm thử vòng lặp AI Agent với client Claude giả lập (không gọi API thật)."""
import copy
from types import SimpleNamespace

from anthropic.types.beta import BetaMessage, BetaTextBlock, BetaToolUseBlock, BetaUsage

from app.agent import agent, llm


def _msg(content, stop):
    return BetaMessage(id="msg_x", type="message", role="assistant", model="claude-opus-5-5", content=content,
                       stop_reason=stop, stop_sequence=None, usage=BetaUsage(input_tokens=1, output_tokens=1))


class FakeMessages:
    def __init__(self):
        self.calls = []
        self.responses = [
            _msg([BetaTextBlock(type="text", text="Để tôi kiểm tra."),
                  BetaToolUseBlock(type="tool_use", id="tu_1", name="analyze_stock", input={"ticker": "FPT"}),
                  BetaToolUseBlock(type="tool_use", id="tu_2", name="propose_order",
                                   input={"ticker": "FPT", "side": "BUY", "quantity": 100, "reason": "test"})],
                 "tool_use"),
            _msg([BetaTextBlock(type="text", text="FPT đạt điểm tốt. Đã tạo đề xuất mua.")], "end_turn"),
        ]

    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))  # chụp lại request tại thời điểm gọi
        return self.responses[len(self.calls) - 1]


def test_agent_tool_loop(monkeypatch):
    fake = FakeMessages()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(llm, "get_client", lambda: SimpleNamespace(beta=SimpleNamespace(messages=fake)))
    out = agent.chat("Có nên mua FPT không?")
    assert out["reply"] == "FPT đạt điểm tốt. Đã tạo đề xuất mua."
    assert [t["name"] for t in out["tools"]] == ["analyze_stock", "propose_order"]
    assert out["proposals"] and out["proposals"][0]["status"] == "pending"
    second = fake.calls[1]
    # lịch sử append-only: user → assistant(tool_use) → user(tool_result, cả 2 kết quả trong 1 message)
    roles = [m["role"] for m in second["messages"]]
    assert roles == ["user", "assistant", "user"]
    results = second["messages"][2]["content"]
    assert {r["tool_use_id"] for r in results} == {"tu_1", "tu_2"}
    assert second["fallbacks"] == "default" and second["model"] == "claude-opus-5-5"
    assert second["system"][0]["cache_control"] == {"type": "ephemeral"}
    # phiên được lưu và hiển thị lại được
    tr = agent.transcript(out["session_id"])
    assert tr[0]["role"] == "user" and tr[-1]["text"].startswith("FPT")
