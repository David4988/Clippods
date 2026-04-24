'use client';
import { useState } from 'react';
import { submitWaitlist } from '@/lib/api';

export default function WaitlistForm() {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('Podcast Creator');
  const [platform, setPlatform] = useState('YouTube');
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await submitWaitlist({ email, role, platform });
      if (res.success) {
        setSubmitted(true);
      } else {
        alert(res.message || 'Error joining waitlist');
      }
    } catch {
      alert('Network error joining waitlist');
    }
    setLoading(false);
  };

  if (submitted) {
    return (
      <div className="bg-surface border border-border p-6 rounded-xl text-center">
        <div className="text-lg font-semibold mb-1">You&apos;re on the list! 🎉</div>
        <div className="text-sm text-muted">We&apos;ll notify you when ClipPods Video Clipper launches.</div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 text-left">
      <input
        type="email"
        placeholder="your@email.com"
        required
        value={email}
        onChange={e => setEmail(e.target.value)}
        className="bg-surface border border-border p-3 rounded-lg text-white outline-none focus:border-white/40 transition-colors text-sm"
      />
      <select
        value={role}
        onChange={e => setRole(e.target.value)}
        className="bg-surface border border-border p-3 rounded-lg text-white outline-none focus:border-white/40 transition-colors text-sm"
      >
        <option value="Podcast Creator">Podcast Creator</option>
        <option value="Streamer">Streamer</option>
        <option value="Marketer">Marketer</option>
        <option value="Content Creator">Content Creator</option>
        <option value="Other">Other</option>
      </select>
      <select
        value={platform}
        onChange={e => setPlatform(e.target.value)}
        className="bg-surface border border-border p-3 rounded-lg text-white outline-none focus:border-white/40 transition-colors text-sm"
      >
        <option value="YouTube">YouTube</option>
        <option value="TikTok">TikTok</option>
        <option value="Instagram">Instagram</option>
        <option value="Twitter/X">Twitter/X</option>
        <option value="LinkedIn">LinkedIn</option>
      </select>
      <button
        type="submit"
        disabled={loading}
        className="bg-white text-black p-3 rounded-lg mt-1 font-semibold transition-all duration-200 disabled:opacity-40 cp-btn-hover"
      >
        {loading ? 'Joining…' : 'Join Waitlist for AI Features'}
      </button>
    </form>
  );
}
