import '../styles/globals.css'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'ClipPods AI Video Clipper | AI Podcast Highlights for Creators',
  description: 'ClipPods AI Video Clipper. Turn long podcasts into high-impact, viral short clips automatically. Uses advanced AI to segment and clip content, built exclusively for regional creators.',
  keywords: 'ClipPods AI Video Clipper, AI clip generation for creators, podcast clips, AI clipping, Tamil podcasts, Hindi podcasts, creator economy AI tool',
  authors: [{ name: 'ClipPods' }],
  robots: 'index, follow',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet" />
      </head>
      <body>
        {children}
      </body>
    </html>
  )
}
