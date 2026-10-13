# AutoTrading VN — Phân tích cổ phiếu, giao dịch tự động & AI Agent quản trị tài sản

Ứng dụng **Web + App (cài được trên điện thoại)** cho nhà đầu tư chứng khoán Việt Nam, chạy trên máy tính Windows của bạn và mở được trên điện thoại:

- **Phân tích cổ phiếu toàn diện** cho **mọi mã niêm yết** HOSE/HNX/UPCoM: kỹ thuật, cơ bản/kế toán, định giá, rủi ro → điểm tổng hợp 0–100 và khuyến nghị.
- **Dữ liệu thật tự động**: giá từ KB Securities → Vietcap → VNDirect → CafeF (và SSI FastConnect / DNSE OpenAPI nếu bạn có khóa API), BCTC từ KBS → Vietcap. Khi không nguồn nào truy cập được, bạn **tải file lên** (Excel/CSV giá, Excel/ảnh/PDF BCTC, ảnh biểu đồ).
- **Giao dịch có kỷ luật** trên tài khoản giấy (mô phỏng sát luật VN): đặt lệnh nhanh, Auto-Trader (cắt lỗ, trailing stop, tỷ trọng theo thị trường, kill-switch), backtest.
- **AI Agent quản trị tài sản & tài chính** (Claude): trò chuyện tiếng Việt, gọi các mô hình phân tích, đọc ảnh biểu đồ và ảnh/PDF BCTC, lập kế hoạch tài chính cá nhân, tạo đề xuất lệnh để bạn duyệt.
- **Tài khoản & đăng nhập**: mỗi người một tài khoản, dữ liệu (danh mục, lệnh, hội thoại AI…) tách riêng hoàn toàn.

> ⚠️ **Lưu ý quan trọng**: Không phần mềm nào đảm bảo lợi nhuận. Ứng dụng giúp bạn ra quyết định có kỷ luật và quản trị rủi ro tốt hơn; mọi khuyến nghị chỉ mang tính tham khảo. Ứng dụng chỉ giao dịch trên **tài khoản giấy (mô phỏng)**. AutoTrading VN là công cụ độc lập, không liên kết với bất kỳ ngân hàng hay công ty chứng khoán nào.

---

## Bắt đầu nhanh trên Windows (không cần biết lập trình)

1. Trên GitHub bấm **Code → Download ZIP**, rồi **chuột phải file ZIP → Extract All** (giải nén *toàn bộ*).
2. Mở thư mục vừa giải nén, **bấm đúp `run.bat`**.
   - Máy chưa có Python 3.10+ → cửa sổ sẽ hỏi cài tự động bằng *winget* (bấm **Y**); hoặc tự cài từ python.org và **tick "Add python.exe to PATH"**.
   - Lần đầu tải thư viện mất 2–5 phút (cần Internet). Không cần Node.js — giao diện đã được build sẵn.
   - Có thể chọn tạo **lối tắt trên Desktop** để lần sau mở nhanh.
3. Trình duyệt tự mở **http://127.0.0.1:8000** → **tạo tài khoản quản trị** (chỉ làm được trên chính máy tính đang chạy ứng dụng).
4. **Giữ cửa sổ đen mở** trong khi dùng; đóng cửa sổ là tắt ứng dụng. Dữ liệu lưu ở `backend/data/` — khi cập nhật phiên bản mới, giữ lại thư mục này (và file `.env`).

macOS / Linux: `./run.sh`.

## 1. Tài khoản, đăng nhập & mở trên điện thoại

