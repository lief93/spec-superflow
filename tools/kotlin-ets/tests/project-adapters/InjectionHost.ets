import { Box, StateHolder } from './Models';

export const providedState: StateHolder = new StateHolder('injected');
export const providedBox: Box<StateHolder> = new Box<StateHolder>(providedState);
