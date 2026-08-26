import { NextRequest, NextResponse } from "next/server";

const endpoint = () => `${process.env.RESEARCH_API_URL ?? "http://localhost:8000"}/api/v1/governance-journal/items`;

export async function GET(request: NextRequest) {
  try {
    const upstream = new URL(endpoint());
    upstream.search = request.nextUrl.search;
    const response = await fetch(upstream, { cache: "no-store" });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const response = await fetch(endpoint(), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: await request.text(),
      cache: "no-store",
    });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 });
  }
}
