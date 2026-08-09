import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { IntervalDueBadge, PlantDueBadge } from '../../../src/components/plants/DueBadge';

describe('PlantDueBadge', () => {
  it('shows an overdue badge when max_days_overdue > 0', () => {
    render(<PlantDueBadge dueCount={2} maxDaysOverdue={3} nextDueOn="2026-01-01" />);
    expect(screen.getByText('Up to 3 days overdue')).toBeInTheDocument();
  });

  it('shows a due-today badge when due but not overdue', () => {
    render(<PlantDueBadge dueCount={1} maxDaysOverdue={0} nextDueOn="2026-01-01" />);
    expect(screen.getByText('Due today')).toBeInTheDocument();
  });

  it('shows the next due date when nothing is due', () => {
    render(<PlantDueBadge dueCount={0} maxDaysOverdue={0} nextDueOn="2026-08-20" />);
    expect(screen.getByText(/Next due/)).toBeInTheDocument();
  });

  it('shows a fallback when there is no scheduled care at all', () => {
    render(<PlantDueBadge dueCount={0} maxDaysOverdue={0} nextDueOn={null} />);
    expect(screen.getByText('No care scheduled')).toBeInTheDocument();
  });
});

describe('IntervalDueBadge', () => {
  it('shows days overdue for a positive value', () => {
    render(<IntervalDueBadge daysOverdue={5} nextDueOn="2026-01-01" />);
    expect(screen.getByText('5 days overdue')).toBeInTheDocument();
  });

  it('shows "Due today" for zero', () => {
    render(<IntervalDueBadge daysOverdue={0} nextDueOn="2026-01-01" />);
    expect(screen.getByText('Due today')).toBeInTheDocument();
  });

  it('shows the future due date for a negative value (not yet due)', () => {
    render(<IntervalDueBadge daysOverdue={-4} nextDueOn="2026-08-20" />);
    expect(screen.getByText(/Due/)).toBeInTheDocument();
  });
});
