/** Type filter with its share of the vault drawn as a 2px bar. */
export interface TypeRowProps {
  /** Drives the dot and the bar colour. */
  type: string;
  /** Defaults to the type name, capitalised by CSS. */
  name?: string;
  count: number;
  /** 0–1, relative to the biggest type — not to the total. */
  share?: number;
  /** Switched on. Off drops the row to 36% and greys the bar. */
  on?: boolean;
  onClick?: () => void;
  style?: React.CSSProperties;
}
export declare function TypeRow(props: TypeRowProps): JSX.Element;
