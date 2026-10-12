# AutoTrading VN — Phân tích cổ phiếu, giao dịch tự động & AI Agent quản trị tài sản

Ứng dụng **Web + App (PWA cài được trên điện thoại)** cho nhà đầu tư chứng khoán Việt Nam:

- **Phân tích cổ phiếu toàn diện**: kỹ thuật, cơ bản/kế toán, định giá, rủi ro → điểm tổng hợp 0–100 và khuyến nghị.
- **Giao dịch tự động có kỷ luật**: lọc cổ phiếu, mua chia lần, cắt lỗ, trailing stop, điều chỉnh tỷ trọng theo thị trường, ngưng mua khi tài khoản sụt sâu (kill-switch), kèm backtest.
- **AI Agent quản trị tài sản & tài chính** (Claude): trò chuyện tiếng Việt, gọi các mô hình phân tích của hệ thống, đọc ảnh biểu đồ nến và ảnh/PDF báo cáo tài chính, lập kế hoạch tài chính cá nhân, tạo đề xuất lệnh để bạn duyệt.
- **Dữ liệu tự động nhiều nguồn**: VNDirect → SSI iBoard → TCBS → VPS → Vietstock → CafeF. Khi **không nguồn nào truy cập được**, bạn tải dữ liệu lên (Excel/CSV giá, Excel/ảnh/PDF BCTC, ảnh biểu đồ).

> ⚠️ **Lưu ý quan trọng**: Không phần mềm nào đảm bảo lợi nhuận. Ứng dụng giúp bạn ra quyết định có kỷ luật và quản trị rủi ro tốt hơn; mọi khuyến nghị chỉ mang tính tham khảo. Mặc định ứng dụng chỉ giao dịch trên **tài khoản giấy (mô phỏng)**.

---

## 1. Kiến thức nền tảng được tích hợp

Toàn bộ mô hình được xây dựng từ bộ tài liệu trong Google Drive của bạn:

| Tài liệu | Áp dụng trong ứng dụng |
|---|---|
| PTVĐTCK bài 0, chương 1 (TTCK, quy định giao dịch) | Lô 100 CP, biên độ HOSE ±7% / HNX ±10% / UPCoM ±15%, bước giá, phí 0,15%, thuế bán 0,1%, T+2 — áp dụng trong tài khoản giấy & Auto-Trader |
| PTVĐTCK chương 2 (sinh lời & rủi ro, quy trình đầu tư 4 bước) | Sinh lời HPR, lũy kế, bình quân hình học/số học, IRR, kỳ vọng theo kịch bản, phương sai; rủi ro hệ thống/phi hệ thống; quy trình chọn → mua → bán → quản trị rủi ro của Auto-Trader |
| PTVĐTCK chương 3 (trái phiếu) | Định giá TP thường/zero/vĩnh cửu, CY, YTM, duration, TP chuyển đổi |
| FQA session 1–2, bài mẫu đòn bẩy BĐS, file "Analysis of ROE, ROA for an industry" | Mô hình MM mở rộng `ROE = (1+LEV)·ROA_op − LEV·Sd`, hồi quy `ROE = a + b·ROA`, `b* = 1 + LEV`, `bs = E(ROE)/E(ROA)`, phân rã **Mundlak** trạng thái/động lực cho từng ngành, DuPont |
| File "Market-Timing Forecast for VN-INDEX" | Mô hình xu hướng `lnP = a + b·t + u` trượt 120 phiên, d(b), độ lệch u → trạng thái thị trường & tỷ trọng cổ phiếu khuyến nghị |
| CFA — Định giá dự án qua DCF & WACC | DCF/FCFF chiết khấu WACC (trọng số thị trường), NPV, IRR, MIRR, PI, thời gian hoàn vốn |
| Toán tài chính (lãi đơn, lãi kép, chiết khấu thương phiếu, chuỗi tiền tệ, vay vốn) | Máy tính tài chính & kế hoạch tài chính cá nhân |
| Kế toán tài chính 2 (C1–C4, Thông tư 99/2025) | Cấu trúc 3 báo cáo tài chính, bộ đọc BCTC Excel/ảnh/PDF, kiểm tra cân đối A = D + E |
| TCDN chương 9 (thuê mua tài sản) | Máy tính "Thuê tài chính hay vay mua" (NAL) |
| Giáo trình Corporate Finance (Berk–DeMarzo, Ross, Pike–Neale, Tse, Benninga, Dempsey, Pilbeam) | CAPM, chi phí vốn, DDM Gordon, P/B–P/E hợp lý, tăng trưởng bền vững, lý thuyết danh mục Markowitz |

