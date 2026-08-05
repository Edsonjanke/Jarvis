export interface HudFrameProps {
  /** Uppercase section label sitting in the top rule. */
  label?: string;
  /** Small right-aligned readout inside the top rule (a count, a unit). */
  right?: string;
  /** Close the block with a mirrored rule below the content. */
  foot?: boolean;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

/**
 * The v2 panel: a labelled rule with a diagonal cut, content hanging beneath.
 * Replaces v1's four-sided plate. Never draw a box around HUD content.
 */
export declare function HudFrame(props: HudFrameProps): JSX.Element;
