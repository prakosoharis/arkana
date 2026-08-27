import { NextResponse } from "next/server";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const response = await fetch(`${process.env.RESEARCH_API_URL ?? "http://localhost:8000"}/api/v1/controlled-learning/proposals/${id}/verification`, { cache: "no-store" });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 });
  }
}
