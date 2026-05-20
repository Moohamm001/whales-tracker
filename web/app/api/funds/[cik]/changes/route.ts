import { NextResponse } from "next/server";
import { getFund, getChanges } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET(_: Request, ctx: { params: { cik: string } }) {
  const fund = getFund(ctx.params.cik);
  if (!fund) return NextResponse.json({ error: "fund not found" }, { status: 404 });
  return NextResponse.json({ fund, changes: getChanges(ctx.params.cik) });
}
