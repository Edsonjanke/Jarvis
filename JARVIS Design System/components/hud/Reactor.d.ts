export interface ReactorProps {
  /** Square edge in px. 420 on the console stage. */
  size?: number;
  /** idle crawls the state arc at 6s; anything else sweeps it at 0.8s. */
  state?: "idle" | "listening" | "thinking" | "speaking";
  /** 0–1. Drives brightness of the whole stack, not its speed. */
  level?: number;
  /** Vertical squash of the ring plane. 1 is head-on; 0.46 is the console's
   *  perspective — the stack lies on a plane seen at an angle. */
  tilt?: number;
  style?: React.CSSProperties;
}

/**
 * The v2 reactor: seven concentric rings — tick bezels, gapped arcs, a slow
 * orbit — lying on a plane seen in perspective, around a triangle core that
 * stands upright. One per screen, dead centre. It carries state (idle /
 * working) and nothing else.
 */
export declare function Reactor(props: ReactorProps): JSX.Element;
