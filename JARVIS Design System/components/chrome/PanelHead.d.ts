/** Eyebrow + one control, the header of every section inside a Panel. */
export interface PanelHeadProps {
  /** Section name. Rendered as an Eyebrow — uppercase, 0.17em, --ink-3. */
  label: string;
  /** Right-hand slot: a ghost Button, a count, or nothing. */
  children?: React.ReactNode;
  /** Adds the hairline rule under the header. Default false. */
  rule?: boolean;
  style?: React.CSSProperties;
}
export declare function PanelHead(props: PanelHeadProps): JSX.Element;
