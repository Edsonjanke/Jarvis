/** Shown only while a conversation is in progress; clears it back to nothing. */
export interface ThreadBarProps {
  /** Default "conversa em andamento". */
  label?: string;
  onNew?: () => void;
  style?: React.CSSProperties;
}
export declare function ThreadBar(props: ThreadBarProps): JSX.Element;
