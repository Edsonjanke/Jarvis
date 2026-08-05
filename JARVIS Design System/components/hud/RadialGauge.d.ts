export interface RadialGaugeProps {
  /** 0–100. */
  value?: number;
  /** Outer diameter in px. 54 in a rail. */
  size?: number;
  /** Tiny word under the number inside the ring (e.g. "memória"). */
  label?: string;
  /** Rows rendered to the right of the ring. */
  caption?: React.ReactNode;
  style?: React.CSSProperties;
}

/** A ring gauge with its percentage inside — used once per rail, for a share of a whole. */
export declare function RadialGauge(props: RadialGaugeProps): JSX.Element;
