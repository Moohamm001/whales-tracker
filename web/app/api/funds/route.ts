import { NextResponse } from "next/server";
import { listFunds } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json({ funds: listFunds() });
}
