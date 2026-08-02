import { type ReactElement, useId, useState } from 'react';

import { todayDay } from '../../lib/calendar';
import { SubmitButton } from '../feedback/SubmitButton';
import { useToast } from '../feedback/ToastProvider';
import { inputClass, labelClass, primaryButtonClass } from './styles';
import { useAddInterval } from './usePlantMutations';

interface AddIntervalFormProps {
  plantId: string;
  offline: boolean;
}

/**
 * "Water, every 15 days, last done on ___".
 *
 * `last_done_on` defaults to today, which makes the first occurrence land
 * `interval_days` from now. Back-dating it is what lets someone enter a plant
 * they already watered last week and get an accurate first due date rather
 * than one that is silently a week late.
 */
export function AddIntervalForm({ plantId, offline }: AddIntervalFormProps): ReactElement {
  const nameId = useId();
  const daysId = useId();
  const lastDoneId = useId();
  const today = todayDay();

  const [name, setName] = useState('');
  const [days, setDays] = useState('15');
  const [lastDone, setLastDone] = useState(today);

  const addInterval = useAddInterval(plantId);
  const { showToast } = useToast();

  const intervalDays = Number(days);
  const valid = name.trim().length > 0 && Number.isInteger(intervalDays) && intervalDays >= 1;

  return (
    <form
      className="border-border bg-surface-sunken flex flex-wrap items-end gap-3 rounded-md border p-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (!valid) return;
        addInterval.mutate(
          {
            name: name.trim(),
            interval_days: intervalDays,
            last_done_on: lastDone || null,
          },
          {
            onSuccess: (interval) => {
              showToast(`${interval.name} scheduled for ${interval.next_due_on}`, 'success');
              setName('');
              setDays('15');
              setLastDone(today);
            },
            onError: (problem) => showToast(problem.detail, 'error'),
          },
        );
      }}
    >
      <div className="min-w-[10rem] flex-1">
        <label htmlFor={nameId} className={labelClass}>
          Action
        </label>
        <input
          id={nameId}
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={80}
          required
          placeholder="Water"
          className={inputClass}
        />
      </div>

      <div className="w-28">
        <label htmlFor={daysId} className={labelClass}>
          Every (days)
        </label>
        <input
          id={daysId}
          type="number"
          min={1}
          max={3650}
          value={days}
          onChange={(event) => setDays(event.target.value)}
          required
          className={inputClass}
        />
      </div>

      <div className="w-44">
        <label htmlFor={lastDoneId} className={labelClass}>
          Last done
        </label>
        <input
          id={lastDoneId}
          type="date"
          value={lastDone}
          max={today}
          onChange={(event) => setLastDone(event.target.value)}
          className={inputClass}
        />
      </div>

      <SubmitButton
        submitting={addInterval.isPending}
        disabled={!valid || offline}
        className={primaryButtonClass}
      >
        Add interval
      </SubmitButton>
    </form>
  );
}