- **Tài khoản đầu tiên** là quản trị viên. Vào **Cài đặt & tài khoản → Quản lý người dùng** để tạo tài khoản cho người khác, khóa/mở khóa, đặt lại mật khẩu, hoặc bật cho phép **tự đăng ký**.
- Mỗi tài khoản có tài khoản giấy, lịch sử lệnh, cấu hình Auto-Trader, đề xuất lệnh, hội thoại AI và ảnh biểu đồ **riêng**. Dữ liệu thị trường và BCTC dùng chung.
- Mật khẩu ≥ 8 ký tự gồm chữ và số, lưu dạng băm PBKDF2; sai quá 8 lần trong 15 phút sẽ bị tạm chặn. Có thể "ghi nhớ đăng nhập 30 ngày" và xem/đăng xuất từng thiết bị.
- **Quên mật khẩu** (hoặc chạy bằng Docker/máy chủ): dùng công cụ dòng lệnh trong thư mục ứng dụng:

  ```bat
  .venv\Scripts\python.exe manage.py list-users
  .venv\Scripts\python.exe manage.py reset-password <tên-đăng-nhập>
  .venv\Scripts\python.exe manage.py create-admin
  ```

**Mở trên điện thoại** — trang **Cài đặt & tài khoản → Mở trên điện thoại** (quét mã QR):

| Cách | Khi nào | Cách bật |
|---|---|---|
| **Qua Internet (4G, ở bất cứ đâu)** | Dùng ngoài nhà | Quản trị viên bấm **Bật** ngay trên máy tính: ứng dụng tải công cụ đường hầm chính thức của Cloudflare (~30 MB) và tạo địa chỉ `https://….trycloudflare.com` (đổi mỗi lần mở lại). Máy tính phải đang bật và chạy ứng dụng. |
| **Cùng mạng Wi-Fi** | Ở nhà, nhanh nhất | Sửa `.env`: `HOST=0.0.0.0`, chạy lại `run.bat`, cho phép Windows Firewall ở "Private network". Mở địa chỉ `http://192.168.x.x:8000` hiển thị trong trang. |

Trên điện thoại: Chrome **⋮ → Thêm vào màn hình chính**, Safari **Chia sẻ → Thêm vào MH chính** để dùng như một ứng dụng. Mọi cách truy cập từ xa đều **bắt buộc đăng nhập**.

## 2. Kiến thức nền tảng được tích hợp

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

## 3. Tính năng chính

| Trang | Nội dung |
|---|---|
| **Tổng quan** | Lời chào, **thẻ tổng tài sản** (ẩn/hiện số dư), tiện ích nhanh, dải chỉ số VN-Index/VN30/HNX/UPCoM, VN-Index + đường xu hướng, trạng thái thị trường chung, cổ phiếu nổi bật, đề xuất lệnh chờ duyệt, phân bổ tài sản |
| **Đặt lệnh nhanh** | Nút giữa thanh điều hướng điện thoại (hoặc trên thanh bên): nhập mã → giá trần/sàn/tham chiếu, bước giá, khối lượng mua tối đa, số CP bán được (T+2), phí/thuế — kiểm tra trước khi gửi |
| **Phân tích cổ phiếu** | Biểu đồ nến (MA20/50/200, Bollinger, khối lượng, RSI, MACD) theo **khoảng thời gian tùy chọn**; 15+ tín hiệu kỹ thuật, mô hình nến, hỗ trợ/kháng cự; chỉ tiêu tài chính theo năm, MM, DuPont, Piotroski F-Score; 7 mô hình định giá; 12 chỉ số rủi ro; kế hoạch giao dịch & đặt lệnh |
| **Bộ lọc & xếp hạng** | Chấm điểm 44 mã thanh khoản cao (danh mục theo dõi mặc định), lọc theo ngành/điểm/khuyến nghị, sắp xếp mọi cột |
| **Danh mục & tối ưu** | Tài khoản giấy, vị thế (khả dụng T+2), lịch sử lệnh, tối ưu Markowitz (max Sharpe / min rủi ro, giới hạn tỷ trọng) cho bất kỳ mã nào bạn chọn, đường biên hiệu quả |
| **Giao dịch tự động** | Tắt / Đề xuất / Tự động trên tài khoản giấy; tham số rủi ro; chạy theo lịch hằng ngày; backtest so với VN-Index |
| **AI Agent** | Chat tiếng Việt, 13 công cụ phân tích, đính kèm ảnh/PDF, duyệt đề xuất lệnh ngay trong khung chat |
| **Tài chính cá nhân** | Ngân sách 50/30/20, quỹ dự phòng, thứ tự trả nợ, phân bổ tài sản theo khẩu vị rủi ro & tuổi, mục tiêu, dự phóng; trắc nghiệm khẩu vị rủi ro; 13 máy tính tài chính |
| **Dữ liệu & nhập liệu** | Kiểm tra kết nối từng nguồn tự động; tải lịch sử giá CSV/Excel; **nhập BCTC bằng Excel** (file mẫu hoặc file xuất từ Vietstock/CafeF/FiinPro…), ảnh/PDF (AI đọc), sửa trực tiếp; **phân tích ảnh chụp biểu đồ nến** và đối chiếu với mô hình định lượng |
| **Cài đặt & tài khoản** | Hồ sơ, đổi mật khẩu, thiết bị đang đăng nhập, **giao diện sáng / tối chuyên nghiệp, chế độ chữ lớn**, quản lý người dùng, mở trên điện thoại |

