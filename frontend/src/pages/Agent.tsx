import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, Check, MessageSquarePlus, Paperclip, Send, Trash2, User, Wrench, X } from "lucide-react";
import { api } from "../lib/api";
import { useStatus } from "../lib/status";
import { cls, vnd } from "../lib/format";
import { Alert, Badge, Card, useToast } from "../components/ui";

const TOOL_LABEL: Record<string, string> = {
  get_market_overview: "Thị trường chung", analyze_stock: "Phân tích cổ phiếu", compare_stocks: "So sánh cổ phiếu",
  screen_stocks: "Lọc cổ phiếu", get_portfolio: "Đọc danh mục", optimize_portfolio: "Tối ưu danh mục",
  propose_order: "Tạo đề xuất lệnh", get_autotrader_plan: "Kế hoạch Auto-Trader", run_backtest: "Backtest",
  financial_calculator: "Máy tính tài chính", personal_finance_plan: "Kế hoạch tài chính cá nhân",
  sector_analysis: "Phân tích ngành", search_knowledge: "Tra cứu kiến thức",
};
const SUGGEST = [
  "Thị trường hiện tại có nên giải ngân không? Tỷ trọng cổ phiếu bao nhiêu là hợp lý?",
  "Lọc giúp tôi 5 cổ phiếu tốt nhất và lập danh mục 300 triệu tối ưu",
  "Phân tích FPT: định giá DCF, đòn bẩy ROE–ROA và kế hoạch giao dịch",
  "Thu nhập 30 triệu/tháng, chi 18 triệu, 28 tuổi, muốn mua nhà 2 tỷ sau 8 năm - lập kế hoạch giúp tôi",
  "Trái phiếu mệnh giá 1 triệu, coupon 10%, giá 1.035.000, còn 2 năm - YTM là bao nhiêu?",
  "Đánh giá danh mục hiện tại của tôi và đề xuất cơ cấu lại",
];

type Msg = { role: "user" | "assistant"; text: string; tools?: { name: string; input?: any; error?: boolean }[]; proposals?: any[]; attachments?: number; files?: string[] };

