"""Tạo file Excel BCTC giả lập định dạng Vietstock/CafeF để kiểm thử bộ đọc Excel."""
from io import BytesIO

from openpyxl import Workbook


def vietstock_like() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "CDKT_KQKD"
    ws.append(["CÔNG TY CỔ PHẦN FPT"])
    ws.append(["Đơn vị: Triệu đồng"])
    ws.append([])
    ws.append(["Chỉ tiêu", "Năm 2022", "Năm 2023", "Năm 2024"])
    rows = [
        ("A. TÀI SẢN NGẮN HẠN", 30_000_000, 34_000_000, 40_000_000),
        ("I. Tiền và các khoản tương đương tiền", 7_000_000, 8_000_000, 9_000_000),
        ("IV. Hàng tồn kho", 2_000_000, 2_200_000, 2_500_000),
        ("V. Tài sản ngắn hạn khác", 500_000, 600_000, 700_000),
        ("TỔNG CỘNG TÀI SẢN", 52_000_000, 60_000_000, 70_000_000),
        ("C. NỢ PHẢI TRẢ", 26_000_000, 29_000_000, 33_000_000),
        ("I. Nợ ngắn hạn", 22_000_000, 25_000_000, 28_000_000),
        ("10. Vay và nợ thuê tài chính ngắn hạn", 10_000_000, 11_000_000, 12_000_000),
        ("8. Vay và nợ thuê tài chính dài hạn", 1_000_000, 1_500_000, 2_000_000),
        ("D. VỐN CHỦ SỞ HỮU", 26_000_000, 31_000_000, 37_000_000),
        ("1. Vốn góp của chủ sở hữu", 10_970_000, 12_700_000, 14_700_000),
        ("11. Lợi nhuận sau thuế chưa phân phối", 8_000_000, 9_500_000, 11_000_000),
        ("1. Doanh thu bán hàng và cung cấp dịch vụ", 44_100_000, 52_700_000, 62_900_000),
        ("3. Doanh thu thuần về bán hàng và cung cấp dịch vụ", 44_000_000, 52_600_000, 62_800_000),
        ("5. Lợi nhuận gộp về bán hàng và cung cấp dịch vụ", 17_000_000, 20_000_000, 24_000_000),
        ("Trong đó: Chi phí lãi vay", 400_000, 500_000, 550_000),
        ("15. Tổng lợi nhuận kế toán trước thuế", 7_600_000, 9_200_000, 11_000_000),
        ("18. Lợi nhuận sau thuế thu nhập doanh nghiệp", 6_500_000, 7_800_000, 9_400_000),
        ("Lợi nhuận sau thuế của cổ đông của Công ty mẹ", 5_300_000, 6_500_000, 7_800_000),
        ("Lưu chuyển tiền thuần từ hoạt động kinh doanh", 6_000_000, 8_000_000, 9_500_000),
        ("1. Tiền chi để mua sắm, xây dựng TSCĐ và các tài sản dài hạn khác", -3_000_000, -3_500_000, -4_000_000),
    ]
    for r in rows:
        ws.append(list(r))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
