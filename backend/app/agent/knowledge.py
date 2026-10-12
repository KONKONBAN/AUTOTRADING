"""Cơ sở kiến thức nền tảng (tóm lược từ tài liệu trong Google Drive của người dùng).

Nguồn: PTVĐTCK (Phân tích & đầu tư chứng khoán) bài 0, chương 1-3; FQA (Phân tích định lượng tài chính)
session 1-2 & bài mẫu đòn bẩy ngành BĐS; Analysis of ROE, ROA for an industry; Market-Timing VN-Index;
CFA - Định giá dự án qua DCF & WACC; Toán tài chính (lãi đơn, lãi kép, chiết khấu thương phiếu, tài khoản
vãng lai, chuỗi tiền tệ, vay vốn); Kế toán tài chính 2 (HĐKD & KQKD, HĐ tài chính & phân phối LN,
HĐ đầu tư, hệ thống BCTC; Thông tư 99/2025); TCDN chương 9 (thuê mua tài sản); sách Corporate Finance
(Berk-DeMarzo, Ross-Westerfield-Jordan, Pike-Neale, Tse), Financial Modeling (Benninga),
Stock Markets & Corporate Finance (Dempsey), International Finance (Pilbeam).
"""

TOPICS: dict[str, str] = {
    "quy_trinh_dau_tu": """QUY TRÌNH ĐẦU TƯ CỔ PHIẾU (PTVĐTCK 2.1) - áp dụng cho mọi phương pháp (tăng trưởng, giá trị, kỹ thuật):
1) Lựa chọn cổ phiếu theo tiêu chí đưa vào danh sách theo dõi (không chọn theo tin đồn/bạn bè).
   - NĐT tăng trưởng: tăng trưởng quý gần nhất, động lực tăng trưởng tương lai.
   - NĐT giá trị: giá trị tài sản, định giá thấp hơn giá trị nội tại.
   - NĐT kỹ thuật: xu hướng và mô hình giá hiện tại.
2) Chọn thời điểm mua: mua cổ phiếu có xu hướng tăng giá.
3) Chọn thời điểm bán: khi thị trường chung phân phối, xu hướng cổ phiếu bị bẻ gãy, tìm được cổ phiếu tốt hơn, hoặc cắt lỗ.
4) Quản lý rủi ro: mức cắt lỗ cho mỗi vị thế; mức thiệt hại tối đa của toàn bộ vốn; không dồn toàn bộ vốn vào 1 mã;
   mua nhiều lần để phân tán rủi ro; dùng margin ở mức phù hợp và chỉ khi thị trường uptrend.
Khuyến nghị (bài 0): Đừng bao giờ đặt trứng vào một giỏ - Đừng để tiền rơi - Hãy quản lý vốn thật tốt.""",

    "sinh_loi_rui_ro": """MỨC SINH LỜI & RỦI RO (PTVĐTCK chương 2)
- Tổng mức lời = Cổ tức + Lãi (lỗ) vốn. r = (P1 − P0 + D1)/P0 = tỷ lệ cổ tức (D1/P0) + tỷ suất lãi vốn ((P1−P0)/P0).
  VD: mua 1.000 CP giá 95.000, cổ tức 15.000/CP, bán 120.000 → lời 40 triệu, thu về 135 triệu.
- Lũy kế t năm: R(t) = (1+R1)(1+R2)...(1+Rt) − 1; bình quân hình học = (1+R(t))^(1/t) − 1.
  VD 11%, −5%, 9% → lũy kế ≈ 15%, bình quân hình học ≈ 4,7%/năm; bình quân số học = 5%/năm.
- IRR: lãi suất làm tổng chi đầu tư = PV thu nhập tương lai. VD dòng tiền [−1; −0,1; −0,5; 0,8; 1,0] tỷ → IRR ≈ 4,17%.
- Sinh lời kỳ vọng theo kịch bản: k = Σ ki·Pi; phương sai σ² = Σ (ki − k)²·Pi; LN thực tế ≈ k ± σ.
  VD giá mua 28.000: phát đạt 30% (40.000; cổ tức 6.000), bình thường 40% (32.000; 3.500), khó khăn 30% (15.000; 2.000) → k = 18,22%.
- Rủi ro hệ thống (không đa dạng hóa được): rủi ro thị trường, lãi suất (quan hệ gián tiếp với giá CP, ngược chiều trực tiếp với giá TP),
  sức mua (lạm phát, tỷ giá). Rủi ro phi hệ thống (kiểm soát được bằng đa dạng hóa): rủi ro kinh doanh (bên trong/bên ngoài),
  rủi ro tài chính (cấu trúc vốn; DN không vay nợ thì không có rủi ro tài chính).
- Beta, CAPM: E(R) = rf + β(Rm − rf); Sharpe = (R − rf)/σ; Max drawdown; VaR.""",

    "trai_phieu": """PHÂN TÍCH & ĐỊNH GIÁ TRÁI PHIẾU (PTVĐTCK chương 3)
- Lợi tức: lãi coupon C = i%·F, chênh lệch giá, lãi của lãi (tái đầu tư).
- Rủi ro: lãi suất (giá TP ngược chiều lãi suất), tái đầu tư (triệt tiêu một phần với rủi ro lãi suất), thanh toán/tín dụng
  (TPCP không có), lạm phát, tỷ giá, thanh khoản.
- Giá TP thường: P = C·[1 − (1+r)^−n]/r + F/(1+r)^n; trả 6 tháng: C/2, r/2, 2n. Zero-coupon: P = F/(1+r)^n. Vĩnh cửu: P = C/r.
- r = coupon → giá = mệnh giá; r > coupon → giá < mệnh giá; gần đáo hạn giá tiến về mệnh giá.
- Lợi suất hiện hành CY = C/P (VD coupon 10%, giá 1.035.000 → 9,67%). YTM: lãi suất làm PV dòng tiền = giá (VD còn 2 năm → 8,04%).
- TP chuyển đổi: tỷ lệ = mệnh giá/giá chuyển đổi (1.000.000/40.000 = 25); giá trị chuyển đổi = 25 × 50.000 = 1.250.000 → nên chuyển đổi.""",

    "thi_truong_vn": """QUY ĐỊNH GIAO DỊCH TTCK VIỆT NAM (PTVĐTCK chương 1)
- Hàng hóa: cổ phiếu (chứng khoán vốn), trái phiếu (chứng khoán nợ), chứng chỉ quỹ, chứng khoán phái sinh.
- Quy trình: mở TK & nộp tiền → đặt/sửa/hủy lệnh → CTCK nhập lệnh lên SGDCK → SGDCK báo kết quả → báo TTLK.
- Biên độ: HOSE ±7%, HNX ±10%, UPCoM ±15% quanh giá tham chiếu (giá đóng cửa phiên trước). Màu: tím = trần, xanh lam = sàn,
  xanh lá = tăng, đỏ = giảm, vàng = tham chiếu.
- Bước giá HOSE: < 10.000đ: 10đ; 10.000–49.950đ: 50đ; ≥ 50.000đ: 100đ. Lô chẵn 100 CP (VD bán 1.530 CP phải tách 1.500 + 30 lô lẻ).
- Thanh toán: CP mua về sau T+2 (khoảng trưa/chiều ngày T+2) mới bán được; tiền bán có thể ứng trước (phí = số tiền × lãi suất/365 × số ngày).
- Phí giao dịch 0,15%–0,3% giá trị (mua và bán); bán chịu thêm thuế TNCN 0,1%.
- Lệnh: LO (giới hạn), ATO/ATC (khớp định kỳ mở/đóng cửa), MP/MTL/MOK/MAK (lệnh thị trường), giao dịch thỏa thuận.
  Khớp lệnh định kỳ: một mức giá duy nhất tối đa khối lượng; khớp liên tục: khớp ngay khi giá mua = giá bán.""",

    "bao_cao_tai_chinh": """BÁO CÁO TÀI CHÍNH & KẾ TOÁN (FQA session 2; KTTC2; Thông tư 99/2025/TT-BTC, TT200, VAS 01, VAS 21)
- 3 hoạt động tài chính nền tảng: Đầu tư & tài trợ (tạo tài sản/huy động vốn) → Kinh doanh & hiệu quả (tạo lợi nhuận, dòng tiền)
  → Định giá & quản trị rủi ro.
- Bảng cân đối kế toán (Báo cáo tình hình tài chính): Tài sản (A) = Nợ phải trả (D) + Vốn chủ sở hữu (E). TS ngắn hạn (mã 100),
  dài hạn (200); Nợ phải trả (300: ngắn hạn 310, dài hạn 330); VCSH (400).
- Báo cáo KQKD: NI = Doanh thu − Giá vốn − Chi phí hoạt động − Lãi vay − Thuế.
  Doanh thu ghi nhận khi chuyển giao rủi ro/lợi ích; giảm trừ doanh thu (chiết khấu thương mại, giảm giá, hàng bán bị trả lại).
- Báo cáo lưu chuyển tiền tệ: dòng tiền thuần = tiền vào − tiền ra; 3 hoạt động: kinh doanh, đầu tư, tài chính.
  Lợi nhuận tốt phải đi kèm dòng tiền HĐKD dương (OCF/NI ≥ 1).
- Phân phối lợi nhuận: trích quỹ (đầu tư phát triển, khen thưởng phúc lợi), chia cổ tức; thay đổi vốn góp CTCP (phát hành, cổ phiếu quỹ).
- Kế toán đầu tư tài chính: chứng khoán kinh doanh (mua để bán kiếm lời: CP, TP niêm yết, CCQ, chứng quyền...) ghi nhận theo giá gốc,
  lập dự phòng giảm giá; đầu tư nắm giữ đến ngày đáo hạn; đầu tư vào công ty con/liên doanh/liên kết.
- Bút toán kết chuyển cuối kỳ xác định kết quả kinh doanh (TK 911).""",

    "don_bay_mm": """ĐÒN BẨY & HIỆU QUẢ TÀI CHÍNH - MÔ HÌNH ROE–ROA (FQA, định lý Modigliani–Miller mở rộng)
- ROE = NI/E; ROA = NI/TA; LEV = D/E; Sd = Rd(1 − T) chi phí nợ sau thuế.
- MM mở rộng: ROE = (1 + LEV)·ROA − LEV·Sd → đòn bẩy chỉ khuếch đại ROE khi ROA (sinh lời hoạt động) > chi phí nợ sau thuế.
- Mô hình định lượng: ROE = a + b·ROA + u; b = hệ số khuếch đại đòn bẩy (lý thuyết b* = 1 + LEV), a = chi phí đòn bẩy.
  Bài mẫu ngành BĐS (AGG, BCM, CCL, CKG, CRE; 72 quan sát): ROE = 0,0204 + 2,2547·ROA (R² = 0,40) → b ≈ b* tạm tính 2,255.
  Phân nhóm: hiệu quả cao (ROA, ROE cao, đòn bẩy hợp lý - CKG, CRE), ổn định (BCM), rủi ro (AGG đòn bẩy 8,6×; CCL hiệu quả thấp).
- Nhà đầu tư không nên đánh giá ROE độc lập: phải xem đồng thời ROA, LEV, chi phí nợ và mức khuếch đại đòn bẩy.
- Dữ liệu chéo (nhiều DN, 1 thời điểm), chuỗi thời gian (1 DN, nhiều thời điểm), dữ liệu bảng (nhiều DN, nhiều thời điểm).
  bs = E(ROE)/E(ROA): trạng thái ổn định. Phân rã Mundlak: ROE_it = a' + bB·E(ROA_i) + bW·[ROA_it − E(ROA_i)];
  bB = quan hệ trạng thái (giữa các DN), bW = quan hệ động lực (trong 1 DN); b gộp = wB·bB + wW·bW (trọng số phương sai).
  VD ngành nhựa/xây dựng (ACC, ASG, AST, BMP, CCC): ROE = 0,063 + 0,843·E(ROA_i) + 1,305·[ROA_it − E(ROA_i)], R² = 0,93.
- DuPont: ROE = Biên LN ròng × Vòng quay tài sản × Hệ số nhân vốn chủ.""",

    "dinh_gia": """ĐỊNH GIÁ DOANH NGHIỆP & DỰ ÁN (CFA - DCF & WACC; Corporate Finance)
- DCF: Giá trị = Σ CF_t/(1 + r)^t; giá thị trường < DCF → định giá thấp (cơ hội); > DCF → định giá cao.
- FCFF chuẩn hóa từ NOPAT = EBIT × (1 − t) (+ khấu hao − capex − ΔVLĐ); chiết khấu bằng WACC. KHÔNG trừ lãi vay ở tử số
  (đã nằm trong WACC - lỗi "tính trùng chi phí").
- WACC = we·re + wd·rd(1 − t) + wp·rp; trọng số theo GIÁ TRỊ THỊ TRƯỜNG và cấu trúc vốn MỤC TIÊU (bẫy "giá trị sổ sách").
  VD: E 60% (re 15%), D 40% (rd 8%), thuế 20% → WACC = 9% + 2,56% = 11,56%.
- NPV > 0 chấp nhận; IRR > hurdle rate chấp nhận. Dự án loại trừ nhau → ưu tiên NPV (IRR giả định tái đầu tư ở IRR, có thể nhiều IRR).
  Dùng MIRR (tái đầu tư ở WACC). Bỏ qua chi phí chìm, chỉ tính dòng tiền tăng thêm, tính ngoại ứng (cannibalization).
  VD: đầu tư 1.000 tỷ, thu 300 tỷ/năm × 5 năm, WACC 10% → NPV = +137,2 tỷ.
- Chi phí vốn CSH: CAPM re = rf + β(Rm − rf). DDM Gordon: P0 = D1/(re − g). P/B hợp lý = (ROE − g)/(re − g).
  P/E hợp lý = payout × (1 + g)/(re − g). Tăng trưởng bền vững g = ROE × tỷ lệ giữ lại.""",

    "toan_tai_chinh": """TOÁN TÀI CHÍNH
- Lãi đơn: I = PV·i·n; FV = PV(1 + i·n). Lãi kép: FV = PV(1 + i)^n; lãi suất hiệu dụng = (1 + i/m)^m − 1.
  FQA: lãi suất thay đổi 6%, 7%, 8% → FV = 100 × 1,06 × 1,07 × 1,08 = 122,5.
- Chiết khấu thương phiếu: số tiền chiết khấu E = F·i·n/360; giá trị nhận được = F − E − hoa hồng.
- Tài khoản vãng lai: tính lãi theo số dư và số ngày (phương pháp rút số dư / tích số).
- Chuỗi tiền tệ (n kỳ, số tiền a, lãi i): FV = a[(1+i)^n − 1]/i; PV = a[1 − (1+i)^−n]/i; đầu kỳ × (1 + i);
  chuỗi biến đổi theo cấp số cộng/nhân.
- Vay vốn: trả góp đều a = PV·i/[1 − (1+i)^−n]; hoặc trả gốc đều, lãi tính trên dư nợ giảm dần.
- Thuê tài sản (TCDN ch.9): thuê hoạt động (full service) vs thuê tài chính (net service); quyết định thuê hay vay mua dựa trên
  NAL = PV chi phí mua − PV chi phí thuê sau thuế, chiết khấu bằng rd(1 − t). NAL > 0 → thuê.""",

    "market_timing": """MARKET-TIMING VN-INDEX
- Mô hình log-tuyến tính: lnP_t = a + b·t + u_t trên cửa sổ trượt; b = tốc độ tăng trưởng xu hướng, u = độ lệch khỏi xu hướng,
  d(b) và d(a) = thay đổi của xu hướng (tăng tốc/suy yếu).
- b > 0, d(b) > 0, giá trên MA50/MA200 → uptrend; b giảm, nhiều "ngày phân phối" (giảm > 0,2% với KL tăng) → phân phối, hạn chế mua.
- Sự kiện minh họa (bài 0): 03/04/2025 Mỹ áp thuế đối ứng 46% với VN → thị trường giảm sàn; 10/04/2025 hoãn thuế 90 ngày → hồi phục.
  Bài học: rủi ro hệ thống khó dự báo → luôn có kế hoạch quản trị rủi ro, không dùng đòn bẩy quá mức.""",

    "danh_muc": """XÂY DỰNG DANH MỤC TỐI ƯU (Module 4)
- E(Rp) = Σ wi·E(Ri); σp² = wᵀΣw. Đa dạng hóa giảm rủi ro phi hệ thống (hệ số tương quan < 1).
- Đường biên hiệu quả Markowitz; danh mục tối đa Sharpe; danh mục phương sai nhỏ nhất.
- Thực hành: 5-10 mã, nhiều ngành có tương quan thấp, mỗi mã ≤ 20-25%; tái cân bằng định kỳ; điều chỉnh tỷ trọng cổ phiếu
  theo trạng thái thị trường chung.""",

    "tai_chinh_ca_nhan": """QUẢN TRỊ TÀI CHÍNH CÁ NHÂN
- Ngân sách 50/30/20; tự động tiết kiệm khi nhận lương; quỹ dự phòng 3-6 tháng chi tiêu (tiết kiệm/CCQ thị trường tiền tệ).
- Trả nợ lãi cao trước (≥ 12%/năm) trước khi đầu tư rủi ro. Bảo hiểm sức khỏe/nhân thọ bảo vệ trước khi đầu tư.
- Phân bổ theo khẩu vị rủi ro (thận trọng / cân bằng / tăng trưởng) và tuổi (tỷ trọng CP ≈ 110 − tuổi).
- Mục tiêu tính bằng giá trị thời gian của tiền: số tiền cần gửi đều mỗi tháng = FV·i/[(1+i)^n − 1].
- Con số tự do tài chính (FIRE) ≈ 25 × chi tiêu năm (quy tắc rút 4%).""",
}


