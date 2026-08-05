/** One note in a list: links, hubs, a traced path. */
export interface RowProps {
  type?: string;
  /** The note title. Truncates with an ellipsis; never wraps. */
  label: string;
  /** Right-hand figure — degree, count, size. --ink-3, 10px. */
  tail?: string | number;
  /** Link direction glyph: "→" out, "←" in. */
  dir?: string;
  /** Step number, used only in the shortest-path list. */
  step?: number;
  selected?: boolean;
  onClick?: () => void;
  style?: React.CSSProperties;
}
export declare function Row(props: RowProps): JSX.Element;