Giao diện theo phong cách ngân hàng số: nền sáng, xanh ngọc, số liệu thẳng cột; màu giá theo chuẩn bảng giá VN (tăng xanh, giảm đỏ, tham chiếu vàng, trần tím, sàn xanh lơ); tìm mã nhanh `Ctrl+K`; font chữ nhúng sẵn nên vẫn hiển thị đẹp khi không có Internet.

## 4. Cấu hình `.env`

File `.env` được tạo tự động ở lần chạy đầu (mẫu: `.env.example`). Sửa bằng Notepad rồi chạy lại `run.bat`.

| Biến | Ý nghĩa |
|---|---|
| `ANTHROPIC_API_KEY` | Khóa Claude API (console.anthropic.com). Không có khóa → AI Agent chạy **chế độ cơ bản** (vẫn phân tích bằng mô hình của hệ thống, nhưng không trò chuyện tự nhiên/đọc ảnh). |
| `AGENT_MODEL` / `AGENT_EFFORT` | Model Claude dùng cho AI Agent và mức suy luận (`low`…`max`). |
| `DATA_MODE` | `auto` (mặc định: dữ liệu thật; nếu mọi nguồn giá đều lỗi thì tạm dùng DEMO có gắn nhãn và **không cho đặt lệnh**) · `live` (chỉ dữ liệu thật) · `demo` (chỉ mô phỏng, để học/thử). |
| `SSI_API_KEY` / `SSI_API_SECRET` | (Tùy chọn) Khóa SSI FastConnect Data — nguồn chính thức, ưu tiên cao nhất. |
| `DNSE_API_KEY` / `DNSE_API_SECRET` | (Tùy chọn) Khóa DNSE OpenAPI. |
| `HOST` / `PORT` | `127.0.0.1` = chỉ máy này (mặc định); `0.0.0.0` = cho điện thoại cùng Wi-Fi. Cổng bận thì ứng dụng tự chọn cổng khác. |
| `PAPER_INITIAL_CASH` | Vốn tài khoản giấy của mỗi tài khoản mới (mặc định 500 triệu). |
| `ALLOW_LIVE_TRADING` | Mặc định `false`. Xem mục 7. |

