/** Opens the actual file behind a note, in a new tab. */
export interface OpenLinkProps {
  href: string;
  /** "Abrir o PDF" / "Abrir o arquivo" — say which kind of file it is. */
  children?: React.ReactNode;
  /** Why it is worth opening: a note whose text came back empty is exactly the one. */
  title?: string;
  style?: React.CSSProperties;
}
export declare function OpenLink(props: OpenLinkProps): JSX.Element;
