import { NextResponse } from "next/server";
import { getTopMovers } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const limit = Math.min(parseInt(url.searchParams.get("limit") ?? "50", 10) || 50, 200);
  return NextResponse.json({ movers: getTopMovers(limit) });
}
