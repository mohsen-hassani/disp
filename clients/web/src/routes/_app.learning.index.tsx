import { createFileRoute } from '@tanstack/react-router';

import { CourseList } from '../components/learning/CourseList';

export const Route = createFileRoute('/_app/learning/')({
  component: CourseList,
  staticData: { title: 'Learning · DISP' },
});
