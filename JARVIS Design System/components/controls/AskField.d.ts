/**
 * The single input in the product: search as you type, ask on Enter.
 */
export interface AskFieldProps {
  /** The left tag. "find" below stage 3, "ask" once the model is wired. */
  mode?: string;
  value: string;
  onChange?: (value: string) => void;
  /** Enter. Runs the question, not the search. */
  onSubmit?: (value: string) => void;
  /** Rotates through the vault's biggest hubs in the real product. */
  placeholder?: string;
  /** Right-hand keyboard hint. Default "enter". */
  hint?: string;
  style?: React.CSSProperties;
}
export declare function AskField(props: AskFieldProps): JSX.Element;
