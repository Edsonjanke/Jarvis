/** A row in the history list: when, what you asked, what it cost. */
export interface TurnRowProps {
  /** Locale timestamp, tabular. */
  when: string;
  question: string;
  /** "6 citações · 318 tokens · sonnet-4.6" */
  meta?: string;
  /** Reopens the answer AND rejoins that conversation. */
  onOpen?: () => void;
  /** Omit to make the row undeletable. Appears on hover. */
  onDelete?: () => void;
  style?: React.CSSProperties;
}
export declare function TurnRow(props: TurnRowProps): JSX.Element;
