/**
 * The product's only ornament: a canvas dial that says what JARVIS is doing.
 */
export interface ReactorDialProps {
  /** idle | listening | thinking | speaking. Anything but idle lights the accent. */
  state?: "idle" | "listening" | "thinking" | "speaking";
  /** 0–1 microphone peak or synthetic level. Feeds the polar meter. */
  level?: number;
  /** The second line: 'diga "jarvis"', "transcribing", a voice name. */
  sub?: string;
  /** Diameter. 176 in the product; the drawing scales with it. */
  size?: number;
  style?: React.CSSProperties;
}
export declare function ReactorDial(props: ReactorDialProps): JSX.Element;
