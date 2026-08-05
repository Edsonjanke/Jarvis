/** Two-line picker row: the name, and the reason under it. */
export interface BrainRowProps {
  /** Model label, tool server, skill name, or edit mode. */
  name: string;
  /** The reason line: "ligada", "falta ELEVENLABS_API_KEY", "propõe e espera você", "⚠ sem description". */
  note?: string;
  /** Current selection — accent text plus an inset 2px accent edge. */
  pressed?: boolean;
  /** A server with no credential cannot be switched on; say so in note. */
  disabled?: boolean;
  onClick?: () => void;
  style?: React.CSSProperties;
}
export declare function BrainRow(props: BrainRowProps): JSX.Element;
