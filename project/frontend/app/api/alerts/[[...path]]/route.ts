type Context = { params: Promise<{ path?: string[] }> };

async function forward(request: Request, context: Context) {
  const { path = [] } = await context.params;
  const resource = path.join("/");
  const allowed = request.method === "GET" ? /^(rules)?$/.test(resource)
    : request.method === "POST" ? /^(rules|evaluate)$/.test(resource)
    : /^(PATCH|DELETE)$/.test(request.method) && /^rules\/\d+$/.test(resource);
  if (!allowed) return Response.json({ detail: "Alert endpoint not found" }, { status: 404 });
  const backend = process.env.BACKEND_API_URL ?? "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${backend}/api/v1/alerts${resource ? `/${resource}` : ""}${new URL(request.url).search}`, {
      method: request.method,
      headers: { "Content-Type": "application/json" },
      body: request.method === "GET" || request.method === "DELETE" ? undefined : await request.text(),
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
    if (response.status === 204) return new Response(null, { status: 204 });
    return new Response(await response.text(), {
      status: response.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json({ detail: "Cannot reach the alert service. Check that the backend is running." }, { status: 502 });
  }
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const DELETE = forward;
