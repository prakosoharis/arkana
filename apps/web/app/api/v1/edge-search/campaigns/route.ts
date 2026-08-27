import { NextResponse } from "next/server";
const base=()=>process.env.RESEARCH_API_URL??"http://localhost:8000";
export async function GET(){try{const response=await fetch(`${base()}/api/v1/edge-search/campaigns`,{cache:"no-store"});return NextResponse.json(await response.json(),{status:response.status})}catch{return NextResponse.json({detail:"Research service is unavailable"},{status:503})}}
export async function POST(request:Request){try{const response=await fetch(`${base()}/api/v1/edge-search/campaigns`,{method:"POST",headers:{"content-type":"application/json"},body:await request.text(),cache:"no-store"});return NextResponse.json(await response.json(),{status:response.status})}catch{return NextResponse.json({detail:"Research service is unavailable"},{status:503})}}
