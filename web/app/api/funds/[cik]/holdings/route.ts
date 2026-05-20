import { NextResponse } from "next/server";
import { getFund, getHoldingsWithInsights } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET(_: Request, ctx: { params: { cik: string } }) {
  const fund = getFund(ctx.params.cik);
  if (!fund) return NextResponse.json({ error: "fund not found" }, { status: 404 });
  return NextResponse.json({ fund, holdings: getHoldingsWithInsights(ctx.params.cik) });
}
