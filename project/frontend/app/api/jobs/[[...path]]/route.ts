type Context = { params: Promise<{ path?: string[] }> };

async function forward(request: Request, context: Context) {
  const { path = [] } = await context.params;
  const resource = path.join("/");
  const allowed = request.method === "GET" ? /^(\d+)?$/.test(resource)
    : request.method === "POST" && /^(collection|\d+\/retry)$/.test(resource);
  if (!allowed) return Response.json({ detail: "Job endpoint not found" }, { status: 404 });
  const backend = process.env.BACKEND_API_URL ?? "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${backend}/api/v1/jobs${resource ? `/${resource}` : ""}${new URL(request.url).search}`, {
      method: request.method,
      headers: { "Content-Type": "application/json" },
      body: request.method === "POST" ? await request.text() : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json({ detail: "Cannot reach the job service. Check that the backend is running." }, { status: 502 });
  }
}

export const GET = forward;
export const POST = forward;
