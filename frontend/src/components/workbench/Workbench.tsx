import { useEffect, useState } from 'react';
import { SourcePane } from './SourcePane';
import { FieldList } from './FieldList';
import type { CaseData } from '@/types/case';

interface WorkbenchProps {
  caseId: string;
}

export function Workbench({ caseId }: WorkbenchProps) {
  const [caseData, setCaseData] = useState<CaseData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedFieldPath, setSelectedFieldPath] = useState<string | null>(null);

  useEffect(() => {
    setIsLoading(true);
    setError(null);
    fetch(`/api/v1/cases/${caseId}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Case not found: ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setCaseData(data);
        setIsLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setIsLoading(false);
      });
  }, [caseId]);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-200 border-t-primary-600" />
      </div>
    );
  }

  if (error || !caseData) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <p className="text-sm text-red-600">{error || 'Failed to load case'}</p>
          <p className="mt-2 text-xs text-gray-500">Case ID: {caseId}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* Source pane — left */}
      <div className="w-1/2 border-r border-gray-200 overflow-auto">
        <SourcePane
          caseData={caseData}
          highlightedFieldPath={selectedFieldPath}
        />
      </div>

      {/* Field list — right */}
      <div className="w-1/2 overflow-auto">
        <FieldList
          caseData={caseData}
          onFieldSelect={setSelectedFieldPath}
          selectedFieldPath={selectedFieldPath}
        />
      </div>
    </div>
  );
}
