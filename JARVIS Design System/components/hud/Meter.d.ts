export interface MeterProps {
  /** Short uppercase label, 3–4 characters (CPU, RAM, NET). */
  label: string;
  /** 0–100. */
  value?: number;
  /** Overrides the "NN%" readout at the end (e.g. "2.4 TB/s"). */
  display?: string;
  /** Bar colour. Status tones are reserved for real thresholds. */
  tone?: "accent" | "warn" | "crit" | "muted";
  /** Cut the bar into 3px ticks. Default true. */
  segmented?: boolean;
  style?: React.CSSProperties;
}

/** A labelled load bar with a value at the end — CPU, RAM, disk, throughput. */
export declare function Meter(props: MeterProps): JSX.Element;
