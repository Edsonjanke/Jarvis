/**
 * The model's answer, its accounting line, and its citations.
 */
export interface AnswerBlockProps {
  /** ask | brief | plan | histórico | remembered. Rendered as an Eyebrow. */
  kind?: string;
  /** The dot-separated accounting line: model, notes read, memory, skills, seconds. */
  meta?: string;
  /** Tooltip listing exactly what was recalled and which skills applied. */
  metaTitle?: string;
  /** The answer text. Kept as written — whiteSpace: pre-wrap. */
  body?: React.ReactNode;
  /** Hit the token ceiling. Adds the warn line under the body. */
  truncated?: boolean;
  /** Cite chips, preceded by an Eyebrow reading "Sources". */
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export declare function AnswerBlock(props: AnswerBlockProps): JSX.Element;