Chạy cho nhà phát triển:

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
.venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8000   # API docs: http://localhost:8000/docs (cần đăng nhập)
cd frontend && npm ci && npm run dev                                    # giao diện dev: http://localhost:5173
cd frontend && npm run build                                            # build lại frontend/dist rồi commit (CI kiểm tra)
```

Docker: `docker build -t autotrading . && docker run -d -p 8000:8000 -v autotrading-data:/app/backend/data --env-file .env --name autotrading autotrading`,
rồi tạo quản trị viên: `docker exec -it autotrading python manage.py create-admin`.

## 5. Dữ liệu: tự động trước, thủ công khi cần

Thứ tự ưu tiên: **dữ liệu bạn nhập → nguồn tự động → DEMO (chỉ giá, luôn gắn nhãn)**.

1. **Danh sách mã**: toàn bộ mã niêm yết HOSE/HNX/UPCoM kèm sàn và ngành ICB, tải từ KBS (dự phòng Vietcap), làm mới mỗi 24 giờ; mất mạng thì dùng bản tải gần nhất.
2. **Giá** (`backend/app/data/providers.py`): SSI FastConnect → DNSE (chỉ khi có khóa) → **KB Securities → Vietcap → VNDirect → CafeF** (CafeF dùng giá điều chỉnh). Ngày giao dịch tính theo giờ Việt Nam. Nguồn lỗi/chặn được tạm bỏ qua 1–5 phút để ứng dụng không bị chậm. Trang **Dữ liệu & nhập liệu → Nguồn tự động → Kiểm tra kết nối** lấy giá FPT từ mọi nguồn và so lệch giữa các nguồn.
3. **BCTC theo năm**: KBS → Vietcap. Không lấy được thì **để trống** (phần cơ bản/định giá báo "chưa có dữ liệu") — **không bao giờ dùng số liệu bịa**.
4. **Khi tất cả nguồn đều lỗi**, giao diện cảnh báo và hướng dẫn nhập tay ở trang **Dữ liệu & nhập liệu**:
   - **Giá**: CSV/Excel từ investing.com (tiếng Anh/Việt), CafeF (có giá điều chỉnh), Amibroker `<Ticker>,<DTYYYYMMDD>,<Open>,…` hoặc bảng *Ngày, Mở cửa, Cao nhất, Thấp nhất, Đóng cửa, Khối lượng*; tự nhận diện ngày/tháng, `1.234,5` hay `1,234.5`, khối lượng `1,2M`, giá nghìn đồng.
   - **BCTC Excel**: tải **file mẫu** (điền sẵn số liệu thật đã có; các ô hệ thống chỉ ước tính được để trống) hoặc dùng file xuất "chỉ tiêu × năm" từ Vietstock/CafeF/FiinPro… Bộ đọc tự nhận diện chỉ tiêu tiếng Việt/Anh (cả mẫu ngân hàng), cột năm (bỏ qua cột quý/6 tháng/dự phóng), đơn vị (đồng/nghìn/triệu/tỷ), ưu tiên *LNST cổ đông công ty mẹ*, cộng vay ngắn + dài hạn. Bạn **xem lại & sửa** trước khi lưu; nút **×1000 / ÷1000** để chỉnh đơn vị.
   - **BCTC ảnh/PDF**: AI trích xuất số liệu (cần API key).
   - **Ảnh biểu đồ nến**: AI đọc xu hướng, mô hình giá/nến, hỗ trợ/kháng cự, đề xuất điểm mua/cắt lỗ và **đối chiếu với tín hiệu định lượng** cùng mã/giai đoạn.

> Các nguồn KBS/Vietcap/VNDirect/CafeF là API công khai không chính thức, có thể thay đổi bất kỳ lúc nào; khi đó cơ chế dự phòng sẽ chuyển nguồn và bạn có thể nhập tay hoặc đăng ký nguồn chính thức (SSI/DNSE). Hãy chạy **Kiểm tra kết nối** sau khi cài đặt để biết nguồn nào đang hoạt động trên mạng của bạn.

## 6. Điểm tổng hợp & chiến lược tự động

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
- Chế độ: **Tắt** (mặc định cho mọi tài khoản mới) · **Đề xuất** (bạn duyệt từng lệnh) · **Tự động trên tài khoản giấy**. Khi bật, chạy mỗi ngày làm việc lúc 14:15 (đổi được), riêng cho từng tài khoản.

**Backtest** dùng cùng bộ quy tắc trên dữ liệu lịch sử. Lưu ý: điểm cơ bản dùng số liệu hiện tại (không point-in-time) nên kết quả có thể lạc quan hơn thực tế.

## 7. Giao dịch tiền thật

Mặc định **tắt**. Ứng dụng có sẵn khung `LiveBrokerAdapter` (`backend/app/trading/broker.py`). Để kết nối công ty chứng khoán (ví dụ SSI FastConnect Trading, DNSE…), bạn cần đăng ký API với công ty chứng khoán, cài đặt các phương thức `account()` / `place_order()` theo tài liệu của họ, rồi đặt `ALLOW_LIVE_TRADING=true`. Khuyến nghị chạy chế độ **Đề xuất** + tài khoản giấy ít nhất vài tháng trước khi dùng tiền thật.

## 8. Kiến trúc

```
backend/app/
  auth.py, context.py  tài khoản, phiên đăng nhập (cookie HttpOnly), ngữ cảnh người dùng cho từng yêu cầu
  data/        http.py (ngắt mạch theo máy chủ), providers.py (nguồn giá + dự phòng), listing.py (toàn bộ mã niêm yết),
               fundamentals.py (BCTC KBS/Vietcap + nhập tay), excel_import.py, universe.py
  analysis/    indicators.py, technical.py, fundamental.py (MM, DuPont, F-Score), valuation.py, risk.py,
               market_timing.py, quant.py (Mundlak), scoring.py
  finance/     calculators.py (toán tài chính, trái phiếu, NPV/IRR, WACC, thuê mua), planner.py (tài chính cá nhân)
  portfolio/   optimizer.py (Markowitz)
  trading/     vn_rules.py, broker.py (tài khoản giấy theo người dùng), engine.py (Auto-Trader), backtest.py
  agent/       llm.py, agent.py (vòng lặp tool-use), tools.py, vision.py (ảnh biểu đồ, BCTC), knowledge.py
  remote.py    mở truy cập từ điện thoại (Wi-Fi / đường hầm Cloudflare)
  main.py      FastAPI + kiểm soát đăng nhập + lịch chạy Auto-Trader + phục vụ giao diện
