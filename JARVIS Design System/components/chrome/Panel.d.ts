/**
 * The floating translucent plate every region of JARVIS sits on.
 */
export interface PanelProps {
  /** Pins the plate to the left rail (342px), the right rail (268px), or leaves it in flow. */
  side?: "left" | "right" | "free";
  /** Scroll inside the plate rather than on the page. Default true. */
  scroll?: boolean;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export declare function Panel(props: PanelProps): JSX.Element;
