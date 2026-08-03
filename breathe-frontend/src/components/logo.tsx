export function Logo({ size = 64 }: { size?: number }) {
  return (
    <div
      className="flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 64 64"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient id="lungGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#2563EB" />
            <stop offset="100%" stopColor="#7C3AED" />
          </linearGradient>
        </defs>
        {/* Left lung */}
        <path
          d="M28 12c0 0-4 6-4 14 0 8 2 14 2 18s-2 6-6 6-8-4-8-14 4-18 12-24c2 0 4 0 4 0z"
          fill="url(#lungGradient)"
          opacity="0.9"
        />
        {/* Right lung */}
        <path
          d="M36 12c0 0 4 6 4 14 0 8-2 14-2 18s2 6 6 6 8-4 8-14-4-18-12-24c-2 0-4 0-4 0z"
          fill="url(#lungGradient)"
          opacity="0.9"
        />
        {/* Trachea */}
        <rect x="30" y="6" width="4" height="14" rx="2" fill="url(#lungGradient)" />
        {/* Bronchi */}
        <path
          d="M32 20L28 24M32 20L36 24"
          stroke="url(#lungGradient)"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}