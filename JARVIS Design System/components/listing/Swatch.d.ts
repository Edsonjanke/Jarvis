/** A 9px taxonomy dot. The product's entire icon set. */
export interface SwatchProps {
  /** One of the seven validated node types; anything else falls back to --t-other. */
  type?: "client" | "project" | "meeting" | "invoice" | "person" | "note" | "reference" | "other";
  /** Escape hatch for a non-taxonomy colour, e.g. a status dot. */
  colour?: string;
  /** Diameter in px. 9 everywhere in the product; 14 in specimens. */
  size?: number;
  style?: React.CSSProperties;
}
export declare function Swatch(props: SwatchProps): JSX.Element;
export declare function typeColour(type: string): string;
