import { dispatchCase, pipelineCase, receiverOnce } from './MethodCases';
import { MethodConsumer } from './MethodConsumers';
import { MethodProjector } from './MethodContracts';
import { MethodPipeline } from './MethodPipeline';
import { MethodDerived } from './MethodProjectors';

export function genericMethodSdkCheck(): number {
  const trace: Array<number> = [];
  const projector: MethodProjector<number> = new MethodDerived<number>(trace);
  const cursor = new MethodPipeline<number>(projector).mapped<string>([1, 2],
    (value: number): string => value.toString(), (value: string): boolean => value.length > 0);
  const first: string = new MethodConsumer().next<string>(cursor);
  return first.length + dispatchCase(2, trace).length + pipelineCase(trace) + receiverOnce(trace);
}