frontend/src/  React + TypeScript + Vite, biểu đồ TradingView Lightweight Charts & Recharts, PWA
run.bat / run.sh / launcher.py   khởi động một chạm (Windows / macOS / Linux)
manage.py                        quản lý tài khoản bằng dòng lệnh
```

## 9. Kiểm thử

```bash
cd backend && ../.venv/bin/python -m pytest -q
```

110 bài kiểm thử, trong đó các công thức được đối chiếu trực tiếp với **ví dụ trong giáo trình** (VD: lũy kế 15% / bình quân 4,7%; IRR 4,17%; sinh lời kỳ vọng 18,22%; YTM 8,04%; TP chuyển đổi tỷ lệ 25; NPV +137,2 tỷ; WACC 11,56%; trần/sàn VNM 61.200/53.200; tách lệnh 1.530 = 1.500 + 30), cùng tài khoản & tách dữ liệu giữa người dùng, chống đoán mật khẩu, bộ đọc dữ liệu từng nguồn (giả lập phản hồi API), bộ đọc Excel/CSV, luật T+2/lô chẵn, Auto-Trader, backtest, tối ưu danh mục, vòng lặp AI Agent và các kiểm thử hồi quy. GitHub Actions chạy kiểm thử, build giao diện và **khởi động thử `run.bat` trên Windows** ở mỗi lần đẩy mã.

---

Biểu đồ giá sử dụng [TradingView Lightweight Charts™](https://www.tradingview.com/lightweight-charts/) (Apache 2.0). Font Be Vietnam Pro và Inter (SIL Open Font License).
