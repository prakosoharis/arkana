import { NextResponse } from "next/server";
export async function GET(){const u=new URL("/api/v1/demo-validation",process.env.RESEARCH_API_URL??"http://localhost:8000");try{const r=await fetch(u,{cache:"no-store"});return NextResponse.json(await r.json(),{status:r.status});}catch{return NextResponse.json({detail:"Research service is unavailable"},{status:503});}}
