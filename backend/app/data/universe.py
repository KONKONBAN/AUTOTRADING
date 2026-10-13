"""Danh sách cổ phiếu theo dõi (universe) - các mã thanh khoản cao trên HOSE/HNX."""

from __future__ import annotations

# ticker: (tên công ty, ngành, sàn, giá tham khảo dùng cho dữ liệu DEMO)
UNIVERSE: dict[str, tuple[str, str, str, float]] = {
    # Ngân hàng
    "VCB": ("Ngân hàng TMCP Ngoại thương Việt Nam", "Ngân hàng", "HOSE", 62_000),
    "BID": ("Ngân hàng TMCP Đầu tư và Phát triển VN", "Ngân hàng", "HOSE", 38_000),
    "CTG": ("Ngân hàng TMCP Công Thương VN", "Ngân hàng", "HOSE", 40_000),
    "TCB": ("Ngân hàng TMCP Kỹ Thương VN", "Ngân hàng", "HOSE", 34_000),
    "MBB": ("Ngân hàng TMCP Quân Đội", "Ngân hàng", "HOSE", 26_000),
    "ACB": ("Ngân hàng TMCP Á Châu", "Ngân hàng", "HOSE", 25_000),
    "VPB": ("Ngân hàng TMCP Việt Nam Thịnh Vượng", "Ngân hàng", "HOSE", 20_000),
    "HDB": ("Ngân hàng TMCP Phát triển TP.HCM", "Ngân hàng", "HOSE", 27_000),
    "STB": ("Ngân hàng TMCP Sài Gòn Thương Tín", "Ngân hàng", "HOSE", 44_000),
    "TPB": ("Ngân hàng TMCP Tiên Phong", "Ngân hàng", "HOSE", 16_000),
    "SHB": ("Ngân hàng TMCP Sài Gòn - Hà Nội", "Ngân hàng", "HOSE", 13_000),
    "VIB": ("Ngân hàng TMCP Quốc tế VN", "Ngân hàng", "HOSE", 19_000),
    # Bất động sản
    "VHM": ("CTCP Vinhomes", "Bất động sản", "HOSE", 80_000),
    "VIC": ("Tập đoàn Vingroup", "Bất động sản", "HOSE", 95_000),
    "VRE": ("CTCP Vincom Retail", "Bất động sản", "HOSE", 27_000),
    "KDH": ("CTCP Đầu tư Kinh doanh Nhà Khang Điền", "Bất động sản", "HOSE", 33_000),
    "NLG": ("CTCP Đầu tư Nam Long", "Bất động sản", "HOSE", 38_000),
    "BCM": ("Tổng Công ty Đầu tư và Phát triển Công nghiệp", "Bất động sản", "HOSE", 65_000),
    # Chứng khoán
    "SSI": ("CTCP Chứng khoán SSI", "Chứng khoán", "HOSE", 30_000),
    "VND": ("CTCP Chứng khoán VNDirect", "Chứng khoán", "HOSE", 16_000),
    "HCM": ("CTCP Chứng khoán TP.HCM", "Chứng khoán", "HOSE", 28_000),
    # Thép - vật liệu
    "HPG": ("CTCP Tập đoàn Hòa Phát", "Thép & Vật liệu", "HOSE", 27_000),
    "HSG": ("CTCP Tập đoàn Hoa Sen", "Thép & Vật liệu", "HOSE", 18_000),
    "NKG": ("CTCP Thép Nam Kim", "Thép & Vật liệu", "HOSE", 15_000),
    # Tiêu dùng - bán lẻ
    "VNM": ("CTCP Sữa Việt Nam", "Tiêu dùng", "HOSE", 60_000),
    "MSN": ("CTCP Tập đoàn Masan", "Tiêu dùng", "HOSE", 78_000),
    "SAB": ("Tổng CTCP Bia - Rượu - NGK Sài Gòn", "Tiêu dùng", "HOSE", 50_000),
    "MWG": ("CTCP Đầu tư Thế Giới Di Động", "Bán lẻ", "HOSE", 65_000),
    "PNJ": ("CTCP Vàng bạc Đá quý Phú Nhuận", "Bán lẻ", "HOSE", 85_000),
    "FRT": ("CTCP Bán lẻ Kỹ thuật số FPT", "Bán lẻ", "HOSE", 170_000),
    # Công nghệ
    "FPT": ("CTCP FPT", "Công nghệ", "HOSE", 120_000),
    "CMG": ("CTCP Tập đoàn Công nghệ CMC", "Công nghệ", "HOSE", 42_000),
    # Năng lượng - tiện ích
    "GAS": ("Tổng Công ty Khí Việt Nam", "Năng lượng", "HOSE", 68_000),
    "PLX": ("Tập đoàn Xăng dầu Việt Nam", "Năng lượng", "HOSE", 37_000),
    "POW": ("Tổng Công ty Điện lực Dầu khí VN", "Năng lượng", "HOSE", 12_500),
    "REE": ("CTCP Cơ Điện Lạnh", "Năng lượng", "HOSE", 68_000),
    "PVS": ("Tổng CTCP Dịch vụ Kỹ thuật Dầu khí", "Năng lượng", "HNX", 33_000),
    # Hóa chất - nông nghiệp - công nghiệp
    "DGC": ("CTCP Tập đoàn Hóa chất Đức Giang", "Hóa chất", "HOSE", 100_000),
    "DCM": ("CTCP Phân bón Dầu khí Cà Mau", "Hóa chất", "HOSE", 36_000),
    "GVR": ("Tập đoàn Công nghiệp Cao su VN", "Công nghiệp", "HOSE", 30_000),
    "BMP": ("CTCP Nhựa Bình Minh", "Công nghiệp", "HOSE", 120_000),
    # Vận tải - logistics - bảo hiểm
    "VJC": ("CTCP Hàng không VietJet", "Hàng không & Logistics", "HOSE", 100_000),
    "GMD": ("CTCP Gemadept", "Hàng không & Logistics", "HOSE", 62_000),
    "BVH": ("Tập đoàn Bảo Việt", "Bảo hiểm", "HOSE", 50_000),
}

