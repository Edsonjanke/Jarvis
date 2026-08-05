/** Right-aligned tabular readout — the vault's own vital signs. */
export interface StatListProps {
  /** Pairs. The literal value "missing" is rendered in --warn. */
  rows: Array<[string, string]>;
  style?: React.CSSProperties;
}
export declare function StatList(props: StatListProps): JSX.Element;
