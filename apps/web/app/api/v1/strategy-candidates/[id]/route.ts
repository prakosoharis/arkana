import { NextRequest, NextResponse } from "next/server";

const root = `${process.env.RESEARCH_API_URL ?? "http://localhost:8000"}/api/v1/strategy-candidates`;

export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try { const response = await fetch(`${root}/${id}`, { cache: "no-store" }); return NextResponse.json(await response.json(), { status: response.status }); }
  catch { return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 }); }
}

export async function PUT(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try { const response = await fetch(`${root}/${id}`, { method: "PUT", headers: { "content-type": "application/json" }, body: await request.text(), cache: "no-store" }); return NextResponse.json(await response.json(), { status: response.status }); }
  catch { return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 }); }
}
