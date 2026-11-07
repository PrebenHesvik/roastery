import { useEffect, useRef } from 'react';

interface Drop {
  x: number;
  y: number;
  length: number;
  speed: number;
  layer: 0 | 1 | 2;
}

/** Horizontal drift per pixel of fall: the rain comes in on the wind, at a slant. */
const SLANT = 0.2;
const MAX_DROPS = 140;
const AREA_PER_DROP = 9000;
const LAYER_ALPHA = [0.35, 0.65, 1] as const;

function makeDrop(width: number, height: number, anywhere: boolean): Drop {
  const layer = Math.floor(Math.random() * 3) as 0 | 1 | 2;
  const length = 10 + layer * 7 + Math.random() * 8;
  return {
    x: Math.random() * (width + height * SLANT) - height * SLANT,
    y: anywhere ? Math.random() * height : -length - Math.random() * height * 0.3,
    length,
    speed: 520 + layer * 180 + Math.random() * 120,
    layer,
  };
}

function prefersStill(): boolean {
  return (
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

/**
 * Quiet rain behind the first viewport. One canvas, at most 140 drops in three alpha layers (three
 * strokes a frame), the pixel ratio capped at 2. It stops when it is off-screen or the tab is
 * hidden, and under reduced motion it draws one still frame and never animates.
 */
export function RainCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const context = canvas?.getContext('2d') ?? null;
    if (canvas === null || context === null) return;

    let drops: Drop[] = [];
    let width = 0;
    let height = 0;
    let frame = 0;
    let last = 0;
    let visible = true;
    let colour = '233 230 223';
    let alpha = 0.16;

    const readColours = () => {
      const style = getComputedStyle(canvas);
      colour = style.getPropertyValue('--rain').trim() || colour;
      alpha = Number.parseFloat(style.getPropertyValue('--rain-alpha')) || alpha;
    };

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      const count = Math.min(MAX_DROPS, Math.round((width * height) / AREA_PER_DROP));
      drops = Array.from({ length: count }, () => makeDrop(width, height, true));
    };

    const draw = () => {
      context.clearRect(0, 0, width, height);
      context.lineWidth = 1;
      context.lineCap = 'round';
      for (const layer of [0, 1, 2] as const) {
        context.strokeStyle = `rgb(${colour} / ${String(alpha * LAYER_ALPHA[layer])})`;
        context.beginPath();
        for (const drop of drops) {
          if (drop.layer !== layer) continue;
          context.moveTo(drop.x, drop.y);
          context.lineTo(drop.x + drop.length * SLANT, drop.y + drop.length);
        }
        context.stroke();
      }
    };

    const step = (now: number) => {
      const seconds = last === 0 ? 0 : Math.min((now - last) / 1000, 0.05);
      last = now;
      for (let index = 0; index < drops.length; index += 1) {
        const drop = drops[index];
        if (drop === undefined) continue;
        drop.y += drop.speed * seconds;
        drop.x += drop.speed * seconds * SLANT;
        if (drop.y > height) drops[index] = makeDrop(width, height, false);
      }
      draw();
      frame = requestAnimationFrame(step);
    };

    const start = () => {
      if (frame !== 0 || prefersStill() || !visible || document.hidden) return;
      last = 0;
      frame = requestAnimationFrame(step);
    };

    const stop = () => {
      if (frame !== 0) cancelAnimationFrame(frame);
      frame = 0;
    };

    const repaint = () => {
      readColours();
      resize();
      draw();
      stop();
      start();
    };

    repaint();

    const sizes = typeof ResizeObserver === 'function' ? new ResizeObserver(repaint) : null;
    sizes?.observe(canvas);

    const seen =
      typeof IntersectionObserver === 'function'
        ? new IntersectionObserver((entries) => {
            visible = entries.some((entry) => entry.isIntersecting);
            if (visible) start();
            else stop();
          })
        : null;
    seen?.observe(canvas);

    const onVisibility = () => {
      if (document.hidden) stop();
      else start();
    };
    document.addEventListener('visibilitychange', onVisibility);

    const motion =
      typeof window.matchMedia === 'function'
        ? window.matchMedia('(prefers-reduced-motion: reduce)')
        : null;
    motion?.addEventListener('change', repaint);

    const themes = new MutationObserver(() => {
      readColours();
      draw();
    });
    themes.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

    return () => {
      stop();
      sizes?.disconnect();
      seen?.disconnect();
      themes.disconnect();
      motion?.removeEventListener('change', repaint);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, []);

  return <canvas ref={ref} className="rain" aria-hidden="true" />;
}
