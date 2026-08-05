export interface TileProps {
  /** Lucide icon name. See Icon — this is a flagged substitution. */
  icon?: string;
  /** One or two short uppercase words. */
  label: string;
  /** Sticky on state. Expressed with aria-pressed, not a different colour. */
  active?: boolean;
  /** Not wired yet: keeps the label, drops to --ink-3, border goes dashed. */
  disabled?: boolean;
  /** Tooltip — on a disabled tile, say which step wires it. */
  title?: string;
  onClick?: () => void;
  style?: React.CSSProperties;
}

/**
 * A square action in the rail grid — glyph over a two-line label. Outlined,
 * never filled; hover and pressed resolve to the same accent triple.
 */
export declare function Tile(props: TileProps): JSX.Element;