def search(query: str) -> str:
    """Tìm các chủ đề kiến thức liên quan (đơn giản theo từ khóa)."""
    q = query.lower()
    keys = {
        "quy_trinh_dau_tu": ["quy trình", "mua", "bán", "cắt lỗ", "chọn cổ phiếu", "margin"],
        "sinh_loi_rui_ro": ["sinh lời", "rủi ro", "lợi nhuận", "phương sai", "beta", "irr", "kỳ vọng", "capm"],
        "trai_phieu": ["trái phiếu", "coupon", "ytm", "lợi suất", "chuyển đổi"],
        "thi_truong_vn": ["t+", "biên độ", "trần", "sàn", "lô", "phí", "thuế", "lệnh", "ato", "atc"],
        "bao_cao_tai_chinh": ["báo cáo", "bctc", "kế toán", "cân đối", "lưu chuyển", "doanh thu", "thông tư"],
        "don_bay_mm": ["roe", "roa", "đòn bẩy", "modigliani", "mm", "mundlak", "dupont", "lev"],
        "dinh_gia": ["định giá", "dcf", "wacc", "npv", "giá trị nội tại", "p/e", "p/b", "cổ tức"],
        "toan_tai_chinh": ["lãi đơn", "lãi kép", "chuỗi tiền", "vay", "trả góp", "chiết khấu", "thuê"],
        "market_timing": ["vn-index", "vnindex", "thị trường chung", "xu hướng thị trường", "timing", "phân phối"],
        "danh_muc": ["danh mục", "markowitz", "đa dạng", "tỷ trọng", "phân bổ"],
        "tai_chinh_ca_nhan": ["cá nhân", "tiết kiệm", "ngân sách", "quỹ dự phòng", "nghỉ hưu", "mục tiêu"],
    }
    hits = [k for k, words in keys.items() if any(w in q for w in words)] or list(TOPICS)[:2]
    return "\n\n".join(TOPICS[k] for k in hits[:3])


def full_text() -> str:
    return "\n\n".join(TOPICS.values())
