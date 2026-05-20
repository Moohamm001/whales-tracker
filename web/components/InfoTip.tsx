export default function InfoTip({ text }: { text: string }) {
  return (
    <span className="tt" tabIndex={0} role="button" aria-label="More info">
      <svg
        width="12"
        height="12"
        viewBox="0 0 20 20"
        fill="currentColor"
        className="text-muted hover:text-sky"
      >
        <path
          fillRule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zM9 8a1 1 0 112 0v5a1 1 0 11-2 0V8zm1-4a1 1 0 100 2 1 1 0 000-2z"
          clipRule="evenodd"
        />
      </svg>
      <span className="tt-body">{text}</span>
    </span>
  );
}
