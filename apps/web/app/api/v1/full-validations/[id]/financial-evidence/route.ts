import {NextRequest,NextResponse} from "next/server";
export async function GET(_:NextRequest,{params}:{params:Promise<{id:string}>}){const{id}=await params;const r=await fetch(`${process.env.RESEARCH_API_URL??"http://localhost:8000"}/api/v1/full-validations/${id}/financial-evidence`,{cache:"no-store"});return NextResponse.json(await r.json(),{status:r.status})}
