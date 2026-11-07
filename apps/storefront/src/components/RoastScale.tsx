import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { t } from '../i18n/t';
import { roastSteps } from '../lib/catalogue';

const STEPS = [20, 32, 44, 56, 68, 84, 100];

/**
 * The seven-step roast scale, light to dark. The steps of this roast fill when the scale first
 * comes into view; with no IntersectionObserver (or reduced motion, by CSS) they are filled at once.
 */
export function RoastScale({ roast, size = 'card' }: { roast: string; size?: 'card' | 'large' }) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(() => typeof IntersectionObserver !== 'function');
  const range = roastSteps(roast);

  useEffect(() => {
    const node = ref.current;
    if (node === null || typeof IntersectionObserver !== 'function') return;
    const reveal = () => {
      setShown(true);
      observer.disconnect();
    };
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) reveal();
      },
      { threshold: 0.25 },
    );
    observer.observe(node);
    // A scale already on screen when it mounts fills on the next frame.
    const frame = requestAnimationFrame(() => {
      const box = node.getBoundingClientRect();
      if (box.bottom > 0 && box.top < window.innerHeight) reveal();
    });
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, []);

  return (
    <div ref={ref} className={`roast roast--${size}`} data-shown={shown}>
      <div className="roast__steps" role="img" aria-label={t('roast.label', { roast })}>
        {STEPS.map((height, index) => {
          const on = range !== null && index >= range[0] && index <= range[1];
          return (
            <i
              key={height}
              className={on ? 'on' : undefined}
              style={{ height: `${String(height)}%`, '--step': index } as CSSProperties}
            />
          );
        })}
      </div>
      <div className="roast__ends" aria-hidden="true">
        <span>{t('roast.light')}</span>
        <span>{t('roast.dark')}</span>
      </div>
    </div>
  );
}
