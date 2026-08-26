import { NextRequest, NextResponse } from "next/server";

const base = () => process.env.RESEARCH_API_URL ?? "http://localhost:8000";

export async function GET(request: NextRequest) {
  try {
    const response = await fetch(`${base()}/api/v1/governance-incidents?${request.nextUrl.searchParams.toString()}`, { cache: "no-store" });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const response = await fetch(`${base()}/api/v1/governance-incidents`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(await request.json()), cache: "no-store",
    });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 });
  }
}
