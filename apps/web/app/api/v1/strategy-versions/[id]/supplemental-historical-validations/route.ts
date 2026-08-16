import { NextRequest, NextResponse } from "next/server";

export async function GET(_: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const response = await fetch(`${process.env.RESEARCH_API_URL ?? "http://localhost:8000"}/api/v1/strategy-versions/${id}/supplemental-historical-validations`, { cache: "no-store" });
  return NextResponse.json(await response.json(), { status: response.status });
}

export async function POST(_: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const response = await fetch(`${process.env.RESEARCH_API_URL ?? "http://localhost:8000"}/api/v1/strategy-versions/${id}/supplemental-historical-validation`, { method: "POST", cache: "no-store" });
  return NextResponse.json(await response.json(), { status: response.status });
}
