export interface IconProps {
  /** Lucide icon name, kebab-case: "mic", "database", "settings", "terminal". */
  name: string;
  /** Box size in px. 15 in tiles, 13 inline. */
  size?: number;
  /** Stroke weight. 1.7 by default — thinner than Lucide's stock 2. */
  strokeWidth?: number;
  style?: React.CSSProperties;
}

/**
 * A Lucide glyph, drawn inline with stroke: currentColor. A flagged
 * substitution: the source codebase contains no icon set of its own. The path
 * data lives in the component and in assets/icons/, not on a CDN.
 */
export declare function Icon(props: IconProps): JSX.Element;
