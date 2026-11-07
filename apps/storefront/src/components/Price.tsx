import { moneyParts, spokenMoney, type Amount } from '../lib/money';

const DIGITS = new Set(['integer', 'fraction']);

/**
 * A price as set and as read aloud (the currency's name). Only the digits are tabular: the face's
 * tabular point and comma are a figure wide, which reads as a gap.
 */
export function Price({ value, className }: { value: Amount; className?: string }) {
  return (
    <span className={className === undefined ? 'num' : `num ${className}`}>
      <span aria-hidden="true">
        {moneyParts(value).map((part, index) =>
          DIGITS.has(part.type) ? (
            <span key={index} className="tnum">
              {part.value}
            </span>
          ) : (
            part.value
          ),
        )}
      </span>
      <span className="visually-hidden">{spokenMoney(value)}</span>
    </span>
  );
}
