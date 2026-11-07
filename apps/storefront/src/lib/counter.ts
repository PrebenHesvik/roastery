/** The counter in Bergen opens Monday to Saturday and is closed on Sundays. */
export function counterOpenOn(date: Date): boolean {
  const weekday = new Intl.DateTimeFormat('en', {
    weekday: 'short',
    timeZone: 'Europe/Oslo',
  }).format(date);
  return weekday !== 'Sun';
}
