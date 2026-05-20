import React from "react";

type Props = {
  title?: string;
  children: React.ReactNode;
  color?: "cyan" | "yellow" | "green" | "magenta" | "white" | "dim";
  className?: string;
};

const COLOR: Record<string, { text: string; border: string }> = {
  cyan:    { text: "text-bbs-brcyan",    border: "border-bbs-brcyan" },
  yellow:  { text: "text-bbs-bryellow",  border: "border-bbs-bryellow" },
  green:   { text: "text-bbs-brgreen",   border: "border-bbs-brgreen" },
  magenta: { text: "text-bbs-brmagenta", border: "border-bbs-brmagenta" },
  white:   { text: "text-bbs-white",     border: "border-bbs-white" },
  dim:     { text: "text-bbs-dim",       border: "border-bbs-dim" },
};

/**
 * BBS box-drawing frame. Uses CSS double borders for the vertical edges and
 * inline ╔═╗╚═╝ characters for the corners — works at any width without
 * misalignment, and the title is styled like ╡ TITLE ╞ on the top border.
 */
export default function Frame({
  title,
  children,
  color = "cyan",
  className = "",
}: Props) {
  const c = COLOR[color];
  return (
    <section className={`my-3 ${className}`}>
      <div className={`flex items-center leading-none ${c.text}`}>
        <span>╔═</span>
        {title && (
          <>
            <span>╡ </span>
            <span className="text-bbs-bryellow font-bold tracking-wider">{title}</span>
            <span> ╞</span>
          </>
        )}
        <span
          className="flex-1 overflow-hidden whitespace-nowrap"
          style={{ borderTop: "2px double currentColor", marginLeft: 4, marginRight: 4 }}
          aria-hidden
        />
        <span>╗</span>
      </div>

      <div
        className={`${c.text} px-3 py-2`}
        style={{
          borderLeft: "2px double currentColor",
          borderRight: "2px double currentColor",
        }}
      >
        <div className="text-bbs-fg">{children}</div>
      </div>

      <div className={`flex items-center leading-none ${c.text}`}>
        <span>╚</span>
        <span
          className="flex-1 overflow-hidden whitespace-nowrap"
          style={{ borderTop: "2px double currentColor", marginLeft: 2, marginRight: 2 }}
          aria-hidden
        />
        <span>╝</span>
      </div>
    </section>
  );
}
