// One fetch wrapper. It parses the contract's error shape { error: { code, message } } and exposes code and message.
export class ApiFailure extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function parse(res) {
  if (res.ok) return (res.status === 204 ? null : await res.json());
  let code = "HTTP_ERROR";
  let message = `Request failed with status ${res.status}.`;
  try {
    const body = (await res.json());
    if (body.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
    }
  } catch {
    // not JSON: keep the generic message
  }
  throw new ApiFailure(res.status, code, message);
}

export async function getJson(path, params) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) if (v !== undefined && v !== "") q.set(k, v);
  const qs = q.toString();
  return parse(await fetch(qs ? `${path}?${qs}` : path));
}

export async function postJson(path) {
  return parse (await fetch(path, { method: "POST" }));
}
