import { numericCase, onceCase, receiverOnce, emptyCase } from './OverloadCases';

export function overloadSdkCheck(): number {
  const trace: Array<number> = [];
  if (emptyCase(0, trace) || emptyCase(1, trace)) return -1;
  if (onceCase(trace) !== 6 || receiverOnce(trace) !== 18) return -2;
  return numericCase(0, trace) + numericCase(1, trace) + numericCase(2, trace) + numericCase(3, trace);
}
