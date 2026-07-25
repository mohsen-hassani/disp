import type { ReactElement } from 'react';

interface FallbackWidgetProps {
  name: string;
}

// §14.3 rule 5: an unsupported schema construct — including nesting past
// the three-level depth cap — renders disabled rather than crashing or
// silently dropping the field. Forward compatibility matters: a future
// module may emit a construct this client predates.
export function FallbackWidget({ name }: FallbackWidgetProps): ReactElement {
  return (
    <input id={name} type="text" disabled value="This setting can't be edited here." readOnly />
  );
}
