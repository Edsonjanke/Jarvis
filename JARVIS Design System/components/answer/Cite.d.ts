/** One cited note, as a chip under an answer. Clicking opens and centres it. */
export interface CiteProps {
  type?: string;
  /** The note title. The id goes in title= for the tooltip, never on screen. */
  title: string;
  onClick?: () => void;
  style?: React.CSSProperties;
}
export declare function Cite(props: CiteProps): JSX.Element;