Phần tóm lược kiến thức nằm ở trang **Kiến thức nền tảng** và trong `backend/app/agent/knowledge.py` (cũng là "bộ não" của AI Agent).

## 2. Tính năng chính

| Trang | Nội dung |
|---|---|
| **Tổng quan** | Tài sản, lãi/lỗ, VN-Index + đường xu hướng, đồng hồ trạng thái thị trường, cổ phiếu nổi bật, đề xuất lệnh chờ duyệt, phân bổ tài sản |
| **Phân tích cổ phiếu** | Biểu đồ nến (MA20/50/200, Bollinger, khối lượng, RSI, MACD) theo **khoảng thời gian tùy chọn**; 15+ tín hiệu kỹ thuật, mô hình nến, hỗ trợ/kháng cự; chỉ tiêu tài chính theo năm, MM, DuPont, Piotroski F-Score; 7 mô hình định giá; 12 chỉ số rủi ro; kế hoạch giao dịch & đặt lệnh |
| **Bộ lọc & xếp hạng** | Chấm điểm 44 mã thanh khoản cao, lọc theo ngành/điểm/khuyến nghị, sắp xếp mọi cột |
| **Danh mục & tối ưu** | Tài khoản giấy, vị thế (khả dụng T+2), lịch sử lệnh, tối ưu Markowitz (max Sharpe / min rủi ro, giới hạn tỷ trọng), đường biên hiệu quả |
| **Giao dịch tự động** | 3 chế độ: Tắt / **Đề xuất** (mặc định — bạn duyệt từng lệnh) / Tự động trên tài khoản giấy; tham số rủi ro; chạy theo lịch hằng ngày; backtest so với VN-Index |
| **AI Agent** | Chat tiếng Việt, 13 công cụ phân tích, đính kèm ảnh/PDF, duyệt đề xuất lệnh ngay trong khung chat |
| **Tài chính cá nhân** | Ngân sách 50/30/20, quỹ dự phòng, thứ tự trả nợ, phân bổ tài sản theo khẩu vị rủi ro & tuổi, mục tiêu, dự phóng; trắc nghiệm khẩu vị rủi ro; 13 máy tính tài chính |
| **Dữ liệu & nhập liệu** | Kiểm tra 6 nguồn tự động; tải lịch sử giá CSV/Excel; **nhập BCTC bằng Excel** (file mẫu hoặc file xuất từ Vietstock/CafeF/FiinPro…), ảnh/PDF (AI đọc), sửa trực tiếp; **phân tích ảnh chụp biểu đồ nến** và đối chiếu với mô hình định lượng |

Giao diện: tông tối chuyên nghiệp (có chế độ sáng), màu theo chuẩn bảng giá VN, tìm mã nhanh `Ctrl+K`, tương thích điện thoại, cài được như app.

## 3. Cài đặt & chạy

Yêu cầu: **Python 3.10+** và **Node.js 18+**.

```bash
# macOS / Linux
./run.sh
# Windows: bấm đúp run.bat
```

Script sẽ tạo file `.env`, cài thư viện, build giao diện rồi chạy tại **http://localhost:8000**.

Chạy thủ công / phát triển:

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
.venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8000   # API: http://localhost:8000/docs
cd frontend && npm install && npm run dev                               # giao diện dev: http://localhost:5173
```

Docker: `docker build -t autotrading . && docker run -p 8000:8000 --env-file .env autotrading`

### Cấu hình `.env`

| Biến | Ý nghĩa |
|---|---|
| `ANTHROPIC_API_KEY` | Khóa Claude API (lấy tại console.anthropic.com). Không có khóa → AI Agent chạy **chế độ cơ bản** (vẫn phân tích được bằng mô hình của hệ thống, nhưng không trò chuyện tự nhiên/đọc ảnh). |
| `AGENT_MODEL` / `AGENT_EFFORT` | Model (mặc định `claude-opus-5-5`) và mức suy luận (`low`…`max`). |
| `DATA_MODE` | `auto` (thử nguồn thật, lỗi thì dùng DEMO) · `live` (chỉ dữ liệu thật) · `demo` (chỉ mô phỏng). |
| `PAPER_INITIAL_CASH` | Vốn tài khoản giấy (mặc định 500 triệu). |
| `ALLOW_LIVE_TRADING` | Mặc định `false`. Xem mục 6. |

### Dùng như app trên điện thoại

Chạy ứng dụng trên máy tính (script đã mở `0.0.0.0`), trên điện thoại cùng mạng Wi-Fi mở `http://<IP-máy-tính>:8000` →
Chrome: menu **⋮ → Cài đặt ứng dụng / Thêm vào màn hình chính**; Safari: **Chia sẻ → Thêm vào MH chính**.
(Để cài PWA đầy đủ ngoài mạng nội bộ cần HTTPS — ví dụ triển khai lên máy chủ có tên miền.)

