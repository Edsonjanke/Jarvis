/**
 * The only button in JARVIS. Etched, uppercase, two sizes.
 */
export interface ButtonProps {
  /** key = the action row under the ask bar; ghost = inline inside a panel header. */
  size?: "key" | "ghost";
  /** Latched state. Renders aria-pressed and the accent triple. Omit for a plain action. */
  pressed?: boolean;
  /** Keeps the label, dims to --ink-3, switches the border to dashed. */
  disabled?: boolean;
  /** Say WHY it is disabled here — "wired in step 4, with voice". */
  title?: string;
  onClick?: (event: React.MouseEvent<HTMLButtonElement>) => void;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export declare function Button(props: ButtonProps): JSX.Element;
