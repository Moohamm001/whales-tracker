import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Whales Tracker — Track hedge fund 13F filings",
  description:
    "Track holdings, quarterly changes, and trends of the world's most-watched investors.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-bg text-slate">
        {/* Top nav */}
        <nav className="bg-navy text-white border-b border-navyDk shadow-card">
          <div className="max-w-7xl mx-auto px-6 h-14 flex items-center">
            <Link
              href="/"
              className="text-white font-semibold text-lg tracking-tight hover:no-underline hover:text-white flex items-center gap-2"
            >
              <span className="inline-block w-7 h-7 rounded bg-sky text-white text-xs font-bold flex items-center justify-center">
                WT
              </span>
              <span>Whales Tracker</span>
            </Link>
            <div className="ml-8 flex items-center gap-1 text-sm">
              <Link
                href="/"
                className="px-3 py-2 text-white/85 hover:text-white hover:bg-navyDk rounded transition-colors hover:no-underline"
              >
                Funds
              </Link>
              <Link
                href="/movers"
                className="px-3 py-2 text-white/85 hover:text-white hover:bg-navyDk rounded transition-colors hover:no-underline"
              >
                Top Movers
              </Link>
              <a
                href="/api/funds"
                className="px-3 py-2 text-white/85 hover:text-white hover:bg-navyDk rounded transition-colors hover:no-underline"
              >
                API
              </a>
            </div>
            <div className="ml-auto text-xs text-white/60">
              Source: <span className="text-white/80">SEC EDGAR 13F-HR</span>
            </div>
          </div>
        </nav>

        <main className="max-w-7xl mx-auto px-6 py-6">{children}</main>

        <footer className="border-t border-line bg-card mt-12">
          <div className="max-w-7xl mx-auto px-6 py-5 text-xs text-muted flex flex-wrap gap-4 justify-between">
            <span>
              Whales Tracker &middot; Data from{" "}
              <a
                href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=13F-HR"
                target="_blank"
                rel="noreferrer"
              >
                SEC EDGAR
              </a>
              {" "}&middot; Tickers via{" "}
              <a href="https://www.openfigi.com/" target="_blank" rel="noreferrer">
                OpenFIGI
              </a>
            </span>
            <span className="text-muted">
              Estimates derived from 13F filings &middot; not investment advice
            </span>
          </div>
        </footer>
      </body>
    </html>
  );
}
