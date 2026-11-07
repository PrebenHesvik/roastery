import { dropKey, keyFor } from '../lib/attempt';
import { api } from './client';
import { Problem, type Schemas } from './queries';

export type CheckoutBody = Schemas['CheckoutRequest'];
export type Outcome = Schemas['SandboxPaymentRequest']['outcome'];

export type Placed =
  | { kind: 'placed'; order: Schemas['PlacedOrder'] }
  | { kind: 'price_changed'; quote: Schemas['Quote'] }
  | { kind: 'out_of_stock'; productId: string; onHand: number }
  | { kind: 'problem'; problem: Problem };

export type Paid =
  | { kind: 'paid'; payment: Schemas['SandboxPayment'] }
  | { kind: 'declined' }
  | { kind: 'outage' }
  | { kind: 'already_paid' }
  | { kind: 'problem'; problem: Problem };

const CHECKOUT = 'checkout';
const payingSlot = (token: string) => `pay.${token}`;

/** A reply the server stored under the key, or not: only a 503 or no reply at all is not. */
function stored(status: number | undefined): boolean {
  return status !== undefined && status !== 503;
}

/**
 * Places the order: one key per attempt (ADR 0019). The key is dropped on any stored reply, so
 * the next try, after a change of price or of stock, is a new attempt.
 */
export async function placeOrder(body: CheckoutBody): Promise<Placed> {
  const key = await keyFor(CHECKOUT, body);
  let status: number | undefined;
  try {
    const { data, error, response } = await api.POST('/checkout', {
      params: { header: { 'Idempotency-Key': key } },
      body,
    });
    status = response.status;
    if (data !== undefined) return { kind: 'placed', order: data };
    const problem = new Problem(error, response.status);
    if (problem.code === 'PriceChanged') {
      return { kind: 'price_changed', quote: problem.body['quote'] as Schemas['Quote'] };
    }
    if (problem.code === 'OutOfStock') {
      return {
        kind: 'out_of_stock',
        productId: String(problem.body['product_id']),
        onHand: Number(problem.body['on_hand']),
      };
    }
    return { kind: 'problem', problem };
  } catch {
    return { kind: 'problem', problem: new Problem(null, 0) };
  } finally {
    if (stored(status)) dropKey(CHECKOUT);
  }
}

/**
 * A sandbox payment attempt. A declined reply is stored under its key, so every attempt after a
 * reply takes a new key; only an outage keeps it, for "try again".
 */
export async function pay(token: string, outcome: Outcome): Promise<Paid> {
  const slot = payingSlot(token);
  const key = await keyFor(slot, { token, outcome });
  let status: number | undefined;
  try {
    const { data, error, response } = await api.POST('/sandbox/payments', {
      params: { header: { 'Idempotency-Key': key } },
      body: { token, outcome },
    });
    status = response.status;
    if (data !== undefined) return { kind: 'paid', payment: data };
    const problem = new Problem(error, response.status);
    switch (problem.code) {
      case 'ProviderRefused':
        return { kind: 'declined' };
      case 'ProviderUnavailable':
        return { kind: 'outage' };
      case 'IllegalTransition':
        return { kind: 'already_paid' };
      default:
        return { kind: 'problem', problem };
    }
  } catch {
    return { kind: 'problem', problem: new Problem(null, 0) };
  } finally {
    if (stored(status)) dropKey(slot);
  }
}
