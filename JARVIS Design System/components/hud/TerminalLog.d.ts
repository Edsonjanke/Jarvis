export interface TerminalLine {
  /** Clock, "22:37:02". */
  at: string;
  /** Three-letter channel. sys and ok are accent/green, err is --crit. */
  tag: "sys" | "ok" | "info" | "warn" | "err";
  text: string;
}

export interface TerminalLogProps {
  /** Oldest first; the view pins itself to the newest line. */
  lines?: TerminalLine[];
  /** Shell prompt under the log. */
  prompt?: string;
  /** Solid caret while a process runs, blinking when idle. */
  busy?: boolean;
  /** Scroll height in px. */
  height?: number;
  style?: React.CSSProperties;
}

/** The console's live log — timestamp, channel tag, line. One per screen. */
export declare function TerminalLog(props: TerminalLogProps): JSX.Element;
