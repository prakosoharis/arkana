import { NextRequest, NextResponse } from "next/server";
const base=()=>process.env.RESEARCH_API_URL??"http://localhost:8000";
export async function POST(request:NextRequest){try{const r=await fetch(`${base()}/api/v1/research-contracts/compile`,{method:"POST",headers:{"content-type":"application/json"},body:await request.text(),cache:"no-store"});return NextResponse.json(await r.json(),{status:r.status});}catch{return NextResponse.json({detail:"Research service is unavailable"},{status:503});}}