## 4. Dữ liệu: tự động trước, thủ công khi cần

Thứ tự ưu tiên: **dữ liệu bạn nhập → nguồn tự động → DEMO**.

1. **Nguồn tự động** (`backend/app/data/providers.py`): VNDirect dchart → SSI iBoard → TCBS → VPS → Vietstock → CafeF. Nguồn lỗi kết nối được tạm bỏ qua 5 phút để ứng dụng không bị chậm; nguồn thành công gần nhất được ưu tiên lần sau. BCTC tự động lấy từ TCBS.
2. **Khi tất cả nguồn đều lỗi**, giao diện hiển thị cảnh báo và hướng dẫn nhập tay ở trang **Dữ liệu & nhập liệu**:
   - **Giá**: CSV/Excel định dạng Amibroker `<Ticker>,<DTYYYYMMDD>,<Open>,<High>,<Low>,<Close>,<Volume>` hoặc bảng có tiêu đề *Ngày, Giá mở cửa, Cao nhất, Thấp nhất, Đóng cửa, Khối lượng* (giá nghìn đồng tự quy đổi).
   - **BCTC Excel**: tải **file mẫu** (điền sẵn số liệu thật đã có; không bao giờ điền số DEMO, các ô hệ thống chỉ ước tính được để trống) hoặc dùng file xuất "chỉ tiêu × năm" từ Vietstock/CafeF/FiinPro… Bộ đọc tự nhận diện chỉ tiêu tiếng Việt/Anh, cột năm (bỏ qua cột quý/6 tháng/dự phóng), kiểu số VN `1.234,5` hay EN `1,234.5`, đơn vị (đồng/nghìn/triệu/tỷ, kể cả "1.000.000 VND"), ưu tiên *LNST cổ đông công ty mẹ*, cộng vay ngắn + dài hạn. Bạn **xem lại & sửa** trước khi lưu; nếu đơn vị phải đoán, dùng nút **×1000 / ÷1000** để chỉnh.
   - Số liệu nhập tay **không bao giờ trộn với số DEMO**: khi chưa có BCTC thật từ nguồn tự động, chỉ các năm bạn nhập được dùng để phân tích.
   - **BCTC ảnh/PDF**: AI trích xuất số liệu (cần API key).
   - **Ảnh biểu đồ nến**: AI đọc xu hướng, mô hình giá/nến, hỗ trợ/kháng cự, đề xuất điểm mua/cắt lỗ và **đối chiếu với tín hiệu định lượng** cùng mã/giai đoạn.
3. **DEMO**: dữ liệu mô phỏng, luôn gắn nhãn vàng "DEMO" để bạn không nhầm với dữ liệu thật.

> Các API dữ liệu kể trên là API công khai không chính thức của các công ty, có thể thay đổi bất kỳ lúc nào; khi đó cơ chế dự phòng sẽ chuyển nguồn và bạn có thể nhập tay.

## 5. Điểm tổng hợp & chiến lược tự động

**Điểm tổng hợp** = 35% kỹ thuật + 30% chất lượng cơ bản + 20% định giá + 15% rủi ro, điều chỉnh theo trạng thái thị trường chung.
≥ 72: MUA · ≥ 60: TÍCH LŨY · ≥ 45: NẮM GIỮ · ≥ 35: GIẢM TỶ TRỌNG · < 35: BÁN/TRÁNH.

