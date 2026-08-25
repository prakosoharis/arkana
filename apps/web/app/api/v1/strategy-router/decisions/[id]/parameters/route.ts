import { NextRequest,NextResponse } from "next/server";
const endpoint=(id:string)=>`${process.env.RESEARCH_API_URL??"http://localhost:8000"}/api/v1/strategy-router/decisions/${id}/parameters`;
export async function GET(_request:NextRequest,{params}:{params:Promise<{id:string}>}){const{id}=await params;try{const response=await fetch(endpoint(id),{cache:"no-store"});return NextResponse.json(await response.json(),{status:response.status})}catch{return NextResponse.json({detail:"Research service is unavailable"},{status:503})}}
