// Gọi REST API backend. Lỗi trả về dạng {detail: "..."} được ném thành Error có thông điệp tiếng Việt.
export class ApiError extends Error {}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `Lỗi ${res.status}`;
    let code: string | undefined;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
      code = j.code;
    } catch {
      /* ignore */
    }
    // truy cập từ xa hết phiên / chưa đặt mật khẩu → quay về màn hình đăng nhập
    if (code === "login_required" || code === "setup_required") window.dispatchEvent(new CustomEvent("auth-required"));
    throw new ApiError(msg);
  }
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("application/json") ? res.json() : (res.blob() as unknown)) as Promise<T>;
}

export const api = {
  get: <T = any>(url: string) => fetch(url).then((r) => handle<T>(r)),
  post: <T = any>(url: string, body?: unknown) =>
    fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) }).then((r) =>
      handle<T>(r)
    ),
  put: <T = any>(url: string, body?: unknown) =>
    fetch(url, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) }).then((r) =>
      handle<T>(r)
    ),
  patch: <T = any>(url: string, body?: unknown) =>
    fetch(url, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) }).then((r) =>
      handle<T>(r)
    ),
  del: <T = any>(url: string) => fetch(url, { method: "DELETE" }).then((r) => handle<T>(r)),
  form: <T = any>(url: string, form: FormData) => fetch(url, { method: "POST", body: form }).then((r) => handle<T>(r)),
};

export function download(url: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}
