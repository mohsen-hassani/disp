import { createFileRoute } from '@tanstack/react-router';

import { PlantNewPage } from './-plant-new';

export const Route = createFileRoute('/_app/plants/new')({
  component: PlantNewPage,
  staticData: { title: 'New plant · DISP' },
});
