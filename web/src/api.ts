// One fetch wrapper. It parses the contract's error shape { error: { code, message } } and exposes code and message.
export class ApiFailure extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function parse<T>(res: Response): Promise<T> {
  if (res.ok) return (res.status === 204 ? null : await res.json()) as T;
  let code = "HTTP_ERROR";
  let message = `Request failed with status ${res.status}.`;
  try {
    const body = (await res.json()) as { error?: { code?: string; message?: string } };
    if (body.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
    }
  } catch {
    // not JSON: keep the generic message
  }
  throw new ApiFailure(res.status, code, message);
}

export async function getJson<T>(path: string, params?: Record<string, string | undefined>): Promise<T> {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) if (v !== undefined && v !== "") q.set(k, v);
  const qs = q.toString();
  return parse<T>(await fetch(qs ? `${path}?${qs}` : path));
}

export async function postJson<T>(path: string): Promise<T> {
  return parse<T>(await fetch(path, { method: "POST" }));
}
