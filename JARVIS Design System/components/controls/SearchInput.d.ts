/** Filters a list already on screen — history, and nothing else so far. */
export interface SearchInputProps {
  value: string;
  onChange?: (value: string) => void;
  /** Enter. The list filters on submit, not on every keystroke. */
  onSubmit?: (value: string) => void;
  placeholder?: string;
  style?: React.CSSProperties;
}
export declare function SearchInput(props: SearchInputProps): JSX.Element;
