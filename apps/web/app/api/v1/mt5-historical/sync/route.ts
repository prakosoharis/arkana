import { NextResponse } from "next/server";

const base = `${process.env.RESEARCH_API_URL ?? "http://localhost:8000"}/api/v1/mt5-historical/sync`;

export async function POST() {
  try {
    const response = await fetch(base, { method: "POST", cache: "no-store" });
    const contentType = response.headers.get("content-type") ?? "";
    const body = contentType.includes("application/json")
      ? await response.json()
      : { detail: `Historical sync failed in research service (HTTP ${response.status}).` };
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 });
  }
}
