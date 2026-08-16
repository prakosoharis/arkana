import { NextRequest, NextResponse } from "next/server";

export async function POST(request:NextRequest){const u=new URL("/api/v1/ai/draft",process.env.RESEARCH_API_URL??"http://localhost:8000");try{const r=await fetch(u,{method:"POST",headers:{"content-type":"application/json"},body:await request.text(),cache:"no-store"});return NextResponse.json(await r.json(),{status:r.status});}catch{return NextResponse.json({detail:"Research service is unavailable"},{status:503});}}
