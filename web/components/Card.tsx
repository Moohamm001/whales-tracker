import React from "react";

type Props = {
  title?: string;
  subtitle?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  pad?: boolean;
};

export default function Card({
  title,
  subtitle,
  right,
  children,
  className = "",
  pad = true,
}: Props) {
  return (
    <section
      className={`bg-card border border-line rounded shadow-card ${className}`}
    >
      {(title || right) && (
        <header className="px-5 py-3 border-b border-line flex items-center justify-between">
          <div>
            {title && (
              <h2 className="text-slate text-base font-semibold leading-tight">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="text-muted text-xs mt-0.5">{subtitle}</p>
            )}
          </div>
          {right && <div className="text-xs text-muted">{right}</div>}
        </header>
      )}
      <div className={pad ? "p-5" : ""}>{children}</div>
    </section>
  );
}
