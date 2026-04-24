'use client';

export default function SoundwaveLoader({ className = '' }: { className?: string }) {
  return (
    <div className={`flex items-end justify-center gap-1 h-8 ${className}`}>
      {[1, 2, 3, 4, 5, 6, 7].map((i) => (
        <div
          key={i}
          className="w-1 bg-current rounded-full"
          style={{
            animation: `soundwave 1.2s ease-in-out infinite`,
            animationDelay: `${i * 0.1}s`,
            height: '20%',
          }}
        />
      ))}
      <style jsx>{`
        @keyframes soundwave {
          0%, 100% { height: 20%; opacity: 0.5; }
          50% { height: 100%; opacity: 1; }
        }
      `}</style>
    </div>
  );
}
