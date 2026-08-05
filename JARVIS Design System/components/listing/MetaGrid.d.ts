/** Key/value metadata under a note title. */
export interface MetaGridProps {
  /** Pairs, in order. A key of "warning" renders its value in --warn. */
  rows: Array<[string, string]>;
  style?: React.CSSProperties;
}
export declare function MetaGrid(props: MetaGridProps): JSX.Element;
