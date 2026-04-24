'use client';

import { useEffect, useRef } from 'react';

export default function CustomCursor() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (window.innerWidth < 768) return;
    
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let width = window.innerWidth;
    let height = window.innerHeight;
    
    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      // High-DPI support
      const dpr = window.devicePixelRatio || 1;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.scale(dpr, dpr);
    };
    resize();
    window.addEventListener('resize', resize);

    let mouse = { x: width / 2, y: height / 2 };
    let smoothMouse = { x: width / 2, y: height / 2 };
    let isHovering = false;

    const onMouseMove = (e: MouseEvent) => {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    };

    const updateHoverState = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      const isClickable = target.tagName.toLowerCase() === 'a' || 
                          target.tagName.toLowerCase() === 'button' ||
                          target.closest('button') ||
                          target.closest('a') ||
                          target.closest('.feature-card') ||
                          target.closest('.step-card') ||
                          target.classList.contains('magnetic');
      isHovering = !!isClickable;
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseover', updateHoverState);

    // Particle System
    class Particle {
      x: number;
      y: number;
      vx: number;
      vy: number;
      angle: number;
      radius: number;
      orbitSpeed: number;
      orbitRadius: number;
      baseOpacity: number;
      
      constructor() {
        this.x = width / 2;
        this.y = height / 2;
        this.vx = 0;
        this.vy = 0;
        this.angle = Math.random() * Math.PI * 2;
        this.radius = Math.random() * 1.5 + 0.5; // Particle size
        this.orbitSpeed = (Math.random() - 0.5) * 0.05;
        this.orbitRadius = Math.random() * 20 + 5;
        this.baseOpacity = Math.random() * 0.5 + 0.3;
      }

      update(targetX: number, targetY: number, hover: boolean) {
        // Orbit math
        this.angle += hover ? this.orbitSpeed * 3 : this.orbitSpeed;
        const currentTargetRadius = hover ? this.orbitRadius * 2 : this.orbitRadius;
        
        const tx = targetX + Math.cos(this.angle) * currentTargetRadius;
        const ty = targetY + Math.sin(this.angle) * currentTargetRadius;

        // Spring physics
        const dx = tx - this.x;
        const dy = ty - this.y;
        
        // When hovering, particles fly in faster and cluster tighter
        const spring = hover ? 0.15 : 0.08;
        const friction = hover ? 0.7 : 0.85;

        this.vx += dx * spring;
        this.vy += dy * spring;
        this.vx *= friction;
        this.vy *= friction;

        this.x += this.vx;
        this.y += this.vy;
      }

      draw() {
        // Drawing the particle
        ctx!.beginPath();
        ctx!.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
        ctx!.fillStyle = `rgba(255, 255, 255, ${isHovering ? this.baseOpacity + 0.2 : this.baseOpacity})`;
        ctx!.fill();
      }
    }

    const numParticles = 45;
    const particles: Particle[] = [];
    for (let i = 0; i < numParticles; i++) {
      particles.push(new Particle());
    }

    let animationFrameId: number;
    const loop = () => {
      // Clear canvas
      ctx.clearRect(0, 0, width, height);

      // Smooth mouse interpolation for the center point
      smoothMouse.x += (mouse.x - smoothMouse.x) * 0.2;
      smoothMouse.y += (mouse.y - smoothMouse.y) * 0.2;

      // Draw exact center dot
      ctx.beginPath();
      ctx.arc(smoothMouse.x, smoothMouse.y, 1.5, 0, Math.PI * 2);
      ctx.fillStyle = 'white';
      ctx.fill();

      // Update and draw particles
      particles.forEach(p => {
        p.update(smoothMouse.x, smoothMouse.y, isHovering);
        p.draw();
      });

      animationFrameId = requestAnimationFrame(loop);
    };

    loop();

    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseover', updateHoverState);
      window.removeEventListener('resize', resize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  if (typeof window !== 'undefined' && window.innerWidth < 768) return null;

  return (
    <canvas 
      ref={canvasRef} 
      className="fixed inset-0 pointer-events-none z-[9999]"
      style={{ mixBlendMode: 'difference' }}
    />
  );
}
