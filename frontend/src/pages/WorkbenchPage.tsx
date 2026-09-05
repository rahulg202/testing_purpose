import { useParams } from 'react-router-dom';
import { Workbench } from '@/components/workbench/Workbench';

export function WorkbenchPage() {
  const { caseId } = useParams<{ caseId: string }>();

  if (!caseId) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-gray-500">No case selected</p>
      </div>
    );
  }

  return <Workbench caseId={caseId} />;
}
