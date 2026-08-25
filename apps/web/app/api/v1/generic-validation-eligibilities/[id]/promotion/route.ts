import { NextRequest, NextResponse } from "next/server";

const endpoint = (id: string) => `${process.env.RESEARCH_API_URL ?? "http://localhost:8000"}/api/v1/generic-validation-eligibilities/${id}/promotion`;
async function forward(response: Response) { return NextResponse.json(await response.json(), { status: response.status }); }
export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) { const { id } = await params; try { return forward(await fetch(endpoint(id), { cache: "no-store" })); } catch { return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 }); } }
export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) { const { id } = await params; try { return forward(await fetch(`${process.env.RESEARCH_API_URL ?? "http://localhost:8000"}/api/v1/generic-validation-eligibilities/${id}/promotions`, { method: "POST", headers: { "content-type": "application/json" }, body: await request.text(), cache: "no-store" })); } catch { return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 }); } }