**Auto-Trader** (`backend/app/trading/engine.py`):
- Tỷ trọng cổ phiếu mục tiêu theo market-timing VN-Index.
- Mua mã có điểm ≥ ngưỡng và xu hướng kỹ thuật xác nhận; **mua thăm dò 50%**, gia tăng khi lãi ≥ 3%.
- Khối lượng theo rủi ro: lỗ tối đa 1,5% vốn/lệnh, tỷ trọng ≤ 20%/mã, ≤ 8 mã.
- Bán khi: chạm cắt lỗ (2×ATR, tối đa 7%), trailing stop 10%, gãy xu hướng, điểm suy giảm, thị trường phân phối.
- Kill-switch: ngưng mua mới khi tài khoản sụt ≥ 15%.
- Không đặt lệnh trên giá DEMO; ngân sách giải ngân dùng chung cho mua mới, mua gia tăng và các đề xuất MUA đang chờ duyệt.

**Lệnh trên tài khoản giấy** mô phỏng lệnh LO: giá đặt là giá giới hạn, lệnh luôn khớp tại giá thị trường hiện tại (mua chỉ khớp khi giá đặt ≥ giá thị trường, bán khi ≤). Khi **duyệt đề xuất**: MUA chấp nhận giá cao hơn giá đề xuất tối đa 2% (không vượt trần); BÁN có giá (VD: AI đề xuất chốt lời) không khớp nếu thị trường thấp hơn giá đề xuất quá 2%; lệnh thoát vị thế của Auto-Trader (cắt lỗ, trailing stop) là lệnh thị trường. Mỗi đề xuất chỉ được duyệt một lần.
- Chạy tự động mỗi ngày làm việc lúc 14:15 (đổi được) nếu chế độ khác "Tắt".

**Backtest** dùng cùng bộ quy tắc trên dữ liệu lịch sử. Lưu ý: điểm cơ bản dùng số liệu hiện tại (không point-in-time) nên kết quả có thể lạc quan hơn thực tế.

## 6. Giao dịch tiền thật

Mặc định **tắt**. Ứng dụng có sẵn khung `LiveBrokerAdapter` (`backend/app/trading/broker.py`). Để kết nối công ty chứng khoán (ví dụ SSI FastConnect Trading, DNSE…), bạn cần đăng ký API với công ty chứng khoán, cài đặt các phương thức `account()` / `place_order()` theo tài liệu của họ, rồi đặt `ALLOW_LIVE_TRADING=true`. Khuyến nghị chạy chế độ **Đề xuất** + tài khoản giấy ít nhất vài tháng trước khi dùng tiền thật.

## 7. Kiến trúc

```
backend/app/
  data/        providers.py (6 nguồn giá + dự phòng), fundamentals.py (BCTC + nhập tay), excel_import.py, universe.py
  analysis/    indicators.py, technical.py, fundamental.py (MM, DuPont, F-Score), valuation.py, risk.py,
               market_timing.py, quant.py (Mundlak), scoring.py
  finance/     calculators.py (toán tài chính, trái phiếu, NPV/IRR, WACC, thuê mua), planner.py (tài chính cá nhân)
  portfolio/   optimizer.py (Markowitz)
  trading/     vn_rules.py, broker.py (tài khoản giấy), engine.py (Auto-Trader), backtest.py
  agent/       llm.py, agent.py (vòng lặp tool-use), tools.py, vision.py (ảnh biểu đồ, BCTC), knowledge.py
  main.py      FastAPI + lịch chạy Auto-Trader + phục vụ giao diện
frontend/src/  React + TypeScript + Vite, biểu đồ TradingView Lightweight Charts & Recharts, PWA
```

## 8. Kiểm thử

```bash
cd backend && ../.venv/bin/python -m pytest -q
```

75 bài kiểm thử, trong đó các công thức được đối chiếu trực tiếp với **ví dụ trong giáo trình** (VD: lũy kế 15% / bình quân 4,7%; IRR 4,17%; sinh lời kỳ vọng 18,22%; YTM 8,04%; TP chuyển đổi tỷ lệ 25; NPV +137,2 tỷ; WACC 11,56%; trần/sàn VNM 61.200/53.200; tách lệnh 1.530 = 1.500 + 30), cùng bộ đọc Excel, luật T+2/lô chẵn, Auto-Trader, backtest, tối ưu danh mục, vòng lặp AI Agent (giả lập) và các kiểm thử hồi quy cho lỗi đã sửa (`tests/test_review_fixes.py`).

---

Biểu đồ giá sử dụng [TradingView Lightweight Charts™](https://www.tradingview.com/lightweight-charts/) (Apache 2.0).
