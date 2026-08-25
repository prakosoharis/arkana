import { NextRequest, NextResponse } from "next/server";

const endpoint = (id: string) => `${process.env.RESEARCH_API_URL ?? "http://localhost:8000"}/api/v1/strategy-versions/${id}/lifecycle-verification`;
async function forward(response: Response) { return NextResponse.json(await response.json(), { status: response.status }); }
export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) { const { id } = await params; try { return forward(await fetch(endpoint(id), { cache: "no-store" })); } catch { return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 }); } }
export async function POST(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) { const { id } = await params; try { return forward(await fetch(endpoint(id), { method: "POST", cache: "no-store" })); } catch { return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 }); } }
