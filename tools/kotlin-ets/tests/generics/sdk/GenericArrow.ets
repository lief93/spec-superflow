export function genericArrowProbe(value: number): number {
  const keep: <U>(input: U) => U = <U>(input: U): U => input;
  return keep<number>(value);
}
