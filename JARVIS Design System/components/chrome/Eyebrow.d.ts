/** The section marker: a 6x1px dash and ten uppercase pixels. */
export interface EyebrowProps {
  children?: React.ReactNode;
  /** Optional trailing count, e.g. "(4)" or "none". Rendered untracked, --ink-3. */
  count?: string | number;
  style?: React.CSSProperties;
}
export declare function Eyebrow(props: EyebrowProps): JSX.Element;