export default function Agent() {
  const { status } = useStatus();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [sessions, setSessions] = useState<any[]>([]);
  const [sid, setSid] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const sentQ = useRef(false);
  // Chống race: mỗi lúc chỉ MỘT câu hỏi được xử lý (ô soạn bị khóa đến khi có trả lời, kể cả khi người dùng
  // chuyển cuộc trò chuyện). Câu trả lời chỉ được nối vào màn hình đang xem nếu đúng cuộc trò chuyện đó.
  const activeRef = useRef<string | null>(null);
  const navSeq = useRef(0);
  const pending = useRef<{ sid: string | null } | null>(null);
  const openSeq = useRef(0);  // chỉ lần mở cuộc trò chuyện mới nhất được áp dụng
  const [typingHere, setTypingHere] = useState(false);

  const loadSessions = () => api.get("/api/agent/sessions").then(setSessions).catch(() => {});
  useEffect(() => { loadSessions(); }, []);
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" }); }, [msgs, busy]);
  useEffect(() => {
    const q = params.get("q");
    if (q && !sentQ.current) {
      sentQ.current = true;
      setParams({}, { replace: true });
      send(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const open = async (id: string) => {
    if (id === activeRef.current) return;  // đang xem đúng cuộc trò chuyện này
    const req = ++openSeq.current;
    let r: any;
    try {
      r = await api.get(`/api/agent/sessions/${id}`);
    } catch (e: any) {  // giữ nguyên màn hình hiện tại để bấm lại là thử tải lại
      if (openSeq.current === req) toast("err", `Không tải được cuộc trò chuyện: ${e.message}`);
      return;
    }
    if (openSeq.current !== req) return;
    navSeq.current++;
    activeRef.current = id;
    setSid(id);
    setTypingHere(pending.current?.sid === id);
    setMsgs(r.messages);
  };
  const newChat = () => {
    openSeq.current++;
    navSeq.current++;
    activeRef.current = null;
    setTypingHere(false);
    setSid(null); setMsgs([]); setInput(""); setFiles([]);
  };
  const remove = async (id: string) => {
    await api.del(`/api/agent/sessions/${id}`);
    if (id === sid) newChat();
    loadSessions();
  };

  async function send(text?: string) {
    const message = (text ?? input).trim();
    if (!message || busy) return;
    setMsgs((m) => [...m, { role: "user", text: message, attachments: files.length, files: files.map((f) => f.name) }]);
    setInput("");
    setBusy(true);
    const form = new FormData();
    form.append("message", message);
    if (sid) form.append("session_id", sid);
    files.forEach((f) => form.append("files", f));
    setFiles([]);
    setTypingHere(true);
    const nav = navSeq.current;
    const sentSid = sid;
    pending.current = { sid };
    const reply = (r: any): Msg => ({ role: "assistant", text: r.reply, tools: r.tools, proposals: r.proposals });
    try {
      const r = await api.form("/api/agent/chat", form);
      if (navSeq.current === nav) {  // người dùng vẫn ở cuộc trò chuyện này
        setSid(r.session_id);
        activeRef.current = r.session_id;
        setMsgs((m) => [...m, reply(r)]);
      } else if (activeRef.current === r.session_id) {  // đã rời đi rồi quay lại: tải lại bản ghi đầy đủ
        const s = await api.get(`/api/agent/sessions/${r.session_id}`);
        if (activeRef.current === r.session_id) {
          const m: Msg[] = s.messages;
          const lastUser = [...m].reverse().find((x) => x.role === "user");
          if (lastUser?.text?.trim() !== message) {
            // câu hỏi không được lưu (lỗi API / bị từ chối) → hiển thị lại câu hỏi và phản hồi
            setMsgs([...m, { role: "user", text: message }, reply(r)]);
          } else if (r.proposals?.length && m.length) {
            // thẻ đề xuất lệnh không nằm trong bản ghi lưu trữ → gắn vào câu trả lời cuối
            setMsgs([...m.slice(0, -1), { ...m[m.length - 1], proposals: r.proposals }]);
          } else {
            setMsgs(m);
          }
        }
      }
      loadSessions();
    } catch (e: any) {
      if (navSeq.current === nav) setMsgs((m) => [...m, { role: "assistant", text: `❌ ${e.message}` }]);
      else if (sentSid && activeRef.current === sentSid)
        setMsgs((m) => [...m, { role: "user", text: message }, { role: "assistant", text: `❌ ${e.message}` }]);
    } finally {
      pending.current = null;
      setBusy(false);
      setTypingHere(false);
    }
  }

  const decide = async (pid: number, ok: boolean) => {
    try {
      const r = await api.post(`/api/proposals/${pid}/${ok ? "approve" : "reject"}`);
      toast(r.status === "failed" ? "err" : "ok", r.status === "executed" ? "Đã khớp lệnh trên tài khoản giấy." : r.status === "rejected" ? "Đã từ chối đề xuất." : r.error);
      setMsgs((m) => m.map((x) => ({ ...x, proposals: x.proposals?.map((p) => (p.proposal_id === pid ? { ...p, status: r.status } : p)) })));
    } catch (e: any) {
      toast("err", e.message);
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>AI Agent quản trị tài sản</h1>
          <p>Trợ lý phân tích đầu tư, quản trị danh mục & tài chính cá nhân - dựa trên kiến thức giáo trình của bạn và dữ liệu thời gian thực.</p>
        </div>
        <div className="row">
          {status && <Badge lg tone={status.ai_enabled ? "brand" : "warn"}><Bot size={13} /> {status.ai_enabled ? `Claude · ${status.ai_model}` : "Chế độ cơ bản (chưa có API key)"}</Badge>}
          <button className="btn" onClick={newChat}><MessageSquarePlus size={15} /> Cuộc trò chuyện mới</button>
        </div>
      </div>
      {status && !status.ai_enabled && (
        <Alert kind="warn" title="AI đang chạy chế độ cơ bản">
          Thêm <code>ANTHROPIC_API_KEY</code> vào file <code>.env</code> rồi khởi động lại để bật trò chuyện tự nhiên, đọc ảnh biểu đồ/BCTC và tư vấn chuyên sâu.
          Chế độ cơ bản vẫn trả lời được: phân tích mã (VD "FPT"), thị trường, danh mục, top cổ phiếu, tra cứu kiến thức.
        </Alert>
      )}
      <div className="chat">
        <Card className="chat-side">
          <div className="small bold muted" style={{ marginBottom: 4 }}>Lịch sử trò chuyện</div>
          {sessions.length === 0 && <div className="small subtle">Chưa có cuộc trò chuyện.</div>}
          {sessions.map((s) => (
            <div key={s.id} className={cls("nav-link", s.id === sid && "active")} style={{ cursor: "pointer", padding: "8px 10px" }} onClick={() => open(s.id)}>
              <span className="grow small" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.title}</span>
              <button className="btn sm icon ghost" onClick={(e) => { e.stopPropagation(); remove(s.id); }}><Trash2 size={13} /></button>
            </div>
          ))}
        </Card>
        <div className="card chat-main">
          <div className="chat-log" ref={logRef}>
            {msgs.length === 0 && (
              <div className="col" style={{ alignItems: "center", gap: 18, margin: "auto", maxWidth: 720, textAlign: "center" }}>
                <div className="avatar ai" style={{ width: 64, height: 64, borderRadius: 20 }}><Bot size={32} /></div>
                <h2>Xin chào! Tôi có thể giúp gì cho bạn hôm nay?</h2>
                <p className="muted">Tôi phân tích cổ phiếu (kỹ thuật, cơ bản, định giá), đánh giá thị trường, tối ưu danh mục, lập kế hoạch tài chính cá nhân,
                  giải bài toán tài chính - và có thể đọc ảnh biểu đồ nến hoặc ảnh/PDF báo cáo tài chính bạn gửi.</p>
                <div className="row wrap" style={{ justifyContent: "center", gap: 8 }}>
                  {SUGGEST.map((s) => <button key={s} className="chip" onClick={() => send(s)}>{s}</button>)}
                </div>
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={cls("msg", m.role === "user" && "user")}>
                <div className={cls("avatar", m.role === "user" ? "me" : "ai")}>{m.role === "user" ? <User size={17} /> : <Bot size={17} />}</div>
                <div className="col" style={{ gap: 6, minWidth: 0 }}>
                  {m.tools && m.tools.length > 0 && (
                    <div>{m.tools.map((t, j) => (
                      <span key={j} className="tool-chip" title={JSON.stringify(t.input)}><Wrench size={11} /> {TOOL_LABEL[t.name] ?? t.name}{t.input?.ticker ? `: ${t.input.ticker}` : ""}{t.error ? " ⚠" : ""}</span>
                    ))}</div>
                  )}
                  <div className="bubble">
                    {m.role === "assistant" ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown> : <p style={{ whiteSpace: "pre-wrap" }}>{m.text}</p>}
                    {!!m.attachments && <div className="tiny subtle" style={{ marginTop: 6 }}><Paperclip size={11} /> {m.files?.join(", ") || `${m.attachments} tệp đính kèm`}</div>}
                  </div>
                  {m.proposals?.filter((p) => p.proposal_id).map((p) => (
                    <div key={p.proposal_id} className="card tight row wrap" style={{ gap: 10 }}>
                      <Badge tone="info">Đề xuất lệnh #{p.proposal_id}</Badge>
                      <span className="small grow">{p.message}</span>
                      {p.status && p.status !== "pending" ? <Badge tone={p.status === "executed" ? "up" : "down"}>{p.status === "executed" ? "Đã khớp" : p.status === "rejected" ? "Đã từ chối" : "Lỗi"}</Badge> : (
                        <>
                          <button className="btn sm buy" onClick={() => decide(p.proposal_id, true)}><Check size={13} /> Duyệt</button>
                          <button className="btn sm" onClick={() => decide(p.proposal_id, false)}><X size={13} /> Bỏ</button>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
            {busy && typingHere && (
              <div className="msg">
                <div className="avatar ai"><Bot size={17} /></div>
                <div className="bubble"><span className="typing"><span /><span /><span /></span> <span className="small subtle">Đang phân tích dữ liệu…</span></div>
              </div>
            )}
          </div>
          <div className="composer">
            {files.length > 0 && (
              <div className="row wrap" style={{ gap: 6 }}>
                {files.map((f, i) => (
                  <span key={i} className="chip on">{f.name} · {vnd(f.size / 1024)} KB <X size={12} onClick={() => setFiles(files.filter((_, j) => j !== i))} /></span>
                ))}
              </div>
            )}
            <div className="composer-row">
              <button className="btn icon" title="Đính kèm ảnh biểu đồ nến / ảnh-PDF báo cáo tài chính" onClick={() => fileRef.current?.click()} disabled={!status?.ai_enabled}>
                <Paperclip size={17} />
              </button>
              <input ref={fileRef} type="file" hidden multiple accept="image/png,image/jpeg,image/webp,application/pdf"
                onChange={(e) => { setFiles([...files, ...Array.from(e.target.files ?? [])]); e.target.value = ""; }} />
              <textarea className="input grow" rows={1}
                placeholder={busy && !typingHere ? "AI đang trả lời ở một cuộc trò chuyện khác - vui lòng chờ…"
                  : "Hỏi về cổ phiếu, danh mục, tài chính cá nhân… (Enter để gửi, Shift+Enter xuống dòng)"}
                value={input} onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
              <button className="btn primary icon" onClick={() => send()} disabled={busy || !input.trim()}><Send size={17} /></button>
            </div>
            <div className="tiny subtle">AI Agent không tự đặt lệnh: mọi lệnh đều là đề xuất và cần bạn duyệt. Thông tin chỉ mang tính tham khảo, không phải cam kết lợi nhuận.</div>
          </div>
        </div>
      </div>
    </>
  );
}
