/** A failure, an absence or a warning. There is no success variant by design. */
export interface AlertProps {
  /** crit = the product cannot work; warn = something is degraded; info = a stage note. */
  level?: "crit" | "warn" | "info";
  /** One or two words, uppercased: Offline, Vault, Skipped, Microphone, Stage 5. */
  label: string;
  /** The sentence. Name the fix or the missing file; never apologise. */
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export declare function Alert(props: AlertProps): JSX.Element;
