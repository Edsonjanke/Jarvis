/** One file that matched what you typed, with the line it matched on. */
export interface ResultRowProps {
  type?: string;
  title: string;
  /** Path relative to the vault root, right-aligned in --ink-3. */
  where?: string;
  /** The matching text, in the proportional face because it is the file's own words. */
  snippet?: string;
  onClick?: () => void;
  style?: React.CSSProperties;
}
export declare function ResultRow(props: ResultRowProps): JSX.Element;
