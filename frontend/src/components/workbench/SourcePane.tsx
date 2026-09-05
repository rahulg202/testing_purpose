import type { CaseData } from '@/types/case';

interface SourcePaneProps {
  caseData: CaseData;
  highlightedFieldPath: string | null;
}

export function SourcePane({ caseData, highlightedFieldPath }: SourcePaneProps) {
  return (
    <div className="p-6">
      <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-4">
        Source Evidence
      </h2>

      {/* Source document display */}
      <div className="space-y-4">
        {caseData.source_records && caseData.source_records.length > 0 ? (
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <p className="text-xs text-gray-500 mb-2">
              Source: {caseData.source_records[0]}
            </p>
            {/* In Sprint 5 this becomes a PDF viewer with bbox highlighting */}
            <div className="prose prose-sm max-w-none">
              <p className="text-sm text-gray-700 whitespace-pre-wrap font-mono">
                {/* Source text will be populated from the SourceRecord raw_text */}
                Source document content will appear here once email intake is connected (Sprint 3).
                {highlightedFieldPath && (
                  <span className="block mt-4 text-xs text-primary-600 bg-primary-50 p-2 rounded">
                    Highlighting evidence for: {highlightedFieldPath}
                  </span>
                )}
              </p>
            </div>
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-gray-300 p-8 text-center">
            <p className="text-sm text-gray-500">No source documents linked</p>
          </div>
        )}
      </div>
    </div>
  );
}
