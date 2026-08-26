import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const response = await fetch(`${process.env.RESEARCH_API_URL ?? "http://localhost:8000"}/api/v1/governance-incidents/${id}/resolutions`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(await request.json()), cache: "no-store",
    });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 });
  }
}
