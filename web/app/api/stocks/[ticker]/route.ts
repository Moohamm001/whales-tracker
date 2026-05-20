import { NextResponse } from "next/server";
import { getStockByTicker, getStockHolders } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET(_: Request, ctx: { params: { ticker: string } }) {
  const stock = getStockByTicker(ctx.params.ticker);
  if (!stock) return NextResponse.json({ error: "stock not found" }, { status: 404 });
  return NextResponse.json({
    stock,
    holders: getStockHolders(ctx.params.ticker),
  });
}
