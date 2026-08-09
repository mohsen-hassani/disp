import { Link } from '@tanstack/react-router';
import type { ReactElement } from 'react';

import type { TileItem } from '../../api/generated';
import { useNavigableDomains } from '../../hooks/useNavigableDomains';
import { dateTime, relativeTime } from '../../lib/format';
import { translateTileHref } from './tileLinks';

interface TileItemRowProps {
  item: TileItem;
}

export function TileItemRow({ item }: TileItemRowProps): ReactElement {
  const navigable = useNavigableDomains();
  const href = item.href ? translateTileHref(item.href, navigable) : null;

  return (
    <li className="flex items-start justify-between gap-3 py-1.5">
      <div className="flex min-w-0 flex-col md:flex-row md:items-baseline md:gap-2">
        {href ? (
          <Link to={href} className="text-text truncate font-medium hover:underline">
            {item.primary}
          </Link>
        ) : (
          <span className="text-text truncate">{item.primary}</span>
        )}
        {item.secondary && <span className="text-text-muted text-xs">{item.secondary}</span>}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {item.timestamp && (
          <time
            dateTime={item.timestamp}
            title={dateTime(item.timestamp)}
            className="text-text-muted text-xs"
          >
            {relativeTime(item.timestamp)}
          </time>
        )}
        {item.done !== null && item.done !== undefined && (
          // §13.5's documented limitation: display-only, never interactive
          // — a real `disabled` input can't be toggled by click or
          // keyboard, so there's nothing further to wire up here.
          <input
            type="checkbox"
            checked={item.done}
            disabled
            readOnly
            aria-readonly="true"
            aria-label="Read-only in this version"
          />
        )}
      </div>
    </li>
  );
}