INDEXES = {"VNINDEX": ("Chỉ số VN-Index", "Chỉ số", "HOSE", 1_300.0),
           "VN30": ("Chỉ số VN30", "Chỉ số", "HOSE", 1_400.0),
           "HNXINDEX": ("Chỉ số HNX-Index", "Chỉ số", "HNX", 240.0),
           "UPCOMINDEX": ("Chỉ số UPCoM-Index", "Chỉ số", "UPCOM", 100.0)}

VN30 = ["ACB", "BCM", "BID", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG", "MBB", "MSN", "MWG",
        "PLX", "POW", "SAB", "SHB", "SSI", "STB", "TCB", "TPB", "VCB", "VHM", "VIB", "VIC",
        "VJC", "VNM", "VPB", "VRE", "SSB", "LPB"]


def info(ticker: str) -> dict:
    """Thông tin mã: danh mục theo dõi mặc định → danh sách niêm yết đầy đủ (KBS/Vietcap) → mặc định."""
    ticker = ticker.upper()
    if ticker in UNIVERSE:
        name, sector, exchange, ref = UNIVERSE[ticker]
    elif ticker in INDEXES:
        name, sector, exchange, ref = INDEXES[ticker]
    else:
        from .listing import lookup  # tránh import vòng
        hit = lookup(ticker)
        if hit:
            name, sector, exchange, ref = hit.get("name") or ticker, hit.get("sector") or "Khác", hit["exchange"], 25_000
        else:
            name, sector, exchange, ref = (ticker, "Khác", "HOSE", 25_000)
    return {"ticker": ticker, "name": name, "sector": sector, "exchange": exchange,
            "reference_price": ref, "in_vn30": ticker in VN30}


def is_listed(ticker: str) -> bool:
    """Mã hợp lệ để phân tích / đặt lệnh: trong danh mục mặc định, danh sách niêm yết, hoặc đã nhập file giá."""
    ticker = ticker.upper().strip()
    if ticker in UNIVERSE or ticker in INDEXES:
        return True
    from .listing import lookup
    if lookup(ticker):
        return True
    from .providers import _imported_history
    return _imported_history(ticker) is not None


def list_universe() -> list[dict]:
    return [info(t) for t in UNIVERSE]


def sectors() -> list[str]:
    return sorted({v[1] for v in UNIVERSE.values()})
