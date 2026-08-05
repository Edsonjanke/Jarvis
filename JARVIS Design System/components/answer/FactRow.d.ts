/** A remembered fact, dated, in the operator's own words. */
export interface FactRowProps {
  /** ISO date — memory is dated, never "recently". */
  when: string;
  /** The fact as stored. Proportional face: these are the person's words. */
  text: string;
  /** Deletes the fact's file. Appears on hover. */
  onForget?: () => void;
  style?: React.CSSProperties;
}
export declare function FactRow(props: FactRowProps): JSX.Element;
