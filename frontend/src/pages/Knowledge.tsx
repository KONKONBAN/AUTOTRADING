import { useState } from "react";
import { Link } from "react-router-dom";
import { BookOpen, Bot, ChevronDown } from "lucide-react";
import { api } from "../lib/api";
import { Card, ErrorBox, Loading, useAsync } from "../components/ui";

const TITLES: Record<string, string> = {
  quy_trinh_dau_tu: "Quy trình đầu tư cổ phiếu 4 bước",
  sinh_loi_rui_ro: "Mức sinh lời & rủi ro",
  trai_phieu: "Phân tích & định giá trái phiếu",
  thi_truong_vn: "Quy định giao dịch TTCK Việt Nam",
  bao_cao_tai_chinh: "Báo cáo tài chính & kế toán",
  don_bay_mm: "Đòn bẩy tài chính - mô hình ROE–ROA (MM mở rộng)",
  dinh_gia: "Định giá doanh nghiệp & dự án (DCF, WACC, NPV, IRR)",
  toan_tai_chinh: "Toán tài chính",
  market_timing: "Market-timing VN-Index",
  danh_muc: "Xây dựng danh mục tối ưu",
  tai_chinh_ca_nhan: "Quản trị tài chính cá nhân",
};

export default function Knowledge() {
  const k = useAsync(() => api.get("/api/knowledge"), []);
  const [open, setOpen] = useState<string | null>("quy_trinh_dau_tu");
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Kiến thức nền tảng</h1>
          <p>Tóm lược từ bộ tài liệu chứng khoán - tài chính - kế toán của bạn. Đây cũng là "bộ não" kiến thức của AI Agent và các mô hình phân tích.</p>
        </div>
        <Link to="/agent" className="btn primary"><Bot size={16} /> Hỏi AI để giải thích thêm</Link>
      </div>
      {k.loading ? <Loading /> : k.error || !k.data ? <ErrorBox error={k.error ?? "Không có dữ liệu"} onRetry={k.reload} /> : (
        <div className="col" style={{ gap: 10 }}>
          {Object.entries(k.data.topics as Record<string, string>).map(([key, text]) => (
            <Card key={key}>
              <button className="row between" style={{ width: "100%", background: "none", border: 0, color: "inherit", cursor: "pointer", padding: 0, font: "inherit" }}
                onClick={() => setOpen(open === key ? null : key)}>
                <h3 className="row" style={{ gap: 10 }}><span className="kpi-icon"><BookOpen size={16} /></span>{TITLES[key] ?? key}</h3>
                <ChevronDown size={18} style={{ transform: open === key ? "rotate(180deg)" : undefined, transition: "0.2s" }} />
              </button>
              {open === key && <div className="muted" style={{ whiteSpace: "pre-wrap", marginTop: 14, lineHeight: 1.75 }}>{text}</div>}
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
