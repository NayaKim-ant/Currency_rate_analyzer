export async function GET(request: Request) {
  const backend = process.env.BACKEND_API_URL ?? "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${backend}/api/v1/forecasts${new URL(request.url).search}`, {
      cache: "no-store", signal: AbortSignal.timeout(10000),
    });
    return new Response(await response.text(), { status: response.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
  } catch (error) {
    const timedOut = error instanceof Error && error.name === "TimeoutError";
    return Response.json({ detail: timedOut
      ? "The backend is taking too long to respond. Forecasts will retry automatically."
      : "The backend is unavailable. Start the backend server; forecasts will retry automatically." },
    { status: timedOut ? 504 : 502 });
  }
}
