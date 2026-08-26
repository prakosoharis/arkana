import { NextResponse } from "next/server";

const endpoint = `${process.env.RESEARCH_API_URL ?? "http://localhost:8000"}/api/v1/governance-journal/source-contract`;

export async function GET() {
  try {
    const response = await fetch(endpoint, { cache: "no-store" });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 });
  }
}
